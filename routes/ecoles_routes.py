import re
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_super_admin

bp = Blueprint('ecoles_routes', __name__, url_prefix='/api/ecoles')

DUREE_ESSAI_JOURS = 30


def _slugifier(texte):
    """Transforme un nom d'école en code court utilisable pour la connexion
    (minuscules, sans accent, tirets) — ex: 'École Les Palmiers' -> 'ecole-les-palmiers'."""
    import unicodedata
    txt = unicodedata.normalize('NFD', texte).encode('ascii', 'ignore').decode('ascii')
    txt = re.sub(r'[^a-zA-Z0-9]+', '-', txt).strip('-').lower()
    return txt or 'ecole'


@bp.route('/publique', methods=['GET'])
def liste_ecoles_publique():
    """Annuaire public des écoles clientes — accessible sans connexion, pour permettre
    à un visiteur de retrouver le site de son école. Ne renvoie que des informations
    non sensibles (nom, code, contact), et exclut les écoles suspendues."""
    rows = db.execute(
        """SELECT id, nom, code, email_contact, telephone_contact
           FROM ecoles WHERE actif=1 AND statut_licence!='suspendue' ORDER BY nom"""
    ).fetchall()
    result = []
    for e in rows:
        d = dict(e)
        s = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='ecole_logo'", (e['id'],)).fetchone()
        d['logo_url'] = s['valeur'] if s else None
        result.append(d)
    return jsonify(result)


@bp.route('/verifier-code', methods=['GET'])
def verifier_code_disponible():
    """Vérifie si un code établissement est déjà pris — utilisé en direct pendant
    la saisie du formulaire d'inscription, pour un retour immédiat à l'utilisateur."""
    code = request.args.get('code', '')
    if not code:
        return jsonify({'disponible': False})
    existe = db.execute("SELECT 1 FROM ecoles WHERE code=?", (code,)).fetchone()
    return jsonify({'disponible': not bool(existe)})


@bp.route('/inscription', methods=['POST'])
def inscription_ecole():
    """Inscription en libre-service d'une nouvelle école cliente : crée l'école
    (en période d'essai) et son tout premier compte administrateur. Route publique,
    accessible sans connexion préalable — c'est le point d'entrée pour un nouveau client."""
    body = request.get_json(silent=True) or {}
    nom_ecole = (body.get('nom_ecole') or '').strip()
    admin_full_name = (body.get('admin_full_name') or '').strip()
    admin_username = (body.get('admin_username') or '').strip()
    admin_password = body.get('admin_password') or ''
    email_contact = (body.get('email_contact') or '').strip()

    if not nom_ecole or not admin_full_name or not admin_username or not admin_password:
        return jsonify({'error': "Nom de l'école, nom de l'administrateur, identifiant et mot de passe sont requis"}), 400
    if len(admin_password) < 6:
        return jsonify({'error': 'Le mot de passe doit contenir au moins 6 caractères'}), 400

    # Génère un code établissement unique à partir du nom (avec suffixe numérique si collision)
    code_base = _slugifier(nom_ecole)
    code = code_base
    suffixe = 2
    while db.execute("SELECT 1 FROM ecoles WHERE code=?", (code,)).fetchone():
        code = f"{code_base}-{suffixe}"
        suffixe += 1

    from datetime import datetime, timedelta
    date_expiration = (datetime.now() + timedelta(days=DUREE_ESSAI_JOURS)).strftime('%Y-%m-%d')

    cur = db.execute(
        """INSERT INTO ecoles (nom, code, email_contact, telephone_contact, statut_licence, date_expiration_licence)
           VALUES (?,?,?,?, 'essai', ?)""",
        (nom_ecole, code, email_contact, body.get('telephone_contact'), date_expiration),
    )
    ecole_id = cur.lastrowid

    try:
        db.execute(
            "INSERT INTO users (ecole_id,username,password_hash,full_name,role,email) VALUES (?,?,?,?,?,?)",
            (ecole_id, admin_username, generate_password_hash(admin_password), admin_full_name, 'admin', email_contact or None),
        )
        db.commit()
    except Exception as e:
        # Échec de création de l'admin (ex: identifiant déjà pris DANS cette école neuve,
        # improbable mais possible si redemandé) -> on annule aussi la création de l'école
        db.execute("DELETE FROM ecoles WHERE id=?", (ecole_id,))
        db.commit()
        return jsonify({'error': f"Impossible de créer le compte administrateur : {e}"}), 400

    log_action(None, 'inscription_ecole', 'ecole', str(ecole_id), {'nom': nom_ecole, 'code': code})
    return jsonify({
        'ecole_id': ecole_id, 'code': code, 'nom': nom_ecole,
        'essai_jusquau': date_expiration,
        'message': f"Bienvenue ! Votre école est prête. Notez bien votre code établissement : « {code} » — il vous sera demandé à chaque connexion.",
    }), 201


@bp.route('', methods=['GET'])
@require_auth
@require_super_admin
def list_ecoles():
    """Liste toutes les écoles clientes avec quelques indicateurs de volumétrie,
    pour la supervision par le super-administrateur."""
    rows = db.execute("SELECT * FROM ecoles ORDER BY created_at DESC").fetchall()
    result = []
    for e in rows:
        d = dict(e)
        d['nb_utilisateurs'] = db.execute("SELECT COUNT(*) as c FROM users WHERE ecole_id=?", (e['id'],)).fetchone()['c']
        d['nb_eleves'] = db.execute("SELECT COUNT(*) as c FROM eleves WHERE ecole_id=? AND statut='actif'", (e['id'],)).fetchone()['c']
        result.append(d)
    return jsonify(result)


@bp.route('/<int:ecole_id>', methods=['GET'])
@require_auth
@require_super_admin
def get_ecole(ecole_id):
    e = db.execute("SELECT * FROM ecoles WHERE id=?", (ecole_id,)).fetchone()
    if not e:
        return jsonify({'error': 'Introuvable'}), 404
    d = row_to_dict(e)
    d['nb_utilisateurs'] = db.execute("SELECT COUNT(*) as c FROM users WHERE ecole_id=?", (ecole_id,)).fetchone()['c']
    d['nb_eleves'] = db.execute("SELECT COUNT(*) as c FROM eleves WHERE ecole_id=? AND statut='actif'", (ecole_id,)).fetchone()['c']
    d['nb_personnel'] = db.execute("SELECT COUNT(*) as c FROM personnel WHERE ecole_id=?", (ecole_id,)).fetchone()['c']
    return jsonify(d)


@bp.route('/<int:ecole_id>', methods=['PUT'])
@require_auth
@require_super_admin
def update_ecole(ecole_id):
    """Modifie le statut de licence ou les informations d'une école cliente
    (activer, suspendre, prolonger l'essai, etc.)."""
    body = request.get_json(silent=True) or {}
    existing = db.execute("SELECT * FROM ecoles WHERE id=?", (ecole_id,)).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404

    statut = body.get('statut_licence')
    if statut and statut not in ('essai', 'active', 'suspendue', 'expiree'):
        return jsonify({'error': 'Statut de licence invalide'}), 400

    db.execute(
        """UPDATE ecoles SET nom=COALESCE(?,nom), email_contact=COALESCE(?,email_contact),
           telephone_contact=COALESCE(?,telephone_contact), statut_licence=COALESCE(?,statut_licence),
           date_expiration_licence=COALESCE(?,date_expiration_licence),
           actif=COALESCE(?,actif) WHERE id=?""",
        (body.get('nom'), body.get('email_contact'), body.get('telephone_contact'), statut,
         body.get('date_expiration_licence'), (1 if body.get('actif') else 0) if 'actif' in body else None, ecole_id),
    )
    db.commit()
    log_action(g.user, 'modification', 'ecole', str(ecole_id),
               {'motif': body.get('motif'), 'avant': {'statut_licence': existing['statut_licence']}, 'apres': body})
    row = db.execute("SELECT * FROM ecoles WHERE id=?", (ecole_id,)).fetchone()
    return jsonify(row_to_dict(row))
