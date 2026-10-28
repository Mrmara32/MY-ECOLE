"""
Configuration commune des tests automatiques de MY-ECOLE.

Chaque lancement des tests utilise une base de données NEUVE dans un dossier
temporaire : aucun risque de toucher aux vraies données (ni sur Render, ni sur
un poste local). Lancer les tests :  python -m pytest -q
"""
import os
import sys
import tempfile

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOSSIER_TEMP = tempfile.mkdtemp(prefix='my-ecole-tests-')

# Ces variables DOIVENT être définies avant l'import de l'application, car la base
# de données est initialisée au moment de l'import.
os.environ.update({
    'GS_2FA_OBLIGATOIRE': '0',
    'GS_DATA_DIR': os.path.join(_DOSSIER_TEMP, 'data'),
    'GS_UPLOADS_DIR': os.path.join(_DOSSIER_TEMP, 'uploads'),
    'GS_LOGS_DIR': os.path.join(_DOSSIER_TEMP, 'logs'),
    'ADMIN_USERNAME': 'admin',
    'ADMIN_PASSWORD': 'Test-Admin-2026!',
    'JWT_SECRET': 'cle-utilisee-uniquement-pour-les-tests',
})
os.environ.pop('RENDER', None)
if os.environ.get('TEST_PG'):
    # Même suite de tests, sur un vrai PostgreSQL jetable (pip install pgserver "psycopg[binary]")
    import pgserver
    _pg = pgserver.get_server(os.path.join(_DOSSIER_TEMP, 'pg'))
    os.environ['DATABASE_URL'] = _pg.get_uri()
else:
    os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, RACINE)

MOT_DE_PASSE_ADMIN = 'Test-Admin-2026!'


@pytest.fixture(scope='session')
def app():
    from app import app as application
    application.config['TESTING'] = True
    return application


@pytest.fixture(scope='session')
def client(app):
    return app.test_client()


@pytest.fixture(scope='session')
def jeton_admin(client):
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': MOT_DE_PASSE_ADMIN})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['token']


@pytest.fixture
def entetes(jeton_admin):
    return {'Authorization': f'Bearer {jeton_admin}'}


@pytest.fixture
def creer_eleve(client, entetes):
    def _creer(nom='Diallo', prenom='Aïssatou', classe='CP'):
        r = client.post('/api/eleves', json={'nom': nom, 'prenom': prenom, 'classe': classe, 'sexe': 'F'},
                        headers=entetes)
        assert r.status_code == 201, r.get_json()
        return r.get_json()
    return _creer


@pytest.fixture
def creer_paiement(client, entetes):
    def _creer(eleve_id, montant_du=1500000, libelle='Scolarité 1er trimestre'):
        r = client.post('/api/paiements', json={
            'eleve_id': eleve_id, 'montant_du': montant_du, 'type_frais': 'scolarite', 'libelle': libelle,
        }, headers=entetes)
        assert r.status_code == 201, r.get_json()
        return r.get_json()
    return _creer
