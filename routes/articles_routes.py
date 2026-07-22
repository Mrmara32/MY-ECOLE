import os
import time
import random
from flask import Blueprint, request, jsonify, g, current_app

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role

bp = Blueprint('articles_routes', __name__, url_prefix='/api/articles')

ALLOWED_PHOTO = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
ALLOWED_VIDEO = {'.mp4', '.webm', '.mov', '.avi'}
PUBLISH_ROLES = ('admin', 'directeur', 'secretaire', 'charge_communication')


def _with_media(article):
    media = db.execute(
        "SELECT * FROM articles_media WHERE article_id=? ORDER BY ordre, created_at", (article['id'],)
    ).fetchall()
    article['media'] = rows_to_list(media)
    return article


@bp.route('', methods=['GET'])
def list_articles():
    """Liste publique (pas d'auth requise) — pour affichage type 'actualités de l'école'."""
    type_ = request.args.get('type')
    sql = "SELECT a.*, u.full_name as auteur_nom FROM articles a LEFT JOIN users u ON u.id=a.auteur_id WHERE a.publie=1"
    params = []
    if type_: sql += " AND a.type=?"; params.append(type_)
    sql += " ORDER BY a.date_publication DESC LIMIT 100"
    rows = rows_to_list(db.execute(sql, params).fetchall())
    for r in rows:
        _with_media(r)
    return jsonify(rows)


@bp.route('/admin', methods=['GET'])
@require_auth
@require_role(*PUBLISH_ROLES)
def list_articles_admin():
    """Liste complète (y compris non publiés) pour la gestion interne."""
    rows = rows_to_list(db.execute(
        "SELECT a.*, u.full_name as auteur_nom FROM articles a LEFT JOIN users u ON u.id=a.auteur_id "
        "ORDER BY a.date_publication DESC"
    ).fetchall())
    for r in rows:
        _with_media(r)
    return jsonify(rows)


@bp.route('/<a_id>', methods=['GET'])
def get_article(a_id):
    row = db.execute("SELECT a.*, u.full_name as auteur_nom FROM articles a LEFT JOIN users u ON u.id=a.auteur_id WHERE a.id=?", (a_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(_with_media(row_to_dict(row)))


@bp.route('', methods=['POST'])
@require_auth
@require_role(*PUBLISH_ROLES)
def create_article():
    body = request.get_json(silent=True) or {}
    titre = body.get('titre')
    if not titre:
        return jsonify({'error': 'Titre requis'}), 400
    aid = gen_id('art')
    db.execute(
        "INSERT INTO articles (id,titre,contenu,type,auteur_id,publie) VALUES (?,?,?,?,?,?)",
        (aid, titre, body.get('contenu'), body.get('type', 'article'), g.user['id'], 1 if body.get('publie', True) else 0),
    )
    db.commit()
    log_action(g.user, 'creation', 'article', aid, {'titre': titre})
    row = db.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    return jsonify(_with_media(row_to_dict(row))), 201


@bp.route('/<a_id>', methods=['PUT'])
@require_auth
@require_role(*PUBLISH_ROLES)
def update_article(a_id):
    body = request.get_json(silent=True) or {}
    a = db.execute("SELECT * FROM articles WHERE id=?", (a_id,)).fetchone()
    if not a:
        return jsonify({'error': 'Introuvable'}), 404
    if a['auteur_id'] != g.user['id'] and g.user['role'] not in ('admin', 'directeur'):
        return jsonify({'error': 'Accès refusé'}), 403
    db.execute(
        "UPDATE articles SET titre=COALESCE(?,titre), contenu=COALESCE(?,contenu), type=COALESCE(?,type), "
        "publie=COALESCE(?,publie) WHERE id=?",
        (body.get('titre'), body.get('contenu'), body.get('type'),
         (1 if body.get('publie') else 0) if 'publie' in body else None, a_id),
    )
    db.commit()
    log_action(g.user, 'modification', 'article', a_id, body)
    row = db.execute("SELECT * FROM articles WHERE id=?", (a_id,)).fetchone()
    return jsonify(_with_media(row_to_dict(row)))


@bp.route('/<a_id>', methods=['DELETE'])
@require_auth
@require_role(*PUBLISH_ROLES)
def delete_article(a_id):
    a = db.execute("SELECT * FROM articles WHERE id=?", (a_id,)).fetchone()
    if not a:
        return jsonify({'error': 'Introuvable'}), 404
    if a['auteur_id'] != g.user['id'] and g.user['role'] not in ('admin', 'directeur'):
        return jsonify({'error': 'Accès refusé'}), 403
    db.execute("DELETE FROM articles WHERE id=?", (a_id,))
    db.commit()
    log_action(g.user, 'suppression', 'article', a_id, {'titre': a['titre']})
    return jsonify({'success': True})


@bp.route('/upload-image-contenu', methods=['POST'])
@require_auth
@require_role(*PUBLISH_ROLES)
def upload_image_contenu():
    """Upload générique d'une image à insérer au milieu du texte d'un article,
    utilisable même avant que l'article ne soit enregistré (pas d'id requis)."""
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_PHOTO:
        return jsonify({'error': 'Format non supporté (jpg, png, gif, webp)'}), 400

    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))
    return jsonify({'url': '/uploads/' + fname})


@bp.route('/<a_id>/media', methods=['POST'])
@require_auth
@require_role(*PUBLISH_ROLES)
def upload_media(a_id):
    if not db.execute("SELECT id FROM articles WHERE id=?", (a_id,)).fetchone():
        return jsonify({'error': 'Article introuvable'}), 404
    file = request.files.get('fichier')
    if not file or file.filename == '':
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext in ALLOWED_PHOTO:
        media_type = 'photo'
    elif ext in ALLOWED_VIDEO:
        media_type = 'video'
    else:
        return jsonify({'error': 'Format non supporté (photos: jpg/png/gif/webp, vidéos: mp4/webm/mov/avi)'}), 400

    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))
    url = '/uploads/' + fname

    mid = gen_id('med')
    db.execute(
        "INSERT INTO articles_media (id,article_id,type,url,legende) VALUES (?,?,?,?,?)",
        (mid, a_id, media_type, url, request.form.get('legende')),
    )
    db.commit()
    row = db.execute("SELECT * FROM articles_media WHERE id=?", (mid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/media/<m_id>', methods=['DELETE'])
@require_auth
@require_role(*PUBLISH_ROLES)
def delete_media(m_id):
    db.execute("DELETE FROM articles_media WHERE id=?", (m_id,))
    db.commit()
    return jsonify({'success': True})
