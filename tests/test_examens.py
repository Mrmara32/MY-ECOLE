"""Examens et concours : création, inscriptions, résultats, statistiques, clôture, droits."""
import pytest


@pytest.fixture
def examen(client, entetes):
    r = client.post('/api/examens', json={'nom': 'Composition T1', 'type': 'composition', 'date_debut': '2026-12-10', 'seuil_admission': 10}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_creation_validations(client, entetes):
    base = {'nom': 'X', 'type': 'composition', 'date_debut': '2026-12-10'}
    for corps in ({**base, 'nom': ' '}, {**base, 'type': 'autre'}, {**base, 'date_debut': '10/12/2026'},
                  {**base, 'date_fin': '2026-12-01'}, {**base, 'seuil_admission': 25}, {**base, 'places': 0}):
        assert client.post('/api/examens', json=corps, headers=entetes).status_code == 400, corps


def test_inscription_classe_numeros_et_doublons(client, entetes, creer_eleve, examen):
    for i in range(3):
        creer_eleve(nom=f'Candidat{i}', prenom='Exam', classe='EXA-6')
    r = client.post(f"/api/examens/{examen['id']}/candidats", json={'classe': 'EXA-6'}, headers=entetes)
    assert r.status_code == 201 and r.get_json()['ajoutes'] == 3
    assert client.post(f"/api/examens/{examen['id']}/candidats", json={'classe': 'EXA-6'}, headers=entetes).get_json()['ajoutes'] == 0   # pas de doublon
    c = client.get(f"/api/examens/{examen['id']}/candidats", headers=entetes).get_json()
    assert [x['numero'] for x in c] == ['C0001', 'C0002', 'C0003']
    # candidat externe refusé pour une simple composition
    assert client.post(f"/api/examens/{examen['id']}/candidats", json={'nom': 'Ext', 'prenom': 'Erne'}, headers=entetes).status_code == 400


def test_resultats_statistiques_et_cloture(client, entetes, creer_eleve):
    xid = client.post('/api/examens', json={'nom': 'BEPC blanc', 'type': 'examen_national', 'date_debut': '2026-06-01', 'seuil_admission': 10},
                      headers=entetes).get_json()['id']
    for i in range(4):
        creer_eleve(nom=f'Bepc{i}', prenom='X', classe='EXA-BEPC')
    client.post(f'/api/examens/{xid}/candidats', json={'classe': 'EXA-BEPC'}, headers=entetes)
    client.post(f'/api/examens/{xid}/candidats', json={'nom': 'Externe', 'prenom': 'Libre'}, headers=entetes)     # externe accepté (national)
    c = client.get(f'/api/examens/{xid}/candidats', headers=entetes).get_json()
    assert len(c) == 5
    assert client.post(f'/api/examens/{xid}/cloturer', headers=entetes).status_code == 409                      # résultats manquants
    assert client.put(f'/api/examens/{xid}/resultats', json={'resultats': [{'id': c[0]['id'], 'moyenne': 21}]}, headers=entetes).status_code == 400
    r = client.put(f'/api/examens/{xid}/resultats', headers=entetes, json={'resultats': [
        {'id': c[0]['id'], 'moyenne': 15.5}, {'id': c[1]['id'], 'moyenne': 10}, {'id': c[2]['id'], 'moyenne': 9.99},
        {'id': c[3]['id'], 'absent': True}, {'id': c[4]['id'], 'moyenne': 12}]})
    assert r.status_code == 200
    s = client.get(f'/api/examens/{xid}/statistiques', headers=entetes).get_json()
    assert (s['inscrits'], s['presents'], s['admis'], s['ajournes'], s['absents']) == (5, 4, 3, 1, 1)
    assert s['taux_reussite'] == 75.0 and s['moyenne_generale'] == 11.87 and s['mentions'] == {'Bien': 1, 'Passable': 1, 'Assez Bien': 1}
    by = {x['id']: x for x in client.get(f'/api/examens/{xid}/candidats', headers=entetes).get_json()}
    assert by[c[1]['id']]['statut'] == 'admis' and by[c[2]['id']]['statut'] == 'ajourne'
    assert client.post(f'/api/examens/{xid}/cloturer', headers=entetes).status_code == 200
    assert client.put(f'/api/examens/{xid}/resultats', json={'resultats': [{'id': c[0]['id'], 'moyenne': 5}]}, headers=entetes).status_code == 409
    assert client.delete(f'/api/examens/{xid}', headers=entetes).status_code == 409


def test_concours_capacite_et_droits(client, entetes):
    xid = client.post('/api/examens', json={'nom': 'Concours 6e', 'type': 'concours_entree', 'date_debut': '2026-07-01', 'places': 2}, headers=entetes).get_json()['id']
    for i in range(2):
        assert client.post(f'/api/examens/{xid}/candidats', json={'nom': f'N{i}', 'prenom': 'P'}, headers=entetes).status_code == 201
    assert client.post(f'/api/examens/{xid}/candidats', json={'nom': 'Trop', 'prenom': 'Tard'}, headers=entetes).status_code == 409
    client.post('/api/users', json={'username': 'ens_exam', 'password': 'Provisoire-1', 'full_name': 'E', 'role': 'enseignant'}, headers=entetes)
    t = client.post('/api/auth/login', json={'username': 'ens_exam', 'password': 'Provisoire-1'}).get_json()['token']
    tok = client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Solide-2026'}, headers={'Authorization': f'Bearer {t}'}).get_json()['token']
    h = {'Authorization': f'Bearer {tok}'}
    assert client.get('/api/examens', headers=h).status_code == 200
    assert client.post('/api/examens', json={'nom': 'Z', 'type': 'composition', 'date_debut': '2026-01-01'}, headers=h).status_code == 403
    assert client.put(f'/api/examens/{xid}/resultats', json={'resultats': []}, headers=h).status_code == 403
