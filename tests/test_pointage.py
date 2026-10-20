"""Pointage biométrique / par badge : passages, numéros, retards, absences, protocole ZKTeco."""
from datetime import datetime, timedelta


def _hier():
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


def _creer_appareil(client, entetes, nom='Entrée principale', serie=None):
    r = client.post('/api/pointage/appareils', json={'nom': nom, 'numero_serie': serie}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _eleve_avec_code(client, entetes, creer_eleve, nom, code):
    eleve = creer_eleve(nom=nom, prenom='Test', classe='CE2')
    r = client.put('/api/pointage/codes', json={'personne_type': 'eleve', 'personne_id': eleve['id'], 'code': code},
                   headers=entetes)
    assert r.status_code == 200, r.get_json()
    return eleve


def _envoyer(client, cle, passages):
    return client.post('/api/pointage/passages', json={'passages': [{'code': c, 'horodatage': h} for c, h in passages]},
                       headers={'X-Cle-Appareil': cle})


def test_cle_appareil_obligatoire_et_secrete(client, entetes):
    assert client.post('/api/pointage/passages', json={'passages': []}).status_code == 401
    assert _envoyer(client, 'mauvaise-cle', []).status_code == 401
    appareil = _creer_appareil(client, entetes)
    assert _envoyer(client, appareil['cle'], []).status_code == 200
    liste = client.get('/api/pointage/appareils', headers=entetes).get_json()
    assert all('cle' not in a and 'cle_hash' not in a for a in liste)   # la clé n'est plus jamais renvoyée


def test_arrivee_a_l_heure_retard_depart_et_doublons(client, entetes, creer_eleve):
    jour = _hier()
    appareil = _creer_appareil(client, entetes)
    a_l_heure = _eleve_avec_code(client, entetes, creer_eleve, 'APunctuel', '00101')   # « 00101 » == « 101 »
    en_retard = _eleve_avec_code(client, entetes, creer_eleve, 'ARetard', '102')
    r = _envoyer(client, appareil['cle'], [
        ('101', f'{jour} 07:55:00'), ('101', f'{jour} 07:55:00'),      # doublon exact
        ('101', f'{jour} 16:10:00'),                                   # départ
        ('102', f'{jour}T08:40:00'),                                   # après 08:15 → retard
        ('999', f'{jour} 07:50:00'),                                   # numéro inconnu
        ('', f'{jour} 07:50:00'), ('103', 'pas une date'),             # invalides
    ])
    res = r.get_json()
    assert (res['nouveaux'], res['doublons'], res['invalides'], res['inconnus']) == (4, 1, 2, 1), res
    assert res['retards_crees'] == 1

    rapport = client.get(f'/api/pointage/jour?date={jour}', headers=entetes).get_json()
    par_id = {e['id']: e for e in rapport['eleves']}
    assert par_id[a_l_heure['id']]['statut'] == 'present'
    assert par_id[a_l_heure['id']]['arrivee'] == '07:55' and par_id[a_l_heure['id']]['depart'] == '16:10'
    assert par_id[en_retard['id']]['statut'] == 'retard' and par_id[en_retard['id']]['arrivee'] == '08:40'

    # Le retard apparaît dans les absences existantes de l'application
    absences = client.get(f"/api/absences?eleve_id={en_retard['id']}", headers=entetes).get_json()
    assert [a['type'] for a in absences if a['date_abs'] == jour] == ['retard']

    # Renvoyer le même lot ne crée rien de plus
    res2 = _envoyer(client, appareil['cle'], [('102', f'{jour} 08:40:00')]).get_json()
    assert res2['doublons'] == 1 and res2['retards_crees'] == 0


def test_numero_deja_pris_et_retrait(client, entetes, creer_eleve):
    a = _eleve_avec_code(client, entetes, creer_eleve, 'NumUn', '201')
    b = creer_eleve(nom='NumDeux', prenom='Test', classe='CE2')
    r = client.put('/api/pointage/codes', json={'personne_type': 'eleve', 'personne_id': b['id'], 'code': '201'}, headers=entetes)
    assert r.status_code == 409
    r = client.put('/api/pointage/codes', json={'personne_type': 'eleve', 'personne_id': a['id'], 'code': ''}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['code'] is None


def test_cloture_cree_les_absences_seulement_si_l_appareil_a_fonctionne(client, entetes, creer_eleve):
    jour = '2026-03-03'
    absent = creer_eleve(nom='ZAbsent', prenom='Test', classe='CM2')
    present = _eleve_avec_code(client, entetes, creer_eleve, 'ZPresent', '301')
    # Aucun passage ce jour-là : refus (appareil en panne ou jour férié)
    r = client.post('/api/pointage/cloture', json={'date': jour}, headers=entetes)
    assert r.status_code == 409 and r.get_json()['aucun_passage']

    appareil = _creer_appareil(client, entetes, nom='Portail 2')
    _envoyer(client, appareil['cle'], [('301', f'{jour} 07:58:00')])
    r = client.post('/api/pointage/cloture', json={'date': jour}, headers=entetes)
    assert r.status_code == 200
    absences = [a for a in client.get(f"/api/absences?eleve_id={absent['id']}", headers=entetes).get_json() if a['date_abs'] == jour]
    assert len(absences) == 1 and absences[0]['type'] == 'absence'
    assert not [a for a in client.get(f"/api/absences?eleve_id={present['id']}", headers=entetes).get_json() if a['date_abs'] == jour]
    # Rejouer la clôture ne duplique rien
    assert client.post('/api/pointage/cloture', json={'date': jour}, headers=entetes).get_json()['absences_creees'] == 0


def test_personnel_et_saisie_manuelle(client, entetes):
    r = client.post('/api/personnel', json={'nom': 'Sylla', 'prenom': 'Mamadou', 'poste': 'Enseignant'}, headers=entetes)
    assert r.status_code in (200, 201), r.get_json()
    pid = r.get_json()['id']
    assert client.put('/api/pointage/codes', json={'personne_type': 'personnel', 'personne_id': pid, 'code': '901'},
                      headers=entetes).status_code == 200
    jour = _hier()
    # Saisie manuelle : motif obligatoire
    assert client.post('/api/pointage/manuel', json={'personne_type': 'personnel', 'personne_id': pid,
                                                     'horodatage': f'{jour} 07:45', 'motif': ''}, headers=entetes).status_code == 400
    r = client.post('/api/pointage/manuel', json={'personne_type': 'personnel', 'personne_id': pid,
                                                  'horodatage': f'{jour} 07:45', 'motif': 'Pointeur en panne'}, headers=entetes)
    assert r.status_code == 201
    ligne = next(p for p in client.get(f'/api/pointage/jour?date={jour}', headers=entetes).get_json()['personnel'] if p['id'] == pid)
    assert ligne['statut'] == 'present' and ligne['arrivee'] == '07:45'


def test_protocole_zkteco_push(client, entetes, creer_eleve):
    jour = _hier()
    eleve = _eleve_avec_code(client, entetes, creer_eleve, 'ZKEleve', '401')
    _creer_appareil(client, entetes, nom='ZKTeco K40', serie='SN-TEST-0001')
    # Appareil inconnu : refusé
    assert client.get('/iclock/cdata?SN=INCONNU&options=all').status_code == 403
    # Poignée de main
    r = client.get('/iclock/cdata?SN=SN-TEST-0001&options=all')
    assert r.status_code == 200 and 'TransFlag' in r.get_data(as_text=True)
    # Envoi des passages (une ligne = PIN, date, statut, mode de vérification…)
    corps = f"401\t{jour} 08:05:00\t0\t1\t0\t0\t0\n401\t{jour} 16:20:00\t1\t1\t0\t0\t0\n"
    r = client.post('/iclock/cdata?SN=SN-TEST-0001&table=ATTLOG&Stamp=1', data=corps)
    assert r.status_code == 200 and r.get_data(as_text=True) == 'OK'
    ligne = next(e for e in client.get(f'/api/pointage/jour?date={jour}', headers=entetes).get_json()['eleves'] if e['id'] == eleve['id'])
    assert ligne['statut'] == 'present' and ligne['arrivee'] == '08:05' and ligne['depart'] == '16:20'
    assert client.get('/iclock/getrequest?SN=SN-TEST-0001').get_data(as_text=True) == 'OK'


def test_appareil_desactive_refuse_et_cle_regeneree(client, entetes):
    a = _creer_appareil(client, entetes, nom='À couper')
    assert client.put(f"/api/pointage/appareils/{a['id']}", json={'actif': False}, headers=entetes).status_code == 200
    assert _envoyer(client, a['cle'], []).status_code == 401
    client.put(f"/api/pointage/appareils/{a['id']}", json={'actif': True, 'regenerer_cle': True}, headers=entetes)
    assert _envoyer(client, a['cle'], []).status_code == 401           # ancienne clé invalide
    nouvelle = client.put(f"/api/pointage/appareils/{a['id']}", json={'regenerer_cle': True}, headers=entetes).get_json()['cle']
    assert _envoyer(client, nouvelle, []).status_code == 200


def test_reglages_et_acces_reserves(client, entetes):
    assert client.get('/api/pointage/jour').status_code == 401
    assert client.put('/api/pointage/parametres', json={'pointage_eleves_heure_debut': '25:99'}, headers=entetes).status_code == 400
    r = client.put('/api/pointage/parametres', json={'pointage_eleves_heure_debut': '07:30', 'pointage_eleves_tolerance_min': '10'}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['pointage_eleves_heure_debut'] == '07:30'
    client.put('/api/pointage/parametres', json={'pointage_eleves_heure_debut': '08:00', 'pointage_eleves_tolerance_min': '15'}, headers=entetes)


def test_relais_lit_les_exports_de_l_appareil(tmp_path):
    import importlib.util
    import os
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'outils_pointage', 'relais_pointage.py')
    spec = importlib.util.spec_from_file_location('relais_pointage', chemin)
    relais = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(relais)
    fichier = tmp_path / 'export.dat'
    fichier.write_text(
        "42\t2026-10-20 07:52:10\t0\t1\n"        # export ZKTeco typique
        "43;2026-10-20;07:58:00\n"               # date et heure séparées
        "44,2026-10-20 08:03\n"
        "ligne sans intérêt\n", encoding='utf-8')
    assert relais.lire_fichier(str(fichier)) == [
        {'code': '42', 'horodatage': '2026-10-20 07:52:10'},
        {'code': '43', 'horodatage': '2026-10-20 07:58:00'},
        {'code': '44', 'horodatage': '2026-10-20 08:03'},
    ]


def test_rapport_du_jour_donne_de_quoi_prevenir_le_parent(client, entetes, creer_eleve):
    jour = _hier()
    appareil = _creer_appareil(client, entetes, nom='Prévenir')
    r = client.post('/api/eleves', json={'nom': 'ParentRetard', 'prenom': 'Test', 'classe': 'CE1', 'sexe': 'F',
                                         'mere_prenom': 'Aissatou', 'mere_nom': 'Camara', 'mere_telephone': '622 55 66 77'}, headers=entetes)
    eleve = r.get_json()
    client.put('/api/pointage/codes', json={'personne_type': 'eleve', 'personne_id': eleve['id'], 'code': '601'}, headers=entetes)
    _envoyer(client, appareil['cle'], [('601', f'{jour} 09:30:00')])
    ligne = next(e for e in client.get(f'/api/pointage/jour?date={jour}', headers=entetes).get_json()['eleves'] if e['id'] == eleve['id'])
    assert ligne['statut'] == 'retard' and ligne['absence_type'] == 'retard'
    assert ligne['contact']['lien'] == 'Mère' and ligne['parent_prevenu_le'] is None
    client.post(f"/api/absences/{ligne['absence_id']}/prevenir", json={'canal': 'whatsapp'}, headers=entetes)
    ligne = next(e for e in client.get(f'/api/pointage/jour?date={jour}', headers=entetes).get_json()['eleves'] if e['id'] == eleve['id'])
    assert ligne['parent_prevenu_le']


def test_rapport_mensuel(client, entetes, creer_eleve):
    appareil = _creer_appareil(client, entetes, nom='Mensuel')
    assidu = _eleve_avec_code(client, entetes, creer_eleve, 'MAssidu', '701')
    absent = _eleve_avec_code(client, entetes, creer_eleve, 'MAbsent', '702')
    r = client.post('/api/personnel', json={'nom': 'Mensuel', 'prenom': 'Prof', 'poste': 'Enseignant'}, headers=entetes)
    pid = r.get_json()['id']
    client.put('/api/pointage/codes', json={'personne_type': 'personnel', 'personne_id': pid, 'code': '703'}, headers=entetes)
    # Mars 2025 : 3 jours de classe ; MAssidu présent les 3 jours dont 1 retard ; MAbsent présent 1 jour ; le prof 2 jours (8 h + 6 h)
    _envoyer(client, appareil['cle'], [
        ('701', '2025-03-03 07:50:00'), ('701', '2025-03-04 08:40:00'), ('701', '2025-03-05 07:55:00'),
        ('702', '2025-03-03 07:58:00'),
        ('703', '2025-03-03 07:30:00'), ('703', '2025-03-03 15:30:00'),
        ('703', '2025-03-04 08:00:00'), ('703', '2025-03-04 14:00:00'),
    ])
    m = client.get('/api/pointage/mensuel?mois=2025-03', headers=entetes).get_json()
    assert m['jours_classe'] == 3
    par_id = {e['id']: e for e in m['eleves']}
    assert (par_id[assidu['id']]['presents'], par_id[assidu['id']]['retards'], par_id[assidu['id']]['absents']) == (3, 1, 0)
    assert par_id[assidu['id']]['taux_presence'] == 100
    assert (par_id[absent['id']]['presents'], par_id[absent['id']]['absents']) == (1, 2)
    prof = next(p for p in m['personnel'] if p['id'] == pid)
    assert prof['presents'] == 2 and prof['heures_presence'] == 14.0
    assert client.get('/api/pointage/mensuel?mois=n-importe-quoi', headers=entetes).status_code == 400


def test_heures_pointees_alimentent_la_paie(app_ctx=None):
    from routes.pointage_routes import heures_pointees
    from database import db
    ec = db.execute("SELECT id FROM ecoles LIMIT 1").fetchone()['id']
    pid = 'perso-h1'
    db.execute("INSERT OR IGNORE INTO codes_pointage (ecole_id,code,personne_type,personne_id) VALUES (?,?,?,?)",
               (ec, '777', 'personnel', pid))
    for h in ('2026-09-01 08:00:00', '2026-09-01 12:30:00', '2026-09-02 08:00:00', '2026-09-02 08:05:00'):
        db.execute("INSERT INTO pointages (id,ecole_id,code,horodatage,source) VALUES (?,?,?,?,?)",
                   ('p'+h, ec, '777', h, 'appareil'))
    db.commit()
    assert heures_pointees(ec, pid, '2026-09') == 4.5


def test_badge_qr_signe_et_scan(client, entetes, creer_eleve):
    import re
    eleve = _eleve_avec_code(client, entetes, creer_eleve, 'Badgé', '55')
    lot = client.get('/api/pointage/badges?type=eleve', headers=entetes).get_json()
    assert lot and '<svg' in lot[0]['svg']
    from routes.pointage_routes import contenu_badge
    from database import db
    ec = db.execute("SELECT ecole_id FROM eleves WHERE id=?", (eleve['id'],)).fetchone()['ecole_id']
    bon = contenu_badge(ec, '55')
    r = client.post('/api/pointage/scan', json={'contenu': bon}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['deja_scanne'] is False
    assert 'Badgé' in r.get_json()['nom']
    # second scan immédiat : pas de doublon
    assert client.post('/api/pointage/scan', json={'contenu': bon}, headers=entetes).get_json()['deja_scanne'] is True
    # badge falsifié ou numéro deviné
    faux = re.sub(r':[0-9a-f]{12}$', ':000000000000', bon)
    assert client.post('/api/pointage/scan', json={'contenu': faux}, headers=entetes).status_code == 400
    assert client.post('/api/pointage/scan', json={'contenu': 'MEC:55'}, headers=entetes).status_code == 400
