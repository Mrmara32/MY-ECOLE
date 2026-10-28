from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from database import db, rows_to_list, row_to_dict, log_action, gen_id
from securite import erreur_mot_de_passe
from auth import revoquer_sessions, require_auth, require_role

bp = Blueprint('users_routes', __name__, url_prefix='/api/users')

ROLES = ['admin', 'directeur', 'directeur_etudes', 'comptable', 'enseignant', 'secretaire', 'charge_communication', 'parent']


@bp.route('', methods=['GET'])
@require_auth
@require_role('admin')
def list_users():
    rows = db.execute(
        "SELECT id,username,full_name,role,email,telephone,civilite,active,created_at,last_login "
        "FROM users WHERE ecole_id=? ORDER BY created_at DESC", (g.user['ecole_id'],)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('', methods=['POST'])
@require_auth
@require_role('admin')
def create_user():
    body = request.get_json(silent=True) or {}
    username, password = body.get('username'), body.get('password')
    full_name, role = body.get('full_name'), body.get('role')
    email, telephone = body.get('email'), body.get('telephone')
    civilite = body.get('civilite') if body.get('civilite') in ('M.', 'Mme') else None

    if not username or not password or not full_name or not role:
        return jsonify({'error': 'Champs requis'}), 400
    if role not in ROLES:
        return jsonify({'error': 'Rôle invalide'}), 400
    if erreur_mot_de_passe(password):
        return jsonify({'error': erreur_mot_de_passe(password)}), 400
    if db.execute("SELECT id FROM users WHERE ecole_id=? AND username=?", (g.user['ecole_id'], username)).fetchone():
        return jsonify({'error': 'Identifiant déjà pris'}), 409

    cur = db.execute(
        "INSERT INTO users (ecole_id,username,password_hash,full_name,role,email,telephone,civilite,doit_changer_mdp) VALUES (?,?,?,?,?,?,?,?,1)",
        (g.user['ecole_id'], username, generate_password_hash(password), full_name, role, email, telephone, civilite),
    )
    db.commit()
    log_action(g.user, 'creation', 'utilisateur', str(cur.lastrowid), {'username': username, 'role': role, 'full_name': full_name})
    row = db.execute(
        "SELECT id,username,full_name,role,email,telephone,civilite,active,created_at FROM users WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/<int:user_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def update_user(user_id):
    body = request.get_json(silent=True) or {}
    existing = db.execute("SELECT * FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404

    db.execute(
        """UPDATE users SET
           full_name=COALESCE(?,full_name), role=COALESCE(?,role),
           email=COALESCE(?,email), telephone=COALESCE(?,telephone),
           civilite=COALESCE(?,civilite),
           active=COALESCE(?,active) WHERE id=? AND ecole_id=?""",
        (
            body.get('full_name'), body.get('role'),
            body.get('email'), body.get('telephone'),
            body.get('civilite') if body.get('civilite') in ('M.', 'Mme') else None,
            (1 if body.get('active') else 0) if 'active' in body else None,
            user_id, g.user['ecole_id'],
        ),
    )
    nouveau_role = body.get('role') if body.get('role') else existing['role']
    desactive = 'active' in body and not body.get('active') and existing['active']
    if nouveau_role != existing['role'] or desactive:
        revoquer_sessions(user_id)  # droits modifiés ou compte désactivé : effet immédiat, pas dans 12 h
    db.commit()
    log_action(g.user, 'modification', 'utilisateur', str(user_id),
               {'motif': body.get('motif'), 'avant': {'full_name': existing['full_name'], 'role': existing['role'], 'active': existing['active']}, 'apres': body})
    row = db.execute(
        "SELECT id,username,full_name,role,email,telephone,active FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<int:user_id>/reset-password', methods=['POST'])
@require_auth
@require_role('admin')
def reset_password(user_id):
    body = request.get_json(silent=True) or {}
    new_password = body.get('newPassword')
    if not new_password or erreur_mot_de_passe(new_password):
        return jsonify({'error': erreur_mot_de_passe(new_password)}), 400
    u = db.execute("SELECT id, username FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    # Mot de passe fixé par l'administrateur = provisoire : l'utilisateur devra le changer à sa prochaine connexion.
    db.execute("UPDATE users SET password_hash=?, doit_changer_mdp=1 WHERE id=? AND ecole_id=?",
               (generate_password_hash(new_password), user_id, g.user['ecole_id']))
    revoquer_sessions(user_id)
    db.commit()
    log_action(g.user, 'reinitialisation_mdp', 'utilisateur', str(user_id), {'username': u['username']})
    return jsonify({'success': True})


@bp.route('/<int:user_id>/revoquer-sessions', methods=['POST'])
@require_auth
@require_role('admin')
def revoquer_sessions_utilisateur(user_id):
    """Coupe toutes les connexions ouvertes d'un utilisateur (compte compromis, appareil perdu)."""
    u = db.execute("SELECT id, username FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    revoquer_sessions(user_id)
    db.commit()
    log_action(g.user, 'revocation_sessions', 'utilisateur', str(user_id), {'username': u['username']})
    return jsonify({'success': True})


@bp.route('/<int:user_id>/reset-2fa', methods=['POST'])
@require_auth
@require_role('admin')
def reset_2fa(user_id):
    """Téléphone perdu et codes de secours épuisés : l'administrateur retire la double authentification."""
    u = db.execute("SELECT id, username FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("UPDATE users SET totp_actif=0, totp_secret=NULL, codes_secours=NULL, totp_dernier_pas=0 WHERE id=?", (user_id,))
    db.commit()
    log_action(g.user, 'reinitialisation_2fa', 'utilisateur', str(user_id), {'username': u['username']})
    return jsonify({'success': True})


@bp.route('/<int:user_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_user(user_id):
    if user_id == g.user['id']:
        return jsonify({'error': 'Vous ne pouvez pas vous supprimer'}), 400
    existing = db.execute("SELECT * FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404

    # Traçabilité : un compte qui a déjà agi sur la plateforme (connexion, opérations, journal) n'est
    # jamais supprimé — on le désactive. Son historique reste ainsi attribuable à une personne.
    from database import compte_a_une_activite
    if compte_a_une_activite(user_id):
        return jsonify({'error': "Ce compte a déjà effectué des actions sur la plateforme : il ne peut pas être supprimé "
                                 "(traçabilité). Désactivez-le plutôt.", 'code': 'compte_avec_activite'}), 409

    # Sécurité renforcée : supprimer un compte administrateur exige de re-saisir
    # son propre mot de passe, pour éviter une suppression accidentelle ou par un
    # tiers ayant momentanément accès à une session déjà ouverte.
    if existing['role'] == 'admin':
        body = request.get_json(silent=True) or {}
        mot_de_passe = body.get('mot_de_passe') or ''
        moi = db.execute("SELECT password_hash FROM users WHERE id=?", (g.user['id'],)).fetchone()
        if not moi or not check_password_hash(moi['password_hash'], mot_de_passe):
            return jsonify({'error': 'Mot de passe incorrect — confirmation requise pour supprimer un compte administrateur'}), 403

    db.execute("DELETE FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'utilisateur', str(user_id), {'username': existing['username']})
    return jsonify({'success': True})


@bp.route('/<int:user_id>/enfants', methods=['GET'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def list_enfants_parent(user_id):
    """Liste les élèves liés à un compte parent (gestion par l'administration)."""
    rows = db.execute(
        """SELECT e.id, e.matricule, e.nom, e.prenom, e.classe
           FROM parents_eleves pe JOIN eleves e ON e.id = pe.eleve_id
           WHERE pe.user_id=? AND e.ecole_id=? ORDER BY e.nom""", (user_id, g.user['ecole_id'])
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/<int:user_id>/enfants', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def lier_enfant_parent(user_id):
    """Lie un élève à un compte parent, pour lui donner accès à ses notes/absences/bulletin."""
    body = request.get_json(silent=True) or {}
    eleve_id = body.get('eleve_id')
    if not eleve_id:
        return jsonify({'error': 'eleve_id requis'}), 400
    u = db.execute("SELECT role FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not u:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    if u['role'] != 'parent':
        return jsonify({'error': "Ce compte n'a pas le rôle « parent »"}), 400
    e = db.execute("SELECT id FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    try:
        db.execute("INSERT INTO parents_eleves (id, ecole_id, user_id, eleve_id) VALUES (?,?,?,?)",
                   (gen_id('pe'), g.user['ecole_id'], user_id, eleve_id))
        db.commit()
    except Exception:
        return jsonify({'error': 'Ce lien existe déjà'}), 409
    log_action(g.user, 'creation', 'lien_parent_eleve', f"{user_id}->{eleve_id}", {})
    return jsonify({'success': True}), 201


@bp.route('/<int:user_id>/enfants/<eleve_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def delier_enfant_parent(user_id, eleve_id):
    # Verifie que le compte parent appartient bien a l'ecole de qui fait la demande,
    # avant de supprimer le lien (empeche de delier un enfant d'une autre ecole).
    u = db.execute("SELECT id FROM users WHERE id=? AND ecole_id=?", (user_id, g.user['ecole_id'])).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM parents_eleves WHERE user_id=? AND eleve_id=?", (user_id, eleve_id))
    db.commit()
    log_action(g.user, 'suppression', 'lien_parent_eleve', f"{user_id}->{eleve_id}", {})
    return jsonify({'success': True})
