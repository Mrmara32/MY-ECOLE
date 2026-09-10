"""
Permissions personnalisees par utilisateur.

Principe additif : ce systeme ne remplace jamais les regles de role existantes
(@require_role) -- il ne fait que les RESTREINDRE davantage, et seulement pour
un utilisateur precis sur lequel un administrateur a explicitement configure
une permission pour un module donne. Tant qu'aucune permission personnalisee
n'a ete definie pour (cet utilisateur, ce module), rien ne change : le
comportement habituel base sur le role s'applique normalement.

Un compte admin ou super-administrateur n'est jamais restreint par ce systeme.
"""
from functools import wraps
from flask import request, jsonify, g

from database import db

# Liste des modules pour lesquels un administrateur peut definir des
# permissions personnalisees. Seuls ces modules sont a la fois configurables
# depuis l'interface ET reellement verifies par le serveur (voir les routes
# concernees) -- un module absent de cette liste n'est pas encore couvert par
# ce systeme, pour ne jamais laisser croire a une restriction qui n'existe pas.
MODULES_PERMISSIONS = [
    ('eleves', "Élèves"),
    ('personnel', "Personnel & Paie"),
    ('comptabilite', "Comptabilité"),
    ('fournisseurs', "Fournisseurs"),
    ('logistique', "Logistique"),
    ('cantine', "Cantine"),
    ('reinscriptions', "Réinscriptions"),
    ('classes', "Classes"),
    ('salles', "Salles"),
    ('notes', "Notes & Bulletins scolaires"),
    ('absences', "Absences"),
    ('emploi_du_temps', "Emploi du temps"),
    ('revision', "Cours de révision"),
    ('candidatures', "Candidatures"),
    ('communication', "Communication"),
]

ACTIONS = ['peut_voir', 'peut_creer', 'peut_modifier', 'peut_supprimer']


def obtenir_permissions_utilisateur(user_id):
    """Renvoie {module: {peut_voir, peut_creer, peut_modifier, peut_supprimer}}
    pour les seuls modules ou une permission personnalisee a ete definie."""
    lignes = db.execute(
        "SELECT * FROM permissions_utilisateur WHERE user_id=?", (user_id,)
    ).fetchall()
    return {
        l['module']: {a: bool(l[a]) for a in ACTIONS}
        for l in lignes
    }


def a_permission(user, module, action):
    """
    True/False : l'utilisateur peut-il faire `action` sur `module` ?
    - admin / super-administrateur : toujours True (jamais restreint).
    - Permission personnalisee existante pour (user, module) : elle fait autorite.
    - Aucune permission personnalisee : True (on laisse @require_role decider,
      ce systeme ne fait alors que ne rien changer).
    """
    if user.get('role') == 'admin' or user.get('est_super_admin'):
        return True
    ligne = db.execute(
        "SELECT * FROM permissions_utilisateur WHERE user_id=? AND module=?",
        (user['id'], module),
    ).fetchone()
    if ligne is None:
        return True  # pas de personnalisation : on ne restreint pas davantage
    return bool(ligne[action])


def require_permission(module, action):
    """Decorateur a poser APRES @require_auth (et eventuellement @require_role) :
    n'ajoute qu'une restriction supplementaire, ne remplace jamais les autres
    controles deja en place sur la route."""
    def decorateur(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not hasattr(g, 'user'):
                return jsonify({'error': 'Non authentifié'}), 401
            if not a_permission(g.user, module, action):
                return jsonify({'error': "Vous n'avez pas la permission d'effectuer cette action"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorateur
