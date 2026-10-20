"""
Couche de compatibilité PostgreSQL.

L'application a été écrite pour SQLite. Plutôt que de réécrire des centaines de requêtes, ce module
expose, au-dessus de psycopg, une connexion qui se comporte comme une connexion sqlite3 (execute,
fetchone, lastrowid, row['colonne'], row[0], PRAGMA…) et traduit à la volée le SQL propre à SQLite :

  ?                          -> %s
  INSERT OR IGNORE/REPLACE   -> INSERT … ON CONFLICT …
  strftime / date('now')     -> to_char(...)
  CURRENT_TIMESTAMP          -> ts_now()  (texte 'AAAA-MM-JJ HH:MM:SS' en UTC, comme SQLite)
  LIKE                       -> ILIKE     (SQLite ignore la casse pour LIKE)
  AUTOINCREMENT / REAL       -> SERIAL / DOUBLE PRECISION

Actif uniquement si la variable d'environnement DATABASE_URL est définie (voir database.py).
"""
import re

import psycopg
from psycopg.rows import RowMaker

# ───────────────────────── lignes ─────────────────────────


class Ligne:
    """Ligne de résultat : accessible par nom (row['x']), par position (row[0]) et convertible en dict."""
    __slots__ = ('_cols', '_vals')

    def __init__(self, cols, vals):
        self._cols, self._vals = cols, vals

    def __getitem__(self, k):
        if isinstance(k, str):
            try:
                return self._vals[self._cols.index(k)]
            except ValueError:
                raise IndexError(f"No item with that key: {k}") from None
        return self._vals[k]

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __eq__(self, other):
        return tuple(self._vals) == (tuple(other._vals) if isinstance(other, Ligne) else tuple(other))

    def __repr__(self):
        return f"Ligne({dict(zip(self._cols, self._vals))})"


def _fabrique_lignes(cursor):
    cols = [d.name for d in (cursor.description or [])]
    return lambda vals: Ligne(cols, list(vals))


# ───────────────────────── traduction SQL ─────────────────────────

_EXPR_NOW = "(now() at time zone 'utc')"
_FORMATS = (('%Y', 'YYYY'), ('%m', 'MM'), ('%d', 'DD'), ('%H', 'HH24'), ('%M', 'MI'), ('%S', 'SS'))


def _format_pg(fmt):
    """'%Y-%m-%d %H:%M' -> 'YYYY-MM-DD HH24:MI' ; lettres libres entre guillemets ('T', 'Z')."""
    sortie, i = '', 0
    while i < len(fmt):
        for src, dst in _FORMATS:
            if fmt.startswith(src, i):
                sortie += dst
                i += len(src)
                break
        else:
            c = fmt[i]
            sortie += f'"{c}"' if c.isalpha() else c
            i += 1
    return sortie


def _decouper_args(texte, debut):
    """texte[debut] == '(' -> (liste des arguments au niveau 1, index après la parenthèse fermante)."""
    niveau, args, courant, i, quote = 0, [], '', debut, None
    while i < len(texte):
        c = texte[i]
        if quote:
            courant += c
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
            courant += c
        elif c == '(':
            niveau += 1
            if niveau > 1:
                courant += c
        elif c == ')':
            niveau -= 1
            if niveau == 0:
                args.append(courant.strip())
                return args, i + 1
            courant += c
        elif c == ',' and niveau == 1:
            args.append(courant.strip())
            courant = ''
        else:
            courant += c
        i += 1
    raise ValueError("parenthèse non fermée")


def _modificateur(mod):
    """'-12 months' / '+1 day' / 'start of month' -> fragment SQL ou None."""
    m = re.fullmatch(r"([+-]?\d+)\s+(day|days|month|months|year|years|hour|hours)", mod.strip().strip("'"), re.I)
    if not m:
        return None
    n, unite = int(m.group(1)), m.group(2).lower().rstrip('s')
    return f" {'+' if n >= 0 else '-'} interval '{abs(n)} {unite}'"


def _reecrire_fonctions(sql):
    # Boucle manuelle : on remplace de gauche à droite
    sortie, pos = '', 0
    motif = re.compile(r"\b(strftime|date|datetime)\s*\(", re.I)
    while True:
        m = motif.search(sql, pos)
        if not m:
            sortie += sql[pos:]
            break
        nom = m.group(1).lower()
        try:
            args, fin = _decouper_args(sql, m.end() - 1)
        except ValueError:
            sortie += sql[pos:]
            break
        args = [_reecrire_fonctions(a) for a in args]

        def valeur(a):
            if a.strip("'").lower() == 'now':
                return _EXPR_NOW
            return f"({a})::timestamp"
        remplacement = None
        if nom == 'strftime' and args and args[0].startswith("'"):
            fmt = _format_pg(args[0].strip("'"))
            cible = valeur(args[1]) if len(args) > 1 else _EXPR_NOW
            for mod in args[2:]:
                frag = _modificateur(mod)
                cible = f"({cible}{frag})" if frag else cible
            remplacement = f"to_char({cible}, '{fmt}')"
        elif nom in ('date', 'datetime') and args:
            if args[0].strip("'").lower() == 'now':
                cible = _EXPR_NOW
                for mod in args[1:]:
                    frag = _modificateur(mod)
                    cible = f"({cible}{frag})" if frag else cible
            else:
                cible = f"({args[0]})::timestamp"
            remplacement = f"to_char({cible}, '{'YYYY-MM-DD' if nom == 'date' else 'YYYY-MM-DD HH24:MI:SS'}')"
        if remplacement is None:
            sortie += sql[pos:fin]
        else:
            sortie += sql[pos:m.start()] + remplacement
        pos = fin
    return sortie


def traduire_schema(sql):
    # En SQLite, « INTEGER PRIMARY KEY » (avec ou sans AUTOINCREMENT) se numérote tout seul.
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY(\s+AUTOINCREMENT)?", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)
    sql = re.sub(r"\bPRAGMA\b[^;\n]*;?", "", sql)
    return traduire(sql, schema=True)


def _placeholders(sql):
    """? -> %s hors guillemets ; % littéral -> %% (psycopg)."""
    sortie, quote = [], None
    for c in sql:
        if quote:
            sortie.append('%%' if c == '%' else c)
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
            sortie.append(c)
        elif c == '?':
            sortie.append('%s')
        elif c == '%':
            sortie.append('%%')
        else:
            sortie.append(c)
    return ''.join(sortie)


CONFLITS = {}          # table -> liste d'ensembles de colonnes uniques (rempli par ConnexionPg)
TABLES_SERIAL = set()  # tables dont la clé 'id' est auto-incrémentée


def traduire(sql, schema=False, conflits=None):
    s = sql.strip().rstrip(';') if not schema else sql
    s = re.sub(r"\bCURRENT_TIMESTAMP\b", "ts_now()", s, flags=re.I)
    s = _reecrire_fonctions(s)
    s = re.sub(r"\bLIKE\b", "ILIKE", s, flags=re.I)
    s = re.sub(r"\bNOT\s+ILIKE\b", "NOT ILIKE", s, flags=re.I)
    m = re.match(r"\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+(\w+)\s*(\(([^)]*)\))?", s, re.I)
    if m and not schema:
        mode, table, cols = m.group(1).upper(), m.group(2), m.group(4)
        s = re.sub(r"INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO", "INSERT INTO", s, count=1, flags=re.I)
        if mode == 'IGNORE':
            s += " ON CONFLICT DO NOTHING"
        else:
            colonnes = [c.strip() for c in (cols or '').split(',') if c.strip()]
            cible = None
            for u in (conflits or {}).get(table, []):
                if set(u) <= set(colonnes):
                    cible = u
                    break
            if cible is None:
                s += " ON CONFLICT DO NOTHING"
            else:
                maj = [c for c in colonnes if c not in cible]
                s += (f" ON CONFLICT ({', '.join(cible)}) DO " +
                      (f"UPDATE SET {', '.join(f'{c}=EXCLUDED.{c}' for c in maj)}" if maj else "NOTHING"))
    elif schema:
        s = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, flags=re.I)
    return s if schema else _placeholders(s)


# ───────────────────────── connexion ─────────────────────────

FONCTIONS_PG = """
CREATE OR REPLACE FUNCTION ts_now() RETURNS text AS
$$ SELECT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS') $$ LANGUAGE SQL STABLE;
CREATE OR REPLACE FUNCTION round(double precision, integer) RETURNS double precision AS
$$ SELECT round($1::numeric, $2)::double precision $$ LANGUAGE SQL IMMUTABLE;
CREATE TABLE IF NOT EXISTS _meta (cle TEXT PRIMARY KEY, valeur TEXT);
"""


class Curseur:
    def __init__(self, cur, lastrowid=None, lignes=None):
        self._cur, self.lastrowid, self._lignes = cur, lastrowid, lignes

    @property
    def rowcount(self):
        return self._cur.rowcount if self._cur is not None else 0

    def fetchone(self):
        if self._lignes is not None:
            return self._lignes.pop(0) if self._lignes else None
        try:
            return self._cur.fetchone()
        except psycopg.ProgrammingError:
            return None

    def fetchall(self):
        if self._lignes is not None:
            out, self._lignes = self._lignes, []
            return out
        try:
            return self._cur.fetchall()
        except psycopg.ProgrammingError:
            return []

    def __iter__(self):
        return iter(self.fetchall())


class ConnexionPg:
    def __init__(self, url):
        self._conn = psycopg.connect(url, row_factory=_fabrique_lignes, options='-c timezone=UTC')
        from psycopg.types.numeric import FloatLoader
        self._conn.adapters.register_loader('numeric', FloatLoader)
        self._savepoint = 0

    # --- état -----
    @property
    def in_transaction(self):
        return self._conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE

    @property
    def closed(self):
        return self._conn.closed or self._conn.broken

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    # --- catalogue -----
    def _charger_catalogue(self):
        if CONFLITS:
            return
        cur = self._conn.execute("""
            SELECT t.relname AS table_, array_agg(a.attname ORDER BY k.ord) AS cols
            FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace AND n.nspname='public'
            JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
            WHERE i.indisunique AND i.indpred IS NULL GROUP BY t.relname, i.indexrelid""")
        for r in cur.fetchall():
            CONFLITS.setdefault(r['table_'], []).append(list(r['cols']))
        for r in self._conn.execute("""SELECT table_name FROM information_schema.columns
                 WHERE table_schema='public' AND column_name='id' AND column_default LIKE 'nextval%%'""").fetchall():
            TABLES_SERIAL.add(r['table_name'])
        # Clé primaire composite/réelle d'abord
        for t in CONFLITS:
            CONFLITS[t].sort(key=len)

    def _vider_catalogue(self):
        CONFLITS.clear()
        TABLES_SERIAL.clear()

    # --- PRAGMA -----
    def _pragma(self, sql):
        m = re.match(r"\s*PRAGMA\s+(\w+)\s*(?:\(\s*(\w+)\s*\)|=\s*(\S+))?", sql, re.I)
        nom, arg, val = m.group(1).lower(), m.group(2), m.group(3)
        if nom == 'user_version':
            if val is not None:
                self._conn.execute("INSERT INTO _meta (cle, valeur) VALUES ('user_version', %s) "
                                   "ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur", (str(int(val)),))
                return Curseur(None, lignes=[])
            r = self._conn.execute("SELECT valeur FROM _meta WHERE cle='user_version'").fetchone()
            return Curseur(None, lignes=[Ligne(['user_version'], [int(r['valeur']) if r else 0])])
        if nom == 'table_info':
            cur = self._conn.execute("""
                SELECT c.ordinal_position-1 AS cid, c.column_name AS name, c.data_type AS type,
                       (c.is_nullable='NO')::int AS notnull, c.column_default AS dflt_value,
                       COALESCE((SELECT 1 FROM information_schema.table_constraints tc
                         JOIN information_schema.key_column_usage kcu USING (constraint_name, table_schema, table_name)
                         WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema='public'
                           AND tc.table_name=c.table_name AND kcu.column_name=c.column_name), 0) AS pk
                FROM information_schema.columns c WHERE c.table_schema='public' AND c.table_name=%s
                ORDER BY c.ordinal_position""", (arg,))
            return Curseur(None, lignes=cur.fetchall())
        return Curseur(None, lignes=[])     # foreign_keys, journal_mode, busy_timeout, optimize… : sans objet ici

    # --- exécution -----
    def execute(self, sql, params=()):
        if re.match(r"\s*PRAGMA\b", sql, re.I):
            return self._pragma(sql)
        self._charger_catalogue()
        t = traduire(sql, conflits=CONFLITS)
        params = tuple(int(p) if isinstance(p, bool) else p for p in (params or ()))
        lastid = None
        m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", t, re.I)
        veut_id = bool(m and m.group(1) in TABLES_SERIAL and 'RETURNING' not in t.upper())
        if veut_id:
            t += " RETURNING id"
        ecriture = not re.match(r"\s*(SELECT|WITH)\b", t, re.I)
        sp = None
        if ecriture and self.in_transaction:
            # PostgreSQL abandonne toute la transaction à la première erreur ; SQLite non. Un point de
            # sauvegarde par écriture rend l'erreur « rattrapable » (try/except) comme avant.
            self._savepoint += 1
            sp = f"sp{self._savepoint}"
            self._conn.execute(f"SAVEPOINT {sp}")
        try:
            cur = self._conn.execute(t, params)
        except Exception:
            if sp:
                self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            raise
        if sp:
            self._conn.execute(f"RELEASE SAVEPOINT {sp}")
        if veut_id:
            r = cur.fetchone()
            lastid = r[0] if r else None
            if re.match(r"\s*INSERT\s+INTO\s+\w+\s*\(\s*id\b", t, re.I):
                # id fourni explicitement : on resynchronise le compteur pour que le suivant ne le percute pas
                self.resynchroniser_sequence(m.group(1))
        return Curseur(cur, lastrowid=lastid)

    def resynchroniser_sequence(self, table):
        self._conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
                           f"GREATEST((SELECT COALESCE(MAX(id),0) FROM {table}), 1))")

    def executemany(self, sql, seq):
        for p in seq:
            self.execute(sql, p)

    def executescript(self, script):
        self._conn.execute(FONCTIONS_PG)
        instructions = [i.strip() for i in _separer_instructions(traduire_schema(script)) if i.strip()]
        # SQLite accepte les références vers des tables définies plus bas ; PostgreSQL non. On rejoue donc
        # les instructions refusées pour « table inexistante » jusqu'à ce que tout soit créé.
        while instructions:
            restantes, erreur = [], None
            for ins in instructions:
                self._conn.execute("SAVEPOINT schema_ins")
                try:
                    self._conn.execute(ins)
                    self._conn.execute("RELEASE SAVEPOINT schema_ins")
                except psycopg.errors.UndefinedTable as e:
                    self._conn.execute("ROLLBACK TO SAVEPOINT schema_ins")
                    restantes.append(ins)
                    erreur = e
            if len(restantes) == len(instructions):
                raise erreur
            instructions = restantes
        self._vider_catalogue()
        self._conn.commit()


def _separer_instructions(sql):
    """Découpe sur les ';' hors guillemets et hors commentaires -- ."""
    morceaux, courant, quote, i = [], [], None, 0
    while i < len(sql):
        c = sql[i]
        if quote:
            courant.append(c)
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
            courant.append(c)
        elif sql.startswith('--', i):
            j = sql.find('\n', i)
            i = len(sql) if j < 0 else j
            continue
        elif c == ';':
            morceaux.append(''.join(courant))
            courant = []
        else:
            courant.append(c)
        i += 1
    morceaux.append(''.join(courant))
    return morceaux
