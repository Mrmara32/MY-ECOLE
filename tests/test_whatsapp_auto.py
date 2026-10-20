"""Envoi automatique WhatsApp (Cloud API) — serveur Meta factice."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

recus = []


class FauxMeta(BaseHTTPRequestHandler):
    def do_POST(self):
        recus.append({'chemin': self.path, 'auth': self.headers.get('Authorization'),
                      'corps': json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"messages":[{"id":"wamid.TEST"}]}')

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_meta(monkeypatch):
    recus.clear()
    srv = HTTPServer(('127.0.0.1', 0), FauxMeta)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for k, v in {'WHATSAPP_API_URL': f'http://127.0.0.1:{srv.server_port}', 'WHATSAPP_TOKEN': 'jeton',
                 'WHATSAPP_PHONE_ID': '123', 'WHATSAPP_MODELE_ABSENCE': 'absence_eleve',
                 'WHATSAPP_MODELE_RELANCE': 'relance_scolarite'}.items():
        monkeypatch.setenv(k, v)
    yield
    srv.shutdown()


def _eleve_avec_mere(client, entetes, creer_eleve, tel='622 98 76 54'):
    e = creer_eleve(nom='Sow', prenom='Fanta', classe='CE1')
    r = client.put(f"/api/eleves/{e['id']}", json={'mere_prenom': 'Kadi', 'mere_nom': 'Bah', 'mere_telephone': tel}, headers=entetes)
    assert r.status_code == 200, r.get_json()
    return e


def test_statut_et_inactif_par_defaut(client, entetes, creer_eleve):
    assert client.get('/api/whatsapp/statut', headers=entetes).get_json() == {'actif': False}
    e = _eleve_avec_mere(client, entetes, creer_eleve)
    a = client.post('/api/absences', json={'eleve_id': e['id'], 'date_abs': '2026-10-19'}, headers=entetes).get_json()
    assert client.post(f"/api/whatsapp/absence/{a['id']}", headers=entetes).status_code == 503


def test_absence_envoyee_une_seule_fois(client, entetes, creer_eleve, faux_meta):
    e = _eleve_avec_mere(client, entetes, creer_eleve)
    a = client.post('/api/absences', json={'eleve_id': e['id'], 'date_abs': '2026-10-19'}, headers=entetes).get_json()
    r = client.post(f"/api/whatsapp/absence/{a['id']}", headers=entetes)
    assert r.status_code == 200 and r.get_json()['message_id'] == 'wamid.TEST'
    m = recus[0]
    assert m['chemin'] == '/v21.0/123/messages' and m['auth'] == 'Bearer jeton'
    assert m['corps']['to'] == '224622987654' and m['corps']['template']['name'] == 'absence_eleve'
    textes = [p['text'] for p in m['corps']['template']['components'][0]['parameters']]
    assert textes[0] == 'Kadi Bah' and textes[1] == 'Fanta Sow' and textes[2] == 'était absent(e)' and textes[3] == '19/10/2026'
    assert client.post(f"/api/whatsapp/absence/{a['id']}", headers=entetes).status_code == 409
    assert len(recus) == 1


def test_relance_montant_et_anti_doublon(client, entetes, creer_eleve, faux_meta):
    from database import db
    e = _eleve_avec_mere(client, entetes, creer_eleve)
    ec = db.execute("SELECT ecole_id FROM eleves WHERE id=?", (e['id'],)).fetchone()['ecole_id']
    db.execute("INSERT INTO paiements (id,ecole_id,eleve_id,montant_du,montant_paye) VALUES (?,?,?,?,?)",
               ('pai-wa', ec, e['id'], 1500000, 500000))
    db.commit()
    r = client.post(f"/api/whatsapp/relance/{e['id']}", headers=entetes)
    assert r.status_code == 200, r.get_json()
    assert recus[0]['corps']['template']['components'][0]['parameters'][4]['text'] == '1 000 000 GNF'
    assert client.post(f"/api/whatsapp/relance/{e['id']}", headers=entetes).status_code == 409


def test_sans_telephone_refuse(client, entetes, creer_eleve, faux_meta):
    e = creer_eleve(nom='Sans', prenom='Tel', classe='CE1')
    a = client.post('/api/absences', json={'eleve_id': e['id'], 'date_abs': '2026-10-19'}, headers=entetes).get_json()
    assert client.post(f"/api/whatsapp/absence/{a['id']}", headers=entetes).status_code == 400
