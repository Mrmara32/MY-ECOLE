"""
Module Logistique — gestion des stocks/fournitures, des achats (bons de commande),
de la maintenance des locaux/équipements et du transport scolaire.
"""
from flask import Blueprint, request, jsonify, g
from datetime import datetime

from database import db, gen_id, rows_to_list, row_to_dict, log_action
from auth import require_auth, require_role
from offline_sync import idempotent

bp = Blueprint('logistique_routes', __name__, url_prefix='/api')

LOG_ROLES = ('admin', 'directeur', 'secretaire')
ACHAT_ROLES = ('admin', 'directeur', 'secretaire', 'comptable')


# ─────────────────────────────────────────────────────────────
# STOCK / FOURNITURES
# ─────────────────────────────────────────────────────────────
@bp.route('/stock/produits', methods=['GET'])
@require_auth
def list_stock_produits():
    categorie = request.args.get('categorie')
    sql = "SELECT * FROM stock_produits WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if categorie:
        sql += " AND categorie=?"
        params.append(categorie)
    sql += " ORDER BY nom"
    return jsonify(rows_to_list(db.execute(sql, params).fetchall()))


@bp.route('/stock/produits', methods=['POST'])
@require_auth
@require_role(*LOG_ROLES)
def create_stock_produit():
    body = request.get_json(silent=True) or {}
    nom = (body.get('nom') or '').strip()
    if not nom:
        return jsonify({'error': 'Le nom du produit est requis'}), 400
    categorie = body.get('categorie') or 'materiel'
    if db.execute(
        "SELECT 1 FROM stock_produits WHERE ecole_id=? AND nom=? AND categorie=?", (g.user['ecole_id'], nom, categorie)
    ).fetchone():
        return jsonify({'error': 'Ce produit existe déjà dans cette catégorie'}), 409
    pid = gen_id('prod')
    db.execute(
        "INSERT INTO stock_produits (id,ecole_id,nom,categorie,unite,quantite,seuil_alerte,prix_unitaire,notes) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pid, g.user['ecole_id'], nom, categorie, body.get('unite') or 'unité',
         body.get('quantite') or 0, body.get('seuil_alerte') or 0, body.get('prix_unitaire') or 0, body.get('notes')),
    )
    db.commit()
    log_action(g.user, 'creation', 'stock_produit', pid, {'nom': nom})
    row = db.execute("SELECT * FROM stock_produits WHERE id=?", (pid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/stock/produits/<p_id>', methods=['PUT'])
@require_auth
@require_role(*LOG_ROLES)
def update_stock_produit(p_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM stock_produits WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        """UPDATE stock_produits SET nom=COALESCE(?,nom), categorie=COALESCE(?,categorie), unite=COALESCE(?,unite),
           seuil_alerte=COALESCE(?,seuil_alerte), prix_unitaire=COALESCE(?,prix_unitaire), notes=COALESCE(?,notes)
           WHERE id=? AND ecole_id=?""",
        (body.get('nom'), body.get('categorie'), body.get('unite'), body.get('seuil_alerte'),
         body.get('prix_unitaire'), body.get('notes'), p_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM stock_produits WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/stock/produits/<p_id>', methods=['DELETE'])
@require_auth
@require_role(*LOG_ROLES)
def delete_stock_produit(p_id):
    if not db.execute("SELECT id FROM stock_produits WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    nb = db.execute("SELECT COUNT(*) as c FROM stock_mouvements WHERE produit_id=?", (p_id,)).fetchone()['c']
    if nb > 0:
        return jsonify({'error': f"Impossible : {nb} mouvement(s) de stock lié(s) à ce produit."}), 409
    db.execute("DELETE FROM stock_produits WHERE id=? AND ecole_id=?", (p_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/stock/mouvements', methods=['GET'])
@require_auth
def list_stock_mouvements():
    produit_id = request.args.get('produit_id')
    sql = ("SELECT m.*, p.nom as produit_nom, p.unite as produit_unite FROM stock_mouvements m "
           "JOIN stock_produits p ON p.id=m.produit_id WHERE m.ecole_id=?")
    params = [g.user['ecole_id']]
    if produit_id:
        sql += " AND m.produit_id=?"
        params.append(produit_id)
    sql += " ORDER BY m.date_mouvement DESC, m.created_at DESC LIMIT 300"
    return jsonify(rows_to_list(db.execute(sql, params).fetchall()))


@bp.route('/stock/mouvements', methods=['POST'])
@require_auth
@require_role(*LOG_ROLES)
@idempotent('create_stock_mouvement')
def create_stock_mouvement():
    body = request.get_json(silent=True) or {}
    produit_id = body.get('produit_id')
    type_mvt = body.get('type')
    try:
        quantite = float(body.get('quantite') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Quantité invalide'}), 400
    if not produit_id or type_mvt not in ('entree', 'sortie') or quantite <= 0:
        return jsonify({'error': 'Produit, type (entree/sortie) et quantité (>0) requis'}), 400
    produit = db.execute("SELECT * FROM stock_produits WHERE id=? AND ecole_id=?", (produit_id, g.user['ecole_id'])).fetchone()
    if not produit:
        return jsonify({'error': 'Produit introuvable'}), 404
    if type_mvt == 'sortie' and quantite > produit['quantite']:
        return jsonify({'error': f"Stock insuffisant (disponible : {produit['quantite']} {produit['unite']})"}), 409

    mid = gen_id('mvt')
    db.execute(
        "INSERT INTO stock_mouvements (id,ecole_id,produit_id,type,quantite,motif,date_mouvement,cree_par) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (mid, g.user['ecole_id'], produit_id, type_mvt, quantite, body.get('motif'),
         body.get('date_mouvement') or datetime.now().strftime('%Y-%m-%d'), g.user['id']),
    )
    delta = quantite if type_mvt == 'entree' else -quantite
    db.execute("UPDATE stock_produits SET quantite = quantite + ? WHERE id=?", (delta, produit_id))
    db.commit()
    log_action(g.user, f'mouvement_stock_{type_mvt}', 'stock_produit', produit_id, {'quantite': quantite})
    row = db.execute("SELECT * FROM stock_produits WHERE id=?", (produit_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


# ─────────────────────────────────────────────────────────────
# ACHATS / BONS DE COMMANDE
# ─────────────────────────────────────────────────────────────
def _commande_avec_lignes(c_id, ecole_id):
    c = db.execute("SELECT * FROM commandes WHERE id=? AND ecole_id=?", (c_id, ecole_id)).fetchone()
    if not c:
        return None
    d = row_to_dict(c)
    lignes = db.execute("SELECT * FROM commande_lignes WHERE commande_id=?", (c_id,)).fetchall()
    d['lignes'] = rows_to_list(lignes)
    fournisseur = db.execute("SELECT nom FROM fournisseurs WHERE id=?", (c['fournisseur_id'],)).fetchone() if c['fournisseur_id'] else None
    d['fournisseur_nom'] = fournisseur['nom'] if fournisseur else None
    return d


@bp.route('/commandes', methods=['GET'])
@require_auth
def list_commandes():
    statut = request.args.get('statut')
    sql = "SELECT * FROM commandes WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if statut:
        sql += " AND statut=?"
        params.append(statut)
    sql += " ORDER BY date_commande DESC, created_at DESC"
    commandes = db.execute(sql, params).fetchall()
    result = []
    for c in commandes:
        d = dict(c)
        fournisseur = db.execute("SELECT nom FROM fournisseurs WHERE id=?", (c['fournisseur_id'],)).fetchone() if c['fournisseur_id'] else None
        d['fournisseur_nom'] = fournisseur['nom'] if fournisseur else '—'
        nb_lignes = db.execute("SELECT COUNT(*) as c FROM commande_lignes WHERE commande_id=?", (c['id'],)).fetchone()['c']
        d['nb_lignes'] = nb_lignes
        result.append(d)
    return jsonify(result)


@bp.route('/commandes/<c_id>', methods=['GET'])
@require_auth
def get_commande(c_id):
    d = _commande_avec_lignes(c_id, g.user['ecole_id'])
    if not d:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(d)


@bp.route('/commandes', methods=['POST'])
@require_auth
@require_role(*ACHAT_ROLES)
@idempotent('create_commande')
def create_commande():
    body = request.get_json(silent=True) or {}
    lignes = body.get('lignes') or []
    if not lignes:
        return jsonify({'error': 'Au moins une ligne de commande est requise'}), 400
    cid = gen_id('cmd')
    montant_total = 0
    lignes_valides = []
    for l in lignes:
        designation = (l.get('designation') or '').strip()
        if not designation:
            continue
        quantite = float(l.get('quantite') or 1)
        prix_unitaire = float(l.get('prix_unitaire') or 0)
        montant_ligne = round(quantite * prix_unitaire)
        montant_total += montant_ligne
        lignes_valides.append((l.get('produit_id'), designation, quantite, prix_unitaire, montant_ligne))
    if not lignes_valides:
        return jsonify({'error': 'Au moins une ligne valide (désignation requise) est nécessaire'}), 400

    db.execute(
        "INSERT INTO commandes (id,ecole_id,numero,fournisseur_id,statut,date_commande,montant_total,notes,cree_par) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, g.user['ecole_id'], body.get('numero'), body.get('fournisseur_id'), body.get('statut') or 'brouillon',
         body.get('date_commande') or datetime.now().strftime('%Y-%m-%d'), montant_total, body.get('notes'), g.user['id']),
    )
    for produit_id, designation, quantite, prix_unitaire, montant_ligne in lignes_valides:
        db.execute(
            "INSERT INTO commande_lignes (id,commande_id,produit_id,designation,quantite,prix_unitaire,montant_ligne) "
            "VALUES (?,?,?,?,?,?,?)",
            (gen_id('cl'), cid, produit_id, designation, quantite, prix_unitaire, montant_ligne),
        )
    db.commit()
    log_action(g.user, 'creation', 'commande', cid, {'montant_total': montant_total})
    return jsonify(_commande_avec_lignes(cid, g.user['ecole_id'])), 201


@bp.route('/commandes/<c_id>', methods=['PUT'])
@require_auth
@require_role(*ACHAT_ROLES)
def update_commande(c_id):
    body = request.get_json(silent=True) or {}
    c = db.execute("SELECT * FROM commandes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    if c['statut'] in ('recue', 'annulee') and 'statut' not in body:
        return jsonify({'error': 'Commande déjà finalisée, non modifiable'}), 409
    db.execute(
        "UPDATE commandes SET numero=COALESCE(?,numero), fournisseur_id=COALESCE(?,fournisseur_id), "
        "statut=COALESCE(?,statut), notes=COALESCE(?,notes) WHERE id=? AND ecole_id=?",
        (body.get('numero'), body.get('fournisseur_id'), body.get('statut'), body.get('notes'), c_id, g.user['ecole_id']),
    )
    db.commit()
    return jsonify(_commande_avec_lignes(c_id, g.user['ecole_id']))


@bp.route('/commandes/<c_id>/receptionner', methods=['POST'])
@require_auth
@require_role(*ACHAT_ROLES)
@idempotent('receptionner_commande')
def receptionner_commande(c_id):
    """Marque la commande comme reçue et incrémente automatiquement le stock
    pour chaque ligne reliée à un produit de l'inventaire."""
    c = db.execute("SELECT * FROM commandes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    if c['statut'] == 'recue':
        return jsonify({'error': 'Déjà réceptionnée'}), 409
    lignes = db.execute("SELECT * FROM commande_lignes WHERE commande_id=?", (c_id,)).fetchall()
    for l in lignes:
        if l['produit_id']:
            db.execute(
                "INSERT INTO stock_mouvements (id,ecole_id,produit_id,type,quantite,motif,commande_id,cree_par) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (gen_id('mvt'), g.user['ecole_id'], l['produit_id'], 'entree', l['quantite'],
                 f"Réception commande {c['numero'] or c_id}", c_id, g.user['id']),
            )
            db.execute("UPDATE stock_produits SET quantite = quantite + ? WHERE id=?", (l['quantite'], l['produit_id']))
    db.execute("UPDATE commandes SET statut='recue', date_reception=COALESCE(date_reception, date('now')) WHERE id=?", (c_id,))
    db.commit()
    log_action(g.user, 'reception_commande', 'commande', c_id, {})
    return jsonify(_commande_avec_lignes(c_id, g.user['ecole_id']))


@bp.route('/commandes/<c_id>', methods=['DELETE'])
@require_auth
@require_role(*ACHAT_ROLES)
def delete_commande(c_id):
    c = db.execute("SELECT * FROM commandes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id'])).fetchone()
    if not c:
        return jsonify({'error': 'Introuvable'}), 404
    if c['statut'] == 'recue':
        return jsonify({'error': 'Impossible de supprimer une commande déjà réceptionnée'}), 409
    db.execute("DELETE FROM commandes WHERE id=? AND ecole_id=?", (c_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# MAINTENANCE DES LOCAUX / ÉQUIPEMENTS
# ─────────────────────────────────────────────────────────────
@bp.route('/maintenance', methods=['GET'])
@require_auth
def list_maintenance():
    statut = request.args.get('statut')
    sql = "SELECT * FROM maintenance_interventions WHERE ecole_id=?"
    params = [g.user['ecole_id']]
    if statut:
        sql += " AND statut=?"
        params.append(statut)
    sql += " ORDER BY CASE priorite WHEN 'urgente' THEN 0 WHEN 'haute' THEN 1 WHEN 'normale' THEN 2 ELSE 3 END, date_signalement DESC"
    rows = db.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if r['salle_id']:
            s = db.execute("SELECT nom FROM salles WHERE id=?", (r['salle_id'],)).fetchone()
            d['salle_nom'] = s['nom'] if s else None
        if r['assigne_a']:
            p = db.execute("SELECT nom, prenom FROM personnel WHERE id=?", (r['assigne_a'],)).fetchone()
            d['assigne_nom'] = f"{p['prenom']} {p['nom']}" if p else None
        result.append(d)
    return jsonify(result)


@bp.route('/maintenance', methods=['POST'])
@require_auth
@require_role(*LOG_ROLES)
@idempotent('create_maintenance')
def create_maintenance():
    body = request.get_json(silent=True) or {}
    titre = (body.get('titre') or '').strip()
    if not titre:
        return jsonify({'error': 'Le titre est requis'}), 400
    mid = gen_id('maint')
    db.execute(
        "INSERT INTO maintenance_interventions (id,ecole_id,titre,salle_id,lieu,equipement,description,priorite,"
        "assigne_a,signale_par,date_signalement) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (mid, g.user['ecole_id'], titre, body.get('salle_id'), body.get('lieu'), body.get('equipement'),
         body.get('description'), body.get('priorite') or 'normale', body.get('assigne_a'),
         g.user['id'], body.get('date_signalement') or datetime.now().strftime('%Y-%m-%d')),
    )
    db.commit()
    log_action(g.user, 'creation', 'maintenance', mid, {'titre': titre})
    row = db.execute("SELECT * FROM maintenance_interventions WHERE id=?", (mid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/maintenance/<m_id>', methods=['PUT'])
@require_auth
@require_role(*LOG_ROLES)
def update_maintenance(m_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM maintenance_interventions WHERE id=? AND ecole_id=?", (m_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    nouveau_statut = body.get('statut')
    date_resolution = body.get('date_resolution')
    if nouveau_statut == 'resolue' and not date_resolution:
        date_resolution = None  # laissera COALESCE poser la date via SQL ci-dessous si besoin
    db.execute(
        """UPDATE maintenance_interventions SET titre=COALESCE(?,titre), salle_id=COALESCE(?,salle_id),
           lieu=COALESCE(?,lieu), equipement=COALESCE(?,equipement), description=COALESCE(?,description),
           priorite=COALESCE(?,priorite), statut=COALESCE(?,statut), assigne_a=COALESCE(?,assigne_a),
           cout=COALESCE(?,cout),
           date_resolution=CASE WHEN ?='resolue' AND date_resolution IS NULL THEN date('now') ELSE COALESCE(?,date_resolution) END
           WHERE id=? AND ecole_id=?""",
        (body.get('titre'), body.get('salle_id'), body.get('lieu'), body.get('equipement'), body.get('description'),
         body.get('priorite'), nouveau_statut, body.get('assigne_a'), body.get('cout'),
         nouveau_statut, date_resolution, m_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM maintenance_interventions WHERE id=? AND ecole_id=?", (m_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/maintenance/<m_id>', methods=['DELETE'])
@require_auth
@require_role(*LOG_ROLES)
def delete_maintenance(m_id):
    if not db.execute("SELECT id FROM maintenance_interventions WHERE id=? AND ecole_id=?", (m_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM maintenance_interventions WHERE id=? AND ecole_id=?", (m_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# TRANSPORT SCOLAIRE
# ─────────────────────────────────────────────────────────────
@bp.route('/transport/vehicules', methods=['GET'])
@require_auth
def list_vehicules():
    rows = db.execute("SELECT * FROM transport_vehicules WHERE ecole_id=? ORDER BY immatriculation", (g.user['ecole_id'],)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if r['chauffeur_id']:
            p = db.execute("SELECT nom, prenom FROM personnel WHERE id=?", (r['chauffeur_id'],)).fetchone()
            d['chauffeur_nom'] = f"{p['prenom']} {p['nom']}" if p else None
        result.append(d)
    return jsonify(result)


@bp.route('/transport/vehicules', methods=['POST'])
@require_auth
@require_role(*LOG_ROLES)
@idempotent('create_vehicule')
def create_vehicule():
    body = request.get_json(silent=True) or {}
    immat = (body.get('immatriculation') or '').strip()
    if not immat:
        return jsonify({'error': "L'immatriculation est requise"}), 400
    if db.execute("SELECT 1 FROM transport_vehicules WHERE ecole_id=? AND immatriculation=?", (g.user['ecole_id'], immat)).fetchone():
        return jsonify({'error': 'Ce véhicule existe déjà'}), 409
    vid = gen_id('veh')
    db.execute(
        "INSERT INTO transport_vehicules (id,ecole_id,immatriculation,marque_modele,capacite,statut,chauffeur_id,notes) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (vid, g.user['ecole_id'], immat, body.get('marque_modele'), body.get('capacite') or 0,
         body.get('statut') or 'actif', body.get('chauffeur_id'), body.get('notes')),
    )
    db.commit()
    row = db.execute("SELECT * FROM transport_vehicules WHERE id=?", (vid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/transport/vehicules/<v_id>', methods=['PUT'])
@require_auth
@require_role(*LOG_ROLES)
def update_vehicule(v_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM transport_vehicules WHERE id=? AND ecole_id=?", (v_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        """UPDATE transport_vehicules SET immatriculation=COALESCE(?,immatriculation), marque_modele=COALESCE(?,marque_modele),
           capacite=COALESCE(?,capacite), statut=COALESCE(?,statut), chauffeur_id=COALESCE(?,chauffeur_id), notes=COALESCE(?,notes)
           WHERE id=? AND ecole_id=?""",
        (body.get('immatriculation'), body.get('marque_modele'), body.get('capacite'), body.get('statut'),
         body.get('chauffeur_id'), body.get('notes'), v_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM transport_vehicules WHERE id=? AND ecole_id=?", (v_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/transport/vehicules/<v_id>', methods=['DELETE'])
@require_auth
@require_role(*LOG_ROLES)
def delete_vehicule(v_id):
    if not db.execute("SELECT id FROM transport_vehicules WHERE id=? AND ecole_id=?", (v_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    nb = db.execute("SELECT COUNT(*) as c FROM transport_itineraires WHERE vehicule_id=?", (v_id,)).fetchone()['c']
    if nb > 0:
        return jsonify({'error': f"Impossible : {nb} itinéraire(s) utilisent ce véhicule."}), 409
    db.execute("DELETE FROM transport_vehicules WHERE id=? AND ecole_id=?", (v_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/transport/itineraires', methods=['GET'])
@require_auth
def list_itineraires():
    rows = db.execute("SELECT * FROM transport_itineraires WHERE ecole_id=? ORDER BY nom", (g.user['ecole_id'],)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if r['vehicule_id']:
            v = db.execute("SELECT immatriculation FROM transport_vehicules WHERE id=?", (r['vehicule_id'],)).fetchone()
            d['vehicule_immat'] = v['immatriculation'] if v else None
        d['nb_eleves'] = db.execute("SELECT COUNT(*) as c FROM transport_eleves WHERE itineraire_id=?", (r['id'],)).fetchone()['c']
        result.append(d)
    return jsonify(result)


@bp.route('/transport/itineraires', methods=['POST'])
@require_auth
@require_role(*LOG_ROLES)
@idempotent('create_itineraire')
def create_itineraire():
    body = request.get_json(silent=True) or {}
    nom = (body.get('nom') or '').strip()
    if not nom:
        return jsonify({'error': "Le nom de l'itinéraire est requis"}), 400
    iid = gen_id('itin')
    db.execute(
        "INSERT INTO transport_itineraires (id,ecole_id,nom,zone,vehicule_id,description) VALUES (?,?,?,?,?,?)",
        (iid, g.user['ecole_id'], nom, body.get('zone'), body.get('vehicule_id'), body.get('description')),
    )
    db.commit()
    row = db.execute("SELECT * FROM transport_itineraires WHERE id=?", (iid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/transport/itineraires/<i_id>', methods=['PUT'])
@require_auth
@require_role(*LOG_ROLES)
def update_itineraire(i_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM transport_itineraires WHERE id=? AND ecole_id=?", (i_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute(
        "UPDATE transport_itineraires SET nom=COALESCE(?,nom), zone=COALESCE(?,zone), vehicule_id=COALESCE(?,vehicule_id), "
        "description=COALESCE(?,description) WHERE id=? AND ecole_id=?",
        (body.get('nom'), body.get('zone'), body.get('vehicule_id'), body.get('description'), i_id, g.user['ecole_id']),
    )
    db.commit()
    row = db.execute("SELECT * FROM transport_itineraires WHERE id=? AND ecole_id=?", (i_id, g.user['ecole_id'])).fetchone()
    return jsonify(row_to_dict(row))


@bp.route('/transport/itineraires/<i_id>', methods=['DELETE'])
@require_auth
@require_role(*LOG_ROLES)
def delete_itineraire(i_id):
    if not db.execute("SELECT id FROM transport_itineraires WHERE id=? AND ecole_id=?", (i_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM transport_itineraires WHERE id=? AND ecole_id=?", (i_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})


@bp.route('/transport/eleves', methods=['GET'])
@require_auth
def list_transport_eleves():
    itineraire_id = request.args.get('itineraire_id')
    sql = ("SELECT t.*, e.nom as eleve_nom, e.prenom as eleve_prenom, e.classe as eleve_classe FROM transport_eleves t "
           "JOIN eleves e ON e.id=t.eleve_id WHERE t.ecole_id=?")
    params = [g.user['ecole_id']]
    if itineraire_id:
        sql += " AND t.itineraire_id=?"
        params.append(itineraire_id)
    sql += " ORDER BY e.nom"
    return jsonify(rows_to_list(db.execute(sql, params).fetchall()))


@bp.route('/transport/eleves', methods=['POST'])
@require_auth
@require_role(*LOG_ROLES)
@idempotent('assign_transport_eleve')
def assign_transport_eleve():
    body = request.get_json(silent=True) or {}
    eleve_id, itineraire_id = body.get('eleve_id'), body.get('itineraire_id')
    if not eleve_id or not itineraire_id:
        return jsonify({'error': 'Élève et itinéraire requis'}), 400
    if db.execute("SELECT 1 FROM transport_eleves WHERE itineraire_id=? AND eleve_id=?", (itineraire_id, eleve_id)).fetchone():
        return jsonify({'error': 'Cet élève est déjà affecté à cet itinéraire'}), 409
    tid = gen_id('te')
    db.execute(
        "INSERT INTO transport_eleves (id,ecole_id,eleve_id,itineraire_id,point_montee) VALUES (?,?,?,?,?)",
        (tid, g.user['ecole_id'], eleve_id, itineraire_id, body.get('point_montee')),
    )
    db.commit()
    row = db.execute("SELECT * FROM transport_eleves WHERE id=?", (tid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route('/transport/eleves/<t_id>', methods=['DELETE'])
@require_auth
@require_role(*LOG_ROLES)
def unassign_transport_eleve(t_id):
    if not db.execute("SELECT id FROM transport_eleves WHERE id=? AND ecole_id=?", (t_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("DELETE FROM transport_eleves WHERE id=? AND ecole_id=?", (t_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'success': True})
