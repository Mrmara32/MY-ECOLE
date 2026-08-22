from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, ecole_id_depuis_code
from auth import require_auth, require_role

bp = Blueprint('eleve_du_mois_routes', __name__, url_prefix='/api/eleve-du-mois')


@bp.route('', methods=['GET'])
@require_auth
def list_eleve_du_mois():
    rows = db.execute(
        """SELECT edm.*, e.nom, e.prenom, e.classe, e.matricule, e.photo_url, u.full_name as designe_par_nom
           FROM eleve_du_mois edm JOIN eleves e ON e.id=edm.eleve_id
           LEFT JOIN users u ON u.id=edm.designe_par
           WHERE edm.ecole_id=? ORDER BY edm.mois DESC""", (g.user['ecole_id'],)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/actuel', methods=['GET'])
def actuel():
    """Le plus récent élève du mois — accessible sans authentification pour affichage public.
    Le code établissement (?ecole=CODE) identifie l'école visitée sur le site vitrine."""
    import datetime
    ecole_id = ecole_id_depuis_code(request.args.get('ecole'))
    mois = datetime.datetime.now().strftime('%Y-%m')
    row = db.execute(
        """SELECT edm.*, e.nom, e.prenom, e.classe, e.matricule, e.photo_url
           FROM eleve_du_mois edm JOIN eleves e ON e.id=edm.eleve_id
           WHERE edm.mois=? AND edm.ecole_id=?""", (mois, ecole_id)
    ).fetchone()
    if not row:
        row = db.execute(
            """SELECT edm.*, e.nom, e.prenom, e.classe, e.matricule, e.photo_url
               FROM eleve_du_mois edm JOIN eleves e ON e.id=edm.eleve_id
               WHERE edm.ecole_id=?
               ORDER BY edm.mois DESC LIMIT 1""", (ecole_id,)
        ).fetchone()
    return jsonify(row_to_dict(row) if row else None)


@bp.route('', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def designer_eleve_du_mois():
    body = request.get_json(silent=True) or {}
    eleve_id, mois = body.get('eleve_id'), body.get('mois')
    if not eleve_id or not mois:
        return jsonify({'error': 'Élève et mois requis'}), 400
    if not db.execute("SELECT id FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Élève introuvable'}), 404

    existing = db.execute("SELECT id FROM eleve_du_mois WHERE mois=? AND ecole_id=?", (mois, g.user['ecole_id'])).fetchone()
    if existing:
        db.execute("UPDATE eleve_du_mois SET eleve_id=?, motif=?, designe_par=? WHERE mois=? AND ecole_id=?",
                   (eleve_id, body.get('motif'), g.user['id'], mois, g.user['ecole_id']))
        eid = existing['id']
    else:
        eid = gen_id('edm')
        db.execute("INSERT INTO eleve_du_mois (id,ecole_id,eleve_id,mois,motif,designe_par) VALUES (?,?,?,?,?,?)",
                   (eid, g.user['ecole_id'], eleve_id, mois, body.get('motif'), g.user['id']))
    db.commit()
    log_action(g.user, 'designation', 'eleve_du_mois', eid, {'eleve_id': eleve_id, 'mois': mois, 'motif': body.get('motif')})
    row = db.execute(
        """SELECT edm.*, e.nom, e.prenom, e.classe, e.matricule, e.photo_url
           FROM eleve_du_mois edm JOIN eleves e ON e.id=edm.eleve_id WHERE edm.id=?""", (eid,)
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/<edm_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_eleve_du_mois(edm_id):
    db.execute("DELETE FROM eleve_du_mois WHERE id=? AND ecole_id=?", (edm_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})
