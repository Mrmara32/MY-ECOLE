import os
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from database import db, get_settings, log_action
from auth import require_auth, require_role

bp = Blueprint('settings_routes', __name__, url_prefix='/api/settings')

ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


@bp.route('', methods=['GET'])
def get_settings_route():
    return jsonify(get_settings())


@bp.route('/seuils-approbation', methods=['PUT'])
@require_auth
@require_role('admin')
def update_seuils():
    """Seuls l'administrateur (fondateur) peut modifier les seuils d'approbation comptable (points 4/5)."""
    from flask import g
    body = request.get_json(silent=True) or {}
    seuil_directeur = body.get('seuil_approbation_directeur')
    seuil_admin = body.get('seuil_approbation_admin')
    if seuil_directeur is not None:
        db.execute("INSERT OR REPLACE INTO settings (cle,valeur) VALUES (?,?)", ('seuil_approbation_directeur', str(seuil_directeur)))
    if seuil_admin is not None:
        db.execute("INSERT OR REPLACE INTO settings (cle,valeur) VALUES (?,?)", ('seuil_approbation_admin', str(seuil_admin)))
    db.commit()
    log_action(g.user, 'modification', 'parametres_approbation', None,
               {'seuil_approbation_directeur': seuil_directeur, 'seuil_approbation_admin': seuil_admin})
    return jsonify(get_settings())


@bp.route('', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def update_settings():
    body = request.get_json(silent=True) or {}
    allowed = ['ecole_nom', 'ecole_adresse', 'ecole_telephone', 'ecole_email', 'annee_scolaire',
               'reseau_facebook', 'reseau_instagram', 'reseau_youtube', 'reseau_tiktok', 'reseau_whatsapp',
               'creneaux_horaires']
    for k in allowed:
        if k in body:
            db.execute("INSERT OR REPLACE INTO settings (cle, valeur) VALUES (?,?)", (k, body[k]))
    db.commit()
    return jsonify(get_settings())


@bp.route('/logo', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def upload_logo():
    file = request.files.get('logo')
    if not file or file.filename == '':
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Format non supporté'}), 400

    import time, random
    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))

    logo_url = '/uploads/' + fname
    db.execute("INSERT OR REPLACE INTO settings (cle, valeur) VALUES (?,?)", ('ecole_logo', logo_url))
    db.commit()
    return jsonify({'logo_url': logo_url})


@bp.route('/cachet', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def upload_cachet():
    """Cachet officiel de l'établissement — utilisé sur les cartes, badges et documents imprimés."""
    file = request.files.get('cachet')
    if not file or file.filename == '':
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Format non supporté'}), 400

    import time, random
    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))

    url = '/uploads/' + fname
    db.execute("INSERT OR REPLACE INTO settings (cle, valeur) VALUES (?,?)", ('ecole_cachet', url))
    db.commit()
    return jsonify({'cachet_url': url})


@bp.route('/signature-directeur', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def upload_signature_directeur():
    """Signature du directeur — utilisée sur les cartes, badges et documents imprimés."""
    file = request.files.get('signature')
    if not file or file.filename == '':
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Format non supporté'}), 400

    import time, random
    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))

    url = '/uploads/' + fname
    db.execute("INSERT OR REPLACE INTO settings (cle, valeur) VALUES (?,?)", ('signature_directeur', url))
    db.commit()
    return jsonify({'signature_url': url})
