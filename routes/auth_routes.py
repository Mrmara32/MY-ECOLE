from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from auth import login as do_login, require_auth, emettre_jeton
import securite

bp = Blueprint('auth_routes', __name__, url_prefix='/api/auth')


@bp.route('/login', methods=['POST'])
def login_route():
    body = request.get_json(silent=True) or {}
    username, password = body.get('username'), body.get('password')
    code_ecole = body.get('code_ecole')
    if not username or not password:
        return jsonify({'error': 'Identifiant et mot de passe requis'}), 400
    cles = securite.cles_connexion(code_ecole or '1', username)
    attente = securite.secondes_restantes(cles)
    if attente:
        minutes = (attente + 59) // 60
        r = jsonify({'error': f"Trop de tentatives de connexion. Réessayez dans {minutes} minute{'s' if minutes > 1 else ''}."})
        r.status_code = 429
        r.headers['Retry-After'] = str(attente)
        return r
    result = do_login(username, password, code_ecole)
    if result == 'ecole_non_confirmee':
        return jsonify({'error': "Cette école n'a pas encore confirmé son adresse e-mail — vérifiez la boîte de réception (et les indésirables) pour le lien reçu à l'inscription."}), 403
    if result == 'compte_non_confirme':
        return jsonify({'error': "Ce compte n'est pas encore activé — vérifiez votre boîte de réception (et vos indésirables) pour le lien d'activation."}), 403
    if result == 'compte_desactive':
        return jsonify({'error': "Ce compte a été désactivé — contactez votre administration."}), 403
    if not result:
        securite.enregistrer_echec(cles)
        return jsonify({'error': 'Identifiant, mot de passe ou établissement incorrect'}), 401
    securite.effacer_echecs(cles[0])
    return jsonify(result)


@bp.route('/me', methods=['GET'])
@require_auth
def me():
    u = db.execute(
        "SELECT id,ecole_id,username,full_name,role,email,telephone,civilite FROM users WHERE id=?", (g.user['id'],)
    ).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    d = dict(u)
    d['doit_changer_mot_de_passe'] = bool(g.user.get('mdp_provisoire'))
    return jsonify(d)


@bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    body = request.get_json(silent=True) or {}
    old_password, new_password = body.get('oldPassword'), body.get('newPassword')
    if not old_password or not new_password:
        return jsonify({'error': 'Champs requis'}), 400
    erreur = securite.erreur_mot_de_passe(new_password)
    if erreur:
        return jsonify({'error': erreur}), 400
    u = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if not check_password_hash(u['password_hash'], old_password):
        return jsonify({'error': 'Ancien mot de passe incorrect'}), 401
    if old_password == new_password:
        return jsonify({'error': "Le nouveau mot de passe doit être différent de l'ancien"}), 400
    db.execute("UPDATE users SET password_hash=?, doit_changer_mdp=0 WHERE id=?",
               (generate_password_hash(new_password), g.user['id']))
    db.commit()
    u = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],)).fetchone()
    # Nouveau jeton sans la mention « mot de passe provisoire » : l'utilisateur peut continuer sans se reconnecter.
    return jsonify({'success': True, 'token': emettre_jeton(u)})

