"""Bilan hebdomadaire : contenu agrégé sans noms, un seul envoi par semaine, désactivable."""
import bilan_hebdo
from tests.test_assistant import _peupler


def _preparer(monkeypatch):
    from database import db
    db.execute("UPDATE users SET email='direction@test.gn' WHERE username='admin'")
    db.execute("DELETE FROM settings WHERE ecole_id=1 AND cle IN ('bilan_dernier_envoi','bilan_hebdo_actif')")
    db.commit()
    envoyes = []
    monkeypatch.setattr(bilan_hebdo.email_service, 'envoyer_email', lambda d, s, h, *a, **k: envoyes.append((d, s, h)) or True)
    return envoyes


def test_contenu_du_bilan_sans_noms(client, monkeypatch):
    _peupler()
    html, nb = bilan_hebdo.contenu_bilan(1)
    assert 'élèves actifs' in html and 'Points d' in html and nb >= 1
    assert 'Secret' not in html


def test_un_seul_envoi_par_semaine_et_desactivable(client, monkeypatch):
    envoyes = _preparer(monkeypatch)
    _peupler()
    assert bilan_hebdo.envoyer_bilan(1) == 1 and envoyes[0][0] == 'direction@test.gn'
    assert bilan_hebdo.envoyer_bilan(1) == 0                      # déjà envoyé cette semaine
    assert bilan_hebdo.envoyer_bilan(1, force=True) == 1          # envoi manuel
    from database import db
    db.execute("DELETE FROM settings WHERE ecole_id=1 AND cle='bilan_dernier_envoi'")
    db.execute("INSERT OR REPLACE INTO settings (ecole_id,cle,valeur) VALUES (1,'bilan_hebdo_actif','0')"); db.commit()
    assert bilan_hebdo.envoyer_bilan(1) == 0
    db.execute("DELETE FROM settings WHERE ecole_id=1 AND cle='bilan_hebdo_actif'"); db.commit()


def test_envoi_manuel_reserve_a_la_direction(client, entetes, monkeypatch):
    envoyes = _preparer(monkeypatch)
    r = client.post('/api/assistant/bilan', headers=entetes, json={})
    assert r.status_code == 200 and r.get_json()['destinataires'] == 1
    assert client.post('/api/assistant/bilan', json={}).status_code == 401
