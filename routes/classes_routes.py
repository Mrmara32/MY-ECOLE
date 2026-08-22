from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role

bp = Blueprint('classes_routes', __name__, url_prefix='/api/classes')


@bp.route('', methods=['GET'])
@require_auth
def list_classes():
    actives_only = request.args.get('actives') != '0'
    sql = "SELECT * FROM classes WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if actives_only:
        sql += " AND active=1"
    sql += " ORDER BY ordre, nom"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def create_classe():
    body = request.get_json(silent=True) or {}
    nom, cycle = body.get('nom'), body.get('cycle')
    if not nom or not cycle:
        return jsonify({'error': 'Nom et cycle requis'}), 400
    if cycle not in ('maternelle', 'primaire', 'college', 'lycee'):
        return jsonify({'error': 'Cycle invalide'}), 400
    if db.execute("SELECT id FROM classes WHERE ecole_id=? AND nom=?", (g.user['ecole_id'], nom)).fetchone():
        return jsonify({'error': 'Cette classe existe déjà'}), 409
    cid = gen_id('cls')
    maxordre = db.execute("SELECT COALESCE(MAX(ordre),0) as m FROM classes WHERE ecole_id=?", (g.user['ecole_id'],)).fetchone()['m']
    db.execute("INSERT INTO classes (id,ecole_id,nom,cycle,ordre) VALUES (?,?,?,?,?)",
               (cid, g.user['ecole_id'], nom, cycle, body.get('ordre', maxordre + 1)))
    db.commit()
    log_action(g.user, 'creation', 'classe', cid, {'nom': nom, 'cycle': cycle})
    row = db.execute("SELECT * FROM classes WHERE id=?", (cid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/<c_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def update_classe(c_id):
    body = request.get_json(silent=True) or {}
    existing = db.execute("SELECT * FROM classes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404

    nouveau_nom = body.get('nom')
    if nouveau_nom and nouveau_nom != existing['nom']:
        # Si la classe est renommée, on met aussi à jour les élèves qui y sont rattachés (même école)
        db.execute("UPDATE eleves SET classe=? WHERE classe=? AND ecole_id=?", (nouveau_nom, existing['nom'], g.user['ecole_id']))

    db.execute(
        "UPDATE classes SET nom=COALESCE(?,nom), cycle=COALESCE(?,cycle), ordre=COALESCE(?,ordre), "
        "active=COALESCE(?,active) WHERE id=? AND ecole_id=?",
        (nouveau_nom, body.get('cycle'), body.get('ordre'),
         (1 if body.get('active') else 0) if 'active' in body else None, c_id, g.user['ecole_id']),
    )
    db.commit()
    log_action(g.user, 'modification', 'classe', c_id, {'motif': body.get('motif'), 'avant': dict(existing), 'apres': body})
    row = db.execute("SELECT * FROM classes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_classe(c_id):
    existing = db.execute("SELECT * FROM classes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404
    nb_eleves = db.execute("SELECT COUNT(*) as c FROM eleves WHERE classe=? AND ecole_id=? AND statut='actif'", (existing['nom'], g.user['ecole_id'])).fetchone()['c']
    if nb_eleves > 0:
        return jsonify({'error': f"Impossible : {nb_eleves} élève(s) actif(s) sont encore dans cette classe. Désactivez-la plutôt, ou déplacez les élèves d'abord."}), 409
    db.execute("DELETE FROM classes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'classe', c_id, {'nom': existing['nom']})
    return jsonify({'success': True})
