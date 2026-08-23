"""
Authentification JWT — équivalent Python de server/auth.js.
PyJWT est une bibliothèque 100% Python pure (aucune compilation requise),
tout comme werkzeug.security pour le hachage des mots de passe (pbkdf2:sha256,
basé sur hashlib, intégré à Python).
"""
import os
import jwt
import datetime
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import check_password_hash

from database import db


def get_secret():
    return os.environ.get('JWT_SECRET', 'dev-secret-changez-en-production')


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

    payload = {
        'id': user['id'],
        'ecole_id': user['ecole_id'],
        'username': user['username'],
        'role': user['role'],
        'name': user['full_name'],
        'est_super_admin': bool(user['est_super_admin']),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12),
        'iat': datetime.datetime.utcnow(),
    }
    token = jwt.encode(payload, get_secret(), algorithm='HS256')
    return {
        'token': token,
        'user': {
            'id': user['id'], 'ecole_id': user['ecole_id'], 'username': user['username'], 'full_name': user['full_name'],
            'role': user['role'], 'email': user['email'], 'civilite': user['civilite'],
            'est_super_admin': bool(user['est_super_admin']),
        },
    }


def require_auth(f):
    """Décorateur : vérifie le token JWT, place l'utilisateur dans g.user. Sur une
    installation autonome (version .exe) dont l'essai est expiré sans licence valide,
    bloque également l'accès ici — protection réelle, pas seulement visuelle côté écran."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Non authentifié'}), 401
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, get_secret(), algorithms=['HS256'])
            payload.setdefault('ecole_id', 1)  # jetons émis avant le multi-établissement
            payload.setdefault('est_super_admin', False)
            g.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expirée — reconnectez-vous'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Session expirée — reconnectez-vous'}), 401

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
