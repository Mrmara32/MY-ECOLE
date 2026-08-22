from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from auth import login as do_login, require_auth

bp = Blueprint('auth_routes', __name__, url_prefix='/api/auth')


@bp.route('/login', methods=['POST'])
def login_route():
    body = request.get_json(silent=True) or {}
    username, password = body.get('username'), body.get('password')
    code_ecole = body.get('code_ecole')
    if not username or not password:
        return jsonify({'error': 'Identifiant et mot de passe requis'}), 400
    result = do_login(username, password, code_ecole)
    if not result:
        return jsonify({'error': 'Identifiant, mot de passe ou établissement incorrect'}), 401
    return jsonify(result)


@bp.route('/me', methods=['GET'])
@require_auth
def me():
    u = db.execute(
        "SELECT id,ecole_id,username,full_name,role,email,telephone,civilite FROM users WHERE id=?", (g.user['id'],)
    ).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(dict(u))


@bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    body = request.get_json(silent=True) or {}
    old_password, new_password = body.get('oldPassword'), body.get('newPassword')
    if not old_password or not new_password:
        return jsonify({'error': 'Champs requis'}), 400
    if len(new_password) < 6:
        return jsonify({'error': 'Min. 6 caractères'}), 400
    u = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if not check_password_hash(u['password_hash'], old_password):
        return jsonify({'error': 'Ancien mot de passe incorrect'}), 401
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_password), g.user['id']))
    db.commit()
    return jsonify({'success': True})
