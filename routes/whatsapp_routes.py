"""Envoi automatique WhatsApp (absences / retards et relances d'impayés) — voir whatsapp_service.py."""
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import whatsapp_service
from auth import require_auth, require_role
from contact_parent import COLONNES_CONTACT, contact_a_prevenir
from database import db, get_settings, log_action

bp = Blueprint('whatsapp_routes', __name__, url_prefix='/api/whatsapp')

ROLES_ABSENCE = ('admin', 'directeur', 'secretaire')
ROLES_RELANCE = ('admin', 'directeur', 'comptable')
DELAI_ANTI_DOUBLON_H = {'absence': 24 * 365, 'relance': 24}


def _deja_envoye(ecole_id, action, entite, entite_id, depuis_h):
    limite = (datetime.utcnow() - timedelta(hours=depuis_h)).strftime('%Y-%m-%d %H:%M:%S')
    return db.execute(
        "SELECT 1 FROM journal_audit WHERE ecole_id=? AND action=? AND entite=? AND entite_id=? "
        "AND created_at>=? AND details LIKE '%whatsapp_auto%' LIMIT 1",
        (ecole_id, action, entite, entite_id, limite)).fetchone() is not None


def _nom_ecole(ecole_id):
    return get_settings(ecole_id).get('ecole_nom') or 'Votre école'


def _echec(erreur, objet, objet_id):
    log_action(g.user, 'echec_envoi', objet, objet_id, {'canal': 'whatsapp_auto', 'erreur': str(erreur)[:200]})


@bp.route('/statut', methods=['GET'])
@require_auth
def statut():
    return jsonify({'actif': whatsapp_service.actif()})


@bp.route('/absence/<absence_id>', methods=['POST'])
@require_auth
@require_role(*ROLES_ABSENCE)
def prevenir_absence(absence_id):
    if not whatsapp_service.actif():
        return jsonify({'error': 'WhatsApp automatique non configuré'}), 503
    ecole_id = g.user['ecole_id']
    a = db.execute(
        f"""SELECT a.id, a.date_abs, a.type, a.duree, e.nom, e.prenom, {COLONNES_CONTACT}
            FROM absences a JOIN eleves e ON e.id=a.eleve_id AND e.ecole_id=a.ecole_id
            WHERE a.id=? AND a.ecole_id=?""", (absence_id, ecole_id)).fetchone()
    if not a:
        return jsonify({'error': 'Absence introuvable'}), 404
    contact = contact_a_prevenir(a)
    if not contact:
        return jsonify({'error': 'Aucun numéro de parent enregistré pour cet élève'}), 400
    if _deja_envoye(ecole_id, 'prevenir_parent', 'absence', absence_id, DELAI_ANTI_DOUBLON_H['absence']):
        return jsonify({'error': 'Le parent a déjà été prévenu automatiquement pour cette absence'}), 409
    situation = 'est arrivé(e) en retard' if a['type'] == 'retard' else 'était absent(e)'
    date = (a['date_abs'] or '')[:10]
    date_fr = '/'.join(reversed(date.split('-'))) if len(date) == 10 else date
    try:
        mid = whatsapp_service.envoyer_modele(
            contact['telephone'], whatsapp_service.modele_absence(),
            [contact['nom'] or 'Madame, Monsieur', f"{a['prenom']} {a['nom']}", situation, date_fr, _nom_ecole(ecole_id)])
    except RuntimeError as e:
        _echec(e, 'absence', absence_id)
        return jsonify({'error': str(e)}), 502
    log_action(g.user, 'prevenir_parent', 'absence', absence_id,
               {'canal': 'whatsapp_auto', 'eleve': f"{a['prenom']} {a['nom']}", 'date': a['date_abs'],
                'type': a['type'], 'message_id': mid})
    return jsonify({'ok': True, 'message_id': mid})


@bp.route('/relance/<eleve_id>', methods=['POST'])
@require_auth
@require_role(*ROLES_RELANCE)
def relancer_impaye(eleve_id):
    if not whatsapp_service.actif():
        return jsonify({'error': 'WhatsApp automatique non configuré'}), 503
    ecole_id = g.user['ecole_id']
    lignes = db.execute(
        f"""SELECT p.montant_du, p.montant_paye, e.nom, e.prenom, e.classe, {COLONNES_CONTACT}
            FROM paiements p JOIN eleves e ON e.id=p.eleve_id AND e.ecole_id=p.ecole_id
            WHERE p.ecole_id=? AND p.eleve_id=? AND p.montant_du - p.montant_paye > 0""", (ecole_id, eleve_id)).fetchall()
    if not lignes:
        return jsonify({'error': 'Aucun solde à régler pour cet élève'}), 400
    reste = round(sum((r['montant_du'] or 0) - (r['montant_paye'] or 0) for r in lignes))
    e = lignes[0]
    contact = contact_a_prevenir(e)
    if not contact:
        return jsonify({'error': 'Aucun numéro de parent enregistré pour cet élève'}), 400
    if _deja_envoye(ecole_id, 'relance', 'relance', eleve_id, DELAI_ANTI_DOUBLON_H['relance']):
        return jsonify({'error': 'Une relance automatique a déjà été envoyée dans les dernières 24 h'}), 409
    montant = f"{reste:,}".replace(',', ' ') + ' GNF'
    try:
        mid = whatsapp_service.envoyer_modele(
            contact['telephone'], whatsapp_service.modele_relance(),
            [contact['nom'] or 'Madame, Monsieur', _nom_ecole(ecole_id), f"{e['prenom']} {e['nom']}", e['classe'] or '-', montant])
    except RuntimeError as err:
        _echec(err, 'relance', eleve_id)
        return jsonify({'error': str(err)}), 502
    log_action(g.user, 'relance', 'relance', eleve_id,
               {'canal': 'whatsapp_auto', 'eleve': f"{e['prenom']} {e['nom']}", 'reste': reste, 'message_id': mid})
    return jsonify({'ok': True, 'message_id': mid})
