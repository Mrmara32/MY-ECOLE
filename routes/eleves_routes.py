import os
import time
import random
from flask import Blueprint, request, jsonify, current_app, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, get_classes_enseignant, matricule_lock, next_sequence
from auth import require_auth, require_role

bp = Blueprint('eleves_routes', __name__, url_prefix='/api/eleves')

FIELDS_BASE = ['matricule', 'nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe',
               'nationalite', 'classe', 'annee_scolaire', 'statut', 'adresse',
               'contact_urgence_nom', 'contact_urgence_telephone']
FIELDS_FILIATION = ['pere_nom', 'pere_prenom', 'pere_profession', 'pere_telephone', 'pere_email',
                     'mere_nom', 'mere_prenom', 'mere_profession', 'mere_telephone', 'mere_email',
                     'tuteur_nom', 'tuteur_prenom', 'tuteur_relation', 'tuteur_telephone', 'tuteur_email']
FIELDS_SANTE = ['groupe_sanguin', 'allergies', 'maladies_chroniques', 'medicaments', 'handicap',
                'medecin_nom', 'medecin_telephone', 'assurance_nom', 'assurance_numero', 'vaccins']
ALL_FIELDS = FIELDS_BASE + FIELDS_FILIATION + FIELDS_SANTE
ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def next_matricule():
    return next_sequence('matricule_eleve', 'M', 6)


@bp.route('', methods=['GET'])
@require_auth
def list_eleves():
    classe = request.args.get('classe')
    statut = request.args.get('statut')
    annee_scolaire = request.args.get('annee_scolaire')
    q = request.args.get('q')

    sql = "SELECT * FROM eleves WHERE 1=1"
    params = []

    # Un enseignant ne voit que les élèves des classes qu'il enseigne réellement
    if g.user['role'] == 'enseignant':
        mes_classes = get_classes_enseignant(g.user['id'])
        if not mes_classes:
            return jsonify([])
        placeholders = ','.join(['?'] * len(mes_classes))
        sql += f" AND classe IN ({placeholders})"
        params += mes_classes

    if classe:
        sql += " AND classe=?"; params.append(classe)
    if statut:
        sql += " AND statut=?"; params.append(statut)
    if annee_scolaire:
        sql += " AND annee_scolaire=?"; params.append(annee_scolaire)
    if q:
        sql += " AND (nom LIKE ? OR prenom LIKE ? OR matricule LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " ORDER BY nom, prenom"

    rows = db.execute(sql, params).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/meta/classes', methods=['GET'])
@require_auth
def meta_classes():
    rows = db.execute(
        "SELECT DISTINCT classe FROM eleves WHERE classe IS NOT NULL ORDER BY classe"
    ).fetchall()
    return jsonify([r['classe'] for r in rows])


@bp.route('/<eleve_id>', methods=['GET'])
@require_auth
def get_eleve(eleve_id):
    row = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(row_to_dict(row))


ROLES_INSCRIPTION_DIRECTE = ('admin', 'directeur', 'secretaire', 'comptable')


@bp.route('/preinscription-publique', methods=['POST'])
def preinscription_publique():
    """Formulaire PUBLIC (sans connexion) permettant à n'importe quel parent de
    préinscrire son enfant depuis le site vitrine de l'école. L'élève reste en
    statut 'preinscrit' tant que le comptable n'a pas validé le paiement."""
    body = request.get_json(silent=True) or {}
    nom, prenom = body.get('nom'), body.get('prenom')
    if not nom or not prenom:
        return jsonify({'error': 'Nom et prénom requis'}), 400

    eid = gen_id('e')
    champs_autorises = ['date_naissance', 'lieu_naissance', 'sexe', 'classe',
                         'pere_nom', 'pere_prenom', 'pere_telephone', 'pere_email',
                         'mere_nom', 'mere_prenom', 'mere_telephone', 'mere_email',
                         'adresse', 'contact_urgence_nom', 'contact_urgence_telephone']
    provided = {f: body[f] for f in champs_autorises if body.get(f) not in (None, '')}
    provided['statut'] = 'preinscrit'  # toujours forcé, jamais actif directement depuis le public

    derniere_erreur = None
    matricule = None
    with matricule_lock:
        for _ in range(5):
            matricule = next_matricule()
            cols = ['id', 'matricule', 'nom', 'prenom'] + list(provided.keys())
            vals = [eid, matricule, nom, prenom] + list(provided.values())
            placeholders = ','.join(['?'] * len(cols))
            try:
                db.execute(f"INSERT INTO eleves ({','.join(cols)}) VALUES ({placeholders})", vals)
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

    row = db.execute("SELECT * FROM eleves WHERE id=?", (eid,)).fetchone()
    return jsonify({'matricule': matricule, 'nom': nom, 'prenom': prenom}), 201


@bp.route('', methods=['POST'])
@require_auth
def create_eleve():
    body = request.get_json(silent=True) or {}
    eid = gen_id('e')
    matricule_impose = body.get('matricule')

    # N'insère que les champs réellement fournis, pour laisser les valeurs par
    # défaut de la base (statut='actif', nationalite='Guinéenne') s'appliquer
    # si l'utilisateur ne les a pas précisées.
    provided = {f: body[f] for f in ALL_FIELDS if body.get(f) not in (None, '')}

    # Préinscription (point 7) : seuls admin/directeur/secrétaire/comptable peuvent
    # inscrire directement un élève en statut "actif". Tout autre rôle authentifié
    # (par ex. un enseignant) peut préinscrire un élève, mais celui-ci reste en
    # statut "preinscrit" tant que le comptable n'a pas validé le paiement.
    if g.user['role'] not in ROLES_INSCRIPTION_DIRECTE:
        provided['statut'] = 'preinscrit'

    # Le verrou sérialise "calculer le prochain matricule → insérer", pour
    # éliminer la collision entre créations quasi simultanées à la source
    # (plutôt que de compter uniquement sur la nouvelle tentative après coup).
    derniere_erreur = None
    with matricule_lock:
        for _ in range(5):
            matricule = matricule_impose or next_matricule()
            cols = ['id', 'matricule'] + list(provided.keys())
            vals = [eid, matricule] + list(provided.values())
            placeholders = ','.join(['?'] * len(cols))
            try:
                db.execute(f"INSERT INTO eleves ({','.join(cols)}) VALUES ({placeholders})", vals)
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

    row = db.execute("SELECT * FROM eleves WHERE id=?", (eid,)).fetchone()
    log_action(g.user, 'creation' if provided.get('statut') != 'preinscrit' else 'preinscription',
               'eleve', eid, {'nom': body.get('nom'), 'prenom': body.get('prenom'), 'classe': body.get('classe')})
    return jsonify(row_to_dict(row)), 201


@bp.route('/<eleve_id>/valider-preinscription', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'comptable')
def valider_preinscription(eleve_id):
    """Le comptable (ou directeur/admin) valide une préinscription une fois le
    paiement des frais d'inscription/réinscription confirmé — l'élève passe alors
    au statut 'actif' et devient pleinement inscrit."""
    body = request.get_json(silent=True) or {}
    e = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    if not e:
        return jsonify({'error': 'Introuvable'}), 404
    if e['statut'] != 'preinscrit':
        return jsonify({'error': "Cet élève n'est pas en attente de préinscription"}), 400

    db.execute("UPDATE eleves SET statut='actif' WHERE id=?", (eleve_id,))
    db.commit()
    log_action(g.user, 'validation_preinscription', 'eleve', eleve_id,
               {'nom': e['nom'], 'prenom': e['prenom'], 'montant_paye': body.get('montant')})

    # Si un montant de paiement d'inscription est précisé, on enregistre la transaction correspondante
    try:
        montant = float(body.get('montant')) if body.get('montant') not in (None, '') else None
    except (TypeError, ValueError):
        montant = None
    if montant and montant > 0:
        tid = gen_id('t')
        date_op = body.get('date_paiement') or __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        db.execute(
            "INSERT INTO transactions (id,type,date_op,description,categorie,moyen_paiement,montant,reference,eleve_id,cree_par,statut_validation) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tid, 'entree', date_op, f"Frais d'inscription — {e['prenom']} {e['nom']} ({e['matricule']})",
             "Frais d'inscription", body.get('moyen_paiement', 'Espèces'), montant,
             body.get('reference') or f"INS-{eleve_id}", eleve_id, g.user['id'], 'auto'),
        )
        db.commit()

    row = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<eleve_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'comptable')
def update_eleve(eleve_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM eleves WHERE id=?", (eleve_id,)).fetchone():
        return jsonify({'error': 'Introuvable'}), 404

    sets, vals = [], []
    for f in ALL_FIELDS:
        if f in body:
            sets.append(f"{f}=?")
            vals.append(body[f])
    if sets:
        vals.append(eleve_id)
        db.execute(f"UPDATE eleves SET {','.join(sets)} WHERE id=?", vals)
        db.commit()

    log_action(g.user, 'modification', 'eleve', eleve_id,
               {'motif': body.get('motif'), 'champs_modifies': {k: v for k, v in body.items() if k in ALL_FIELDS}})
    row = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/<eleve_id>/photo', methods=['POST'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def upload_photo(eleve_id):
    file = request.files.get('photo')
    if not file or file.filename == '':
        return jsonify({'error': 'Pas de fichier'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Format non supporté'}), 400

    if not db.execute("SELECT id FROM eleves WHERE id=?", (eleve_id,)).fetchone():
        return jsonify({'error': 'Élève introuvable'}), 404

    fname = f"{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))

    url = '/uploads/' + fname
    db.execute("UPDATE eleves SET photo_url=? WHERE id=?", (url, eleve_id))
    db.commit()
    return jsonify({'photo_url': url})


@bp.route('/<eleve_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
def delete_eleve(eleve_id):
    existing = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM eleves WHERE id=?", (eleve_id,))
    db.commit()
    log_action(g.user, 'suppression', 'eleve', eleve_id, {'nom': existing['nom'], 'prenom': existing['prenom']})
    return jsonify({'success': True})
