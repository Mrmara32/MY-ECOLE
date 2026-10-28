"""
Protection des comptes : blocage après échecs de connexion répétés et règles de mot de passe.

Blocage (anti « force brute »), conservé en base pour survivre aux redémarrages :
  * 5 échecs sur un même identifiant en 15 minutes -> cet identifiant est bloqué 15 minutes ;
  * 40 échecs depuis une même adresse en 15 minutes -> cette adresse est bloquée 15 minutes.
Une connexion réussie remet le compteur de l'identifiant à zéro.
Compromis assumé : un inconnu peut bloquer 15 minutes un identifiant précis en multipliant
les essais ; c'est préférable à laisser deviner un mot de passe sans limite.
"""
import datetime

from flask import request

from database import db

FENETRE = datetime.timedelta(minutes=15)
LIMITE_IDENTIFIANT = 5
LIMITE_ADRESSE = 40
MOTS_DE_PASSE_COURANTS = {
    'password', 'motdepasse', 'azerty123', 'qwerty123', 'admin1234', 'admin@2025!', 'admin@2025', '12345678',
    '123456789', '1234567890', 'password1', 'abcd1234', 'azertyuiop', 'ecole1234', 'changeme1',
}


def _maintenant():
    return datetime.datetime.utcnow()


def _fmt(d):
    return d.strftime('%Y-%m-%d %H:%M:%S')


def adresse_client():
    """Adresse du visiteur : sur Render la dernière valeur de X-Forwarded-For est ajoutée par le
    relais de confiance (les valeurs précédentes peuvent être inventées par le visiteur)."""
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[-1].strip()
    return request.remote_addr or 'inconnue'


def cles_connexion(ecole_ref, username):
    return [f"u:{ecole_ref}:{(username or '').strip().lower()}", f"ip:{adresse_client()}"]


def secondes_restantes(cles):
    """0 si la connexion peut être tentée, sinon le nombre de secondes avant la fin du blocage."""
    maintenant = _maintenant()
    reste = 0
    for cle in cles:
        r = db.execute("SELECT bloque_jusqu FROM echecs_connexion WHERE cle=?", (cle,)).fetchone()
        if r and r['bloque_jusqu']:
            fin = datetime.datetime.strptime(r['bloque_jusqu'], '%Y-%m-%d %H:%M:%S')
            if fin > maintenant:
                reste = max(reste, int((fin - maintenant).total_seconds()) + 1)
    return reste


def enregistrer_echec(cles):
    """Compte l'échec. Renvoie True si cet échec vient de BLOQUER l'identifiant (pour alerter le titulaire)."""
    maintenant = _maintenant()
    vient_de_bloquer = False
    for cle in cles:
        limite = LIMITE_ADRESSE if cle.startswith('ip:') else LIMITE_IDENTIFIANT
        r = db.execute("SELECT nombre, debut FROM echecs_connexion WHERE cle=?", (cle,)).fetchone()
        debut = datetime.datetime.strptime(r['debut'], '%Y-%m-%d %H:%M:%S') if r else None
        if not r or maintenant - debut > FENETRE:
            nombre, debut = 1, maintenant
        else:
            nombre = r['nombre'] + 1
        bloque = _fmt(maintenant + FENETRE) if nombre >= limite else None
        if bloque and cle.startswith('u:') and nombre == limite:
            vient_de_bloquer = True
        db.execute("INSERT INTO echecs_connexion (cle, nombre, debut, bloque_jusqu) VALUES (?,?,?,?) "
                   "ON CONFLICT(cle) DO UPDATE SET nombre=excluded.nombre, debut=excluded.debut, "
                   "bloque_jusqu=excluded.bloque_jusqu", (cle, nombre, _fmt(debut), bloque))
    db.commit()
    return vient_de_bloquer


def effacer_echecs(cle_identifiant):
    db.execute("DELETE FROM echecs_connexion WHERE cle=?", (cle_identifiant,))
    db.commit()


ROLES_SENSIBLES = ('admin', 'directeur', 'comptable')     # mot de passe de 12 caractères, double authentification obligatoire


def erreur_mot_de_passe(mdp, username=None, role=None):
    """Message d'erreur si le mot de passe est trop faible, sinon None.
    8 caractères minimum (12 pour administrateurs, directeurs et comptables), avec majuscule, minuscule,
    chiffre et symbole ; refus des mots de passe courants, uniquement numériques ou proches de l'identifiant."""
    mdp = mdp or ''
    minimum = 12 if role in ROLES_SENSIBLES else 8
    if len(mdp) < minimum:
        return f'Le mot de passe doit contenir au moins {minimum} caractères'
    if mdp.isdigit():
        return 'Le mot de passe ne peut pas être uniquement numérique'
    if not (any(c.islower() for c in mdp) and any(c.isupper() for c in mdp)
            and any(c.isdigit() for c in mdp) and any(not c.isalnum() for c in mdp)):
        return 'Le mot de passe doit contenir une majuscule, une minuscule, un chiffre et un symbole (ex : ! @ # ?)'
    bas = mdp.lower()
    if bas in MOTS_DE_PASSE_COURANTS or any(c in bas for c in ('motdepasse', 'password', 'azerty', 'qwerty', '123456')):
        return 'Ce mot de passe est trop courant : choisissez-en un autre'
    u = (username or '').strip().lower()
    if len(u) >= 3 and (u in bas or bas in u):
        return "Le mot de passe est trop proche de l'identifiant"
    return None


# ── Limitation de débit : 10/min sur la connexion, 60/min visiteur anonyme, 300/min utilisateur connecté ──
import threading
import time as _time

LIMITES_DEBIT = {'connexion': 10, 'anonyme': 60, 'connecte': 300}
_debit = {}
_verrou_debit = threading.Lock()


def debit_depasse(categorie, cle):
    """Fenêtre glissante d'une minute. Renvoie les secondes à attendre si la limite est dépassée, sinon 0."""
    maintenant = _time.time()
    with _verrou_debit:
        passes = [t for t in _debit.get((categorie, cle), []) if maintenant - t < 60]
        if len(passes) >= LIMITES_DEBIT[categorie]:
            _debit[(categorie, cle)] = passes
            return int(60 - (maintenant - passes[0])) + 1
        passes.append(maintenant)
        _debit[(categorie, cle)] = passes
        if len(_debit) > 20000:
            _debit.clear()
    return 0


def debit_assistant(user_id, limite):
    """Messages à l'assistante : au plus `limite` par minute et par utilisateur. Renvoie les secondes à attendre ou 0."""
    maintenant = _time.time()
    cle = ('assistant', user_id)
    with _verrou_debit:
        passes = [t for t in _debit.get(cle, []) if maintenant - t < 60]
        if len(passes) >= limite:
            _debit[cle] = passes
            return int(60 - (maintenant - passes[0])) + 1
        passes.append(maintenant)
        _debit[cle] = passes
    return 0
