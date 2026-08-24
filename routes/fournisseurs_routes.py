from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role

bp = Blueprint('fournisseurs_routes', __name__, url_prefix='/api/fournisseurs')

FIN_ROLES = ('admin', 'directeur', 'comptable')


@bp.route('', methods=['GET'])
@require_auth
def list_fournisseurs():
    actifs_only = request.args.get('actifs') == '1'
    q = request.args.get('q', '').strip()
    sql = "SELECT * FROM fournisseurs WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if actifs_only:
        sql += " AND actif=1"
    if q:
        sql += " AND nom LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY nom"
    rows = db.execute(sql, params).fetchall()
    result = []
    for f in rows:
        d = dict(f)
        totaux = db.execute(
            "SELECT COALESCE(SUM(montant),0) as total, COUNT(*) as nb FROM transactions "
            "WHERE fournisseur_id=? AND ecole_id=? AND statut_validation IN ('auto','valide')",
            (f['id'], g.user['ecole_id']),
        ).fetchone()
        d['total_paye'] = totaux['total']
        d['nb_transactions'] = totaux['nb']
        result.append(d)
    return jsonify(result)


@bp.route('/<f_id>', methods=['GET'])
@require_auth
def get_fournisseur(f_id):
    row = db.execute("SELECT * FROM fournisseurs WHERE id=? AND ecole_id=?", (f_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    d = row_to_dict(row)
    historique = db.execute(
        "SELECT * FROM transactions WHERE fournisseur_id=? AND ecole_id=? ORDER BY date_op DESC",
        (f_id, g.user['ecole_id']),
    ).fetchall()
    d['historique'] = rows_to_list(historique)
    d['total_paye'] = sum(t['montant'] for t in historique if t['statut_validation'] in ('auto', 'valide'))
    return jsonify(d)


@bp.route('', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def create_fournisseur():
    body = request.get_json(silent=True) or {}
    nom = (body.get('nom') or '').strip()
    if not nom:
        return jsonify({'error': 'Le nom du fournisseur est requis'}), 400
    if db.execute("SELECT 1 FROM fournisseurs WHERE ecole_id=? AND nom=?", (g.user['ecole_id'], nom)).fetchone():
        return jsonify({'error': 'Ce fournisseur existe déjà'}), 409
    fid = gen_id('four')
    db.execute(
        "INSERT INTO fournisseurs (id,ecole_id,nom,categorie,telephone,email,adresse,notes) VALUES (?,?,?,?,?,?,?,?)",
        (fid, g.user['ecole_id'], nom, body.get('categorie'), body.get('telephone'),
         body.get('email'), body.get('adresse'), body.get('notes')),
    )
    db.commit()
    log_action(g.user, 'creation', 'fournisseur', fid, {'nom': nom})
    row = db.execute("SELECT * FROM fournisseurs WHERE id=?", (fid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/<f_id>', methods=['PUT'])
@require_auth
@require_role(*FIN_ROLES)
def update_fournisseur(f_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM fournisseurs WHERE id=? AND ecole_id=?", (f_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        """UPDATE fournisseurs SET nom=COALESCE(?,nom), categorie=COALESCE(?,categorie),
           telephone=COALESCE(?,telephone), email=COALESCE(?,email), adresse=COALESCE(?,adresse),
           notes=COALESCE(?,notes), actif=COALESCE(?,actif) WHERE id=? AND ecole_id=?""",
        (body.get('nom'), body.get('categorie'), body.get('telephone'), body.get('email'),
         body.get('adresse'), body.get('notes'),
         (1 if body.get('actif') else 0) if 'actif' in body else None, f_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM fournisseurs WHERE id=? AND ecole_id=?", (f_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/<f_id>', methods=['DELETE'])
@require_auth
@require_role(*FIN_ROLES)
def delete_fournisseur(f_id):
    if not db.execute("SELECT id FROM fournisseurs WHERE id=? AND ecole_id=?", (f_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    nb_transactions = db.execute(
        "SELECT COUNT(*) as c FROM transactions WHERE fournisseur_id=? AND ecole_id=?", (f_id, g.user['ecole_id'])
    ).fetchone()['c']
    if nb_transactions > 0:
        return jsonify({'error': f"Impossible : {nb_transactions} transaction(s) sont liées à ce fournisseur. Désactivez-le plutôt."}), 409
    db.execute("DELETE FROM fournisseurs WHERE id=? AND ecole_id=?", (f_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})
