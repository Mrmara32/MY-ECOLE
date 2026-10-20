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
from database import db, debut_ecriture_exclusive, gen_id, get_settings, log_action, next_numero_recu, rows_to_list
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


def imputer_sur_echeances(ecole_id, eleve_id, montant, reference, numero_recu, recu_par):
    """Répartit un montant reçu par Orange Money sur les échéances impayées de l'élève, les plus
    anciennes d'abord (le surplus éventuel va sur la dernière). À appeler dans le verrou d'écriture ;
    l'appelant valide. Renvoie [(paiement_id, montant imputé)] — vide s'il n'y a plus rien à payer."""
    reste_a_placer = round(montant)
    dus = _paiements_dus(ecole_id, eleve_id)
    maintenant = datetime.now().strftime('%Y-%m-%d')
    affectes = []
    for i, pai in enumerate(dus):
        if reste_a_placer <= 0:
            break
        du = round(pai['montant_du'] - pai['montant_paye'])
        part = reste_a_placer if i == len(dus) - 1 else min(du, reste_a_placer)
        appliquer_versement(ecole_id, pai, part, maintenant, 'Orange Money', reference, numero_recu, recu_par)
        affectes.append((pai['id'], part))
        reste_a_placer -= part
    return affectes


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
    affectes = imputer_sur_echeances(ecole_id, rec['eleve_id'], rec['montant'], rec['order_id'], rec['numero_recu'], None)
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


# ───────────── Paiement marchand par QR (sans API) ─────────────
# Le parent scanne le QR « Paiement marchand » de l'école avec son application Orange Money et reçoit
# un SMS avec un numéro de transaction. La personne qui encaisse enregistre ce numéro ici : il est
# unique (pas de double saisie) et le versement et le reçu suivent.
ROLES_DECLARER = ROLES_LIEN + ('secretaire',)
CLES_CONFIG = ('om_marchand_nom', 'om_marchand_code', 'om_instructions')


def _config(ecole_id):
    s = get_settings(ecole_id)
    return {'nom': s.get('om_marchand_nom', ''), 'code': s.get('om_marchand_code', ''),
            'instructions': s.get('om_instructions', ''), 'qr_url': s.get('om_qr_image', '')}


@bp.route('/config', methods=['GET'])
@require_auth
def lire_config():
    return jsonify(_config(g.user['ecole_id']))


@bp.route('/config', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def ecrire_config():
    body = request.get_json(silent=True) or {}
    for cle, champ in (('om_marchand_nom', 'nom'), ('om_marchand_code', 'code'), ('om_instructions', 'instructions')):
        if champ in body:
            db.execute("INSERT OR REPLACE INTO settings (ecole_id, cle, valeur) VALUES (?,?,?)",
                       (g.user['ecole_id'], cle, str(body[champ] or '').strip()[:500]))
    db.commit()
    return jsonify(_config(g.user['ecole_id']))


@bp.route('/qr', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def televerser_qr():
    """Photo ou capture du QR « Ma carte QR » de l'application Orange Money de l'école."""
    import os
    import random
    import time
    from flask import current_app
    import securite_http
    fichier = request.files.get('qr')
    if not fichier or fichier.filename == '':
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    ext = os.path.splitext(fichier.filename)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp') or not securite_http.est_image(fichier):
        return jsonify({'error': 'Le fichier doit être une vraie image (PNG, JPEG ou WebP)'}), 400
    nom = f"om_qr_{int(time.time() * 1000)}_{random.randint(1000, 9999)}{ext}"
    fichier.save(os.path.join(current_app.config['UPLOAD_DIR'], nom))
    url = '/uploads/' + nom
    db.execute("INSERT OR REPLACE INTO settings (ecole_id, cle, valeur) VALUES (?,?,?)", (g.user['ecole_id'], 'om_qr_image', url))
    db.commit()
    log_action(g.user, 'modification', 'orange_money_qr', None, {'fichier': nom})
    return jsonify({'qr_url': url})


def _normaliser_transaction(t):
    return ''.join(c for c in str(t or '').upper() if c.isalnum() or c in '.-_')[:40]


def _appliquer_declaration(d, valideur):
    """Impute une déclaration déjà verrouillée (statut a_valider). Renvoie le numéro de reçu."""
    ecole_id = d['ecole_id']
    numero = d['numero_recu'] or next_numero_recu(ecole_id)
    affectes = imputer_sur_echeances(ecole_id, d['eleve_id'], d['montant'], 'OM-' + d['transaction_id'], numero, valideur['id'])
    return numero, affectes


@bp.route('/declarations', methods=['POST'])
@require_auth
@require_role(*ROLES_DECLARER)
def declarer():
    ecole_id = g.user['ecole_id']
    body = request.get_json(silent=True) or {}
    eleve = db.execute("SELECT nom, prenom FROM eleves WHERE id=? AND ecole_id=?", (body.get('eleve_id'), ecole_id)).fetchone()
    if not eleve:
        return jsonify({'error': 'Élève introuvable'}), 404
    transaction = _normaliser_transaction(body.get('transaction_id'))
    if len(transaction) < 6:
        return jsonify({'error': "Le numéro de transaction Orange Money (reçu par SMS) est requis"}), 400
    try:
        montant = round(float(body.get('montant')))
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if montant < MONTANT_MIN:
        return jsonify({'error': f'Montant minimum : {MONTANT_MIN} GNF'}), 400
    valider_tout_de_suite = bool(body.get('valider')) and g.user['role'] in ROLES_LIEN
    did = gen_id('omd')
    debut_ecriture_exclusive()
    if db.execute("SELECT 1 FROM paiements_om_declares WHERE ecole_id=? AND transaction_id=?", (ecole_id, transaction)).fetchone():
        db.commit()
        return jsonify({'error': 'Ce numéro de transaction a déjà été enregistré'}), 409
    db.execute("INSERT INTO paiements_om_declares (ecole_id,id,eleve_id,montant,transaction_id,telephone,declare_par) VALUES (?,?,?,?,?,?,?)",
               (ecole_id, did, body.get('eleve_id'), montant, transaction, str(body.get('telephone') or '')[:20], g.user['id']))
    resultat = {'id': did, 'statut': 'a_valider'}
    if valider_tout_de_suite:
        d = db.execute("SELECT * FROM paiements_om_declares WHERE id=?", (did,)).fetchone()
        numero, affectes = _appliquer_declaration(d, g.user)
        statut = 'valide' if affectes else 'a_verifier'
        db.execute("UPDATE paiements_om_declares SET statut=?, valide_par=?, valide_le=?, numero_recu=? WHERE id=?",
                   (statut, g.user['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), numero, did))
        resultat.update(statut=statut, numero_recu=numero)
    db.commit()
    log_action(g.user, 'declaration_orange_money', 'paiement_om', did,
               {'eleve': f"{eleve['prenom']} {eleve['nom']}", 'montant': montant, 'transaction': transaction, **{k: resultat[k] for k in ('statut',)}})
    return jsonify(resultat), 201


@bp.route('/declarations', methods=['GET'])
@require_auth
@require_role(*ROLES_DECLARER)
def lister_declarations():
    statut = request.args.get('statut')
    sql = ("SELECT d.id, d.montant, d.transaction_id, d.telephone, d.statut, d.numero_recu, d.motif_rejet, d.created_at, "
           "e.nom, e.prenom, e.classe FROM paiements_om_declares d JOIN eleves e ON e.id=d.eleve_id WHERE d.ecole_id=?")
    params = [g.user['ecole_id']]
    if statut:
        sql += " AND d.statut=?"
        params.append(statut)
    sql += " ORDER BY d.created_at DESC LIMIT 200"
    return jsonify(rows_to_list(db.execute(sql, params).fetchall()))


@bp.route('/declarations/<did>/valider', methods=['POST'])
@require_auth
@require_role(*ROLES_LIEN)
def valider_declaration(did):
    debut_ecriture_exclusive()
    d = db.execute("SELECT * FROM paiements_om_declares WHERE id=? AND ecole_id=?", (did, g.user['ecole_id'])).fetchone()
    if not d:
        db.commit()
        return jsonify({'error': 'Déclaration introuvable'}), 404
    if d['statut'] != 'a_valider':
        db.commit()
        return jsonify({'error': 'Déjà traitée'}), 409
    numero, affectes = _appliquer_declaration(d, g.user)
    statut = 'valide' if affectes else 'a_verifier'
    db.execute("UPDATE paiements_om_declares SET statut=?, valide_par=?, valide_le=?, numero_recu=? WHERE id=?",
               (statut, g.user['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), numero, did))
    db.commit()
    log_action(g.user, 'validation_orange_money', 'paiement_om', did,
               {'montant': d['montant'], 'transaction': d['transaction_id'], 'numero_recu': numero, 'statut': statut})
    return jsonify({'statut': statut, 'numero_recu': numero})


@bp.route('/declarations/<did>/rejeter', methods=['POST'])
@require_auth
@require_role(*ROLES_LIEN)
def rejeter_declaration(did):
    motif = ((request.get_json(silent=True) or {}).get('motif') or '').strip()
    if len(motif) < 5:
        return jsonify({'error': 'Indiquez le motif du rejet (5 caractères minimum)'}), 400
    debut_ecriture_exclusive()
    cur = db.execute("UPDATE paiements_om_declares SET statut='rejete', motif_rejet=?, valide_par=?, valide_le=? "
                     "WHERE id=? AND ecole_id=? AND statut='a_valider'",
                     (motif, g.user['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), did, g.user['ecole_id']))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({'error': 'Déclaration introuvable ou déjà traitée'}), 404
    log_action(g.user, 'rejet_orange_money', 'paiement_om', did, {'motif': motif})
    return jsonify({'statut': 'rejete'})
