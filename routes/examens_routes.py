"""
Examens et concours : sessions (examen national, composition, examen blanc, concours d'entrée),
inscription des candidats (élèves de l'école ou candidats externes), numéros de candidat,
saisie des résultats (moyenne /20 -> admis/ajourné + mention), statistiques, clôture.
"""
from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, next_sequence
from auth import require_auth, require_role
from permissions import require_permission
from bulletins import mention, annee_en_cours

bp = Blueprint('examens_routes', __name__, url_prefix='/api/examens')

TYPES = ('examen_national', 'composition', 'examen_blanc', 'concours_entree')
ROLES_GESTION = ('admin', 'directeur', 'secretaire')
ROLES_LECTURE = ROLES_GESTION + ('enseignant',)
ROLES_DIRECTION = ('admin', 'directeur')


def _examen(exam_id):
    return db.execute("SELECT * FROM examens WHERE id=? AND ecole_id=?", (exam_id, g.user['ecole_id'])).fetchone()


def _date_ok(d):
    return isinstance(d, str) and len(d) == 10 and d[4] == '-' and d[7] == '-'


@bp.route('', methods=['GET'])
@require_auth
@require_role(*ROLES_LECTURE)
@require_permission('examens', 'peut_voir')
def liste():
    return jsonify(rows_to_list(db.execute(
        "SELECT x.*, (SELECT COUNT(*) FROM examen_candidats c WHERE c.examen_id=x.id) AS nb_candidats, "
        "(SELECT COUNT(*) FROM examen_candidats c WHERE c.examen_id=x.id AND c.statut='admis') AS nb_admis "
        "FROM examens x WHERE x.ecole_id=? ORDER BY x.date_debut DESC LIMIT 500", (g.user['ecole_id'],)).fetchall()))


@bp.route('', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('examens', 'peut_creer')
def creer():
    b = request.get_json(silent=True) or {}
    nom = (b.get('nom') or '').strip()
    if not nom:
        return jsonify({'error': "Le nom de l'examen est obligatoire"}), 400
    if b.get('type') not in TYPES:
        return jsonify({'error': 'Type invalide'}), 400
    if not _date_ok(b.get('date_debut')) or (b.get('date_fin') and not _date_ok(b['date_fin'])):
        return jsonify({'error': 'Dates invalides (AAAA-MM-JJ)'}), 400
    if b.get('date_fin') and b['date_fin'] < b['date_debut']:
        return jsonify({'error': 'La date de fin précède la date de début'}), 400
    try:
        seuil = float(b.get('seuil_admission', 10))
        places = int(b['places']) if b.get('places') not in (None, '') else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Seuil ou nombre de places invalide'}), 400
    if not 0 < seuil <= 20 or (places is not None and places < 1):
        return jsonify({'error': "Seuil d'admission entre 0 et 20 ; nombre de places positif"}), 400
    xid = gen_id('exa')
    db.execute("INSERT INTO examens (id, ecole_id, nom, type, annee_scolaire, classe, date_debut, date_fin, lieu, seuil_admission, places) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               (xid, g.user['ecole_id'], nom[:150], b['type'], annee_en_cours(g.user['ecole_id']), (b.get('classe') or '').strip() or None,
                b['date_debut'], b.get('date_fin') or None, (b.get('lieu') or '').strip()[:150], seuil, places))
    db.commit()
    log_action(g.user, 'creation', 'examen', xid, {'nom': nom})
    return jsonify(row_to_dict(_examen(xid))), 201


@bp.route('/<exam_id>', methods=['DELETE'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('examens', 'peut_supprimer')
def supprimer(exam_id):
    x = _examen(exam_id)
    if not x:
        return jsonify({'error': 'Examen introuvable'}), 404
    if x['cloture']:
        return jsonify({'error': 'Un examen clôturé ne peut plus être supprimé'}), 409
    db.execute("DELETE FROM examen_candidats WHERE examen_id=?", (exam_id,))
    db.execute("DELETE FROM examens WHERE id=?", (exam_id,))
    db.commit()
    log_action(g.user, 'suppression', 'examen', exam_id, {'nom': x['nom']})
    return jsonify({'success': True})


@bp.route('/<exam_id>/candidats', methods=['GET'])
@require_auth
@require_role(*ROLES_LECTURE)
@require_permission('examens', 'peut_voir')
def candidats(exam_id):
    if not _examen(exam_id):
        return jsonify({'error': 'Examen introuvable'}), 404
    return jsonify(rows_to_list(db.execute(
        "SELECT c.*, e.classe, e.matricule FROM examen_candidats c LEFT JOIN eleves e ON e.id=c.eleve_id "
        "WHERE c.examen_id=? AND c.ecole_id=? ORDER BY c.numero", (exam_id, g.user['ecole_id'])).fetchall()))


def _ajouter(x, nom, prenom, eleve_id=None, naissance=None, tel=None):
    n = next_sequence(f"examen_{x['id']}", 'C', 4, g.user['ecole_id'])
    cid = gen_id('can')
    db.execute("INSERT INTO examen_candidats (id, ecole_id, examen_id, eleve_id, nom, prenom, date_naissance, telephone, numero) "
               "VALUES (?,?,?,?,?,?,?,?,?)", (cid, g.user['ecole_id'], x['id'], eleve_id, nom, prenom, naissance, tel, n))
    return cid


@bp.route('/<exam_id>/candidats', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('examens', 'peut_creer')
def inscrire(exam_id):
    """Inscrit : des élèves ({eleve_ids:[…]}), toute une classe ({classe:'CM2'}) ou un candidat externe ({nom, prenom})."""
    x = _examen(exam_id)
    if not x:
        return jsonify({'error': 'Examen introuvable'}), 404
    if x['cloture']:
        return jsonify({'error': 'Examen clôturé'}), 409
    b = request.get_json(silent=True) or {}
    ecole = g.user['ecole_id']
    eleves = []
    if b.get('classe'):
        eleves = db.execute("SELECT id, nom, prenom, date_naissance FROM eleves WHERE ecole_id=? AND classe=? AND statut='actif' ORDER BY nom, prenom",
                            (ecole, b['classe'])).fetchall()
    elif b.get('eleve_ids'):
        for eid in b['eleve_ids'][:500]:
            e = db.execute("SELECT id, nom, prenom, date_naissance FROM eleves WHERE id=? AND ecole_id=? AND statut='actif'", (eid, ecole)).fetchone()
            if e:
                eleves.append(e)
    elif (b.get('nom') or '').strip() and (b.get('prenom') or '').strip():
        if x['type'] != 'concours_entree' and x['type'] != 'examen_national':
            return jsonify({'error': "Les candidats externes ne sont admis que pour un concours d'entrée ou un examen national"}), 400
        eleves = None
    else:
        return jsonify({'error': 'Précisez des élèves, une classe ou un candidat externe'}), 400
    deja = {r['eleve_id'] for r in db.execute("SELECT eleve_id FROM examen_candidats WHERE examen_id=? AND eleve_id IS NOT NULL", (exam_id,)).fetchall()}
    nb = db.execute("SELECT COUNT(*) AS n FROM examen_candidats WHERE examen_id=?", (exam_id,)).fetchone()['n']
    ajoutes = []
    if eleves is None:
        a_ajouter = [(b['nom'].strip(), b['prenom'].strip(), None, b.get('date_naissance'), b.get('telephone'))]
    else:
        a_ajouter = [(e['nom'], e['prenom'], e['id'], e['date_naissance'], None) for e in eleves if e['id'] not in deja]
    if x['places'] and x['type'] == 'concours_entree' and nb + len(a_ajouter) > x['places']:
        return jsonify({'error': f"Capacité dépassée : {x['places']} places, {nb} déjà inscrits"}), 409
    for nom, prenom, eid, nais, tel in a_ajouter:
        ajoutes.append(_ajouter(x, nom, prenom, eid, nais, tel))
    db.commit()
    log_action(g.user, 'inscription', 'examen', exam_id, {'nb': len(ajoutes)})
    return jsonify({'ajoutes': len(ajoutes), 'ignores': (len(eleves) - len(ajoutes)) if eleves is not None else 0}), 201


@bp.route('/<exam_id>/resultats', methods=['PUT'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('examens', 'peut_modifier')
def saisir_resultats(exam_id):
    """Corps : {resultats:[{id, moyenne}|{id, absent:true}]}. Admis si moyenne >= seuil de l'examen."""
    x = _examen(exam_id)
    if not x:
        return jsonify({'error': 'Examen introuvable'}), 404
    if x['cloture']:
        return jsonify({'error': 'Examen clôturé : les résultats ne peuvent plus être modifiés'}), 409
    lignes = (request.get_json(silent=True) or {}).get('resultats')
    if not isinstance(lignes, list) or not lignes:
        return jsonify({'error': 'Aucun résultat'}), 400
    maj = []
    for r in lignes:
        c = db.execute("SELECT id FROM examen_candidats WHERE id=? AND examen_id=?", (r.get('id'), exam_id)).fetchone()
        if not c:
            return jsonify({'error': f"Candidat introuvable : {r.get('id')}"}), 404
        if r.get('absent'):
            maj.append(('absent', None, None, c['id']))
            continue
        if r.get('moyenne') in (None, ''):
            maj.append(('inscrit', None, None, c['id']))      # effacer le résultat
            continue
        try:
            m = round(float(r['moyenne']), 2)
        except (TypeError, ValueError):
            return jsonify({'error': 'Moyenne invalide'}), 400
        if not 0 <= m <= 20:
            return jsonify({'error': 'Une moyenne doit être comprise entre 0 et 20'}), 400
        maj.append(('admis' if m >= x['seuil_admission'] else 'ajourne', m, mention(m), c['id']))
    for statut, m, ment, cid in maj:
        db.execute("UPDATE examen_candidats SET statut=?, moyenne=?, mention=? WHERE id=?", (statut, m, ment, cid))
    db.commit()
    log_action(g.user, 'resultats', 'examen', exam_id, {'nb': len(maj)})
    return jsonify({'success': True, 'enregistres': len(maj)})


@bp.route('/<exam_id>/candidats/<cid>', methods=['DELETE'])
@require_auth
@require_role(*ROLES_GESTION)
@require_permission('examens', 'peut_supprimer')
def retirer(exam_id, cid):
    x = _examen(exam_id)
    if not x:
        return jsonify({'error': 'Examen introuvable'}), 404
    if x['cloture']:
        return jsonify({'error': 'Examen clôturé'}), 409
    db.execute("DELETE FROM examen_candidats WHERE id=? AND examen_id=? AND ecole_id=?", (cid, exam_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/<exam_id>/statistiques', methods=['GET'])
@require_auth
@require_role(*ROLES_LECTURE)
@require_permission('examens', 'peut_voir')
def statistiques(exam_id):
    x = _examen(exam_id)
    if not x:
        return jsonify({'error': 'Examen introuvable'}), 404
    cands = rows_to_list(db.execute("SELECT statut, moyenne, mention FROM examen_candidats WHERE examen_id=?", (exam_id,)).fetchall())
    presents = [c for c in cands if c['statut'] in ('admis', 'ajourne')]
    admis = [c for c in presents if c['statut'] == 'admis']
    moy = [c['moyenne'] for c in presents if c['moyenne'] is not None]
    mentions = {}
    for c in admis:
        mentions[c['mention']] = mentions.get(c['mention'], 0) + 1
    return jsonify({
        'inscrits': len(cands), 'presents': len(presents), 'absents': sum(1 for c in cands if c['statut'] == 'absent'),
        'sans_resultat': sum(1 for c in cands if c['statut'] == 'inscrit'),
        'admis': len(admis), 'ajournes': len(presents) - len(admis),
        'taux_reussite': round(100 * len(admis) / len(presents), 1) if presents else None,
        'moyenne_generale': round(sum(moy) / len(moy), 2) if moy else None,
        'meilleure': max(moy) if moy else None, 'plus_basse': min(moy) if moy else None,
        'mentions': mentions,
    })


@bp.route('/<exam_id>/cloturer', methods=['POST'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('examens', 'peut_modifier')
def cloturer(exam_id):
    x = _examen(exam_id)
    if not x:
        return jsonify({'error': 'Examen introuvable'}), 404
    if db.execute("SELECT 1 FROM examen_candidats WHERE examen_id=? AND statut='inscrit'", (exam_id,)).fetchone():
        return jsonify({'error': "Des candidats n'ont pas de résultat : saisissez une moyenne ou marquez-les absents avant de clôturer"}), 409
    db.execute("UPDATE examens SET cloture=1 WHERE id=?", (exam_id,))
    db.commit()
    log_action(g.user, 'cloture', 'examen', exam_id, {'nom': x['nom']})
    return jsonify({'success': True})
