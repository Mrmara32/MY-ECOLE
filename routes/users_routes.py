from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash

from database import db, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role

bp = Blueprint('users_routes', __name__, url_prefix='/api/users')

ROLES = ['admin', 'directeur', 'comptable', 'enseignant', 'secretaire', 'charge_communication']


@bp.route('', methods=['GET'])
@require_auth
@require_role('admin')
def list_users():
    rows = db.execute(
        "SELECT id,username,full_name,role,email,telephone,active,created_at,last_login "
        "FROM users ORDER BY created_at DESC"
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

    if not username or not password or not full_name or not role:
        return jsonify({'error': 'Champs requis'}), 400
    if role not in ROLES:
        return jsonify({'error': 'Rôle invalide'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Mot de passe trop court'}), 400
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({'error': 'Identifiant déjà pris'}), 409

    cur = db.execute(
        "INSERT INTO users (username,password_hash,full_name,role,email,telephone) VALUES (?,?,?,?,?,?)",
        (username, generate_password_hash(password), full_name, role, email, telephone),
    )
    db.commit()
    log_action(g.user, 'creation', 'utilisateur', str(cur.lastrowid), {'username': username, 'role': role, 'full_name': full_name})
    row = db.execute(
        "SELECT id,username,full_name,role,email,telephone,active,created_at FROM users WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/<int:user_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def update_user(user_id):
    body = request.get_json(silent=True) or {}
    existing = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404

    db.execute(
        """UPDATE users SET
           full_name=COALESCE(?,full_name), role=COALESCE(?,role),
           email=COALESCE(?,email), telephone=COALESCE(?,telephone),
           active=COALESCE(?,active) WHERE id=?""",
        (
            body.get('full_name'), body.get('role'),
            body.get('email'), body.get('telephone'),
            (1 if body.get('active') else 0) if 'active' in body else None,
            user_id,
        ),
    )
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
    if not new_password or len(new_password) < 6:
        return jsonify({'error': 'Min. 6 caractères'}), 400
    u = db.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_password), user_id))
    db.commit()
    log_action(g.user, 'reinitialisation_mdp', 'utilisateur', str(user_id), {'username': u['username']})
    return jsonify({'success': True})


@bp.route('/<int:user_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_user(user_id):
    if user_id == g.user['id']:
        return jsonify({'error': 'Vous ne pouvez pas vous supprimer'}), 400
    existing = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    log_action(g.user, 'suppression', 'utilisateur', str(user_id), {'username': existing['username']})
    return jsonify({'success': True})
