import json
from flask import Blueprint, request, jsonify

from database import db, rows_to_list
from auth import require_auth, require_role

bp = Blueprint('journal_routes', __name__, url_prefix='/api/journal')


@bp.route('', methods=['GET'])
@require_auth
@require_role('admin')
def list_journal():
    """Journal d'audit complet — réservé à l'administrateur (fondateur). Point 6 du cahier des charges:
    permet de reconstituer l'historique de toutes les actions sensibles effectuées dans l'application."""
    entite = request.args.get('entite')
    action = request.args.get('action')
    user_id = request.args.get('user_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    q = request.args.get('q')
    limit = min(int(request.args.get('limit', 200)), 1000)

    sql = "SELECT * FROM journal_audit WHERE 1=1"
    params = []
    if entite: sql += " AND entite=?"; params.append(entite)
    if action: sql += " AND action=?"; params.append(action)
    if user_id: sql += " AND user_id=?"; params.append(user_id)
    if date_debut: sql += " AND date(created_at)>=?"; params.append(date_debut)
    if date_fin: sql += " AND date(created_at)<=?"; params.append(date_fin)
    if q: sql += " AND (user_nom LIKE ? OR details LIKE ? OR entite_id LIKE ?)"; params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = rows_to_list(db.execute(sql, params).fetchall())
    # Décoder les détails JSON pour un affichage plus lisible côté client
    for r in rows:
        if r.get('details'):
            try:
                r['details'] = json.loads(r['details'])
            except Exception:
                pass
    return jsonify(rows)


@bp.route('/entites', methods=['GET'])
@require_auth
@require_role('admin')
def entites_journal():
    """Liste les types d'entités et d'actions présents dans le journal, pour peupler les filtres."""
    entites = [r['entite'] for r in db.execute("SELECT DISTINCT entite FROM journal_audit ORDER BY entite").fetchall()]
    actions = [r['action'] for r in db.execute("SELECT DISTINCT action FROM journal_audit ORDER BY action").fetchall()]
    return jsonify({'entites': entites, 'actions': actions})
