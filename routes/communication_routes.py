from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict
from auth import require_auth, require_role

bp = Blueprint('communication_routes', __name__, url_prefix='/api')


# ─────────────────────────────────────────────────────────────
# ANNONCES
# ─────────────────────────────────────────────────────────────
@bp.route('/annonces', methods=['GET'])
@require_auth
def list_annonces():
    rows = db.execute(
        "SELECT a.*, u.full_name as auteur_nom FROM annonces a LEFT JOIN users u ON u.id=a.auteur_id "
        "ORDER BY a.date_publication DESC LIMIT 100"
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/annonces', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'charge_communication')
def create_annonce():
    body = request.get_json(silent=True) or {}
    titre, contenu = body.get('titre'), body.get('contenu')
    if not titre or not contenu:
        return jsonify({'error': 'Titre et contenu requis'}), 400
    aid = gen_id('ann')
    db.execute(
        "INSERT INTO annonces (id,auteur_id,titre,contenu,cible) VALUES (?,?,?,?,?)",
        (aid, g.user['id'], titre, contenu, body.get('cible', 'tous')),
    )
    db.commit()
    row = db.execute(
        "SELECT a.*, u.full_name as auteur_nom FROM annonces a LEFT JOIN users u ON u.id=a.auteur_id WHERE a.id=?",
        (aid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/annonces/<a_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'charge_communication')
def update_annonce(a_id):
    body = request.get_json(silent=True) or {}
    a = db.execute("SELECT * FROM annonces WHERE id=?", (a_id,)).fetchone()
    if not a:
        return jsonify({'error': 'Introuvable'}), 404
    if a['auteur_id'] != g.user['id'] and g.user['role'] != 'admin':
        return jsonify({'error': 'Accès refusé'}), 403
    db.execute(
        "UPDATE annonces SET titre=COALESCE(?,titre), contenu=COALESCE(?,contenu), cible=COALESCE(?,cible) WHERE id=?",
        (body.get('titre'), body.get('contenu'), body.get('cible'), a_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM annonces WHERE id=?", (a_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/annonces/<a_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'charge_communication')
def delete_annonce(a_id):
    a = db.execute("SELECT * FROM annonces WHERE id=?", (a_id,)).fetchone()
    if not a:
        return jsonify({'error': 'Introuvable'}), 404
    if a['auteur_id'] != g.user['id'] and g.user['role'] != 'admin':
        return jsonify({'error': 'Accès refusé'}), 403
    db.execute("DELETE FROM annonces WHERE id=?", (a_id,))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────────────────
@bp.route('/messages', methods=['GET'])
@require_auth
def list_messages():
    destinataire_type = request.args.get('destinataire_type')
    destinataire_id = request.args.get('destinataire_id')
    sql = "SELECT m.*, u.full_name as expediteur_nom FROM messages m LEFT JOIN users u ON u.id=m.expediteur_id WHERE 1=1"
    params = []
    if destinataire_type: sql += " AND m.destinataire_type=?"; params.append(destinataire_type)
    if destinataire_id: sql += " AND m.destinataire_id=?"; params.append(destinataire_id)
    sql += " ORDER BY m.date_envoi DESC LIMIT 200"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/messages', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'charge_communication')
def create_message():
    body = request.get_json(silent=True) or {}
    destinataire_type, contenu = body.get('destinataire_type'), body.get('contenu')
    if not destinataire_type or not contenu:
        return jsonify({'error': 'Destinataire et contenu requis'}), 400
    mid = gen_id('msg')
    db.execute(
        "INSERT INTO messages (id,expediteur_id,destinataire_type,destinataire_id,sujet,contenu) VALUES (?,?,?,?,?,?)",
        (mid, g.user['id'], destinataire_type, body.get('destinataire_id'), body.get('sujet'), contenu),
    )
    db.commit()
    row = db.execute(
        "SELECT m.*, u.full_name as expediteur_nom FROM messages m LEFT JOIN users u ON u.id=m.expediteur_id WHERE m.id=?",
        (mid,),
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/messages/<m_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'charge_communication')
def delete_message(m_id):
    db.execute("DELETE FROM messages WHERE id=?", (m_id,))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@bp.route('/dashboard', methods=['GET'])
@require_auth
def dashboard():
    def scalar(sql, params=()):
        row = db.execute(sql, params).fetchone()
        return list(row)[0] if row else 0

    stats = {
        'eleves': scalar("SELECT COUNT(*) FROM eleves WHERE statut='actif'"),
        'eleves_filles': scalar("SELECT COUNT(*) FROM eleves WHERE statut='actif' AND sexe='F'"),
        'personnel': scalar("SELECT COUNT(*) FROM personnel"),
        'recettes': scalar("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE type='entree' AND statut_validation IN ('auto','valide')"),
        'depenses': scalar("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE type='sortie' AND statut_validation IN ('auto','valide')"),
        'salaires_verses': scalar("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE type='sortie' AND categorie='Salaires' AND statut_validation IN ('auto','valide')"),
        'absences_jour': scalar("SELECT COUNT(*) FROM absences WHERE date_abs=date('now') AND type='absence'"),
        'impayes': scalar("SELECT COALESCE(SUM(montant_du-montant_paye),0) FROM paiements WHERE statut!='paye'"),
        'eleves_avec_impayes': scalar("SELECT COUNT(DISTINCT eleve_id) FROM paiements WHERE statut!='paye'"),
        'devoirs_actifs': scalar("SELECT COUNT(*) FROM devoirs WHERE statut='En cours'"),
        'reinsc_attente': scalar("SELECT COUNT(*) FROM reinscriptions WHERE statut='en_attente'"),
        'depenses_en_attente': scalar("SELECT COUNT(*) FROM transactions WHERE statut_validation IN ('attente_directeur','attente_admin')"),
        'montant_en_attente': scalar("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE statut_validation IN ('attente_directeur','attente_admin')"),
        'total_du_scolarite': scalar("SELECT COALESCE(SUM(montant_du),0) FROM paiements"),
        'total_paye_scolarite': scalar("SELECT COALESCE(SUM(montant_paye),0) FROM paiements"),
    }
    stats['depenses_hors_salaires'] = stats['depenses'] - stats['salaires_verses']
    stats['solde'] = stats['recettes'] - stats['depenses']
    stats['solde_caisse'] = stats['recettes'] - stats['salaires_verses'] - stats['depenses_hors_salaires']
    stats['taux_recouvrement'] = round((stats['total_paye_scolarite'] / stats['total_du_scolarite'] * 100), 1) if stats['total_du_scolarite'] > 0 else 0.0

    recouvrement_par_classe = rows_to_list(db.execute(
        """SELECT e.classe,
           COUNT(DISTINCT e.id) as nb_eleves,
           COALESCE(SUM(pp.montant_du),0) as montant_du,
           COALESCE(SUM(pp.montant_paye),0) as montant_paye
           FROM eleves e
           LEFT JOIN paiements pp ON pp.eleve_id = e.id
           WHERE e.statut='actif' AND e.classe IS NOT NULL
           GROUP BY e.classe ORDER BY e.classe"""
    ).fetchall())
    for r in recouvrement_par_classe:
        r['montant_reste'] = r['montant_du'] - r['montant_paye']

    recettes_par_categorie = rows_to_list(db.execute(
        """SELECT COALESCE(categorie,'Non catégorisé') as categorie, COALESCE(SUM(montant),0) as montant
           FROM transactions WHERE type='entree' AND statut_validation IN ('auto','valide')
           GROUP BY categorie ORDER BY montant DESC"""
    ).fetchall())

    eleves_impayes_liste = rows_to_list(db.execute(
        """SELECT e.id, e.nom, e.prenom, e.classe, e.matricule,
           SUM(p.montant_du-p.montant_paye) as reste
           FROM eleves e JOIN paiements p ON p.eleve_id=e.id
           WHERE p.statut!='paye'
           GROUP BY e.id ORDER BY reste DESC LIMIT 10"""
    ).fetchall())

    finances_mois = rows_to_list(db.execute(
        """SELECT strftime('%Y-%m',date_op) as mois,
           SUM(CASE WHEN type='entree' THEN montant ELSE 0 END) as recettes,
           SUM(CASE WHEN type='sortie' THEN montant ELSE 0 END) as depenses
           FROM transactions WHERE date_op >= date('now','-12 months') AND statut_validation IN ('auto','valide')
           GROUP BY strftime('%Y-%m',date_op) ORDER BY mois"""
    ).fetchall())

    eleves_classe = rows_to_list(db.execute(
        "SELECT classe, COUNT(*) as n FROM eleves WHERE statut='actif' AND classe IS NOT NULL "
        "GROUP BY classe ORDER BY classe"
    ).fetchall())

    dernieres_transactions = rows_to_list(db.execute(
        "SELECT * FROM transactions ORDER BY date_op DESC, created_at DESC LIMIT 5"
    ).fetchall())

    prochains_devoirs = rows_to_list(db.execute(
        "SELECT * FROM devoirs WHERE statut='En cours' AND date_remise>=date('now') ORDER BY date_remise LIMIT 5"
    ).fetchall())

    dernieres_annonces = rows_to_list(db.execute(
        "SELECT a.*, u.full_name as auteur_nom FROM annonces a LEFT JOIN users u ON u.id=a.auteur_id "
        "ORDER BY a.date_publication DESC LIMIT 3"
    ).fetchall())

    personnel_absent_jour = rows_to_list(db.execute(
        """SELECT ap.*, p.nom, p.prenom, p.poste, p.matiere
           FROM absences_personnel ap JOIN personnel p ON p.id=ap.personnel_id
           WHERE date(ap.date_debut) <= date('now') AND (ap.date_fin IS NULL OR date(ap.date_fin) >= date('now'))
           ORDER BY p.nom"""
    ).fetchall())
    stats['personnel_absent_jour'] = len(personnel_absent_jour)

    result = {
        'stats': stats,
        'finances_mois': finances_mois,
        'eleves_classe': eleves_classe,
        'dernieres_transactions': dernieres_transactions,
        'prochains_devoirs': prochains_devoirs,
        'dernieres_annonces': dernieres_annonces,
        'personnel_absent_jour': personnel_absent_jour,
        'recouvrement_par_classe': recouvrement_par_classe,
        'recettes_par_categorie': recettes_par_categorie,
        'eleves_impayes_liste': eleves_impayes_liste,
    }

    # Un enseignant ne doit jamais voir la situation financière de l'école,
    # même en interrogeant directement l'API — le filtrage se fait ici côté serveur.
    if g.user['role'] == 'enseignant':
        champs_financiers_stats = [
            'recettes', 'depenses', 'salaires_verses', 'impayes', 'eleves_avec_impayes',
            'depenses_en_attente', 'montant_en_attente', 'total_du_scolarite',
            'total_paye_scolarite', 'depenses_hors_salaires', 'solde', 'solde_caisse',
            'taux_recouvrement',
        ]
        for champ in champs_financiers_stats:
            result['stats'].pop(champ, None)
        for cle in ('finances_mois', 'dernieres_transactions', 'recouvrement_par_classe',
                    'recettes_par_categorie', 'eleves_impayes_liste'):
            result[cle] = []

    return jsonify(result)
