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


def login(username, password):
    user = db.execute(
        "SELECT * FROM users WHERE username=? AND active=1", (username,)
    ).fetchone()
    if not user or not check_password_hash(user['password_hash'], password):
        return None

    db.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user['id'],))
    db.commit()

    payload = {
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'name': user['full_name'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12),
        'iat': datetime.datetime.utcnow(),
    }
    token = jwt.encode(payload, get_secret(), algorithm='HS256')
    return {
        'token': token,
        'user': {
            'id': user['id'], 'username': user['username'], 'full_name': user['full_name'],
            'role': user['role'], 'email': user['email'],
        },
    }


def require_auth(f):
    """Décorateur : vérifie le token JWT, place l'utilisateur dans g.user."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Non authentifié'}), 401
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, get_secret(), algorithms=['HS256'])
            g.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expirée — reconnectez-vous'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Session expirée — reconnectez-vous'}), 401
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
