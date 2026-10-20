"""Relit une sauvegarde chiffrée (.zip.enc) téléchargée depuis votre stockage.

Usage :  python dechiffrer.py ecole-2026-10-20.zip.enc  "VOTRE MOT DE PASSE GS_BACKUP_CLE"
Résultat : ecole-2026-10-20.zip  (contient ecole.db)
Nécessite :  pip install cryptography
"""
import base64
import hashlib
import sys

from cryptography.fernet import Fernet, InvalidToken

SEL = b'my-ecole-sauvegarde-v1'

if len(sys.argv) != 3:
    sys.exit(__doc__)
source, phrase = sys.argv[1], sys.argv[2]
cle = base64.urlsafe_b64encode(hashlib.pbkdf2_hmac('sha256', phrase.encode(), SEL, 200_000, dklen=32))
try:
    clair = Fernet(cle).decrypt(open(source, 'rb').read())
except InvalidToken:
    sys.exit('Mot de passe incorrect ou fichier abîmé.')
sortie = source[:-4] if source.endswith('.enc') else source + '.zip'
open(sortie, 'wb').write(clair)
print('Écrit :', sortie)
