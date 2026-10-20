"""Double authentification TOTP : module, activation, connexion en deux étapes, codes de secours."""
import time

import pytest

import double_authentification as da


def test_vecteur_rfc6238():
    # Vecteur de test officiel RFC 6238 (SHA-1, secret ASCII « 12345678901234567890 », t=59 s, 8 chiffres)
    import base64
    secret = base64.b32encode(b'12345678901234567890').decode()
    assert da.code_a(secret, 59 // 30, 8) == '94287082'


def test_verification_tolerance_et_rejeu():
    s = da.nouveau_secret()
    t = 1_700_000_000
    pas = t // 30
    code = da.code_a(s, pas)
    assert da.verifier(s, code, 0, t) == pas
    assert da.verifier(s, code, pas, t) is None                      # même code refusé une seconde fois
    assert da.verifier(s, da.code_a(s, pas - 1), 0, t) == pas - 1     # horloge en retard d'une période
    assert da.verifier(s, da.code_a(s, pas + 5), 0, t) is None        # trop loin
    assert da.verifier(s, '12ab', 0, t) is None


def test_codes_de_secours_usage_unique():
    codes, emp = da.generer_codes_secours()
    assert len(codes) == 8
    reste = da.consommer_code_secours(emp, codes[0])
    assert reste is not None and da.consommer_code_secours(reste, codes[0]) is None
    assert da.consommer_code_secours(emp, 'zzzz-zzzz') is None


@pytest.fixture
def compte_2fa(client, entetes):
    nom = f"deux{int(time.time()*1000) % 10**8}"
    r = client.post('/api/users', json={'username': nom, 'password': 'Provisoire-1', 'full_name': 'Deux', 'role': 'secretaire'}, headers=entetes)
    assert r.status_code == 201
    uid = r.get_json()['id']
    tok = client.post('/api/auth/login', json={'username': nom, 'password': 'Provisoire-1'}).get_json()['token']
    r = client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Solide-2026'},
                    headers={'Authorization': f'Bearer {tok}'})
    h = {'Authorization': f"Bearer {r.get_json()['token']}"}
    return nom, uid, h


def _activer(client, h):
    p = client.post('/api/auth/2fa/preparer', headers=h).get_json()
    assert p['uri'].startswith('otpauth://totp/')
    code = da.code_a(p['secret'], int(time.time() // 30))
    r = client.post('/api/auth/2fa/activer', json={'code': code}, headers=h)
    assert r.status_code == 200, r.get_json()
    return p['secret'], r.get_json()['codes_secours']


def test_activation_mauvais_code_refuse(client, compte_2fa):
    _, _, h = compte_2fa
    client.post('/api/auth/2fa/preparer', headers=h)
    assert client.post('/api/auth/2fa/activer', json={'code': '000000'}, headers=h).status_code == 400
    assert client.get('/api/auth/2fa', headers=h).get_json()['actif'] is False


def test_connexion_en_deux_etapes_et_code_de_secours(client, compte_2fa):
    nom, _, h = compte_2fa
    secret, secours = _activer(client, h)
    assert len(secours) == 8
    # étape 1 : mot de passe seul -> pas de jeton
    r = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026'})
    assert r.status_code == 200 and r.get_json() == {'requires_2fa': True}
    # mauvais code
    r = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026', 'code_2fa': '123456'})
    assert r.status_code == 401
    # code de secours (le code TOTP courant est déjà consommé par l'activation)
    r = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026', 'code_2fa': secours[0]})
    assert r.status_code == 200 and r.get_json()['token'] and r.get_json()['user']['codes_secours_restants'] == 7
    # le même code de secours ne resservira pas
    r = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026', 'code_2fa': secours[0]})
    assert r.status_code == 401


def test_code_totp_valide_une_seule_fois(client, compte_2fa):
    nom, _, h = compte_2fa
    secret, _ = _activer(client, h)
    suivant = da.code_a(secret, int(time.time() // 30) + 1)          # pas suivant, accepté par la tolérance
    ok = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026', 'code_2fa': suivant})
    assert ok.status_code == 200 and ok.get_json().get('token')
    rejeu = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026', 'code_2fa': suivant})
    assert rejeu.status_code == 401


def test_reinitialisation_par_admin(client, entetes, compte_2fa):
    nom, uid, h = compte_2fa
    _activer(client, h)
    assert client.post(f'/api/users/{uid}/reset-2fa', headers=entetes).status_code == 200
    r = client.post('/api/auth/login', json={'username': nom, 'password': 'Solide-2026'})
    assert r.status_code == 200 and r.get_json().get('token')
    assert client.post(f'/api/users/{uid}/reset-2fa', headers=h).status_code == 403   # un non-admin ne peut pas


def test_desactivation_exige_mot_de_passe_et_code(client, compte_2fa):
    nom, _, h = compte_2fa
    secret, _ = _activer(client, h)
    code = da.code_a(secret, int(time.time() // 30) + 1)
    assert client.post('/api/auth/2fa/desactiver', json={'password': 'faux', 'code': code}, headers=h).status_code == 401
    assert client.post('/api/auth/2fa/desactiver', json={'password': 'Solide-2026', 'code': code}, headers=h).status_code == 200
    assert client.get('/api/auth/2fa', headers=h).get_json()['actif'] is False
