"""
Double authentification (TOTP, RFC 6238) : code à 6 chiffres qui change toutes les 30 secondes,
généré par une application d'authentification (Google Authenticator, Microsoft Authenticator,
Aegis, FreeOTP…). Aucune dépendance externe : HMAC-SHA1 de la bibliothèque standard.

  * le secret est propre à chaque compte (aléatoire, 160 bits) ;
  * un code ne peut servir qu'une fois (protection contre le rejeu) ;
  * 8 codes de secours à usage unique, affichés une seule fois, conservés hachés ;
  * tolérance d'une période (30 s) avant/après pour les horloges légèrement décalées.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

PERIODE = 30
CHIFFRES = 6
TOLERANCE = 1


def nouveau_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def _decoder(secret):
    secret = secret.strip().replace(' ', '').upper()
    return base64.b32decode(secret + '=' * (-len(secret) % 8))


def code_a(secret, pas, chiffres=CHIFFRES):
    """Code TOTP du pas de temps donné (HOTP, RFC 4226)."""
    mac = hmac.new(_decoder(secret), struct.pack('>Q', pas), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    n = (struct.unpack('>I', mac[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** chiffres)
    return str(n).zfill(chiffres)


def verifier(secret, code, dernier_pas=0, maintenant=None):
    """-> pas de temps accepté (int) ou None. Refuse un pas déjà utilisé (rejeu)."""
    code = ''.join(c for c in str(code or '') if c.isdigit())
    if len(code) != CHIFFRES:
        return None
    pas_courant = int((maintenant if maintenant is not None else time.time()) // PERIODE)
    for decalage in range(-TOLERANCE, TOLERANCE + 1):
        pas = pas_courant + decalage
        if pas > (dernier_pas or 0) and hmac.compare_digest(code_a(secret, pas), code):
            return pas
    return None


def uri_otpauth(secret, compte, emetteur='MY-ECOLE'):
    return (f"otpauth://totp/{quote(emetteur)}:{quote(compte)}?secret={secret}"
            f"&issuer={quote(emetteur)}&algorithm=SHA1&digits={CHIFFRES}&period={PERIODE}")


def _hash(code):
    return hashlib.sha256(code.replace('-', '').strip().lower().encode()).hexdigest()


def generer_codes_secours(n=8):
    """-> (codes en clair à montrer UNE fois, JSON des empreintes à stocker)."""
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]
    return codes, json.dumps([_hash(c) for c in codes])


def consommer_code_secours(json_empreintes, code):
    """-> nouveau JSON sans le code utilisé, ou None si le code est inconnu."""
    try:
        liste = json.loads(json_empreintes or '[]')
    except ValueError:
        return None
    h = _hash(code or '')
    if h not in liste:
        return None
    liste.remove(h)
    return json.dumps(liste)
