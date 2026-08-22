import os
import time
import random
from flask import Blueprint, request, jsonify, g, current_app

from database import db, gen_id, rows_to_list, row_to_dict, log_action, get_classes_enseignant, next_matricule_personnel, matricule_lock
from auth import require_auth, require_role

bp = Blueprint('scolarite_routes', __name__, url_prefix='/api')

# ─────────────────────────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────────────────────────
@bp.route('/notes', methods=['GET'])
@require_auth
def list_notes():
    eleve_id = request.args.get('eleve_id')
    classe = request.args.get('classe')
    matiere = request.args.get('matiere')
    trimestre = request.args.get('trimestre')

    sql = """SELECT n.*, e.nom, e.prenom, e.classe, e.matricule
             FROM notes n JOIN eleves e ON e.id=n.eleve_id WHERE n.ecole_id=?"""
    params = [g.user['ecole_id']]

    if g.user['role'] == 'enseignant':
        mes_classes = get_classes_enseignant(g.user['id'])
        if not mes_classes:
            return jsonify([])
        sql += f" AND e.classe IN ({','.join(['?']*len(mes_classes))})"
        params += mes_classes

    if g.user['role'] == 'parent':
        mes_enfants = [r['eleve_id'] for r in db.execute(
            "SELECT eleve_id FROM parents_eleves WHERE user_id=?", (g.user['id'],)).fetchall()]
        if not mes_enfants:
            return jsonify([])
        if eleve_id and eleve_id not in mes_enfants:
            return jsonify({'error': "Accès refusé à cet élève"}), 403
        sql += f" AND n.eleve_id IN ({','.join(['?']*len(mes_enfants))})"
        params += mes_enfants

    if eleve_id: sql += " AND n.eleve_id=?"; params.append(eleve_id)
    if classe: sql += " AND e.classe=?"; params.append(classe)
    if matiere: sql += " AND n.matiere=?"; params.append(matiere)
    if trimestre: sql += " AND n.trimestre=?"; params.append(trimestre)
    sql += " ORDER BY e.nom, n.matiere"

    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/notes', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def create_note():
    body = request.get_json(silent=True) or {}
    eleve_id, matiere, trimestre = body.get('eleve_id'), body.get('matiere'), body.get('trimestre')
    if not eleve_id or not matiere or not trimestre:
        return jsonify({'error': 'Champs requis'}), 400
    nid = gen_id('n')
    db.execute(
        "INSERT INTO notes (id,ecole_id,eleve_id,matiere,trimestre,type,note,note_max,date_note) VALUES (?,?,?,?,?,?,?,?,?)",
        (nid, g.user['ecole_id'], eleve_id, matiere, trimestre, body.get('type'), body.get('note'),
         body.get('note_max', 20), body.get('date_note')),
    )
    db.commit()
    row = db.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/notes/<note_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def update_note(note_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE notes SET note=COALESCE(?,note), note_max=COALESCE(?,note_max), "
        "type=COALESCE(?,type), date_note=COALESCE(?,date_note) WHERE id=? AND ecole_id=?",
        (body.get('note'), body.get('note_max'), body.get('type'), body.get('date_note'), note_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/notes/<note_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def delete_note(note_id):
    db.execute("DELETE FROM notes WHERE id=? AND ecole_id=?", (note_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# DEVOIRS
# ─────────────────────────────────────────────────────────────
@bp.route('/devoirs', methods=['GET'])
@require_auth
def list_devoirs():
    classe, statut = request.args.get('classe'), request.args.get('statut')
    sql = "SELECT * FROM devoirs WHERE ecole_id=?"
    params = [g.user['ecole_id']]

    if g.user['role'] == 'enseignant':
        mes_classes = get_classes_enseignant(g.user['id'])
        if not mes_classes:
            return jsonify([])
        sql += f" AND classe IN ({','.join(['?']*len(mes_classes))})"
        params += mes_classes

    if g.user['role'] == 'parent':
        classes_enfants = [r['classe'] for r in db.execute(
            """SELECT DISTINCT e.classe FROM parents_eleves pe JOIN eleves e ON e.id=pe.eleve_id
               WHERE pe.user_id=? AND e.classe IS NOT NULL""", (g.user['id'],)).fetchall()]
        if not classes_enfants:
            return jsonify([])
        sql += f" AND classe IN ({','.join(['?']*len(classes_enfants))})"
        params += classes_enfants

    if classe: sql += " AND classe=?"; params.append(classe)
    if statut: sql += " AND statut=?"; params.append(statut)
    sql += " ORDER BY date_remise ASC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/devoirs', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def create_devoir():
    body = request.get_json(silent=True) or {}
    if not body.get('titre'):
        return jsonify({'error': 'Titre requis'}), 400
    did = gen_id('d')
    db.execute(
        "INSERT INTO devoirs (id,ecole_id,titre,matiere,classe,professeur_id,date_assignation,date_remise,description,statut) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (did, g.user['ecole_id'], body['titre'], body.get('matiere'), body.get('classe'), body.get('professeur_id'),
         body.get('date_assignation'), body.get('date_remise'), body.get('description'),
         body.get('statut', 'En cours')),
    )
    db.commit()
    row = db.execute("SELECT * FROM devoirs WHERE id=?", (did,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/devoirs/<devoir_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def update_devoir(devoir_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE devoirs SET titre=COALESCE(?,titre), matiere=COALESCE(?,matiere), "
        "classe=COALESCE(?,classe), date_remise=COALESCE(?,date_remise), "
        "description=COALESCE(?,description), statut=COALESCE(?,statut) WHERE id=? AND ecole_id=?",
        (body.get('titre'), body.get('matiere'), body.get('classe'), body.get('date_remise'),
         body.get('description'), body.get('statut'), devoir_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM devoirs WHERE id=?", (devoir_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/devoirs/<devoir_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'enseignant')
def delete_devoir(devoir_id):
    db.execute("DELETE FROM devoirs WHERE id=? AND ecole_id=?", (devoir_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# EMPLOI DU TEMPS
# ─────────────────────────────────────────────────────────────
@bp.route('/emploi-du-temps', methods=['GET'])
@require_auth
def list_edt():
    classe = request.args.get('classe')
    professeur_id = request.args.get('professeur_id')
    sql = "SELECT * FROM emploi_du_temps WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if classe: sql += " AND classe=?"; params.append(classe)
    if professeur_id: sql += " AND professeur_id=?"; params.append(professeur_id)
    sql += " ORDER BY jour, creneau"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/emploi-du-temps', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def create_edt():
    body = request.get_json(silent=True) or {}
    jour, creneau, classe = body.get('jour'), body.get('creneau'), body.get('classe')
    if not jour or not creneau or not classe:
        return jsonify({'error': 'Jour, créneau, classe requis'}), 400
    conflict = db.execute(
        "SELECT id FROM emploi_du_temps WHERE ecole_id=? AND jour=? AND creneau=? AND classe=?", (g.user['ecole_id'], jour, creneau, classe)
    ).fetchone()
    if conflict:
        return jsonify({'error': 'Conflit : ce créneau est déjà occupé pour cette classe'}), 409
    eid = gen_id('edt')
    db.execute(
        "INSERT INTO emploi_du_temps (id,ecole_id,jour,creneau,classe,matiere,professeur_id,salle) VALUES (?,?,?,?,?,?,?,?)",
        (eid, g.user['ecole_id'], jour, creneau, classe, body.get('matiere'), body.get('professeur_id'), body.get('salle')),
    )
    db.commit()
    row = db.execute("SELECT * FROM emploi_du_temps WHERE id=?", (eid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/emploi-du-temps/<edt_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def update_edt(edt_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE emploi_du_temps SET matiere=COALESCE(?,matiere), professeur_id=COALESCE(?,professeur_id), "
        "salle=COALESCE(?,salle) WHERE id=? AND ecole_id=?",
        (body.get('matiere'), body.get('professeur_id'), body.get('salle'), edt_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM emploi_du_temps WHERE id=? AND ecole_id=?", (edt_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/emploi-du-temps/<edt_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_edt(edt_id):
    db.execute("DELETE FROM emploi_du_temps WHERE id=? AND ecole_id=?", (edt_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# ABSENCES
# ─────────────────────────────────────────────────────────────
@bp.route('/absences', methods=['GET'])
@require_auth
def list_absences():
    eleve_id = request.args.get('eleve_id')
    classe = request.args.get('classe')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')

    sql = """SELECT a.*, e.nom, e.prenom, e.classe, e.matricule
             FROM absences a JOIN eleves e ON e.id=a.eleve_id WHERE a.ecole_id=?"""
    params = [g.user['ecole_id']]

    if g.user['role'] == 'enseignant':
        mes_classes = get_classes_enseignant(g.user['id'])
        if not mes_classes:
            return jsonify([])
        sql += f" AND e.classe IN ({','.join(['?']*len(mes_classes))})"
        params += mes_classes

    if g.user['role'] == 'parent':
        mes_enfants = [r['eleve_id'] for r in db.execute(
            "SELECT eleve_id FROM parents_eleves WHERE user_id=?", (g.user['id'],)).fetchall()]
        if not mes_enfants:
            return jsonify([])
        if eleve_id and eleve_id not in mes_enfants:
            return jsonify({'error': "Accès refusé à cet élève"}), 403
        sql += f" AND a.eleve_id IN ({','.join(['?']*len(mes_enfants))})"
        params += mes_enfants

    if eleve_id: sql += " AND a.eleve_id=?"; params.append(eleve_id)
    if classe: sql += " AND e.classe=?"; params.append(classe)
    if date_debut: sql += " AND a.date_abs>=?"; params.append(date_debut)
    if date_fin: sql += " AND a.date_abs<=?"; params.append(date_fin)
    sql += " ORDER BY a.date_abs DESC"

    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/absences/stats/<eleve_id>', methods=['GET'])
@require_auth
def stats_absences(eleve_id):
    row = db.execute(
        """SELECT
           SUM(CASE WHEN type='absence' THEN 1 ELSE 0 END) as total_absences,
           SUM(CASE WHEN type='retard' THEN 1 ELSE 0 END) as total_retards,
           SUM(CASE WHEN type='absence' AND justifie=1 THEN 1 ELSE 0 END) as justifiees,
           SUM(CASE WHEN type='absence' AND justifie=0 THEN 1 ELSE 0 END) as non_justifiees
           FROM absences WHERE eleve_id=? AND ecole_id=?""",
        (eleve_id, g.user['ecole_id']),
    ).fetchone()
    result = dict(row)
    for k in result:
        result[k] = result[k] or 0
    return jsonify(result)


@bp.route('/absences', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'enseignant', 'secretaire')
def create_absence():
    body = request.get_json(silent=True) or {}
    eleve_id, date_abs = body.get('eleve_id'), body.get('date_abs')
    if not eleve_id or not date_abs:
        return jsonify({'error': 'Élève et date requis'}), 400
    aid = gen_id('abs')
    db.execute(
        "INSERT INTO absences (id,ecole_id,eleve_id,date_abs,type,justifie,motif,duree) VALUES (?,?,?,?,?,?,?,?)",
        (aid, g.user['ecole_id'], eleve_id, date_abs, body.get('type', 'absence'), 1 if body.get('justifie') else 0,
         body.get('motif'), body.get('duree', 'journée')),
    )
    db.commit()
    row = db.execute("SELECT * FROM absences WHERE id=?", (aid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/absences/<absence_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'enseignant', 'secretaire')
def update_absence(absence_id):
    body = request.get_json(silent=True) or {}
    # Un enseignant peut modifier une absence, mais doit obligatoirement fournir une justification
    if g.user['role'] == 'enseignant' and not body.get('motif'):
        return jsonify({'error': 'Une justification (motif) est obligatoire pour modifier une absence'}), 400
    db.execute(
        "UPDATE absences SET type=COALESCE(?,type), justifie=COALESCE(?,justifie), "
        "motif=COALESCE(?,motif), duree=COALESCE(?,duree) WHERE id=? AND ecole_id=?",
        (body.get('type'), (1 if body.get('justifie') else 0) if 'justifie' in body else None,
         body.get('motif'), body.get('duree'), absence_id, g.user['ecole_id']),
    )
    db.commit()
    if g.user['role'] == 'enseignant':
        log_action(g.user, 'modification', 'absence', absence_id, {'motif': body.get('motif')})
    row = db.execute("SELECT * FROM absences WHERE id=? AND ecole_id=?", (absence_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/absences/<absence_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def delete_absence(absence_id):
    db.execute("DELETE FROM absences WHERE id=? AND ecole_id=?", (absence_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# RÉINSCRIPTIONS
# ─────────────────────────────────────────────────────────────
@bp.route('/reinscriptions', methods=['GET'])
@require_auth
def list_reinscriptions():
    annee_scolaire = request.args.get('annee_scolaire')
    statut = request.args.get('statut')
    sql = """SELECT r.*, e.nom, e.prenom, e.matricule, e.classe as classe_actuelle, u.full_name as validee_par_nom
             FROM reinscriptions r JOIN eleves e ON e.id=r.eleve_id
             LEFT JOIN users u ON u.id=r.validee_par WHERE r.ecole_id=?"""
    params = [g.user['ecole_id']]
    if annee_scolaire: sql += " AND r.annee_scolaire=?"; params.append(annee_scolaire)
    if statut: sql += " AND r.statut=?"; params.append(statut)
    sql += " ORDER BY r.date_demande DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/reinscriptions', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def create_reinscription():
    body = request.get_json(silent=True) or {}
    eleve_id, annee_scolaire = body.get('eleve_id'), body.get('annee_scolaire')
    if not eleve_id or not annee_scolaire:
        return jsonify({'error': 'Élève et année scolaire requis'}), 400
    eleve = db.execute("SELECT classe FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not eleve:
        return jsonify({'error': 'Élève introuvable'}), 404
    rid = gen_id('r')
    try:
        db.execute(
            "INSERT INTO reinscriptions (id,ecole_id,eleve_id,annee_scolaire,classe_precedente,classe_nouvelle,notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (rid, g.user['ecole_id'], eleve_id, annee_scolaire, eleve['classe'], body.get('classe_nouvelle'), body.get('notes')),
        )
        db.commit()
    except Exception:
        return jsonify({'error': 'Réinscription déjà enregistrée pour cet élève/année'}), 409
    row = db.execute("SELECT * FROM reinscriptions WHERE id=?", (rid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/reinscriptions/<r_id>/valider', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def valider_reinscription(r_id):
    body = request.get_json(silent=True) or {}
    r = db.execute("SELECT * FROM reinscriptions WHERE id=? AND ecole_id=?", (r_id, g.user['ecole_id'])).fetchone()
    if not r:
        return jsonify({'error': 'Introuvable'}), 404
    statut = body.get('statut', 'validee')
    db.execute(
        "UPDATE reinscriptions SET statut=?, date_validation=CURRENT_TIMESTAMP, validee_par=?, "
        "classe_nouvelle=COALESCE(?,classe_nouvelle) WHERE id=?",
        (statut, g.user['id'], body.get('classe_nouvelle'), r_id),
    )
    db.commit()
    if statut == 'validee':
        updated = db.execute("SELECT * FROM reinscriptions WHERE id=?", (r_id,)).fetchone()
        if updated['classe_nouvelle']:
            db.execute(
                "UPDATE eleves SET classe=?, annee_scolaire=?, statut='actif' WHERE id=?",
                (updated['classe_nouvelle'], updated['annee_scolaire'], updated['eleve_id']),
            )
            db.commit()
    log_action(g.user, 'validation_reinscription' if statut == 'validee' else 'refus_reinscription', 'reinscription', r_id,
               {'eleve_id': r['eleve_id'], 'annee_scolaire': r['annee_scolaire'], 'classe_nouvelle': body.get('classe_nouvelle')})
    row = db.execute("SELECT * FROM reinscriptions WHERE id=?", (r_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/reinscriptions/<r_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_reinscription(r_id):
    db.execute("DELETE FROM reinscriptions WHERE id=? AND ecole_id=?", (r_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# PERSONNEL
# ─────────────────────────────────────────────────────────────
@bp.route('/personnel', methods=['GET'])
@require_auth
def list_personnel():
    mois = request.args.get('mois') or __import__('datetime').datetime.now().strftime('%Y-%m')
    rows = db.execute("SELECT * FROM personnel WHERE ecole_id=? ORDER BY nom, prenom", (g.user['ecole_id'],)).fetchall()
    result = rows_to_list(rows)
    # Pour le personnel payé à l'heure, calculer le salaire du mois à partir des heures saisies
    for p in result:
        if p.get('type_remuneration') == 'horaire':
            h = db.execute("SELECT nombre_heures FROM heures_enseignement WHERE personnel_id=? AND ecole_id=? AND mois=?", (p['id'], g.user['ecole_id'], mois)).fetchone()
            p['heures_mois'] = h['nombre_heures'] if h else 0
            p['salaire_calcule'] = round((h['nombre_heures'] if h else 0) * (p.get('taux_horaire') or 0))
        else:
            p['heures_mois'] = None
            p['salaire_calcule'] = p.get('salaire') or 0
    return jsonify(result)


@bp.route('/personnel', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def create_personnel():
    body = request.get_json(silent=True) or {}
    pid = gen_id('p')
    matricule_impose = body.get('matricule')
    cycles_str = body.get('cycle_enseignement') or ''
    cycles_liste = [c.strip() for c in cycles_str.split(',') if c.strip()]
    type_remuneration = body.get('type_remuneration') or (
        'horaire' if ('college' in cycles_liste or 'lycee' in cycles_liste) and body.get('poste') == 'Enseignant' else 'mensuel'
    )
    # Nouvelle tentative automatique en cas de collision de matricule (créations
    # quasi simultanées) — voir la même logique pour les élèves.
    derniere_erreur = None
    with matricule_lock:
        for _ in range(5):
            matricule = matricule_impose or next_matricule_personnel(g.user['ecole_id'])
            try:
                db.execute(
                    "INSERT INTO personnel (id,ecole_id,nom,prenom,poste,matiere,telephone,email,date_embauche,salaire,user_id,cycle_enseignement,type_remuneration,taux_horaire,matricule,adresse) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, g.user['ecole_id'], body.get('nom', ''), body.get('prenom', ''), body.get('poste'), body.get('matiere'),
                     body.get('telephone'), body.get('email'), body.get('date_embauche'),
                     body.get('salaire', 0), body.get('user_id'), body.get('cycle_enseignement'),
                     type_remuneration, body.get('taux_horaire', 0), matricule, body.get('adresse')),
                )
                db.commit()
                derniere_erreur = None
                break
            except Exception as e:
                derniere_erreur = e
                if matricule_impose or 'matricule' not in str(e).lower():
                    return jsonify({'error': str(e)}), 400
                continue
    if derniere_erreur is not None:
        return jsonify({'error': str(derniere_erreur)}), 400
    log_action(g.user, 'creation', 'personnel', pid, {'nom': body.get('nom'), 'prenom': body.get('prenom'), 'poste': body.get('poste')})
    row = db.execute("SELECT * FROM personnel WHERE id=?", (pid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/personnel/<p_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def update_personnel(p_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        """UPDATE personnel SET nom=COALESCE(?,nom), prenom=COALESCE(?,prenom), poste=COALESCE(?,poste),
           matiere=COALESCE(?,matiere), telephone=COALESCE(?,telephone), email=COALESCE(?,email),
           date_embauche=COALESCE(?,date_embauche), salaire=COALESCE(?,salaire),
           cycle_enseignement=COALESCE(?,cycle_enseignement), type_remuneration=COALESCE(?,type_remuneration),
           taux_horaire=COALESCE(?,taux_horaire), adresse=COALESCE(?,adresse) WHERE id=? AND ecole_id=?""",
        (body.get('nom'), body.get('prenom'), body.get('poste'), body.get('matiere'),
         body.get('telephone'), body.get('email'), body.get('date_embauche'),
         body.get('salaire'), body.get('cycle_enseignement'), body.get('type_remuneration'),
         body.get('taux_horaire'), body.get('adresse'), p_id, g.user['ecole_id']),
    )
    db.commit()
    log_action(g.user, 'modification', 'personnel', p_id, {'motif': body.get('motif'), **body})
    row = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/personnel/<p_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def delete_personnel(p_id):
    db.execute("DELETE FROM personnel WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'personnel', p_id, {})
    return jsonify({'success': True})


ALLOWED_PHOTO_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


@bp.route('/personnel/<p_id>/photo', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def upload_photo_personnel(p_id):
    if not db.execute("SELECT id FROM personnel WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    file = request.files.get('photo')
    if not file or file.filename == '':
        return jsonify({'error': 'Pas de fichier'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXT:
        return jsonify({'error': 'Format non supporté'}), 400
    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))
    url = '/uploads/' + fname
    db.execute("UPDATE personnel SET photo_url=? WHERE id=? AND ecole_id=?", (url, p_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'photo_url': url})


# ─────────────────────────────────────────────────────────────
# HEURES D'ENSEIGNEMENT (personnel payé à l'heure — collège/lycée)
# ─────────────────────────────────────────────────────────────
@bp.route('/personnel/<p_id>/heures', methods=['GET'])
@require_auth
def list_heures_personnel(p_id):
    rows = db.execute(
        "SELECT * FROM heures_enseignement WHERE personnel_id=? AND ecole_id=? ORDER BY mois DESC", (p_id, g.user['ecole_id'])
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/personnel/<p_id>/heures', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def saisir_heures_personnel(p_id):
    body = request.get_json(silent=True) or {}
    mois, nombre_heures = body.get('mois'), body.get('nombre_heures')
    if not mois or nombre_heures is None:
        return jsonify({'error': 'Mois et nombre d\'heures requis'}), 400
    personnel = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone()
    if not personnel:
        return jsonify({'error': 'Personnel introuvable'}), 404
    hid = gen_id('h')
    db.execute(
        "INSERT INTO heures_enseignement (id,ecole_id,personnel_id,mois,nombre_heures) VALUES (?,?,?,?,?) "
        "ON CONFLICT(personnel_id,mois) DO UPDATE SET nombre_heures=excluded.nombre_heures",
        (hid, g.user['ecole_id'], p_id, mois, nombre_heures),
    )
    db.commit()
    log_action(g.user, 'saisie_heures', 'personnel', p_id,
               {'mois': mois, 'nombre_heures': nombre_heures, 'nom': f"{personnel['prenom']} {personnel['nom']}"})
    row = db.execute("SELECT * FROM heures_enseignement WHERE personnel_id=? AND ecole_id=? AND mois=?", (p_id, g.user['ecole_id'], mois)).fetchone()
    return jsonify(row_to_dict(row)), 201


# ─────────────────────────────────────────────────────────────
# SÉANCES DE COURS (traçabilité précise + validation par la direction
# + comptabilisation automatique des heures en paie)
# ─────────────────────────────────────────────────────────────
def _duree_depuis_creneau(creneau):
    """Calcule la durée en heures d'un créneau du type '08h30 - 09h30'. Retourne 1.0 par défaut si le format n'est pas reconnu."""
    if not creneau:
        return 1.0
    try:
        deb, fin = [c.strip() for c in creneau.split('-')]
        def to_minutes(t):
            t = t.replace('h', ':').replace('H', ':')
            if t.endswith(':'):
                t += '00'
            h, m = t.split(':')
            return int(h) * 60 + int(m or 0)
        return max(0.25, round((to_minutes(fin) - to_minutes(deb)) / 60, 2))
    except Exception:
        return 1.0


@bp.route('/seances-cours', methods=['GET'])
@require_auth
def list_seances_cours():
    personnel_id = request.args.get('personnel_id')
    mois = request.args.get('mois')
    statut = request.args.get('statut')
    sql = """SELECT s.*, p.nom, p.prenom, p.matricule FROM seances_cours s
             JOIN personnel p ON p.id=s.personnel_id WHERE s.ecole_id=?"""
    params = [g.user['ecole_id']]
    # Un enseignant ne voit que ses propres séances
    if g.user['role'] == 'enseignant':
        mon_personnel = db.execute("SELECT id FROM personnel WHERE user_id=? AND ecole_id=?", (g.user['id'], g.user['ecole_id'])).fetchone()
        if not mon_personnel:
            return jsonify([])
        sql += " AND s.personnel_id=?"; params.append(mon_personnel['id'])
    elif personnel_id:
        sql += " AND s.personnel_id=?"; params.append(personnel_id)
    if mois:
        sql += " AND substr(s.date_seance,1,7)=?"; params.append(mois)
    if statut:
        sql += " AND s.statut=?"; params.append(statut)
    sql += " ORDER BY s.date_seance DESC, s.creneau DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/seances-cours', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'enseignant')
def create_seance_cours():
    body = request.get_json(silent=True) or {}
    personnel_id = body.get('personnel_id')
    date_seance = body.get('date_seance')
    if not personnel_id or not date_seance:
        return jsonify({'error': 'Enseignant et date requis'}), 400

    # Un enseignant ne peut déclarer une séance que pour lui-même
    if g.user['role'] == 'enseignant':
        mon_personnel = db.execute("SELECT id FROM personnel WHERE user_id=? AND ecole_id=?", (g.user['id'], g.user['ecole_id'])).fetchone()
        if not mon_personnel or mon_personnel['id'] != personnel_id:
            return jsonify({'error': 'Vous ne pouvez déclarer une séance que pour vous-même'}), 403

    personnel = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not personnel:
        return jsonify({'error': 'Personnel introuvable'}), 404

    creneau = body.get('creneau')
    duree = body.get('duree_heures')
    if not duree:
        duree = _duree_depuis_creneau(creneau)

    try:
        jour = body.get('jour') or __import__('datetime').datetime.strptime(date_seance, '%Y-%m-%d').strftime('%A')
    except Exception:
        jour = body.get('jour')
    JOURS_FR = {'Monday':'Lundi','Tuesday':'Mardi','Wednesday':'Mercredi','Thursday':'Jeudi','Friday':'Vendredi','Saturday':'Samedi','Sunday':'Dimanche'}
    jour = JOURS_FR.get(jour, jour)

    sid = gen_id('sc')
    db.execute(
        """INSERT INTO seances_cours (id,ecole_id,personnel_id,date_seance,jour,creneau,classe,salle,matiere,duree_heures,statut,cree_par)
           VALUES (?,?,?,?,?,?,?,?,?,?,'en_attente',?)""",
        (sid, g.user['ecole_id'], personnel_id, date_seance, jour, creneau, body.get('classe'), body.get('salle'),
         body.get('matiere'), duree, g.user['id']),
    )
    db.commit()
    log_action(g.user, 'declaration_seance', 'personnel', personnel_id,
               {'date': date_seance, 'creneau': creneau, 'classe': body.get('classe'), 'nom': f"{personnel['prenom']} {personnel['nom']}"})
    row = db.execute("""SELECT s.*, p.nom, p.prenom FROM seances_cours s JOIN personnel p ON p.id=s.personnel_id WHERE s.id=?""", (sid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/seances-cours/<s_id>/valider', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'directeur_etudes')
def valider_seance_cours(s_id):
    s = db.execute("SELECT * FROM seances_cours WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id'])).fetchone()
    if not s:
        return jsonify({'error': 'Introuvable'}), 404
    if s['statut'] != 'en_attente':
        return jsonify({'error': 'Cette séance a déjà été traitée'}), 400
    db.execute(
        "UPDATE seances_cours SET statut='validee', valide_par=?, date_validation=CURRENT_TIMESTAMP WHERE id=?",
        (g.user['id'], s_id),
    )
    db.commit()
    log_action(g.user, 'validation_seance', 'seance_cours', s_id, {'date': s['date_seance'], 'classe': s['classe']})
    row = db.execute("""SELECT s.*, p.nom, p.prenom FROM seances_cours s JOIN personnel p ON p.id=s.personnel_id WHERE s.id=?""", (s_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/seances-cours/valider-groupe', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'directeur_etudes')
def valider_groupe_seances():
    """Valide en une seule fois toutes les séances en attente d'un enseignant pour un mois donné."""
    body = request.get_json(silent=True) or {}
    personnel_id, mois = body.get('personnel_id'), body.get('mois')
    if not personnel_id or not mois:
        return jsonify({'error': 'Enseignant et mois requis'}), 400
    ids = db.execute(
        "SELECT id FROM seances_cours WHERE personnel_id=? AND ecole_id=? AND substr(date_seance,1,7)=? AND statut='en_attente'",
        (personnel_id, g.user['ecole_id'], mois),
    ).fetchall()
    for row in ids:
        db.execute("UPDATE seances_cours SET statut='validee', valide_par=?, date_validation=CURRENT_TIMESTAMP WHERE id=?",
                   (g.user['id'], row['id']))
    db.commit()
    log_action(g.user, 'validation_seances_groupe', 'personnel', personnel_id, {'mois': mois, 'nombre': len(ids)})
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/seances-cours/<s_id>/rejeter', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'directeur_etudes')
def rejeter_seance_cours(s_id):
    body = request.get_json(silent=True) or {}
    s = db.execute("SELECT * FROM seances_cours WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id'])).fetchone()
    if not s:
        return jsonify({'error': 'Introuvable'}), 404
    if s['statut'] != 'en_attente':
        return jsonify({'error': 'Cette séance a déjà été traitée'}), 400
    db.execute(
        "UPDATE seances_cours SET statut='rejetee', motif_rejet=?, valide_par=?, date_validation=CURRENT_TIMESTAMP WHERE id=?",
        (body.get('motif'), g.user['id'], s_id),
    )
    db.commit()
    log_action(g.user, 'rejet_seance', 'seance_cours', s_id, {'motif': body.get('motif')})
    row = db.execute("""SELECT s.*, p.nom, p.prenom FROM seances_cours s JOIN personnel p ON p.id=s.personnel_id WHERE s.id=?""", (s_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/seances-cours/<s_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_seance_cours(s_id):
    db.execute("DELETE FROM seances_cours WHERE id=? AND ecole_id=?", (s_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/personnel/<p_id>/creneaux-emploi-temps', methods=['GET'])
@require_auth
def creneaux_emploi_temps_personnel(p_id):
    """Retourne les créneaux réguliers (issus de l'emploi du temps) de cet enseignant,
    pour pré-remplir facilement la déclaration d'une séance."""
    rows = db.execute(
        "SELECT DISTINCT jour, creneau, classe, salle, matiere FROM emploi_du_temps WHERE professeur_id=? AND ecole_id=? ORDER BY jour, creneau",
        (p_id, g.user['ecole_id']),
    ).fetchall()
    return jsonify(rows_to_list(rows))


# ─────────────────────────────────────────────────────────────
# ABSENCES DU PERSONNEL (point 6 : savoir si un enseignant est absent)
# ─────────────────────────────────────────────────────────────
@bp.route('/absences-personnel', methods=['GET'])
@require_auth
def list_absences_personnel():
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    sql = """SELECT ap.*, p.nom, p.prenom, p.poste, p.matiere
             FROM absences_personnel ap JOIN personnel p ON p.id=ap.personnel_id WHERE ap.ecole_id=?"""
    params = [g.user['ecole_id']]
    if date_debut: sql += " AND (ap.date_fin IS NULL OR ap.date_fin>=?)"; params.append(date_debut)
    if date_fin: sql += " AND ap.date_debut<=?"; params.append(date_fin)
    sql += " ORDER BY ap.date_debut DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/absences-personnel/aujourd-hui', methods=['GET'])
@require_auth
def absences_personnel_aujourdhui():
    """Liste des membres du personnel absents AUJOURD'HUI — pour affichage dashboard/alerte."""
    rows = db.execute(
        """SELECT ap.*, p.nom, p.prenom, p.poste, p.matiere
           FROM absences_personnel ap JOIN personnel p ON p.id=ap.personnel_id
           WHERE ap.ecole_id=? AND date(ap.date_debut) <= date('now') AND (ap.date_fin IS NULL OR date(ap.date_fin) >= date('now'))
           ORDER BY p.nom""",
        (g.user['ecole_id'],)
    ).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/absences-personnel', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def signaler_absence_personnel():
    body = request.get_json(silent=True) or {}
    personnel_id, date_debut = body.get('personnel_id'), body.get('date_debut')
    if not personnel_id or not date_debut:
        return jsonify({'error': 'Personnel et date requis'}), 400
    p = db.execute("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (personnel_id, g.user['ecole_id'])).fetchone()
    if not p:
        return jsonify({'error': 'Personnel introuvable'}), 404
    aid = gen_id('apr')
    db.execute(
        "INSERT INTO absences_personnel (id,ecole_id,personnel_id,date_debut,date_fin,motif,remplace_par,signale_par) VALUES (?,?,?,?,?,?,?,?)",
        (aid, g.user['ecole_id'], personnel_id, date_debut, body.get('date_fin'), body.get('motif'), body.get('remplace_par'), g.user['id']),
    )
    db.commit()
    log_action(g.user, 'signalement_absence', 'personnel', personnel_id,
               {'nom': f"{p['prenom']} {p['nom']}", 'date_debut': date_debut, 'motif': body.get('motif')})
    row = db.execute("SELECT * FROM absences_personnel WHERE id=?", (aid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/absences-personnel/<a_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def update_absence_personnel(a_id):
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE absences_personnel SET date_fin=COALESCE(?,date_fin), motif=COALESCE(?,motif), "
        "remplace_par=COALESCE(?,remplace_par) WHERE id=? AND ecole_id=?",
        (body.get('date_fin'), body.get('motif'), body.get('remplace_par'), a_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM absences_personnel WHERE id=? AND ecole_id=?", (a_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/absences-personnel/<a_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def delete_absence_personnel(a_id):
    db.execute("DELETE FROM absences_personnel WHERE id=? AND ecole_id=?", (a_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})

