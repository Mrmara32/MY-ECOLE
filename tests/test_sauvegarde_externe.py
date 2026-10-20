"""Envoi chiffré des sauvegardes vers un stockage compatible S3 (serveur factice local)."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import sauvegarde_externe as ext

recus = []


class FauxS3(BaseHTTPRequestHandler):
    def do_PUT(self):
        corps = self.rfile.read(int(self.headers['Content-Length']))
        recus.append({'chemin': self.path, 'auth': self.headers.get('Authorization', ''), 'corps': corps})
        self.send_response(500 if 'refuse' in self.path else 200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_s3(monkeypatch):
    recus.clear()
    srv = HTTPServer(('127.0.0.1', 0), FauxS3)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for k, v in {'GS_S3_ENDPOINT': f'http://127.0.0.1:{srv.server_port}', 'GS_S3_REGION': 'auto',
                 'GS_S3_BUCKET': 'seau', 'GS_S3_KEY_ID': 'KID', 'GS_S3_SECRET': 'SEC',
                 'GS_BACKUP_CLE': 'mot de passe de test'}.items():
        monkeypatch.setenv(k, v)
    yield srv
    srv.shutdown()


def test_chiffrement_aller_retour_et_mauvaise_cle():
    c = ext.chiffrer(b'donnees eleves', 'bonne')
    assert b'eleves' not in c and ext.dechiffrer(c, 'bonne') == b'donnees eleves'
    with pytest.raises(Exception):
        ext.dechiffrer(c, 'mauvaise')


def test_non_configure_n_envoie_rien(monkeypatch):
    monkeypatch.delenv('GS_S3_BUCKET', raising=False)
    assert not ext.configure() and 'GS_S3_BUCKET' in ext.statut()['manquantes']
    assert ext.envoyer_si_besoin() is None


def test_envoi_chiffre_signe_et_une_seule_fois_par_jour(faux_s3):
    import sauvegarde
    sauvegarde.sauvegarde_du_jour()
    assert ext.envoyer_si_besoin()
    assert ext.envoyer_si_besoin() is None  # déjà parti aujourd'hui
    assert len(recus) == 1
    r = recus[0]
    assert r['chemin'].startswith('/seau/ecole-') and r['chemin'].endswith('.zip.enc')
    assert r['auth'].startswith('AWS4-HMAC-SHA256 Credential=KID/')
    clair = ext.dechiffrer(r['corps'], 'mot de passe de test')
    assert clair[:2] == b'PK'  # c'est bien le zip
    assert ext.statut()['dernier_envoi']


def test_echec_memorise_puis_reessaye(faux_s3, monkeypatch):
    import sauvegarde
    sauvegarde.sauvegarde_du_jour()
    monkeypatch.setattr(ext, 'lire_etat', lambda: {})
    monkeypatch.setattr(ext, 'televerser', lambda *a: (_ for _ in ()).throw(RuntimeError('panne')))
    with pytest.raises(RuntimeError):
        ext.envoyer_si_besoin()


def test_route_essai_reservee_au_super_admin(client, entetes, faux_s3):
    r = client.post('/api/systeme/sauvegardes/hors-serveur/essai', headers=entetes)
    assert r.status_code == 200 and r.get_json()['nom'].endswith('-manuel.zip.enc')
    assert client.get('/api/systeme/sauvegardes', headers=entetes).get_json()['hors_serveur']['configure'] is True
    assert client.post('/api/systeme/sauvegardes/hors-serveur/essai').status_code == 401
