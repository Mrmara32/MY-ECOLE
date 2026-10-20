"""Import d'élèves (Excel/CSV) et attestations de scolarité numérotées."""
import csv
import io
import os
from datetime import date

from flask import Blueprint, request, jsonify, g, Response

import import_eleves as imp
from database import db, gen_id, row_to_dict, log_action, next_sequence, matricule_lock, get_settings
from auth import require_auth, require_role
from permissions import require_permission

bp = Blueprint('import_eleves_routes', __name__, url_prefix='/api')

ROLES_ADMINISTRATION = ('admin', 'directeur', 'secretaire')
TAILLE_MAX = 5 * 1024 * 1024


@bp.route('/import-eleves/modele', methods=['GET'])
@require_auth
@require_role(*ROLES_ADMINISTRATION)
def modele_import():
    """Fichier CSV modèle (séparateur ; et BOM UTF-8 : s'ouvre correctement dans Excel en français)."""
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=';')
    w.writerow(imp.MODELE_TITRES); w.writerow(imp.MODELE_EXEMPLE)
    return Response('﻿' + sortie.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="modele-import-eleves.csv"'})


@bp.route('/import-eleves', methods=['POST'])
@require_auth
@require_role(*ROLES_ADMINISTRATION)
@require_permission('eleves', 'peut_creer')
def importer_eleves():
    """Multipart : fichier=<.xlsx|.csv>, simulation=1 pour vérifier sans rien enregistrer.
    Les lignes valides sont enregistrées ; les lignes en erreur ou déjà présentes sont signalées et ignorées."""
    fichier = request.files.get('fichier')
    if not fichier or not fichier.filename:
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    contenu = fichier.read(TAILLE_MAX + 1)
    if len(contenu) > TAILLE_MAX:
        return jsonify({'error': 'Fichier trop volumineux (5 Mo maximum)'}), 400
    ext = os.path.splitext(fichier.filename)[1].lower()
    try:
        lignes, erreur = imp.lire_fichier(contenu, ext)
    except Exception:
        return jsonify({'error': "Impossible de lire ce fichier : vérifiez qu'il s'agit bien d'un .xlsx ou d'un .csv valide"}), 400
    if erreur:
        return jsonify({'error': erreur}), 400

    simulation = request.form.get('simulation') in ('1', 'true', 'oui')
    eid = g.user['ecole_id']
    classes = {r['nom'] for r in db.execute("SELECT nom FROM classes WHERE ecole_id=?", (eid,)).fetchall()}
    existants = {(r['nom'].lower(), r['prenom'].lower(), r['date_naissance'] or '')
                 for r in db.execute("SELECT nom, prenom, date_naissance FROM eleves WHERE ecole_id=?", (eid,)).fetchall()}
    matricules = {r['matricule'] for r in db.execute("SELECT matricule FROM eleves WHERE ecole_id=?", (eid,)).fetchall()}
    annee = get_settings(eid).get('annee_scolaire')

    valides, problemes, doublons = [], [], []
    vus = set()
    for brute in lignes:
        v, erreurs = imp.valider_ligne(brute, classes)
        cle = ((v.get('nom') or '').lower(), (v.get('prenom') or '').lower(), v.get('date_naissance') or '')
        if not erreurs and (cle in existants or cle in vus):
            doublons.append({'ligne': brute['_ligne'], 'nom': f"{v['prenom']} {v['nom']}"})
            continue
        if not erreurs and v.get('matricule') and v['matricule'] in matricules:
            erreurs.append(f"Matricule déjà utilisé : {v['matricule']}")
        if erreurs:
            problemes.append({'ligne': brute['_ligne'], 'nom': f"{v.get('prenom', '')} {v.get('nom', '')}".strip(), 'erreurs': erreurs})
            continue
        vus.add(cle)
        if v.get('matricule'):
            matricules.add(v['matricule'])
        valides.append(v)

    resume = {'simulation': simulation, 'lignes_lues': len(lignes), 'a_importer': len(valides),
              'erreurs': problemes, 'doublons': doublons}
    if simulation or not valides:
        return jsonify({**resume, 'importes': 0})

    importes = 0
    with matricule_lock:
        for v in valides:
            champs = {k: val for k, val in v.items() if k != 'matricule'}
            if annee and 'annee_scolaire' not in champs:
                champs['annee_scolaire'] = annee
            matricule = v.get('matricule') or next_sequence('matricule_eleve', 'M', 6, ecole_id=eid)
            cols = ['id', 'ecole_id', 'matricule'] + list(champs)
            db.execute(f"INSERT INTO eleves ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                       [gen_id('e'), eid, matricule] + list(champs.values()))
            importes += 1
        db.commit()
    log_action(g.user, 'creation', 'import_eleves', None, {'importes': importes, 'erreurs': len(problemes), 'doublons': len(doublons)})
    return jsonify({**resume, 'importes': importes})


@bp.route('/eleves/<eleve_id>/attestation', methods=['POST'])
@require_auth
@require_role(*ROLES_ADMINISTRATION)
@require_permission('eleves', 'peut_voir')
def delivrer_attestation(eleve_id):
    """Délivre une attestation de scolarité NUMÉROTÉE (ATT-AAAA-00001) et la trace au journal.
    Seul un élève actif peut en recevoir une."""
    e = db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    if e['statut'] != 'actif':
        return jsonify({'error': "Seul un élève inscrit (statut actif) peut recevoir une attestation de scolarité"}), 400
    aujourdhui = date.today()
    with matricule_lock:
        numero = next_sequence(f'attestation_{aujourdhui.year}', f'ATT-{aujourdhui.year}-', 5, ecole_id=g.user['ecole_id'])
    log_action(g.user, 'creation', 'attestation', eleve_id, {'numero': numero})
    return jsonify({'numero': numero, 'date': aujourdhui.isoformat(), 'eleve': row_to_dict(e)}), 201
