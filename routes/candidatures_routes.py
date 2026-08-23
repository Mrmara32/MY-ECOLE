from datetime import datetime
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash

from database import db, gen_id, rows_to_list, row_to_dict, log_action, next_matricule_personnel, matricule_lock, ecole_id_depuis_code
from auth import require_auth, require_role
from email_service import generer_jeton, envoyer_confirmation_enseignant

bp = Blueprint('candidatures_routes', __name__, url_prefix='/api/candidatures')


@bp.route('', methods=['POST'])
def soumettre_candidature():
    """Soumission PUBLIQUE — accessible sans connexion (en ligne) pour qu'un enseignant
    puisse postuler lui-même en indiquant les matières et horaires qu'il souhaite enseigner.
    Le candidat choisit dès maintenant son identifiant et mot de passe : si sa candidature
    est acceptée, son compte n'attendra plus qu'une confirmation par e-mail pour être actif."""
    body = request.get_json(silent=True) or {}
    nom, prenom = body.get('nom'), body.get('prenom')
    email = (body.get('email') or '').strip()
    username_souhaite = (body.get('username_souhaite') or '').strip()
    password = body.get('password') or ''
    if not nom or not prenom:
        return jsonify({'error': 'Nom et prénom requis'}), 400
    if not email or '@' not in email:
        return jsonify({'error': 'Une adresse e-mail valide est requise'}), 400
    if not username_souhaite:
        return jsonify({'error': 'Un identifiant de connexion est requis'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Le mot de passe doit contenir au moins 6 caractères'}), 400
    matieres = body.get('matieres')
    if isinstance(matieres, list):
        matieres = ', '.join(matieres)
    ecole_id = ecole_id_depuis_code(body.get('code_ecole') or request.args.get('ecole'))

    if db.execute("SELECT 1 FROM users WHERE ecole_id=? AND username=?", (ecole_id, username_souhaite)).fetchone():
        return jsonify({'error': "Cet identifiant est déjà pris — choisissez-en un autre"}), 409

    cid = gen_id('cand')
    db.execute(
        """INSERT INTO candidatures_enseignants
           (id,ecole_id,nom,prenom,telephone,email,matieres,cycle,disponibilites,message,username_souhaite,password_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, ecole_id, nom, prenom, body.get('telephone'), email, matieres,
         body.get('cycle'), body.get('disponibilites'), body.get('message'),
         username_souhaite, generate_password_hash(password)),
    )
    db.commit()
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (cid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def list_candidatures():
    statut = request.args.get('statut')
    sql = "SELECT * FROM candidatures_enseignants WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if statut: sql += " AND statut=?"; params.append(statut)
    sql += " ORDER BY date_candidature DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/<c_id>', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def get_candidature(c_id):
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>/approuver', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def approuver_candidature(c_id):
    """Approuve la candidature : crée (ou met à jour) la fiche personnel correspondante
    avec les matières et disponibilités choisies par le candidat lui-même.
    Ces informations restent modifiables ensuite librement par l'administration."""
    body = request.get_json(silent=True) or {}
    c = db.execute("SELECT * FROM candidatures_enseignants WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    if c['statut'] != 'en_attente':
        return jsonify({'error': 'Cette candidature a déjà été traitée'}), 400

    pid = gen_id('p')
    derniere_erreur = None
    with matricule_lock:
        for _ in range(5):
            matricule = next_matricule_personnel(g.user['ecole_id'])
            try:
                db.execute(
                    "INSERT INTO personnel (id,ecole_id,nom,prenom,poste,matiere,telephone,email,cycle_enseignement,date_embauche,matricule) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, g.user['ecole_id'], c['nom'], c['prenom'], 'Enseignant', c['matieres'], c['telephone'], c['email'],
                     c['cycle'], datetime.now().strftime('%Y-%m-%d'), matricule),
                )
                db.commit()
                derniere_erreur = None
                break
            except Exception as e:
                derniere_erreur = e
                if 'matricule' not in str(e).lower():
                    return jsonify({'error': str(e)}), 400
                continue
    if derniere_erreur is not None:
        return jsonify({'error': str(derniere_erreur)}), 400
    db.execute(
        "UPDATE candidatures_enseignants SET statut='approuvee', personnel_id=?, approuve_par=?, date_approbation=CURRENT_TIMESTAMP WHERE id=? AND ecole_id=?",
        (pid, g.user['id'], c_id, g.user['ecole_id']),
    )

    # Crée le compte de connexion (inactif jusqu'à confirmation par e-mail) avec
    # l'identifiant et le mot de passe choisis par le candidat lui-même à la soumission.
    compte_cree = False
    if c['username_souhaite'] and c['password_hash']:
        deja_pris = db.execute(
            "SELECT 1 FROM users WHERE ecole_id=? AND username=?", (g.user['ecole_id'], c['username_souhaite'])
        ).fetchone()
        if not deja_pris:
            jeton = generer_jeton()
            cur = db.execute(
                "INSERT INTO users (ecole_id,username,password_hash,full_name,role,email,active,jeton_confirmation) "
                "VALUES (?,?,?,?,?,?,0,?)",
                (g.user['ecole_id'], c['username_souhaite'], c['password_hash'], f"{c['prenom']} {c['nom']}",
                 'enseignant', c['email'], jeton),
            )
            db.execute("UPDATE personnel SET user_id=? WHERE id=?", (cur.lastrowid, pid))
            nom_ecole_row = db.execute("SELECT nom FROM ecoles WHERE id=?", (g.user['ecole_id'],)).fetchone()
            envoyer_confirmation_enseignant(c['email'], c['prenom'], nom_ecole_row['nom'] if nom_ecole_row else 'votre école', jeton)
            compte_cree = True

    db.commit()
    log_action(g.user, 'approbation', 'candidature', c_id,
               {'nom': f"{c['prenom']} {c['nom']}", 'matieres': c['matieres'], 'compte_cree': compte_cree})
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>/rejeter', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def rejeter_candidature(c_id):
    body = request.get_json(silent=True) or {}
    c = db.execute("SELECT * FROM candidatures_enseignants WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        "UPDATE candidatures_enseignants SET statut='rejetee', approuve_par=?, date_approbation=CURRENT_TIMESTAMP WHERE id=? AND ecole_id=?",
        (g.user['id'], c_id, g.user['ecole_id']),
    )
    db.commit()
    log_action(g.user, 'rejet', 'candidature', c_id, {'nom': f"{c['prenom']} {c['nom']}", 'motif': body.get('motif')})
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_candidature(c_id):
    db.execute("DELETE FROM candidatures_enseignants WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/confirmer/<jeton>', methods=['GET'])
def confirmer_compte_enseignant(jeton):
    """Active le compte de connexion d'un enseignant après clic sur le lien reçu
    par e-mail suite à l'approbation de sa candidature. Route publique (le jeton,
    long et aléatoire, fait office de preuve d'identité)."""
    u = db.execute("SELECT * FROM users WHERE jeton_confirmation=?", (jeton,)).fetchone()
    if not u:
        return "Lien de confirmation invalide ou déjà utilisé.", 400
    db.execute("UPDATE users SET active=1, jeton_confirmation=NULL WHERE id=?", (u['id'],))
    db.commit()
    log_action(None, 'confirmation_email', 'utilisateur', str(u['id']), {'username': u['username']})
    from flask import redirect
    return redirect("/?compte_confirme=1")
