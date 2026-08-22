from flask import Blueprint, jsonify, g

from database import db, rows_to_list
from auth import require_auth, require_role

bp = Blueprint('parent_routes', __name__, url_prefix='/api/parent')


@bp.route('/mes-enfants', methods=['GET'])
@require_auth
@require_role('parent')
def mes_enfants():
    """Liste les élèves liés au compte parent actuellement connecté (auto-service,
    contrairement à /api/users/<id>/enfants qui est réservé à l'administration)."""
    rows = db.execute(
        """SELECT e.id, e.matricule, e.nom, e.prenom, e.classe, e.photo_url
           FROM parents_eleves pe JOIN eleves e ON e.id = pe.eleve_id
           WHERE pe.user_id=? ORDER BY e.nom""", (g.user['id'],)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/messages', methods=['GET'])
@require_auth
@require_role('parent')
def mes_messages():
    """Messages destinés au parent connecté : ceux adressés à l'un de ses enfants
    précisément, à la classe de l'un de ses enfants, ou diffusés à tous les parents."""
    mes_enfants = db.execute(
        "SELECT eleve_id FROM parents_eleves WHERE user_id=?", (g.user['id'],)
    ).fetchall()
    if not mes_enfants:
        return jsonify([])
    eleve_ids = [r['eleve_id'] for r in mes_enfants]
    classes = [r['classe'] for r in db.execute(
        f"SELECT DISTINCT classe FROM eleves WHERE id IN ({','.join(['?']*len(eleve_ids))}) AND classe IS NOT NULL",
        eleve_ids
    ).fetchall()]

    conditions = ["m.destinataire_type IN ('tous','tous_parents')"]
    params = []
    if eleve_ids:
        conditions.append(f"(m.destinataire_type='eleve' AND m.destinataire_id IN ({','.join(['?']*len(eleve_ids))}))")
        params += eleve_ids
    if classes:
        conditions.append(f"(m.destinataire_type='classe' AND m.destinataire_id IN ({','.join(['?']*len(classes))}))")
        params += classes

    sql = f"""SELECT m.*, u.full_name as expediteur_nom FROM messages m
              LEFT JOIN users u ON u.id=m.expediteur_id
              WHERE m.ecole_id=? AND ({' OR '.join(conditions)}) ORDER BY m.date_envoi DESC LIMIT 100"""
    rows = db.execute(sql, [g.user['ecole_id']] + params).fetchall()
    return jsonify(rows_to_list(rows))
