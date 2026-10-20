"""
Résultats scolaires : coefficients, moyennes pondérées, rangs (ex æquo), validation des notes,
accès des parents, décisions de fin d'année et réinscriptions.
"""
import pytest


@pytest.fixture
def classe_test(client, entetes):
    """Crée deux classes consécutives (6e Test -> 5e Test) et leurs matières à coefficients."""
    def _creer(nom, cycle='college', matieres=None):
        r = client.post('/api/classes', json={'nom': nom, 'cycle': cycle}, headers=entetes)
        assert r.status_code in (201, 409), r.get_json()
        if matieres:
            r = client.put('/api/matieres-classe', json={'classe': nom, 'matieres': matieres}, headers=entetes)
            assert r.status_code == 200, r.get_json()
        return nom
    return _creer


@pytest.fixture
def noter(client, entetes):
    def _noter(eleve_id, matiere, note, trimestre=1, note_max=20):
        r = client.post('/api/notes', json={'eleve_id': eleve_id, 'matiere': matiere, 'note': note,
                                            'trimestre': trimestre, 'note_max': note_max}, headers=entetes)
        assert r.status_code == 201, r.get_json()
    return _noter


def _bulletin(client, entetes, classe, periode='1'):
    r = client.get(f'/api/bulletins/classe/{classe}?periode={periode}', headers=entetes)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_moyenne_ponderee_par_les_coefficients(client, entetes, creer_eleve, classe_test, noter):
    c = classe_test('Coef-A', matieres=[{'matiere': 'Maths', 'coefficient': 3}, {'matiere': 'Français', 'coefficient': 1}])
    a = creer_eleve(nom='Aaa', prenom='A', classe=c)
    noter(a['id'], 'Maths', 16); noter(a['id'], 'Français', 8)
    res = _bulletin(client, entetes, c)
    ligne = res['eleves'][0]
    assert ligne['moyenne_generale'] == 14.0          # (16*3 + 8*1) / 4, pas (16+8)/2 = 12
    assert ligne['mention'] == 'Bien'
    maths = next(m for m in res['matieres'] if m['matiere'] == 'Maths')
    assert maths['coefficient'] == 3 and maths['moyenne_classe'] == 16.0


def test_rang_avec_ex_aequo_et_matiere_sans_note_ignoree(client, entetes, creer_eleve, classe_test, noter):
    c = classe_test('Coef-B', matieres=[{'matiere': 'Maths', 'coefficient': 2}, {'matiere': 'Histoire', 'coefficient': 2}])
    e1, e2, e3, e4 = (creer_eleve(nom=n, prenom='X', classe=c) for n in ('Bb1', 'Bb2', 'Bb3', 'Bb4'))
    for e, v in ((e1, 15), (e2, 15), (e3, 10)):
        noter(e['id'], 'Maths', v)
    noter(e4['id'], 'Maths', 18); noter(e4['id'], 'Histoire', 18)
    res = {x['eleve_id']: x for x in _bulletin(client, entetes, c)['eleves']}
    # Histoire sans note pour e1 : ignorée, et non comptée comme 0
    assert res[e1['id']]['moyenne_generale'] == 15.0
    assert res[e4['id']]['rang'] == 1
    assert res[e1['id']]['rang'] == res[e2['id']]['rang'] == 2
    assert res[e3['id']]['rang'] == 4                 # 1er, 2e ex æquo, 2e ex æquo, 4e
    assert res[e1['id']]['effectif'] == 4


def test_note_ramenee_sur_20_et_moyenne_annuelle(client, entetes, creer_eleve, classe_test, noter):
    c = classe_test('Coef-C', matieres=[{'matiere': 'Maths', 'coefficient': 1}])
    e = creer_eleve(nom='Cc', prenom='C', classe=c)
    noter(e['id'], 'Maths', 8, trimestre=1, note_max=10)    # 16/20
    noter(e['id'], 'Maths', 10, trimestre=2)                # 10/20
    res = _bulletin(client, entetes, c, 'annee')['eleves'][0]
    assert res['moyennes_trimestres'] == {'1': 16.0, '2': 10.0}
    assert res['moyenne_generale'] == 13.0                   # trimestre 3 absent : non compté
    assert res['decision_proposee'] == 'admis'


def test_notes_invalides_refusees(client, entetes, creer_eleve):
    e = creer_eleve(nom='Dd', prenom='D')
    base = {'eleve_id': e['id'], 'matiere': 'Maths', 'trimestre': 1}
    assert client.post('/api/notes', json={**base, 'note': 25}, headers=entetes).status_code == 400
    assert client.post('/api/notes', json={**base, 'note': -1}, headers=entetes).status_code == 400
    assert client.post('/api/notes', json={**base, 'note': 'abc'}, headers=entetes).status_code == 400
    assert client.post('/api/notes', json={**base, 'note': 5, 'trimestre': 4}, headers=entetes).status_code == 400
    assert client.post('/api/notes', json={**base, 'note': 5, 'note_max': 0}, headers=entetes).status_code == 400
    assert client.post('/api/notes', json={**base, 'eleve_id': 'inexistant', 'note': 5}, headers=entetes).status_code == 404
    ok = client.post('/api/notes', json={**base, 'note': 15}, headers=entetes)
    assert ok.status_code == 201
    assert client.put(f"/api/notes/{ok.get_json()['id']}", json={'note': 99}, headers=entetes).status_code == 400


def test_coefficients_invalides_refuses(client, entetes, classe_test):
    c = classe_test('Coef-E')
    for mats in ([{'matiere': 'M', 'coefficient': 0}], [{'matiere': 'M', 'coefficient': 'x'}],
                 [{'matiere': 'M', 'coefficient': 1}, {'matiere': 'm', 'coefficient': 2}], [{'matiere': ' ', 'coefficient': 1}]):
        assert client.put('/api/matieres-classe', json={'classe': c, 'matieres': mats}, headers=entetes).status_code == 400
    assert client.put('/api/matieres-classe', json={'classe': 'Inconnue', 'matieres': []}, headers=entetes).status_code == 404


def test_appreciation_saisie_remplace_l_automatique(client, entetes, creer_eleve, classe_test, noter):
    c = classe_test('Coef-F', matieres=[{'matiere': 'Maths', 'coefficient': 1}])
    e = creer_eleve(nom='Ff', prenom='F', classe=c); noter(e['id'], 'Maths', 17)
    assert _bulletin(client, entetes, c)['eleves'][0]['appreciation_saisie'] is False
    r = client.put('/api/bulletins/appreciation', json={'eleve_id': e['id'], 'periode': '1', 'appreciation': 'Élève sérieux.'}, headers=entetes)
    assert r.status_code == 200
    ligne = _bulletin(client, entetes, c)['eleves'][0]
    assert ligne['appreciation'] == 'Élève sérieux.' and ligne['appreciation_saisie'] is True
    client.put('/api/bulletins/appreciation', json={'eleve_id': e['id'], 'periode': '1', 'appreciation': ''}, headers=entetes)
    assert _bulletin(client, entetes, c)['eleves'][0]['appreciation_saisie'] is False


def test_parent_voit_son_enfant_mais_pas_la_classe(client, entetes, creer_eleve, classe_test, noter):
    import database
    c = classe_test('Coef-G', matieres=[{'matiere': 'Maths', 'coefficient': 1}])
    mon, autre = creer_eleve(nom='Gg1', prenom='G', classe=c), creer_eleve(nom='Gg2', prenom='G', classe=c)
    noter(mon['id'], 'Maths', 12); noter(autre['id'], 'Maths', 18)
    r = client.post('/api/users', json={'username': 'parent-g', 'password': 'Parent-Test-1', 'full_name': 'Parent G', 'role': 'parent'}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    database.db.execute("INSERT INTO parents_eleves (user_id, eleve_id) VALUES (?,?)", (r.get_json()['id'], mon['id']))
    database.db.commit()
    tok = client.post('/api/auth/login', json={'username': 'parent-g', 'password': 'Parent-Test-1'}).get_json()['token']
    # compte créé par l'administrateur : mot de passe provisoire, à changer avant toute autre action
    r = client.post('/api/auth/change-password', json={'oldPassword': 'Parent-Test-1', 'newPassword': 'Parent-Final-2'},
                    headers={'Authorization': f'Bearer {tok}'})
    assert r.status_code == 200, r.get_json()
    h = {'Authorization': f"Bearer {r.get_json()['token']}"}
    assert client.get(f'/api/bulletins/classe/{c}', headers=h).status_code == 403
    assert client.get(f"/api/bulletins/eleve/{autre['id']}", headers=h).status_code == 403
    r = client.get(f"/api/bulletins/eleve/{mon['id']}", headers=h)
    assert r.status_code == 200
    corps = r.get_json()
    assert corps['eleve']['moyenne_generale'] == 12.0 and 'eleves' not in corps   # pas les résultats des autres


def test_fin_annee_decisions_puis_reinscriptions(client, entetes, creer_eleve, classe_test, noter):
    c1 = classe_test('Fin-1', cycle='primaire', matieres=[{'matiere': 'Maths', 'coefficient': 1}])
    c2 = classe_test('Fin-2', cycle='primaire')
    # 'Fin-2' est créée après 'Fin-1' : elle la suit dans l'ordre
    bon, faible = creer_eleve(nom='Hh1', prenom='H', classe=c1), creer_eleve(nom='Hh2', prenom='H', classe=c1)
    noter(bon['id'], 'Maths', 14); noter(faible['id'], 'Maths', 6)
    prop = client.get(f'/api/fin-annee/{c1}', headers=entetes).get_json()
    assert prop['classe_suivante_suggeree'] == c2
    dec = {x['eleve_id']: x['decision_proposee'] for x in prop['eleves']}
    assert dec[bon['id']] == 'admis' and dec[faible['id']] == 'redouble'

    r = client.post('/api/fin-annee/decisions', json={
        'annee_scolaire': '2025-2026', 'classe': c1,
        'decisions': [{'eleve_id': i, 'decision': d} for i, d in dec.items()]}, headers=entetes)
    assert r.status_code == 200, r.get_json()
    # décision invalide / élève d'une autre classe : refusées
    assert client.post('/api/fin-annee/decisions', json={'annee_scolaire': '2025-2026', 'classe': c1,
                       'decisions': [{'eleve_id': bon['id'], 'decision': 'promu'}]}, headers=entetes).status_code == 400
    assert client.post('/api/fin-annee/decisions', json={'annee_scolaire': '2025-2026', 'classe': c1,
                       'decisions': [{'eleve_id': 'zzz', 'decision': 'admis'}]}, headers=entetes).status_code == 400

    r = client.post('/api/fin-annee/reinscriptions', json={'annee_scolaire': '2025-2026', 'nouvelle_annee': '2026-2027'}, headers=entetes)
    assert r.get_json()['creees'] == 2
    r = client.post('/api/fin-annee/reinscriptions', json={'annee_scolaire': '2025-2026', 'nouvelle_annee': '2026-2027'}, headers=entetes)
    assert r.get_json()['creees'] == 0 and r.get_json()['deja_existantes'] == 2     # idempotent
    rei = {x['eleve_id']: x for x in client.get('/api/reinscriptions?annee_scolaire=2026-2027', headers=entetes).get_json()}
    assert rei[bon['id']]['classe_nouvelle'] == c2 and rei[bon['id']]['statut'] == 'en_attente'
    assert rei[faible['id']]['classe_nouvelle'] == c1                                # redoublant : reste en classe
    # la décision enregistrée apparaît dans le bulletin annuel
    ligne = next(x for x in _bulletin(client, entetes, c1, 'annee')['eleves'] if x['eleve_id'] == bon['id'])
    assert ligne['decision']['decision'] == 'admis'
