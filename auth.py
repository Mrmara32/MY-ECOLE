"""
Authentification JWT — équivalent Python de server/auth.js.
PyJWT est une bibliothèque 100% Python pure (aucune compilation requise),
tout comme werkzeug.security pour le hachage des mots de passe (pbkdf2:sha256,
basé sur hashlib, intégré à Python).
"""
import os
import secrets
import time
import hashlib
import jwt
import datetime
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import check_password_hash

from database import db, DATA_DIR

_secret_jwt = None


def _secret_local():
    """Secret propre à CETTE installation, tiré au hasard au premier démarrage et rangé à
    côté de la base de données. Sert quand JWT_SECRET n'est pas configuré (exécutable
    installé dans une école, développement) : aucun secret n'est jamais écrit dans le code,
    donc aucun n'est partagé entre installations ni visible dans le dépôt."""
    chemin = os.path.join(DATA_DIR, 'cle_jwt_locale.txt')
    try:
        fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_urlsafe(48))
    for _ in range(50):  # un autre processus (worker gunicorn) peut être en train de l'écrire
        with open(chemin) as f:
            valeur = f.read().strip()
        if valeur:
            return valeur
        time.sleep(0.05)
    raise RuntimeError(f"Secret de connexion illisible : {chemin}")


def get_secret():
    global _secret_jwt
    if _secret_jwt is None:
        configure = (os.environ.get('JWT_SECRET') or '').strip()
        # Une valeur d'exemple (« changez-moi... », publiée dans .env.example) n'est jamais un secret.
        if configure and 'changez' not in configure.lower():
            _secret_jwt = configure
        else:
            if configure:
                print("[auth] JWT_SECRET contient une valeur d'exemple : ignorée, secret local utilisé.")
            _secret_jwt = _secret_local()
    return _secret_jwt


def ecole_id_optionnelle():
    """Pour une route accessible avec OU sans connexion (ex: paramètres publics affichés
    sur la page de connexion) : renvoie l'ecole_id de l'utilisateur connecté si un jeton
    valide est présent, sinon None (l'appelant décide alors d'une valeur par défaut)."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    try:
        payload = jwt.decode(auth_header[7:], get_secret(), algorithms=['HS256'])
        return payload.get('ecole_id', 1)
    except jwt.InvalidTokenError:
        return None


def login(username, password, code_ecole=None):
    """Authentifie un utilisateur au sein d'une école précise. Le code établissement
    identifie l'école (les identifiants ne sont uniques qu'au sein d'une même école,
    pas globalement) — s'il est omis, on suppose l'école n°1 (installation mono-école
    existante), pour ne rien casser des connexions actuelles."""
    if code_ecole:
        ecole = db.execute("SELECT id, actif, statut_licence, email_confirme FROM ecoles WHERE code=?", (code_ecole,)).fetchone()
        if not ecole or not ecole['actif'] or ecole['statut_licence'] in ('suspendue', 'expiree'):
            return None
        if not ecole['email_confirme']:
            return 'ecole_non_confirmee'
        ecole_id = ecole['id']
    else:
        ecole_id = 1

    user = db.execute(
        "SELECT * FROM users WHERE ecole_id=? AND username=?", (ecole_id, username)
    ).fetchone()
    if not user or not check_password_hash(user['password_hash'], password):
        return None
    if not user['active']:
        return 'compte_non_confirme' if user['jeton_confirmation'] else 'compte_desactive'

    db.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user['id'],))
    db.commit()

    token = emettre_jeton(user)
    return {
        'token': token,
        'user': {
            'id': user['id'], 'ecole_id': user['ecole_id'], 'username': user['username'], 'full_name': user['full_name'],
            'role': user['role'], 'email': user['email'], 'civilite': user['civilite'],
            'est_super_admin': bool(user['est_super_admin']),
            'doit_changer_mot_de_passe': bool(user['doit_changer_mdp']),
        },
    }


DUREE_ACCES = 3600                 # jeton d'accès : 1 heure
DUREE_RENOUVELLEMENT = 7 * 86400   # jeton de renouvellement : 7 jours
INACTIVITE_MAX = 30 * 60           # déconnexion après 30 minutes sans activité


def _empreinte_renouvellement(jeton):
    return hashlib.sha256(jeton.encode()).hexdigest()


def _appareil(ua):
    ua = (ua or '')[:200]
    nav = next((n for n in ('Edg', 'Chrome', 'Firefox', 'Safari', 'Electron') if n in ua), 'Navigateur')
    sys_ = next((n for n in ('Android', 'iPhone', 'iPad', 'Windows', 'Mac', 'Linux') if n in ua), 'appareil inconnu')
    return f"{nav} · {sys_}"


def creer_session(user, ip='', ua='', sid=None):
    """Ouvre (ou renouvelle) une session d'appareil. Renvoie (jeton_acces, jeton_renouvellement).
    Le jeton de renouvellement est opaque, valable 7 jours, à usage unique : chaque renouvellement
    en émet un nouveau et rend l'ancien inutilisable (liste noire des jetons déjà utilisés)."""
    now = int(time.time())
    renouv = secrets.token_urlsafe(40)
    h = _empreinte_renouvellement(renouv)
    if sid:
        db.execute("UPDATE sessions_appareils SET renouvellement_hash=?, derniere_activite=?, expire_le=? WHERE id=?",
                   (h, now, now + DUREE_RENOUVELLEMENT, sid))
    else:
        sid = secrets.token_hex(12)
        db.execute("INSERT INTO sessions_appareils (id,user_id,ecole_id,renouvellement_hash,ip,appareil,cree_le,derniere_activite,expire_le) "
                   "VALUES (?,?,?,?,?,?,?,?,?)",
                   (sid, user['id'], user['ecole_id'], h, ip, _appareil(ua), now, now, now + DUREE_RENOUVELLEMENT))
        db.execute("DELETE FROM sessions_appareils WHERE expire_le < ? OR (revoquee=1 AND derniere_activite < ?)", (now, now - 86400))
    return emettre_jeton(user, sid), renouv


def renouveler_session(renouv, ip=''):
    """Échange un jeton de renouvellement valide contre une nouvelle paire. (paire, erreur)."""
    if not renouv:
        return None, 'Session expirée — reconnectez-vous'
    now = int(time.time())
    s = db.execute("SELECT * FROM sessions_appareils WHERE renouvellement_hash=?", (_empreinte_renouvellement(renouv),)).fetchone()
    if not s or s['revoquee'] or s['expire_le'] < now or now - s['derniere_activite'] > INACTIVITE_MAX * 48:
        return None, 'Session expirée — reconnectez-vous'
    user = db.execute("SELECT * FROM users WHERE id=?", (s['user_id'],)).fetchone()
    if not user or not user['active']:
        return None, 'Session terminée — reconnectez-vous'
    acces, nouveau = creer_session(user, sid=s['id'])
    return {'token': acces, 'refresh_token': nouveau, 'user_id': user['id']}, None


def revoquer_session_appareil(sid):
    db.execute("UPDATE sessions_appareils SET revoquee=1 WHERE id=?", (sid,))


def mfa_requise(user):
    """Double authentification obligatoire pour les comptes sensibles (admin, directeur, comptable).
    Désactivable uniquement par GS_2FA_OBLIGATOIRE=0 (tests, installation locale)."""
    if os.environ.get('GS_2FA_OBLIGATOIRE', '1') == '0':
        return False
    from securite import ROLES_SENSIBLES
    return user['role'] in ROLES_SENSIBLES and not user['totp_actif']


def emettre_jeton(user, sid=None):
    """Jeton de session. Tant que le mot de passe est provisoire, le jeton porte la mention
    'mdp_provisoire' et require_auth n'autorise alors QUE le changement de mot de passe."""
    payload = {
        'id': user['id'],
        'ecole_id': user['ecole_id'],
        'username': user['username'],
        'role': user['role'],
        'name': user['full_name'],
        'est_super_admin': bool(user['est_super_admin']),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=DUREE_ACCES),
        'iat': datetime.datetime.utcnow(),
        'jti': secrets.token_hex(12),                       # identifiant du jeton : permet de le révoquer (déconnexion)
        'sv': (user['session_version'] if 'session_version' in user.keys() else 0) or 0,  # voir revoquer_sessions
    }
    if sid:
        payload['sid'] = sid
    if user['doit_changer_mdp']:
        payload['mdp_provisoire'] = True
    if mfa_requise(user):
        payload['mfa_requise'] = True
    return jwt.encode(payload, get_secret(), algorithm='HS256')


def revoquer_sessions(user_id):
    """Invalide immédiatement TOUS les jetons déjà émis pour cet utilisateur (changement de
    mot de passe, de rôle, désactivation, perte d'un appareil…). Les jetons portent la
    « version de session » ; l'incrémenter les rend tous caducs."""
    db.execute("UPDATE users SET session_version = COALESCE(session_version, 0) + 1 WHERE id=?", (user_id,))
    db.execute("UPDATE sessions_appareils SET revoquee=1 WHERE user_id=?", (user_id,))


def revoquer_jeton(payload):
    """Déconnexion : ce jeton précis ne sera plus accepté, même avant son expiration."""
    jti = payload.get('jti')
    if not jti:
        return
    exp = payload.get('exp') or 0
    db.execute("DELETE FROM jetons_revoques WHERE expire_le < ?", (int(time.time()),))
    db.execute("INSERT OR IGNORE INTO jetons_revoques (jti, expire_le) VALUES (?, ?)", (jti, int(exp)))


def charger_session(token):
    """Décode un jeton ET vérifie qu'il est toujours valable côté serveur (compte existant et
    actif, version de session à jour, jeton non révoqué). Renvoie (payload, None) ou
    (None, message_d_erreur)."""
    try:
        payload = jwt.decode(token, get_secret(), algorithms=['HS256'])
    except jwt.InvalidTokenError:
        return None, 'Session expirée — reconnectez-vous'
    payload.setdefault('ecole_id', 1)  # jetons émis avant le multi-établissement
    payload.setdefault('est_super_admin', False)
    ligne = db.execute("SELECT active, session_version FROM users WHERE id=?", (payload.get('id'),)).fetchone()
    if not ligne or not ligne['active'] or (ligne['session_version'] or 0) != payload.get('sv', 0):
        return None, 'Session terminée — reconnectez-vous'
    if payload.get('jti') and db.execute("SELECT 1 FROM jetons_revoques WHERE jti=?", (payload['jti'],)).fetchone():
        return None, 'Session terminée — reconnectez-vous'
    if payload.get('sid'):
        now = int(time.time())
        sess = db.execute("SELECT revoquee, derniere_activite FROM sessions_appareils WHERE id=?", (payload['sid'],)).fetchone()
        if not sess or sess['revoquee']:
            return None, 'Session terminée — reconnectez-vous'
        if now - sess['derniere_activite'] > INACTIVITE_MAX:
            db.execute("UPDATE sessions_appareils SET revoquee=1 WHERE id=?", (payload['sid'],))
            db.commit()
            return None, 'Déconnecté après 30 minutes d\'inactivité — reconnectez-vous'
        if now - sess['derniere_activite'] >= 60:  # on évite une écriture à chaque requête
            db.execute("UPDATE sessions_appareils SET derniere_activite=? WHERE id=?", (now, payload['sid']))
            db.commit()
    return payload, None


# Seules routes accessibles avec un mot de passe provisoire.
ROUTES_MDP_PROVISOIRE = ('/api/auth/change-password', '/api/auth/me', '/api/auth/logout', '/api/auth/logout-all')


ROUTES_MFA = ('/api/auth/me', '/api/auth/logout', '/api/auth/logout-all', '/api/auth/2fa', '/api/auth/2fa/preparer',
              '/api/auth/2fa/activer', '/api/auth/sessions')


def require_auth(f):
    """Décorateur : vérifie le token JWT, place l'utilisateur dans g.user. Sur une
    installation autonome (version .exe) dont l'essai est expiré sans licence valide,
    bloque également l'accès ici — protection réelle, pas seulement visuelle côté écran."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Non authentifié'}), 401
        payload, erreur = charger_session(auth_header[7:])
        if erreur:
            return jsonify({'error': erreur}), 401
        g.user = payload

        if g.user.get('mdp_provisoire') and request.path not in ROUTES_MDP_PROVISOIRE:
            return jsonify({'error': 'Vous devez d\'abord changer votre mot de passe provisoire.',
                             'code': 'MOT_DE_PASSE_A_CHANGER'}), 403

        if g.user.get('mfa_requise') and request.path not in ROUTES_MFA:
            return jsonify({'error': "La double authentification est obligatoire pour votre rôle : activez-la pour continuer.",
                             'code': 'DOUBLE_AUTH_REQUISE'}), 403

        from licence import statut_licence
        statut = statut_licence(db)
        if statut.get('bloque'):
            return jsonify({'error': "La période d'essai est terminée. Merci de saisir une clé de licence pour continuer.",
                             'licence_bloquee': True}), 402

        return f(*args, **kwargs)
    return wrapper


def require_super_admin(f):
    """Décorateur : réserve une route au(x) super-administrateur(s), qui supervisent
    l'ensemble des écoles clientes de l'installation (indépendamment de leur propre école)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not hasattr(g, 'user'):
            return jsonify({'error': 'Non authentifié'}), 401
        if not g.user.get('est_super_admin'):
            return jsonify({'error': 'Accès réservé au super-administrateur'}), 403
        return f(*args, **kwargs)
    return wrapper


def require_role(*roles):
    """Décorateur paramétré : restreint l'accès à certains rôles."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not hasattr(g, 'user'):
                return jsonify({'error': 'Non authentifié'}), 401
            if g.user['role'] not in roles:
                return jsonify({'error': 'Accès refusé'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
