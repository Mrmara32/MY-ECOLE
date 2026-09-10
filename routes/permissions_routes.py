from flask import Blueprint, request, jsonify, g

from database import db, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role
from permissions import MODULES_PERMISSIONS, ACTIONS, obtenir_permissions_utilisateur

bp = Blueprint('permissions_routes', __name__, url_prefix='/api/permissions')


@bp.route('/modules', methods=['GET'])
@require_auth
@require_role('admin')
def liste_modules():
    """Liste des modules pour lesquels des permissions personnalisées peuvent
    être définies — sert à construire la grille dans l'interface."""
    return jsonify([{'module': m, 'label': lbl} for m, lbl in MODULES_PERMISSIONS])


@bp.route('/utilisateur/<int:user_id>', methods=['GET'])
@require_auth
@require_role('admin')
def obtenir_permissions(user_id):
    utilisateur = db.execute(
        "SELECT id, full_name, role FROM users WHERE id=? AND ecole_id=?",
        (user_id, g.user['ecole_id']),
    ).fetchone()
    if not utilisateur:
        return jsonify({'error': 'Utilisateur introuvable'}), 404

    permissions_existantes = obtenir_permissions_utilisateur(user_id)
    # Pour chaque module connu, on renvoie soit la personnalisation existante,
    # soit null pour indiquer "aucune personnalisation — comportement par
    # défaut du rôle appliqué" (distinct d'un module explicitement tout
    # décoché, qui lui a des valeurs 0/0/0/0 enregistrées).
    matrice = {
        module: permissions_existantes.get(module)
        for module, _ in MODULES_PERMISSIONS
    }
    return jsonify({
        'utilisateur': row_to_dict(utilisateur),
        'permissions': matrice,
    })


@bp.route('/utilisateur/<int:user_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def definir_permissions(user_id):
    utilisateur = db.execute(
        "SELECT id, role FROM users WHERE id=? AND ecole_id=?",
        (user_id, g.user['ecole_id']),
    ).fetchone()
    if not utilisateur:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    if utilisateur['role'] == 'admin':
        return jsonify({'error': "Impossible de restreindre un compte administrateur"}), 400

    body = request.get_json(silent=True) or {}
    permissions = body.get('permissions') or {}
    modules_valides = {m for m, _ in MODULES_PERMISSIONS}

    for module, valeurs in permissions.items():
        if module not in modules_valides:
            continue
        if valeurs is None:
            # Retirer la personnalisation : le module retombe sur le
            # comportement par défaut du rôle de l'utilisateur.
            db.execute(
                "DELETE FROM permissions_utilisateur WHERE user_id=? AND module=?",
                (user_id, module),
            )
            continue
        flags = [1 if valeurs.get(a) else 0 for a in ACTIONS]
        db.execute(
            """INSERT INTO permissions_utilisateur
               (ecole_id, user_id, module, peut_voir, peut_creer, peut_modifier, peut_supprimer, modifie_par, modifie_le)
               VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, module) DO UPDATE SET
                 peut_voir=excluded.peut_voir, peut_creer=excluded.peut_creer,
                 peut_modifier=excluded.peut_modifier, peut_supprimer=excluded.peut_supprimer,
                 modifie_par=excluded.modifie_par, modifie_le=CURRENT_TIMESTAMP""",
            (g.user['ecole_id'], user_id, module, *flags, g.user['id']),
        )
    db.commit()
    log_action(g.user, 'modification', 'permissions', str(user_id), {'permissions': permissions})

    return jsonify({'permissions': obtenir_permissions_utilisateur(user_id)})
