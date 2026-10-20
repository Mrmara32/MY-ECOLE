"""
Paiement de la scolarité par Orange Money (API « Orange Money Web Payment », developer.orange.com).

Déroulement : l'école génère un lien de paiement pour un élève → le parent l'ouvre, confirme avec
son code Orange Money → Orange prévient l'application → l'application VÉRIFIE auprès d'Orange que le
paiement est réussi, puis enregistre le versement et le reçu. Aucun montant n'est jamais cru sur
la seule parole de l'appel entrant.

Il faut un compte MARCHAND Orange Money (pas un compte personnel) : s'abonner en boutique Orange
avec les documents de l'entreprise (registre de commerce, NIF, pièces d'identité des dirigeants),
puis ouvrir une application « Orange Money Web Payment » sur developer.orange.com.

Variables d'environnement (Render) :
  OM_AUTH           l'en-tête d'autorisation de l'application (« Basic xxxx »), ou à défaut
                    OM_CLIENT_ID + OM_CLIENT_SECRET
  OM_MERCHANT_KEY   la clé marchand fournie par Orange
  OM_MODE           « test » (bac à sable : chemin dev, devise OUV — défaut) ou « prod » (chemin gn, devise GNF)
  URL_APPLICATION   adresse publique de l'application (pour le retour et la notification)

Le contrat d'API suit les intégrations publiques connues ; chemin pays, devise et plafonds sont à
CONFIRMER dans le bac à sable d'Orange avant le passage en production.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

_verrou = threading.Lock()
_jeton = {'valeur': None, 'expire': 0}


def _val(nom):
    return (os.environ.get(nom) or '').strip()


def _en_tete_auth():
    if _val('OM_AUTH'):
        return _val('OM_AUTH')
    if _val('OM_CLIENT_ID') and _val('OM_CLIENT_SECRET'):
        return 'Basic ' + base64.b64encode(f"{_val('OM_CLIENT_ID')}:{_val('OM_CLIENT_SECRET')}".encode()).decode()
    return ''


def reglages_manquants():
    m = []
    if not _en_tete_auth():
        m.append('OM_AUTH')
    if not _val('OM_MERCHANT_KEY'):
        m.append('OM_MERCHANT_KEY')
    return m


def actif():
    return not reglages_manquants()


def mode():
    return 'prod' if _val('OM_MODE').lower() == 'prod' else 'test'


def _chemin_pays():
    return 'gn' if mode() == 'prod' else 'dev'


def devise():
    return 'GNF' if mode() == 'prod' else 'OUV'


def _base():
    return (_val('OM_API_URL') or 'https://api.orange.com').rstrip('/')


def _appel(url, donnees, entetes, form=False):
    corps = donnees if form else json.dumps(donnees).encode()
    req = urllib.request.Request(url, data=corps, method='POST', headers=entetes)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            detail = e.read()[:300].decode(errors='replace')
        except Exception:
            detail = ''
        raise RuntimeError(f"Orange Money a refusé la demande (HTTP {e.code}) : {detail}"[:350])
    except urllib.error.URLError as e:
        raise RuntimeError(f"Orange Money injoignable : {e.reason}")


def _obtenir_jeton(forcer=False):
    with _verrou:
        if not forcer and _jeton['valeur'] and time.time() < _jeton['expire']:
            return _jeton['valeur']
        rep = _appel(_base() + '/oauth/v3/token', b'grant_type=client_credentials',
                     {'Authorization': _en_tete_auth(), 'Content-Type': 'application/x-www-form-urlencoded',
                      'Accept': 'application/json'}, form=True)
        if not rep.get('access_token'):
            raise RuntimeError("Orange Money n'a pas renvoyé de jeton d'accès")
        _jeton['valeur'] = rep['access_token']
        _jeton['expire'] = time.time() + max(60, int(rep.get('expires_in', 3600)) - 120)
        return _jeton['valeur']


def _appel_api(chemin, donnees):
    for tentative in (1, 2):
        try:
            return _appel(f"{_base()}/orange-money-webpay/{_chemin_pays()}/v1/{chemin}", donnees,
                          {'Authorization': 'Bearer ' + _obtenir_jeton(forcer=tentative == 2),
                           'Content-Type': 'application/json', 'Accept': 'application/json'})
        except RuntimeError as e:
            if tentative == 1 and 'HTTP 401' in str(e):
                continue
            raise


def creer_paiement(order_id, montant, reference, url_retour, url_annulation, url_notification):
    """Renvoie {'payment_url', 'pay_token', 'notif_token'}."""
    if not actif():
        raise RuntimeError('Orange Money non configuré : ' + ', '.join(reglages_manquants()))
    rep = _appel_api('webpayment', {
        'merchant_key': _val('OM_MERCHANT_KEY'), 'currency': devise(), 'order_id': order_id,
        'amount': int(montant), 'return_url': url_retour, 'cancel_url': url_annulation,
        'notif_url': url_notification, 'lang': 'fr', 'reference': str(reference)[:30]})
    if not rep.get('payment_url') or not rep.get('pay_token'):
        raise RuntimeError("Orange Money n'a pas renvoyé de lien de paiement : " + json.dumps(rep)[:200])
    return {'payment_url': rep['payment_url'], 'pay_token': rep['pay_token'], 'notif_token': rep.get('notif_token')}


def statut_paiement(order_id, montant, pay_token):
    """'reussi', 'echoue' ou 'en_attente'. Une panne n'est jamais prise pour un échec : elle lève RuntimeError."""
    rep = _appel_api('transactionstatus', {'order_id': order_id, 'amount': int(montant), 'pay_token': pay_token})
    etat = str(rep.get('status') or '').upper()
    if etat == 'SUCCESS':
        return 'reussi'
    if etat in ('FAILED', 'EXPIRED'):
        return 'echoue'
    return 'en_attente'
