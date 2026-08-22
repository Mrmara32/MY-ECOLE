from datetime import datetime
from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role

bp = Blueprint('paie_routes', __name__, url_prefix='/api/paie')

PAIE_ROLES = ('admin', 'directeur', 'comptable')
PLAFOND_AVANCE = 0.40  # une avance sur salaire ne peut jamais dépasser 40% du salaire de référence


def _calculer_montant(personnel, mois):
    """Calcule automatiquement le salaire de base pour un membre du personnel,
    selon son mode de rémunération (mensuel fixe, ou horaire selon les heures du mois).
    Pour le personnel horaire, les heures proviennent en priorité des séances de cours
    validées par la direction (traçabilité précise) ; à défaut, de la saisie manuelle
    historique (mois où aucune séance détaillée n'a encore été déclarée)."""
    if personnel['type_remuneration'] == 'horaire':
        h_seances = db.execute(
            "SELECT COALESCE(SUM(duree_heures),0) as h FROM seances_cours WHERE personnel_id=? AND ecole_id=? AND substr(date_seance,1,7)=? AND statut='validee'",
            (personnel['id'], personnel['ecole_id'], mois)
        ).fetchone()['h']
        source = 'seances'
        h = h_seances
        if h_seances == 0:
            h_manuel = db.execute(
                "SELECT COALESCE(SUM(nombre_heures),0) as h FROM heures_enseignement WHERE personnel_id=? AND ecole_id=? AND mois=?",
                (personnel['id'], personnel['ecole_id'], mois)
            ).fetchone()['h']
            if h_manuel > 0:
                h = h_manuel
                source = 'manuel'
        taux = personnel['taux_horaire'] or 0
        return {'type_remuneration': 'horaire', 'heures': h, 'taux_horaire': taux, 'salaire_base': round(h * taux), 'source_heures': source}
    else:
        return {'type_remuneration': 'mensuel', 'heures': None, 'taux_horaire': None, 'salaire_base': personnel['salaire'] or 0}


def _calculer_prime_revision(personnel_id, mois, ecole_id):
    """Calcule la part de 60% des recettes de cours de révision revenant à cet
    enseignant pour ce mois (au prorata des heures de séances assurées), en ne
    comptant que les séances pas encore redistribuées."""
    total_recettes = db.execute(
        """SELECT COALESCE(SUM(montant),0) as s FROM transactions
           WHERE ecole_id=? AND type='entree' AND categorie='Cours de révision' AND statut_validation IN ('auto','valide')
           AND strftime('%Y-%m',date_op)=?""", (ecole_id, mois)
    ).fetchone()['s']
    pool_60pct = total_recettes * 0.60

    total_heures_mois = db.execute(
        "SELECT COALESCE(SUM(duree_heures),0) as h FROM revision_seances WHERE ecole_id=? AND strftime('%Y-%m',date_seance)=?", (ecole_id, mois)
    ).fetchone()['h']
    if total_heures_mois <= 0:
        return {'prime': 0, 'heures': 0}

    mes_heures = db.execute(
        """SELECT COALESCE(SUM(duree_heures),0) as h FROM revision_seances
           WHERE personnel_id=? AND ecole_id=? AND strftime('%Y-%m',date_seance)=? AND redistribue=0""",
        (personnel_id, ecole_id, mois)
    ).fetchone()['h']
    if mes_heures <= 0:
        return {'prime': 0, 'heures': 0}

    part_horaire = pool_60pct / total_heures_mois
    return {'prime': round(part_horaire * mes_heures), 'heures': mes_heures}


def _reference_salaire(personnel_id, ecole_id):
    """Salaire de référence utilisé pour plafonner une avance à 40% : le salaire
    fixe pour le personnel mensuel, ou le montant du dernier bulletin généré
    pour le personnel horaire (à défaut, refuse l'avance)."""
    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, ecole_id)).fetchone()
    if not p:
        return None
    if p['type_remuneration'] == 'mensuel':
        return p['salaire'] or 0
    dernier = db.execute(
        "SELECT montant_net FROM bulletins_salaire WHERE personnel_id=? AND ecole_id=? ORDER BY mois DESC LIMIT 1", (personnel_id, ecole_id)
    ).fetchone()
    return dernier['montant_net'] if dernier else None


# ─────────────────────────────────────────────────────────────
# CALCUL & LISTE
# ─────────────────────────────────────────────────────────────
@bp.route('/calcul/<personnel_id>', methods=['GET'])
@require_auth
@require_role(*PAIE_ROLES)
def calculer(personnel_id):
    mois = request.args.get('mois') or datetime.now().strftime('%Y-%m')
    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Introuvable'}), 404
    calc = _calculer_montant(p, mois)
    prime_rev = _calculer_prime_revision(personnel_id, mois, g.user['ecole_id'])
    calc['prime_revision'] = prime_rev['prime']
    calc['heures_revision'] = prime_rev['heures']

    avance = db.execute(
        "SELECT * FROM avances_salaire WHERE personnel_id=? AND ecole_id=? AND mois_remboursement=? AND statut='en_cours'",
        (personnel_id, g.user['ecole_id'], mois)
    ).fetchone()
    calc['avance_en_attente'] = row_to_dict(avance) if avance else None

    deja_paye = db.execute(
        "SELECT * FROM bulletins_salaire WHERE personnel_id=? AND ecole_id=? AND mois=?", (personnel_id, g.user['ecole_id'], mois)
    ).fetchone()
    calc['deja_genere'] = bool(deja_paye)
    calc['bulletin_existant'] = row_to_dict(deja_paye) if deja_paye else None
    calc['mois'] = mois
    calc['personnel'] = row_to_dict(p)
    return jsonify(calc)


@bp.route('/liste', methods=['GET'])
@require_auth
@require_role(*PAIE_ROLES)
def liste_paie():
    """Vue d'ensemble de la paie du mois pour tout le personnel."""
    mois = request.args.get('mois') or datetime.now().strftime('%Y-%m')
    personnel = db.execute("SELECT * FROM personnel WHERE ecole_id=? ORDER BY nom, prenom", (g.user['ecole_id'],)).fetchall()
    result = []
    for p in personnel:
        calc = _calculer_montant(dict(p), mois)
        prime_rev = _calculer_prime_revision(p['id'], mois, g.user['ecole_id'])
        calc['prime_revision'] = prime_rev['prime']
        bulletin = db.execute(
            "SELECT * FROM bulletins_salaire WHERE personnel_id=? AND ecole_id=? AND mois=?", (p['id'], g.user['ecole_id'], mois)
        ).fetchone()
        row = dict(p)
        row.update(calc)
        row['deja_paye'] = bool(bulletin)
        row['bulletin_id'] = bulletin['id'] if bulletin else None
        result.append(row)
    masse_totale = sum((r['salaire_base'] or 0) + (r['prime_revision'] or 0) for r in result)
    return jsonify({'mois': mois, 'personnel': result, 'masse_salariale_totale': masse_totale})


# ─────────────────────────────────────────────────────────────
# VALIDATION DE LA MASSE SALARIALE (comptable → directeur → admin)
# Le comptable ne peut pas payer les salaires sans cette validation en cascade.
# ─────────────────────────────────────────────────────────────
@bp.route('/validation', methods=['GET'])
@require_auth
@require_role(*PAIE_ROLES)
def get_validation():
    mois = request.args.get('mois') or datetime.now().strftime('%Y-%m')
    row = db.execute(
        """SELECT v.*, u1.full_name as soumis_par_nom, u2.full_name as valide_directeur_par_nom,
           u3.full_name as valide_admin_par_nom
           FROM validations_paie v
           LEFT JOIN users u1 ON u1.id=v.soumis_par
           LEFT JOIN users u2 ON u2.id=v.valide_directeur_par
           LEFT JOIN users u3 ON u3.id=v.valide_admin_par
           WHERE v.mois=? AND v.ecole_id=?""", (mois, g.user['ecole_id'])
    ).fetchone()
    return jsonify(row_to_dict(row) if row else None)


@bp.route('/validation', methods=['POST'])
@require_auth
@require_role(*PAIE_ROLES)
def soumettre_validation():
    """Le comptable (ou directeur/admin) soumet la situation de la masse salariale
    du mois pour validation en cascade : directeur puis administrateur."""
    body = request.get_json(silent=True) or {}
    mois = body.get('mois') or datetime.now().strftime('%Y-%m')

    existing = db.execute("SELECT * FROM validations_paie WHERE mois=? AND ecole_id=?", (mois, g.user['ecole_id'])).fetchone()
    if existing and existing['statut'] not in ('rejete',):
        return jsonify({'error': 'Une soumission existe déjà pour ce mois'}), 409

    # Calcule la masse salariale totale du mois au moment de la soumission
    personnel = db.execute("SELECT * FROM personnel WHERE ecole_id=?", (g.user['ecole_id'],)).fetchall()
    masse = 0
    for p in personnel:
        calc = _calculer_montant(dict(p), mois)
        prime = _calculer_prime_revision(p['id'], mois, g.user['ecole_id'])
        masse += calc['salaire_base'] + prime['prime']

    vid = existing['id'] if existing else gen_id('val')
    if existing:
        db.execute(
            "UPDATE validations_paie SET statut='attente_directeur', masse_salariale_totale=?, soumis_par=?, "
            "date_soumission=CURRENT_TIMESTAMP, valide_directeur_par=NULL, date_validation_directeur=NULL, "
            "valide_admin_par=NULL, date_validation_admin=NULL, motif_rejet=NULL WHERE id=?",
            (masse, g.user['id'], vid),
        )
    else:
        db.execute(
            "INSERT INTO validations_paie (id,ecole_id,mois,statut,masse_salariale_totale,soumis_par) VALUES (?,?,?,?,?,?)",
            (vid, g.user['ecole_id'], mois, 'attente_directeur', masse, g.user['id']),
        )
    db.commit()
    log_action(g.user, 'soumission_masse_salariale', 'validation_paie', vid, {'mois': mois, 'masse': masse})
    row = db.execute("SELECT * FROM validations_paie WHERE id=?", (vid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/validation/<v_id>/valider-directeur', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def valider_directeur(v_id):
    body = request.get_json(silent=True) or {}
    v = db.execute("SELECT * FROM validations_paie WHERE id=? AND ecole_id=?", (v_id, g.user['ecole_id'])).fetchone()
    if not v:
        return jsonify({'error': 'Introuvable'}), 404
    if v['statut'] != 'attente_directeur':
        return jsonify({'error': "Cette soumission n'est pas en attente de pré-validation du directeur"}), 400

    if body.get('rejeter'):
        db.execute("UPDATE validations_paie SET statut='rejete', motif_rejet=? WHERE id=?",
                   (body.get('motif'), v_id))
        db.commit()
        log_action(g.user, 'rejet_masse_salariale', 'validation_paie', v_id, {'motif': body.get('motif')})
    else:
        db.execute(
            "UPDATE validations_paie SET statut='attente_admin', valide_directeur_par=?, date_validation_directeur=CURRENT_TIMESTAMP WHERE id=?",
            (g.user['id'], v_id),
        )
        db.commit()
        log_action(g.user, 'pre_validation_masse_salariale', 'validation_paie', v_id, {'mois': v['mois']})
    row = db.execute("SELECT * FROM validations_paie WHERE id=?", (v_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/validation/<v_id>/valider-admin', methods=['PUT'])
@require_auth
@require_role('admin')
def valider_admin(v_id):
    """Approbation finale par l'administrateur (fondateur) — seule cette étape
    autorise réellement le décaissement et le paiement des salaires."""
    body = request.get_json(silent=True) or {}
    v = db.execute("SELECT * FROM validations_paie WHERE id=? AND ecole_id=?", (v_id, g.user['ecole_id'])).fetchone()
    if not v:
        return jsonify({'error': 'Introuvable'}), 404
    if v['statut'] != 'attente_admin':
        return jsonify({'error': "Cette soumission n'est pas en attente d'approbation finale"}), 400

    if body.get('rejeter'):
        db.execute("UPDATE validations_paie SET statut='rejete', motif_rejet=? WHERE id=?",
                   (body.get('motif'), v_id))
        db.commit()
        log_action(g.user, 'rejet_masse_salariale', 'validation_paie', v_id, {'motif': body.get('motif')})
    else:
        db.execute(
            "UPDATE validations_paie SET statut='approuve', valide_admin_par=?, date_validation_admin=CURRENT_TIMESTAMP WHERE id=?",
            (g.user['id'], v_id),
        )
        db.commit()
        log_action(g.user, 'approbation_finale_masse_salariale', 'validation_paie', v_id,
                   {'mois': v['mois'], 'masse': v['masse_salariale_totale']})
    row = db.execute("SELECT * FROM validations_paie WHERE id=?", (v_id,)).fetchone()
    return jsonify(row_to_dict(row))


# ─────────────────────────────────────────────────────────────
# TYPES DE PRIMES (liste déroulante modifiable)
# ─────────────────────────────────────────────────────────────
@bp.route('/types-primes', methods=['GET'])
@require_auth
def list_types_primes():
    actives_only = request.args.get('actives') != '0'
    sql = "SELECT * FROM types_primes WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if actives_only:
        sql += " AND active=1"
    sql += " ORDER BY nom"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/types-primes', methods=['POST'])
@require_auth
@require_role(*PAIE_ROLES)
def create_type_prime():
    body = request.get_json(silent=True) or {}
    nom = body.get('nom')
    if not nom:
        return jsonify({'error': 'Nom requis'}), 400
    if db.execute("SELECT id FROM types_primes WHERE ecole_id=? AND nom=?", (g.user['ecole_id'], nom)).fetchone():
        return jsonify({'error': 'Ce type de prime existe déjà'}), 409
    tid = gen_id('tp')
    db.execute("INSERT INTO types_primes (id,ecole_id,nom) VALUES (?,?,?)", (tid, g.user['ecole_id'], nom))
    db.commit()
    row = db.execute("SELECT * FROM types_primes WHERE id=?", (tid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/types-primes/<t_id>', methods=['PUT'])
@require_auth
@require_role(*PAIE_ROLES)
def update_type_prime(t_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE types_primes SET nom=COALESCE(?,nom), active=COALESCE(?,active) WHERE id=? AND ecole_id=?",
        (body.get('nom'), (1 if body.get('active') else 0) if 'active' in body else None, t_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM types_primes WHERE id=? AND ecole_id=?", (t_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/types-primes/<t_id>', methods=['DELETE'])
@require_auth
@require_role(*PAIE_ROLES)
def delete_type_prime(t_id):
    db.execute("DELETE FROM types_primes WHERE id=? AND ecole_id=?", (t_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# AVANCES SUR SALAIRE (plafond strict de 40%)
# ─────────────────────────────────────────────────────────────
@bp.route('/avances', methods=['GET'])
@require_auth
@require_role(*PAIE_ROLES)
def list_avances():
    personnel_id = request.args.get('personnel_id')
    statut = request.args.get('statut')
    sql = """SELECT a.*, p.nom, p.prenom, u.full_name as cree_par_nom
             FROM avances_salaire a JOIN personnel p ON p.id=a.personnel_id
             LEFT JOIN users u ON u.id=a.cree_par WHERE a.ecole_id=?"""
    params = [g.user['ecole_id']]
    if personnel_id: sql += " AND a.personnel_id=?"; params.append(personnel_id)
    if statut: sql += " AND a.statut=?"; params.append(statut)
    sql += " ORDER BY a.date_avance DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/avances/plafond/<personnel_id>', methods=['GET'])
@require_auth
@require_role(*PAIE_ROLES)
def plafond_avance(personnel_id):
    """Retourne le plafond maximum (40% du salaire de référence) pour cet employé,
    ainsi que le montant déjà engagé en avances non remboursées."""
    ref = _reference_salaire(personnel_id, g.user['ecole_id'])
    if ref is None:
        return jsonify({'error': "Aucun salaire de référence disponible (aucun bulletin généré pour ce personnel horaire)", 'plafond': 0, 'salaire_reference': 0})
    en_cours = db.execute(
        "SELECT COALESCE(SUM(montant),0) as s FROM avances_salaire WHERE personnel_id=? AND ecole_id=? AND statut='en_cours'",
        (personnel_id, g.user['ecole_id'])
    ).fetchone()['s']
    plafond = round(ref * PLAFOND_AVANCE)
    return jsonify({'salaire_reference': ref, 'plafond': plafond, 'deja_engage': en_cours, 'disponible': max(0, plafond - en_cours)})


@bp.route('/avances', methods=['POST'])
@require_auth
@require_role('admin', 'comptable')
def create_avance():
    body = request.get_json(silent=True) or {}
    personnel_id = body.get('personnel_id')
    montant = body.get('montant')
    try:
        montant = float(montant) if montant is not None else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if not personnel_id or not montant or montant <= 0:
        return jsonify({'error': 'Personnel et montant valide requis'}), 400

    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Personnel introuvable'}), 404

    ref = _reference_salaire(personnel_id, g.user['ecole_id'])
    if ref is None or ref <= 0:
        return jsonify({'error': "Impossible de déterminer un salaire de référence pour plafonner l'avance"}), 400

    en_cours = db.execute(
        "SELECT COALESCE(SUM(montant),0) as s FROM avances_salaire WHERE personnel_id=? AND ecole_id=? AND statut='en_cours'",
        (personnel_id, g.user['ecole_id'])
    ).fetchone()['s']
    plafond = ref * PLAFOND_AVANCE
    if en_cours + montant > plafond + 0.01:
        disponible = max(0, plafond - en_cours)
        return jsonify({
            'error': f"Cette avance dépasse le plafond autorisé de 40% du salaire ({round(plafond):,} GNF). "
                     f"Montant encore disponible : {round(disponible):,} GNF".replace(',', ' ')
        }), 400

    aid = gen_id('av')
    date_avance = body.get('date_avance') or datetime.now().strftime('%Y-%m-%d')
    mois_remboursement = body.get('mois_remboursement') or datetime.now().strftime('%Y-%m')
    db.execute(
        "INSERT INTO avances_salaire (id,ecole_id,personnel_id,montant,motif,date_avance,mois_remboursement,cree_par) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (aid, g.user['ecole_id'], personnel_id, montant, body.get('motif'), date_avance, mois_remboursement, g.user['id']),
    )
    # Décaissement immédiat de l'avance -> transaction de dépense
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,ecole_id,type,date_op,description,categorie,moyen_paiement,montant,reference,cree_par,statut_validation) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tid, g.user['ecole_id'], 'sortie', date_avance, f"Avance sur salaire — {p['prenom']} {p['nom']}",
         'Salaires', body.get('moyen_paiement', 'Espèces'), montant, f"AV-{aid}", g.user['id'], 'auto'),
    )
    db.commit()
    log_action(g.user, 'avance_salaire', 'personnel', personnel_id,
               {'montant': montant, 'nom': f"{p['prenom']} {p['nom']}", 'plafond_40pct': round(plafond)})
    row = db.execute("SELECT * FROM avances_salaire WHERE id=?", (aid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/avances/<a_id>/annuler', methods=['PUT'])
@require_auth
@require_role('admin')
def annuler_avance(a_id):
    a = db.execute("SELECT * FROM avances_salaire WHERE id=? AND ecole_id=?", (a_id, g.user['ecole_id'])).fetchone()
    if not a:
        return jsonify({'error': 'Introuvable'}), 404
    if a['statut'] != 'en_cours':
        return jsonify({'error': 'Seule une avance en cours peut être annulée'}), 400
    db.execute("UPDATE avances_salaire SET statut='annulee' WHERE id=? AND ecole_id=?", (a_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# BULLETINS DE SALAIRE
# ─────────────────────────────────────────────────────────────
@bp.route('/bulletins', methods=['POST'])
@require_auth
@require_role(*PAIE_ROLES)
def generer_bulletin():
    body = request.get_json(silent=True) or {}
    personnel_id = body.get('personnel_id')
    mois = body.get('mois')
    if not personnel_id or not mois:
        return jsonify({'error': 'Personnel et mois requis'}), 400

    # Le comptable ne peut payer les salaires que si la masse salariale du mois
    # a été pré-validée par le directeur PUIS approuvée par l'administrateur.
    if g.user['role'] == 'comptable':
        validation = db.execute("SELECT * FROM validations_paie WHERE mois=? AND ecole_id=?", (mois, g.user['ecole_id'])).fetchone()
        if not validation or validation['statut'] != 'approuve':
            return jsonify({
                'error': "Vous ne pouvez pas payer les salaires de ce mois : la masse salariale doit d'abord être "
                         "soumise, pré-validée par le directeur, puis approuvée par l'administrateur."
            }), 403

    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Personnel introuvable'}), 404

    if db.execute("SELECT id FROM bulletins_salaire WHERE personnel_id=? AND ecole_id=? AND mois=?", (personnel_id, g.user['ecole_id'], mois)).fetchone():
        return jsonify({'error': 'Un bulletin existe déjà pour ce mois'}), 409

    calc = _calculer_montant(dict(p), mois)
    prime_rev = _calculer_prime_revision(personnel_id, mois, g.user['ecole_id'])
    try:
        primes = float(body.get('primes')) if body.get('primes') not in (None, '') else 0
        deductions = float(body.get('deductions')) if body.get('deductions') not in (None, '') else 0
    except (TypeError, ValueError):
        return jsonify({'error': 'Primes ou déductions invalides'}), 400

    # Avance sur salaire en attente pour ce mois -> déduite automatiquement
    avance = db.execute(
        "SELECT * FROM avances_salaire WHERE personnel_id=? AND ecole_id=? AND mois_remboursement=? AND statut='en_cours'",
        (personnel_id, g.user['ecole_id'], mois)
    ).fetchone()
    avance_deduite = avance['montant'] if avance else 0

    montant_net = calc['salaire_base'] + prime_rev['prime'] + primes - deductions - avance_deduite

    bid = gen_id('bul')
    date_paiement = body.get('date_paiement') or datetime.now().strftime('%Y-%m-%d')
    db.execute(
        """INSERT INTO bulletins_salaire
           (id,ecole_id,personnel_id,mois,type_remuneration,heures,taux_horaire,salaire_base,prime_revision,
            heures_revision,primes,primes_detail,deductions,avance_deduite,montant_net,date_paiement,genere_par)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid, g.user['ecole_id'], personnel_id, mois, calc['type_remuneration'], calc['heures'], calc['taux_horaire'],
         calc['salaire_base'], prime_rev['prime'], prime_rev['heures'], primes, body.get('primes_detail'),
         deductions, avance_deduite, montant_net, date_paiement, g.user['id']),
    )

    # Marquer les séances de révision comme redistribuées, et l'avance comme remboursée
    if prime_rev['heures'] > 0:
        db.execute(
            "UPDATE revision_seances SET redistribue=1 WHERE personnel_id=? AND strftime('%Y-%m',date_seance)=? AND redistribue=0",
            (personnel_id, mois),
        )
    if avance:
        db.execute("UPDATE avances_salaire SET statut='remboursee' WHERE id=?", (avance['id'],))

    # Transaction comptable automatique (dépense - catégorie Salaires, toujours auto-approuvée
    # car déjà couverte par la validation de la masse salariale ou l'autorité admin/directeur)
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,ecole_id,type,date_op,description,categorie,moyen_paiement,montant,reference,cree_par,statut_validation) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tid, g.user['ecole_id'], 'sortie', date_paiement, f"Salaire {mois} — {p['prenom']} {p['nom']}",
         'Salaires', body.get('moyen_paiement', 'Virement bancaire'), montant_net,
         f"SAL-{bid}", g.user['id'], 'auto'),
    )
    db.commit()
    log_action(g.user, 'paiement_salaire', 'personnel', personnel_id,
               {'mois': mois, 'montant_net': montant_net, 'prime_revision': prime_rev['prime'],
                'avance_deduite': avance_deduite, 'nom': f"{p['prenom']} {p['nom']}"})
    row = db.execute("SELECT * FROM bulletins_salaire WHERE id=?", (bid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/bulletins', methods=['GET'])
@require_auth
@require_role(*PAIE_ROLES)
def list_bulletins():
    personnel_id = request.args.get('personnel_id')
    mois = request.args.get('mois')
    sql = """SELECT b.*, p.nom, p.prenom, p.poste, p.matiere FROM bulletins_salaire b
             JOIN personnel p ON p.id=b.personnel_id WHERE b.ecole_id=?"""
    params = [g.user['ecole_id']]
    if personnel_id: sql += " AND b.personnel_id=?"; params.append(personnel_id)
    if mois: sql += " AND b.mois=?"; params.append(mois)
    sql += " ORDER BY b.mois DESC, p.nom"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/bulletins/<b_id>', methods=['GET'])
@require_auth
def get_bulletin(b_id):
    row = db.execute(
        """SELECT b.*, p.nom, p.prenom, p.poste, p.matiere, p.photo_url, p.cycle_enseignement
           FROM bulletins_salaire b JOIN personnel p ON p.id=b.personnel_id WHERE b.id=? AND b.ecole_id=?""", (b_id, g.user['ecole_id'])
    ).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/bulletins/<b_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_bulletin(b_id):
    b = db.execute("SELECT * FROM bulletins_salaire WHERE id=? AND ecole_id=?", (b_id, g.user['ecole_id'])).fetchone()
    if not b:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM bulletins_salaire WHERE id=? AND ecole_id=?", (b_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'bulletin_salaire', b_id, {'mois': b['mois']})
    return jsonify({'success': True})
