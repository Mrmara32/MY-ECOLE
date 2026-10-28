"""Conformité : en-têtes de sécurité, CORS, fichiers téléversés, droits des personnes, minimisation des données de santé."""
import io
import json

import pytest

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def _connecte(client, entetes, nom, role):
    client.post('/api/users', json={'username': nom, 'password': 'Provisoire-1', 'full_name': nom, 'role': role}, headers=entetes)
    t = client.post('/api/auth/login', json={'username': nom, 'password': 'Provisoire-1'}).get_json()['token']
    tok = client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Solide-2026-Zq'},
                      headers={'Authorization': f'Bearer {t}'}).get_json()['token']
    return {'Authorization': f'Bearer {tok}'}


def test_en_tetes_de_securite(client, entetes):
    r = client.get('/')
    assert r.headers['X-Content-Type-Options'] == 'nosniff' and r.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert "frame-ancestors 'self'" in r.headers['Content-Security-Policy'] and "object-src 'none'" in r.headers['Content-Security-Policy']
    assert 'Referrer-Policy' in r.headers and 'Permissions-Policy' in r.headers
    api = client.get('/api/auth/me', headers=entetes)
    assert api.headers['Cache-Control'] == 'no-store'
    assert 'Strict-Transport-Security' not in r.headers                                       # HTTP local : pas de HSTS
    assert 'max-age' in client.get('/', headers={'X-Forwarded-Proto': 'https'}).headers['Strict-Transport-Security']


def test_cors_ferme_par_defaut(client):
    r = client.get('/api/settings', headers={'Origin': 'https://site-pirate.example'})
    assert 'Access-Control-Allow-Origin' not in r.headers


def test_fichier_deguise_en_image_refuse(client, entetes):
    faux = client.post('/api/settings/logo', data={'logo': (io.BytesIO(b'<script>alert(1)</script>'), 'logo.png')},
                       headers=entetes, content_type='multipart/form-data')
    assert faux.status_code == 400
    vrai = client.post('/api/settings/logo', data={'logo': (io.BytesIO(PNG), 'logo.png')}, headers=entetes, content_type='multipart/form-data')
    assert vrai.status_code == 200


def test_donnees_de_sante_minimisees_selon_le_role(client, entetes, creer_eleve):
    e = creer_eleve(nom='Sante', prenom='Test', classe='CONF-1')
    client.put(f"/api/eleves/{e['id']}", json={'allergies': 'arachides', 'groupe_sanguin': 'O+', 'assurance_numero': 'A-123'}, headers=entetes)
    assert client.get(f"/api/eleves/{e['id']}", headers=entetes).get_json()['groupe_sanguin'] == 'O+'
    compta = _connecte(client, entetes, 'compta_conf', 'comptable')
    d = client.get(f"/api/eleves/{e['id']}", headers=compta).get_json()
    assert d['allergies'] is None and d['groupe_sanguin'] is None and d['assurance_numero'] is None
    assert all(x['allergies'] is None for x in client.get('/api/eleves?classe=CONF-1', headers=compta).get_json())


def test_export_donnees_et_anonymisation(client, entetes, creer_eleve, creer_paiement):
    e = creer_eleve(nom='Oubliable', prenom='Ancien', classe='CONF-2')
    creer_paiement(e['id'])
    client.put(f"/api/eleves/{e['id']}", json={'pere_telephone': '622000000', 'allergies': 'pollen'}, headers=entetes)
    r = client.get(f"/api/eleves/{e['id']}/donnees", headers=entetes)
    assert r.status_code == 200 and 'attachment' in r.headers['Content-Disposition']
    paquet = json.loads(r.data)
    assert paquet['eleve']['nom'] == 'Oubliable' and len(paquet['donnees']['paiements']) >= 1
    # un élève actif ne s'anonymise pas
    assert client.post(f"/api/eleves/{e['id']}/anonymiser", json={'confirmation': e['matricule']}, headers=entetes).status_code == 409
    client.put(f"/api/eleves/{e['id']}", json={'statut': 'transfere'}, headers=entetes)
    assert client.post(f"/api/eleves/{e['id']}/anonymiser", json={'confirmation': 'faux'}, headers=entetes).status_code == 400
    assert client.post(f"/api/eleves/{e['id']}/anonymiser", json={'confirmation': e['matricule']}, headers=entetes).status_code == 200
    d = client.get(f"/api/eleves/{e['id']}", headers=entetes).get_json()
    assert d['nom'] == 'ANONYME' and d['pere_telephone'] is None and d['allergies'] is None
    assert len(json.loads(client.get(f"/api/eleves/{e['id']}/donnees", headers=entetes).data)['donnees']['paiements']) >= 1   # comptabilité conservée
    simple = _connecte(client, entetes, 'sec_conf', 'secretaire')
    assert client.get(f"/api/eleves/{e['id']}/donnees", headers=simple).status_code == 403


def test_echecs_et_connexions_journalises(client, entetes):
    client.post('/api/auth/login', json={'username': 'inconnu_journal', 'password': 'nimportequoi1'})
    journal = client.get('/api/journal?limit=200', headers=entetes)
    texte = journal.data.decode()
    assert 'echec_connexion' in texte and 'inconnu_journal' in texte and 'nimportequoi1' not in texte


def test_politique_de_confidentialite_publique(client):
    r = client.get('/confidentialite.html')
    assert r.status_code == 200 and 'Protection des données personnelles' in r.data.decode()
