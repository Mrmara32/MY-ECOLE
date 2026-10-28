"""
Outils de données de l'Assistante IA : statistiques AGRÉGÉES de l'établissement (effectifs, paiements à jour,
résultats, assiduité, recettes/dépenses, vie scolaire), jamais de noms d'élèves ni de notes individuelles.
Chaque outil est réservé aux rôles qui ont déjà accès à ces informations dans l'application, et toujours
limité à l'établissement de l'utilisateur. Les enseignants ne voient que leurs classes quand l'emploi du temps les rattache à elles.
"""
from datetime import date, timedelta

from database import db
from bulletins import annee_en_cours

DIRECTION = ('admin', 'directeur', 'directeur_etudes')
MIN_EFFECTIF = 3          # en dessous, une moyenne pourrait désigner un élève : on ne la communique pas


def _classes_enseignant(user):
    """Classes rattachées à l'enseignant par l'emploi du temps ; None = pas de rattachement connu (vue d'ensemble)."""
    if user.get('role') != 'enseignant':
        return None
    lignes = db.execute(
        "SELECT DISTINCT e.classe FROM emploi_du_temps e JOIN personnel p ON p.id=e.professeur_id "
        "WHERE e.ecole_id=? AND p.user_id=?", (user['ecole_id'], user['id'])).fetchall()
    classes = [l['classe'] for l in lignes if l['classe']]
    return classes or None


def _filtre_classes(user, colonne):
    cl = _classes_enseignant(user)
    if not cl:
        return '', []
    return f" AND {colonne} IN ({','.join('?' * len(cl))})", cl


def outil_effectifs(user, args):
    f, p = _filtre_classes(user, 'e.classe')
    lignes = db.execute(
        "SELECT COALESCE(e.classe,'(sans classe)') AS classe, c.cycle AS cycle, MIN(c.ordre) AS ordre, COUNT(*) AS total, "
        "SUM(CASE WHEN e.sexe='F' THEN 1 ELSE 0 END) AS filles, SUM(CASE WHEN e.sexe='M' THEN 1 ELSE 0 END) AS garcons "
        "FROM eleves e LEFT JOIN classes c ON c.nom=e.classe AND c.ecole_id=e.ecole_id "
        "WHERE e.ecole_id=? AND e.statut='actif'" + f + " GROUP BY COALESCE(e.classe,'(sans classe)'), c.cycle ORDER BY MIN(c.ordre), 1",
        [user['ecole_id']] + p).fetchall()
    classes = [{k: v for k, v in dict(l).items() if k != 'ordre'} for l in lignes]
    cycles = {}
    for c in classes:
        k = c['cycle'] or 'non défini'
        cycles[k] = cycles.get(k, 0) + c['total']
    return {'total_eleves_actifs': sum(c['total'] for c in classes), 'par_cycle': cycles, 'par_classe': classes}


def outil_paiements(user, args):
    """Élèves « à jour » = aucune échéance de scolarité non soldée."""
    f, p = _filtre_classes(user, 'e.classe')
    lignes = db.execute(
        "SELECT COALESCE(e.classe,'(sans classe)') AS classe, e.id AS eleve, "
        "COALESCE(SUM(pa.montant_du),0) AS du, COALESCE(SUM(pa.montant_paye),0) AS paye, "
        "SUM(CASE WHEN pa.statut!='paye' THEN 1 ELSE 0 END) AS non_soldes, "
        "SUM(CASE WHEN pa.statut='en_retard' THEN 1 ELSE 0 END) AS en_retard "
        "FROM eleves e LEFT JOIN paiements pa ON pa.eleve_id=e.id AND pa.ecole_id=e.ecole_id "
        "WHERE e.ecole_id=? AND e.statut='actif'" + f + " GROUP BY COALESCE(e.classe,'(sans classe)'), e.id",
        [user['ecole_id']] + p).fetchall()
    par = {}
    for l in lignes:
        c = par.setdefault(l['classe'], {'classe': l['classe'], 'eleves': 0, 'a_jour': 0, 'avec_impayes': 0,
                                          'sans_frais_enregistres': 0, 'montant_du': 0.0, 'montant_paye': 0.0})
        c['eleves'] += 1
        c['montant_du'] += l['du']; c['montant_paye'] += l['paye']
        if l['du'] == 0:
            c['sans_frais_enregistres'] += 1
        elif (l['non_soldes'] or 0) == 0:
            c['a_jour'] += 1
        else:
            c['avec_impayes'] += 1
    classes = sorted(par.values(), key=lambda c: c['classe'])
    for c in classes:
        c['reste_a_payer'] = round(c['montant_du'] - c['montant_paye'], 2)
        c['taux_recouvrement_pct'] = round(100 * c['montant_paye'] / c['montant_du'], 1) if c['montant_du'] else None
        c['montant_du'] = round(c['montant_du'], 2); c['montant_paye'] = round(c['montant_paye'], 2)
    tot = {k: sum(c[k] for c in classes) for k in ('eleves', 'a_jour', 'avec_impayes', 'sans_frais_enregistres')}
    du = sum(c['montant_du'] for c in classes); paye = sum(c['montant_paye'] for c in classes)
    tot.update({'montant_du': round(du, 2), 'montant_paye': round(paye, 2), 'reste_a_payer': round(du - paye, 2),
                'taux_recouvrement_pct': round(100 * paye / du, 1) if du else None})
    return {'ensemble': tot, 'par_classe': classes}


def outil_resultats(user, args):
    annee = annee_en_cours(user['ecole_id'])
    f, p = _filtre_classes(user, 'e.classe')
    sql = ("SELECT e.classe AS classe, n.matiere AS matiere, n.trimestre AS trimestre, COUNT(*) AS nb, "
           "AVG(n.note * 20.0 / NULLIF(n.note_max,0)) AS moyenne, "
           "SUM(CASE WHEN n.note * 20.0 / NULLIF(n.note_max,0) >= 10 THEN 1 ELSE 0 END) AS reussites "
           "FROM notes n JOIN eleves e ON e.id=n.eleve_id AND e.ecole_id=n.ecole_id "
           "WHERE n.ecole_id=? AND e.statut='actif' AND n.note IS NOT NULL AND (n.annee_scolaire=? OR n.annee_scolaire IS NULL)" + f)
    params = [user['ecole_id'], annee] + p
    if args.get('trimestre'):
        sql += " AND n.trimestre=?"; params.append(int(args['trimestre']))
    if args.get('classe'):
        sql += " AND e.classe=?"; params.append(str(args['classe']))
    sql += " GROUP BY e.classe, n.matiere, n.trimestre"
    brut = db.execute(sql, params).fetchall()
    # regroupe les trimestres (sauf si demandé) et masque les petits groupes
    agg = {}
    for l in brut:
        k = (l['classe'], l['matiere'])
        a = agg.setdefault(k, {'nb': 0, 'somme': 0.0, 'reussites': 0})
        a['nb'] += l['nb']; a['somme'] += (l['moyenne'] or 0) * l['nb']; a['reussites'] += l['reussites'] or 0
    lignes = [{'classe': c, 'matiere': m, 'nb_notes': a['nb'], 'moyenne_sur_20': round(a['somme'] / a['nb'], 2),
               'taux_reussite_pct': round(100 * a['reussites'] / a['nb'], 1)}
              for (c, m), a in agg.items() if a['nb'] >= MIN_EFFECTIF]
    par_classe = {}
    for l in lignes:
        d = par_classe.setdefault(l['classe'], [0, 0.0, 0])
        d[0] += l['nb_notes']; d[1] += l['moyenne_sur_20'] * l['nb_notes']
    classes = sorted([{'classe': c, 'nb_notes': d[0], 'moyenne_generale_sur_20': round(d[1] / d[0], 2)}
                      for c, d in par_classe.items()], key=lambda x: x['moyenne_generale_sur_20'])
    lignes.sort(key=lambda x: x['moyenne_sur_20'])
    return {'annee_scolaire': annee, 'classes_du_plus_faible_au_plus_fort': classes,
            'matieres_les_plus_faibles': lignes[:12], 'matieres_les_plus_fortes': lignes[-6:][::-1],
            'note': f"groupes de moins de {MIN_EFFECTIF} notes masqués"}


def outil_assiduite(user, args):
    jours = max(1, min(int(args.get('jours') or 30), 365))
    depuis = (date.today() - timedelta(days=jours)).isoformat()
    f, p = _filtre_classes(user, 'e.classe')
    lignes = db.execute(
        "SELECT COALESCE(e.classe,'(sans classe)') AS classe, a.type AS type, a.justifie AS justifie, COUNT(*) AS nb "
        "FROM absences a JOIN eleves e ON e.id=a.eleve_id AND e.ecole_id=a.ecole_id "
        "WHERE a.ecole_id=? AND a.date_abs>=?" + f + " GROUP BY COALESCE(e.classe,'(sans classe)'), a.type, a.justifie",
        [user['ecole_id'], depuis] + p).fetchall()
    par = {}
    for l in lignes:
        c = par.setdefault(l['classe'], {'classe': l['classe'], 'absences': 0, 'retards': 0, 'non_justifiees': 0})
        if l['type'] == 'retard':
            c['retards'] += l['nb']
        else:
            c['absences'] += l['nb']
            if not l['justifie']:
                c['non_justifiees'] += l['nb']
    classes = sorted(par.values(), key=lambda c: -c['absences'])
    return {'periode_jours': jours, 'total_absences': sum(c['absences'] for c in classes),
            'total_retards': sum(c['retards'] for c in classes), 'par_classe': classes}


def outil_finances(user, args):
    eid = user['ecole_id']
    depuis = (date.today().replace(day=1) - timedelta(days=330)).isoformat()
    mois = db.execute(
        "SELECT SUBSTR(date_op,1,7) AS mois, type, COALESCE(SUM(montant),0) AS total FROM transactions "
        "WHERE ecole_id=? AND statut_validation IN ('auto','valide') AND date_op>=? GROUP BY SUBSTR(date_op,1,7), type ORDER BY 1",
        (eid, depuis)).fetchall()
    par_mois = {}
    for l in mois:
        m = par_mois.setdefault(l['mois'], {'mois': l['mois'], 'recettes': 0, 'depenses': 0})
        m['recettes' if l['type'] == 'entree' else 'depenses'] = round(l['total'], 2)
    cats = db.execute(
        "SELECT COALESCE(categorie,'Non catégorisé') AS categorie, type, COALESCE(SUM(montant),0) AS total FROM transactions "
        "WHERE ecole_id=? AND statut_validation IN ('auto','valide') AND date_op>=? GROUP BY COALESCE(categorie,'Non catégorisé'), type ORDER BY 3 DESC",
        (eid, depuis)).fetchall()
    dettes = db.execute(
        "SELECT COALESCE(SUM(t.montant - COALESCE(t.montant_regle,0)),0) AS reste FROM transactions t "
        "WHERE t.ecole_id=? AND t.a_regler=1 AND t.type='sortie'", (eid,)).fetchone()
    return {'par_mois': list(par_mois.values()),
            'principales_recettes': [{'categorie': c['categorie'], 'total': round(c['total'], 2)} for c in cats if c['type'] == 'entree'][:8],
            'principales_depenses': [{'categorie': c['categorie'], 'total': round(c['total'], 2)} for c in cats if c['type'] == 'sortie'][:8],
            'dettes_fournisseurs_restantes': round(dettes['reste'] or 0, 2),
            'periode': f"depuis {depuis}"}


def outil_vie_ecole(user, args):
    eid = user['ecole_id']
    depuis = (date.today() - timedelta(days=90)).isoformat()

    def n(sql, *p):
        r = db.execute(sql, (eid,) + p).fetchone()
        return list(dict(r).values())[0] or 0
    disc = db.execute("SELECT type, COUNT(*) AS nb FROM discipline WHERE ecole_id=? AND date_fait>=? GROUP BY type", (eid, depuis)).fetchall()
    return {
        'discipline_90_jours': {d['type']: d['nb'] for d in disc},
        'devoirs_en_cours': n("SELECT COUNT(*) FROM devoirs WHERE ecole_id=? AND statut='En cours'"),
        'reinscriptions_en_attente': n("SELECT COUNT(*) FROM reinscriptions WHERE ecole_id=? AND statut='en_attente'"),
        'seances_a_valider': n("SELECT COUNT(*) FROM seances_cours WHERE ecole_id=? AND statut='en_attente'"),
        'depenses_a_valider': n("SELECT COUNT(*) FROM transactions WHERE ecole_id=? AND statut_validation IN ('attente_directeur','attente_admin')"),
        'personnel': n("SELECT COUNT(*) FROM personnel WHERE ecole_id=?"),
        'livres_catalogue': n("SELECT COUNT(*) FROM livres WHERE ecole_id=?"),
    }


OUTILS = {
    'effectifs': {
        'roles': DIRECTION + ('secretaire', 'comptable', 'enseignant'), 'fn': outil_effectifs,
        'description': "Nombre d'élèves actifs par classe et par cycle (maternelle, primaire, collège, lycée), avec filles/garçons.",
        'schema': {'type': 'object', 'properties': {}}},
    'paiements': {
        'roles': DIRECTION + ('secretaire', 'comptable'), 'fn': outil_paiements,
        'description': "Situation des paiements de scolarité par classe : élèves à jour, élèves avec impayés, montants dus/payés, taux de recouvrement.",
        'schema': {'type': 'object', 'properties': {}}},
    'resultats': {
        'roles': DIRECTION + ('enseignant',), 'fn': outil_resultats,
        'description': "Résultats scolaires agrégés de l'année en cours : moyenne sur 20 et taux de réussite par classe et par matière ; classes et matières les plus faibles.",
        'schema': {'type': 'object', 'properties': {'trimestre': {'type': 'integer'}, 'classe': {'type': 'string'}}}},
    'assiduite': {
        'roles': DIRECTION + ('secretaire', 'enseignant'), 'fn': outil_assiduite,
        'description': "Absences et retards par classe sur les N derniers jours (30 par défaut), dont absences non justifiées.",
        'schema': {'type': 'object', 'properties': {'jours': {'type': 'integer'}}}},
    'finances': {
        'roles': DIRECTION + ('comptable',), 'fn': outil_finances,
        'description': "Recettes et dépenses par mois (12 derniers mois), principales catégories, dettes fournisseurs restantes.",
        'schema': {'type': 'object', 'properties': {}}},
    'vie_ecole': {
        'roles': DIRECTION, 'fn': outil_vie_ecole,
        'description': "Vie de l'établissement : discipline (90 jours), devoirs en cours, réinscriptions et séances à valider, dépenses à valider, effectif du personnel.",
        'schema': {'type': 'object', 'properties': {}}},
}


def outils_pour(role):
    return [{'name': k, 'description': v['description'], 'input_schema': v['schema']}
            for k, v in OUTILS.items() if role in v['roles']]


def executer(nom, user, args):
    o = OUTILS.get(nom)
    if not o or user.get('role') not in o['roles']:
        return {'erreur': "Outil non autorisé pour votre rôle."}
    try:
        return o['fn'](user, args or {})
    except Exception as e:
        print(f"[assistant] outil {nom}: {type(e).__name__}: {e}")
        return {'erreur': "Données indisponibles pour le moment."}


def alertes(user):
    """« Le point de l'assistante » : alertes calculées par règles (sans appel au modèle) à partir des mêmes statistiques agrégées,
    limitées à ce que le rôle a le droit de consulter."""
    role = user.get('role')
    liste = []

    def ajouter(niveau, titre, detail, question):
        liste.append({'niveau': niveau, 'titre': titre, 'detail': detail, 'question': question})

    if role in OUTILS['paiements']['roles']:
        p = outil_paiements(user, {})
        e = p['ensemble']
        if e['eleves']:
            if e['avec_impayes']:
                ajouter('orange' if e['avec_impayes'] * 4 < e['eleves'] else 'rouge',
                        f"{e['a_jour']} élèves sur {e['eleves']} sont à jour de leurs paiements",
                        f"{e['avec_impayes']} élève(s) ont des impayés ; reste à recouvrer : {e['reste_a_payer']:,.0f}".replace(',', ' '),
                        "Comment relancer les familles et améliorer le recouvrement des frais de scolarité ?")
            faibles = [c for c in p['par_classe'] if c['taux_recouvrement_pct'] is not None and c['taux_recouvrement_pct'] < 50 and c['montant_du'] > 0]
            if faibles:
                ajouter('rouge', "Recouvrement inférieur à 50 % : " + ', '.join(c['classe'] for c in faibles[:4]),
                        "Ces classes concentrent le retard de paiement.", "Que faire pour les classes dont le recouvrement est inférieur à 50 % ?")
            if e['sans_frais_enregistres']:
                ajouter('info', f"{e['sans_frais_enregistres']} élève(s) sans frais de scolarité enregistrés",
                        "Leur situation de paiement ne peut pas être suivie.", "Comment enregistrer les frais de scolarité des élèves qui n'en ont pas ?")
    if role in OUTILS['resultats']['roles']:
        r = outil_resultats(user, {})
        faibles = [c for c in r['classes_du_plus_faible_au_plus_fort'] if c['moyenne_generale_sur_20'] < 10]
        if faibles:
            ajouter('rouge', "Moyenne générale sous 10/20 : " + ', '.join(f"{c['classe']} ({c['moyenne_generale_sur_20']})" for c in faibles[:4]),
                    "Ces classes ont besoin d'un plan de remédiation.", "Propose un plan pour améliorer les résultats des classes les plus faibles.")
        mat = [m for m in r['matieres_les_plus_faibles'] if m['moyenne_sur_20'] < 8]
        if mat:
            ajouter('orange', "Matières en difficulté : " + ', '.join(f"{m['matiere']} en {m['classe']} ({m['moyenne_sur_20']})" for m in mat[:3]),
                    "Moyennes inférieures à 8/20.", "Comment remédier aux difficultés dans les matières les plus faibles ?")
    if role in OUTILS['assiduite']['roles']:
        a = outil_assiduite(user, {'jours': 30})
        if a['par_classe'] and a['par_classe'][0]['non_justifiees'] >= 10:
            c = a['par_classe'][0]
            ajouter('orange', f"Absences non justifiées en {c['classe']} : {c['non_justifiees']} en 30 jours",
                    f"{a['total_absences']} absences et {a['total_retards']} retards dans l'école sur 30 jours.",
                    "Comment réduire les absences non justifiées ?")
    if role in DIRECTION:
        v = outil_vie_ecole(user, {})
        for cle, texte, q in (('reinscriptions_en_attente', "réinscription(s) en attente de décision", "Comment traiter rapidement les réinscriptions en attente ?"),
                              ('depenses_a_valider', "dépense(s) à valider", None), ('seances_a_valider', "séance(s) de cours à valider", None)):
            if v[cle]:
                ajouter('info', f"{v[cle]} {texte}", "Action de la direction attendue.", q or f"Que dois-je vérifier avant de valider les {texte.split('(')[0]}s ?")
    if role in OUTILS['finances']['roles']:
        f = outil_finances(user, {})
        mois = f['par_mois']
        if len(mois) >= 2 and mois[-2]['recettes']:
            dernier_complet, precedent = mois[-1], mois[-2]
            if dernier_complet['depenses'] > dernier_complet['recettes'] > 0:
                ajouter('rouge', f"Dépenses supérieures aux recettes en {dernier_complet['mois']}",
                        f"Recettes {dernier_complet['recettes']:,.0f} — dépenses {dernier_complet['depenses']:,.0f}".replace(',', ' '),
                        "Comment réduire les dépenses et augmenter les recettes de l'école ?")
        if f['dettes_fournisseurs_restantes'] > 0:
            ajouter('info', "Dettes fournisseurs à régler : " + f"{f['dettes_fournisseurs_restantes']:,.0f}".replace(',', ' '),
                    "Voir « Dettes fournisseurs » dans Comptabilité.", "Comment prioriser le règlement de nos dettes fournisseurs ?")
    ordre = {'rouge': 0, 'orange': 1, 'info': 2}
    liste.sort(key=lambda a: ordre[a['niveau']])
    return liste[:8]
