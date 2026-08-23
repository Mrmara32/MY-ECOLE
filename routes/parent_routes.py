from flask import Blueprint, jsonify, g, request
from werkzeug.security import generate_password_hash

from database import db, rows_to_list, gen_id, ecole_id_depuis_code, log_action
from auth import require_auth, require_role
from email_service import generer_jeton, envoyer_confirmation_parent

bp = Blueprint('parent_routes', __name__, url_prefix='/api/parent')


@bp.route('/inscription', methods=['POST'])
def inscription_parent():
    """Auto-inscription PUBLIQUE d'un compte parent — accessible sans connexion.
    Le matricule de l'enfant sert de preuve d'appartenance à l'établissement (il
    n'est normalement connu que des familles, via les documents remis par l'école) ;
    la confirmation par e-mail apporte une seconde vérification avant activation."""
    body = request.get_json(silent=True) or {}
    nom_complet = (body.get('nom_complet') or '').strip()
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''
    email = (body.get('email') or '').strip()
    matricule_enfant = (body.get('matricule_enfant') or '').strip()

    if not nom_complet or not username or not matricule_enfant:
        return jsonify({'error': "Nom complet, identifiant souhaité et matricule de l'enfant sont requis"}), 400
    if len(password) < 6:
        return jsonify({'error': 'Le mot de passe doit contenir au moins 6 caractères'}), 400
    if not email or '@' not in email:
        return jsonify({'error': "Une adresse e-mail valide est requise pour confirmer l'inscription"}), 400

    ecole_id = ecole_id_depuis_code(body.get('code_ecole') or request.args.get('ecole'))

    eleve = db.execute(
        "SELECT id, nom, prenom FROM eleves WHERE ecole_id=? AND matricule=?", (ecole_id, matricule_enfant)
    ).fetchone()
    if not eleve:
        return jsonify({'error': "Aucun élève ne correspond à ce matricule dans cet établissement — vérifiez le numéro communiqué par l'école"}), 404

    if db.execute("SELECT 1 FROM users WHERE ecole_id=? AND username=?", (ecole_id, username)).fetchone():
        return jsonify({'error': "Cet identifiant est déjà pris — choisissez-en un autre"}), 409

    jeton = generer_jeton()
    cur = db.execute(
        "INSERT INTO users (ecole_id,username,password_hash,full_name,role,email,active,jeton_confirmation) "
        "VALUES (?,?,?,?,?,?,0,?)",
        (ecole_id, username, generate_password_hash(password), nom_complet, 'parent', email, jeton),
    )
    user_id = cur.lastrowid
    db.execute("INSERT INTO parents_eleves (id,user_id,eleve_id) VALUES (?,?,?)", (gen_id('pe'), user_id, eleve['id']))
    db.commit()

    nom_ecole_row = db.execute("SELECT nom, code FROM ecoles WHERE id=?", (ecole_id,)).fetchone()
    nom_ecole = nom_ecole_row['nom'] if nom_ecole_row else 'votre école'
    code_ecole_email = nom_ecole_row['code'] if nom_ecole_row else None
    email_envoye = envoyer_confirmation_parent(email, nom_complet, nom_ecole, code_ecole_email, jeton)
    log_action(None, 'inscription_parent', 'utilisateur', str(user_id), {'nom': nom_complet, 'enfant': f"{eleve['prenom']} {eleve['nom']}"})

    return jsonify({
        'ok': True,
        'enfant_trouve': f"{eleve['prenom']} {eleve['nom']}",
        'email_envoye': email_envoye,
        'message': (
            f"Compte créé pour le suivi de {eleve['prenom']} {eleve['nom']} — un e-mail de confirmation "
            f"vient d'être envoyé à {email}, cliquez sur le lien qu'il contient pour l'activer."
            if email_envoye else
            "Compte créé, mais l'e-mail de confirmation n'a pas pu être envoyé — contactez l'école pour activer votre accès."
        ),
    }), 201


@bp.route('/confirmer/<jeton>', methods=['GET'])
def confirmer_parent(jeton):
    """Active un compte parent après clic sur le lien reçu par e-mail. Route publique
    (le jeton, long et aléatoire, fait office de preuve d'identité)."""
    u = db.execute("SELECT * FROM users WHERE jeton_confirmation=? AND role='parent'", (jeton,)).fetchone()
    if not u:
        return "Lien de confirmation invalide ou déjà utilisé.", 400
    db.execute("UPDATE users SET active=1, jeton_confirmation=NULL WHERE id=?", (u['id'],))
    db.commit()
    log_action(None, 'confirmation_email', 'utilisateur', str(u['id']), {'username': u['username']})
    from flask import redirect
    return redirect("/espace-parents.html?compte_confirme=1")


@bp.route('/mes-enfants', methods=['GET'])
@require_auth
@require_role('parent')
def mes_enfants():
    """Liste les élèves liés au compte parent actuellement connecté (auto-service,
    contrairement à /api/users/<id>/enfants qui est réservé à l'administration)."""
    rows = db.execute(
        """SELECT e.id, e.matricule, e.nom, e.prenom, e.classe, e.photo_url
           FROM parents_eleves pe JOIN eleves e ON e.id = pe.eleve_id
           WHERE pe.user_id=? ORDER BY e.nom""", (g.user['id'],)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/messages', methods=['GET'])
@require_auth
@require_role('parent')
def mes_messages():
    """Messages destinés au parent connecté : ceux adressés à l'un de ses enfants
    précisément, à la classe de l'un de ses enfants, ou diffusés à tous les parents."""
    mes_enfants = db.execute(
        "SELECT eleve_id FROM parents_eleves WHERE user_id=?", (g.user['id'],)
    ).fetchall()
    if not mes_enfants:
        return jsonify([])
    eleve_ids = [r['eleve_id'] for r in mes_enfants]
    classes = [r['classe'] for r in db.execute(
        f"SELECT DISTINCT classe FROM eleves WHERE id IN ({','.join(['?']*len(eleve_ids))}) AND classe IS NOT NULL",
        eleve_ids
    ).fetchall()]

    conditions = ["m.destinataire_type IN ('tous','tous_parents')"]
    params = []
    if eleve_ids:
        conditions.append(f"(m.destinataire_type='eleve' AND m.destinataire_id IN ({','.join(['?']*len(eleve_ids))}))")
        params += eleve_ids
    if classes:
        conditions.append(f"(m.destinataire_type='classe' AND m.destinataire_id IN ({','.join(['?']*len(classes))}))")
        params += classes

    sql = f"""SELECT m.*, u.full_name as expediteur_nom FROM messages m
              LEFT JOIN users u ON u.id=m.expediteur_id
              WHERE m.ecole_id=? AND ({' OR '.join(conditions)}) ORDER BY m.date_envoi DESC LIMIT 100"""
    rows = db.execute(sql, [g.user['ecole_id']] + params).fetchall()
    return jsonify(rows_to_list(rows))
