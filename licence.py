"""
Gestion des licences — installation locale (version .exe / hors-ligne).
Chaque installation démarre avec une période d'essai gratuite de 14 jours ; au-delà,
une clé de licence valide est nécessaire pour continuer à utiliser l'application.

Les clés sont signées hors-ligne par l'éditeur avec sa CLÉ PRIVÉE
(outils_editeur/generer_licence.py, jamais distribué avec l'application) et vérifiées
ici avec la CLÉ PUBLIQUE correspondante (signature Ed25519). Aucune connexion internet
n'est nécessaire pour activer une licence, ce qui convient à un usage en zone à
connectivité limitée.

Ce fichier ne contient AUCUN secret : la clé publique ci-dessous permet seulement de
VÉRIFIER une licence, pas d'en fabriquer une. Elle peut être lue par n'importe qui
(dépôt, exécutable) sans danger. Seule la clé privée, gardée par l'éditeur hors du
projet, permet de produire une licence valide.

Format d'une clé : IDENTIFIANT-EXPIRATION-SIGNATURE, par exemple
ECOLEDJELY-PERPETUEL-<signature> ou ECOLEDJELY-20271231-<signature>. La signature fait
103 caractères (A-Z et 2-7) : la clé se copie-colle plutôt qu'elle ne se tape.
"""
import base64
import binascii
import re
import os
import sys
from datetime import datetime, date

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Clé publique de l'éditeur (Ed25519, 32 octets en base64). Pour en changer : générer une
# nouvelle paire avec `python outils_editeur/generer_licence.py --creer-cles`, remplacer
# cette valeur, reconstruire l'exécutable. Les licences signées avec l'ancienne clé
# privée cessent alors d'être acceptées.
CLE_PUBLIQUE_LICENCES = "MtopJuDZPCs2MwoV99Uuo69nhluumyJdB4V+tbk4XtE="
# Préfixe ajouté au texte signé, pour qu'une signature produite pour autre chose ne
# puisse jamais servir de licence. Doit être identique dans l'outil de l'éditeur.
CONTEXTE_SIGNATURE = "MY-ECOLE-LICENCE-V2"
DUREE_ESSAI_JOURS = 14

# Ce module de licence (essai 14 jours + clé) ne concerne QUE les installations locales
# autonomes (version .exe / hors-ligne, une école = une installation). Il reste totalement
# INACTIF sur la plateforme web multi-écoles hébergée, qui gère déjà ses propres licences
# par école (voir ecoles_routes.py).
#
# Activation automatique : dès que l'application tourne en tant qu'exécutable compilé
# (PyInstaller définit sys.frozen=True), sans qu'aucune configuration ne soit nécessaire —
# c'est le signe fiable qu'il s'agit d'une installation locale, pas du serveur web.
# La variable d'environnement GS_LICENCE_HORS_LIGNE=1 reste disponible pour forcer
# l'activation manuellement (utile pour tester ce système en développement).
def licence_active() -> bool:
    if os.environ.get('GS_LICENCE_HORS_LIGNE') == '1':
        return True
    if getattr(sys, 'frozen', False):
        return True
    return False


def texte_signe(identifiant: str, expiration: str) -> bytes:
    """Ce que la signature d'une licence couvre (identique côté éditeur et côté application)."""
    return f"{CONTEXTE_SIGNATURE}|{identifiant}|{expiration}".encode('ascii')


def signature_valide(identifiant: str, expiration: str, signature_b32: str) -> bool:
    """La signature a-t-elle bien été produite par la clé privée de l'éditeur ?"""
    if not re.fullmatch(r'[A-Z2-7]{103}', signature_b32):
        return False
    try:
        signature = base64.b32decode(signature_b32 + '=')
        cle = Ed25519PublicKey.from_public_bytes(base64.b64decode(CLE_PUBLIQUE_LICENCES))
        cle.verify(signature, texte_signe(identifiant, expiration))
        return True
    except (InvalidSignature, binascii.Error, ValueError):
        return False


def verifier_cle_licence(cle: str) -> dict:
    """Vérifie une clé de licence. Retourne toujours un dict avec au moins la clé 'valide'."""
    if not cle or not cle.strip():
        return {'valide': False, 'erreur': "Aucune clé fournie"}
    parties = re.sub(r'\s+', '', cle).upper().split('-')
    if len(parties) != 3:
        return {'valide': False, 'erreur': "Format de clé invalide"}
    identifiant, exp, sig_fournie = parties
    if not re.fullmatch(r'[A-Z0-9]{1,12}', identifiant) or not re.fullmatch(r'PERPETUEL|\d{8}', exp):
        return {'valide': False, 'erreur': "Format de clé invalide"}

    if not signature_valide(identifiant, exp, sig_fournie):
        return {'valide': False, 'erreur': "Clé de licence invalide"}

    if exp != 'PERPETUEL':
        try:
            date_exp = datetime.strptime(exp, '%Y%m%d').date()
        except ValueError:
            return {'valide': False, 'erreur': "Clé de licence corrompue (date illisible)"}
        if date.today() > date_exp:
            return {'valide': False, 'erreur': f"Cette licence a expiré le {date_exp.strftime('%d/%m/%Y')}",
                    'identifiant': identifiant, 'expiration': exp}

    return {'valide': True, 'identifiant': identifiant, 'expiration': exp}


def statut_licence(db) -> dict:
    """Détermine le statut actuel de l'installation : licence active, période d'essai
    en cours (avec jours restants), ou essai expiré (blocage). `db` est la connexion
    sqlite3 partagée de l'application (voir database.py). Sur la plateforme web (SaaS),
    ce système est désactivé : renvoie toujours 'illimitee' sans aucun blocage."""
    if not licence_active():
        return {'mode': 'illimitee', 'bloque': False}

    row_cle = db.execute("SELECT valeur FROM settings WHERE ecole_id=1 AND cle='licence_cle'").fetchone()
    if row_cle and row_cle['valeur']:
        verif = verifier_cle_licence(row_cle['valeur'])
        if verif['valide']:
            return {'mode': 'licenciee', 'identifiant': verif.get('identifiant'),
                    'expiration': verif.get('expiration'), 'bloque': False}
        # Clé enregistrée mais désormais invalide/expirée -> retombe sur la logique d'essai ci-dessous

    row_install = db.execute("SELECT valeur FROM settings WHERE ecole_id=1 AND cle='date_installation'").fetchone()
    if not row_install or not row_install['valeur']:
        # Ne devrait pas arriver (initialisée au premier démarrage), filet de sécurité
        date_installation = date.today()
        db.execute("INSERT OR REPLACE INTO settings (ecole_id,cle,valeur) VALUES (1,'date_installation',?)",
                   (date_installation.isoformat(),))
        db.commit()
    else:
        date_installation = datetime.strptime(row_install['valeur'], '%Y-%m-%d').date()

    jours_ecoules = (date.today() - date_installation).days
    jours_restants = DUREE_ESSAI_JOURS - jours_ecoules

    if jours_restants > 0:
        return {'mode': 'essai', 'jours_restants': jours_restants, 'bloque': False}
    return {'mode': 'essai_expire', 'jours_restants': 0, 'bloque': True}


def initialiser_date_installation(db):
    """Enregistre la date de première utilisation, une seule fois — appelé au démarrage
    de l'application (voir database.py: init_db()). Sans effet sur la plateforme web (SaaS)."""
    if not licence_active():
        return
    existe = db.execute("SELECT 1 FROM settings WHERE ecole_id=1 AND cle='date_installation'").fetchone()
    if not existe:
        db.execute("INSERT INTO settings (ecole_id,cle,valeur) VALUES (1,'date_installation',?)",
                   (date.today().isoformat(),))
        db.commit()
