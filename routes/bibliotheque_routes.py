"""
Bibliothèque : catalogue des livres (nombre d'exemplaires), prêts aux élèves et au personnel,
retours, retards. Un exemplaire prêté n'est plus disponible tant qu'il n'est pas rendu.
"""
from datetime import date, timedelta

from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role
from permissions import require_permission

bp = Blueprint('bibliotheque_routes', __name__, url_prefix='/api/bibliotheque')

ROLES_GESTION = ('admin', 'directeur', 'secretaire')
ROLES_LECTURE = ROLES_GESTION + ('enseignant',)
PRETS_MAX_PAR_EMPRUNTEUR = 3
DUREE_PAR_DEFAUT_JOURS = 14
DUREE_MAX_JOURS = 120


def _aujourdhui():
    return date.today().isoformat()


def _livre(livre_id):
    return db.execute("SELECT * FROM livres WHERE id=? AND ecole_id=?", (livre_id, g.user['ecole_id'])).fetchone()


def _en_cours(livre_id):
    return db.execute("SELECT COUNT(*) AS n FROM prets_livres WHERE livre_id=? AND date_retour IS NULL", (livre_id,)).fetchone()['n']


@bp.route('/livres', methods=['GET'])
@require_auth
@require_role(*ROLES_LECTURE)
@require_permission('bibliotheque', 'peut_voir')
def liste_livres():
    sql = ("SELECT l.*, (SELECT COUNT(*) FROM prets_livres p WHERE p.livre_id=l.id AND p.date_retour IS NULL) AS pretes "
           "FROM livres l WHERE l.ecole_id=?")
    params = [g.user['ecole_id']]
    q = (request.args.get('q') or '').strip()
    if q:
        sql += " AND (l.titre LIKE ? OR l.auteur LIKE ? OR l.isbn LIKE ? OR l.categorie LIKE ?)"
        params += [f"%{q}%"] * 4
    livres = rows_to_list(db.execute(sql + " ORDER BY l.titre LIMIT 1000", params).fetchall())
    for l in livres:
        l['disponibles'] = max(0, l['exemplaires'] - l['pretes'])
    return jsonify(livres)


def _valider_livre(body, partiel=False):
    v = {}
    if not partiel or 'titre' in body:
        titre = (body.get('titre') or '').strip()
        if not titre:
            return None, 'Le titre est obligatoire'
        v['titre'] = titre[:200]
    for k, n in (('auteur', 150), ('isbn', 30), ('categorie', 80), ('emplacement', 80)):
        if k in body:
            v[k] = (body.get(k) or '').strip()[:n]
    if 'exemplaires' in body or not partiel:
        try:
            n = int(body.get('exemplaires', 1))
        except (TypeError, ValueError):
            return None, "Nombre d'exemplaires invalide"
        if not 0 <= n <= 10000:
            return None, "Le nombre d'exemplaires doit être compris entre 0 et 10000"
        v['exemplaires'] = n
    return v, None


@bp.route('/livres', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('bibliotheque', 'peut_creer')
def creer_livre():
    v, erreur = _valider_livre(request.get_json(silent=True) or {})
    if erreur:
        return jsonify({'error': erreur}), 400
    lid = gen_id('liv')
    cols = ['id', 'ecole_id'] + list(v)
    db.execute(f"INSERT INTO livres ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
               [lid, g.user['ecole_id']] + list(v.values()))
    db.commit()
    log_action(g.user, 'creation', 'livre', lid, {'titre': v['titre']})
    return jsonify(row_to_dict(_livre(lid))), 201


@bp.route('/livres/<livre_id>', methods=['PUT'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('bibliotheque', 'peut_modifier')
def modifier_livre(livre_id):
    if not _livre(livre_id):
        return jsonify({'error': 'Livre introuvable'}), 404
    v, erreur = _valider_livre(request.get_json(silent=True) or {}, partiel=True)
    if erreur:
        return jsonify({'error': erreur}), 400
    if not v:
        return jsonify({'error': 'Rien à modifier'}), 400
    if 'exemplaires' in v and v['exemplaires'] < _en_cours(livre_id):
        return jsonify({'error': f"{_en_cours(livre_id)} exemplaire(s) sont actuellement prêtés : le total ne peut pas être inférieur"}), 400
    db.execute(f"UPDATE livres SET {','.join(f'{k}=?' for k in v)} WHERE id=? AND ecole_id=?",
               list(v.values()) + [livre_id, g.user['ecole_id']])
    db.commit()
    log_action(g.user, 'modification', 'livre', livre_id, v)
    return jsonify(row_to_dict(_livre(livre_id)))


@bp.route('/livres/<livre_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
@require_permission('bibliotheque', 'peut_supprimer')
def supprimer_livre(livre_id):
    l = _livre(livre_id)
    if not l:
        return jsonify({'error': 'Livre introuvable'}), 404
    if _en_cours(livre_id):
        return jsonify({'error': "Ce livre a des prêts en cours : enregistrez d'abord les retours"}), 409
    db.execute("DELETE FROM livres WHERE id=? AND ecole_id=?", (livre_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'livre', livre_id, {'titre': l['titre']})
    return jsonify({'success': True})


@bp.route('/prets', methods=['GET'])
@require_auth
@require_role(*ROLES_LECTURE)
@require_permission('bibliotheque', 'peut_voir')
def liste_prets():
    sql = ("SELECT p.*, l.titre, l.auteur FROM prets_livres p JOIN livres l ON l.id=p.livre_id WHERE p.ecole_id=?")
    params = [g.user['ecole_id']]
    statut = request.args.get('statut', 'en_cours')
    if statut == 'en_cours':
        sql += " AND p.date_retour IS NULL"
    elif statut == 'retard':
        sql += " AND p.date_retour IS NULL AND p.date_retour_prevue < ?"; params.append(_aujourdhui())
    elif statut == 'rendu':
        sql += " AND p.date_retour IS NOT NULL"
    if request.args.get('emprunteur_id'):
        sql += " AND p.emprunteur_id=?"; params.append(request.args['emprunteur_id'])
    prets = rows_to_list(db.execute(sql + " ORDER BY p.date_retour_prevue, p.date_pret DESC LIMIT 1000", params).fetchall())
    auj = _aujourdhui()
    for p in prets:
        p['en_retard'] = p['date_retour'] is None and p['date_retour_prevue'] < auj
        ref = date.fromisoformat(p['date_retour'] or auj)
        p['jours_retard'] = max(0, (ref - date.fromisoformat(p['date_retour_prevue'])).days)
    return jsonify(prets)


@bp.route('/prets', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('bibliotheque', 'peut_creer')
def preter():
    body = request.get_json(silent=True) or {}
    livre = _livre(body.get('livre_id'))
    if not livre:
        return jsonify({'error': 'Livre introuvable'}), 404
    type_emp = body.get('emprunteur_type', 'eleve')
    eid = body.get('emprunteur_id')
    if type_emp == 'eleve':
        e = db.execute("SELECT id, nom, prenom, statut FROM eleves WHERE id=? AND ecole_id=?", (eid, g.user['ecole_id'])).fetchone()
        if not e or e['statut'] != 'actif':
            return jsonify({'error': 'Élève introuvable ou non actif'}), 404
    elif type_emp == 'personnel':
        e = db.execute("SELECT id, nom, prenom FROM personnel WHERE id=? AND ecole_id=?", (eid, g.user['ecole_id'])).fetchone()
        if not e:
            return jsonify({'error': 'Membre du personnel introuvable'}), 404
    else:
        return jsonify({'error': "Type d'emprunteur invalide"}), 400
    if livre['exemplaires'] - _en_cours(livre['id']) <= 0:
        return jsonify({'error': 'Aucun exemplaire disponible pour ce livre'}), 409
    deja = db.execute("SELECT COUNT(*) AS n FROM prets_livres WHERE ecole_id=? AND emprunteur_id=? AND date_retour IS NULL",
                      (g.user['ecole_id'], eid)).fetchone()['n']
    if deja >= PRETS_MAX_PAR_EMPRUNTEUR:
        return jsonify({'error': f"{PRETS_MAX_PAR_EMPRUNTEUR} livres déjà empruntés : un retour est nécessaire avant un nouveau prêt"}), 409
    if db.execute("SELECT 1 FROM prets_livres WHERE ecole_id=? AND emprunteur_id=? AND date_retour IS NULL AND date_retour_prevue < ?",
                  (g.user['ecole_id'], eid, _aujourdhui())).fetchone():
        return jsonify({'error': "Cet emprunteur a un livre en retard : il doit d'abord le rendre"}), 409
    if db.execute("SELECT 1 FROM prets_livres WHERE ecole_id=? AND emprunteur_id=? AND livre_id=? AND date_retour IS NULL",
                  (g.user['ecole_id'], eid, livre['id'])).fetchone():
        return jsonify({'error': 'Cet emprunteur a déjà ce livre'}), 409
    try:
        jours = int(body.get('jours') or DUREE_PAR_DEFAUT_JOURS)
    except (TypeError, ValueError):
        return jsonify({'error': 'Durée invalide'}), 400
    if not 1 <= jours <= DUREE_MAX_JOURS:
        return jsonify({'error': f"La durée doit être comprise entre 1 et {DUREE_MAX_JOURS} jours"}), 400
    pid = gen_id('pre')
    db.execute("INSERT INTO prets_livres (id, ecole_id, livre_id, emprunteur_type, emprunteur_id, emprunteur_nom, date_pret, "
               "date_retour_prevue, enregistre_par) VALUES (?,?,?,?,?,?,?,?,?)",
               (pid, g.user['ecole_id'], livre['id'], type_emp, eid, f"{e['prenom']} {e['nom']}", _aujourdhui(),
                (date.today() + timedelta(days=jours)).isoformat(), g.user['id']))
    db.commit()
    log_action(g.user, 'pret', 'livre', livre['id'], {'emprunteur': eid, 'pret': pid})
    return jsonify(row_to_dict(db.execute("SELECT * FROM prets_livres WHERE id=?", (pid,)).fetchone())), 201


@bp.route('/prets/<pret_id>/retour', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('bibliotheque', 'peut_modifier')
def rendre(pret_id):
    p = db.execute("SELECT * FROM prets_livres WHERE id=? AND ecole_id=?", (pret_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Prêt introuvable'}), 404
    if p['date_retour']:
        return jsonify({'error': 'Ce livre a déjà été rendu'}), 409
    db.execute("UPDATE prets_livres SET date_retour=? WHERE id=?", (_aujourdhui(), pret_id))
    db.commit()
    log_action(g.user, 'retour', 'livre', p['livre_id'], {'pret': pret_id})
    return jsonify({'success': True})


@bp.route('/stats', methods=['GET'])
@require_auth
@require_role(*ROLES_LECTURE)
@require_permission('bibliotheque', 'peut_voir')
def stats():
    e = g.user['ecole_id']
    return jsonify({
        'titres': db.execute("SELECT COUNT(*) AS n FROM livres WHERE ecole_id=?", (e,)).fetchone()['n'],
        'exemplaires': db.execute("SELECT COALESCE(SUM(exemplaires),0) AS n FROM livres WHERE ecole_id=?", (e,)).fetchone()['n'],
        'prets_en_cours': db.execute("SELECT COUNT(*) AS n FROM prets_livres WHERE ecole_id=? AND date_retour IS NULL", (e,)).fetchone()['n'],
        'en_retard': db.execute("SELECT COUNT(*) AS n FROM prets_livres WHERE ecole_id=? AND date_retour IS NULL AND date_retour_prevue < ?",
                                (e, _aujourdhui())).fetchone()['n'],
    })
