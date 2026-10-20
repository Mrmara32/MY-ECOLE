"""
Moteur de calcul des résultats scolaires (moyennes, rangs, mentions, décisions).

Une seule source de vérité : l'écran des notes, le bulletin imprimé et le portail
parents lisent tous ces résultats via l'API, au lieu de refaire chacun leurs calculs
(avant, chaque écran recalculait de son côté, sans coefficients).

Règles appliquées (usage courant des établissements guinéens) :
  * chaque note est ramenée sur 20 ; la moyenne d'une matière est la moyenne de ses notes ;
  * la moyenne générale est la moyenne des matières PONDÉRÉE par les coefficients de la
    classe (coefficient 1 pour une matière sans coefficient défini) ;
  * une matière sans aucune note pour l'élève est ignorée (elle ne compte pas comme 0) ;
  * la moyenne annuelle est la moyenne des moyennes générales des trimestres disponibles ;
  * rang « à l'américaine » : deux élèves à égalité ont le même rang, le suivant saute
    (1er, 2e ex æquo, 2e ex æquo, 4e) ;
  * décision automatique proposée : admis si moyenne annuelle >= seuil (10 par défaut,
    réglable via le paramètre « seuil_passage »), sinon redouble. Le directeur garde la
    main : la proposition est modifiable avant d'être enregistrée.
"""
from database import db

PERIODES = ('1', '2', '3', 'annee')
SEUIL_PASSAGE_DEFAUT = 10.0


def mention(moy):
    if moy is None:
        return None
    return ('Très Bien' if moy >= 16 else 'Bien' if moy >= 14 else
            'Assez Bien' if moy >= 12 else 'Passable' if moy >= 10 else 'Insuffisant')


def appreciation_auto(moy):
    if moy is None:
        return 'Pas assez de notes'
    if moy >= 18: return 'Excellent travail ! Félicitations.'
    if moy >= 16: return 'Très bon travail. Continuez ainsi.'
    if moy >= 14: return 'Bon travail. Quelques efforts restent à fournir.'
    if moy >= 12: return 'Travail satisfaisant. Des progrès sont possibles.'
    if moy >= 10: return 'Résultats passables. Un effort supplémentaire est nécessaire.'
    return "Résultats insuffisants. Un sérieux travail de rattrapage s'impose."


def seuil_passage(ecole_id):
    r = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='seuil_passage'", (ecole_id,)).fetchone()
    try:
        v = float(r['valeur']) if r and r['valeur'] not in (None, '') else SEUIL_PASSAGE_DEFAUT
    except (TypeError, ValueError):
        v = SEUIL_PASSAGE_DEFAUT
    return v if 0 < v <= 20 else SEUIL_PASSAGE_DEFAUT


def coefficients_classe(ecole_id, classe):
    rows = db.execute("SELECT matiere, coefficient FROM matieres_classe WHERE ecole_id=? AND classe=?",
                      (ecole_id, classe)).fetchall()
    return {r['matiere']: float(r['coefficient']) for r in rows}


def classer(valeurs):
    """{id: moyenne|None} -> {id: rang|None}, rang à l'américaine sur des moyennes arrondies."""
    notees = sorted(((round(v, 2), k) for k, v in valeurs.items() if v is not None), key=lambda t: -t[0])
    rangs, rang_courant, precedent = {}, 0, None
    for position, (v, k) in enumerate(notees, start=1):
        if v != precedent:
            rang_courant, precedent = position, v
        rangs[k] = rang_courant
    return {k: rangs.get(k) for k in valeurs}


def _moyenne_ponderee(parmat, coefs):
    num = den = 0.0
    for mat, m in parmat.items():
        if m is None:
            continue
        c = coefs.get(mat, 1.0)
        if c <= 0:
            continue
        num += m * c
        den += c
    return num / den if den else None


def _moyennes_trimestre(ecole_id, classe, trimestre, eleves, coefs):
    """-> {eleve_id: {matiere: moyenne/20}} pour un trimestre."""
    ids = [e['id'] for e in eleves]
    if not ids:
        return {}
    ph = ','.join('?' * len(ids))
    rows = db.execute(
        f"SELECT eleve_id, matiere, note, note_max FROM notes WHERE ecole_id=? AND trimestre=? "
        f"AND note IS NOT NULL AND eleve_id IN ({ph})", [ecole_id, int(trimestre)] + ids).fetchall()
    cumul = {}
    for r in rows:
        nmax = r['note_max'] or 20
        if nmax <= 0:
            continue
        cumul.setdefault(r['eleve_id'], {}).setdefault(r['matiere'], []).append(r['note'] / nmax * 20)
    return {eid: {m: sum(v) / len(v) for m, v in mats.items()} for eid, mats in cumul.items()}


def calculer_classe(ecole_id, classe, periode):
    """Résultats de toute une classe pour un trimestre ('1','2','3') ou l'année ('annee')."""
    if periode not in PERIODES:
        raise ValueError('Période invalide')
    eleves = db.execute(
        "SELECT id, nom, prenom, matricule, sexe FROM eleves WHERE ecole_id=? AND classe=? AND statut='actif' "
        "ORDER BY nom, prenom", (ecole_id, classe)).fetchall()
    coefs = coefficients_classe(ecole_id, classe)
    seuil = seuil_passage(ecole_id)
    tris = {t: _moyennes_trimestre(ecole_id, classe, t, eleves, coefs) for t in ('1', '2', '3')}

    parmat_par_eleve, moy_par_eleve = {}, {}
    moy_tri_par_eleve = {}
    for e in eleves:
        eid = e['id']
        gen = {t: _moyenne_ponderee(tris[t].get(eid, {}), coefs) for t in ('1', '2', '3')}
        gen = {t: v for t, v in gen.items() if v is not None}
        moy_tri_par_eleve[eid] = {t: round(v, 2) for t, v in gen.items()}
        if periode == 'annee':
            mats = {}
            for t in ('1', '2', '3'):
                for m, v in tris[t].get(eid, {}).items():
                    mats.setdefault(m, []).append(v)
            parmat_par_eleve[eid] = {m: sum(v) / len(v) for m, v in mats.items()}
            moy_par_eleve[eid] = sum(gen.values()) / len(gen) if gen else None
        else:
            parmat_par_eleve[eid] = tris[periode].get(eid, {})
            moy_par_eleve[eid] = gen.get(periode)

    rangs = classer(moy_par_eleve)
    effectif_classe = sum(1 for v in moy_par_eleve.values() if v is not None)

    saisies = {}
    for r in db.execute("SELECT eleve_id, appreciation FROM appreciations_bulletin WHERE ecole_id=? AND periode=? "
                        "AND eleve_id IN (SELECT id FROM eleves WHERE ecole_id=? AND classe=?)",
                        (ecole_id, periode, ecole_id, classe)).fetchall():
        saisies[r['eleve_id']] = r['appreciation']
    decisions = {}
    if periode == 'annee':
        for r in db.execute("SELECT eleve_id, decision, classe_suivante FROM decisions_annuelles "
                            "WHERE ecole_id=? AND classe_origine=?", (ecole_id, classe)).fetchall():
            decisions[r['eleve_id']] = dict(r)

    matieres = sorted({m for d in parmat_par_eleve.values() for m in d} | set(coefs))
    stats = []
    for m in matieres:
        vals = [d[m] for d in parmat_par_eleve.values() if m in d]
        stats.append({'matiere': m, 'coefficient': coefs.get(m, 1.0),
                      'moyenne_classe': round(sum(vals) / len(vals), 2) if vals else None,
                      'min': round(min(vals), 2) if vals else None,
                      'max': round(max(vals), 2) if vals else None})

    sortie = []
    for e in eleves:
        eid, moy = e['id'], moy_par_eleve[e['id']]
        proposee = None if moy is None or periode != 'annee' else ('admis' if moy >= seuil else 'redouble')
        sortie.append({
            'eleve_id': eid, 'nom': e['nom'], 'prenom': e['prenom'], 'matricule': e['matricule'],
            'moyennes': {m: round(v, 2) for m, v in parmat_par_eleve[eid].items()},
            'moyenne_generale': None if moy is None else round(moy, 2),
            'moyennes_trimestres': moy_tri_par_eleve[eid],
            'rang': rangs[eid], 'effectif': effectif_classe,
            'mention': mention(moy),
            'appreciation': saisies.get(eid) or appreciation_auto(moy),
            'appreciation_saisie': eid in saisies,
            'decision_proposee': proposee,
            'decision': decisions.get(eid),
        })
    toutes = [s['moyenne_generale'] for s in sortie if s['moyenne_generale'] is not None]
    return {'classe': classe, 'periode': periode, 'seuil_passage': seuil, 'matieres': stats,
            'moyenne_classe': round(sum(toutes) / len(toutes), 2) if toutes else None,
            'moyenne_min': min(toutes) if toutes else None, 'moyenne_max': max(toutes) if toutes else None,
            'eleves': sortie}


def classe_suivante(ecole_id, classe):
    """Classe de l'ordre suivant dans l'école (None pour la dernière classe)."""
    cur = db.execute("SELECT ordre FROM classes WHERE ecole_id=? AND nom=?", (ecole_id, classe)).fetchone()
    if not cur:
        return None
    nxt = db.execute("SELECT nom FROM classes WHERE ecole_id=? AND active=1 AND ordre>? ORDER BY ordre, nom LIMIT 1",
                     (ecole_id, cur['ordre'])).fetchone()
    return nxt['nom'] if nxt else None
