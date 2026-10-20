"""
Tests des améliorations d'octobre 2026 : traçabilité des paiements, numéros de reçu,
sauvegardes, annulation des écritures en cas d'erreur, version de l'interface,
lecture des relevés bancaires.
"""
import io
import json
import zipfile
from datetime import datetime

from conftest import MOT_DE_PASSE_ADMIN


# ── Paiements : suppression tracée ─────────────────────────────────────────

def test_suppression_paiement_refusee_sans_motif(client, entetes, creer_eleve, creer_paiement):
    paiement = creer_paiement(creer_eleve(nom='SansMotif')['id'])
    r = client.delete(f"/api/paiements/{paiement['id']}", headers=entetes)
    assert r.status_code == 400
    assert 'motif' in r.get_json()['error'].lower()
    r = client.delete(f"/api/paiements/{paiement['id']}", json={'motif': 'ab'}, headers=entetes)
    assert r.status_code == 400


def test_suppression_paiement_archive_versements_et_journal(client, entetes, creer_eleve, creer_paiement):
    eleve = creer_eleve(nom='Archive', prenom='Fatoumata')
    paiement = creer_paiement(eleve['id'], montant_du=900000, libelle='Scolarité T2')
    client.post(f"/api/paiements/{paiement['id']}/verser", json={'montant': 300000}, headers=entetes)
    client.post(f"/api/paiements/{paiement['id']}/verser", json={'montant': 200000}, headers=entetes)

    r = client.delete(f"/api/paiements/{paiement['id']}",
                      json={'motif': 'Paiement créé en double par erreur'}, headers=entetes)
    assert r.status_code == 200, r.get_json()

    archive = client.get('/api/paiements-supprimes', headers=entetes).get_json()
    ligne = next(l for l in archive if l['paiement_id'] == paiement['id'])
    assert ligne['motif'] == 'Paiement créé en double par erreur'
    assert ligne['montant_paye'] == 500000
    assert ligne['nb_versements'] == 2
    assert 'Fatoumata' in ligne['eleve_nom']

    import database
    donnees = json.loads(database.db.execute(
        "SELECT donnees FROM paiements_supprimes WHERE paiement_id=?", (paiement['id'],)).fetchone()['donnees'])
    assert [v['montant'] for v in donnees['versements']] == [300000, 200000]

    trace = database.db.execute(
        "SELECT details FROM journal_audit WHERE action='suppression' AND entite='paiement' AND entite_id=?",
        (paiement['id'],)).fetchone()
    assert trace and 'en double' in trace['details']

    # Les recettes déjà passées en comptabilité restent intactes
    recettes = [t for t in client.get('/api/transactions', headers=entetes).get_json() if t.get('eleve_id') == eleve['id']]
    assert len(recettes) == 2


def test_ecritures_financieres_journalisees(client, entetes):
    import database
    annee = '2031-2032'
    r = client.post('/api/frais', json={'classe': 'CM2', 'annee_scolaire': annee, 'scolarite_annuelle': 2400000},
                    headers=entetes)
    assert r.status_code == 201
    fid = r.get_json()['id']
    client.put(f'/api/frais/{fid}', json={'scolarite_annuelle': 2600000}, headers=entetes)
    client.delete(f'/api/frais/{fid}', headers=entetes)
    actions = [r['action'] for r in database.db.execute(
        "SELECT action FROM journal_audit WHERE entite='bareme_frais' AND entite_id=? ORDER BY created_at", (fid,)).fetchall()]
    assert sorted(actions) == ['creation', 'modification', 'suppression']


# ── Numéro de reçu renvoyé à l'écran (imprimé sur le reçu remis au parent) ──

def test_versement_renvoie_le_numero_de_recu_officiel(client, entetes, creer_eleve, creer_paiement):
    eleve = creer_eleve(nom='Recu')
    paiement = creer_paiement(eleve['id'], montant_du=400000)
    r = client.post(f"/api/paiements/{paiement['id']}/verser", json={'montant': 400000}, headers=entetes)
    numero = r.get_json()['numero_recu']
    assert numero.startswith(f'REC-{datetime.now().year}-')
    recette = next(t for t in client.get('/api/transactions', headers=entetes).get_json() if t.get('eleve_id') == eleve['id'])
    assert recette['reference'] == numero


def test_versements_simultanes_sur_le_meme_paiement(app, jeton_admin, creer_eleve, creer_paiement):
    """Deux caisses encaissent au même instant sur le MÊME paiement : aucun montant
    ne doit être perdu."""
    from concurrent.futures import ThreadPoolExecutor
    entetes = {'Authorization': f'Bearer {jeton_admin}'}
    paiement = creer_paiement(creer_eleve(nom='MemePaiement')['id'], montant_du=1000000)

    def verser(_):
        with app.test_client() as c:
            return c.post(f"/api/paiements/{paiement['id']}/verser", json={'montant': 50000}, headers=entetes).status_code

    with ThreadPoolExecutor(max_workers=8) as executeur:
        codes = list(executeur.map(verser, range(16)))
    assert codes == [200] * 16
    import database
    paye = database.db.execute("SELECT montant_paye FROM paiements WHERE id=?", (paiement['id'],)).fetchone()['montant_paye']
    assert paye == 16 * 50000


def test_une_ecriture_longue_ne_bloque_pas_les_consultations(app, jeton_admin):
    """Pendant qu'un enregistrement est en cours (simulé ici en gardant le verrou
    d'écriture), les autres utilisateurs peuvent toujours consulter les pages ; les
    enregistrements suivants attendent simplement leur tour."""
    import threading
    import time
    import database
    entetes = {'Authorization': f'Bearer {jeton_admin}'}
    database.verrou_ecritures.acquire()
    try:
        debut = time.monotonic()
        with app.test_client() as c:
            assert c.get('/api/eleves', headers=entetes).status_code == 200
        assert time.monotonic() - debut < 2

        resultat = {}

        def ecrire():
            with app.test_client() as c:
                resultat['code'] = c.post('/api/eleves', json={'nom': 'EnAttente', 'prenom': 'Test'},
                                          headers=entetes).status_code

        fil = threading.Thread(target=ecrire)
        fil.start()
        time.sleep(0.3)
        assert 'code' not in resultat, "l'écriture aurait dû attendre son tour"
    finally:
        database.verrou_ecritures.release()
    fil.join(timeout=10)
    assert resultat.get('code') == 201


# ── Erreurs : message clair + aucune écriture à moitié faite ───────────────

def test_erreur_inattendue_message_clair_et_ecritures_annulees(app, client, entetes):
    import database

    def vue_qui_plante(*args, **kwargs):
        database.db.execute("INSERT INTO settings (cle, valeur, ecole_id) VALUES ('test_ecriture_partielle', 'x', 1)")
        raise RuntimeError('panne simulée')

    nom_vue = 'finances_routes.solde_paiements'
    vue_originale = app.view_functions[nom_vue]
    app.view_functions[nom_vue] = vue_qui_plante
    try:
        r = client.get('/api/paiements/solde/inexistant', headers=entetes)
    finally:
        app.view_functions[nom_vue] = vue_originale

    assert r.status_code == 500
    corps = r.get_json()
    assert corps['reference'].startswith('ERR-')
    assert 'panne simulée' not in corps['error']
    assert corps['reference'] in corps['detail']
    reste = database.db.execute("SELECT 1 FROM settings WHERE cle='test_ecriture_partielle'").fetchone()
    assert reste is None, "l'écriture faite avant l'erreur aurait dû être annulée"


# ── Sauvegardes ────────────────────────────────────────────────────────────

def _base_dans_zip(contenu):
    with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
        assert archive.namelist() == ['ecole.db']
        return archive.read('ecole.db')


def test_sauvegarde_immediate_par_le_super_admin(client, entetes):
    r = client.get('/api/systeme/sauvegardes/maintenant', headers=entetes)
    assert r.status_code == 200
    assert 'attachment' in r.headers['Content-Disposition']
    assert _base_dans_zip(r.data).startswith(b'SQLite format 3')


def test_sauvegarde_refusee_a_un_utilisateur_ordinaire(client, entetes):
    client.post('/api/users', json={'username': 'compta.test', 'password': 'Compta-2026!', 'full_name': 'Comptable Test',
                                    'role': 'comptable'}, headers=entetes)
    r = client.post('/api/auth/login', json={'username': 'compta.test', 'password': 'Compta-2026!'})
    entetes_comptable = {'Authorization': f"Bearer {r.get_json()['token']}"}
    assert client.get('/api/systeme/sauvegardes/maintenant', headers=entetes_comptable).status_code == 403
    assert client.get('/api/systeme/sauvegardes', headers=entetes_comptable).status_code == 403


def test_sauvegarde_automatique_du_jour_et_telechargement(client, entetes):
    import sauvegarde
    sauvegarde.sauvegarde_du_jour()
    sauvegarde.sauvegarde_du_jour()  # deuxième appel le même jour : rien de plus
    liste = client.get('/api/systeme/sauvegardes', headers=entetes).get_json()['sauvegardes']
    noms = [s['nom'] for s in liste]
    assert f"ecole-{datetime.now():%Y-%m-%d}.zip" in noms and len(noms) == 1
    r = client.get(f"/api/systeme/sauvegardes/{noms[0]}", headers=entetes)
    assert r.status_code == 200 and _base_dans_zip(r.data).startswith(b'SQLite format 3')
    assert client.get('/api/systeme/sauvegardes/..%2Fecole.db', headers=entetes).status_code == 404


def test_rotation_des_sauvegardes(monkeypatch, tmp_path):
    import sauvegarde
    monkeypatch.setattr(sauvegarde, 'DOSSIER', str(tmp_path))
    monkeypatch.setattr(sauvegarde, 'NB_A_CONSERVER', 3)
    for jour in range(1, 7):
        (tmp_path / f"ecole-2026-01-0{jour}.zip").write_bytes(b'x')
    sauvegarde._supprimer_anciennes()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        'ecole-2026-01-04.zip', 'ecole-2026-01-05.zip', 'ecole-2026-01-06.zip']


# ── Interface : version automatique ────────────────────────────────────────

def test_service_worker_porte_la_version_de_l_interface(client):
    version = client.get('/api/health').get_json()['version']
    r = client.get('/sw.js')
    assert r.status_code == 200
    texte = r.get_data(as_text=True)
    assert '__VERSION__' not in texte
    assert f"my-ecole-shell-{version}" in texte
    assert '/js/vendor/chart.umd.min.js' in texte


def test_bibliotheques_servies_localement(client):
    for chemin in ('/js/vendor/chart.umd.min.js', '/js/vendor/html2canvas.min.js', '/js/vendor/jspdf.umd.min.js'):
        r = client.get(chemin)
        assert r.status_code == 200 and len(r.data) > 100000, chemin
    index = client.get('/').get_data(as_text=True)
    assert 'cdn.jsdelivr' not in index and 'js/vendor/chart.umd.min.js' in index


# ── Rattachement des recettes à la bonne école ─────────────────────────────

def test_recettes_rattachees_a_l_ecole_de_l_eleve():
    import database
    db = database.db
    db.execute("INSERT INTO ecoles (nom, code, statut_licence) VALUES ('École Test B', 'ecole-test-b', 'active')")
    ecole_b = db.execute("SELECT id FROM ecoles WHERE code='ecole-test-b'").fetchone()['id']
    db.execute("INSERT INTO eleves (id, ecole_id, matricule, nom, prenom) VALUES ('e_test_b', ?, 'B000001', 'Bah', 'Ibrahima')",
               (ecole_b,))
    db.execute("INSERT INTO transactions (id, type, date_op, categorie, montant, eleve_id) "
               "VALUES ('t_test_b', 'entree', '2026-10-01', 'Frais d''inscription', 250000, 'e_test_b')")
    db.commit()
    database._rattacher_a_la_bonne_ecole()
    assert db.execute("SELECT ecole_id FROM transactions WHERE id='t_test_b'").fetchone()['ecole_id'] == ecole_b


# ── Relevés bancaires (sans pandas) ────────────────────────────────────────

def test_releve_csv_dates_francaises_et_montants():
    from releve_bancaire import lire_releve
    csv_texte = ("Date;Libellé;Montant\n"
                 "05/10/2026;Versement scolarité;1 500 000\n"
                 "06/10/2026;Achat fournitures;-250.000,50\n"
                 "07/10/2026;Frais bancaires;(12 000)\n"
                 ";Total;1 238 000\n")
    lignes, erreur = lire_releve(csv_texte.encode('cp1252'), '.csv')
    assert erreur is None
    assert lignes == [
        {'date': '2026-10-05', 'description': 'Versement scolarité', 'montant': 1500000.0, 'type': 'entree'},
        {'date': '2026-10-06', 'description': 'Achat fournitures', 'montant': 250000.5, 'type': 'sortie'},
        {'date': '2026-10-07', 'description': 'Frais bancaires', 'montant': 12000.0, 'type': 'sortie'},
    ]


def test_releve_excel_sans_ligne_de_titres():
    from openpyxl import Workbook
    from releve_bancaire import lire_releve
    classeur = Workbook()
    feuille = classeur.active
    feuille.append([datetime(2026, 10, 5), 'Virement parent', 750000])
    feuille.append(['2026-10-06', 'Retrait', -100000])
    tampon = io.BytesIO()
    classeur.save(tampon)
    lignes, erreur = lire_releve(tampon.getvalue(), '.xlsx')
    assert erreur is None
    assert [(l['date'], l['type'], l['montant']) for l in lignes] == [
        ('2026-10-05', 'entree', 750000.0), ('2026-10-06', 'sortie', 100000.0)]


def test_releve_ancien_format_xls_message_clair():
    from releve_bancaire import lire_releve
    lignes, erreur = lire_releve(b'contenu', '.xls')
    assert lignes is None and '.xlsx' in erreur


def test_connexion_admin_toujours_possible(client):
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': MOT_DE_PASSE_ADMIN})
    assert r.status_code == 200


def test_migrations_versionnees_appliquees_une_seule_fois():
    import database
    derniere = max(m[0] for m in database.MIGRATIONS_VERSIONNEES)
    assert database.version_base() == derniere
    # Rejouer ne doit rien refaire ni échouer
    database.appliquer_migrations_versionnees()
    assert database.version_base() == derniere


def test_migration_en_attente_est_appliquee_apres_copie_de_securite(monkeypatch):
    import os
    import database
    appels = []
    suivante = database.version_base() + 1
    monkeypatch.setattr(database, 'MIGRATIONS_VERSIONNEES',
                        database.MIGRATIONS_VERSIONNEES + [(suivante, 'test', lambda: appels.append(1))])
    database.appliquer_migrations_versionnees()
    assert appels == [1]
    assert database.version_base() == suivante
    assert os.path.isfile(os.path.join(database.DATA_DIR, 'sauvegardes',
                                       f'avant-migration-v{suivante - 1}-vers-v{suivante}.db'))
    database.appliquer_migrations_versionnees()
    assert appels == [1]  # pas rejouée


def test_migration_en_echec_ne_change_pas_la_version(monkeypatch):
    import database
    avant = database.version_base()

    def casse():
        raise RuntimeError('boum')
    monkeypatch.setattr(database, 'MIGRATIONS_VERSIONNEES',
                        database.MIGRATIONS_VERSIONNEES + [(avant + 5, 'cassée', casse)])
    database.appliquer_migrations_versionnees()
    assert database.version_base() == avant


def test_relances_impayes_contact_retard_et_journal(client, entetes):
    r = client.post('/api/eleves', json={'nom': 'Relance', 'prenom': 'Fatoumata', 'classe': 'CE1', 'sexe': 'F',
                                         'pere_telephone': '622 00 11 22', 'mere_telephone': '',
                                         'mere_prenom': '', 'pere_prenom': 'Ibrahima', 'pere_nom': 'Relance'},
                    headers=entetes)
    assert r.status_code == 201, r.get_json()
    eleve = r.get_json()
    r = client.post('/api/paiements', json={'eleve_id': eleve['id'], 'montant_du': 400000, 'type_frais': 'scolarite',
                                            'libelle': 'Tranche 1', 'date_echeance': '2020-01-15'}, headers=entetes)
    assert r.status_code == 201, r.get_json()

    r = client.get('/api/paiements-impayes', headers=entetes)
    assert r.status_code == 200
    ligne = next(x for x in r.get_json() if x['eleve_id'] == eleve['id'])
    assert ligne['reste'] == 400000 and ligne['reste_en_retard'] == 400000
    assert ligne['contact']['lien'] == 'Père' and ligne['contact']['telephone'] == '622 00 11 22'
    assert ligne['derniere_relance'] is None

    r = client.post(f"/api/paiements-impayes/{eleve['id']}/relance", json={'canal': 'whatsapp', 'reste': 400000},
                    headers=entetes)
    assert r.status_code == 200
    ligne = next(x for x in client.get('/api/paiements-impayes', headers=entetes).get_json()
                 if x['eleve_id'] == eleve['id'])
    assert ligne['nb_relances'] == 1 and ligne['derniere_relance']


def test_relances_reservees_au_personnel_financier(client):
    assert client.get('/api/paiements-impayes').status_code == 401


def test_prevenir_parent_absence_contact_et_journal(client, entetes):
    r = client.post('/api/eleves', json={'nom': 'Absent', 'prenom': 'Oumar', 'classe': 'CM1', 'sexe': 'M',
                                         'tuteur_prenom': 'Sekou', 'tuteur_nom': 'Absent',
                                         'tuteur_telephone': '+224 664 00 11 22'}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    eleve = r.get_json()
    r = client.post('/api/absences', json={'eleve_id': eleve['id'], 'date_abs': '2026-10-19', 'type': 'absence',
                                           'motif': 'maladie'}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    absence_id = r.get_json()['id']

    ligne = next(a for a in client.get('/api/absences?eleve_id=' + eleve['id'], headers=entetes).get_json()
                 if a['id'] == absence_id)
    assert ligne['contact']['lien'] == 'Tuteur' and ligne['contact']['telephone'] == '+224 664 00 11 22'
    assert ligne['parent_prevenu_le'] is None

    r = client.post(f'/api/absences/{absence_id}/prevenir', json={'canal': 'sms'}, headers=entetes)
    assert r.status_code == 200
    ligne = next(a for a in client.get('/api/absences?eleve_id=' + eleve['id'], headers=entetes).get_json()
                 if a['id'] == absence_id)
    assert ligne['parent_prevenu_le']
    assert client.post('/api/absences/inconnue/prevenir', json={}, headers=entetes).status_code == 404
    assert client.post(f'/api/absences/{absence_id}/prevenir', json={}).status_code == 401
