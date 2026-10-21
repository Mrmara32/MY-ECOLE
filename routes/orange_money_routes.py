"""Paiement de la scolarité par Orange Money — voir orange_money_service.py.

Sécurité : la notification d'Orange (appel public, sans connexion) ne fait que DÉCLENCHER une
vérification auprès d'Orange ; le versement n'est enregistré que si Orange confirme « SUCCESS »,
une seule fois, et jamais sur la foi du contenu de l'appel."""
import hmac
import secrets
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


def _creer_lien_paiement(ecole_id, eleve, eleve_id, montant, cree_par, user=None):
    """Crée le paiement chez Orange et le suit en base. Renvoie (dict, None) ou (None, message d'erreur)."""
    rid = gen_id('pol')
    order_id = 'MYE' + rid.replace('-', '')[-14:]
    base = url_application()
    try:
        lien = om.creer_paiement(order_id, montant, f"Scolarite {eleve['matricule'] or ''}".strip(),
                                 f"{base}/api/orange-money/retour?ref={rid}", f"{base}/api/orange-money/retour?ref={rid}",
                                 f"{base}/api/orange-money/notification?ref={rid}")
    except RuntimeError as e:
        return None, str(e)
    debut_ecriture_exclusive()
    db.execute("INSERT INTO paiements_en_ligne (ecole_id,id,eleve_id,montant,order_id,pay_token,notif_token,payment_url,cree_par) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (ecole_id, rid, eleve_id, montant, order_id, lien['pay_token'], lien['notif_token'], lien['payment_url'], cree_par))
    db.commit()
    log_action(user or _systeme(ecole_id), 'lien_orange_money', 'paiement_en_ligne', rid,
               {'eleve': f"{eleve['prenom']} {eleve['nom']}", 'montant': montant, 'origine': 'caisse' if user else 'parent'})
    return {'id': rid, 'payment_url': lien['payment_url'], 'montant': montant}, None


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

    lien, erreur = _creer_lien_paiement(ecole_id, eleve, eleve_id, montant, g.user['id'], g.user)
    if erreur:
        return jsonify({'error': erreur}), 502
    return jsonify(lien)


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
    nom = f"e{g.user['ecole_id']}_om_qr_{secrets.token_hex(12)}{ext}"
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


def _confirmer_au_payeur(ecole_id, d, numero_recu):
    """SMS de confirmation au numéro laissé par le payeur, si l'envoi SMS est configuré.
    Un échec d'envoi ne change jamais l'enregistrement du paiement."""
    import sms_service
    if not sms_service.actif() or not sms_service.numero_international(d['telephone']):
        return
    eleve = db.execute("SELECT nom, prenom FROM eleves WHERE id=?", (d['eleve_id'],)).fetchone()
    ecole = get_settings(ecole_id).get('ecole_nom') or 'Votre école'
    try:
        sms_service.envoyer_sms(d['telephone'], f"{ecole} : paiement Orange Money de {round(d['montant']):,} GNF".replace(',', ' ')
                                + f" bien reçu pour {eleve['prenom']} {eleve['nom']}. Reçu N° {numero_recu}. Merci.")
    except RuntimeError as e:
        print(f"[orange-money] SMS de confirmation non envoyé : {e}")


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
    if resultat.get('statut') == 'valide':
        _confirmer_au_payeur(ecole_id, {'telephone': str(body.get('telephone') or ''), 'eleve_id': body.get('eleve_id'), 'montant': montant}, resultat['numero_recu'])
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
    if statut == 'valide':
        _confirmer_au_payeur(g.user['ecole_id'], d, numero)
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


# ───────────── Page publique « Payer la scolarité » ─────────────
# Le parent saisit nom, prénom et matricule de l'élève : l'application retrouve la fiche, puis
#  - avec l'API Orange : envoie le parent payer chez Orange, la confirmation et la comptabilité sont automatiques ;
#  - sans API (QR marchand) : il paie avec le QR de l'école et saisit le n° de transaction ; la déclaration attend
#    la validation de la comptabilité (sinon n'importe qui pourrait se faire créditer avec un faux numéro).
def _sans_accent(t):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFD', str(t or '')).encode('ascii', 'ignore').decode().lower().split())


def _cle_limite():
    import securite
    return [f"ip:payer:{securite.adresse_client()}"]


def _eleve_public(ecole_id, nom, prenom, matricule):
    """Retrouve l'élève à partir des trois informations saisies, ou None. Comptage des échecs par adresse."""
    import securite
    if securite.secondes_restantes(_cle_limite()):
        return 'bloque'
    mat = ''.join(str(matricule or '').upper().split())
    n, p = _sans_accent(nom), _sans_accent(prenom)
    if mat and n and p:
        for e in db.execute("SELECT id, nom, prenom, classe, matricule, statut FROM eleves WHERE ecole_id=? AND UPPER(REPLACE(matricule,' ',''))=?",
                            (ecole_id, mat)).fetchall():
            if {_sans_accent(e['nom']), _sans_accent(e['prenom'])} == {n, p} or \
               (_sans_accent(e['nom']) == n and _sans_accent(e['prenom']) == p):
                return e
    securite.enregistrer_echec(_cle_limite())
    return None


def _reponse_eleve(e):
    return {'nom': e['nom'], 'prenom': e['prenom'], 'classe': e['classe']}


def _ecole_publique():
    from database import ecole_id_depuis_code
    return ecole_id_depuis_code(request.args.get('ecole') or (request.get_json(silent=True) or {}).get('ecole'))


@bp.route('/public/config', methods=['GET'])
def config_publique():
    ecole_id = _ecole_publique()
    c = _config(ecole_id)
    return jsonify({'ecole_nom': get_settings(ecole_id).get('ecole_nom', ''), 'mode': 'api' if om.actif() else 'qr',
                    'qr_url': c['qr_url'], 'code': c['code'], 'nom': c['nom'], 'instructions': c['instructions']})


def _identifier():
    ecole_id = _ecole_publique()
    b = request.get_json(silent=True) or {}
    e = _eleve_public(ecole_id, b.get('nom'), b.get('prenom'), b.get('matricule'))
    if e == 'bloque':
        return ecole_id, b, None, (jsonify({'error': 'Trop de tentatives : réessayez dans quelques minutes.'}), 429)
    if not e:
        return ecole_id, b, None, (jsonify({'error': "Aucun élève ne correspond à ces trois informations (nom, prénom, matricule). Vérifiez la saisie."}), 404)
    return ecole_id, b, e, None


@bp.route('/public/verifier', methods=['POST'])
def verifier_eleve_public():
    ecole_id, b, e, erreur = _identifier()
    if erreur:
        return erreur
    reste = round(sum(p['montant_du'] - p['montant_paye'] for p in _paiements_dus(ecole_id, e['id'])))
    return jsonify({'eleve': _reponse_eleve(e), 'reste': reste})


@bp.route('/public/payer', methods=['POST'])
def payer_public():
    ecole_id, b, e, erreur = _identifier()
    if erreur:
        return erreur
    reste = round(sum(p['montant_du'] - p['montant_paye'] for p in _paiements_dus(ecole_id, e['id'])))
    if reste <= 0:
        return jsonify({'error': "Aucun solde à régler pour cet élève : merci !"}), 400
    try:
        montant = round(float(b.get('montant'))) if b.get('montant') not in (None, '') else reste
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if montant < MONTANT_MIN or montant > reste:
        return jsonify({'error': f'Le montant doit être compris entre {MONTANT_MIN} et {reste} GNF'}), 400
    if om.actif():
        lien, err = _creer_lien_paiement(ecole_id, e, e['id'], montant, None)
        if err:
            return jsonify({'error': "Le paiement en ligne est momentanément indisponible. Réessayez plus tard."}), 502
        return jsonify({'mode': 'api', 'payment_url': lien['payment_url']})
    transaction = _normaliser_transaction(b.get('transaction_id'))
    if len(transaction) < 6:
        return jsonify({'error': "Saisissez le numéro de transaction reçu par SMS après votre paiement Orange Money"}), 400
    did = gen_id('omd')
    debut_ecriture_exclusive()
    if db.execute("SELECT 1 FROM paiements_om_declares WHERE ecole_id=? AND transaction_id=?", (ecole_id, transaction)).fetchone():
        db.commit()
        return jsonify({'error': 'Ce numéro de transaction a déjà été enregistré'}), 409
    db.execute("INSERT INTO paiements_om_declares (ecole_id,id,eleve_id,montant,transaction_id,telephone,declare_par) VALUES (?,?,?,?,?,?,?)",
               (ecole_id, did, e['id'], montant, transaction, str(b.get('telephone') or '')[:20], 'parent (page publique)'))
    db.commit()
    log_action(_systeme(ecole_id), 'declaration_orange_money', 'paiement_om', did,
               {'eleve': f"{e['prenom']} {e['nom']}", 'montant': montant, 'transaction': transaction, 'origine': 'page publique'})
    return jsonify({'mode': 'qr', 'ok': True})


# ───────────── Rapprochement avec le relevé Orange Money Marchand ─────────────
@bp.route('/declarations/rapprocher', methods=['POST'])
@require_auth
@require_role(*ROLES_LIEN)
def rapprocher():
    """Compare les paiements « à valider » au relevé d'opérations téléchargé depuis Orange Money Marchand
    (CSV ou Excel, n'importe quelle disposition de colonnes). Un paiement n'est « confirmé » que si son numéro
    de transaction ET son montant figurent sur la MÊME ligne du relevé. Sans `appliquer=1`, rien n'est modifié."""
    import os
    from releve_bancaire import lignes_brutes, lire_montant
    fichier = request.files.get('fichier')
    if not fichier or not fichier.filename:
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    contenu = fichier.read(5 * 1024 * 1024 + 1)
    if len(contenu) > 5 * 1024 * 1024:
        return jsonify({'error': 'Fichier trop volumineux (5 Mo maximum)'}), 413
    lignes, erreur = lignes_brutes(contenu, os.path.splitext(fichier.filename)[1].lower())
    if erreur:
        return jsonify({'error': erreur}), 400
    analysees = []
    for ligne in lignes:
        cellules = [_normaliser_transaction(c) for c in ligne if c is not None]
        montants = set()
        for c in ligne:
            m = lire_montant(c)
            if m is not None:
                montants.add(round(abs(m)))
        analysees.append((cellules, montants))

    ecole_id = g.user['ecole_id']
    attente = db.execute(
        "SELECT d.id, d.montant, d.transaction_id, e.nom, e.prenom FROM paiements_om_declares d "
        "JOIN eleves e ON e.id=d.eleve_id WHERE d.ecole_id=? AND d.statut='a_valider' ORDER BY d.created_at", (ecole_id,)).fetchall()
    resultat = []
    for d in attente:
        etat, trouves = 'introuvable', []
        for cellules, montants in analysees:
            if any(c == d['transaction_id'] or (len(d['transaction_id']) >= 8 and d['transaction_id'] in c) for c in cellules):
                if round(d['montant']) in montants:
                    etat, trouves = 'confirme', []
                    break
                etat, trouves = 'montant_different', sorted(m for m in montants if m >= MONTANT_MIN)
        resultat.append({'id': d['id'], 'eleve': f"{d['prenom']} {d['nom']}", 'montant': d['montant'],
                         'transaction_id': d['transaction_id'], 'etat': etat, 'montants_releve': trouves})
    valides = 0
    if request.form.get('appliquer') == '1':
        debut_ecriture_exclusive()
        for r in resultat:
            if r['etat'] != 'confirme':
                continue
            d = db.execute("SELECT * FROM paiements_om_declares WHERE id=? AND ecole_id=? AND statut='a_valider'", (r['id'], ecole_id)).fetchone()
            if not d:
                continue
            numero, affectes = _appliquer_declaration(d, g.user)
            statut = 'valide' if affectes else 'a_verifier'
            db.execute("UPDATE paiements_om_declares SET statut=?, valide_par=?, valide_le=?, numero_recu=? WHERE id=?",
                       (statut, g.user['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), numero, d['id']))
            r['etat'], r['numero_recu'] = statut, numero
            valides += 1
        db.commit()
        for r in resultat:
            if r.get('numero_recu'):
                log_action(g.user, 'validation_orange_money', 'paiement_om', r['id'],
                           {'montant': r['montant'], 'transaction': r['transaction_id'], 'numero_recu': r['numero_recu'], 'via': 'relevé Orange'})
                d = db.execute("SELECT * FROM paiements_om_declares WHERE id=?", (r['id'],)).fetchone()
                if r['etat'] == 'valide':
                    _confirmer_au_payeur(ecole_id, d, r['numero_recu'])
    compte = {k: sum(1 for r in resultat if r['etat'] == k) for k in ('confirme', 'montant_different', 'introuvable', 'valide', 'a_verifier')}
    return jsonify({'resultat': resultat, 'compte': compte, 'valides': valides})
