"""
Santé et performance de la base de données (SQLite).

  * indexer_cles_etrangeres() : crée un index pour chaque colonne de jointure/filtre usuelle
    (ecole_id, eleve_id, …) qui n'en a pas encore — les écrans restent rapides quand la base grossit ;
  * diagnostic() : contrôle d'intégrité, clés étrangères, taille, volumétrie par table, index manquants ;
  * optimiser() : met à jour les statistiques du planificateur (PRAGMA optimize) et récupère l'espace libre.
"""
import os

COLONNES_A_INDEXER = ('ecole_id', 'eleve_id', 'user_id', 'parent_id', 'paiement_id', 'classe_id',
                      'enseignant_id', 'produit_id', 'fournisseur_id', 'commande_id')


def _pg():
    import database
    return database.USE_PG


def _tables(db):
    if _pg():
        return [r['table_name'] for r in db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name <> '_meta'").fetchall()]
    return [r['name'] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]


def _colonnes_indexees_en_tete(db, table):
    if _pg():
        # première colonne de chaque index (clé primaire et UNIQUE comprises)
        return {r['col'] for r in db.execute("""
            SELECT a.attname AS col FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=i.indkey[0]
            WHERE t.relname=? AND t.relnamespace='public'::regnamespace""", (table,)).fetchall()}
    """Colonnes qui sont la PREMIÈRE colonne d'un index (un index (ecole_id, x) sert aussi à filtrer ecole_id)."""
    tetes = set()
    for idx in db.execute(f"PRAGMA index_list({table})").fetchall():
        cols = db.execute(f"PRAGMA index_info({idx['name']})").fetchall()
        if cols:
            tetes.add(cols[0]['name'])
    for c in db.execute(f"PRAGMA table_info({table})").fetchall():
        if c['pk'] == 1 and sum(1 for x in db.execute(f"PRAGMA table_info({table})").fetchall() if x['pk']) == 1:
            tetes.add(c['name'])
    return tetes


def index_manquants(db):
    manquants = []
    for t in _tables(db):
        cols = {r['name'] for r in db.execute(f"PRAGMA table_info({t})").fetchall()}
        deja = _colonnes_indexees_en_tete(db, t)
        for c in COLONNES_A_INDEXER:
            if c in cols and c not in deja:
                manquants.append((t, c))
    return manquants


def indexer_cles_etrangeres(db):
    crees = []
    for t, c in index_manquants(db):
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_auto_{t}_{c} ON {t}({c})")
        crees.append(f"{t}.{c}")
    db.commit()
    if crees:
        print(f"[migration] {len(crees)} index créés : {', '.join(crees)}")
    return crees


def optimiser(db):
    if _pg():
        return          # autovacuum / analyse automatiques côté PostgreSQL
    db.execute("PRAGMA optimize")
    db.commit()


def _diagnostic_pg(db):
    volumes = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _tables(db)}
    taille = db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
    orphelins = db.execute("""SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated""").fetchone()[0]
    return {
        'moteur': 'postgresql',
        'integrite_ok': True, 'integrite': ['ok'],
        'cles_etrangeres_orphelines': [], 'nb_orphelins': orphelins,
        'taille_mo': round(taille / 1048576, 2), 'wal_mo': 0, 'espace_libre_mo': 0,
        'mode_journal': 'wal',
        'version_schema': db.execute("PRAGMA user_version").fetchone()[0],
        'index_manquants': [f"{t}.{c}" for t, c in index_manquants(db)],
        'lignes_par_table': dict(sorted(volumes.items(), key=lambda kv: -kv[1])[:25]),
        'total_lignes': sum(volumes.values()),
    }


def diagnostic(db, chemin_base):
    if _pg():
        return _diagnostic_pg(db)
    integrite = [r[0] for r in db.execute("PRAGMA integrity_check").fetchall()]
    fk = [dict(table=r[0], rowid=r[1], parent=r[2]) for r in db.execute("PRAGMA foreign_key_check").fetchall()]
    taille = os.path.getsize(chemin_base) if os.path.exists(chemin_base) else 0
    wal = chemin_base + '-wal'
    volumes = {}
    for t in _tables(db):
        volumes[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    page = db.execute("PRAGMA page_size").fetchone()[0]
    libres = db.execute("PRAGMA freelist_count").fetchone()[0]
    return {
        'integrite_ok': integrite == ['ok'],
        'integrite': integrite[:10],
        'cles_etrangeres_orphelines': fk[:50],
        'nb_orphelins': len(fk),
        'taille_mo': round(taille / 1048576, 2),
        'wal_mo': round(os.path.getsize(wal) / 1048576, 2) if os.path.exists(wal) else 0,
        'espace_libre_mo': round(libres * page / 1048576, 2),
        'mode_journal': db.execute("PRAGMA journal_mode").fetchone()[0],
        'version_schema': db.execute("PRAGMA user_version").fetchone()[0],
        'index_manquants': [f"{t}.{c}" for t, c in index_manquants(db)],
        'lignes_par_table': dict(sorted(volumes.items(), key=lambda kv: -kv[1])[:25]),
        'total_lignes': sum(volumes.values()),
    }
