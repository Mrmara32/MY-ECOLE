"""
Outils système réservés au super-administrateur : sauvegardes de la base.

Une sauvegarde contient TOUTES les écoles de l'installation : seul le
super-administrateur y a donc accès (jamais l'administrateur d'une école cliente).
"""
from datetime import datetime

from flask import Blueprint, jsonify, send_file, g

import sauvegarde
from auth import require_auth, require_super_admin
from database import log_action

bp = Blueprint('systeme_routes', __name__, url_prefix='/api/systeme')


@bp.route('/sauvegardes', methods=['GET'])
@require_auth
@require_super_admin
def lister_sauvegardes():
    return jsonify({
        'sauvegardes': sauvegarde.lister(),
        'conservees': sauvegarde.NB_A_CONSERVER,
    })


@bp.route('/sauvegardes/maintenant', methods=['GET'])
@require_auth
@require_super_admin
def telecharger_sauvegarde_maintenant():
    contenu = sauvegarde.archive_en_memoire()
    log_action(g.user, 'telechargement', 'sauvegarde', None, {'type': 'copie immédiate'})
    return send_file(contenu, mimetype='application/zip', as_attachment=True,
                     download_name=f"my-ecole-sauvegarde-{datetime.now():%Y-%m-%d-%H%M}.zip")


@bp.route('/sauvegardes/<nom>', methods=['GET'])
@require_auth
@require_super_admin
def telecharger_sauvegarde(nom):
    chemin = sauvegarde.chemin_sauvegarde(nom)
    if not chemin:
        return jsonify({'error': 'Sauvegarde introuvable'}), 404
    log_action(g.user, 'telechargement', 'sauvegarde', nom, {'type': 'copie automatique'})
    return send_file(chemin, mimetype='application/zip', as_attachment=True, download_name=nom)
