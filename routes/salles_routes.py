from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role
from offline_sync import idempotent
from permissions import require_permission

bp = Blueprint('salles_routes', __name__, url_prefix='/api/salles')


@bp.route('', methods=['GET'])
@require_auth
@require_permission('salles', 'peut_voir')
def list_salles():
    actives_only = request.args.get('actives') != '0'
    sql = "SELECT * FROM salles WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if actives_only:
        sql += " AND active=1"
    sql += " ORDER BY nom"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
@idempotent('create_salle')
@require_permission('salles', 'peut_creer')
def create_salle():
    body = request.get_json(silent=True) or {}
    nom = body.get('nom')
    if not nom:
        return jsonify({'error': 'Nom requis'}), 400
    if db.execute("SELECT id FROM salles WHERE ecole_id=? AND nom=?", (g.user['ecole_id'], nom)).fetchone():
        return jsonify({'error': 'Cette salle existe déjà'}), 409
    sid = gen_id('salle')
    db.execute("INSERT INTO salles (id,ecole_id,nom,capacite,batiment) VALUES (?,?,?,?,?)",
               (sid, g.user['ecole_id'], nom, body.get('capacite'), body.get('batiment')))
    db.commit()
    log_action(g.user, 'creation', 'salle', sid, {'nom': nom})
    row = db.execute("SELECT * FROM salles WHERE id=?", (sid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/<s_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
@require_permission('salles', 'peut_modifier')
def update_salle(s_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM salles WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        "UPDATE salles SET nom=COALESCE(?,nom), capacite=COALESCE(?,capacite), "
        "batiment=COALESCE(?,batiment), active=COALESCE(?,active) WHERE id=? AND ecole_id=?",
        (body.get('nom'), body.get('capacite'), body.get('batiment'),
         (1 if body.get('active') else 0) if 'active' in body else None, s_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM salles WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<s_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
@require_permission('salles', 'peut_supprimer')
def delete_salle(s_id):
    if not db.execute("SELECT id FROM salles WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM salles WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'salle', s_id, {})
    return jsonify({'success': True})
