"""Protection des comptes : blocage après échecs, règles de mot de passe, mot de passe provisoire."""
import os
import pytest

import securite


def _login(client, user, mdp):
    return client.post('/api/auth/login', json={'username': user, 'password': mdp})


@pytest.fixture
def creer_compte(client, entetes):
    def _creer(username, mdp='Provisoire-1', role='secretaire'):
        r = client.post('/api/users', json={'username': username, 'password': mdp, 'full_name': username.title(), 'role': role}, headers=entetes)
        assert r.status_code == 201, r.get_json()
        return r.get_json()
    return _creer


def test_regles_de_mot_de_passe():
    assert securite.erreur_mot_de_passe('abc123') is not None            # trop court
    assert securite.erreur_mot_de_passe('abcdefgh') is not None          # pas de chiffre
    assert securite.erreur_mot_de_passe('12345678') is not None          # pas de lettre
    assert securite.erreur_mot_de_passe('Password1') is not None         # mot de passe courant
    assert securite.erreur_mot_de_passe('admin@2025!') is not None       # mot de passe par défaut publié
    assert securite.erreur_mot_de_passe('Rentree2026') is not None       # pas de symbole
    assert securite.erreur_mot_de_passe('Rentree-2026') is None
    assert securite.erreur_mot_de_passe('Rentree-2026', role='comptable') is None
    assert securite.erreur_mot_de_passe('Rentree-26', role='comptable') is not None   # 12 caractères pour les rôles sensibles
    assert securite.erreur_mot_de_passe('12345678') is not None          # uniquement numérique
    assert securite.erreur_mot_de_passe('Mara-Conakry-9', username='mara') is not None  # proche du nom d'utilisateur


def test_creation_de_compte_refuse_mot_de_passe_faible(client, entetes):
    r = client.post('/api/users', json={'username': 'faible', 'password': 'abc', 'full_name': 'F', 'role': 'secretaire'}, headers=entetes)
    assert r.status_code == 400


def test_blocage_apres_cinq_echecs_puis_deblocage_par_reussite_avant_limite(client, creer_compte):
    creer_compte('bloque1')
    for _ in range(5):
        assert _login(client, 'bloque1', 'mauvais-mdp-1').status_code == 401
    r = _login(client, 'bloque1', 'Provisoire-1')       # même le bon mot de passe est refusé pendant le blocage
    assert r.status_code == 429 and int(r.headers['Retry-After']) > 0
    assert 'minute' in r.get_json()['error']


def test_reussite_remet_le_compteur_a_zero(client, creer_compte):
    creer_compte('reset1')
    for _ in range(4):
        _login(client, 'reset1', 'mauvais-mdp-1')
    assert _login(client, 'reset1', 'Provisoire-1').status_code == 200
    for _ in range(4):                                  # 4 nouveaux échecs : pas encore bloqué
        assert _login(client, 'reset1', 'mauvais-mdp-1').status_code == 401
    assert _login(client, 'reset1', 'Provisoire-1').status_code == 200


def test_blocage_expire(client, creer_compte):
    import database
    creer_compte('expire1')
    for _ in range(5):
        _login(client, 'expire1', 'mauvais-mdp-1')
    assert _login(client, 'expire1', 'Provisoire-1').status_code == 429
    database.db.execute("UPDATE echecs_connexion SET bloque_jusqu='2000-01-01 00:00:00' WHERE cle LIKE 'u:%expire1'")
    database.db.commit()
    assert _login(client, 'expire1', 'Provisoire-1').status_code == 200


def test_mot_de_passe_provisoire_bloque_tout_sauf_le_changement(client, creer_compte):
    creer_compte('prov1')
    r = _login(client, 'prov1', 'Provisoire-1').get_json()
    assert r['user']['doit_changer_mot_de_passe'] is True
    h = {'Authorization': f"Bearer {r['token']}"}
    bloque = client.get('/api/eleves', headers=h)
    assert bloque.status_code == 403 and bloque.get_json()['code'] == 'MOT_DE_PASSE_A_CHANGER'
    assert client.get('/api/auth/me', headers=h).get_json()['doit_changer_mot_de_passe'] is True
    # nouveau mot de passe identique ou faible : refusé
    assert client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Provisoire-1'}, headers=h).status_code == 400
    assert client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'court1'}, headers=h).status_code == 400
    ok = client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Definitif-2026'}, headers=h)
    assert ok.status_code == 200
    h2 = {'Authorization': f"Bearer {ok.get_json()['token']}"}
    assert client.get('/api/eleves', headers=h2).status_code == 200
    assert _login(client, 'prov1', 'Definitif-2026').get_json()['user']['doit_changer_mot_de_passe'] is False


def test_reinitialisation_par_admin_rend_le_mot_de_passe_provisoire(client, entetes, creer_compte):
    u = creer_compte('reinit1')
    h = {'Authorization': f"Bearer {_login(client, 'reinit1', 'Provisoire-1').get_json()['token']}"}
    client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Choisi-par-moi-1'}, headers=h)
    assert _login(client, 'reinit1', 'Choisi-par-moi-1').get_json()['user']['doit_changer_mot_de_passe'] is False
    assert client.post(f"/api/users/{u['id']}/reset-password", json={'newPassword': 'faible'}, headers=entetes).status_code == 400
    assert client.post(f"/api/users/{u['id']}/reset-password", json={'newPassword': 'Nouveau-Temp-3'}, headers=entetes).status_code == 200
    assert _login(client, 'reinit1', 'Nouveau-Temp-3').get_json()['user']['doit_changer_mot_de_passe'] is True


@pytest.mark.skipif(bool(os.environ.get("TEST_PG")), reason="lance un processus SQLite isolé")
def test_admin_par_defaut_doit_changer_son_mot_de_passe(tmp_path, monkeypatch):
    """Sans ADMIN_PASSWORD configuré, le compte admin créé au premier démarrage est en mot de passe provisoire."""
    import sqlite3, subprocess, sys, os, textwrap
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = textwrap.dedent("""
        import database, sys
        r = database.db.execute("SELECT doit_changer_mdp FROM users WHERE username='admin'").fetchone()
        print('FLAG', r['doit_changer_mdp'])
    """)
    env = {k: v for k, v in os.environ.items() if k not in ('ADMIN_PASSWORD', 'RENDER')}
    env.update({'GS_DATA_DIR': str(tmp_path / 'd'), 'GS_UPLOADS_DIR': str(tmp_path / 'u'), 'GS_LOGS_DIR': str(tmp_path / 'l'), 'PYTHONPATH': racine})
    sortie = subprocess.run([sys.executable, '-c', "from app import app\n" + code], cwd=racine, env=env,
                            capture_output=True, text=True, timeout=120)
    assert 'FLAG 1' in sortie.stdout, sortie.stdout + sortie.stderr


def test_ancien_mot_de_passe_par_defaut_publie_est_signale():
    import database
    from werkzeug.security import generate_password_hash
    database.db.execute("INSERT INTO users (ecole_id,username,password_hash,full_name,role) VALUES (1,?,?,?,?)",
                        ('admin-ancien', generate_password_hash('Admin@2025!'), 'Ancien', 'admin'))
    database.db.execute("INSERT INTO users (ecole_id,username,password_hash,full_name,role) VALUES (1,?,?,?,?)",
                        ('admin-sain', generate_password_hash('Mot-de-passe-perso-9'), 'Sain', 'admin'))
    database.db.commit()
    assert database.signaler_mots_de_passe_par_defaut() == 1
    flags = {r['username']: r['doit_changer_mdp'] for r in database.db.execute("SELECT username, doit_changer_mdp FROM users WHERE username IN ('admin-ancien','admin-sain')")}
    assert flags == {'admin-ancien': 1, 'admin-sain': 0}
