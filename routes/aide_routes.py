"""Aide et à propos : coordonnées de l'éditeur, version, licence de l'école, acceptation des conditions."""
from flask import Blueprint, current_app, g, jsonify, request

import conditions
from auth import require_auth
from database import db
from licence import licence_active, statut_licence

bp = Blueprint('aide_routes', __name__, url_prefix='/api/aide')


@bp.route('/info', methods=['GET'])
def info():
    """Public : disponible aussi depuis l'écran de connexion ou de licence bloquée."""
    return jsonify({'editeur': conditions.contact_editeur(), 'version': current_app.config.get('APP_VERSION'),
                    'version_conditions': conditions.VERSION_CONDITIONS})


@bp.route('/licence', methods=['GET'])
@require_auth
def licence():
    """État de la licence : installation autonome (clé à saisir) ou école de la plateforme web."""
    if licence_active():
        s = statut_licence(db)
        return jsonify({'type': 'locale', 'mode': s['mode'], 'jours_restants': s.get('jours_restants'),
                        'expiration': s.get('expiration'), 'bloque': s['bloque']})
    e = db.execute("SELECT nom, code, statut_licence, date_expiration_licence FROM ecoles WHERE id=?",
                   (g.user['ecole_id'],)).fetchone()
    if not e:
        return jsonify({'type': 'web', 'statut': 'active'})
    from datetime import date
    jours = None
    if e['date_expiration_licence']:
        try:
            jours = (date.fromisoformat(str(e['date_expiration_licence'])[:10]) - date.today()).days
        except ValueError:
            pass
    return jsonify({'type': 'web', 'ecole': e['nom'], 'code': e['code'], 'statut': e['statut_licence'],
                    'expiration': e['date_expiration_licence'], 'jours_restants': jours})


@bp.route('/conditions', methods=['GET'])
@require_auth
def statut_conditions():
    deja = db.execute("SELECT 1 FROM acceptations_conditions WHERE user_id=? AND version=?",
                      (g.user['id'], conditions.VERSION_CONDITIONS)).fetchone()
    return jsonify({'version': conditions.VERSION_CONDITIONS, 'acceptees': bool(deja)})


@bp.route('/conditions', methods=['POST'])
@require_auth
def accepter_conditions():
    erreur = conditions.acceptation_manquante(request.get_json(silent=True))
    if erreur:
        return erreur
    db.execute("INSERT OR IGNORE INTO acceptations_conditions (ecole_id,user_id,version) VALUES (?,?,?)",
               (g.user['ecole_id'], g.user['id'], conditions.VERSION_CONDITIONS))
    db.commit()
    conditions.journaliser(g.user['ecole_id'], g.user.get('name'), 'connexion', g.user['id'])
    return jsonify({'ok': True})
