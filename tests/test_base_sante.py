"""Santé de la base : migration d'index, diagnostic, accès réservé au super-administrateur."""
import base_sante
from database import db, DB_PATH


def test_plus_aucun_index_manquant_apres_migration():
    assert base_sante.index_manquants(db) == []


def test_indexer_est_idempotent_et_rattrape_un_index_supprime():
    db.execute("DROP INDEX idx_auto_versements_eleve_id"); db.commit()
    assert ('versements', 'eleve_id') in base_sante.index_manquants(db)
    assert "versements.eleve_id" in base_sante.indexer_cles_etrangeres(db)
    assert base_sante.indexer_cles_etrangeres(db) == []


def test_diagnostic_sain():
    d = base_sante.diagnostic(db, DB_PATH)
    assert d['integrite_ok'] and d['nb_orphelins'] == 0 and d['index_manquants'] == []
    assert d['mode_journal'] == 'wal' and d['version_schema'] >= 4 and d['total_lignes'] > 0


def test_endpoint_reserve_au_super_admin(client, entetes):
    r = client.get('/api/systeme/base', headers=entetes)
    assert r.status_code == 200 and r.get_json()['integrite_ok'] is True
    assert client.post('/api/systeme/base/optimiser', headers=entetes).status_code == 200
    tok = client.post('/api/users', json={'username': 'simple', 'password': 'Provisoire-1', 'full_name': 'S', 'role': 'secretaire'}, headers=entetes)
    t = client.post('/api/auth/login', json={'username': 'simple', 'password': 'Provisoire-1'}).get_json()['token']
    assert client.get('/api/systeme/base', headers={'Authorization': f'Bearer {t}'}).status_code in (401, 403)
