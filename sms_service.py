"""
Envoi automatique de SMS via l'API « SMS Guinée Conakry » d'Orange (developer.orange.com).

Pourquoi Orange : c'est l'opérateur qui vend directement les SMS en Guinée, par lots payables
avec Orange Money ou du crédit : de 80 à 200 GNF le SMS (≈ 0,01 à 0,02 USD), soit environ cinq
fois moins que les agrégateurs internationaux (≈ 0,09 USD). Voir
https://developer.orange.com/apis/sms-gn/pricing — tarifs à reconfirmer avant achat.

Mise en route (une fois) :
  1. Créer un compte sur developer.orange.com, ajouter l'API « SMS Guinée Conakry » et créer
     une application (MyApps) : le portail donne un « Authorization header » (Basic …).
  2. Acheter un lot de SMS (Configure → bouton d'achat), payable avec Orange Money.
  3. Sur Render, définir :
       ORANGE_SMS_AUTH     l'en-tête d'autorisation de l'application, tel qu'affiché par le portail
                           (« Basic xxxxxxxx ») — ou, à défaut, ORANGE_SMS_CLIENT_ID + ORANGE_SMS_CLIENT_SECRET
       ORANGE_SMS_SENDER   le numéro expéditeur indiqué sur le portail (ex. 224xxxxxxxxx)
       ORANGE_SMS_NOM      optionnel : nom d'expéditeur personnalisé (option payante auprès d'Orange)
L'envoi reste INACTIF tant que ces réglages ne sont pas définis ; les boutons SMS manuels restent.
Limite d'Orange : 5 SMS par seconde.
"""
import base64
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

_verrou = threading.Lock()
_jeton = {'valeur': None, 'expire': 0}
LONGUEUR_MAX = 320  # 2 SMS de 160 caractères

# Caractères hors alphabet GSM courant → équivalent simple, pour tenir dans 160 caractères par SMS
_REMPLACEMENTS = {'’': "'", '‘': "'", '“': '"', '”': '"', '«': '"', '»': '"', '–': '-', '—': '-',
                  '…': '...', 'œ': 'oe', 'Œ': 'OE', ' ': ' ', ' ': ' '}
_GARDES = set("éèùàòìÉçÇøØåÅäöüÄÖÜñÑß")


def _val(nom):
    return (os.environ.get(nom) or '').strip()


def _en_tete_auth():
    if _val('ORANGE_SMS_AUTH'):
        return _val('ORANGE_SMS_AUTH')
    if _val('ORANGE_SMS_CLIENT_ID') and _val('ORANGE_SMS_CLIENT_SECRET'):
        brut = f"{_val('ORANGE_SMS_CLIENT_ID')}:{_val('ORANGE_SMS_CLIENT_SECRET')}".encode()
        return 'Basic ' + base64.b64encode(brut).decode()
    return ''


def reglages_manquants():
    manquants = []
    if not _en_tete_auth():
        manquants.append('ORANGE_SMS_AUTH')
    if not _val('ORANGE_SMS_SENDER'):
        manquants.append('ORANGE_SMS_SENDER')
    return manquants


def actif():
    return not reglages_manquants()


def numero_international(tel):
    n = re.sub(r'[^\d+]', '', str(tel or ''))
    if n.startswith('+'):
        n = n[1:]
    elif n.startswith('00'):
        n = n[2:]
    n = re.sub(r'\D', '', n)
    if len(n) == 9:
        n = '224' + n
    return n if len(n) >= 11 else ''


def nettoyer(texte):
    """Texte prêt pour un SMS : apostrophes/guillemets simples, accents hors alphabet SMS retirés."""
    texte = re.sub(r'«[ \u00a0\u202f]*', '"', str(texte or ''))
    texte = re.sub(r'[ \u00a0\u202f]*»', '"', texte)
    sortie = []
    for c in texte:
        if c in _REMPLACEMENTS:
            sortie.append(_REMPLACEMENTS[c])
            continue
        if ord(c) > 127 and c not in _GARDES:
            c = ''.join(x for x in unicodedata.normalize('NFD', c) if unicodedata.category(x) != 'Mn')
        sortie.append(c)
    return re.sub(r'[ \t]+', ' ', ''.join(sortie)).strip()[:LONGUEUR_MAX]


def _base():
    return (_val('ORANGE_API_URL') or 'https://api.orange.com').rstrip('/')


def _obtenir_jeton():
    with _verrou:
        if _jeton['valeur'] and time.time() < _jeton['expire']:
            return _jeton['valeur']
        req = urllib.request.Request(
            _base() + '/oauth/v3/token', data=b'grant_type=client_credentials', method='POST',
            headers={'Authorization': _en_tete_auth(), 'Content-Type': 'application/x-www-form-urlencoded',
                     'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                rep = json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Orange a refusé l'authentification (HTTP {e.code}) : vérifiez ORANGE_SMS_AUTH")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Orange injoignable : {e.reason}")
        if not rep.get('access_token'):
            raise RuntimeError("Orange n'a pas renvoyé de jeton d'accès")
        _jeton['valeur'] = rep['access_token']
        _jeton['expire'] = time.time() + max(60, int(rep.get('expires_in', 3600)) - 120)
        return _jeton['valeur']


def envoyer_sms(telephone, message):
    """Envoie un SMS. Renvoie l'identifiant d'Orange, ou lève RuntimeError."""
    if not actif():
        raise RuntimeError('SMS automatique non configuré : ' + ', '.join(reglages_manquants()))
    destinataire = numero_international(telephone)
    if not destinataire:
        raise RuntimeError('Numéro de téléphone invalide')
    texte = nettoyer(message)
    if not texte:
        raise RuntimeError('Message vide')
    expediteur = re.sub(r'\D', '', _val('ORANGE_SMS_SENDER'))
    demande = {'address': f'tel:+{destinataire}', 'senderAddress': f'tel:+{expediteur}',
               'outboundSMSTextMessage': {'message': texte}}
    if _val('ORANGE_SMS_NOM'):
        demande['senderName'] = _val('ORANGE_SMS_NOM')
    for tentative in (1, 2):
        jeton = _obtenir_jeton()
        req = urllib.request.Request(
            f"{_base()}/smsmessaging/v1/outbound/{urllib.parse.quote('tel:+' + expediteur, safe='')}/requests",
            data=json.dumps({'outboundSMSMessageRequest': demande}).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + jeton, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                rep = json.loads(r.read() or b'{}')
            url = rep.get('outboundSMSMessageRequest', {}).get('resourceURL') or ''
            return url.rstrip('/').rsplit('/', 1)[-1] or 'ok'
        except urllib.error.HTTPError as e:
            if e.code == 401 and tentative == 1:  # jeton expiré côté Orange : on en redemande un
                _jeton['valeur'] = None
                continue
            try:
                detail = json.loads(e.read()).get('requestError', {}).get('serviceException', {}).get('text', '')
            except Exception:
                detail = ''
            if any(m in detail.lower() for m in ('balance', 'credit', 'bundle')):
                detail = 'Lot de SMS épuisé ou expiré — rachetez un lot sur le portail Orange. ' + detail
            raise RuntimeError(f"Orange a refusé le SMS (HTTP {e.code}) : {detail}"[:300])
        except urllib.error.URLError as e:
            raise RuntimeError(f"Orange injoignable : {e.reason}")
