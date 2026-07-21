from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, get_settings
from auth import require_auth, require_role

bp = Blueprint('finances_routes', __name__, url_prefix='/api')

FIN_ROLES = ('admin', 'directeur', 'comptable', 'secretaire')


def determiner_statut_validation(type_, montant, role_createur):
    """Applique les règles d'approbation comptable (points 3/4/5 du cahier des charges):
    - L'admin (fondateur) a toujours autorité totale : ses opérations sont auto-validées.
    - Les recettes (entrée) ne nécessitent pas d'approbation.
    - Dépenses (sortie) :
        < seuil_directeur              -> auto-validé
        seuil_directeur..seuil_admin    -> attente_directeur (sauf si le créateur EST le directeur -> auto)
        > seuil_admin                   -> attente_admin (sauf si le créateur EST l'admin -> auto, déjà couvert ci-dessus)
    """
    if role_createur == 'admin':
        return 'auto'
    if type_ == 'entree':
        return 'auto'
    s = get_settings()
    seuil_directeur = float(s.get('seuil_approbation_directeur') or 30000)
    seuil_admin = float(s.get('seuil_approbation_admin') or 100000)
    if montant < seuil_directeur:
        return 'auto'
    if montant <= seuil_admin:
        return 'auto' if role_createur == 'directeur' else 'attente_directeur'
    return 'attente_admin'


# ─────────────────────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────────────────────
@bp.route('/transactions', methods=['GET'])
@require_auth
def list_transactions():
    type_ = request.args.get('type')
    categorie = request.args.get('categorie')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    q = request.args.get('q')
    statut_validation = request.args.get('statut_validation')

    sql = ("SELECT t.*, e.nom as eleve_nom, e.prenom as eleve_prenom, "
           "u1.full_name as cree_par_nom, u2.full_name as valide_par_nom "
           "FROM transactions t LEFT JOIN eleves e ON e.id=t.eleve_id "
           "LEFT JOIN users u1 ON u1.id=t.cree_par LEFT JOIN users u2 ON u2.id=t.valide_par WHERE 1=1")
    params = []
    if type_: sql += " AND t.type=?"; params.append(type_)
    if categorie: sql += " AND t.categorie=?"; params.append(categorie)
    if date_debut: sql += " AND t.date_op>=?"; params.append(date_debut)
    if date_fin: sql += " AND t.date_op<=?"; params.append(date_fin)
    if q: sql += " AND (t.description LIKE ? OR t.reference LIKE ?)"; params += [f"%{q}%", f"%{q}%"]
    if statut_validation: sql += " AND t.statut_validation=?"; params.append(statut_validation)
    sql += " ORDER BY t.date_op DESC, t.created_at DESC"

    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/transactions/en-attente', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def transactions_en_attente():
    """Liste les transactions en attente d'approbation, filtrées selon le rôle de qui consulte."""
    if g.user['role'] == 'admin':
        sql = ("SELECT t.*, e.nom as eleve_nom, e.prenom as eleve_prenom, u.full_name as cree_par_nom "
               "FROM transactions t LEFT JOIN eleves e ON e.id=t.eleve_id LEFT JOIN users u ON u.id=t.cree_par "
               "WHERE t.statut_validation IN ('attente_directeur','attente_admin') ORDER BY t.created_at DESC")
        rows = db.execute(sql).fetchall()
    else:  # directeur : ne voit que ce qu'il doit lui-même approuver
        sql = ("SELECT t.*, e.nom as eleve_nom, e.prenom as eleve_prenom, u.full_name as cree_par_nom "
               "FROM transactions t LEFT JOIN eleves e ON e.id=t.eleve_id LEFT JOIN users u ON u.id=t.cree_par "
               "WHERE t.statut_validation='attente_directeur' ORDER BY t.created_at DESC")
        rows = db.execute(sql).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/transactions', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def create_transaction():
    body = request.get_json(silent=True) or {}
    type_, date_op = body.get('type'), body.get('date_op')
    try:
        montant = float(body.get('montant')) if body.get('montant') is not None else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if not type_ or not date_op or not montant:
        return jsonify({'error': 'Type, date et montant requis'}), 400
    if montant <= 0:
        return jsonify({'error': 'Le montant doit être positif'}), 400

    statut = determiner_statut_validation(type_, montant, g.user['role'])
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,type,date_op,description,categorie,moyen_paiement,montant,reference,eleve_id,cree_par,statut_validation) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tid, type_, date_op, body.get('description'), body.get('categorie'), body.get('moyen_paiement'),
         montant, body.get('reference'), body.get('eleve_id'), g.user['id'], statut),
    )
    db.commit()
    log_action(g.user, 'creation', 'transaction', tid, {'type': type_, 'montant': montant, 'statut_validation': statut})
    row = db.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
    result = row_to_dict(row)
    if statut in ('attente_directeur', 'attente_admin'):
        result['_info'] = ("Cette dépense dépasse le seuil autorisé et doit être approuvée par "
                            + ("l'administrateur" if statut == 'attente_admin' else "le directeur")
                            + " avant d'être comptabilisée dans les totaux.")
    return jsonify(result), 201


@bp.route('/transactions/<t_id>/approuver', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def approuver_transaction(t_id):
    t = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    if not t:
        return jsonify({'error': 'Introuvable'}), 404
    if t['statut_validation'] == 'attente_directeur' and g.user['role'] not in ('directeur', 'admin'):
        return jsonify({'error': 'Accès refusé'}), 403
    if t['statut_validation'] == 'attente_admin' and g.user['role'] != 'admin':
        return jsonify({'error': "Seul l'administrateur peut approuver cette opération"}), 403
    if t['statut_validation'] not in ('attente_directeur', 'attente_admin'):
        return jsonify({'error': "Cette opération n'est pas en attente d'approbation"}), 400

    db.execute("UPDATE transactions SET statut_validation='valide', valide_par=?, date_validation=CURRENT_TIMESTAMP WHERE id=?",
               (g.user['id'], t_id))
    db.commit()
    log_action(g.user, 'approbation', 'transaction', t_id, {'montant': t['montant'], 'description': t['description']})
    row = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/transactions/<t_id>/rejeter', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def rejeter_transaction(t_id):
    body = request.get_json(silent=True) or {}
    t = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    if not t:
        return jsonify({'error': 'Introuvable'}), 404
    if t['statut_validation'] == 'attente_admin' and g.user['role'] != 'admin':
        return jsonify({'error': "Seul l'administrateur peut rejeter cette opération"}), 403
    if t['statut_validation'] not in ('attente_directeur', 'attente_admin'):
        return jsonify({'error': "Cette opération n'est pas en attente d'approbation"}), 400

    db.execute("UPDATE transactions SET statut_validation='rejete', valide_par=?, date_validation=CURRENT_TIMESTAMP, motif_rejet=? WHERE id=?",
               (g.user['id'], body.get('motif'), t_id))
    db.commit()
    log_action(g.user, 'rejet', 'transaction', t_id, {'motif': body.get('motif'), 'montant': t['montant']})
    row = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/transactions/<t_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def update_transaction(t_id):
    """Toute modification d'une transaction existante est réservée à l'administrateur (point 3)."""
    body = request.get_json(silent=True) or {}
    existing = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        "UPDATE transactions SET description=COALESCE(?,description), categorie=COALESCE(?,categorie), "
        "moyen_paiement=COALESCE(?,moyen_paiement), montant=COALESCE(?,montant), reference=COALESCE(?,reference), "
        "date_op=COALESCE(?,date_op) WHERE id=?",
        (body.get('description'), body.get('categorie'), body.get('moyen_paiement'),
         body.get('montant'), body.get('reference'), body.get('date_op'), t_id),
    )
    db.commit()
    log_action(g.user, 'modification', 'transaction', t_id, {'avant': dict(existing), 'apres': body})
    row = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/transactions/<t_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_transaction(t_id):
    existing = db.execute("SELECT * FROM transactions WHERE id=?", (t_id,)).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM transactions WHERE id=?", (t_id,))
    db.commit()
    log_action(g.user, 'suppression', 'transaction', t_id, dict(existing))
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# BARÈMES FRAIS
# ─────────────────────────────────────────────────────────────
@bp.route('/frais', methods=['GET'])
@require_auth
def list_frais():
    rows = db.execute("SELECT * FROM frais_scolarite ORDER BY annee_scolaire DESC, classe").fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/frais', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'comptable')
def create_frais():
    body = request.get_json(silent=True) or {}
    classe, annee_scolaire = body.get('classe'), body.get('annee_scolaire')
    if not classe or not annee_scolaire:
        return jsonify({'error': 'Classe et année requis'}), 400
    fid = gen_id('fs')
    try:
        db.execute(
            "INSERT INTO frais_scolarite (id,classe,annee_scolaire,frais_inscription,scolarite_annuelle,nombre_tranches) "
            "VALUES (?,?,?,?,?,?)",
            (fid, classe, annee_scolaire, body.get('frais_inscription', 0),
             body.get('scolarite_annuelle', 0), body.get('nombre_tranches', 3)),
        )
        db.commit()
    except Exception:
        return jsonify({'error': 'Barème déjà existant pour cette classe/année'}), 409
    row = db.execute("SELECT * FROM frais_scolarite WHERE id=?", (fid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/frais/<f_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def update_frais(f_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE frais_scolarite SET frais_inscription=COALESCE(?,frais_inscription), "
        "scolarite_annuelle=COALESCE(?,scolarite_annuelle), nombre_tranches=COALESCE(?,nombre_tranches) WHERE id=?",
        (body.get('frais_inscription'), body.get('scolarite_annuelle'), body.get('nombre_tranches'), f_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM frais_scolarite WHERE id=?", (f_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/frais/<f_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_frais(f_id):
    db.execute("DELETE FROM frais_scolarite WHERE id=?", (f_id,))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# PAIEMENTS ÉCHELONNÉS
# ─────────────────────────────────────────────────────────────
@bp.route('/paiements', methods=['GET'])
@require_auth
def list_paiements():
    eleve_id = request.args.get('eleve_id')
    classe = request.args.get('classe')
    statut = request.args.get('statut')
    annee_scolaire = request.args.get('annee_scolaire')

    sql = """SELECT p.*, e.nom, e.prenom, e.classe, e.matricule
             FROM paiements p JOIN eleves e ON e.id=p.eleve_id WHERE 1=1"""
    params = []
    if eleve_id: sql += " AND p.eleve_id=?"; params.append(eleve_id)
    if classe: sql += " AND e.classe=?"; params.append(classe)
    if statut: sql += " AND p.statut=?"; params.append(statut)
    if annee_scolaire: sql += " AND p.annee_scolaire=?"; params.append(annee_scolaire)
    sql += " ORDER BY p.date_echeance ASC"

    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/paiements/generer', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def generer_paiements():
    body = request.get_json(silent=True) or {}
    eleve_id, annee_scolaire = body.get('eleve_id'), body.get('annee_scolaire')
    if not eleve_id or not annee_scolaire:
        return jsonify({'error': 'Élève et année requis'}), 400

    eleve = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    if not eleve:
        return jsonify({'error': 'Élève introuvable'}), 404

    bareme = db.execute(
        "SELECT * FROM frais_scolarite WHERE classe=? AND annee_scolaire=?", (eleve['classe'], annee_scolaire)
    ).fetchone()
    if not bareme:
        return jsonify({'error': f"Aucun barème pour la classe {eleve['classe']} en {annee_scolaire}"}), 404

    existing = db.execute(
        "SELECT COUNT(*) as c FROM paiements WHERE eleve_id=? AND annee_scolaire=?", (eleve_id, annee_scolaire)
    ).fetchone()['c']
    if existing > 0:
        return jsonify({'error': 'Paiements déjà générés pour cet élève/année'}), 409

    date_debut = body.get('date_debut')
    start = datetime.fromisoformat(date_debut) if date_debut else datetime.now()
    count = 0

    if bareme['frais_inscription'] > 0:
        pid = gen_id('pai')
        db.execute(
            "INSERT INTO paiements (id,eleve_id,annee_scolaire,type_frais,libelle,montant_du,date_echeance) "
            "VALUES (?,?,?,?,?,?,?)",
            (pid, eleve_id, annee_scolaire, 'inscription', "Frais d'inscription",
             bareme['frais_inscription'], start.strftime('%Y-%m-%d')),
        )
        count += 1

    # Répartition des tranches de scolarité : 45% / 40% / 15% du montant annuel
    # (remplace l'ancienne répartition en parts égales)
    POURCENTAGES_TRANCHES = [0.45, 0.40, 0.15]
    nb = len(POURCENTAGES_TRANCHES)
    for i, pct in enumerate(POURCENTAGES_TRANCHES):
        d = start + timedelta(days=i * 91)  # approx. tous les 3 mois
        montant_tranche = round(bareme['scolarite_annuelle'] * pct)
        pid = gen_id('pai') + str(i)
        db.execute(
            "INSERT INTO paiements (id,eleve_id,annee_scolaire,type_frais,libelle,montant_du,date_echeance) "
            "VALUES (?,?,?,?,?,?,?)",
            (pid, eleve_id, annee_scolaire, f'tranche_{i+1}', f'Tranche {i+1} de scolarité ({int(pct*100)}%)',
             montant_tranche, d.strftime('%Y-%m-%d')),
        )
        count += 1

    db.commit()
    return jsonify({'success': True, 'count': count}), 201


@bp.route('/paiements', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def create_paiement():
    body = request.get_json(silent=True) or {}
    eleve_id, montant_du = body.get('eleve_id'), body.get('montant_du')
    if not eleve_id or not montant_du:
        return jsonify({'error': 'Élève et montant requis'}), 400
    pid = gen_id('pai')
    db.execute(
        "INSERT INTO paiements (id,eleve_id,annee_scolaire,type_frais,libelle,montant_du,date_echeance) "
        "VALUES (?,?,?,?,?,?,?)",
        (pid, eleve_id, body.get('annee_scolaire'), body.get('type_frais', 'autre'),
         body.get('libelle', 'Paiement'), montant_du, body.get('date_echeance')),
    )
    db.commit()
    row = db.execute("SELECT * FROM paiements WHERE id=?", (pid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/paiements/<p_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_paiement(p_id):
    db.execute("DELETE FROM paiements WHERE id=?", (p_id,))
    db.commit()
    return jsonify({'success': True})


@bp.route('/paiements/<p_id>/verser', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def verser_paiement(p_id):
    body = request.get_json(silent=True) or {}
    try:
        montant = float(body.get('montant')) if body.get('montant') is not None else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if not montant or montant <= 0:
        return jsonify({'error': 'Montant invalide'}), 400

    pai = db.execute("SELECT * FROM paiements WHERE id=?", (p_id,)).fetchone()
    if not pai:
        return jsonify({'error': 'Paiement introuvable'}), 404

    # Le montant en Franc Guinéen n'a pas de sous-unité utile en pratique : on arrondit
    # systématiquement pour ne jamais laisser un résidu de calcul flottant (ex: 0,33 GNF)
    # bloquer indéfiniment un paiement par ailleurs déjà réglé. Aucune limite maximale
    # n'est imposée : un léger dépassement (arrondi, pourboire, avance) reste acceptable.
    montant = round(montant)

    date_vers = body.get('date_vers') or datetime.now().strftime('%Y-%m-%d')
    moyen_paiement = body.get('moyen_paiement', 'Espèces')

    vid = gen_id('v')
    db.execute(
        "INSERT INTO versements (id,paiement_id,eleve_id,date_vers,montant,moyen_paiement,reference,recu_par) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (vid, p_id, pai['eleve_id'], date_vers, montant, moyen_paiement, body.get('reference'), g.user['id']),
    )
    new_paye = round(pai['montant_paye'] + montant)
    statut = 'paye' if new_paye >= round(pai['montant_du']) - 1 else ('partiel' if new_paye > 0 else 'a_payer')
    db.execute("UPDATE paiements SET montant_paye=?, statut=? WHERE id=?", (new_paye, statut, p_id))

    eleve = db.execute("SELECT nom,prenom,matricule FROM eleves WHERE id=?", (pai['eleve_id'],)).fetchone()
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,type,date_op,description,categorie,moyen_paiement,montant,reference,eleve_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (tid, 'entree', date_vers, f"{pai['libelle']} — {eleve['prenom']} {eleve['nom']} ({eleve['matricule']})",
         "Frais d'inscription" if pai['type_frais'] == 'inscription' else 'Frais de scolarité',
         moyen_paiement, montant, body.get('reference') or f"REC-{vid}", pai['eleve_id']),
    )
    db.commit()

    row = db.execute("SELECT * FROM paiements WHERE id=?", (p_id,)).fetchone()
    log_action(g.user, 'versement', 'paiement', p_id, {'montant': montant, 'eleve_id': pai['eleve_id'], 'moyen_paiement': moyen_paiement})
    return jsonify({'paiement': row_to_dict(row)})


@bp.route('/paiements/solde/<eleve_id>', methods=['GET'])
@require_auth
def solde_paiements(eleve_id):
    row = db.execute(
        """SELECT
           COALESCE(SUM(montant_du),0) as total_du,
           COALESCE(SUM(montant_paye),0) as total_paye,
           COALESCE(SUM(montant_du-montant_paye),0) as reste,
           SUM(CASE WHEN statut='paye' THEN 1 ELSE 0 END) as payees,
           SUM(CASE WHEN statut!='paye' THEN 1 ELSE 0 END) as en_attente
           FROM paiements WHERE eleve_id=?""",
        (eleve_id,),
    ).fetchone()
    result = dict(row)
    for k in ('payees', 'en_attente'):
        result[k] = result[k] or 0
    return jsonify(result)


@bp.route('/paiements/soldes', methods=['GET'])
@require_auth
def soldes_tous():
    rows = db.execute(
        """SELECT e.id, e.matricule, e.nom, e.prenom, e.classe,
           COALESCE(SUM(p.montant_du),0) as total_du, COALESCE(SUM(p.montant_paye),0) as total_paye,
           COALESCE(SUM(p.montant_du-p.montant_paye),0) as reste
           FROM eleves e LEFT JOIN paiements p ON p.eleve_id=e.id
           GROUP BY e.id ORDER BY reste DESC, e.nom"""
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/versements/<eleve_id>', methods=['GET'])
@require_auth
def versements_eleve(eleve_id):
    rows = db.execute(
        """SELECT v.*, p.libelle, u.full_name as recu_par_nom
           FROM versements v LEFT JOIN paiements p ON p.id=v.paiement_id LEFT JOIN users u ON u.id=v.recu_par
           WHERE v.eleve_id=? ORDER BY v.date_vers DESC""",
        (eleve_id,),
    ).fetchall()
    return jsonify(rows_to_list(rows))


# ─────────────────────────────────────────────────────────────
# CANTINE
# ─────────────────────────────────────────────────────────────
@bp.route('/cantine/menus', methods=['GET'])
@require_auth
def list_menus():
    debut, fin = request.args.get('debut'), request.args.get('fin')
    sql = "SELECT * FROM cantine_menus WHERE 1=1"
    params = []
    if debut: sql += " AND date_menu>=?"; params.append(debut)
    if fin: sql += " AND date_menu<=?"; params.append(fin)
    sql += " ORDER BY date_menu DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/cantine/menus', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def create_menu():
    body = request.get_json(silent=True) or {}
    if not body.get('date_menu'):
        return jsonify({'error': 'Date requise'}), 400
    mid = gen_id('menu')
    try:
        db.execute(
            "INSERT INTO cantine_menus (id,date_menu,entree,plat,dessert) VALUES (?,?,?,?,?)",
            (mid, body['date_menu'], body.get('entree'), body.get('plat'), body.get('dessert')),
        )
        db.commit()
    except Exception:
        return jsonify({'error': 'Menu existant pour cette date'}), 409
    row = db.execute("SELECT * FROM cantine_menus WHERE id=?", (mid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/cantine/menus/<m_id>', methods=['PUT'])
@require_auth
@require_role(*FIN_ROLES)
def update_menu(m_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE cantine_menus SET entree=COALESCE(?,entree), plat=COALESCE(?,plat), dessert=COALESCE(?,dessert) WHERE id=?",
        (body.get('entree'), body.get('plat'), body.get('dessert'), m_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM cantine_menus WHERE id=?", (m_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/cantine/menus/<m_id>', methods=['DELETE'])
@require_auth
@require_role(*FIN_ROLES)
def delete_menu(m_id):
    db.execute("DELETE FROM cantine_menus WHERE id=?", (m_id,))
    db.commit()
    return jsonify({'success': True})


@bp.route('/cantine/abonnements', methods=['GET'])
@require_auth
def list_abonnements():
    mois = request.args.get('mois')
    classe = request.args.get('classe')
    paye = request.args.get('paye')

    sql = """SELECT c.*, e.nom, e.prenom, e.classe, e.matricule
             FROM cantine_abonnements c JOIN eleves e ON e.id=c.eleve_id WHERE 1=1"""
    params = []
    if mois: sql += " AND c.mois=?"; params.append(mois)
    if classe: sql += " AND e.classe=?"; params.append(classe)
    if paye not in (None, ''): sql += " AND c.paye=?"; params.append(1 if paye == '1' else 0)
    sql += " ORDER BY c.mois DESC, e.nom"

    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/cantine/abonnements', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def create_abonnement():
    body = request.get_json(silent=True) or {}
    eleve_id, mois = body.get('eleve_id'), body.get('mois')
    if not eleve_id or not mois:
        return jsonify({'error': 'Élève et mois requis'}), 400
    aid = gen_id('abo')
    try:
        db.execute(
            "INSERT INTO cantine_abonnements (id,eleve_id,mois,formule,montant) VALUES (?,?,?,?,?)",
            (aid, eleve_id, mois, body.get('formule', 'complète'), body.get('montant', 0)),
        )
        db.commit()
    except Exception:
        return jsonify({'error': 'Abonnement déjà existant pour cet élève/mois'}), 409
    row = db.execute("SELECT * FROM cantine_abonnements WHERE id=?", (aid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/cantine/abonnements/<a_id>', methods=['PUT'])
@require_auth
@require_role(*FIN_ROLES)
def update_abonnement(a_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE cantine_abonnements SET formule=COALESCE(?,formule), montant=COALESCE(?,montant), "
        "paye=COALESCE(?,paye) WHERE id=?",
        (body.get('formule'), body.get('montant'), (1 if body.get('paye') else 0) if 'paye' in body else None, a_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM cantine_abonnements WHERE id=?", (a_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/cantine/abonnements/<a_id>/payer', methods=['POST'])
@require_auth
@require_role(*FIN_ROLES)
def payer_abonnement(a_id):
    body = request.get_json(silent=True) or {}
    abo = db.execute(
        "SELECT c.*, e.nom, e.prenom, e.matricule FROM cantine_abonnements c "
        "JOIN eleves e ON e.id=c.eleve_id WHERE c.id=?", (a_id,)
    ).fetchone()
    if not abo:
        return jsonify({'error': 'Introuvable'}), 404
    if abo['paye']:
        return jsonify({'error': 'Déjà payé'}), 400

    db.execute("UPDATE cantine_abonnements SET paye=1 WHERE id=?", (a_id,))
    d = body.get('date_vers') or datetime.now().strftime('%Y-%m-%d')
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,type,date_op,description,categorie,moyen_paiement,montant,reference,eleve_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (tid, 'entree', d, f"Cantine {abo['mois']} — {abo['prenom']} {abo['nom']} ({abo['matricule']})",
         'Cantine', body.get('moyen_paiement', 'Espèces'), abo['montant'],
         body.get('reference') or f"CANT-{abo['id']}", abo['eleve_id']),
    )
    db.commit()
    return jsonify({'success': True})


@bp.route('/cantine/abonnements/<a_id>', methods=['DELETE'])
@require_auth
@require_role(*FIN_ROLES)
def delete_abonnement(a_id):
    db.execute("DELETE FROM cantine_abonnements WHERE id=?", (a_id,))
    db.commit()
    return jsonify({'success': True})
