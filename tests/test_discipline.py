"""Discipline / vie scolaire : saisie, droits par rôle, visibilité parents, historique."""
import pytest


def _compte(client, entetes, username, role, mdp='Compte-Test-1'):
    r = client.post('/api/users', json={'username': username, 'password': mdp, 'full_name': username, 'role': role}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    uid = r.get_json()['id']
    tok = client.post('/api/auth/login', json={'username': username, 'password': mdp}).get_json()['token']
    # mot de passe provisoire : changement obligatoire avant usage
    r = client.post('/api/auth/change-password', json={'oldPassword': mdp, 'newPassword': mdp + '-X9'}, headers={'Authorization': f'Bearer {tok}'})
    return uid, {'Authorization': f"Bearer {r.get_json()['token']}"}


@pytest.fixture
def classe_dis(client, entetes):
    client.post('/api/classes', json={'nom': 'Dis-A', 'cycle': 'college'}, headers=entetes)
    return 'Dis-A'


def _fait(client, h, eleve, **kw):
    corps = {'eleve_id': eleve['id'], 'type': 'observation', 'motif': 'Bavardages', 'date_fait': '2026-10-15', **kw}
    return client.post('/api/discipline', json=corps, headers=h)


def test_saisie_validation_et_historique(client, entetes, creer_eleve, classe_dis):
    e = creer_eleve(nom='Dis1', prenom='A', classe=classe_dis)
    assert _fait(client, entetes, e).status_code == 201
    assert _fait(client, entetes, e, type='inconnu').status_code == 400
    assert _fait(client, entetes, e, motif='  ').status_code == 400
    assert _fait(client, entetes, e, date_fait='15/10/2026').status_code == 400
    assert _fait(client, entetes, e, type='exclusion_temporaire').status_code == 400          # durée obligatoire
    assert _fait(client, entetes, e, type='exclusion_temporaire', nb_jours=3, motif='Violence').status_code == 201
    assert _fait(client, entetes, e, type='felicitations', motif='Major de classe').status_code == 201
    assert client.post('/api/discipline', json={'eleve_id': 'x', 'type': 'observation', 'motif': 'm', 'date_fait': '2026-10-15'}, headers=entetes).status_code == 404
    liste = client.get(f"/api/discipline?eleve_id={e['id']}", headers=entetes).get_json()
    assert len(liste) == 3
    resume = client.get(f"/api/discipline/resume/{e['id']}", headers=entetes).get_json()
    assert resume['exclusion_temporaire'] == {'nombre': 1, 'jours': 3} and resume['felicitations']['nombre'] == 1


def test_modification_suppression_reservees_a_la_direction_et_tracees(client, entetes, creer_eleve, classe_dis):
    e = creer_eleve(nom='Dis2', prenom='B', classe=classe_dis)
    d = _fait(client, entetes, e).get_json()
    _, sec = _compte(client, entetes, 'sec-dis', 'secretaire')
    assert client.put(f"/api/discipline/{d['id']}", json={'motif': 'x'}, headers=sec).status_code == 403
    assert client.delete(f"/api/discipline/{d['id']}", headers=sec).status_code == 403
    assert client.put(f"/api/discipline/{d['id']}", json={'motif': 'Retards répétés'}, headers=entetes).get_json()['motif'] == 'Retards répétés'
    assert client.delete(f"/api/discipline/{d['id']}", headers=entetes).status_code == 200
    assert client.delete(f"/api/discipline/{d['id']}", headers=entetes).status_code == 404


def test_enseignant_limite_a_ses_classes_et_sanctions_lourdes_interdites(client, entetes, creer_eleve, classe_dis):
    import database
    mien, autre = creer_eleve(nom='Dis3', prenom='C', classe=classe_dis), creer_eleve(nom='Dis4', prenom='D', classe='Dis-Autre')
    uid, ens = _compte(client, entetes, 'ens-dis', 'enseignant')
    assert client.get('/api/discipline', headers=ens).get_json() == []                    # aucune classe attribuée
    assert _fait(client, ens, mien).status_code == 403
    database.db.execute("INSERT INTO personnel (id, ecole_id, nom, prenom, user_id) VALUES ('p-dis',1,'Prof','Dis',?)", (uid,))
    database.db.execute("INSERT INTO emploi_du_temps (id, ecole_id, jour, creneau, classe, professeur_id) VALUES ('edt-dis',1,'Lundi','07h30',?,'p-dis')", (classe_dis,))
    database.db.commit()
    assert _fait(client, ens, mien).status_code == 201
    assert _fait(client, ens, autre).status_code == 403                                  # pas sa classe
    assert _fait(client, ens, mien, type='blame').status_code == 403                     # sanction lourde : direction seule
    assert _fait(client, ens, mien, type='exclusion_temporaire', nb_jours=2).status_code == 403
    vus = client.get('/api/discipline', headers=ens).get_json()
    ids = {x['eleve_id'] for x in vus}
    assert mien['id'] in ids and autre['id'] not in ids              # uniquement les élèves de ses classes
    assert {x['classe'] for x in vus} == {classe_dis}


def test_parent_ne_voit_que_les_faits_visibles_de_son_enfant(client, entetes, creer_eleve, classe_dis):
    import database
    mon, autre = creer_eleve(nom='Dis5', prenom='E', classe=classe_dis), creer_eleve(nom='Dis6', prenom='F', classe=classe_dis)
    _fait(client, entetes, mon, motif='Visible')
    _fait(client, entetes, mon, motif='Note interne', visible_parents=False)
    _fait(client, entetes, autre, motif='Autre enfant')
    uid, par = _compte(client, entetes, 'par-dis', 'parent')
    database.db.execute("INSERT INTO parents_eleves (id, user_id, eleve_id) VALUES (?,?,?)", (database.gen_id('pe'), uid, mon['id']))
    database.db.commit()
    vus = client.get('/api/discipline', headers=par).get_json()
    assert [x['motif'] for x in vus] == ['Visible']
    assert client.get(f"/api/discipline/resume/{autre['id']}", headers=par).status_code == 403
    assert client.post('/api/discipline', json={'eleve_id': mon['id'], 'type': 'observation', 'motif': 'm', 'date_fait': '2026-10-15'}, headers=par).status_code == 403
    assert client.get('/api/discipline').status_code == 401
