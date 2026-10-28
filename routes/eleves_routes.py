import os
import time
import random
import secrets
from flask import Blueprint, request, jsonify, current_app, g

from database import db, gen_id, rows_to_list, row_to_dict, log_action, get_classes_enseignant, matricule_lock, next_sequence, ecole_id_depuis_code, next_numero_recu
from auth import require_auth, require_role
from permissions import require_permission
from offline_sync import idempotent

bp = Blueprint('eleves_routes', __name__, url_prefix='/api/eleves')
bp_verif = Blueprint('badge_verification', __name__)

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
import securite_http


def _minimiser(d):
    """Minimisation des données : chacun ne voit des informations de santé que ce que son rôle exige.
    Direction et secrétariat : tout. Enseignant : l'essentiel pour la sécurité de l'élève (allergies,
    maladies chroniques, handicap, médicaments). Comptable et autres : aucune donnée de santé."""
    role = g.user['role']
    if role in ('admin', 'directeur', 'secretaire'):
        return d
    gardes = ('allergies', 'maladies_chroniques', 'handicap', 'medicaments') if role == 'enseignant' else ()
    for c in FIELDS_SANTE:
        if c in d and c not in gardes:
            d[c] = None
    return d


def next_matricule():
    return next_sequence('matricule_eleve', 'M', 6, ecole_id=g.user['ecole_id'])


@bp.route('', methods=['GET'])
@require_auth
@require_permission('eleves', 'peut_voir')
def list_eleves():
    classe = request.args.get('classe')
    statut = request.args.get('statut')
    annee_scolaire = request.args.get('annee_scolaire')
    q = request.args.get('q')

    sql = "SELECT * FROM eleves WHERE ecole_id=?"
    params = [g.user['ecole_id']]

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
    return jsonify([_minimiser(d) for d in rows_to_list(rows)])


@bp.route('/meta/classes', methods=['GET'])
@require_auth
def meta_classes():
    rows = db.execute(
        "SELECT DISTINCT classe FROM eleves WHERE classe IS NOT NULL AND ecole_id=? ORDER BY classe",
        (g.user['ecole_id'],)
    ).fetchall()
    return jsonify([r['classe'] for r in rows])


@bp.route('/<eleve_id>', methods=['GET'])
@require_auth
@require_permission('eleves', 'peut_voir')
def get_eleve(eleve_id):
    row = db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not row:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify(_minimiser(row_to_dict(row)))


ROLES_INSCRIPTION_DIRECTE = ('admin', 'directeur', 'secretaire', 'comptable')


@bp.route('/preinscription-publique', methods=['POST'])
def preinscription_publique():
    """Formulaire PUBLIC (sans connexion) permettant à n'importe quel parent de
    préinscrire son enfant depuis le site vitrine de l'école. L'élève reste en
    statut 'preinscrit' tant que le comptable n'a pas validé le paiement."""
    body = request.get_json(silent=True) or {}
    import conditions
    refus = conditions.acceptation_manquante(body)
    if refus:
        return refus
    nom, prenom = body.get('nom'), body.get('prenom')
    if not nom or not prenom:
        return jsonify({'error': 'Nom et prénom requis'}), 400

    eid = gen_id('e')
    ecole_id = ecole_id_depuis_code(body.get('code_ecole') or request.args.get('ecole'))
    conditions.journaliser(ecole_id, f"{prenom} {nom}", 'préinscription élève')
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
            matricule = next_sequence('matricule_eleve', 'M', 6, ecole_id=ecole_id)
            cols = ['id', 'ecole_id', 'matricule', 'nom', 'prenom'] + list(provided.keys())
            vals = [eid, ecole_id, matricule, nom, prenom] + list(provided.values())
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
@require_permission('eleves', 'peut_creer')
@idempotent('create_eleve')
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
            cols = ['id', 'ecole_id', 'matricule'] + list(provided.keys())
            vals = [eid, g.user['ecole_id'], matricule] + list(provided.values())
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
    e = db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not e:
        return jsonify({'error': 'Introuvable'}), 404
    if e['statut'] != 'preinscrit':
        return jsonify({'error': "Cet élève n'est pas en attente de préinscription"}), 400

    db.execute("UPDATE eleves SET statut='actif' WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'validation_preinscription', 'eleve', eleve_id,
               {'nom': e['nom'], 'prenom': e['prenom'], 'montant_paye': body.get('montant')})

    # Si un montant de paiement d'inscription est précisé, on enregistre la transaction correspondante
    try:
        montant = float(body.get('montant')) if body.get('montant') not in (None, '') else None
    except (TypeError, ValueError):
        montant = None
    numero_recu = None
    if montant and montant > 0:
        tid = gen_id('t')
        date_op = body.get('date_paiement') or __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        numero_recu = (body.get('reference') or '').strip() or next_numero_recu(g.user['ecole_id'])
        # ecole_id précisé : sans lui, la recette tombait dans la comptabilité de l'école n°1.
        db.execute(
            "INSERT INTO transactions (id,ecole_id,type,date_op,description,categorie,moyen_paiement,montant,reference,eleve_id,cree_par,statut_validation) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, g.user['ecole_id'], 'entree', date_op, f"Frais d'inscription — {e['prenom']} {e['nom']} ({e['matricule']})",
             "Frais d'inscription", body.get('moyen_paiement', 'Espèces'), montant,
             numero_recu, eleve_id, g.user['id'], 'auto'),
        )
        db.commit()

    row = db.execute("SELECT * FROM eleves WHERE id=?", (eleve_id,)).fetchone()
    resultat = row_to_dict(row)
    if numero_recu:
        resultat['numero_recu'] = numero_recu
    return jsonify(resultat)


@bp.route('/<eleve_id>', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'comptable')
@require_permission('eleves', 'peut_modifier')
def update_eleve(eleve_id):
    body = request.get_json(silent=True) or {}
    if not db.execute("SELECT id FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Introuvable'}), 404

    sets, vals = [], []
    for f in ALL_FIELDS:
        if f in body:
            sets.append(f"{f}=?")
            vals.append(body[f])
    if sets:
        vals.append(eleve_id)
        vals.append(g.user['ecole_id'])
        db.execute(f"UPDATE eleves SET {','.join(sets)} WHERE id=? AND ecole_id=?", vals)
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
    if ext not in ALLOWED_EXT or not securite_http.est_image(file):
        return jsonify({'error': 'Format non supporté : le fichier doit être une vraie image (PNG, JPEG, GIF ou WebP)'}), 400

    if not db.execute("SELECT id FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone():
        return jsonify({'error': 'Élève introuvable'}), 404

    fname = f"e{g.user['ecole_id']}_{secrets.token_hex(12)}{ext}"
    upload_dir = current_app.config['UPLOAD_DIR']
    file.save(os.path.join(upload_dir, fname))

    url = '/uploads/' + fname
    db.execute("UPDATE eleves SET photo_url=? WHERE id=? AND ecole_id=?", (url, eleve_id, g.user['ecole_id']))
    db.commit()
    return jsonify({'photo_url': url})


@bp.route('/<eleve_id>', methods=['DELETE'])
@require_auth
@require_role('admin', 'directeur', 'secretaire')
@require_permission('eleves', 'peut_supprimer')
def delete_eleve(eleve_id):
    existing = db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()
    if not existing:
        return jsonify({'error': 'Introuvable'}), 404
    from database import eleve_a_des_operations
    avec_operations = eleve_a_des_operations(g.user['ecole_id'], eleve_id)
    if avec_operations and g.user['role'] != 'admin':
        return jsonify({'error': "Seul l'administrateur de l'école peut supprimer un enregistrement qui a déjà fait l'objet d'une transaction. Archivez plutôt l'élève (statut inactif)."}), 403
    db.execute("DELETE FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id']))
    db.commit()
    log_action(g.user, 'suppression', 'eleve', eleve_id, {'nom': existing['nom'], 'prenom': existing['prenom'],
                                                          'matricule': existing['matricule'], 'avec_operations': avec_operations})
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────
# BADGE ÉLÈVE SÉCURISÉ : QR signé + page publique de vérification
# ─────────────────────────────────────────────────────────────
def _signature_badge_eleve(ecole_id, eleve_id, annee):
    import hmac, hashlib
    from auth import get_secret
    msg = f"badge-eleve|{ecole_id}|{eleve_id}|{annee}".encode()
    return hmac.new(get_secret().encode(), msg, hashlib.sha256).hexdigest()[:16]


def _fin_annee_scolaire(annee):
    """« 2026-2027 » -> 31/07/2027 (fin d'année scolaire ; sinon 31/07 de l'année suivante)."""
    import re
    from datetime import date
    m = re.search(r'(\d{4})\D+(\d{4})', annee or '')
    an = int(m.group(2)) if m else date.today().year + 1
    return f"{an}-07-31"


@bp.route('/<eleve_id>/badge-securise', methods=['GET'])
@require_auth
@require_role('admin', 'directeur', 'secretaire', 'comptable')
def badge_securise(eleve_id):
    import segno
    from database import get_settings
    ecole_id = g.user['ecole_id']
    e = db.execute("SELECT id, matricule, annee_scolaire FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, ecole_id)).fetchone()
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    annee = e['annee_scolaire'] or get_settings(ecole_id).get('annee_scolaire') or ''
    sig = _signature_badge_eleve(ecole_id, e['id'], annee)
    url = f"{request.host_url.rstrip('/')}/v/{ecole_id}/{sig[:12]}"      # court : QR peu dense, lisible même petit
    qr = segno.make(url, error='m', micro=False)
    return jsonify({
        'annee': annee, 'signature': sig, 'url': url, 'expire': _fin_annee_scolaire(annee),
        'code_controle': '-'.join(sig[i:i + 4] for i in (0, 4, 8)).upper(),
        'numero': f"{ecole_id:02d}-{(annee or '0000')[:4]}-{(e['matricule'] or e['id'])[-6:]}".upper(),
        'qr_svg': qr.svg_inline(scale=6, border=0, dark='#000', light=None, omitsize=False),
    })


@bp_verif.route('/api/verifier-badge/<int:ecole_id>/<eleve_id>/<annee>/<sig>', methods=['GET'])
def verifier_badge_api(ecole_id, eleve_id, annee, sig):
    import hmac
    from datetime import date
    from database import get_settings
    annee = '' if annee == '-' else annee
    if request.endpoint == 'badge_verification.verifier_badge_api' and _trop_de_tentatives():
        return jsonify({'valide': False, 'motif': 'Trop de vérifications. Réessayez dans une minute.'}), 429
    if not hmac.compare_digest(sig, _signature_badge_eleve(ecole_id, eleve_id, annee)):
        return jsonify({'valide': False, 'motif': 'Signature invalide : ce badge est un faux ou a été falsifié.'}), 200
    e = db.execute("SELECT nom, prenom, classe, matricule, statut FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, ecole_id)).fetchone()
    if not e:
        return jsonify({'valide': False, 'motif': "Cet élève n'existe plus dans l'établissement."}), 200
    if (e['statut'] or 'actif') not in ('actif', 'reinscrit', 'reinsrit'):
        return jsonify({'valide': False, 'motif': "L'élève n'est plus inscrit dans l'établissement."}), 200
    expire = _fin_annee_scolaire(annee)
    expire_ok = date.today().isoformat() <= expire
    st = get_settings(ecole_id)
    return jsonify({
        'valide': expire_ok, 'motif': None if expire_ok else 'Badge expiré (année scolaire terminée).',
        'ecole': st.get('ecole_nom') or '', 'nom': e['nom'], 'prenom': e['prenom'],
        'classe': e['classe'], 'matricule': e['matricule'], 'annee': annee, 'expire': expire,
    })


_tentatives_verif = {}


def _trop_de_tentatives():
    """Limite simple : 30 vérifications par minute et par adresse (anti devinette)."""
    import time
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    maintenant = time.time()
    recents = [t for t in _tentatives_verif.get(ip, []) if maintenant - t < 60]
    recents.append(maintenant)
    _tentatives_verif[ip] = recents
    if len(_tentatives_verif) > 5000:
        _tentatives_verif.clear()
    return len(recents) > 30


@bp_verif.route('/api/verifier-badge-code', methods=['GET'])
def verifier_badge_par_code():
    """Vérification à la main depuis le site vitrine : matricule + code de contrôle imprimés sur le badge."""
    from database import ecole_id_depuis_code, get_settings
    if _trop_de_tentatives():
        return jsonify({'valide': False, 'motif': 'Trop de vérifications. Réessayez dans une minute.'}), 429
    ecole_id = ecole_id_depuis_code(request.args.get('ecole'))
    code = ''.join(c for c in (request.args.get('code') or '').lower() if c in '0123456789abcdef')
    if len(code) != 12:
        return jsonify({'valide': False, 'motif': 'Saisissez le code de contrôle complet imprimé au verso du badge (12 caractères, ex : A1B2-C3D4-E5F6).'}), 400
    return _verifier_par_code(ecole_id, code, (request.args.get('matricule') or '').strip())


def _verifier_par_code(ecole_id, code, matricule=''):
    from database import get_settings
    annee_defaut = get_settings(ecole_id).get('annee_scolaire') or ''
    sql, params = "SELECT id, annee_scolaire FROM eleves WHERE ecole_id=?", [ecole_id]
    if matricule:
        sql += " AND UPPER(matricule)=UPPER(?)"
        params.append(matricule)
    for e in db.execute(sql, params).fetchall():
        annee = e['annee_scolaire'] or annee_defaut
        sig = _signature_badge_eleve(ecole_id, e['id'], annee)
        if sig[:12] == code:
            return verifier_badge_api(ecole_id, e['id'], annee or '-', sig)
    return jsonify({'valide': False, 'motif': "Ce code ne correspond à aucun badge de l'établissement : le badge est faux ou a été modifié."})


@bp_verif.route('/api/v/<int:ecole_id>/<code>', methods=['GET'])
def verifier_court_api(ecole_id, code):
    if _trop_de_tentatives():
        return jsonify({'valide': False, 'motif': 'Trop de vérifications. Réessayez dans une minute.'}), 429
    return _verifier_par_code(ecole_id, ''.join(c for c in code.lower() if c in '0123456789abcdef')[:12])


@bp_verif.route('/v/<int:ecole_id>/<code>', methods=['GET'])
def verifier_court_page(ecole_id, code):
    """Cible du QR code du badge : page publique de vérification."""
    r = verifier_court_api(ecole_id, code).get_json()
    return _page_verification(ecole_id, r)


@bp_verif.route('/verifier-badge/<int:ecole_id>/<eleve_id>/<annee>/<sig>', methods=['GET'])
def verifier_badge_page(ecole_id, eleve_id, annee, sig):
    """Page publique ouverte quand on scanne le QR du badge avec un téléphone."""
    from html import escape
    return _page_verification(ecole_id, verifier_badge_api(ecole_id, eleve_id, annee, sig).get_json())


def _page_verification(ecole_id, r):
    from html import escape
    from database import get_settings
    st_ = get_settings(ecole_id)
    logo = f"<img src='{escape(st_['ecole_logo'])}' alt='' style='height:70px;margin-bottom:10px'>" if st_.get('ecole_logo') else ''
    if r.get('valide'):
        corps = (f"<div class='ok'>✔ Badge authentique</div><h1>{escape(r['prenom'] or '')} {escape((r['nom'] or '').upper())}</h1>"
                 f"<p>Classe : <b>{escape(r['classe'] or '—')}</b></p><p>Matricule : <b>{escape(r['matricule'] or '—')}</b></p>"
                 f"<p>{escape(r['ecole'])}</p><p>Année scolaire {escape(r['annee'])} — valable jusqu'au {escape(r['expire'])}</p>")
    else:
        corps = f"<div class='ko'>✖ Badge non valide</div><p>{escape(r.get('motif') or '')}</p>"
        if r.get('ecole'):
            corps += f"<p>{escape(r['ecole'])}</p>"
    page = ("<!DOCTYPE html><html lang='fr'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Vérification du badge</title><style>body{font-family:Arial,sans-serif;background:#f3f4f6;margin:0;padding:24px;text-align:center;color:#111}"
            ".c{max-width:380px;margin:30px auto;background:#fff;border-radius:14px;padding:26px;box-shadow:0 4px 18px rgba(0,0,0,.12)}"
            ".ok{background:#16a34a;color:#fff;padding:10px;border-radius:8px;font-weight:700}.ko{background:#dc2626;color:#fff;padding:10px;border-radius:8px;font-weight:700}"
            "h1{font-size:22px;margin:18px 0 6px}p{margin:6px 0;color:#374151}</style></head><body><div class='c'>" + logo + corps + "<p style='margin-top:18px'><a href='/vitrine' style='color:#0f7a6c'>Retour au site de l'école</a></p></div></body></html>")
    from flask import make_response
    resp = make_response(page)
    resp.headers['Cache-Control'] = 'no-store'
    return resp
