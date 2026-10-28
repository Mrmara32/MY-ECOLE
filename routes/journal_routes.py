import json
from flask import Blueprint, request, jsonify, g

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

    sql = "SELECT * FROM journal_audit WHERE ecole_id=?"
    params = [g.user['ecole_id']]
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
    entites = [r['entite'] for r in db.execute("SELECT DISTINCT entite FROM journal_audit WHERE ecole_id=? ORDER BY entite", (g.user['ecole_id'],)).fetchall()]
    actions = [r['action'] for r in db.execute("SELECT DISTINCT action FROM journal_audit WHERE ecole_id=? ORDER BY action", (g.user['ecole_id'],)).fetchall()]
    return jsonify({'entites': entites, 'actions': actions})


@bp.route('/integrite', methods=['GET'])
@require_auth
@require_role('admin')
def verifier_integrite():
    """Recalcule la chaîne d'empreintes du journal : détecte toute ligne modifiée, supprimée ou insérée après coup."""
    from database import _empreinte_journal
    ecole_id = g.user['ecole_id']
    rows = db.execute("SELECT * FROM journal_audit WHERE ecole_id=? AND rang IS NOT NULL ORDER BY rang", (ecole_id,)).fetchall()
    precedente, attendu, anomalies = None, None, []
    for r in rows:
        if precedente is None:
            precedente = ''   # point de départ : la plus ancienne ligne conservée
        if attendu is not None and r['rang'] != attendu:
            anomalies.append({'rang': attendu, 'probleme': 'entrée manquante (supprimée ?)'})
        calcul = _empreinte_journal(precedente if attendu is not None else '', r['ecole_id'], r['rang'], r['user_id'], r['user_nom'],
                                    r['action'], r['entite'], r['entite_id'], r['details'], r['ip'], r['created_at'])
        if attendu is not None and calcul != r['empreinte']:
            anomalies.append({'rang': r['rang'], 'id': r['id'], 'probleme': 'contenu modifié'})
        precedente, attendu = r['empreinte'], r['rang'] + 1
    return jsonify({'entrees_verifiees': len(rows), 'integre': not anomalies, 'anomalies': anomalies[:50]})
