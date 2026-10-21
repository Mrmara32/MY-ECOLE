"""Conditions d'utilisation : acceptation obligatoire aux inscriptions ; page Aide et à propos."""
import conditions


def test_inscription_ecole_exige_l_acceptation(client):
    corps = {'nom_ecole': 'Ecole Test Cgu', 'admin_full_name': 'A B', 'admin_username': 'abcgu',
             'admin_password': 'Motdepasse123', 'email_contact': 'a@b.com'}
    r = client.post('/api/ecoles/inscription', json=corps)
    assert r.status_code == 400 and 'accepter' in r.get_json()['error']
    r = client.post('/api/ecoles/inscription', json={**corps, 'accepte_conditions': True})
    assert r.status_code == 201


def test_autres_inscriptions_publiques_exigent_l_acceptation(client):
    assert client.post('/api/eleves/preinscription-publique', json={'nom': 'X', 'prenom': 'Y'}).status_code == 400
    assert client.post('/api/parent/inscription', json={'nom_complet': 'X'}).status_code == 400
    assert client.post('/api/candidatures', json={'nom': 'X', 'prenom': 'Y'}).status_code == 400
    r = client.post('/api/eleves/preinscription-publique', json={'nom': 'Sow', 'prenom': 'Awa', 'accepte_conditions': 'on',
                                                                  'pere_telephone': '622000000'})
    assert r.status_code in (200, 201)


def test_acceptation_du_personnel_par_version(client, entetes):
    s = client.get('/api/aide/conditions', headers=entetes).get_json()
    assert s['version'] == conditions.VERSION_CONDITIONS and not s['acceptees']
    assert client.post('/api/aide/conditions', json={}, headers=entetes).status_code == 400
    assert client.post('/api/aide/conditions', json={'accepte_conditions': True}, headers=entetes).status_code == 200
    assert client.post('/api/aide/conditions', json={'accepte_conditions': True}, headers=entetes).status_code == 200  # idempotent
    assert client.get('/api/aide/conditions', headers=entetes).get_json()['acceptees']


def test_info_contact_et_licence(client, entetes, monkeypatch):
    monkeypatch.delenv('EDITEUR_EMAIL', raising=False)
    i = client.get('/api/aide/info').get_json()
    assert i['editeur']['telephone'] == '661-97-43-43' and i['editeur']['whatsapp'] == '224661974343' and i['editeur']['email'] == ''
    monkeypatch.setenv('EDITEUR_EMAIL', 'contact@exemple.test')
    assert client.get('/api/aide/info').get_json()['editeur']['email'] == 'contact@exemple.test'
    assert client.get('/api/aide/licence').status_code == 401
    l = client.get('/api/aide/licence', headers=entetes).get_json()
    assert l['type'] == 'web' and l['statut'] in ('active', 'essai')


def test_pages_legales_servies(client):
    for chemin in ('/conditions.html', '/conditions', '/confidentialite.html'):
        r = client.get(chemin)
        assert r.status_code == 200 and b'Actif System' in r.data
