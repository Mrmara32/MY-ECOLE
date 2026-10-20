"""
Vie scolaire : discipline (observations, avertissements, blâmes, retenues, exclusions temporaires)
et félicitations, avec historique par élève, visible des parents.
"""
from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, get_classes_enseignant
from auth import require_auth, require_role
from permissions import require_permission

bp = Blueprint('discipline_routes', __name__, url_prefix='/api/discipline')

TYPES = ('felicitations', 'observation', 'avertissement', 'retenue', 'blame', 'exclusion_temporaire')
# Sanctions lourdes : réservées à la direction (un enseignant signale, la direction sanctionne).
TYPES_DIRECTION = ('blame', 'exclusion_temporaire')
ROLES_SAISIE = ('admin', 'directeur', 'secretaire', 'enseignant')
ROLES_DIRECTION = ('admin', 'directeur')


def _eleve(eleve_id):
    return db.execute("SELECT id, classe FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()


def _peut_gerer_classe(classe):
    if g.user['role'] == 'enseignant':
        return classe in get_classes_enseignant(g.user['id'])
    return True


def _valider(body, partiel=False):
    """-> (valeurs, erreur)."""
    v = {}
    if not partiel or 'type' in body:
        if body.get('type') not in TYPES:
            return None, f"Type invalide (attendu : {', '.join(TYPES)})"
        v['type'] = body['type']
    if not partiel or 'motif' in body:
        motif = (body.get('motif') or '').strip()
        if not motif:
            return None, 'Le motif est obligatoire'
        v['motif'] = motif[:300]
    if 'date_fait' in body or not partiel:
        d = body.get('date_fait') or ''
        if len(d) != 10 or d[4] != '-' or d[7] != '-':
            return None, 'Date invalide (AAAA-MM-JJ)'
        v['date_fait'] = d
    for k in ('description', 'sanction'):
        if k in body:
            v[k] = (body.get(k) or '').strip()[:1000]
    if 'nb_jours' in body:
        try:
            nb = int(body.get('nb_jours') or 0)
        except (TypeError, ValueError):
            return None, "Nombre de jours invalide"
        if not 0 <= nb <= 60:
            return None, "Le nombre de jours d'exclusion doit être compris entre 0 et 60"
        v['nb_jours'] = nb
    if 'visible_parents' in body:
        v['visible_parents'] = 1 if body.get('visible_parents') else 0
    return v, None


@bp.route('', methods=['GET'])
@require_auth
@require_permission('discipline', 'peut_voir')
def list_discipline():
    sql = ("SELECT d.*, e.nom, e.prenom, e.classe, e.matricule, u.full_name AS saisi_par "
           "FROM discipline d JOIN eleves e ON e.id=d.eleve_id LEFT JOIN users u ON u.id=d.enregistre_par "
           "WHERE d.ecole_id=?")
    params = [g.user['ecole_id']]
    if g.user['role'] == 'enseignant':
        mes = get_classes_enseignant(g.user['id'])
        if not mes:
            return jsonify([])
        sql += f" AND e.classe IN ({','.join('?' * len(mes))})"; params += mes
    elif g.user['role'] == 'parent':
        sql += " AND d.visible_parents=1 AND d.eleve_id IN (SELECT eleve_id FROM parents_eleves WHERE user_id=?)"
        params.append(g.user['id'])
    elif g.user['role'] not in ('admin', 'directeur', 'secretaire'):
        return jsonify({'error': 'Accès refusé'}), 403
    for arg, col in (('eleve_id', 'd.eleve_id'), ('classe', 'e.classe'), ('type', 'd.type')):
        if request.args.get(arg):
            sql += f" AND {col}=?"; params.append(request.args[arg])
    if request.args.get('du'):
        sql += " AND d.date_fait>=?"; params.append(request.args['du'])
    if request.args.get('au'):
        sql += " AND d.date_fait<=?"; params.append(request.args['au'])
    return jsonify(rows_to_list(db.execute(sql + " ORDER BY d.date_fait DESC, d.created_at DESC LIMIT 1000", params).fetchall()))


@bp.route('', methods=['POST'])
@require_auth
@require_role(*ROLES_SAISIE)
@require_permission('discipline', 'peut_creer')
def create_discipline():
    body = request.get_json(silent=True) or {}
    e = _eleve(body.get('eleve_id'))
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    if not _peut_gerer_classe(e['classe']):
        return jsonify({'error': "Cet élève n'est pas dans une de vos classes"}), 403
    v, erreur = _valider(body)
    if erreur:
        return jsonify({'error': erreur}), 400
    if v['type'] in TYPES_DIRECTION and g.user['role'] not in ROLES_DIRECTION:
        return jsonify({'error': "Un blâme ou une exclusion est prononcé par la direction : signalez les faits par une observation."}), 403
    if v['type'] == 'exclusion_temporaire' and not v.get('nb_jours'):
        return jsonify({'error': "Indiquez la durée de l'exclusion (nombre de jours)"}), 400
    v.setdefault('visible_parents', 1)
    did = gen_id('dis')
    cols = ['id', 'ecole_id', 'eleve_id', 'enregistre_par'] + list(v)
    db.execute(f"INSERT INTO discipline ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
               [did, g.user['ecole_id'], e['id'], g.user['id']] + list(v.values()))
    db.commit()
    log_action(g.user, 'creation', 'discipline', did, {'eleve_id': e['id'], 'type': v['type'], 'motif': v['motif']})
    return jsonify(row_to_dict(db.execute("SELECT * FROM discipline WHERE id=?", (did,)).fetchone())), 201


@bp.route('/<d_id>', methods=['PUT'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('discipline', 'peut_modifier')
def update_discipline(d_id):
    actuel = db.execute("SELECT * FROM discipline WHERE id=? AND ecole_id=?", (d_id, g.user['ecole_id'])).fetchone()
    if not actuel:
        return jsonify({'error': 'Introuvable'}), 404
    body = request.get_json(silent=True) or {}
    v, erreur = _valider(body, partiel=True)
    if erreur:
        return jsonify({'error': erreur}), 400
    if not v:
        return jsonify({'error': 'Rien à modifier'}), 400
    sets = ','.join(f"{k}=?" for k in v)
    db.execute(f"UPDATE discipline SET {sets} WHERE id=? AND ecole_id=?", list(v.values()) + [d_id, g.user['ecole_id']])
    db.commit()
    log_action(g.user, 'modification', 'discipline', d_id, v)
    return jsonify(row_to_dict(db.execute("SELECT * FROM discipline WHERE id=?", (d_id,)).fetchone()))


@bp.route('/<d_id>', methods=['DELETE'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('discipline', 'peut_supprimer')
def delete_discipline(d_id):
    actuel = db.execute("SELECT * FROM discipline WHERE id=? AND ecole_id=?", (d_id, g.user['ecole_id'])).fetchone()
    if not actuel:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM discipline WHERE id=? AND ecole_id=?", (d_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'discipline', d_id, {'eleve_id': actuel['eleve_id'], 'type': actuel['type'], 'motif': actuel['motif']})
    return jsonify({'success': True})


@bp.route('/resume/<eleve_id>', methods=['GET'])
@require_auth
@require_permission('discipline', 'peut_voir')
def resume_eleve(eleve_id):
    """Nombre de faits par type pour un élève (fiche élève, conseil de classe)."""
    e = _eleve(eleve_id)
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    if g.user['role'] == 'parent':
        if not db.execute("SELECT 1 FROM parents_eleves WHERE user_id=? AND eleve_id=?", (g.user['id'], eleve_id)).fetchone():
            return jsonify({'error': 'Accès refusé à cet élève'}), 403
    elif g.user['role'] not in ('admin', 'directeur', 'secretaire') and not _peut_gerer_classe(e['classe']):
        return jsonify({'error': 'Accès refusé à cet élève'}), 403
    filtre = " AND visible_parents=1" if g.user['role'] == 'parent' else ""
    rows = db.execute("SELECT type, COUNT(*) AS n, COALESCE(SUM(nb_jours),0) AS jours FROM discipline "
                      "WHERE eleve_id=? AND ecole_id=?" + filtre + " GROUP BY type", (eleve_id, g.user['ecole_id'])).fetchall()
    return jsonify({r['type']: {'nombre': r['n'], 'jours': r['jours']} for r in rows})
