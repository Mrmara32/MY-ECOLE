"""Révocation des sessions et protection des fichiers téléversés."""
import io

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def _entete(token):
    return {'Authorization': 'Bearer ' + token}


def _connexion(client, username, mot_de_passe):
    r = client.post('/api/auth/login', json={'username': username, 'password': mot_de_passe})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['token']


def _creer_utilisateur(client, token, username, role='secretaire'):
    r = client.post('/api/users', headers=_entete(token), json={
        'username': username, 'password': 'Zebre#Lune-2026', 'full_name': 'Test ' + username, 'role': role})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['id']


def test_deconnexion_revoque_le_jeton(client, jeton_admin):
    from tests.conftest import MOT_DE_PASSE_ADMIN
    jeton_admin = _connexion(client, 'admin', MOT_DE_PASSE_ADMIN)
    assert client.get('/api/auth/me', headers=_entete(jeton_admin)).status_code == 200
    assert client.post('/api/auth/logout', headers=_entete(jeton_admin)).status_code == 200
    assert client.get('/api/auth/me', headers=_entete(jeton_admin)).status_code == 401


def test_changement_de_role_coupe_les_sessions(client, jeton_admin):
    uid = _creer_utilisateur(client, jeton_admin, 'sess_role')
    tok = _connexion(client, 'sess_role', 'Zebre#Lune-2026')
    assert client.get('/api/auth/me', headers=_entete(tok)).status_code == 200
    client.put(f'/api/users/{uid}', headers=_entete(jeton_admin), json={'role': 'enseignant'})
    assert client.get('/api/auth/me', headers=_entete(tok)).status_code == 401
    # la nouvelle connexion fonctionne
    assert client.get('/api/auth/me', headers=_entete(_connexion(client, 'sess_role', 'Zebre#Lune-2026'))).status_code == 200


def test_desactivation_et_reset_mdp_coupent_les_sessions(client, jeton_admin):
    uid = _creer_utilisateur(client, jeton_admin, 'sess_off')
    tok = _connexion(client, 'sess_off', 'Zebre#Lune-2026')
    client.put(f'/api/users/{uid}', headers=_entete(jeton_admin), json={'active': False})
    assert client.get('/api/auth/me', headers=_entete(tok)).status_code == 401

    uid2 = _creer_utilisateur(client, jeton_admin, 'sess_pwd')
    tok2 = _connexion(client, 'sess_pwd', 'Zebre#Lune-2026')
    r = client.post(f'/api/users/{uid2}/reset-password', headers=_entete(jeton_admin), json={'newPassword': 'Autre#Zebre-99x'})
    assert r.status_code == 200
    assert client.get('/api/auth/me', headers=_entete(tok2)).status_code == 401


def test_revocation_admin_et_deconnexion_partout(client, jeton_admin):
    uid = _creer_utilisateur(client, jeton_admin, 'sess_rev')
    tok = _connexion(client, 'sess_rev', 'Zebre#Lune-2026')
    tok_bis = _connexion(client, 'sess_rev', 'Zebre#Lune-2026')
    assert client.post(f'/api/users/{uid}/revoquer-sessions', headers=_entete(jeton_admin)).status_code == 200
    assert client.get('/api/auth/me', headers=_entete(tok)).status_code == 401
    assert client.get('/api/auth/me', headers=_entete(tok_bis)).status_code == 401
    tok3 = _connexion(client, 'sess_rev', 'Zebre#Lune-2026')
    assert client.post('/api/auth/logout-all', headers=_entete(tok3)).status_code == 200
    assert client.get('/api/auth/me', headers=_entete(tok3)).status_code == 401


def test_fichiers_prives_exigent_une_connexion(client, jeton_admin, creer_eleve):
    from tests.conftest import MOT_DE_PASSE_ADMIN
    eleve_id = creer_eleve()['id']
    jeton_admin = _connexion(client, 'admin', MOT_DE_PASSE_ADMIN)
    r = client.post(f'/api/eleves/{eleve_id}/photo', headers=_entete(jeton_admin),
                    data={'photo': (io.BytesIO(PNG), 'p.png')}, content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    url = r.get_json()['photo_url']
    assert url.startswith('/uploads/') and len(url) > 24  # nom imprévisible
    client.delete_cookie('gs_media', path='/uploads')
    assert client.get(url).status_code == 401                                    # anonyme
    assert client.get(url, headers=_entete(jeton_admin)).status_code == 200      # en-tête
    # cookie posé par une requête d'API authentifiée, utilisable par un <img>
    client.get('/api/auth/me', headers=_entete(jeton_admin))
    assert client.get(url).status_code == 200
    # après déconnexion le cookie ne donne plus accès
    client.post('/api/auth/logout', headers=_entete(jeton_admin))
    assert client.get(url).status_code == 401


def test_logo_reste_public(client, jeton_admin):
    r = client.post('/api/settings/logo', headers=_entete(jeton_admin),
                    data={'logo': (io.BytesIO(PNG), 'l.png')}, content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    url = r.get_json().get('logo_url') or r.get_json().get('url')
    client.delete_cookie('gs_media', path='/uploads')
    assert client.get(url).status_code == 200


def test_fichier_d_une_autre_ecole_refuse(client, jeton_admin):
    _creer_utilisateur(client, jeton_admin, 'sec_ecole')
    jeton = _connexion(client, 'sec_ecole', 'Zebre#Lune-2026')
    r = client.post('/api/auth/change-password', headers=_entete(jeton),
                    json={'oldPassword': 'Zebre#Lune-2026', 'newPassword': 'Nouveau#Zebre-77'})
    jeton = r.get_json()['token']
    client.delete_cookie('gs_media', path='/uploads')
    assert client.get('/uploads/e999_abc.png', headers=_entete(jeton)).status_code == 403
    assert client.get('/uploads/e1_abc.png', headers=_entete(jeton)).status_code != 403  # sa propre école : pas refusé
