"""Spécifique à PostgreSQL (lancer avec TEST_PG=1) : traduction SQL et aller-retour SQLite <-> PostgreSQL."""
import os
import sqlite3

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_PG'), reason="nécessite PostgreSQL (TEST_PG=1)")


def test_traduction_sql():
    import pg_compat as p
    t = p.traduire("SELECT strftime('%Y-%m', date_op) m, date('now','-12 months') d FROM t WHERE a LIKE ? AND b=?")
    assert "to_char((date_op)::timestamp, 'YYYY-MM')" in t and "interval '12 month'" in t
    assert "ILIKE %s" in t and "b=%s" in t and '?' not in t
    assert p.traduire("INSERT OR IGNORE INTO settings (cle, valeur) VALUES (?, ?)").endswith("ON CONFLICT DO NOTHING")
    assert "ts_now()" in p.traduire("UPDATE x SET d=CURRENT_TIMESTAMP")
    assert "LIKE 'a%%'" in p.traduire("SELECT * FROM x WHERE n LIKE 'a%'").replace('ILIKE', 'LIKE')
    assert p.traduire_schema("id INTEGER PRIMARY KEY AUTOINCREMENT, p REAL").startswith("id SERIAL PRIMARY KEY, p DOUBLE")


def test_ligne_acces_par_nom_position_et_dict(client):
    from database import db
    r = db.execute("SELECT 1 AS a, 'x' AS b").fetchone()
    assert r['a'] == 1 and r[1] == 'x' and dict(r) == {'a': 1, 'b': 'x'}


def test_erreur_rattrapable_comme_en_sqlite(client):
    from database import db
    db.execute("INSERT INTO settings (cle, valeur) VALUES ('t_unique', '1') ON CONFLICT DO NOTHING")
    with pytest.raises(Exception):
        db.execute("INSERT INTO ecoles (id, nom, code) VALUES (1, 'x', 'ecole-1')")
    assert db.execute("SELECT 1 AS n").fetchone()['n'] == 1       # la transaction reste utilisable
    db.rollback()


def test_aller_retour_sqlite_postgres(tmp_path, client, entetes, creer_eleve):
    import pg_migration
    from database import db
    creer_eleve(nom='Roundtrip', prenom='Test')
    db.commit()
    fichier = str(tmp_path / 'copie.db')
    pg_migration.exporter_vers_sqlite(fichier)
    s = sqlite3.connect(fichier)
    assert s.execute("SELECT COUNT(*) FROM eleves WHERE nom='Roundtrip'").fetchone()[0] == 1
    s.close()
    avant = db.execute("SELECT COUNT(*) AS n FROM eleves").fetchone()['n']
    bilan = pg_migration.importer_depuis_sqlite(fichier, vider=True)
    assert bilan['ecarts'] == {}
    assert db.execute("SELECT COUNT(*) AS n FROM eleves").fetchone()['n'] == avant
    # la base reste utilisable après l'import (compteurs d'auto-incrément resynchronisés)
    assert client.post('/api/users', json={'username': 'apresimport', 'password': 'Provisoire-1', 'full_name': 'A', 'role': 'secretaire'},
                       headers=entetes).status_code in (201, 401)
