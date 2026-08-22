from datetime import datetime
from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role

bp = Blueprint('revision_routes', __name__, url_prefix='/api/cours-revision')

GESTION_ROLES = ('admin', 'directeur', 'comptable', 'secretaire', 'enseignant')
# L'enseignant peut inscrire des élèves, mais ne doit ni créer/modifier un cours,
# ni gérer les enseignants assignés ou les séances — réservé à la gestion administrative.
GESTION_SANS_ENSEIGNANT = ('admin', 'directeur', 'comptable', 'secretaire')


def _cours_with_stats(cours_id, ecole_id):
    row = db.execute("SELECT * FROM cours_revision WHERE id=? AND ecole_id=?", (cours_id, ecole_id)).fetchone()
    if not row:
        return None
    c = row_to_dict(row)
    stats = db.execute(
        """SELECT COUNT(*) as nb_participants,
           SUM(CASE WHEN est_externe=1 THEN 1 ELSE 0 END) as nb_externes,
           COALESCE(SUM(montant_paye),0) as total_paye
           FROM revision_participants WHERE cours_id=?""", (cours_id,)
    ).fetchone()
    c.update(dict(stats))
    enseignants = db.execute(
        """SELECT ce.*, p.nom, p.prenom FROM cours_revision_enseignants ce
           JOIN personnel p ON p.id=ce.personnel_id WHERE ce.cours_id=?""", (cours_id,)
    ).fetchall()
    c['enseignants'] = rows_to_list(enseignants)
    return c


# ─────────────────────────────────────────────────────────────
# COURS DE RÉVISION
# ─────────────────────────────────────────────────────────────
@bp.route('', methods=['GET'])
@require_auth
def list_cours():
    statut = request.args.get('statut')
    sql = "SELECT * FROM cours_revision WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if statut: sql += " AND statut=?"; params.append(statut)
    sql += " ORDER BY date_debut DESC"
    rows = db.execute(sql, params).fetchall()
    result = []
    for r in rows:
        c = dict(r)
        stats = db.execute(
            """SELECT COUNT(*) as nb_participants, COALESCE(SUM(montant_paye),0) as total_paye
               FROM revision_participants WHERE cours_id=?""", (c['id'],)
        ).fetchone()
        c.update(dict(stats))
        enseignants = db.execute(
            """SELECT p.nom, p.prenom FROM cours_revision_enseignants ce
               JOIN personnel p ON p.id=ce.personnel_id WHERE ce.cours_id=?""", (c['id'],)
        ).fetchall()
        c['noms_enseignants'] = ', '.join(f"{e['prenom']} {e['nom']}" for e in enseignants)
        if g.user['role'] == 'enseignant':
            c.pop('prix', None)
            c.pop('total_paye', None)
        result.append(c)
    return jsonify(result)


@bp.route('/<c_id>', methods=['GET'])
@require_auth
def get_cours(c_id):
    c = _cours_with_stats(c_id, g.user['ecole_id'])
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    if g.user['role'] == 'enseignant':
        c.pop('prix', None)
        c.pop('total_paye', None)
    return jsonify(c)


@bp.route('', methods=['POST'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def create_cours():
    body = request.get_json(silent=True) or {}
    titre = body.get('titre')
    if not titre:
        return jsonify({'error': 'Titre requis'}), 400
    cid = gen_id('rev')
    db.execute(
        "INSERT INTO cours_revision (id,ecole_id,titre,matiere,niveau,description,date_debut,date_fin,prix,capacite_max,salle,duree_seance) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, g.user['ecole_id'], titre, body.get('matiere'), body.get('niveau'), body.get('description'),
         body.get('date_debut'), body.get('date_fin'), body.get('prix', 0), body.get('capacite_max'),
         body.get('salle'), body.get('duree_seance', 1)),
    )
    db.commit()
    log_action(g.user, 'creation', 'cours_revision', cid, {'titre': titre, 'prix': body.get('prix', 0)})
    return jsonify(_cours_with_stats(cid, g.user['ecole_id'])), 201


@bp.route('/<c_id>', methods=['PUT'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def update_cours(c_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        """UPDATE cours_revision SET titre=COALESCE(?,titre), matiere=COALESCE(?,matiere),
           niveau=COALESCE(?,niveau), description=COALESCE(?,description),
           date_debut=COALESCE(?,date_debut), date_fin=COALESCE(?,date_fin),
           prix=COALESCE(?,prix), capacite_max=COALESCE(?,capacite_max), statut=COALESCE(?,statut),
           salle=COALESCE(?,salle), duree_seance=COALESCE(?,duree_seance)
           WHERE id=? AND ecole_id=?""",
        (body.get('titre'), body.get('matiere'), body.get('niveau'), body.get('description'),
         body.get('date_debut'), body.get('date_fin'), body.get('prix'), body.get('capacite_max'),
         body.get('statut'), body.get('salle'), body.get('duree_seance'), c_id, g.user['ecole_id']),
    )
    db.commit()
    log_action(g.user, 'modification', 'cours_revision', c_id, {'motif': body.get('motif'), **body})
    return jsonify(_cours_with_stats(c_id, g.user['ecole_id']))


@bp.route('/<c_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_cours(c_id):
    c = db.execute("SELECT * FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'cours_revision', c_id, {'titre': c['titre']})
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# PARTICIPANTS (élèves internes OU externes d'autres écoles)
# ─────────────────────────────────────────────────────────────
@bp.route('/<c_id>/participants', methods=['GET'])
@require_auth
def list_participants(c_id):
    if not db.execute("SELECT id FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Cours introuvable'}), 404
    rows = db.execute(
        """SELECT p.*,
           (SELECT COUNT(*) FROM revision_evaluations e WHERE e.participant_id=p.id) as nb_evaluations
           FROM revision_participants p WHERE p.cours_id=? ORDER BY p.nom, p.prenom""", (c_id,)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/<c_id>/participants', methods=['POST'])
@require_auth
@require_role(*GESTION_ROLES)
def add_participant(c_id):
    body = request.get_json(silent=True) or {}
    cours = db.execute("SELECT * FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not cours:
        return jsonify({'error': 'Cours introuvable'}), 404

    eleve_id = body.get('eleve_id')
    nom, prenom = body.get('nom'), body.get('prenom')

    # Si un élève interne est sélectionné, on récupère son nom/prénom automatiquement
    if eleve_id:
        eleve = db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
        if not eleve:
            return jsonify({'error': 'Élève introuvable'}), 404
        nom, prenom = eleve['nom'], eleve['prenom']
        est_externe = 0
        ecole_origine = 'Interne (élève de notre école)'
    else:
        if not nom or not prenom:
            return jsonify({'error': 'Nom et prénom requis pour un participant externe'}), 400
        est_externe = 1
        ecole_origine = body.get('ecole_origine') or 'Externe (non précisé)'

    # Vérifier la capacité maximale si définie
    if cours['capacite_max']:
        nb_actuel = db.execute("SELECT COUNT(*) as c FROM revision_participants WHERE cours_id=?", (c_id,)).fetchone()['c']
        if nb_actuel >= cours['capacite_max']:
            return jsonify({'error': f"Capacité maximale atteinte ({cours['capacite_max']} places)"}), 409

    pid = gen_id('rp')
    db.execute(
        "INSERT INTO revision_participants (id,ecole_id,cours_id,eleve_id,nom,prenom,telephone,ecole_origine,est_externe) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pid, g.user['ecole_id'], c_id, eleve_id, nom, prenom, body.get('telephone'), ecole_origine, est_externe),
    )
    db.commit()
    log_action(g.user, 'inscription', 'cours_revision', c_id,
               {'participant': f"{prenom} {nom}", 'externe': bool(est_externe), 'ecole_origine': ecole_origine})
    row = db.execute("SELECT * FROM revision_participants WHERE id=?", (pid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/participants/<p_id>', methods=['DELETE'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def delete_participant(p_id):
    db.execute("DELETE FROM revision_participants WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/participants/<p_id>/payer', methods=['POST'])
@require_auth
@require_role('admin', 'comptable')
def payer_participant(p_id):
    body = request.get_json(silent=True) or {}
    try:
        montant = float(body.get('montant')) if body.get('montant') is not None else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Montant invalide'}), 400
    if not montant or montant <= 0:
        return jsonify({'error': 'Montant invalide'}), 400

    p = db.execute(
        """SELECT rp.*, c.titre as cours_titre, c.prix as prix_cours
           FROM revision_participants rp JOIN cours_revision c ON c.id=rp.cours_id WHERE rp.id=? AND rp.ecole_id=?""", (p_id, g.user['ecole_id'])
    ).fetchone()
    if not p:
        return jsonify({'error': 'Participant introuvable'}), 404

    # Le cours de révision est un forfait MENSUEL RÉCURRENT (pas un montant dû unique) :
    # un participant règle le même montant chaque mois, donc le cumul versé peut librement
    # dépasser le prix d'un seul mois — aucune limite maximale n'est imposée ici.
    prix = p['prix_cours'] or 0

    new_paye = p['montant_paye'] + montant
    statut = 'paye' if prix > 0 and new_paye >= prix - 0.01 else ('partiel' if new_paye > 0 else 'impaye')
    db.execute("UPDATE revision_participants SET montant_paye=?, statut_paiement=? WHERE id=?", (new_paye, statut, p_id))

    # Créer automatiquement une transaction comptable (recette — toujours auto-approuvée)
    date_vers = body.get('date_vers') or datetime.now().strftime('%Y-%m-%d')
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,ecole_id,type,date_op,description,categorie,moyen_paiement,montant,reference,eleve_id,cree_par,statut_validation) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, g.user['ecole_id'], 'entree', date_vers, f"Cours de révision « {p['cours_titre']} » — {p['prenom']} {p['nom']}",
         'Cours de révision', body.get('moyen_paiement', 'Espèces'), montant,
         body.get('reference') or f"REV-{p_id}", p['eleve_id'], g.user['id'], 'auto'),
    )
    db.commit()
    log_action(g.user, 'versement', 'cours_revision', p_id, {'montant': montant, 'participant': f"{p['prenom']} {p['nom']}"})
    row = db.execute("SELECT * FROM revision_participants WHERE id=?", (p_id,)).fetchone()
    return jsonify(row_to_dict(row))


# ─────────────────────────────────────────────────────────────
# ÉVALUATIONS — chaque participant doit être évalué
# ─────────────────────────────────────────────────────────────
@bp.route('/participants/<p_id>/evaluations', methods=['GET'])
@require_auth
def list_evaluations(p_id):
    if not db.execute("SELECT id FROM revision_participants WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Participant introuvable'}), 404
    rows = db.execute(
        """SELECT e.*, u.full_name as evaluateur_nom FROM revision_evaluations e
           LEFT JOIN users u ON u.id=e.evaluateur_id WHERE e.participant_id=? ORDER BY e.date_evaluation DESC""",
        (p_id,)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/participants/<p_id>/evaluations', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def create_evaluation(p_id):
    body = request.get_json(silent=True) or {}
    p = db.execute("SELECT * FROM revision_participants WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Participant introuvable'}), 404
    date_evaluation = body.get('date_evaluation') or datetime.now().strftime('%Y-%m-%d')
    eid = gen_id('reval')
    db.execute(
        "INSERT INTO revision_evaluations (id,ecole_id,participant_id,date_evaluation,note,note_max,appreciation,evaluateur_id) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (eid, g.user['ecole_id'], p_id, date_evaluation, body.get('note'), body.get('note_max', 20), body.get('appreciation'), g.user['id']),
    )
    db.commit()
    log_action(g.user, 'evaluation', 'cours_revision', p_id,
               {'participant': f"{p['prenom']} {p['nom']}", 'note': body.get('note')})
    row = db.execute("SELECT * FROM revision_evaluations WHERE id=?", (eid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/evaluations/<e_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def delete_evaluation(e_id):
    db.execute("DELETE FROM revision_evaluations WHERE id=? AND ecole_id=?", (e_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# ENSEIGNANTS ASSIGNÉS AU COURS (point : sélectionner enseignants + matière)
# ─────────────────────────────────────────────────────────────
@bp.route('/<c_id>/enseignants', methods=['GET'])
@require_auth
def list_enseignants_cours(c_id):
    if not db.execute("SELECT id FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Cours introuvable'}), 404
    rows = db.execute(
        """SELECT ce.*, p.nom, p.prenom, p.telephone FROM cours_revision_enseignants ce
           JOIN personnel p ON p.id=ce.personnel_id WHERE ce.cours_id=? ORDER BY p.nom""", (c_id,)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/<c_id>/enseignants', methods=['POST'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def assigner_enseignant(c_id):
    body = request.get_json(silent=True) or {}
    personnel_id = body.get('personnel_id')
    if not personnel_id:
        return jsonify({'error': 'Enseignant requis'}), 400
    if not db.execute("SELECT id FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Cours introuvable'}), 404
    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Enseignant introuvable'}), 404
    ceid = gen_id('ce')
    try:
        db.execute(
            "INSERT INTO cours_revision_enseignants (id,ecole_id,cours_id,personnel_id,matiere,jour,creneau) VALUES (?,?,?,?,?,?,?)",
            (ceid, g.user['ecole_id'], c_id, personnel_id, body.get('matiere'), body.get('jour'), body.get('creneau')))
        db.commit()
    except Exception:
        return jsonify({'error': 'Cet enseignant est déjà assigné à ce cours'}), 409
    log_action(g.user, 'assignation', 'cours_revision', c_id,
               {'enseignant': f"{p['prenom']} {p['nom']}", 'matiere': body.get('matiere'),
                'jour': body.get('jour'), 'creneau': body.get('creneau')})
    row = db.execute(
        "SELECT ce.*, p.nom, p.prenom FROM cours_revision_enseignants ce JOIN personnel p ON p.id=ce.personnel_id WHERE ce.id=?",
        (ceid,)
    ).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/enseignants/<ce_id>', methods=['DELETE'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def retirer_enseignant(ce_id):
    db.execute("DELETE FROM cours_revision_enseignants WHERE id=? AND ecole_id=?", (ce_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# SÉANCES ENSEIGNÉES (base du calcul de redistribution)
# ─────────────────────────────────────────────────────────────
@bp.route('/<c_id>/seances', methods=['GET'])
@require_auth
def list_seances(c_id):
    if not db.execute("SELECT id FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Cours introuvable'}), 404
    rows = db.execute(
        """SELECT rs.*, p.nom, p.prenom FROM revision_seances rs
           JOIN personnel p ON p.id=rs.personnel_id WHERE rs.cours_id=? ORDER BY rs.date_seance DESC""", (c_id,)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/<c_id>/seances', methods=['POST'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def enregistrer_seance(c_id):
    body = request.get_json(silent=True) or {}
    personnel_id = body.get('personnel_id')
    date_seance = body.get('date_seance')
    if not personnel_id or not date_seance:
        return jsonify({'error': 'Enseignant et date requis'}), 400
    cours = db.execute("SELECT * FROM cours_revision WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not cours:
        return jsonify({'error': 'Cours introuvable'}), 404
    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Enseignant introuvable'}), 404
    sid = gen_id('rs')
    duree = body.get('duree_heures', cours['duree_seance'] or 1)
    db.execute(
        "INSERT INTO revision_seances (id,ecole_id,cours_id,personnel_id,date_seance,duree_heures) VALUES (?,?,?,?,?,?)",
        (sid, g.user['ecole_id'], c_id, personnel_id, date_seance, duree),
    )
    db.commit()
    log_action(g.user, 'seance_enseignee', 'cours_revision', c_id,
               {'enseignant': f"{p['prenom']} {p['nom']}", 'date': date_seance, 'duree_heures': duree})
    row = db.execute("SELECT * FROM revision_seances WHERE id=?", (sid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/seances/<s_id>', methods=['DELETE'])
@require_auth
@require_role(*GESTION_SANS_ENSEIGNANT)
def delete_seance(s_id):
    db.execute("DELETE FROM revision_seances WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# REDISTRIBUTION MENSUELLE — 60% des recettes aux enseignants (au prorata des heures)
# ─────────────────────────────────────────────────────────────
@bp.route('/redistribution', methods=['GET'])
@require_auth
@require_role('admin', 'directeur', 'comptable')
def calculer_redistribution():
    """Calcule, pour un mois donné, la part de 60% des recettes de cours de révision
    à redistribuer à chaque enseignant, au prorata des heures de séances assurées."""
    mois = request.args.get('mois')
    if not mois:
        return jsonify({'error': 'Mois requis (format AAAA-MM)'}), 400

    total_recettes = db.execute(
        """SELECT COALESCE(SUM(montant),0) as s FROM transactions
           WHERE ecole_id=? AND type='entree' AND categorie='Cours de révision' AND statut_validation IN ('auto','valide')
           AND strftime('%Y-%m',date_op)=?""", (g.user['ecole_id'], mois)
    ).fetchone()['s']
    pool_60pct = round(total_recettes * 0.60)

    heures_par_enseignant = rows_to_list(db.execute(
        """SELECT rs.personnel_id, p.nom, p.prenom, p.taux_horaire,
           SUM(rs.duree_heures) as total_heures,
           SUM(CASE WHEN rs.redistribue=1 THEN rs.duree_heures ELSE 0 END) as heures_deja_payees
           FROM revision_seances rs JOIN personnel p ON p.id=rs.personnel_id
           WHERE rs.ecole_id=? AND strftime('%Y-%m',rs.date_seance)=?
           GROUP BY rs.personnel_id ORDER BY p.nom""", (g.user['ecole_id'], mois)
    ).fetchall())

    total_heures_mois = sum(h['total_heures'] for h in heures_par_enseignant)

    for h in heures_par_enseignant:
        h['heures_non_payees'] = h['total_heures'] - h['heures_deja_payees']
        h['part'] = round(pool_60pct * (h['total_heures'] / total_heures_mois)) if total_heures_mois > 0 else 0
        # Montant restant à verser = part totale au prorata des heures NON encore redistribuées
        h['montant_a_verser'] = round(h['part'] * (h['heures_non_payees'] / h['total_heures'])) if h['total_heures'] > 0 else 0

    return jsonify({
        'mois': mois,
        'total_recettes': total_recettes,
        'pool_60pct': pool_60pct,
        'total_heures': total_heures_mois,
        'enseignants': heures_par_enseignant,
    })


@bp.route('/redistribution/verser', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'comptable')
def verser_redistribution():
    """Marque la redistribution du mois comme versée pour un enseignant donné :
    crée la transaction de dépense correspondante et marque les séances comme redistribuées."""
    body = request.get_json(silent=True) or {}
    personnel_id = body.get('personnel_id')
    mois = body.get('mois')
    montant = body.get('montant')
    if not personnel_id or not mois or not montant:
        return jsonify({'error': 'Enseignant, mois et montant requis'}), 400

    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Enseignant introuvable'}), 404

    date_vers = body.get('date_vers') or datetime.now().strftime('%Y-%m-%d')
    tid = gen_id('t')
    db.execute(
        "INSERT INTO transactions (id,ecole_id,type,date_op,description,categorie,moyen_paiement,montant,reference,cree_par,statut_validation) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tid, g.user['ecole_id'], 'sortie', date_vers, f"Redistribution cours de révision ({mois}) — {p['prenom']} {p['nom']}",
         'Redistribution cours de révision', body.get('moyen_paiement', 'Espèces'), montant,
         f"REDIST-{personnel_id}-{mois}", g.user['id'], 'auto'),
    )
    db.execute(
        "UPDATE revision_seances SET redistribue=1 WHERE personnel_id=? AND ecole_id=? AND strftime('%Y-%m',date_seance)=?",
        (personnel_id, g.user['ecole_id'], mois),
    )
    db.commit()
    log_action(g.user, 'redistribution_versee', 'cours_revision', personnel_id,
               {'mois': mois, 'montant': montant, 'enseignant': f"{p['prenom']} {p['nom']}"})
    return jsonify({'success': True, 'transaction_id': tid})
