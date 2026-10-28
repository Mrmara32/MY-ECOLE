"""
Chiffrement des secrets conservés en base (ex : secret de double authentification) — Fernet (AES-128-CBC + HMAC-SHA256).

La clé vient de GS_CLE_CHIFFREMENT si elle est définie, sinon elle est dérivée du secret de session de
l'installation. Une valeur chiffrée commence par « enc: » ; une valeur ancienne (non chiffrée) est
lue telle quelle, puis chiffrée au prochain démarrage (migration).
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

PREFIXE = 'enc:'


def _cle():
    phrase = (os.environ.get('GS_CLE_CHIFFREMENT') or '').strip()
    if not phrase:
        from auth import get_secret
        phrase = 'coffre|' + get_secret()
    return base64.urlsafe_b64encode(hashlib.sha256(phrase.encode('utf-8')).digest())


def chiffrer(valeur):
    if valeur is None or valeur == '' or str(valeur).startswith(PREFIXE):
        return valeur
    return PREFIXE + Fernet(_cle()).encrypt(str(valeur).encode('utf-8')).decode('ascii')


def dechiffrer(valeur):
    if valeur is None or not str(valeur).startswith(PREFIXE):
        return valeur
    try:
        return Fernet(_cle()).decrypt(str(valeur)[len(PREFIXE):].encode('ascii')).decode('utf-8')
    except InvalidToken:
        return None   # clé changée : le secret est inutilisable (le titulaire devra reconfigurer sa 2FA)
