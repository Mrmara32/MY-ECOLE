"""
Envoi automatique de messages WhatsApp via l'API officielle « WhatsApp Business Platform »
(Cloud API de Meta). Les boutons manuels (lien wa.me) restent disponibles : ceci s'y ajoute,
et reste INACTIF tant que les réglages ci-dessous ne sont pas définis.

Règles de WhatsApp : pour écrire le premier à un parent, il faut un MODÈLE de message
(« template ») créé puis approuvé par Meta. Les modèles à créer (catégorie « Utilitaire »,
langue française) — les {{n}} sont remplis automatiquement :

  Absence / retard (nom à mettre dans WHATSAPP_MODELE_ABSENCE) :
    « Bonjour {{1}}, l'école {{5}} vous informe que {{2}} {{3}} le {{4}}. Merci de contacter l'école si besoin. »
    1 = parent, 2 = élève, 3 = « était absent(e) » ou « est arrivé(e) en retard », 4 = date, 5 = école

  Relance de scolarité (nom à mettre dans WHATSAPP_MODELE_RELANCE) :
    « Bonjour {{1}}, l'école {{2}} vous rappelle que la scolarité de {{3}} ({{4}}) présente un solde
      de {{5}}. Merci de bien vouloir régulariser. »
    1 = parent, 2 = école, 3 = élève, 4 = classe, 5 = montant

Variables d'environnement (Render) :
  WHATSAPP_TOKEN            jeton d'accès permanent (utilisateur système de Meta Business)
  WHATSAPP_PHONE_ID         identifiant du numéro d'envoi (« Phone number ID »)
  WHATSAPP_MODELE_ABSENCE   nom du modèle approuvé pour les absences
  WHATSAPP_MODELE_RELANCE   nom du modèle approuvé pour les relances
  WHATSAPP_LANGUE           optionnel, défaut « fr »
Le coût est facturé par Meta à chaque message modèle ; consultez la grille tarifaire
de Meta pour votre pays avant d'activer.
"""
import json
import os
import re
import urllib.error
import urllib.request

VERSION_API = 'v21.0'


def _val(nom):
    return (os.environ.get(nom) or '').strip()


def reglages_manquants():
    return [v for v in ('WHATSAPP_TOKEN', 'WHATSAPP_PHONE_ID', 'WHATSAPP_MODELE_ABSENCE', 'WHATSAPP_MODELE_RELANCE')
            if not _val(v)]


def actif():
    return not reglages_manquants()


def numero_international(tel):
    """Même règle que l'écran : numéros guinéens à 9 chiffres → préfixe 224."""
    n = re.sub(r'[^\d+]', '', str(tel or ''))
    if n.startswith('+'):
        n = n[1:]
    elif n.startswith('00'):
        n = n[2:]
    n = re.sub(r'\D', '', n)
    if len(n) == 9:
        n = '224' + n
    return n if len(n) >= 11 else ''


def _propre(texte):
    """WhatsApp refuse retours à la ligne, tabulations et longues suites d'espaces dans un paramètre."""
    t = re.sub(r'\s+', ' ', str(texte or '')).strip()
    return t[:200] or '-'


def envoyer_modele(telephone, modele, parametres):
    """Envoie un message modèle. Renvoie l'identifiant du message chez Meta, ou lève RuntimeError."""
    if not actif():
        raise RuntimeError('WhatsApp automatique non configuré : ' + ', '.join(reglages_manquants()))
    destinataire = numero_international(telephone)
    if not destinataire:
        raise RuntimeError('Numéro de téléphone invalide')
    charge = {
        'messaging_product': 'whatsapp', 'to': destinataire, 'type': 'template',
        'template': {'name': modele, 'language': {'code': _val('WHATSAPP_LANGUE') or 'fr'},
                     'components': [{'type': 'body',
                                     'parameters': [{'type': 'text', 'text': _propre(p)} for p in parametres]}]},
    }
    base = _val('WHATSAPP_API_URL') or 'https://graph.facebook.com'
    req = urllib.request.Request(
        f"{base.rstrip('/')}/{VERSION_API}/{_val('WHATSAPP_PHONE_ID')}/messages",
        data=json.dumps(charge).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + _val('WHATSAPP_TOKEN'), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            reponse = json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get('error', {}).get('message', '')
        except Exception:
            detail = ''
        raise RuntimeError(f"WhatsApp a refusé le message (HTTP {e.code}) : {detail}"[:300])
    except urllib.error.URLError as e:
        raise RuntimeError(f"WhatsApp injoignable : {e.reason}")
    messages = reponse.get('messages') or []
    return messages[0].get('id') if messages else None


def modele_absence():
    return _val('WHATSAPP_MODELE_ABSENCE')


def modele_relance():
    return _val('WHATSAPP_MODELE_RELANCE')
