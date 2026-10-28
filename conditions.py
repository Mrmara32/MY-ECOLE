"""Conditions d'utilisation et politique de confidentialité : version en vigueur, acceptation
obligatoire aux inscriptions publiques, et coordonnées de l'éditeur (Actif System Groupe).

Changer VERSION_CONDITIONS (et les pages public/conditions.html / confidentialite.html) fait
redemander l'acceptation à chaque membre du personnel à sa prochaine connexion."""
import os
import re

from flask import jsonify

from database import log_action

VERSION_CONDITIONS = '2026-10-28'
_VRAI = (True, 'true', 'on', '1', 1, 'oui')


def acceptation_manquante(body):
    """None si l'utilisateur a coché la case ; sinon la réponse d'erreur 400 à renvoyer."""
    if (body or {}).get('accepte_conditions') in _VRAI:
        return None
    return jsonify({'error': "Vous devez accepter les conditions d'utilisation et la politique de "
                             "confidentialité pour continuer."}), 400


def journaliser(ecole_id, qui, contexte, user_id=None):
    """Trace de l'acceptation (date, version, contexte) dans le journal d'audit."""
    log_action({'id': user_id, 'name': qui or 'Visiteur', 'ecole_id': ecole_id}, 'acceptation_conditions',
               'conditions', VERSION_CONDITIONS, {'contexte': contexte, 'version': VERSION_CONDITIONS})


def contact_editeur():
    """Coordonnées d'Actif System Groupe. L'e-mail est lu dans EDITEUR_EMAIL (aucune adresse n'est
    inventée : tant qu'il n'est pas défini, il n'est simplement pas affiché)."""
    tel = (os.environ.get('EDITEUR_TEL') or '661-97-43-43').strip()
    chiffres = re.sub(r'\D', '', os.environ.get('EDITEUR_WHATSAPP') or tel)
    if len(chiffres) == 9:
        chiffres = '224' + chiffres
    return {'nom': 'Actif System Groupe', 'telephone': tel, 'whatsapp': chiffres,
            'email': (os.environ.get('EDITEUR_EMAIL') or '').strip()}
