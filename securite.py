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
    maintenant = _maintenant()
    for cle in cles:
        limite = LIMITE_ADRESSE if cle.startswith('ip:') else LIMITE_IDENTIFIANT
        r = db.execute("SELECT nombre, debut FROM echecs_connexion WHERE cle=?", (cle,)).fetchone()
        debut = datetime.datetime.strptime(r['debut'], '%Y-%m-%d %H:%M:%S') if r else None
        if not r or maintenant - debut > FENETRE:
            nombre, debut = 1, maintenant
        else:
            nombre = r['nombre'] + 1
        bloque = _fmt(maintenant + FENETRE) if nombre >= limite else None
        db.execute("INSERT INTO echecs_connexion (cle, nombre, debut, bloque_jusqu) VALUES (?,?,?,?) "
                   "ON CONFLICT(cle) DO UPDATE SET nombre=excluded.nombre, debut=excluded.debut, "
                   "bloque_jusqu=excluded.bloque_jusqu", (cle, nombre, _fmt(debut), bloque))
    db.commit()


def effacer_echecs(cle_identifiant):
    db.execute("DELETE FROM echecs_connexion WHERE cle=?", (cle_identifiant,))
    db.commit()


def erreur_mot_de_passe(mdp):
    """Message d'erreur si le mot de passe est trop faible, sinon None."""
    mdp = mdp or ''
    if len(mdp) < 8:
        return 'Le mot de passe doit contenir au moins 8 caractères'
    if not any(c.isalpha() for c in mdp) or not any(c.isdigit() for c in mdp):
        return 'Le mot de passe doit contenir au moins une lettre et un chiffre'
    if mdp.lower() in MOTS_DE_PASSE_COURANTS:
        return 'Ce mot de passe est trop courant : choisissez-en un autre'
    return None
