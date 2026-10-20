"""Envoi d'e-mails par l'API web de Brevo (serveur factice local)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import email_service

recus = []


class FauxBrevo(BaseHTTPRequestHandler):
    def do_POST(self):
        recus.append({'cle': self.headers.get('api-key'),
                      'corps': json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
        self.send_response(400 if recus[-1]['corps']['subject'] == 'refuse' else 201)
        self.end_headers()
        self.wfile.write(b'{}')

    def log_message(self, *a):
        pass


def _serveur(monkeypatch):
    recus.clear()
    srv = HTTPServer(('127.0.0.1', 0), FauxBrevo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv('BREVO_API_URL', f'http://127.0.0.1:{srv.server_port}/v3/smtp/email')
    monkeypatch.setenv('BREVO_API_KEY', 'cle-test')
    monkeypatch.setenv('EMAIL_EXPEDITEUR', 'ecole@example.org')
    monkeypatch.setenv('EMAIL_EXPEDITEUR_NOM', 'MY-ECOLE')
    return srv


def test_envoi_par_api_avec_piece_jointe(monkeypatch):
    srv = _serveur(monkeypatch)
    try:
        ok = email_service.envoyer_email('parent@example.org', 'Reçu', '<p>Bonjour</p>',
                                         piece_jointe={'nom_fichier': 'recu.pdf', 'contenu_base64': 'QUJD', 'type_mime': 'application/pdf'})
    finally:
        srv.shutdown()
    assert ok and recus[0]['cle'] == 'cle-test'
    c = recus[0]['corps']
    assert c['sender'] == {'email': 'ecole@example.org', 'name': 'MY-ECOLE'}
    assert c['to'] == [{'email': 'parent@example.org'}] and c['attachment'][0]['name'] == 'recu.pdf'


def test_refus_de_brevo_ne_leve_pas(monkeypatch):
    srv = _serveur(monkeypatch)
    try:
        assert email_service.envoyer_email('a@b.org', 'refuse', '<p>x</p>') is False
    finally:
        srv.shutdown()


def test_sans_expediteur_echec_propre(monkeypatch):
    monkeypatch.setenv('BREVO_API_KEY', 'k')
    monkeypatch.delenv('EMAIL_EXPEDITEUR', raising=False)
    monkeypatch.delenv('EMAIL_ADRESSE', raising=False)
    assert email_service.envoyer_email('a@b.org', 's', '<p>x</p>') is False
