"""
Pointage biométrique / par badge des élèves, enseignants et personnel administratif.

Principe : l'appareil (ou le petit programme relais installé dans l'école) envoie
seulement « le numéro N est passé à telle heure ». L'application associe ce numéro à une
fiche (élève ou personnel), en déduit arrivée / départ / retard / absence, et ne stocke
jamais d'empreinte ni de visage.

Deux façons d'envoyer les passages :
  1. POST /api/pointage/passages  — avec la clé secrète de l'appareil (programme relais,
     ou tout appareil capable d'appeler une adresse web).
  2. /iclock/...                  — protocole « push » standard des terminaux ZKTeco :
     l'appareil s'annonce avec son numéro de série (à enregistrer dans l'application).
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, Response, g, jsonify, request

from auth import require_auth, require_role
from contact_parent import COLONNES_CONTACT, contact_a_prevenir
from database import db, gen_id, log_action, rows_to_list

bp = Blueprint('pointage_routes', __name__, url_prefix='/api/pointage')
bp_zk = Blueprint('pointage_zk_routes', __name__)

ROLES_GESTION = ('admin', 'directeur')
ROLES_CONSULTATION = ('admin', 'directeur', 'secretaire')

PARAMETRES_DEFAUT = {
    'pointage_eleves_heure_debut': '08:00',
    'pointage_eleves_tolerance_min': '15',
    'pointage_personnel_heure_debut': '08:00',
    'pointage_personnel_tolerance_min': '10',
}
ECART_MINIMUM_DEPART_MIN = 30   # un 2e passage moins de 30 min après le 1er n'est pas un départ


# ───────────────────────── utilitaires ─────────────────────────
def normaliser_code(code):
    """Les appareils numérotent parfois « 00042 » : on compare toujours « 42 »."""
    c = str(code or '').strip()
    return str(int(c)) if c.isdigit() else c


def normaliser_horodatage(valeur):
    """'2026-10-20 07:52:10' ou '2026-10-20T07:52' → '2026-10-20 07:52:10'. None si invalide."""
    v = str(valeur or '').strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(v[:19] if fmt.endswith('%S') else v[:16], fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


def _minutes(hhmm):
    try:
        h, m = str(hhmm).split(':')[:2]
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return 8 * 60


def _hm(horodatage):
    return horodatage[11:16]


def _parametres(ecole_id):
    lignes = {r['cle']: r['valeur'] for r in db.execute(
        "SELECT cle, valeur FROM settings WHERE ecole_id=? AND cle LIKE 'pointage_%'", (ecole_id,)).fetchall()}
    return {k: lignes.get(k) or v for k, v in PARAMETRES_DEFAUT.items()}


def _limite_retard(parametres, categorie):
    """Heure limite (en minutes depuis minuit) après laquelle l'arrivée compte comme un retard."""
    cle = 'eleves' if categorie == 'eleve' else 'personnel'
    try:
        tolerance = int(parametres[f'pointage_{cle}_tolerance_min'])
    except (TypeError, ValueError):
        tolerance = 15
    return _minutes(parametres[f'pointage_{cle}_heure_debut']) + tolerance


def _hash_cle(cle):
    return hashlib.sha256(cle.encode('utf-8')).hexdigest()


def _appareil_par_cle(cle):
    if not cle:
        return None
    candidat = _hash_cle(cle)
    for a in db.execute("SELECT * FROM appareils_pointage WHERE actif=1 AND cle_hash IS NOT NULL").fetchall():
        if hmac.compare_digest(a['cle_hash'], candidat):
            return a
    return None


def _jour_suivant(date):
    return (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')


def _date_valide(date):
    try:
        datetime.strptime(date or '', '%Y-%m-%d')
        return date
    except ValueError:
        return None


# ───────────────────────── enregistrement des passages ─────────────────────────
def enregistrer_passages(ecole_id, appareil_id, passages):
    """Enregistre une liste de (code, horodatage). Idempotent : un passage déjà reçu est
    ignoré. Crée au passage les retards des élèves arrivés après l'heure limite.
    Renvoie un dict de compteurs."""
    maintenant_max = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    res = {'recus': 0, 'nouveaux': 0, 'doublons': 0, 'invalides': 0, 'inconnus': 0, 'retards_crees': 0}
    jours_touches = set()
    codes_inconnus = set()
    codes = {r['code']: (r['personne_type'], r['personne_id']) for r in db.execute(
        "SELECT code, personne_type, personne_id FROM codes_pointage WHERE ecole_id=?", (ecole_id,)).fetchall()}

    for code_brut, horodatage_brut in passages:
        res['recus'] += 1
        code, horo = normaliser_code(code_brut), normaliser_horodatage(horodatage_brut)
        if not code or not horo or horo > maintenant_max:
            res['invalides'] += 1
            continue
        cur = db.execute(
            "INSERT OR IGNORE INTO pointages (ecole_id,id,appareil_id,code,horodatage,source) VALUES (?,?,?,?,?, 'appareil')",
            (ecole_id, gen_id('pt'), appareil_id, code, horo))
        if cur.rowcount == 0:
            res['doublons'] += 1
            continue
        res['nouveaux'] += 1
        jours_touches.add(horo[:10])
        if code not in codes:
            codes_inconnus.add(code)
    res['inconnus'] = len(codes_inconnus)

    for jour in sorted(jours_touches):
        res['retards_crees'] += _creer_retards_du_jour(ecole_id, jour)
    return res


def _creer_retards_du_jour(ecole_id, jour):
    """Pour chaque élève dont la PREMIÈRE arrivée du jour dépasse l'heure limite, crée un
    « retard » (sauf si une absence ou un retard est déjà enregistré ce jour-là)."""
    limite = _limite_retard(_parametres(ecole_id), 'eleve')
    premieres = _premieres_arrivees(ecole_id, jour, 'eleve')
    if not premieres:
        deja = set()
    else:
        deja = {r['eleve_id'] for r in db.execute(
            "SELECT eleve_id FROM absences WHERE ecole_id=? AND date_abs=?", (ecole_id, jour)).fetchall()}
    crees = 0
    for eleve_id, horo in premieres.items():
        if eleve_id in deja or _minutes(_hm(horo)) <= limite:
            continue
        existe = db.execute("SELECT 1 FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, ecole_id)).fetchone()
        if not existe:
            continue
        db.execute(
            "INSERT INTO absences (id,ecole_id,eleve_id,date_abs,type,justifie,motif,duree) VALUES (?,?,?,?,?,?,?,?)",
            (gen_id('abs'), ecole_id, eleve_id, jour, 'retard', 0, f"Pointage : arrivé à {_hm(horo)}", 'retard'))
        crees += 1
    return crees


def _passages_du_jour(ecole_id, jour):
    """{(type, personne_id): [horodatages triés]} pour la journée, codes résolus."""
    codes = {r['code']: (r['personne_type'], r['personne_id']) for r in db.execute(
        "SELECT code, personne_type, personne_id FROM codes_pointage WHERE ecole_id=?", (ecole_id,)).fetchall()}
    par_personne = {}
    for r in db.execute(
            "SELECT code, horodatage, personne_type, personne_id FROM pointages "
            "WHERE ecole_id=? AND horodatage>=? AND horodatage<? ORDER BY horodatage",
            (ecole_id, jour + ' 00:00:00', _jour_suivant(jour) + ' 00:00:00')).fetchall():
        cible = (r['personne_type'], r['personne_id']) if r['personne_id'] else codes.get(r['code'])
        if cible:
            par_personne.setdefault(cible, []).append(r['horodatage'])
    return par_personne


def _premieres_arrivees(ecole_id, jour, categorie):
    return {pid: h[0] for (t, pid), h in _passages_du_jour(ecole_id, jour).items() if t == categorie}


def _arrivee_depart(horodatages):
    premiere, derniere = horodatages[0], horodatages[-1]
    ecart = (datetime.strptime(derniere, '%Y-%m-%d %H:%M:%S') - datetime.strptime(premiere, '%Y-%m-%d %H:%M:%S'))
    depart = derniere if ecart >= timedelta(minutes=ECART_MINIMUM_DEPART_MIN) else None
    return premiere, depart


def heures_pointees(ecole_id, personnel_id, mois):
    """Heures de présence d'un membre du personnel sur un mois 'YYYY-MM' :
    pour chaque jour, dernier passage − premier passage (si l'écart atteint le minimum)."""
    codes = {r['code']: (r['personne_type'], r['personne_id']) for r in db.execute(
        "SELECT code, personne_type, personne_id FROM codes_pointage WHERE ecole_id=?", (ecole_id,)).fetchall()}
    par_jour = {}
    for r in db.execute("SELECT code, horodatage, personne_type, personne_id FROM pointages "
                        "WHERE ecole_id=? AND substr(horodatage,1,7)=? ORDER BY horodatage",
                        (ecole_id, mois)).fetchall():
        cible = (r['personne_type'], r['personne_id']) if r['personne_id'] else codes.get(r['code'])
        if cible == ('personnel', personnel_id):
            par_jour.setdefault(r['horodatage'][:10], []).append(r['horodatage'])
    total = 0.0
    fmt = '%Y-%m-%d %H:%M:%S'
    for h in par_jour.values():
        _, depart = _arrivee_depart(h)
        if depart:
            total += (datetime.strptime(depart, fmt) - datetime.strptime(h[0], fmt)).total_seconds() / 3600
    return round(total, 2)


# ───────────────────────── 1) envoi par clé d'appareil ─────────────────────────
@bp.route('/passages', methods=['POST'])
def recevoir_passages():
    """Appelé par l'appareil ou le programme relais. En-tête : X-Cle-Appareil.
    Corps : {"passages": [{"code": "42", "horodatage": "2026-10-20 07:52:10"}, ...]}"""
    appareil = _appareil_par_cle(request.headers.get('X-Cle-Appareil', '').strip())
    if not appareil:
        return jsonify({'error': 'Clé d\'appareil invalide'}), 401
    body = request.get_json(silent=True) or {}
    liste = body.get('passages')
    if not isinstance(liste, list):
        return jsonify({'error': 'Liste « passages » requise'}), 400
    if len(liste) > 5000:
        return jsonify({'error': '5000 passages maximum par envoi'}), 400
    passages = [(p.get('code'), p.get('horodatage')) for p in liste if isinstance(p, dict)]
    res = enregistrer_passages(appareil['ecole_id'], appareil['id'], passages)
    db.execute("UPDATE appareils_pointage SET derniere_activite=? WHERE id=?",
               (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), appareil['id']))
    db.commit()
    return jsonify(res)


# ───────────────────────── 2) protocole « push » ZKTeco ─────────────────────────
def _appareil_zk():
    serie = (request.args.get('SN') or '').strip()
    if not serie:
        return None
    return db.execute("SELECT * FROM appareils_pointage WHERE actif=1 AND numero_serie=?", (serie,)).fetchone()


def _texte(contenu, code=200):
    return Response(contenu, status=code, mimetype='text/plain')


@bp_zk.route('/iclock/cdata', methods=['GET', 'POST'])
def zk_cdata():
    appareil = _appareil_zk()
    if not appareil:
        return _texte('UNKNOWN DEVICE', 403)
    if request.method == 'GET':
        # Poignée de main : l'appareil demande ses réglages d'envoi.
        return _texte(
            f"GET OPTION FROM: {appareil['numero_serie']}\n"
            "ATTLOGStamp=None\nOPERLOGStamp=9999\nATTPHOTOStamp=None\nErrorDelay=30\nDelay=10\n"
            "TransTimes=00:00;14:05\nTransInterval=1\n"
            "TransFlag=TransData AttLog\tOpLog\tAttPhoto\tEnrollUser\tChgUser\tEnrollFP\tChgFP\tUserPic\n"
            "TimeZone=0\nRealtime=1\nEncrypt=None\n")
    if (request.args.get('table') or '').upper() == 'ATTLOG':
        passages = []
        for ligne in request.get_data(as_text=True).splitlines():
            champs = ligne.strip().split('\t')
            if len(champs) >= 2 and champs[0].strip():
                passages.append((champs[0], champs[1]))
        enregistrer_passages(appareil['ecole_id'], appareil['id'], passages)
    # (OPERLOG, photos, etc. : accusé de réception sans traitement)
    db.execute("UPDATE appareils_pointage SET derniere_activite=? WHERE id=?",
               (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), appareil['id']))
    db.commit()
    return _texte('OK')


@bp_zk.route('/iclock/getrequest', methods=['GET'])
def zk_getrequest():
    return _texte('OK') if _appareil_zk() else _texte('UNKNOWN DEVICE', 403)


@bp_zk.route('/iclock/devicecmd', methods=['POST'])
def zk_devicecmd():
    return _texte('OK') if _appareil_zk() else _texte('UNKNOWN DEVICE', 403)


# ───────────────────────── appareils ─────────────────────────
@bp.route('/appareils', methods=['GET'])
@require_auth
@require_role(*ROLES_GESTION)
def lister_appareils():
    rows = db.execute(
        "SELECT id, nom, numero_serie, actif, derniere_activite, created_at, (cle_hash IS NOT NULL) AS a_une_cle "
        "FROM appareils_pointage WHERE ecole_id=? ORDER BY created_at", (g.user['ecole_id'],)).fetchall()
    return jsonify(rows_to_list(rows))


@bp.route('/appareils', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
def creer_appareil():
    body = request.get_json(silent=True) or {}
    nom = (body.get('nom') or '').strip()
    serie = (body.get('numero_serie') or '').strip() or None
    if not nom:
        return jsonify({'error': 'Nom de l\'appareil requis'}), 400
    if serie and db.execute("SELECT 1 FROM appareils_pointage WHERE numero_serie=?", (serie,)).fetchone():
        return jsonify({'error': 'Ce numéro de série est déjà enregistré'}), 409
    cle = secrets.token_urlsafe(24)
    aid = gen_id('app')
    db.execute("INSERT INTO appareils_pointage (ecole_id,id,nom,numero_serie,cle_hash) VALUES (?,?,?,?,?)",
               (g.user['ecole_id'], aid, nom, serie, _hash_cle(cle)))
    db.commit()
    log_action(g.user, 'creation', 'appareil_pointage', aid, {'nom': nom, 'numero_serie': serie})
    # La clé n'est montrée qu'UNE fois : seule son empreinte est conservée.
    return jsonify({'id': aid, 'nom': nom, 'numero_serie': serie, 'cle': cle}), 201


@bp.route('/appareils/<aid>', methods=['PUT'])
@require_auth
@require_role(*ROLES_GESTION)
def modifier_appareil(aid):
    body = request.get_json(silent=True) or {}
    appareil = db.execute("SELECT * FROM appareils_pointage WHERE id=? AND ecole_id=?", (aid, g.user['ecole_id'])).fetchone()
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404
    nom = (body.get('nom') or appareil['nom']).strip()
    actif = appareil['actif'] if body.get('actif') is None else (1 if body.get('actif') else 0)
    db.execute("UPDATE appareils_pointage SET nom=?, actif=? WHERE id=?", (nom, actif, aid))
    reponse = {'ok': True}
    if body.get('regenerer_cle'):
        cle = secrets.token_urlsafe(24)
        db.execute("UPDATE appareils_pointage SET cle_hash=? WHERE id=?", (_hash_cle(cle), aid))
        reponse['cle'] = cle
    db.commit()
    log_action(g.user, 'modification', 'appareil_pointage', aid,
               {'nom': nom, 'actif': actif, 'cle_regeneree': bool(body.get('regenerer_cle'))})
    return jsonify(reponse)


@bp.route('/appareils/<aid>', methods=['DELETE'])
@require_auth
@require_role(*ROLES_GESTION)
def supprimer_appareil(aid):
    cur = db.execute("DELETE FROM appareils_pointage WHERE id=? AND ecole_id=?", (aid, g.user['ecole_id']))
    db.commit()
    if not cur.rowcount:
        return jsonify({'error': 'Appareil introuvable'}), 404
    log_action(g.user, 'suppression', 'appareil_pointage', aid)
    return jsonify({'ok': True})


# ───────────────────────── numéros ↔ fiches ─────────────────────────
@bp.route('/personnes', methods=['GET'])
@require_auth
@require_role(*ROLES_GESTION)
def lister_personnes():
    """Élèves ou personnel avec leur numéro de pointage (s'il existe)."""
    type_ = request.args.get('type', 'eleve')
    ecole_id = g.user['ecole_id']
    if type_ == 'personnel':
        sql = ("SELECT p.id, p.nom, p.prenom, p.poste AS detail, c.code FROM personnel p "
               "LEFT JOIN codes_pointage c ON c.ecole_id=p.ecole_id AND c.personne_type='personnel' AND c.personne_id=p.id "
               "WHERE p.ecole_id=? ORDER BY p.nom, p.prenom")
        params = [ecole_id]
    else:
        sql = ("SELECT e.id, e.nom, e.prenom, e.classe AS detail, c.code FROM eleves e "
               "LEFT JOIN codes_pointage c ON c.ecole_id=e.ecole_id AND c.personne_type='eleve' AND c.personne_id=e.id "
               "WHERE e.ecole_id=? AND COALESCE(e.statut,'actif') IN ('actif','reinsrit')")
        params = [ecole_id]
        if request.args.get('classe'):
            sql += " AND e.classe=?"
            params.append(request.args['classe'])
        sql += " ORDER BY e.classe, e.nom, e.prenom"
    return jsonify(rows_to_list(db.execute(sql, params).fetchall()))


@bp.route('/codes', methods=['PUT'])
@require_auth
@require_role(*ROLES_GESTION)
def definir_code():
    """Associe (ou retire, si code vide) le numéro de pointage d'une personne."""
    body = request.get_json(silent=True) or {}
    type_, pid = body.get('personne_type'), body.get('personne_id')
    code = normaliser_code(body.get('code'))
    ecole_id = g.user['ecole_id']
    table = {'eleve': 'eleves', 'personnel': 'personnel'}.get(type_)
    if not table or not pid or not db.execute(f"SELECT 1 FROM {table} WHERE id=? AND ecole_id=?", (pid, ecole_id)).fetchone():
        return jsonify({'error': 'Personne introuvable'}), 404
    db.execute("DELETE FROM codes_pointage WHERE ecole_id=? AND personne_type=? AND personne_id=?", (ecole_id, type_, pid))
    if code:
        autre = db.execute("SELECT personne_type, personne_id FROM codes_pointage WHERE ecole_id=? AND code=?",
                           (ecole_id, code)).fetchone()
        if autre:
            db.rollback()
            return jsonify({'error': f"Le numéro {code} est déjà attribué à une autre personne"}), 409
        db.execute("INSERT INTO codes_pointage (ecole_id,code,personne_type,personne_id) VALUES (?,?,?,?)",
                   (ecole_id, code, type_, pid))
    db.commit()
    # Des passages déjà reçus sous ce numéro peuvent maintenant être rattachés : rien à
    # recalculer, le rapport du jour résout les numéros à la lecture.
    return jsonify({'ok': True, 'code': code or None})


@bp.route('/codes/auto', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
def attribuer_codes_automatiquement():
    """Donne un numéro libre (à saisir ensuite dans l'appareil) à tous ceux qui n'en ont pas."""
    type_ = (request.get_json(silent=True) or {}).get('type', 'eleve')
    ecole_id = g.user['ecole_id']
    if type_ == 'personnel':
        sans = db.execute(
            "SELECT p.id FROM personnel p WHERE p.ecole_id=? AND NOT EXISTS (SELECT 1 FROM codes_pointage c "
            "WHERE c.ecole_id=p.ecole_id AND c.personne_type='personnel' AND c.personne_id=p.id) ORDER BY p.nom, p.prenom",
            (ecole_id,)).fetchall()
    else:
        type_ = 'eleve'
        sans = db.execute(
            "SELECT e.id FROM eleves e WHERE e.ecole_id=? AND COALESCE(e.statut,'actif') IN ('actif','reinsrit') "
            "AND NOT EXISTS (SELECT 1 FROM codes_pointage c WHERE c.ecole_id=e.ecole_id AND c.personne_type='eleve' "
            "AND c.personne_id=e.id) ORDER BY e.classe, e.nom, e.prenom", (ecole_id,)).fetchall()
    numeros = [int(r['code']) for r in db.execute("SELECT code FROM codes_pointage WHERE ecole_id=?", (ecole_id,)).fetchall()
               if r['code'].isdigit()]
    prochain = (max(numeros) if numeros else 0) + 1
    for r in sans:
        db.execute("INSERT INTO codes_pointage (ecole_id,code,personne_type,personne_id) VALUES (?,?,?,?)",
                   (ecole_id, str(prochain), type_, r['id']))
        prochain += 1
    db.commit()
    log_action(g.user, 'creation', 'codes_pointage', None, {'type': type_, 'nombre': len(sans)})
    return jsonify({'ok': True, 'attribues': len(sans)})


# ───────────────────────── réglages ─────────────────────────
@bp.route('/parametres', methods=['GET'])
@require_auth
@require_role(*ROLES_CONSULTATION)
def lire_parametres():
    return jsonify(_parametres(g.user['ecole_id']))


@bp.route('/parametres', methods=['PUT'])
@require_auth
@require_role(*ROLES_GESTION)
def modifier_parametres():
    body = request.get_json(silent=True) or {}
    for cle in PARAMETRES_DEFAUT:
        if cle not in body:
            continue
        valeur = str(body[cle]).strip()
        if cle.endswith('heure_debut'):
            if normaliser_horodatage(f"2000-01-01 {valeur}") is None:
                return jsonify({'error': f"Heure invalide pour {cle} (format HH:MM)"}), 400
        elif not valeur.isdigit() or int(valeur) > 240:
            return jsonify({'error': 'La tolérance doit être un nombre de minutes (0 à 240)'}), 400
        db.execute("INSERT OR REPLACE INTO settings (ecole_id,cle,valeur) VALUES (?,?,?)", (g.user['ecole_id'], cle, valeur))
    db.commit()
    log_action(g.user, 'modification', 'parametres_pointage', None, {k: body[k] for k in PARAMETRES_DEFAUT if k in body})
    return jsonify(_parametres(g.user['ecole_id']))


# ───────────────────────── rapport du jour ─────────────────────────
def _statut(premiere, limite):
    return 'present' if _minutes(_hm(premiere)) <= limite else 'retard'


@bp.route('/jour', methods=['GET'])
@require_auth
@require_role(*ROLES_CONSULTATION)
def rapport_du_jour():
    ecole_id = g.user['ecole_id']
    jour = _date_valide(request.args.get('date')) or datetime.now().strftime('%Y-%m-%d')
    parametres = _parametres(ecole_id)
    passages = _passages_du_jour(ecole_id, jour)

    # — Élèves
    classe = request.args.get('classe')
    sql = ("SELECT id, nom, prenom, classe, matricule FROM eleves WHERE ecole_id=? "
           "AND COALESCE(statut,'actif') IN ('actif','reinsrit')")
    params = [ecole_id]
    if classe:
        sql += " AND classe=?"
        params.append(classe)
    sql += " ORDER BY classe, nom, prenom"
    absences = {r['eleve_id']: r for r in db.execute(
        "SELECT id, eleve_id, type, justifie, motif, duree FROM absences WHERE ecole_id=? AND date_abs=?",
        (ecole_id, jour)).fetchall()}
    contacts = {r['id']: contact_a_prevenir(r) for r in db.execute(
        f"SELECT e.id, {COLONNES_CONTACT} FROM eleves e WHERE e.ecole_id=?", (ecole_id,)).fetchall()}
    prevenus = {r['entite_id']: r['derniere'] for r in db.execute(
        "SELECT entite_id, MAX(created_at) AS derniere FROM journal_audit "
        "WHERE ecole_id=? AND action='prevenir_parent' AND entite='absence' GROUP BY entite_id", (ecole_id,)).fetchall()}
    limite_eleves = _limite_retard(parametres, 'eleve')
    eleves = []
    for e in db.execute(sql, params).fetchall():
        ligne = {'id': e['id'], 'nom': e['nom'], 'prenom': e['prenom'], 'classe': e['classe'], 'matricule': e['matricule'],
                 'arrivee': None, 'depart': None}
        h = passages.get(('eleve', e['id']))
        if h:
            premiere, depart = _arrivee_depart(h)
            ligne.update(arrivee=_hm(premiere), depart=_hm(depart) if depart else None,
                         statut=_statut(premiere, limite_eleves))
        elif e['id'] in absences:
            ligne['statut'] = 'absent'
            ligne['justifie'] = bool(absences[e['id']]['justifie'])
        else:
            ligne['statut'] = 'non_pointe'
        # Retard ou absence enregistré ce jour-là : de quoi prévenir le parent en un clic
        # (même fenêtre que dans Absences).
        ab = absences.get(e['id'])
        if ab and ligne['statut'] in ('retard', 'absent'):
            ligne.update(absence_id=ab['id'], absence_type=ab['type'], motif=ab['motif'], duree=ab['duree'],
                         contact=contacts.get(e['id']), parent_prevenu_le=prevenus.get(ab['id']))
        eleves.append(ligne)

    # — Personnel
    absences_personnel = {r['personnel_id'] for r in db.execute(
        "SELECT personnel_id FROM absences_personnel WHERE ecole_id=? AND date_debut<=? AND (date_fin IS NULL OR date_fin>=?)",
        (ecole_id, jour, jour)).fetchall()}
    limite_personnel = _limite_retard(parametres, 'personnel')
    personnel = []
    for p in db.execute("SELECT id, nom, prenom, poste FROM personnel WHERE ecole_id=? ORDER BY nom, prenom", (ecole_id,)).fetchall():
        ligne = {'id': p['id'], 'nom': p['nom'], 'prenom': p['prenom'], 'poste': p['poste'], 'arrivee': None, 'depart': None}
        h = passages.get(('personnel', p['id']))
        if h:
            premiere, depart = _arrivee_depart(h)
            ligne.update(arrivee=_hm(premiere), depart=_hm(depart) if depart else None,
                         statut=_statut(premiere, limite_personnel))
        elif p['id'] in absences_personnel:
            ligne['statut'] = 'absent_signale'
        else:
            ligne['statut'] = 'non_pointe'
        personnel.append(ligne)

    def compte(lignes, statut):
        return sum(1 for x in lignes if x['statut'] == statut)

    nb_passages = db.execute(
        "SELECT COUNT(*) AS n FROM pointages WHERE ecole_id=? AND horodatage>=? AND horodatage<?",
        (ecole_id, jour + ' 00:00:00', _jour_suivant(jour) + ' 00:00:00')).fetchone()['n']
    return jsonify({
        'date': jour, 'parametres': parametres, 'nb_passages': nb_passages,
        'resume': {
            'eleves': {**{s: compte(eleves, s) for s in ('present', 'retard', 'absent', 'non_pointe')}, 'total': len(eleves)},
            'personnel': {**{s: compte(personnel, s) for s in ('present', 'retard', 'absent_signale', 'non_pointe')},
                          'total': len(personnel)},
        },
        'eleves': eleves, 'personnel': personnel,
    })


@bp.route('/passages', methods=['GET'])
@require_auth
@require_role(*ROLES_GESTION)
def derniers_passages():
    """Derniers passages reçus, y compris ceux dont le numéro n'est associé à personne :
    c'est ainsi qu'on repère un numéro mal saisi dans l'appareil."""
    ecole_id = g.user['ecole_id']
    jour = _date_valide(request.args.get('date'))
    sql = ("SELECT p.horodatage, p.code, p.source, p.motif, a.nom AS appareil, "
           "COALESCE(p.personne_type, c.personne_type) AS personne_type, "
           "COALESCE(p.personne_id, c.personne_id) AS personne_id "
           "FROM pointages p LEFT JOIN appareils_pointage a ON a.id=p.appareil_id "
           "LEFT JOIN codes_pointage c ON c.ecole_id=p.ecole_id AND c.code=p.code WHERE p.ecole_id=?")
    params = [ecole_id]
    if jour:
        sql += " AND p.horodatage>=? AND p.horodatage<?"
        params += [jour + ' 00:00:00', _jour_suivant(jour) + ' 00:00:00']
    sql += " ORDER BY p.horodatage DESC LIMIT 200"
    lignes = rows_to_list(db.execute(sql, params).fetchall())
    noms = {}
    for t, table in (('eleve', 'eleves'), ('personnel', 'personnel')):
        ids = sorted({l['personne_id'] for l in lignes if l['personne_type'] == t and l['personne_id']})
        if ids:
            for r in db.execute(f"SELECT id, nom, prenom FROM {table} WHERE ecole_id=? AND id IN ({','.join('?' * len(ids))})",
                                [ecole_id] + ids).fetchall():
                noms[(t, r['id'])] = f"{r['prenom']} {r['nom']}"
    for l in lignes:
        l['personne'] = noms.get((l['personne_type'], l['personne_id']))
    return jsonify(lignes)


# ───────────────────────── saisie manuelle et clôture ─────────────────────────
@bp.route('/manuel', methods=['POST'])
@require_auth
@require_role(*ROLES_CONSULTATION)
def passage_manuel():
    """Passage saisi à la main (appareil en panne, badge oublié…) : motif obligatoire, tracé."""
    body = request.get_json(silent=True) or {}
    type_, pid = body.get('personne_type'), body.get('personne_id')
    motif = (body.get('motif') or '').strip()
    horo = normaliser_horodatage(body.get('horodatage'))
    ecole_id = g.user['ecole_id']
    table = {'eleve': 'eleves', 'personnel': 'personnel'}.get(type_)
    if not table or not pid or not db.execute(f"SELECT 1 FROM {table} WHERE id=? AND ecole_id=?", (pid, ecole_id)).fetchone():
        return jsonify({'error': 'Personne introuvable'}), 404
    if not horo:
        return jsonify({'error': 'Date et heure invalides'}), 400
    if len(motif) < 5:
        return jsonify({'error': 'Précisez le motif (au moins 5 caractères)'}), 400
    cur = db.execute(
        "INSERT OR IGNORE INTO pointages (ecole_id,id,appareil_id,code,horodatage,source,personne_type,personne_id,saisi_par,motif) "
        "VALUES (?,?,NULL,?,?,'manuel',?,?,?,?)",
        (ecole_id, gen_id('pt'), f"M:{type_}:{pid}", horo, type_, pid, g.user.get('name'), motif))
    retards = _creer_retards_du_jour(ecole_id, horo[:10]) if cur.rowcount and type_ == 'eleve' else 0
    db.commit()
    log_action(g.user, 'creation', 'pointage_manuel', pid, {'type': type_, 'horodatage': horo, 'motif': motif})
    return jsonify({'ok': True, 'retards_crees': retards}), 201


@bp.route('/cloture', methods=['POST'])
@require_auth
@require_role(*ROLES_GESTION)
def cloturer_la_journee():
    """Crée une absence pour chaque élève qui n'a ni pointé ni déjà une absence/un retard
    enregistré ce jour-là. Refusée si l'appareil n'a envoyé AUCUN passage ce jour-là
    (panne, jour férié) sauf confirmation explicite."""
    body = request.get_json(silent=True) or {}
    ecole_id = g.user['ecole_id']
    jour = _date_valide(body.get('date')) or datetime.now().strftime('%Y-%m-%d')
    passages = _passages_du_jour(ecole_id, jour)
    if not any(t == 'eleve' for (t, _pid) in passages) and not body.get('forcer'):
        return jsonify({'error': "Aucun élève n'a pointé ce jour-là : appareil en panne ou jour sans classe ? "
                                 "Rien n'a été créé.", 'aucun_passage': True}), 409
    deja = {r['eleve_id'] for r in db.execute(
        "SELECT eleve_id FROM absences WHERE ecole_id=? AND date_abs=?", (ecole_id, jour)).fetchall()}
    crees = 0
    for e in db.execute("SELECT id FROM eleves WHERE ecole_id=? AND COALESCE(statut,'actif') IN ('actif','reinsrit')",
                        (ecole_id,)).fetchall():
        if ('eleve', e['id']) in passages or e['id'] in deja:
            continue
        db.execute(
            "INSERT INTO absences (id,ecole_id,eleve_id,date_abs,type,justifie,motif,duree) VALUES (?,?,?,?,?,?,?,?)",
            (gen_id('abs'), ecole_id, e['id'], jour, 'absence', 0, 'Non pointé (clôture de la journée)', 'journée'))
        crees += 1
    db.commit()
    log_action(g.user, 'creation', 'cloture_pointage', None, {'date': jour, 'absences_creees': crees})
    return jsonify({'ok': True, 'date': jour, 'absences_creees': crees})


# ───────────────────────── rapport du mois ─────────────────────────
def _heures_presence(horodatages):
    """Durée entre la première et la dernière arrivée de la journée, en heures (0 si un seul passage)."""
    premiere, depart = _arrivee_depart(horodatages)
    if not depart:
        return 0.0
    ecart = datetime.strptime(depart, '%Y-%m-%d %H:%M:%S') - datetime.strptime(premiere, '%Y-%m-%d %H:%M:%S')
    return round(ecart.total_seconds() / 3600, 2)


@bp.route('/mensuel', methods=['GET'])
@require_auth
@require_role(*ROLES_CONSULTATION)
def rapport_du_mois():
    """Ponctualité du mois : par élève (jours de classe, présences, retards, absences) et par
    membre du personnel (jours de présence, retards, heures de présence)."""
    ecole_id = g.user['ecole_id']
    mois = request.args.get('mois') or datetime.now().strftime('%Y-%m')
    try:
        debut = datetime.strptime(mois + '-01', '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Mois invalide (format AAAA-MM)'}), 400
    fin = (debut.replace(day=28) + timedelta(days=4)).replace(day=1)
    parametres = _parametres(ecole_id)
    limites = {'eleve': _limite_retard(parametres, 'eleve'), 'personnel': _limite_retard(parametres, 'personnel')}

    codes = {r['code']: (r['personne_type'], r['personne_id']) for r in db.execute(
        "SELECT code, personne_type, personne_id FROM codes_pointage WHERE ecole_id=?", (ecole_id,)).fetchall()}
    par_personne_jour = {}
    for r in db.execute(
            "SELECT code, horodatage, personne_type, personne_id FROM pointages "
            "WHERE ecole_id=? AND horodatage>=? AND horodatage<? ORDER BY horodatage",
            (ecole_id, debut.strftime('%Y-%m-%d') + ' 00:00:00', fin.strftime('%Y-%m-%d') + ' 00:00:00')).fetchall():
        cible = (r['personne_type'], r['personne_id']) if r['personne_id'] else codes.get(r['code'])
        if cible:
            par_personne_jour.setdefault(cible, {}).setdefault(r['horodatage'][:10], []).append(r['horodatage'])

    jours_classe = {j for (t, _), jours in par_personne_jour.items() if t == 'eleve' for j in jours}
    jours_service = {j for (t, _), jours in par_personne_jour.items() if t == 'personnel' for j in jours}
    justifiees = {}
    for r in db.execute(
            "SELECT eleve_id, date_abs FROM absences WHERE ecole_id=? AND type='absence' AND justifie=1 "
            "AND date_abs>=? AND date_abs<?", (ecole_id, debut.strftime('%Y-%m-%d'), fin.strftime('%Y-%m-%d'))).fetchall():
        justifiees.setdefault(r['eleve_id'], set()).add(r['date_abs'])

    def stats(categorie, pid, jours_ref):
        jours = par_personne_jour.get((categorie, pid), {})
        retards = sum(1 for h in jours.values() if _minutes(_hm(h[0])) > limites[categorie])
        presents = len([j for j in jours if j in jours_ref])
        heures = round(sum(_heures_presence(h) for h in jours.values()), 1)
        return jours, presents, retards, heures

    eleves = []
    sql = ("SELECT id, nom, prenom, classe, matricule FROM eleves WHERE ecole_id=? "
           "AND COALESCE(statut,'actif') IN ('actif','reinsrit')")
    params = [ecole_id]
    if request.args.get('classe'):
        sql += " AND classe=?"
        params.append(request.args['classe'])
    for e in db.execute(sql + " ORDER BY classe, nom, prenom", params).fetchall():
        _, presents, retards, _h = stats('eleve', e['id'], jours_classe)
        absents = len(jours_classe) - presents
        just = len([j for j in justifiees.get(e['id'], set()) if j in jours_classe and j not in par_personne_jour.get(('eleve', e['id']), {})])
        eleves.append({'id': e['id'], 'nom': e['nom'], 'prenom': e['prenom'], 'classe': e['classe'], 'matricule': e['matricule'],
                       'presents': presents, 'retards': retards, 'absents': absents, 'absences_justifiees': just,
                       'taux_presence': round(100 * presents / len(jours_classe)) if jours_classe else None})
    personnel = []
    for p in db.execute("SELECT id, nom, prenom, poste FROM personnel WHERE ecole_id=? ORDER BY nom, prenom", (ecole_id,)).fetchall():
        _, presents, retards, heures = stats('personnel', p['id'], jours_service)
        personnel.append({'id': p['id'], 'nom': p['nom'], 'prenom': p['prenom'], 'poste': p['poste'],
                          'presents': presents, 'retards': retards, 'heures_presence': heures,
                          'absents': len(jours_service) - presents,
                          'taux_presence': round(100 * presents / len(jours_service)) if jours_service else None})
    return jsonify({'mois': mois, 'jours_classe': len(jours_classe), 'jours_service': len(jours_service),
                    'eleves': eleves, 'personnel': personnel})
