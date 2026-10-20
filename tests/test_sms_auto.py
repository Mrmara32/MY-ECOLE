"""Envoi automatique de SMS (API Orange) — serveur factice local."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import sms_service

recus = []


class FauxOrange(BaseHTTPRequestHandler):
    def do_POST(self):
        corps = self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/oauth/v3/token':
            recus.append({'jeton_auth': self.headers.get('Authorization')})
            self.send_response(200); self.end_headers()
            self.wfile.write(b'{"access_token":"JETON1","expires_in":3600}')
            return
        recus.append({'chemin': self.path, 'auth': self.headers.get('Authorization'), 'corps': json.loads(corps)})
        self.send_response(201); self.end_headers()
        self.wfile.write(b'{"outboundSMSMessageRequest":{"resourceURL":"https://api.orange.com/x/requests/ID42"}}')

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_orange(monkeypatch):
    recus.clear()
    sms_service._jeton.update(valeur=None, expire=0)
    srv = HTTPServer(('127.0.0.1', 0), FauxOrange)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for k, v in {'ORANGE_API_URL': f'http://127.0.0.1:{srv.server_port}', 'ORANGE_SMS_AUTH': 'Basic abc',
                 'ORANGE_SMS_SENDER': '224622000000'}.items():
        monkeypatch.setenv(k, v)
    yield
    srv.shutdown()


def _eleve(client, entetes, creer_eleve):
    e = creer_eleve(nom='Sow', prenom='Fanta', classe='CE1')
    r = client.put(f"/api/eleves/{e['id']}", json={'mere_prenom': 'Kadi', 'mere_nom': 'Bah', 'mere_telephone': '622 98 76 54'}, headers=entetes)
    assert r.status_code == 200
    return e


def test_nettoyage_accents_et_longueur():
    assert sms_service.nettoyer("L’élève est arrivé à l’heure ôtée… « oui »") == 'L\'élève est arrivé à l\'heure otée... "oui"'
    assert len(sms_service.nettoyer('x' * 1000)) == sms_service.LONGUEUR_MAX


def test_non_configure(monkeypatch):
    monkeypatch.delenv('ORANGE_SMS_AUTH', raising=False)
    monkeypatch.delenv('ORANGE_SMS_CLIENT_ID', raising=False)
    assert not sms_service.actif() and 'ORANGE_SMS_AUTH' in sms_service.reglages_manquants()
    with pytest.raises(RuntimeError):
        sms_service.envoyer_sms('622987654', 'x')


def test_envoi_format_orange_et_jeton_reutilise(faux_orange):
    assert sms_service.envoyer_sms('622 98 76 54', 'Bonjour') == 'ID42'
    sms_service.envoyer_sms('622 98 76 54', 'Encore')
    jetons = [r for r in recus if 'jeton_auth' in r]
    envois = [r for r in recus if 'chemin' in r]
    assert len(jetons) == 1 and jetons[0]['jeton_auth'] == 'Basic abc'
    assert envois[0]['chemin'] == '/smsmessaging/v1/outbound/tel%3A%2B224622000000/requests'
    assert envois[0]['auth'] == 'Bearer JETON1'
    r = envois[0]['corps']['outboundSMSMessageRequest']
    assert r['address'] == 'tel:+224622987654' and r['senderAddress'] == 'tel:+224622000000'
    assert r['outboundSMSTextMessage']['message'] == 'Bonjour'


def test_routes_absence_et_relance(client, entetes, creer_eleve, faux_orange):
    e = _eleve(client, entetes, creer_eleve)
    assert client.get('/api/sms/statut', headers=entetes).get_json()['actif'] is True
    a = client.post('/api/absences', json={'eleve_id': e['id'], 'date_abs': '2026-10-19', 'type': 'absence'}, headers=entetes)
    assert a.status_code in (200, 201), a.get_json()
    aid = a.get_json()['id']
    r = client.post(f'/api/sms/absence/{aid}', json={'message': 'Fanta était absente'}, headers=entetes)
    assert r.status_code == 200, r.get_json()
    envoi = [x for x in recus if 'chemin' in x][-1]['corps']['outboundSMSMessageRequest']
    assert envoi['address'] == 'tel:+224622987654' and 'absente' in envoi['outboundSMSTextMessage']['message']
    assert client.post(f'/api/sms/absence/{aid}', json={}, headers=entetes).status_code == 409  # pas de doublon
    assert client.post(f'/api/sms/absence/inconnue', json={}, headers=entetes).status_code == 404
    assert client.post(f'/api/sms/relance/{e["id"]}', json={}, headers=entetes).status_code == 400  # aucun solde
    assert client.post(f'/api/sms/absence/{aid}').status_code == 401
