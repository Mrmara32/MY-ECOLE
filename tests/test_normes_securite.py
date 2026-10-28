"""Normes de sécurité : jetons courts + renouvellement, inactivité, appareils, débit, 2FA obligatoire, motif, chiffrement."""
import time
import pytest

from tests.conftest import MOT_DE_PASSE_ADMIN


def _h(t):
    return {'Authorization': 'Bearer ' + t}


def _login(client, user='admin', mdp=MOT_DE_PASSE_ADMIN):
    r = client.post('/api/auth/login', json={'username': user, 'password': mdp})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_renouvellement_a_usage_unique(client):
    d = _login(client)
    assert d['refresh_token']
    r = client.post('/api/auth/refresh', json={'refresh_token': d['refresh_token']})
    assert r.status_code == 200
    nouveau = r.get_json()
    assert client.get('/api/auth/me', headers=_h(nouveau['token'])).status_code == 200
    # l'ancien jeton de renouvellement est « utilisé » : refusé
    assert client.post('/api/auth/refresh', json={'refresh_token': d['refresh_token']}).status_code == 401
    assert client.post('/api/auth/refresh', json={'refresh_token': 'n-importe-quoi'}).status_code == 401


def test_jeton_d_acces_dure_une_heure(client):
    import jwt, auth
    d = _login(client)
    p = jwt.decode(d['token'], auth.get_secret(), algorithms=['HS256'])
    assert 3500 <= p['exp'] - p['iat'] <= 3700 and p.get('sid')


def test_deconnexion_coupe_aussi_le_renouvellement(client):
    d = _login(client)
    client.post('/api/auth/logout', headers=_h(d['token']))
    assert client.post('/api/auth/refresh', json={'refresh_token': d['refresh_token']}).status_code == 401


def test_inactivite_30_minutes(client):
    from database import db
    d = _login(client)
    assert client.get('/api/auth/me', headers=_h(d['token'])).status_code == 200
    import jwt, auth
    sid = jwt.decode(d['token'], auth.get_secret(), algorithms=['HS256'])['sid']
    db.execute("UPDATE sessions_appareils SET derniere_activite=? WHERE id=?", (int(time.time()) - 31 * 60, sid))
    db.commit()
    r = client.get('/api/auth/me', headers=_h(d['token']))
    assert r.status_code == 401 and 'inactivité' in r.get_json()['error']


def test_liste_et_deconnexion_des_appareils(client):
    a, b = _login(client), _login(client)
    liste = client.get('/api/auth/sessions', headers=_h(a['token'])).get_json()
    assert len(liste) >= 2 and sum(1 for s in liste if s['courante']) == 1
    autre = next(s for s in liste if not s['courante'])
    assert client.delete(f"/api/auth/sessions/{autre['id']}", headers=_h(a['token'])).status_code == 200
    assert client.get('/api/auth/sessions', headers=_h(a['token'])).status_code == 200


def test_limitation_du_debit_connexion(client):
    import securite
    client.application.config['DEBIT_ACTIF'] = True
    securite._debit.clear()
    try:
        codes = [client.post('/api/auth/refresh', json={'refresh_token': 'x'}).status_code for _ in range(12)]
        assert codes[:10] == [401] * 10 and codes[10] == 429
        securite._debit.clear()
        codes = [client.get('/api/public/inexistant').status_code for _ in range(62)]
        assert 429 in codes[60:]
    finally:
        client.application.config['DEBIT_ACTIF'] = False
        securite._debit.clear()


def test_double_authentification_obligatoire_pour_les_roles_sensibles(client, monkeypatch):
    monkeypatch.setenv('GS_2FA_OBLIGATOIRE', '1')
    d = _login(client)
    assert d['user']['double_auth_requise'] is True
    assert client.get('/api/eleves', headers=_h(d['token'])).status_code == 403
    assert client.get('/api/eleves', headers=_h(d['token'])).get_json()['code'] == 'DOUBLE_AUTH_REQUISE'
    assert client.get('/api/auth/me', headers=_h(d['token'])).status_code == 200
    # activation : le secret est chiffré en base et le nouveau jeton débloque l'accès
    import double_authentification as da
    from database import db
    p = client.post('/api/auth/2fa/preparer', headers=_h(d['token'])).get_json()
    brut = db.execute("SELECT totp_secret FROM users WHERE username='admin'").fetchone()['totp_secret']
    assert brut != p['secret'] and brut.startswith('enc:')
    code = da.code_a(p['secret'], int(time.time()) // 30)
    r = client.post('/api/auth/2fa/activer', headers=_h(d['token']), json={'code': code})
    assert r.status_code == 200
    assert client.get('/api/eleves', headers=_h(r.get_json()['token'])).status_code == 200
    db.execute("UPDATE users SET totp_actif=0, totp_secret=NULL, codes_secours=NULL WHERE username='admin'")  # la base est partagée entre les tests
    db.commit()


def test_motif_obligatoire_pour_supprimer_une_donnee_financiere(client, entetes):
    client.application.config['MOTIF_ACTIF'] = True
    try:
        t = client.post('/api/transactions', headers=entetes, json={'type': 'sortie', 'date_op': '2026-01-05', 'categorie': 'Test', 'montant': 100,
                                                                       'description': 'à supprimer', 'date': '2026-01-05'})
        tid = t.get_json().get('id')
        assert tid
        r = client.delete(f'/api/transactions/{tid}', headers=entetes)
        assert r.status_code == 400 and r.get_json()['code'] == 'MOTIF_REQUIS'
        r = client.delete(f'/api/transactions/{tid}', headers={**entetes, 'X-Motif': 'Doublon%20saisi%20par%20erreur'})
        assert r.status_code == 200
        from database import db
        ligne = db.execute("SELECT details FROM journal_audit WHERE details LIKE '%Doublon saisi%' LIMIT 1").fetchone()
        assert ligne
    finally:
        client.application.config['MOTIF_ACTIF'] = False


def test_secrets_chiffres_fernet():
    import coffre
    c = coffre.chiffrer('secret-messagerie')
    assert c != 'secret-messagerie' and coffre.dechiffrer(c) == 'secret-messagerie'
    assert coffre.dechiffrer('ancienne-valeur-en-clair') == 'ancienne-valeur-en-clair'


def test_redirection_https(client, monkeypatch):
    monkeypatch.setenv('FORCE_HTTPS', '1')
    r = client.get('/', headers={'X-Forwarded-Proto': 'http'})
    assert r.status_code == 301 and r.headers['Location'].startswith('https://')
    r = client.get('/', headers={'X-Forwarded-Proto': 'https'})
    assert r.status_code != 301 and 'max-age=31536000' in r.headers.get('Strict-Transport-Security', '')
