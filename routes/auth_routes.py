from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from auth import login as do_login, require_auth, emettre_jeton
import securite
import double_authentification as da
from database import log_action

bp = Blueprint('auth_routes', __name__, url_prefix='/api/auth')


def _journaliser_securite(action, username, code_ecole):
    """Trace les échecs de connexion (détection d'attaques) sans jamais enregistrer de mot de passe."""
    from database import ecole_id_depuis_code
    try:
        ecole = ecole_id_depuis_code(code_ecole) if code_ecole else 1
        log_action({'id': None, 'name': str(username)[:80], 'ecole_id': ecole}, action, 'securite', None,
                   {'ip': securite.adresse_client()})
    except Exception:
        pass


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
        _journaliser_securite('echec_connexion', username, code_ecole)
        securite.enregistrer_echec(cles)
        return jsonify({'error': 'Identifiant, mot de passe ou établissement incorrect'}), 401
    # Double authentification : mot de passe correct, mais le compte exige aussi un code.
    u = db.execute("SELECT id, totp_secret, totp_actif, totp_dernier_pas, codes_secours FROM users WHERE id=?",
                   (result['user']['id'],)).fetchone()
    if u and u['totp_actif']:
        code = (body.get('code_2fa') or '').strip()
        if not code:
            return jsonify({'requires_2fa': True}), 200
        pas = da.verifier(u['totp_secret'], code, u['totp_dernier_pas'])
        if pas:
            db.execute("UPDATE users SET totp_dernier_pas=? WHERE id=?", (pas, u['id']))
            db.commit()
        else:
            reste = da.consommer_code_secours(u['codes_secours'], code)
            if reste is None:
                _journaliser_securite('echec_2fa', username, code_ecole)
                securite.enregistrer_echec(cles)
                return jsonify({'error': 'Code de vérification incorrect', 'requires_2fa': True}), 401
            db.execute("UPDATE users SET codes_secours=? WHERE id=?", (reste, u['id']))
            db.commit()
            result['user']['codes_secours_restants'] = len(__import__('json').loads(reste))
    securite.effacer_echecs(cles[0])
    log_action({'id': result['user']['id'], 'name': result['user']['full_name'], 'ecole_id': result['user']['ecole_id']},
               'connexion', 'securite', None, {'ip': securite.adresse_client()})
    return jsonify(result)


# ── Gestion de la double authentification par l'utilisateur lui-même ──

@bp.route('/2fa', methods=['GET'])
@require_auth
def statut_2fa():
    u = db.execute("SELECT totp_actif, codes_secours FROM users WHERE id=?", (g.user['id'],)).fetchone()
    restants = len(__import__('json').loads(u['codes_secours'] or '[]')) if u and u['totp_actif'] else 0
    return jsonify({'actif': bool(u and u['totp_actif']), 'codes_secours_restants': restants})


@bp.route('/2fa/preparer', methods=['POST'])
@require_auth
def preparer_2fa():
    """Génère un secret (pas encore actif) à scanner dans l'application d'authentification."""
    u = db.execute("SELECT username, totp_actif FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if u['totp_actif']:
        return jsonify({'error': 'La double authentification est déjà active'}), 400
    secret = da.nouveau_secret()
    db.execute("UPDATE users SET totp_secret=?, totp_dernier_pas=0 WHERE id=?", (secret, g.user['id']))
    db.commit()
    return jsonify({'secret': secret, 'uri': da.uri_otpauth(secret, u['username'])})


@bp.route('/2fa/activer', methods=['POST'])
@require_auth
def activer_2fa():
    body = request.get_json(silent=True) or {}
    u = db.execute("SELECT totp_secret, totp_actif FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if u['totp_actif'] or not u['totp_secret']:
        return jsonify({'error': 'Préparez d\'abord la double authentification'}), 400
    pas = da.verifier(u['totp_secret'], body.get('code'))
    if not pas:
        return jsonify({'error': 'Code incorrect : vérifiez l\'heure de votre téléphone et réessayez'}), 400
    codes, empreintes = da.generer_codes_secours()
    db.execute("UPDATE users SET totp_actif=1, totp_dernier_pas=?, codes_secours=? WHERE id=?",
               (pas, empreintes, g.user['id']))
    db.commit()
    log_action(g.user, 'activation_2fa', 'utilisateur', str(g.user['id']), {})
    return jsonify({'success': True, 'codes_secours': codes})


@bp.route('/2fa/desactiver', methods=['POST'])
@require_auth
def desactiver_2fa():
    body = request.get_json(silent=True) or {}
    u = db.execute("SELECT password_hash, totp_secret, totp_actif, totp_dernier_pas FROM users WHERE id=?",
                   (g.user['id'],)).fetchone()
    if not u['totp_actif']:
        return jsonify({'success': True})
    if not check_password_hash(u['password_hash'], body.get('password') or ''):
        return jsonify({'error': 'Mot de passe incorrect'}), 401
    if not da.verifier(u['totp_secret'], body.get('code'), u['totp_dernier_pas']):
        return jsonify({'error': 'Code de vérification incorrect'}), 401
    db.execute("UPDATE users SET totp_actif=0, totp_secret=NULL, codes_secours=NULL, totp_dernier_pas=0 WHERE id=?",
               (g.user['id'],))
    db.commit()
    log_action(g.user, 'desactivation_2fa', 'utilisateur', str(g.user['id']), {})
    return jsonify({'success': True})


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

