"""
Bilan hebdomadaire de l'établissement envoyé par e-mail à la direction (admin et directeur) chaque lundi matin.
Contenu calculé par règles à partir des statistiques agrégées de l'assistante (aucun nom d'élève, aucun appel à l'IA payante).
Désactivable par établissement (paramètre bilan_hebdo_actif = 0) ou globalement (BILAN_HEBDO=0).
"""
import html
import os
import threading
import time
from datetime import datetime, date

import assistant_donnees as ad
from database import db, verrou_ecritures, log_action
import email_service


def _montant(x):
    return f"{x:,.0f}".replace(',', ' ')


def contenu_bilan(ecole_id):
    """HTML du bilan + nombre d'alertes."""
    u = {'id': 0, 'ecole_id': ecole_id, 'role': 'admin'}
    eff = ad.outil_effectifs(u, {})
    pay = ad.outil_paiements(u, {})['ensemble']
    alertes = ad.alertes(u)
    nom = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='ecole_nom'", (ecole_id,)).fetchone()
    lignes_cycle = ''.join(f"<tr><td style='padding:3px 10px 3px 0'>{html.escape(str(k))}</td><td><b>{v}</b></td></tr>"
                           for k, v in eff['par_cycle'].items())
    couleur = {'rouge': '#dc2626', 'orange': '#d97706', 'info': '#2563eb'}
    liste = ''.join(
        f"<li style='margin:8px 0'><span style='color:{couleur[a['niveau']]}'>●</span> <b>{html.escape(a['titre'])}</b><br>"
        f"<span style='color:#6b7280;font-size:13px'>{html.escape(a['detail'])}</span></li>" for a in alertes) \
        or "<li>Aucune alerte cette semaine : tout est en ordre.</li>"
    corps = f"""
      <p>Voici le point de la semaine{' pour <b>' + html.escape(nom['valeur']) + '</b>' if nom and nom['valeur'] else ''} :</p>
      <p><b>{eff['total_eleves_actifs']}</b> élèves actifs, dont <b>{pay['a_jour']}</b> à jour de leurs paiements
         et <b>{pay['avec_impayes']}</b> avec impayés (reste à recouvrer : <b>{_montant(pay['reste_a_payer'])}</b>
         ; taux de recouvrement : <b>{pay['taux_recouvrement_pct'] if pay['taux_recouvrement_pct'] is not None else '—'} %</b>).</p>
      <table style='font-size:14px'>{lignes_cycle}</table>
      <h3 style='color:#0E332C;margin:18px 0 4px'>Points d'attention</h3>
      <ul style='padding-left:18px;margin:0'>{liste}</ul>
      <p style='margin-top:18px'>Ouvrez MY-ECOLE et cliquez sur <b>« Que faire ? »</b> dans « Le point de l'assistante »
         pour obtenir des recommandations détaillées.</p>"""
    return email_service._gabarit("Bilan hebdomadaire de l'école", corps), len(alertes)


def envoyer_bilan(ecole_id, force=False):
    """Envoie le bilan aux administrateurs et directeurs ayant une adresse e-mail. Renvoie le nombre de destinataires."""
    semaine = '%d-W%02d' % date.today().isocalendar()[:2]
    marque = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='bilan_dernier_envoi'", (ecole_id,)).fetchone()
    if not force and marque and marque['valeur'] == semaine:
        return 0
    actif = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='bilan_hebdo_actif'", (ecole_id,)).fetchone()
    if not force and actif and str(actif['valeur']) == '0':
        return 0
    dest = [r['email'] for r in db.execute(
        "SELECT DISTINCT email FROM users WHERE ecole_id=? AND role IN ('admin','directeur') AND active=1 AND email IS NOT NULL AND email<>''",
        (ecole_id,)).fetchall()]
    if not dest:
        return 0
    html_bilan, _ = contenu_bilan(ecole_id)
    envoyes = sum(1 for d in dest if email_service.envoyer_email(d, "Bilan hebdomadaire de votre école — MY-ECOLE", html_bilan))
    if envoyes:
        # Dans une requête (envoi manuel) le verrou d'écriture est déjà tenu ; en tâche de fond, on le prend.
        from flask import has_request_context
        if has_request_context():
            _marquer(ecole_id, semaine)
        else:
            with verrou_ecritures:
                _marquer(ecole_id, semaine)
        log_action({'id': None, 'name': 'Système', 'ecole_id': ecole_id}, 'bilan_hebdomadaire', 'assistant', None, {'destinataires': envoyes})
    return envoyes


def _marquer(ecole_id, semaine):
    db.execute("INSERT OR REPLACE INTO settings (ecole_id, cle, valeur) VALUES (?,?,?)", (ecole_id, 'bilan_dernier_envoi', semaine))
    db.commit()


def envoyer_a_tous():
    for e in db.execute("SELECT id FROM ecoles WHERE actif=1 AND email_confirme=1").fetchall():
        try:
            n = envoyer_bilan(e['id'])
            if n:
                print(f"[bilan] école {e['id']} : {n} e-mail(s) envoyé(s)", flush=True)
        except Exception as err:
            print(f"[bilan] école {e['id']} : échec ({type(err).__name__})", flush=True)


def demarrer_bilan_hebdomadaire():
    """Vérifie chaque heure : le lundi à partir de 7 h (UTC = Conakry), envoie le bilan de la semaine (une seule fois par école)."""
    if os.environ.get('BILAN_HEBDO') == '0':
        return

    def boucle():
        time.sleep(180)
        while True:
            try:
                n = datetime.utcnow()
                if n.weekday() == 0 and n.hour >= 7:
                    envoyer_a_tous()
            except Exception as err:
                print(f"[bilan] erreur : {type(err).__name__}", flush=True)
            time.sleep(3600)
    threading.Thread(target=boucle, name='bilan-hebdomadaire', daemon=True).start()
