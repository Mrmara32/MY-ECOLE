"""
Passage SQLite <-> PostgreSQL.

  importer_depuis_sqlite(chemin)   copie TOUTES les données d'une base SQLite (ex : /var/data/ecole.db)
                                   vers la base PostgreSQL configurée (DATABASE_URL) ;
  exporter_vers_sqlite(chemin)     fait l'inverse (sert aux sauvegardes et à un éventuel retour arrière).

Les valeurs sont converties selon le type de la colonne de destination (SQLite est très tolérant sur
les types, PostgreSQL non). Les tables sont copiées dans un ordre qui respecte les clés étrangères.
"""
import os
import sqlite3

import psycopg

import database


def _tables_sqlite(src):
    return [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]


def _convertir(v, type_pg):
    if v is None:
        return None
    if type_pg in ('integer', 'bigint', 'smallint'):
        if isinstance(v, str):
            v = v.strip()
            return int(float(v)) if v else None
        return int(v)
    if type_pg in ('double precision', 'numeric', 'real'):
        if isinstance(v, str):
            v = v.strip()
            return float(v) if v else None
        return float(v)
    if type_pg == 'text':
        if isinstance(v, bytes):
            return v.decode('utf-8', 'replace')
        return str(v)
    if type_pg == 'bytea':
        return bytes(v) if not isinstance(v, str) else v.encode()
    return v


def importer_depuis_sqlite(chemin, vider=False, journal=print, initialiser=True):
    if not database.USE_PG:
        raise RuntimeError("DATABASE_URL (PostgreSQL) n'est pas défini")
    src = sqlite3.connect(chemin)
    src.row_factory = sqlite3.Row
    if initialiser:
        database.init_db()                  # crée le schéma à jour dans PostgreSQL
    dst = database.connexion_courante()._conn
    tables_src = _tables_sqlite(src)
    types = {}
    for r in dst.execute("""SELECT table_name, column_name, data_type FROM information_schema.columns
                            WHERE table_schema='public'""").fetchall():
        types.setdefault(r['table_name'], {})[r['column_name']] = r['data_type']
    tables = [t for t in tables_src if t in types]
    ignorees = [t for t in tables_src if t not in types]
    if ignorees:
        journal(f"Tables absentes du schéma PostgreSQL (ignorées) : {', '.join(ignorees)}")

    deja = {t: dst.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()['n'] for t in tables}
    if vider:
        dst.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
        dst.commit()
    else:
        # Seules les tables d'amorçage (école n°1, paramètres, classes par défaut…) peuvent déjà contenir des lignes
        pass

    lignes = {}
    for t in tables:
        cols = [c[1] for c in src.execute(f"PRAGMA table_info({t})").fetchall() if c[1] in types[t]]
        lignes[t] = (cols, [tuple(_convertir(row[c], types[t][c]) for c in cols)
                            for row in src.execute(f"SELECT {', '.join(cols)} FROM {t}").fetchall()])
    # Copie avec rejeu : une ligne dont le parent n'est pas encore copié est retentée au tour suivant.
    restant = {t: list(v[1]) for t, v in lignes.items()}
    tour = 0
    while any(restant.values()):
        tour += 1
        progres = 0
        for t in tables:
            if not restant[t]:
                continue
            cols = lignes[t][0]
            sql = (f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                   f"ON CONFLICT DO NOTHING")
            suite = []
            for ligne in restant[t]:
                dst.execute("SAVEPOINT l")
                try:
                    dst.execute(sql, ligne)
                    dst.execute("RELEASE SAVEPOINT l")
                    progres += 1
                except psycopg.errors.ForeignKeyViolation:
                    dst.execute("ROLLBACK TO SAVEPOINT l")
                    suite.append(ligne)
            restant[t] = suite
        dst.commit()
        if not progres:
            reste = {t: len(v) for t, v in restant.items() if v}
            raise RuntimeError(f"Lignes impossibles à copier (clé étrangère orpheline dans la source) : {reste}")
        if tour > 50:
            raise RuntimeError("Trop de tours de copie")
    # Compteurs d'auto-incrément
    for r in dst.execute("""SELECT table_name FROM information_schema.columns WHERE table_schema='public'
                            AND column_name='id' AND column_default LIKE 'nextval%%'""").fetchall():
        t = r['table_name']
        dst.execute(f"SELECT setval(pg_get_serial_sequence('{t}','id'), GREATEST((SELECT COALESCE(MAX(id),0) FROM {t}),1))")
    dst.commit()
    # Vérification : mêmes effectifs
    ecarts = {}
    for t in tables:
        n_src = src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        n_dst = dst.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()['n']
        if n_src != n_dst:
            ecarts[t] = (n_src, n_dst)
    src.close()
    return {'tables': len(tables), 'lignes': sum(len(v[1]) for v in lignes.values()), 'ecarts': ecarts}


def exporter_vers_sqlite(destination):
    """Copie cohérente (une seule transaction) de la base PostgreSQL dans un fichier SQLite."""
    dst = sqlite3.connect(destination)
    try:
        dst.executescript(database.SCHEMA)
        src = database.connexion_courante()._conn
        src.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY") if not src.info.transaction_status else None
        cols_sqlite = {}
        for (t,) in dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            cols_sqlite[t] = [c[1] for c in dst.execute(f"PRAGMA table_info({t})").fetchall()]
        dst.execute("PRAGMA foreign_keys = OFF")
        for t, cols in cols_sqlite.items():
            existantes = {r['column_name'] for r in src.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (t,)).fetchall()}
            cc = [c for c in cols if c in existantes]
            if not cc:
                continue
            for lot in iter(lambda cur=src.execute(f"SELECT {', '.join(cc)} FROM {t}"): cur.fetchmany(1000), []):
                dst.executemany(f"INSERT OR IGNORE INTO {t} ({', '.join(cc)}) VALUES ({', '.join('?' * len(cc))})",
                                [tuple(r) for r in lot])
        dst.commit()
        src.rollback()
    finally:
        dst.close()


def migrer_au_demarrage():
    """Une seule fois : si MIGRER_DEPUIS_SQLITE désigne un fichier SQLite (ex : /var/data/ecole.db), ses
    données sont copiées dans PostgreSQL. Le fichier SQLite n'est jamais modifié : retirer DATABASE_URL
    suffit pour revenir en arrière. Un repère dans la table _meta empêche toute seconde copie."""
    chemin = os.environ.get('MIGRER_DEPUIS_SQLITE', '').strip()
    if not (database.USE_PG and chemin and os.path.exists(chemin)):
        return None
    db = database.connexion_courante()
    db.execute("SELECT pg_advisory_lock(7003)")
    try:
        db.commit()
        if db.execute("SELECT 1 FROM _meta WHERE cle='migration_sqlite'").fetchone():
            return None
        print(f"[postgres] Copie des données de {chemin} vers PostgreSQL…", flush=True)
        bilan = importer_depuis_sqlite(chemin, vider=True, initialiser=False)
        if bilan['ecarts']:
            raise RuntimeError(f"Copie incomplète, écarts : {bilan['ecarts']}")
        db.execute("INSERT INTO _meta (cle, valeur) VALUES ('migration_sqlite', ?)", (chemin,))
        db.commit()
        print(f"[postgres] Copie terminée : {bilan['lignes']} lignes, {bilan['tables']} tables.", flush=True)
        return bilan
    finally:
        db.execute("SELECT pg_advisory_unlock(7003)")
        db.commit()


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        sys.exit("Usage : DATABASE_URL=postgresql://… python pg_migration.py /chemin/ecole.db [--vider]")
    bilan = importer_depuis_sqlite(sys.argv[1], vider='--vider' in sys.argv)
    print(f"Copié : {bilan['lignes']} lignes dans {bilan['tables']} tables")
    if bilan['ecarts']:
        sys.exit(f"ÉCARTS (source, destination) : {bilan['ecarts']}")
    print("Vérification des effectifs : OK")
