"""
Gestion des licences — installation locale (version .exe / hors-ligne).
Chaque installation démarre avec une période d'essai gratuite de 14 jours ; au-delà,
une clé de licence valide est nécessaire pour continuer à utiliser l'application.

Les clés sont générées hors-ligne par l'outil `outil_licences.py` (réservé à l'éditeur,
JAMAIS distribué avec l'application) et vérifiées ici par simple signature HMAC — aucune
connexion internet n'est nécessaire pour activer une licence, ce qui convient à un usage
en zone à connectivité limitée.

IMPORTANT : SECRET_LICENCE doit être IDENTIQUE dans ce fichier et dans outil_licences.py,
et ne doit JAMAIS être partagé ni inclus dans un dépôt public — c'est lui qui garantit
qu'une clé de licence ne peut être fabriquée que par l'éditeur.
"""
import hmac
import hashlib
import re
import os
import sys
from datetime import datetime, date

SECRET_LICENCE = "GestionScolaire-Guinee-2026-CleSecreteEditeur-NePasPartager"
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


def _signature(payload: str) -> str:
    return hmac.new(SECRET_LICENCE.encode(), payload.encode(), hashlib.sha256).hexdigest()[:8].upper()


def generer_cle_licence(identifiant_client: str, expiration=None) -> str:
    """Génère une clé de licence pour un client donné, au format lisible
    IDENTIFIANT-EXPIRATION-SIGNATURE (ex: ECOLEDJELY-PERPETUEL-A1B2C3D4).
    `expiration` : None (licence perpétuelle) ou date 'AAAA-MM-JJ' (licence limitée dans le temps).
    Réservé à l'outil de génération de l'éditeur — voir outil_licences.py.
    """
    import unicodedata
    sans_accents = unicodedata.normalize('NFD', identifiant_client).encode('ascii', 'ignore').decode('ascii')
    identifiant_propre = re.sub(r'[^A-Za-z0-9]', '', sans_accents).upper()[:12]
    if not identifiant_propre:
        raise ValueError("Identifiant client invalide (doit contenir au moins un caractère alphanumérique)")
    exp = expiration.replace('-', '') if expiration else "PERPETUEL"
    payload = f"{identifiant_propre}-{exp}"
    sig = _signature(payload)
    return f"{payload}-{sig}"


def verifier_cle_licence(cle: str) -> dict:
    """Vérifie une clé de licence. Retourne toujours un dict avec au moins la clé 'valide'."""
    if not cle or not cle.strip():
        return {'valide': False, 'erreur': "Aucune clé fournie"}
    parties = cle.strip().upper().replace(' ', '').split('-')
    if len(parties) != 3:
        return {'valide': False, 'erreur': "Format de clé invalide"}
    identifiant, exp, sig_fournie = parties
    payload = f"{identifiant}-{exp}"

    sig_attendue = _signature(payload)
    if not hmac.compare_digest(sig_fournie, sig_attendue):
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
