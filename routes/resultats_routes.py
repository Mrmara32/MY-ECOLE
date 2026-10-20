"""
Résultats scolaires : matières et coefficients par classe, bulletins calculés par le
serveur (moyennes pondérées, rangs, mentions), appréciations du conseil de classe et
décisions de fin d'année reliées au circuit de réinscription existant.
"""
from flask import Blueprint, request, jsonify, g

import bulletins
from database import db, gen_id, rows_to_list, log_action, get_classes_enseignant
from auth import require_auth, require_role
from permissions import require_permission

bp = Blueprint('resultats_routes', __name__, url_prefix='/api')

ROLES_DIRECTION = ('admin', 'directeur')
DECISIONS = ('admis', 'redouble', 'exclu')


def _classe_existe(classe):
    return bool(classe) and db.execute("SELECT 1 FROM classes WHERE ecole_id=? AND nom=?",
                                       (g.user['ecole_id'], classe)).fetchone()


def _acces_classe(classe):
    """Un enseignant ne voit que les classes où il enseigne ; un parent n'a pas accès aux classes."""
    if g.user['role'] == 'parent':
        return False
    if g.user['role'] == 'enseignant':
        return classe in get_classes_enseignant(g.user['id'])
    return True


# ── Matières & coefficients ───────────────────────────────────
@bp.route('/matieres-classe', methods=['GET'])
@require_auth
@require_permission('notes', 'peut_voir')
def list_matieres_classe():
    classe = request.args.get('classe')
    sql, params = "SELECT * FROM matieres_classe WHERE ecole_id=?", [g.user['ecole_id']]
    if classe:
        sql += " AND classe=?"; params.append(classe)
    return jsonify(rows_to_list(db.execute(sql + " ORDER BY classe, matiere", params).fetchall()))


@bp.route('/matieres-classe', methods=['PUT'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('notes', 'peut_modifier')
def set_matieres_classe():
    """Remplace la liste des matières (et coefficients) d'une classe : {classe, matieres:[{matiere, coefficient}]}."""
    body = request.get_json(silent=True) or {}
    classe, matieres = body.get('classe'), body.get('matieres')
    if not _classe_existe(classe):
        return jsonify({'error': 'Classe introuvable'}), 404
    if not isinstance(matieres, list):
        return jsonify({'error': 'Liste de matières requise'}), 400
    propres, vues = [], set()
    for m in matieres:
        nom = str((m or {}).get('matiere') or '').strip()
        try:
            coef = float((m or {}).get('coefficient', 1))
        except (TypeError, ValueError):
            return jsonify({'error': f'Coefficient invalide pour « {nom} »'}), 400
        if not nom:
            return jsonify({'error': 'Nom de matière vide'}), 400
        if not 0 < coef <= 20:
            return jsonify({'error': f'Le coefficient de « {nom} » doit être compris entre 0 (exclu) et 20'}), 400
        if nom.lower() in vues:
            return jsonify({'error': f'Matière « {nom} » en double'}), 400
        vues.add(nom.lower()); propres.append((nom, coef))
    eid = g.user['ecole_id']
    db.execute("DELETE FROM matieres_classe WHERE ecole_id=? AND classe=?", (eid, classe))
    for nom, coef in propres:
        db.execute("INSERT INTO matieres_classe (id,ecole_id,classe,matiere,coefficient) VALUES (?,?,?,?,?)",
                   (gen_id('mc'), eid, classe, nom, coef))
    db.commit()
    log_action(g.user, 'modification', 'matieres_classe', classe, {'nombre': len(propres)})
    return jsonify(rows_to_list(db.execute(
        "SELECT * FROM matieres_classe WHERE ecole_id=? AND classe=? ORDER BY matiere", (eid, classe)).fetchall()))


# ── Bulletins ─────────────────────────────────────────────────
@bp.route('/bulletins/classe/<path:classe>', methods=['GET'])
@require_auth
@require_permission('notes', 'peut_voir')
def bulletins_classe(classe):
    periode = request.args.get('periode', '1')
    if periode not in bulletins.PERIODES:
        return jsonify({'error': "Période invalide (1, 2, 3 ou annee)"}), 400
    if not _classe_existe(classe):
        return jsonify({'error': 'Classe introuvable'}), 404
    if not _acces_classe(classe):
        return jsonify({'error': 'Accès refusé à cette classe'}), 403
    return jsonify(bulletins.calculer_classe(g.user['ecole_id'], classe, periode))


@bp.route('/bulletins/eleve/<eleve_id>', methods=['GET'])
@require_auth
@require_permission('notes', 'peut_voir')
def bulletin_eleve(eleve_id):
    periode = request.args.get('periode', '1')
    if periode not in bulletins.PERIODES:
        return jsonify({'error': "Période invalide (1, 2, 3 ou annee)"}), 400
    e = db.execute("SELECT id, classe FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    if g.user['role'] == 'parent':
        if not db.execute("SELECT 1 FROM parents_eleves WHERE user_id=? AND eleve_id=?", (g.user['id'], eleve_id)).fetchone():
            return jsonify({'error': 'Accès refusé à cet élève'}), 403
    elif not _acces_classe(e['classe']):
        return jsonify({'error': 'Accès refusé à cet élève'}), 403
    res = bulletins.calculer_classe(g.user['ecole_id'], e['classe'], periode)
    ligne = next((x for x in res['eleves'] if x['eleve_id'] == eleve_id), None)
    if ligne is None:  # élève non actif dans la classe
        return jsonify({'error': "Cet élève n'est pas actif dans sa classe"}), 404
    # Un parent ne reçoit que les statistiques de classe, jamais les résultats des autres élèves.
    return jsonify({k: v for k, v in res.items() if k != 'eleves'} | {'eleve': ligne})


@bp.route('/bulletins/appreciation', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
@require_permission('notes', 'peut_modifier')
def set_appreciation():
    body = request.get_json(silent=True) or {}
    eleve_id, periode = body.get('eleve_id'), str(body.get('periode', ''))
    texte = (body.get('appreciation') or '').strip()[:500]
    e = db.execute("SELECT id, classe FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not e or periode not in bulletins.PERIODES:
        return jsonify({'error': 'Élève ou période invalide'}), 400
    if not _acces_classe(e['classe']):
        return jsonify({'error': 'Accès refusé à cette classe'}), 403
    if texte:
        db.execute("INSERT INTO appreciations_bulletin (ecole_id,eleve_id,periode,appreciation) VALUES (?,?,?,?) "
                   "ON CONFLICT(eleve_id,periode) DO UPDATE SET appreciation=excluded.appreciation, "
                   "updated_at=CURRENT_TIMESTAMP", (g.user['ecole_id'], eleve_id, periode, texte))
    else:  # texte vide : retour à l'appréciation automatique
        db.execute("DELETE FROM appreciations_bulletin WHERE eleve_id=? AND periode=? AND ecole_id=?",
                   (eleve_id, periode, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ── Fin d'année ───────────────────────────────────────────────
@bp.route('/fin-annee/<path:classe>', methods=['GET'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('notes', 'peut_voir')
def fin_annee_classe(classe):
    """Résultats annuels de la classe + décision proposée + classe suivante suggérée."""
    if not _classe_existe(classe):
        return jsonify({'error': 'Classe introuvable'}), 404
    res = bulletins.calculer_classe(g.user['ecole_id'], classe, 'annee')
    res['classe_suivante_suggeree'] = bulletins.classe_suivante(g.user['ecole_id'], classe)
    return jsonify(res)


@bp.route('/fin-annee/decisions', methods=['POST'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('notes', 'peut_modifier')
def enregistrer_decisions():
    """{annee_scolaire, classe, decisions:[{eleve_id, decision, classe_suivante?}]} — décisions du conseil de classe."""
    body = request.get_json(silent=True) or {}
    annee, classe, liste = body.get('annee_scolaire'), body.get('classe'), body.get('decisions')
    if not annee or not _classe_existe(classe) or not isinstance(liste, list) or not liste:
        return jsonify({'error': 'Année scolaire, classe et décisions requises'}), 400
    eid = g.user['ecole_id']
    res = bulletins.calculer_classe(eid, classe, 'annee')
    moyennes = {x['eleve_id']: x['moyenne_generale'] for x in res['eleves']}
    suggeree = bulletins.classe_suivante(eid, classe)
    lignes = []
    for d in liste:
        d = d or {}
        if d.get('eleve_id') not in moyennes:
            return jsonify({'error': "Élève inconnu ou inactif dans cette classe"}), 400
        if d.get('decision') not in DECISIONS:
            return jsonify({'error': f"Décision invalide (attendu : {', '.join(DECISIONS)})"}), 400
        suivante = None
        if d['decision'] == 'admis':
            suivante = d.get('classe_suivante') or suggeree
            if not suivante or not _classe_existe(suivante):
                return jsonify({'error': "Classe suivante à préciser pour un élève admis"}), 400
        elif d['decision'] == 'redouble':
            suivante = classe
        lignes.append((eid, d['eleve_id'], annee, classe, moyennes[d['eleve_id']], d['decision'], suivante, g.user['id']))
    for l in lignes:
        db.execute("INSERT INTO decisions_annuelles (ecole_id,eleve_id,annee_scolaire,classe_origine,moyenne_annuelle,"
                   "decision,classe_suivante,decide_par) VALUES (?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(eleve_id,annee_scolaire) DO UPDATE SET classe_origine=excluded.classe_origine, "
                   "moyenne_annuelle=excluded.moyenne_annuelle, decision=excluded.decision, "
                   "classe_suivante=excluded.classe_suivante, decide_par=excluded.decide_par", l)
    db.commit()
    log_action(g.user, 'creation', 'decisions_annuelles', classe, {'annee': annee, 'nombre': len(lignes)})
    return jsonify({'success': True, 'enregistrees': len(lignes)})


@bp.route('/fin-annee/reinscriptions', methods=['POST'])
@require_auth
@require_role(*ROLES_DIRECTION)
@require_permission('reinscriptions', 'peut_creer')
def proposer_reinscriptions():
    """{annee_scolaire (décisions), nouvelle_annee} — crée des réinscriptions EN ATTENTE pour les élèves admis ou
    redoublants. Leur validation (écran Réinscriptions) change la classe et génère les frais, comme d'habitude."""
    body = request.get_json(silent=True) or {}
    annee, nouvelle = body.get('annee_scolaire'), body.get('nouvelle_annee')
    if not annee or not nouvelle or annee == nouvelle:
        return jsonify({'error': "Année des décisions et nouvelle année (différente) requises"}), 400
    eid = g.user['ecole_id']
    lignes = db.execute("SELECT * FROM decisions_annuelles WHERE ecole_id=? AND annee_scolaire=? "
                        "AND decision IN ('admis','redouble')", (eid, annee)).fetchall()
    creees = deja = 0
    for d in lignes:
        if db.execute("SELECT 1 FROM reinscriptions WHERE eleve_id=? AND annee_scolaire=?", (d['eleve_id'], nouvelle)).fetchone():
            deja += 1
            continue
        db.execute("INSERT INTO reinscriptions (id,ecole_id,eleve_id,annee_scolaire,classe_precedente,classe_nouvelle,notes) "
                   "VALUES (?,?,?,?,?,?,?)",
                   (gen_id('rei'), eid, d['eleve_id'], nouvelle, d['classe_origine'], d['classe_suivante'],
                    f"Décision du conseil de classe {annee} : {d['decision']} (moyenne {d['moyenne_annuelle']:.2f}/20)"
                    if d['moyenne_annuelle'] is not None else f"Décision du conseil de classe {annee} : {d['decision']}"))
        creees += 1
    db.commit()
    log_action(g.user, 'creation', 'reinscriptions', None, {'depuis': annee, 'vers': nouvelle, 'creees': creees})
    return jsonify({'success': True, 'creees': creees, 'deja_existantes': deja})
