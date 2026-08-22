from flask import Blueprint, request, jsonify

from database import db
from licence import statut_licence, verifier_cle_licence

bp = Blueprint('licence_routes', __name__, url_prefix='/api/licence')


@bp.route('/statut', methods=['GET'])
def get_statut_licence():
    """Route publique (sans connexion) : permet au frontend de savoir, même avant
    la connexion, si l'installation est en essai, licenciée, ou bloquée."""
    return jsonify(statut_licence(db))


@bp.route('/activer', methods=['POST'])
def activer_licence():
    """Enregistre une clé de licence. Route publique (sans connexion) car elle doit
    rester utilisable même lorsque la période d'essai est expirée et bloque l'accès
    au reste de l'application."""
    body = request.get_json(silent=True) or {}
    cle = (body.get('cle') or '').strip()
    if not cle:
        return jsonify({'error': 'Clé de licence requise'}), 400

    verif = verifier_cle_licence(cle)
    if not verif['valide']:
        return jsonify({'error': verif.get('erreur', 'Clé de licence invalide')}), 400

    db.execute("INSERT OR REPLACE INTO settings (ecole_id,cle,valeur) VALUES (1,'licence_cle',?)", (cle,))
    db.commit()
    return jsonify(statut_licence(db))
