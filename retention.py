"""
Durées de conservation des données personnelles (limitation de la conservation : RGPD art. 5,
lois nationales de protection des données).

  * élèves : un dossier d'ancien élève (statut ≠ actif) sans activité depuis N années (10 par défaut)
    devient « à anonymiser » ; la direction valide l'anonymisation en lot (jamais automatique,
    car elle est irréversible et certains dossiers doivent être gardés plus longtemps par la loi) ;
  * journal d'audit : purgé automatiquement au-delà de N mois (36 par défaut, 12 minimum) ;
  * jetons de session révoqués : purgés dès leur expiration.
"""
import threading
import time
from datetime import datetime, timedelta

from database import db

DEFAUT_ELEVES_ANNEES = 10
DEFAUT_JOURNAL_MOIS = 36


def _reglage(ecole_id, cle, defaut):
    r = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle=?", (ecole_id, cle)).fetchone()
    try:
        return int(r['valeur']) if r and r['valeur'] not in (None, '') else defaut
    except (ValueError, TypeError):
        return defaut


def politique(ecole_id):
    return {'eleves_annees': _reglage(ecole_id, 'retention_eleves_annees', DEFAUT_ELEVES_ANNEES),
            'journal_mois': _reglage(ecole_id, 'retention_journal_mois', DEFAUT_JOURNAL_MOIS)}


def enregistrer_politique(ecole_id, eleves_annees=None, journal_mois=None):
    for cle, val, mini in (('retention_eleves_annees', eleves_annees, 1), ('retention_journal_mois', journal_mois, 12)):
        if val is None:
            continue
        try:
            val = int(val)
        except (ValueError, TypeError):
            raise ValueError('Valeur numérique attendue')
        if val < mini or val > 100:
            raise ValueError(f'La durée doit être comprise entre {mini} et 100')
        db.execute("INSERT OR REPLACE INTO settings (ecole_id, cle, valeur) VALUES (?,?,?)", (ecole_id, cle, str(val)))
    db.commit()


def candidats_anonymisation(ecole_id, annees):
    """Anciens élèves non encore anonymisés dont la dernière trace (création, note, paiement,
    absence) date de plus de `annees` ans."""
    limite = (datetime.utcnow() - timedelta(days=365 * annees)).strftime('%Y-%m-%d')
    lignes = db.execute(
        """SELECT e.id, e.matricule, e.nom, e.prenom, e.statut, e.created_at,
                  (SELECT MAX(created_at) FROM notes WHERE eleve_id=e.id) AS d_notes,
                  (SELECT MAX(created_at) FROM paiements WHERE eleve_id=e.id) AS d_paie,
                  (SELECT MAX(created_at) FROM absences WHERE eleve_id=e.id) AS d_abs
           FROM eleves e WHERE e.ecole_id=? AND e.statut <> 'actif' AND e.nom <> 'ANONYME'""", (ecole_id,)).fetchall()
    res = []
    for r in lignes:
        dates = [str(d)[:10] for d in (r['created_at'], r['d_notes'], r['d_paie'], r['d_abs']) if d]
        derniere = max(dates) if dates else ''
        if derniere and derniere < limite:
            d = dict(r)
            d['derniere_activite'] = derniere
            res.append(d)
    return res


# Un journal d'audit se conserve au moins 10 ans (pratique comptable internationale / OHADA).
MIN_JOURNAL_MOIS = 120


def purger():
    """Purge technique quotidienne (idempotente) : journaux au-delà de la durée de l'école, jetons expirés."""
    db.execute("DELETE FROM jetons_revoques WHERE expire_le < ?", (int(time.time()),))
    for e in db.execute("SELECT id FROM ecoles").fetchall():
        mois = max(politique(e['id'])['journal_mois'], MIN_JOURNAL_MOIS)
        limite = (datetime.utcnow() - timedelta(days=30 * mois)).strftime('%Y-%m-%d')
        db.execute("DELETE FROM journal_audit WHERE ecole_id=? AND created_at < ?", (e['id'], limite))
    db.commit()


def demarrer_purge_automatique():
    def boucle():
        time.sleep(120)
        while True:
            try:
                purger()
            except Exception as err:  # ne jamais faire tomber le serveur pour un nettoyage
                print(f"[retention] Purge impossible : {err}", flush=True)
            time.sleep(24 * 3600)
    threading.Thread(target=boucle, name='purge-conservation', daemon=True).start()
