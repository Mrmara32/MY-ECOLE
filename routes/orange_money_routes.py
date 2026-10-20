"""Paiement de la scolarité par Orange Money — voir orange_money_service.py.

Sécurité : la notification d'Orange (appel public, sans connexion) ne fait que DÉCLENCHER une
vérification auprès d'Orange ; le versement n'est enregistré que si Orange confirme « SUCCESS »,
une seule fois, et jamais sur la foi du contenu de l'appel."""
import hmac
from datetime import datetime
from html import escape

from flask import Blueprint, Response, g, jsonify, request

import orange_money_service as om
from auth import require_auth, require_role
from database import db, debut_ecriture_exclusive, gen_id, log_action, next_numero_recu, rows_to_list
from email_service import url_application
from routes.finances_routes import appliquer_versement

bp = Blueprint('orange_money_routes', __name__, url_prefix='/api/orange-money')

ROLES_LIEN = ('admin', 'directeur', 'comptable')
MONTANT_MIN = 1000


def _paiements_dus(ecole_id, eleve_id):
    return db.execute(
        "SELECT * FROM paiements WHERE ecole_id=? AND eleve_id=? AND montant_du - montant_paye > 0 "
        "ORDER BY COALESCE(date_echeance, '9999-12-31'), created_at", (ecole_id, eleve_id)).fetchall()


def _systeme(ecole_id):
    return {'id': None, 'name': 'Orange Money', 'ecole_id': ecole_id}


def confirmer(rec):
    """Interroge Orange et, si le paiement est réussi, enregistre les versements (une seule fois).
    Renvoie 'reussi', 'echoue', 'en_attente' ou 'a_verifier'."""
    if rec['statut'] != 'en_attente':
        return rec['statut']
    etat = om.statut_paiement(rec['order_id'], rec['montant'], rec['pay_token'])
    if etat == 'en_attente':
        return 'en_attente'
    ecole_id = rec['ecole_id']
    if etat == 'echoue':
        debut_ecriture_exclusive()
        db.execute("UPDATE paiements_en_ligne SET statut='echoue', confirme_le=? WHERE id=? AND statut='en_attente'",
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), rec['id']))
        db.commit()
        return 'echoue'

    # Réussi : le numéro de reçu est fixé d'abord et conservé sur la ligne, même si deux
    # confirmations se croisent (pas de trou dans la numérotation).
    if not rec['numero_recu']:
        numero = next_numero_recu(ecole_id)
        debut_ecriture_exclusive()
        db.execute("UPDATE paiements_en_ligne SET numero_recu=? WHERE id=? AND numero_recu IS NULL", (numero, rec['id']))
        db.commit()
    debut_ecriture_exclusive()
    rec = db.execute("SELECT * FROM paiements_en_ligne WHERE id=?", (rec['id'],)).fetchone()
    if rec['statut'] != 'en_attente':
        db.commit()
        return rec['statut']
    reste_a_placer = round(rec['montant'])
    dus = _paiements_dus(ecole_id, rec['eleve_id'])
    maintenant = datetime.now().strftime('%Y-%m-%d')
    affectes = []
    for i, pai in enumerate(dus):
        if reste_a_placer <= 0:
            break
        du = round(pai['montant_du'] - pai['montant_paye'])
        part = reste_a_placer if i == len(dus) - 1 else min(du, reste_a_placer)
        appliquer_versement(ecole_id, pai, part, maintenant, 'Orange Money', rec['order_id'], rec['numero_recu'], None)
        affectes.append((pai['id'], part))
        reste_a_placer -= part
    # Rien à imputer (solde réglé entre-temps en caisse) : l'argent est reçu, un humain doit trancher.
    statut = 'reussi' if affectes else 'a_verifier'
    db.execute("UPDATE paiements_en_ligne SET statut=?, confirme_le=? WHERE id=?",
               (statut, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), rec['id']))
    db.commit()
    log_action(_systeme(ecole_id), 'paiement_orange_money', 'paiement_en_ligne', rec['id'],
               {'montant': rec['montant'], 'eleve_id': rec['eleve_id'], 'numero_recu': rec['numero_recu'],
                'paiements': affectes, 'statut': statut})
    return statut


@bp.route('/statut', methods=['GET'])
@require_auth
def statut():
    return jsonify({'actif': om.actif(), 'mode': om.mode()})


@bp.route('/lien', methods=['POST'])
@require_auth
@require_role(*ROLES_LIEN)
def creer_lien():
    """Génère le lien de paiement Orange Money d'un élève (par défaut : tout le solde dû)."""
    if not om.actif():
        return jsonify({'error': 'Orange Money non configuré'}), 503
    ecole_id = g.user['ecole_id']
    body = request.get_json(silent=True) or {}
    eleve_id = body.get('eleve_id')
    eleve = db.execute("SELECT nom, prenom, matricule FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, ecole_id)).fetchone()
    if not eleve:
        return jsonify({'error': 'Élève introuvable'}), 404
    total_du = round(sum(p['montant_du'] - p['montant_paye'] for p in _paiements_dus(ecole_id, eleve_id)))
    if total_du <= 0:
        return jsonify({'error': 'Aucun solde à régler pour cet élève'}), 400
    try:
        montant = round(float(body['montant'])) if body.get('montant') not in (None, '') else total_du
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if montant < MONTANT_MIN or montant > total_du:
        return jsonify({'error': f'Le montant doit être compris entre {MONTANT_MIN} GNF et le solde dû ({total_du} GNF)'}), 400

    rid = gen_id('pol')
    order_id = 'MYE' + rid.replace('-', '')[-14:]
    base = url_application()
    try:
        lien = om.creer_paiement(order_id, montant, f"Scolarite {eleve['matricule'] or ''}".strip(),
                                 f"{base}/api/orange-money/retour?ref={rid}", f"{base}/api/orange-money/retour?ref={rid}",
                                 f"{base}/api/orange-money/notification?ref={rid}")
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 502
    debut_ecriture_exclusive()
    db.execute("INSERT INTO paiements_en_ligne (ecole_id,id,eleve_id,montant,order_id,pay_token,notif_token,payment_url,cree_par) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (ecole_id, rid, eleve_id, montant, order_id, lien['pay_token'], lien['notif_token'], lien['payment_url'], g.user['id']))
    db.commit()
    log_action(g.user, 'lien_orange_money', 'paiement_en_ligne', rid,
               {'eleve': f"{eleve['prenom']} {eleve['nom']}", 'montant': montant})
    return jsonify({'id': rid, 'payment_url': lien['payment_url'], 'montant': montant})


@bp.route('/notification', methods=['POST'])
def notification():
    """Appelée par Orange. Aucune connexion possible : l'authenticité vient du notif_token, et
    le résultat est de toute façon revérifié auprès d'Orange."""
    rec = db.execute("SELECT * FROM paiements_en_ligne WHERE id=?", (request.args.get('ref', ''),)).fetchone()
    body = request.get_json(silent=True) or {}
    jeton = str(body.get('notif_token') or '')
    if not rec or not rec['notif_token'] or not hmac.compare_digest(jeton, rec['notif_token']):
        return jsonify({'error': 'Notification refusée'}), 403
    try:
        confirmer(rec)
    except RuntimeError:
        return jsonify({'ok': False}), 503  # Orange réessaiera ; le parent et l'école peuvent aussi relancer
    return jsonify({'ok': True})


MESSAGES_RETOUR = {
    'reussi': ('✅ Paiement confirmé', "Merci ! Votre paiement a bien été reçu. L'école vous remettra le reçu."),
    'en_attente': ('⏳ Paiement en cours de vérification',
                   "Nous n'avons pas encore la confirmation d'Orange Money. Ne payez pas une seconde fois : "
                   "l'école vérifiera avant de vous solliciter."),
    'echoue': ('❌ Paiement non abouti', "Le paiement n'a pas été effectué. Vous pouvez demander un nouveau lien à l'école."),
    'a_verifier': ('✅ Paiement reçu', "Votre paiement est reçu, l'école le rattachera à votre dossier."),
}


@bp.route('/retour', methods=['GET', 'POST'])
def retour():
    """Page affichée au parent à son retour d'Orange Money."""
    rec = db.execute("SELECT * FROM paiements_en_ligne WHERE id=?", (request.args.get('ref', ''),)).fetchone()
    etat = 'en_attente'
    if rec:
        try:
            etat = confirmer(rec)
        except RuntimeError:
            etat = 'en_attente'
    titre, texte = MESSAGES_RETOUR.get(etat, MESSAGES_RETOUR['en_attente'])
    page = (f'<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Paiement</title><body style="font-family:Arial,sans-serif;max-width:420px;margin:15vh auto;padding:0 20px;text-align:center">'
            f'<h2>{escape(titre)}</h2><p>{escape(texte)}</p></body></html>')
    return Response(page, mimetype='text/html')


@bp.route('/verifier/<rid>', methods=['POST'])
@require_auth
@require_role(*ROLES_LIEN)
def verifier(rid):
    """Revérifie à la main un paiement resté « en attente » (notification perdue)."""
    rec = db.execute("SELECT * FROM paiements_en_ligne WHERE id=? AND ecole_id=?", (rid, g.user['ecole_id'])).fetchone()
    if not rec:
        return jsonify({'error': 'Paiement introuvable'}), 404
    try:
        return jsonify({'statut': confirmer(rec)})
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 502


@bp.route('/paiements', methods=['GET'])
@require_auth
@require_role(*ROLES_LIEN)
def lister():
    rows = db.execute(
        "SELECT p.id, p.montant, p.statut, p.numero_recu, p.created_at, p.confirme_le, e.nom, e.prenom, e.classe "
        "FROM paiements_en_ligne p JOIN eleves e ON e.id=p.eleve_id WHERE p.ecole_id=? "
        "ORDER BY p.created_at DESC LIMIT 100", (g.user['ecole_id'],)).fetchall()
    return jsonify(rows_to_list(rows))
