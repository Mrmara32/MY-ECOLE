"""
Sauvegardes de la base de données MY-ECOLE.

1. Copie AUTOMATIQUE une fois par jour, rangée à côté de la base (dossier
   « sauvegardes »), en conservant les 14 dernières (réglable avec GS_BACKUP_JOURS).
   Protège contre une erreur de manipulation ou une base abîmée : on peut revenir
   à l'état d'un jour précis.
2. Copie À LA DEMANDE, téléchargeable par le super-administrateur depuis
   Paramètres → Sauvegardes : c'est elle qu'il faut conserver régulièrement HORS
   du serveur (clé USB, Google Drive…), seule vraie protection en cas de perte
   totale du serveur ou du poste.

Les copies utilisent l'API de sauvegarde intégrée à SQLite : elles sont toujours
cohérentes, même si des utilisateurs travaillent au même moment. Chaque copie est
un fichier .zip contenant ecole.db (s'ouvre directement sous Windows).
"""
import io
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime

import database

DOSSIER = os.environ.get('GS_BACKUP_DIR') or os.path.join(database.DATA_DIR, 'sauvegardes')
NB_A_CONSERVER = max(1, int(os.environ.get('GS_BACKUP_JOURS', '14')))
FORMAT_NOM = re.compile(r'^ecole-\d{4}-\d{2}-\d{2}\.zip$')

_verrou = threading.Lock()
_demarre = False


def preparer_dossier():
    os.makedirs(DOSSIER, exist_ok=True)
    return DOSSIER


def _copier_base_vers(destination):
    """Copie cohérente de la base, même pendant que d'autres utilisateurs écrivent."""
    if database.USE_PG:
        import pg_migration       # PostgreSQL : on exporte vers un fichier SQLite portable (même format de sauvegarde)
        return pg_migration.exporter_vers_sqlite(destination)
    source = sqlite3.connect(database.DB_PATH, timeout=database.DELAI_ATTENTE_VERROU_S)
    try:
        cible = sqlite3.connect(destination)
        try:
            source.backup(cible)
        finally:
            cible.close()
    finally:
        source.close()


def _creer_zip(chemin_zip):
    with tempfile.TemporaryDirectory(dir=preparer_dossier()) as dossier_temp:
        copie = os.path.join(dossier_temp, 'ecole.db')
        _copier_base_vers(copie)
        with zipfile.ZipFile(chemin_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(copie, arcname='ecole.db')


def sauvegarde_du_jour():
    """Crée la copie du jour si elle n'existe pas encore. Renvoie son chemin, ou None
    si elle existait déjà."""
    with _verrou:
        nom = f"ecole-{datetime.now():%Y-%m-%d}.zip"
        chemin = os.path.join(preparer_dossier(), nom)
        if os.path.exists(chemin):
            return None
        partiel = chemin + '.partiel'
        _creer_zip(partiel)
        os.replace(partiel, chemin)  # le fichier n'apparaît qu'une fois complet
        _supprimer_anciennes()
        return chemin


def _supprimer_anciennes():
    fichiers = sorted(f for f in os.listdir(DOSSIER) if FORMAT_NOM.match(f))
    for ancien in fichiers[:-NB_A_CONSERVER]:
        try:
            os.remove(os.path.join(DOSSIER, ancien))
        except OSError:
            pass


def lister():
    if not os.path.isdir(DOSSIER):
        return []
    resultat = []
    for nom in sorted(os.listdir(DOSSIER), reverse=True):
        if FORMAT_NOM.match(nom):
            infos = os.stat(os.path.join(DOSSIER, nom))
            resultat.append({
                'nom': nom,
                'taille': infos.st_size,
                'date': datetime.fromtimestamp(infos.st_mtime).strftime('%Y-%m-%d %H:%M'),
            })
    return resultat


def chemin_sauvegarde(nom):
    """Chemin d'une copie automatique existante — uniquement si le nom a exactement
    le format attendu (ecole-AAAA-MM-JJ.zip)."""
    if not nom or not FORMAT_NOM.match(nom):
        return None
    chemin = os.path.join(DOSSIER, nom)
    return chemin if os.path.isfile(chemin) else None


def archive_en_memoire():
    """Copie fraîche de la base, compressée, prête à être téléchargée."""
    descripteur, chemin_zip = tempfile.mkstemp(suffix='.zip', dir=preparer_dossier())
    os.close(descripteur)
    try:
        _creer_zip(chemin_zip)
        with open(chemin_zip, 'rb') as f:
            return io.BytesIO(f.read())
    finally:
        try:
            os.remove(chemin_zip)
        except OSError:
            pass


def demarrer_sauvegardes_automatiques(intervalle_s=3600):
    """Vérifie toutes les heures que la copie du jour existe (thread en arrière-plan).
    Désactivable avec GS_BACKUP_DESACTIVE=1."""
    global _demarre
    if _demarre or os.environ.get('GS_BACKUP_DESACTIVE') == '1':
        return
    _demarre = True

    def boucle():
        time.sleep(60)  # laisse le serveur finir de démarrer
        while True:
            try:
                chemin = sauvegarde_du_jour()
                if chemin:
                    print(f"[sauvegarde] Copie du jour créée : {chemin}", flush=True)
            except Exception as e:
                print(f"[sauvegarde] Échec de la copie automatique : {e}", flush=True)
            try:
                import sauvegarde_externe
                envoye = sauvegarde_externe.envoyer_si_besoin()
                if envoye:
                    print(f"[sauvegarde] Copie envoyée hors serveur : {envoye}", flush=True)
            except Exception as e:
                print(f"[sauvegarde] Échec de l'envoi hors serveur (nouvel essai dans 1 h) : {e}", flush=True)
            time.sleep(intervalle_s)

    threading.Thread(target=boucle, name='sauvegardes-automatiques', daemon=True).start()
