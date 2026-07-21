from datetime import datetime
from flask import Blueprint, request, jsonify, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, next_matricule_personnel, matricule_lock
from auth import require_auth, require_role

bp = Blueprint('candidatures_routes', __name__, url_prefix='/api/candidatures')


@bp.route('', methods=['POST'])
def soumettre_candidature():
    """Soumission PUBLIQUE — accessible sans connexion (en ligne) pour qu'un enseignant
    puisse postuler lui-même en indiquant les matières et horaires qu'il souhaite enseigner."""
    body = request.get_json(silent=True) or {}
    nom, prenom = body.get('nom'), body.get('prenom')
    if not nom or not prenom:
        return jsonify({'error': 'Nom et prénom requis'}), 400
    matieres = body.get('matieres')
    if isinstance(matieres, list):
        matieres = ', '.join(matieres)
    cid = gen_id('cand')
    db.execute(
        """INSERT INTO candidatures_enseignants
           (id,nom,prenom,telephone,email,matieres,cycle,disponibilites,message)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (cid, nom, prenom, body.get('telephone'), body.get('email'), matieres,
         body.get('cycle'), body.get('disponibilites'), body.get('message')),
    )
    db.commit()
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (cid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def list_candidatures():
    statut = request.args.get('statut')
    sql = "SELECT * FROM candidatures_enseignants WHERE 1=1"
    params = []
    if statut: sql += " AND statut=?"; params.append(statut)
    sql += " ORDER BY date_candidature DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/<c_id>', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def get_candidature(c_id):
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (c_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>/approuver', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def approuver_candidature(c_id):
    """Approuve la candidature : crée (ou met à jour) la fiche personnel correspondante
    avec les matières et disponibilités choisies par le candidat lui-même.
    Ces informations restent modifiables ensuite librement par l'administration."""
    body = request.get_json(silent=True) or {}
    c = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (c_id,)).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    if c['statut'] != 'en_attente':
        return jsonify({'error': 'Cette candidature a déjà été traitée'}), 400

    pid = gen_id('p')
    derniere_erreur = None
    with matricule_lock:
        for _ in range(5):
            matricule = next_matricule_personnel()
            try:
                db.execute(
                    "INSERT INTO personnel (id,nom,prenom,poste,matiere,telephone,email,cycle_enseignement,date_embauche,matricule) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (pid, c['nom'], c['prenom'], 'Enseignant', c['matieres'], c['telephone'], c['email'],
                     c['cycle'], datetime.now().strftime('%Y-%m-%d'), matricule),
                )
                db.commit()
                derniere_erreur = None
                break
            except Exception as e:
                derniere_erreur = e
                if 'matricule' not in str(e).lower():
                    return jsonify({'error': str(e)}), 400
                continue
    if derniere_erreur is not None:
        return jsonify({'error': str(derniere_erreur)}), 400
    db.execute(
        "UPDATE candidatures_enseignants SET statut='approuvee', personnel_id=?, approuve_par=?, date_approbation=CURRENT_TIMESTAMP WHERE id=?",
        (pid, g.user['id'], c_id),
    )
    db.commit()
    log_action(g.user, 'approbation', 'candidature', c_id,
               {'nom': f"{c['prenom']} {c['nom']}", 'matieres': c['matieres']})
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (c_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>/rejeter', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def rejeter_candidature(c_id):
    body = request.get_json(silent=True) or {}
    c = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (c_id,)).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        "UPDATE candidatures_enseignants SET statut='rejetee', approuve_par=?, date_approbation=CURRENT_TIMESTAMP WHERE id=?",
        (g.user['id'], c_id),
    )
    db.commit()
    log_action(g.user, 'rejet', 'candidature', c_id, {'nom': f"{c['prenom']} {c['nom']}", 'motif': body.get('motif')})
    row = db.execute("SELECT * FROM candidatures_enseignants WHERE id=?", (c_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<c_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur')
def delete_candidature(c_id):
    db.execute("DELETE FROM candidatures_enseignants WHERE id=?", (c_id,))
    db.commit()
    return jsonify({'success': True})
