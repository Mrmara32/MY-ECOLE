"""Paiement Orange Money (Web Payment) — serveur Orange factice."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import orange_money_service as om

etat = {'statut': 'INITIATED', 'appels': []}


class FauxOrange(BaseHTTPRequestHandler):
    def do_POST(self):
        corps = self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200); self.end_headers()
        if self.path.endswith('/oauth/v3/token'):
            self.wfile.write(b'{"access_token":"T","expires_in":3600}')
        elif self.path.endswith('/webpayment'):
            etat['appels'].append(('webpayment', json.loads(corps)))
            self.wfile.write(b'{"payment_url":"https://pay.example/abc","pay_token":"PT1","notif_token":"NT1"}')
        elif self.path.endswith('/transactionstatus'):
            etat['appels'].append(('status', json.loads(corps)))
            self.wfile.write(json.dumps({'status': etat['statut']}).encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_om(monkeypatch):
    etat.update(statut='INITIATED', appels=[])
    om._jeton.update(valeur=None, expire=0)
    srv = HTTPServer(('127.0.0.1', 0), FauxOrange)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for k, v in {'OM_API_URL': f'http://127.0.0.1:{srv.server_port}', 'OM_AUTH': 'Basic x',
                 'OM_MERCHANT_KEY': 'MK', 'URL_APPLICATION': 'https://ecole.example'}.items():
        monkeypatch.setenv(k, v)
    yield
    srv.shutdown()


def _dossier(client, entetes, creer_eleve, creer_paiement):
    e = creer_eleve(nom='Barry', prenom='Mamadou', classe='CE2')
    p1 = creer_paiement(e['id'], 300000, 'Tranche 1')
    p2 = creer_paiement(e['id'], 200000, 'Tranche 2')
    return e, p1, p2


def _reste(client, entetes, eleve_id):
    return client.get(f'/api/paiements/solde/{eleve_id}', headers=entetes).get_json()['reste']


def test_non_configure_et_reglages(monkeypatch, client, entetes):
    monkeypatch.delenv('OM_AUTH', raising=False)
    assert client.get('/api/orange-money/statut', headers=entetes).get_json()['actif'] is False
    assert client.post('/api/orange-money/lien', json={'eleve_id': 'x'}, headers=entetes).status_code == 503


def test_parcours_complet_paiement_reussi(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 400000}, headers=entetes)
    assert r.status_code == 200, r.get_json()
    rid = r.get_json()['id']
    assert r.get_json()['payment_url'] == 'https://pay.example/abc'
    envoi = etat['appels'][0][1]
    assert envoi['amount'] == 400000 and envoi['merchant_key'] == 'MK' and envoi['currency'] == 'OUV'
    assert envoi['notif_url'].startswith('https://ecole.example/api/orange-money/notification?ref=')
    assert _reste(client, entetes, e['id']) == 500000  # rien n'est encaissé avant confirmation

    # fausse notification : refusée
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'status': 'SUCCESS', 'notif_token': 'FAUX'}).status_code == 403
    assert _reste(client, entetes, e['id']) == 500000
    # vraie notification mais Orange dit encore « en cours » : rien
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'}).status_code == 200
    assert _reste(client, entetes, e['id']) == 500000
    # Orange confirme
    etat['statut'] = 'SUCCESS'
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'}).status_code == 200
    assert _reste(client, entetes, e['id']) == 100000
    # notification répétée / retour du parent : pas de double encaissement
    client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'})
    page = client.get(f'/api/orange-money/retour?ref={rid}')
    assert 'Paiement confirmé' in page.get_data(as_text=True)
    assert _reste(client, entetes, e['id']) == 100000
    liste = client.get('/api/orange-money/paiements', headers=entetes).get_json()
    assert liste[0]['statut'] == 'reussi' and liste[0]['numero_recu'].startswith('REC-')


def test_paiement_echoue_et_montants_invalides(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, *_ = _dossier(client, entetes, creer_eleve, creer_paiement)
    assert client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 999999999}, headers=entetes).status_code == 400
    assert client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 10}, headers=entetes).status_code == 400
    rid = client.post('/api/orange-money/lien', json={'eleve_id': e['id']}, headers=entetes).get_json()['id']
    etat['statut'] = 'FAILED'
    assert client.post(f'/api/orange-money/verifier/{rid}', headers=entetes).get_json()['statut'] == 'echoue'
    assert _reste(client, entetes, e['id']) == 500000
    etat['statut'] = 'SUCCESS'  # un échec déjà constaté ne se transforme pas en encaissement
    assert client.post(f'/api/orange-money/verifier/{rid}', headers=entetes).get_json()['statut'] == 'echoue'
    assert _reste(client, entetes, e['id']) == 500000


def test_solde_regle_entre_temps_va_en_verification(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    rid = client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 100000}, headers=entetes).get_json()['id']
    for p, m in ((p1, 300000), (p2, 200000)):
        assert client.post(f"/api/paiements/{p['id']}/verser", json={'montant': m}, headers=entetes).status_code == 200
    etat['statut'] = 'SUCCESS'
    assert client.post(f'/api/orange-money/verifier/{rid}', headers=entetes).get_json()['statut'] == 'a_verifier'


# ───────────── paiement marchand par QR ─────────────
def test_declaration_validation_et_doublon(client, entetes, creer_eleve, creer_paiement):
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 400000, 'transaction_id': 'MP261020.2345.A12345'}, headers=entetes)
    assert r.status_code == 201 and r.get_json()['statut'] == 'a_valider'
    assert _reste(client, entetes, e['id']) == 500000  # pas encore encaissé
    # même numéro de transaction : refusé, même écrit autrement
    assert client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 400000, 'transaction_id': 'mp261020.2345.a12345'}, headers=entetes).status_code == 409
    did = r.get_json()['id']
    assert len(client.get('/api/orange-money/declarations?statut=a_valider', headers=entetes).get_json()) == 1
    v = client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes)
    assert v.status_code == 200 and v.get_json()['numero_recu'].startswith('REC-')
    assert _reste(client, entetes, e['id']) == 100000
    assert client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes).status_code == 409  # une seule fois
    assert _reste(client, entetes, e['id']) == 100000


def test_encaissement_direct_rejet_et_controles(client, entetes, creer_eleve, creer_paiement):
    e, *_ = _dossier(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 500000, 'transaction_id': 'TX-DIRECT-001', 'valider': True}, headers=entetes)
    assert r.status_code == 201 and r.get_json()['statut'] == 'valide' and _reste(client, entetes, e['id']) == 0
    assert client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 5000, 'transaction_id': 'ab'}, headers=entetes).status_code == 400
    e2, *_ = _dossier(client, entetes, creer_eleve, creer_paiement)
    did = client.post('/api/orange-money/declarations', json={'eleve_id': e2['id'], 'montant': 5000, 'transaction_id': 'TX-REJET-002'}, headers=entetes).get_json()['id']
    assert client.post(f'/api/orange-money/declarations/{did}/rejeter', json={'motif': 'x'}, headers=entetes).status_code == 400
    assert client.post(f'/api/orange-money/declarations/{did}/rejeter', json={'motif': 'Transaction introuvable chez Orange'}, headers=entetes).status_code == 200
    assert client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes).status_code == 409
    assert _reste(client, entetes, e2['id']) == 500000
    assert client.post('/api/orange-money/declarations', json={}).status_code == 401


def test_config_marchand(client, entetes):
    r = client.put('/api/orange-money/config', json={'nom': 'GS El Hadji Mountaga Djely', 'code': '123456', 'instructions': 'Scannez le QR'}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['code'] == '123456'
    assert client.get('/api/orange-money/config', headers=entetes).get_json()['nom'].startswith('GS El Hadji')
