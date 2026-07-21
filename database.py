"""
Base de données SQLite — module natif Python (sqlite3), aucune compilation requise.
C'est la principale raison du passage de Node.js à Python : better-sqlite3 (Node)
doit être recompilé pour chaque version de Node.js, ce qui causait des erreurs
d'installation. Le module sqlite3 de Python est intégré au langage lui-même.
"""
import sqlite3
import threading

# Verrou dédié à la génération de matricule (élèves ET personnel) : sous
# gunicorn/production avec plusieurs threads, deux créations quasi simultanées
# pouvaient auparavant calculer le même "prochain" matricule avant que l'une
# des deux n'ait validé son insertion. Ce verrou sérialise strictement la
# séquence "calculer le prochain matricule → l'utiliser", ce qui élimine la
# collision à la source plutôt que de compter sur de simples nouvelles tentatives.
matricule_lock = threading.Lock()
import os
import sys
import time
import random
import string
from werkzeug.security import generate_password_hash

# GS_DATA_DIR peut être défini par le launcher desktop (dossier utilisateur).
# Sinon : à côté du véritable exécutable si l'application est empaquetée avec
# PyInstaller (sys.frozen), sinon dossier "data" local à côté de ce fichier (mode web/CLI).
if os.environ.get('GS_DATA_DIR'):
    DATA_DIR = os.environ['GS_DATA_DIR']
elif getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), 'data')
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'ecole.db')

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode = WAL")
db.execute("PRAGMA foreign_keys = ON")


def gen_id(prefix='id'):
    """Génère un identifiant unique lisible, équivalent du genId() côté Node."""
    ts = format(int(time.time() * 1000), 'x')
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{ts}{rnd}"


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  cle   TEXT PRIMARY KEY,
  valeur TEXT
);

-- Compteurs internes (ex: dernier numéro de matricule utilisé), séparés des
-- paramètres exposés à l'utilisateur (table settings) pour éviter tout risque
-- de modification accidentelle depuis l'écran Paramètres. L'incrémentation
-- atomique de cette table (combinée au verrou applicatif matricule_lock) évite
-- toute collision, y compris sous forte charge concurrente, contrairement à un
-- calcul basé sur "le dernier matricule créé" (peu fiable : la résolution des
-- horodatages SQLite est à la seconde près, insuffisante en cas de créations
-- multiples la même seconde).
CREATE TABLE IF NOT EXISTS sequences (
  nom    TEXT PRIMARY KEY,
  valeur INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  username     TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name    TEXT NOT NULL,
  role         TEXT NOT NULL CHECK(role IN ('admin','directeur','comptable','enseignant','secretaire','charge_communication')),
  email        TEXT,
  telephone    TEXT,
  active       INTEGER DEFAULT 1,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  last_login   TEXT
);

CREATE TABLE IF NOT EXISTS classes (
  id         TEXT PRIMARY KEY,
  nom        TEXT UNIQUE NOT NULL,
  cycle      TEXT NOT NULL CHECK(cycle IN ('maternelle','primaire','college','lycee')),
  ordre      INTEGER DEFAULT 0,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS personnel (
  id            TEXT PRIMARY KEY,
  nom           TEXT NOT NULL,
  prenom        TEXT NOT NULL,
  poste         TEXT,
  matiere       TEXT,
  telephone     TEXT,
  email         TEXT,
  date_embauche TEXT,
  salaire       REAL DEFAULT 0,
  cycle_enseignement TEXT,
  type_remuneration  TEXT DEFAULT 'mensuel' CHECK(type_remuneration IN ('mensuel','horaire')),
  taux_horaire       REAL DEFAULT 0,
  user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS heures_enseignement (
  id           TEXT PRIMARY KEY,
  personnel_id TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  mois         TEXT NOT NULL,
  nombre_heures REAL NOT NULL DEFAULT 0,
  valide       INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(personnel_id, mois)
);

-- Séances de cours individuelles (ex: "08h30-09h30, M. Sylla, 12ème Année, salle 2").
-- Permet à la direction de savoir précisément QUAND un enseignant a donné cours,
-- de valider chaque séance, et d'en déduire automatiquement le nombre d'heures
-- comptabilisées en paie pour le personnel rémunéré à l'heure (collège/lycée).
CREATE TABLE IF NOT EXISTS seances_cours (
  id              TEXT PRIMARY KEY,
  personnel_id    TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  date_seance     TEXT NOT NULL,
  jour            TEXT,
  creneau         TEXT,
  classe          TEXT,
  salle           TEXT,
  matiere         TEXT,
  duree_heures    REAL NOT NULL DEFAULT 1,
  statut          TEXT DEFAULT 'en_attente' CHECK(statut IN ('en_attente','validee','rejetee')),
  motif_rejet     TEXT,
  cree_par        INTEGER REFERENCES users(id),
  valide_par      INTEGER REFERENCES users(id),
  date_validation TEXT,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eleves (
  id                TEXT PRIMARY KEY,
  matricule         TEXT UNIQUE,
  nom               TEXT NOT NULL,
  prenom            TEXT NOT NULL,
  date_naissance    TEXT,
  lieu_naissance    TEXT,
  sexe              TEXT CHECK(sexe IN ('M','F')),
  nationalite       TEXT DEFAULT 'Guinéenne',
  classe            TEXT,
  annee_scolaire    TEXT,
  statut            TEXT DEFAULT 'actif' CHECK(statut IN ('actif','inactif','reinsrit','exclu','transfere','preinscrit')),
  photo_url         TEXT,
  pere_nom          TEXT,
  pere_prenom       TEXT,
  pere_profession   TEXT,
  pere_telephone    TEXT,
  pere_email        TEXT,
  mere_nom          TEXT,
  mere_prenom       TEXT,
  mere_profession   TEXT,
  mere_telephone    TEXT,
  mere_email        TEXT,
  tuteur_nom        TEXT,
  tuteur_prenom     TEXT,
  tuteur_relation   TEXT,
  tuteur_telephone  TEXT,
  tuteur_email      TEXT,
  adresse           TEXT,
  contact_urgence_nom       TEXT,
  contact_urgence_telephone TEXT,
  groupe_sanguin    TEXT,
  allergies         TEXT,
  maladies_chroniques TEXT,
  medicaments       TEXT,
  handicap          TEXT,
  medecin_nom       TEXT,
  medecin_telephone TEXT,
  assurance_nom     TEXT,
  assurance_numero  TEXT,
  vaccins           TEXT,
  created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
  id         TEXT PRIMARY KEY,
  eleve_id   TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  matiere    TEXT NOT NULL,
  trimestre  INTEGER NOT NULL,
  type       TEXT,
  note       REAL,
  note_max   REAL DEFAULT 20,
  date_note  TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS devoirs (
  id              TEXT PRIMARY KEY,
  titre           TEXT NOT NULL,
  matiere         TEXT,
  classe          TEXT,
  professeur_id   TEXT,
  date_assignation TEXT,
  date_remise     TEXT,
  description     TEXT,
  statut          TEXT DEFAULT 'En cours',
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS emploi_du_temps (
  id           TEXT PRIMARY KEY,
  jour         TEXT NOT NULL,
  creneau      TEXT NOT NULL,
  classe       TEXT NOT NULL,
  matiere      TEXT,
  professeur_id TEXT,
  salle        TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(jour, creneau, classe)
);

CREATE TABLE IF NOT EXISTS absences (
  id         TEXT PRIMARY KEY,
  eleve_id   TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  date_abs   TEXT NOT NULL,
  type       TEXT DEFAULT 'absence' CHECK(type IN ('absence','retard')),
  justifie   INTEGER DEFAULT 0,
  motif      TEXT,
  duree      TEXT DEFAULT 'journée',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS absences_personnel (
  id           TEXT PRIMARY KEY,
  personnel_id TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  date_debut   TEXT NOT NULL,
  date_fin     TEXT,
  motif        TEXT,
  remplace_par TEXT,
  signale_par  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
  id             TEXT PRIMARY KEY,
  type           TEXT NOT NULL CHECK(type IN ('entree','sortie')),
  date_op        TEXT NOT NULL,
  description    TEXT,
  categorie      TEXT,
  moyen_paiement TEXT,
  montant        REAL NOT NULL,
  reference      TEXT,
  eleve_id       TEXT REFERENCES eleves(id) ON DELETE SET NULL,
  cree_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  statut_validation TEXT NOT NULL DEFAULT 'auto' CHECK(statut_validation IN ('auto','attente_directeur','attente_admin','valide','rejete')),
  valide_par     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_validation TEXT,
  motif_rejet    TEXT,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journal_audit (
  id          TEXT PRIMARY KEY,
  user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  user_nom    TEXT,
  action      TEXT NOT NULL,
  entite      TEXT NOT NULL,
  entite_id   TEXT,
  details     TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
  id               TEXT PRIMARY KEY,
  titre            TEXT NOT NULL,
  contenu          TEXT,
  type             TEXT DEFAULT 'article' CHECK(type IN ('article','evenement')),
  auteur_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_publication TEXT DEFAULT CURRENT_TIMESTAMP,
  publie           INTEGER DEFAULT 1,
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles_media (
  id         TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  type       TEXT NOT NULL CHECK(type IN ('photo','video')),
  url        TEXT NOT NULL,
  legende    TEXT,
  ordre      INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eleve_du_mois (
  id         TEXT PRIMARY KEY,
  eleve_id   TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  mois       TEXT NOT NULL UNIQUE,
  motif      TEXT,
  designe_par INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS salles (
  id         TEXT PRIMARY KEY,
  nom        TEXT UNIQUE NOT NULL,
  capacite   INTEGER,
  batiment   TEXT,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cours_revision (
  id            TEXT PRIMARY KEY,
  titre         TEXT NOT NULL,
  matiere       TEXT,
  niveau        TEXT,
  description   TEXT,
  date_debut    TEXT,
  date_fin      TEXT,
  prix          REAL DEFAULT 0,
  capacite_max  INTEGER,
  salle         TEXT,
  duree_seance  REAL DEFAULT 1,
  statut        TEXT DEFAULT 'actif' CHECK(statut IN ('actif','termine','annule')),
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cours_revision_enseignants (
  id           TEXT PRIMARY KEY,
  cours_id     TEXT NOT NULL REFERENCES cours_revision(id) ON DELETE CASCADE,
  personnel_id TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  matiere      TEXT,
  jour         TEXT,
  creneau      TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(cours_id, personnel_id)
);

CREATE TABLE IF NOT EXISTS revision_seances (
  id             TEXT PRIMARY KEY,
  cours_id       TEXT NOT NULL REFERENCES cours_revision(id) ON DELETE CASCADE,
  personnel_id   TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  date_seance    TEXT NOT NULL,
  duree_heures   REAL NOT NULL DEFAULT 1,
  redistribue    INTEGER DEFAULT 0,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bulletins_salaire (
  id            TEXT PRIMARY KEY,
  personnel_id  TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  mois          TEXT NOT NULL,
  type_remuneration TEXT,
  heures        REAL,
  taux_horaire  REAL,
  salaire_base  REAL DEFAULT 0,
  prime_revision REAL DEFAULT 0,
  heures_revision REAL DEFAULT 0,
  primes        REAL DEFAULT 0,
  primes_detail TEXT,
  deductions    REAL DEFAULT 0,
  avance_deduite REAL DEFAULT 0,
  montant_net   REAL NOT NULL,
  date_paiement TEXT,
  genere_par    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(personnel_id, mois)
);

CREATE TABLE IF NOT EXISTS avances_salaire (
  id                TEXT PRIMARY KEY,
  personnel_id      TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  montant           REAL NOT NULL,
  motif             TEXT,
  date_avance       TEXT NOT NULL,
  mois_remboursement TEXT NOT NULL,
  statut            TEXT DEFAULT 'en_cours' CHECK(statut IN ('en_cours','remboursee','annulee')),
  cree_par          INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS types_primes (
  id         TEXT PRIMARY KEY,
  nom        TEXT UNIQUE NOT NULL,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS validations_paie (
  id                      TEXT PRIMARY KEY,
  mois                    TEXT NOT NULL UNIQUE,
  statut                  TEXT DEFAULT 'attente_directeur' CHECK(statut IN ('attente_directeur','attente_admin','approuve','rejete')),
  masse_salariale_totale  REAL DEFAULT 0,
  soumis_par              INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_soumission         TEXT DEFAULT CURRENT_TIMESTAMP,
  valide_directeur_par    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_validation_directeur TEXT,
  valide_admin_par        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_validation_admin   TEXT,
  motif_rejet             TEXT,
  created_at              TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candidatures_enseignants (
  id              TEXT PRIMARY KEY,
  nom             TEXT NOT NULL,
  prenom          TEXT NOT NULL,
  telephone       TEXT,
  email           TEXT,
  matieres        TEXT,
  cycle           TEXT,
  disponibilites  TEXT,
  message         TEXT,
  statut          TEXT DEFAULT 'en_attente' CHECK(statut IN ('en_attente','approuvee','rejetee')),
  personnel_id    TEXT REFERENCES personnel(id) ON DELETE SET NULL,
  approuve_par    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_approbation TEXT,
  date_candidature TEXT DEFAULT CURRENT_TIMESTAMP,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS revision_participants (
  id               TEXT PRIMARY KEY,
  cours_id         TEXT NOT NULL REFERENCES cours_revision(id) ON DELETE CASCADE,
  eleve_id         TEXT REFERENCES eleves(id) ON DELETE SET NULL,
  nom              TEXT NOT NULL,
  prenom           TEXT NOT NULL,
  telephone        TEXT,
  ecole_origine    TEXT,
  est_externe      INTEGER DEFAULT 1,
  montant_paye     REAL DEFAULT 0,
  statut_paiement  TEXT DEFAULT 'impaye' CHECK(statut_paiement IN ('impaye','partiel','paye')),
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS revision_evaluations (
  id             TEXT PRIMARY KEY,
  participant_id TEXT NOT NULL REFERENCES revision_participants(id) ON DELETE CASCADE,
  date_evaluation TEXT NOT NULL,
  note           REAL,
  note_max       REAL DEFAULT 20,
  appreciation   TEXT,
  evaluateur_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS frais_scolarite (
  id                  TEXT PRIMARY KEY,
  classe              TEXT NOT NULL,
  annee_scolaire      TEXT NOT NULL,
  frais_inscription   REAL DEFAULT 0,
  scolarite_annuelle  REAL DEFAULT 0,
  nombre_tranches     INTEGER DEFAULT 3,
  UNIQUE(classe, annee_scolaire)
);

CREATE TABLE IF NOT EXISTS paiements (
  id             TEXT PRIMARY KEY,
  eleve_id       TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  annee_scolaire TEXT,
  type_frais     TEXT,
  libelle        TEXT,
  montant_du     REAL NOT NULL,
  montant_paye   REAL DEFAULT 0,
  date_echeance  TEXT,
  statut         TEXT DEFAULT 'a_payer' CHECK(statut IN ('a_payer','partiel','paye','en_retard')),
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS versements (
  id             TEXT PRIMARY KEY,
  paiement_id    TEXT NOT NULL REFERENCES paiements(id) ON DELETE CASCADE,
  eleve_id       TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  date_vers      TEXT NOT NULL,
  montant        REAL NOT NULL,
  moyen_paiement TEXT,
  reference      TEXT,
  recu_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reinscriptions (
  id              TEXT PRIMARY KEY,
  eleve_id        TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  annee_scolaire  TEXT NOT NULL,
  classe_precedente TEXT,
  classe_nouvelle TEXT,
  statut          TEXT DEFAULT 'en_attente' CHECK(statut IN ('en_attente','validee','refusee')),
  date_demande    TEXT DEFAULT CURRENT_TIMESTAMP,
  date_validation TEXT,
  validee_par     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  notes           TEXT,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(eleve_id, annee_scolaire)
);

CREATE TABLE IF NOT EXISTS cantine_abonnements (
  id        TEXT PRIMARY KEY,
  eleve_id  TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  mois      TEXT NOT NULL,
  formule   TEXT DEFAULT 'complète',
  montant   REAL DEFAULT 0,
  paye      INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(eleve_id, mois)
);

CREATE TABLE IF NOT EXISTS cantine_menus (
  id         TEXT PRIMARY KEY,
  date_menu  TEXT NOT NULL UNIQUE,
  entree     TEXT,
  plat       TEXT,
  dessert    TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
  id                TEXT PRIMARY KEY,
  expediteur_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  destinataire_type TEXT NOT NULL CHECK(destinataire_type IN ('eleve','classe','tous_parents','tous')),
  destinataire_id   TEXT,
  sujet             TEXT,
  contenu           TEXT,
  date_envoi        TEXT DEFAULT CURRENT_TIMESTAMP,
  created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS annonces (
  id               TEXT PRIMARY KEY,
  auteur_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  titre            TEXT NOT NULL,
  contenu          TEXT,
  date_publication TEXT DEFAULT CURRENT_TIMESTAMP,
  cible            TEXT DEFAULT 'tous',
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_eleves_classe   ON eleves(classe);
CREATE INDEX IF NOT EXISTS idx_notes_eleve     ON notes(eleve_id);
CREATE INDEX IF NOT EXISTS idx_absences_eleve  ON absences(eleve_id);
CREATE INDEX IF NOT EXISTS idx_absences_date   ON absences(date_abs);
CREATE INDEX IF NOT EXISTS idx_paiements_eleve ON paiements(eleve_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date_op);
CREATE INDEX IF NOT EXISTS idx_reinsc_eleve    ON reinscriptions(eleve_id);
"""


# ================================================================
# MIGRATION — ajoute automatiquement les colonnes manquantes sur les
# bases de données créées avec une version antérieure du schéma.
# SQLite ne fait JAMAIS ça tout seul avec "CREATE TABLE IF NOT EXISTS" :
# si la table existe déjà, ses colonnes ne sont pas mises à jour, ce qui
# provoquait des erreurs 500 sur tout le module comptabilité et le
# personnel dès qu'une base créée avant ces fonctionnalités était réutilisée.
# ================================================================
MIGRATIONS = {
    'cours_revision_enseignants': {
        'jour': "TEXT",
        'creneau': "TEXT",
    },
    'eleves': {
        'contact_urgence_nom': "TEXT",
        'contact_urgence_telephone': "TEXT",
    },
    'bulletins_salaire': {
        'prime_revision': "REAL DEFAULT 0",
        'heures_revision': "REAL DEFAULT 0",
        'avance_deduite': "REAL DEFAULT 0",
    },
    'transactions': {
        'cree_par': "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        'statut_validation': "TEXT NOT NULL DEFAULT 'auto'",
        'valide_par': "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        'date_validation': "TEXT",
        'motif_rejet': "TEXT",
    },
    'cours_revision': {
        'salle': "TEXT",
        'duree_seance': "REAL DEFAULT 1",
    },
    'personnel': {
        'cycle_enseignement': "TEXT",
        'type_remuneration': "TEXT NOT NULL DEFAULT 'mensuel'",
        'taux_horaire': "REAL DEFAULT 0",
        'photo_url': "TEXT",
        'matricule': "TEXT",
        'adresse': "TEXT",
    },
}


def _reparer_references_corrompues(table_cassee_ref, table_correcte):
    """Répare toute table dont le schéma référence encore 'table_cassee_ref' au lieu de
    'table_correcte'. Séquelle d'un comportement SQLite peu connu : un ALTER TABLE ... RENAME TO
    réécrit AUTOMATIQUEMENT les clauses REFERENCES de TOUTES les autres tables qui pointaient vers
    la table renommée — y compris quand cette table est ensuite supprimée en fin de migration,
    laissant une référence vers une table qui n'existe plus (d'où des erreurs "no such table:
    ..._old_migration" qui semblent totalement sans rapport, par exemple lors d'un ajout de
    personnel ou d'une opération comptable). Ce correctif répare rétroactivement toute base déjà
    touchée ; la cause elle-même est corrigée par ailleurs via PRAGMA legacy_alter_table."""
    tables_touchees = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE ?",
        (f'%{table_cassee_ref}%',)
    ).fetchall()
    for t in tables_touchees:
        nom_table = t['name']
        if nom_table in (table_cassee_ref, table_correcte):
            continue
        sql_corrige = t['sql'].replace(f'"{table_cassee_ref}"', table_correcte).replace(table_cassee_ref, table_correcte)
        if sql_corrige == t['sql']:
            continue
        try:
            print(f"[migration] Réparation d'une référence corrompue sur la table '{nom_table}' (pointait vers '{table_cassee_ref}' au lieu de '{table_correcte}')")
            # legacy_alter_table=ON : empêche ce même renommage de corrompre EN CASCADE
            # d'autres tables qui référenceraient elles-mêmes '{nom_table}'.
            db.execute("PRAGMA legacy_alter_table = ON")
            db.execute("PRAGMA foreign_keys=OFF")
            nom_temp = f"{nom_table}_repair_tmp"
            db.execute(f"ALTER TABLE {nom_table} RENAME TO {nom_temp}")
            db.execute(sql_corrige)
            colonnes = [r['name'] for r in db.execute(f"PRAGMA table_info({nom_temp})").fetchall()]
            colonnes_str = ",".join(colonnes)
            db.execute(f"INSERT INTO {nom_table} ({colonnes_str}) SELECT {colonnes_str} FROM {nom_temp}")
            db.execute(f"DROP TABLE {nom_temp}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
            db.commit()
            print(f"[migration] Table '{nom_table}' réparée avec succès")
        except Exception as e:
            print(f"[migration] Erreur lors de la réparation de '{nom_table}' : {e}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")


def run_migrations():
    # Priorité absolue : réparer toute corruption de référence héritée d'une migration
    # précédente, AVANT toute autre opération (voir _reparer_references_corrompues ci-dessus).
    _reparer_references_corrompues('users_old_migration', 'users')
    _reparer_references_corrompues('eleves_old_migration', 'eleves')

    tables_existantes = {r['name'] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for table, colonnes in MIGRATIONS.items():
        if table not in tables_existantes:
            continue  # la table sera créée avec le schéma complet par executescript()
        colonnes_actuelles = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for colonne, definition in colonnes.items():
            if colonne not in colonnes_actuelles:
                try:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {definition}")
                    print(f"[migration] Colonne ajoutée : {table}.{colonne}")
                except Exception as e:
                    print(f"[migration] Erreur sur {table}.{colonne}: {e}")
    db.commit()

    # Rattrapage : attribue un matricule à tout membre du personnel qui n'en a pas
    # encore (créé avant l'introduction du matricule, ou via un chemin qui l'omettait,
    # comme l'approbation de candidature avant ce correctif).
    if 'personnel' in tables_existantes:
        sans_matricule = db.execute(
            "SELECT id FROM personnel WHERE matricule IS NULL OR matricule='' ORDER BY created_at"
        ).fetchall()
        for row in sans_matricule:
            m = next_matricule_personnel()
            db.execute("UPDATE personnel SET matricule=? WHERE id=?", (m, row['id']))
            db.commit()
        if sans_matricule:
            print(f"[migration] Matricule attribué à {len(sans_matricule)} membre(s) du personnel existant")

    # Initialise (une seule fois) les compteurs de séquence à partir du plus haut
    # matricule déjà existant, pour que les bases déjà en service ne repartent
    # jamais de zéro (ce qui recréerait justement des doublons avec l'existant).
    if not db.execute("SELECT 1 FROM sequences WHERE nom='matricule_eleve'").fetchone():
        row = db.execute("SELECT matricule FROM eleves WHERE matricule LIKE 'M%'").fetchall()
        maxi = 0
        for r in row:
            try: maxi = max(maxi, int(r['matricule'][1:]))
            except (ValueError, TypeError): pass
        db.execute("INSERT INTO sequences (nom, valeur) VALUES ('matricule_eleve', ?)", (maxi,))
        db.commit()
    if 'personnel' in tables_existantes and not db.execute("SELECT 1 FROM sequences WHERE nom='matricule_personnel'").fetchone():
        row = db.execute("SELECT matricule FROM personnel WHERE matricule LIKE 'P%'").fetchall()
        maxi = 0
        for r in row:
            try: maxi = max(maxi, int(r['matricule'][1:]))
            except (ValueError, TypeError): pass
        db.execute("INSERT INTO sequences (nom, valeur) VALUES ('matricule_personnel', ?)", (maxi,))
        db.commit()

    if 'personnel' in tables_existantes:
        # Empêche définitivement deux membres du personnel de partager le même
        # matricule (protège contre une collision lors de créations quasi
        # simultanées). Index partiel (ignore les NULL) pour rester compatible
        # avec d'éventuelles données historiques encore incomplètes.
        try:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_personnel_matricule ON personnel(matricule) WHERE matricule IS NOT NULL AND matricule != ''")
            db.commit()
        except Exception as e:
            print(f"[migration] Index unique matricule personnel non créé (doublons existants probables) : {e}")

    # Migration spéciale : ajout du rôle 'charge_communication' à la contrainte CHECK
    # de la table users (SQLite ne permet pas de modifier une contrainte CHECK existante
    # sans recréer la table — les données sont conservées à l'identique).
    #
    # Cette migration est volontairement auto-réparatrice : si une exécution précédente
    # a été interrompue en plein milieu (coupure de courant, plusieurs processus démarrés
    # en même temps, etc.), une table temporaire "users_old_migration" a pu rester sur le
    # disque sans que la table "users" définitive n'ait été correctement reconstituée.
    # On détecte et on répare ce cas AVANT de tenter quoi que ce soit d'autre, pour ne
    # jamais se retrouver bloqué sur "no such table: users_old_migration".
    NOUVEAU_SCHEMA_USERS = """
        CREATE TABLE users (
          id           INTEGER PRIMARY KEY AUTOINCREMENT,
          username     TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          full_name    TEXT NOT NULL,
          role         TEXT NOT NULL CHECK(role IN ('admin','directeur','comptable','enseignant','secretaire','charge_communication')),
          email        TEXT,
          telephone    TEXT,
          active       INTEGER DEFAULT 1,
          created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
          last_login   TEXT
        )
    """
    users_existe = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    users_old_existe = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users_old_migration'").fetchone()

    if users_old_existe:
        # Une migration précédente a été interrompue avant son nettoyage final.
        try:
            print("[migration] Reprise d'une migration users interrompue précédemment...")
            db.execute("PRAGMA legacy_alter_table = ON")
            db.execute("PRAGMA foreign_keys=OFF")
            if not users_existe:
                # La table définitive n'a jamais été recréée : on la recrée maintenant.
                db.execute(NOUVEAU_SCHEMA_USERS)
            # On ne recopie que si la table définitive est vide (pour ne jamais dupliquer).
            nb = db.execute("SELECT COUNT(*) as n FROM users").fetchone()['n']
            if nb == 0:
                colonnes = [r['name'] for r in db.execute("PRAGMA table_info(users_old_migration)").fetchall()]
                colonnes_str = ",".join(colonnes)
                db.execute(f"INSERT INTO users ({colonnes_str}) SELECT {colonnes_str} FROM users_old_migration")
            db.execute("DROP TABLE users_old_migration")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
            db.commit()
            print("[migration] Migration users réparée et terminée avec succès")
            users_existe = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        except Exception as e:
            print(f"[migration] Erreur lors de la réparation de la migration users : {e}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")

    if users_existe and users_existe['sql'] and 'charge_communication' not in users_existe['sql']:
        try:
            print("[migration] Mise à jour de la contrainte de rôle utilisateurs (ajout charge_communication)")
            db.execute("PRAGMA legacy_alter_table = ON")
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("ALTER TABLE users RENAME TO users_old_migration")
            db.execute(NOUVEAU_SCHEMA_USERS)
            colonnes = [r['name'] for r in db.execute("PRAGMA table_info(users_old_migration)").fetchall()]
            colonnes_str = ",".join(colonnes)
            db.execute(f"INSERT INTO users ({colonnes_str}) SELECT {colonnes_str} FROM users_old_migration")
            db.execute("DROP TABLE users_old_migration")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
            db.commit()
            print("[migration] Contrainte de rôle mise à jour avec succès")
        except Exception as e:
            print(f"[migration] Erreur lors de la mise à jour de la contrainte de rôle : {e}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")

    # Migration spéciale : ajout du statut 'preinscrit' à la contrainte CHECK de eleves
    # (nécessaire pour le point 7 du cahier des charges : préinscription par n'importe qui,
    # validée ensuite par le comptable une fois le paiement effectué).
    # Même logique auto-réparatrice que pour users ci-dessus (voir commentaire détaillé plus haut).
    NOUVEAU_SCHEMA_ELEVES = """
        CREATE TABLE eleves (
          id                TEXT PRIMARY KEY,
          matricule         TEXT UNIQUE,
          nom               TEXT NOT NULL,
          prenom            TEXT NOT NULL,
          date_naissance    TEXT,
          lieu_naissance    TEXT,
          sexe              TEXT CHECK(sexe IN ('M','F')),
          nationalite       TEXT DEFAULT 'Guinéenne',
          classe            TEXT,
          annee_scolaire    TEXT,
          statut            TEXT DEFAULT 'actif' CHECK(statut IN ('actif','inactif','reinsrit','exclu','transfere','preinscrit')),
          photo_url         TEXT,
          pere_nom          TEXT,
          pere_prenom       TEXT,
          pere_profession   TEXT,
          pere_telephone    TEXT,
          pere_email        TEXT,
          mere_nom          TEXT,
          mere_prenom       TEXT,
          mere_profession   TEXT,
          mere_telephone    TEXT,
          mere_email        TEXT,
          tuteur_nom        TEXT,
          tuteur_prenom     TEXT,
          tuteur_relation   TEXT,
          tuteur_telephone  TEXT,
          tuteur_email      TEXT,
          adresse           TEXT,
          contact_urgence_nom       TEXT,
          contact_urgence_telephone TEXT,
          groupe_sanguin    TEXT,
          allergies         TEXT,
          maladies_chroniques TEXT,
          medicaments       TEXT,
          handicap          TEXT,
          medecin_nom       TEXT,
          medecin_telephone TEXT,
          assurance_nom     TEXT,
          assurance_numero  TEXT,
          vaccins           TEXT,
          created_at        TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    eleves_existe = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='eleves'").fetchone()
    eleves_old_existe = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='eleves_old_migration'").fetchone()

    if eleves_old_existe:
        try:
            print("[migration] Reprise d'une migration eleves interrompue précédemment...")
            db.execute("PRAGMA legacy_alter_table = ON")
            db.execute("PRAGMA foreign_keys=OFF")
            if not eleves_existe:
                db.execute(NOUVEAU_SCHEMA_ELEVES)
            nb = db.execute("SELECT COUNT(*) as n FROM eleves").fetchone()['n']
            if nb == 0:
                colonnes = [r['name'] for r in db.execute("PRAGMA table_info(eleves_old_migration)").fetchall()]
                colonnes_str = ",".join(colonnes)
                db.execute(f"INSERT INTO eleves ({colonnes_str}) SELECT {colonnes_str} FROM eleves_old_migration")
            db.execute("DROP TABLE eleves_old_migration")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
            db.commit()
            print("[migration] Migration eleves réparée et terminée avec succès")
            eleves_existe = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='eleves'").fetchone()
        except Exception as e:
            print(f"[migration] Erreur lors de la réparation de la migration eleves : {e}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")

    if eleves_existe and eleves_existe['sql'] and 'preinscrit' not in eleves_existe['sql']:
        try:
            print("[migration] Mise à jour de la contrainte de statut élèves (ajout preinscrit)")
            db.execute("PRAGMA legacy_alter_table = ON")
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("ALTER TABLE eleves RENAME TO eleves_old_migration")
            db.execute(NOUVEAU_SCHEMA_ELEVES)
            # Colonnes communes entre l'ancienne et la nouvelle table (ordre indifférent, on nomme explicitement)
            colonnes_communes = [r['name'] for r in db.execute("PRAGMA table_info(eleves_old_migration)").fetchall()]
            colonnes_str = ",".join(colonnes_communes)
            db.execute(f"INSERT INTO eleves ({colonnes_str}) SELECT {colonnes_str} FROM eleves_old_migration")
            db.execute("DROP TABLE eleves_old_migration")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
            db.commit()
            print("[migration] Contrainte de statut élèves mise à jour avec succès")
        except Exception as e:
            print(f"[migration] Erreur lors de la mise à jour de la contrainte de statut élèves : {e}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")


def init_db():
    db.executescript(SCHEMA)
    db.commit()
    run_migrations()

    # Paramètres par défaut
    defaults = {
        'ecole_nom': 'Groupe Scolaire',
        'ecole_adresse': '',
        'ecole_telephone': '',
        'ecole_email': '',
        'ecole_logo': '',
        'annee_scolaire': '2024-2025',
        'reseau_facebook': '',
        'reseau_instagram': '',
        'reseau_youtube': '',
        'reseau_tiktok': '',
        'reseau_whatsapp': '',
        'seuil_approbation_directeur': '30000',
        'seuil_approbation_admin': '100000',
        'creneaux_horaires': '["07h30 - 09h30","09h30 - 11h30","11h30 - 13h30","14h00 - 16h00","16h00 - 18h00"]',
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (cle, valeur) VALUES (?, ?)", (k, v))
    db.commit()

    # Classes par défaut (si aucune n'existe encore)
    count_classes = db.execute("SELECT COUNT(*) as c FROM classes").fetchone()['c']
    if count_classes == 0:
        defaults_classes = [
            ('Petite Section', 'maternelle'), ('Moyenne Section', 'maternelle'), ('Grande Section', 'maternelle'),
            ('CP', 'primaire'), ('CE1', 'primaire'), ('CE2', 'primaire'), ('CM1', 'primaire'), ('CM2', 'primaire'),
            ('6ème A', 'college'), ('6ème B', 'college'), ('5ème A', 'college'), ('5ème B', 'college'),
            ('4ème A', 'college'), ('4ème B', 'college'), ('3ème A', 'college'), ('3ème B', 'college'),
            ('2nde A', 'lycee'), ('2nde B', 'lycee'), ('1ère A', 'lycee'), ('1ère B', 'lycee'),
            ('Terminale A', 'lycee'), ('Terminale D', 'lycee'),
        ]
        for i, (nom, cycle) in enumerate(defaults_classes):
            db.execute("INSERT OR IGNORE INTO classes (id,nom,cycle,ordre) VALUES (?,?,?,?)",
                       (gen_id('cls'), nom, cycle, i))
        db.commit()

    # Salles par défaut (si aucune n'existe encore)
    count_salles = db.execute("SELECT COUNT(*) as c FROM salles").fetchone()['c']
    if count_salles == 0:
        for i in range(1, 11):
            db.execute("INSERT OR IGNORE INTO salles (id,nom,capacite) VALUES (?,?,?)",
                       (gen_id('salle'), f"Salle {i}", 35))
        db.execute("INSERT OR IGNORE INTO salles (id,nom,capacite) VALUES (?,?,?)", (gen_id('salle'), "Laboratoire", 30))
        db.execute("INSERT OR IGNORE INTO salles (id,nom,capacite) VALUES (?,?,?)", (gen_id('salle'), "Bibliothèque", 40))
        db.execute("INSERT OR IGNORE INTO salles (id,nom,capacite) VALUES (?,?,?)", (gen_id('salle'), "Salle informatique", 25))
        db.commit()

    # Types de primes par défaut (liste déroulante modifiable)
    count_primes = db.execute("SELECT COUNT(*) as c FROM types_primes").fetchone()['c']
    if count_primes == 0:
        for nom in ["Prime de transport", "Prime de logement", "Prime d'ancienneté", "Prime de rendement",
                    "Prime de fin d'année", "Prime exceptionnelle", "Heures supplémentaires"]:
            db.execute("INSERT OR IGNORE INTO types_primes (id,nom) VALUES (?,?)", (gen_id('tp'), nom))
        db.commit()

    # Compte admin initial
    count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    if count == 0:
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD', 'Admin@2025!')
        pwd_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username,password_hash,full_name,role,email) VALUES (?,?,?,?,?)",
            (username, pwd_hash, 'Administrateur Principal', 'admin', 'admin@ecole.com'),
        )
        db.commit()
        print("\n" + "=" * 48)
        print("  Compte administrateur créé")
        print(f"  Identifiant  : {username}")
        print(f"  Mot de passe : {password}")
        print("  Changez ce mot de passe rapidement !")
        print("=" * 48 + "\n")


def get_settings():
    rows = db.execute("SELECT cle, valeur FROM settings").fetchall()
    return {r['cle']: r['valeur'] for r in rows}


def next_sequence(nom, prefixe, largeur):
    """Incrémente atomiquement et retourne le prochain identifiant séquentiel
    (ex: 'M000123'). Toujours utilisé à l'intérieur de matricule_lock par les
    appelants, pour une garantie totale d'unicité même sous forte charge
    concurrente (contrairement à un calcul basé sur le dernier enregistrement créé)."""
    row = db.execute("SELECT valeur FROM sequences WHERE nom=?", (nom,)).fetchone()
    valeur = (row['valeur'] if row else 0) + 1
    db.execute("INSERT INTO sequences (nom, valeur) VALUES (?,?) ON CONFLICT(nom) DO UPDATE SET valeur=?", (nom, valeur, valeur))
    db.commit()
    return prefixe + str(valeur).zfill(largeur)


def next_matricule_personnel():
    """Génère le prochain matricule personnel (P0001, P0002…), partagé par toutes les
    routes qui créent une fiche personnel (création directe, approbation de candidature)."""
    return next_sequence('matricule_personnel', 'P', 4)


def get_classes_enseignant(user_id):
    """Retourne la liste des classes qu'un enseignant donné (via son user_id) enseigne
    réellement, déduite de l'emploi du temps. Utilisé pour restreindre ce qu'un
    enseignant peut voir (élèves, notes, absences, devoirs) à SES classes uniquement."""
    personnel = db.execute("SELECT id FROM personnel WHERE user_id=?", (user_id,)).fetchone()
    if not personnel:
        return []
    rows = db.execute(
        "SELECT DISTINCT classe FROM emploi_du_temps WHERE professeur_id=?", (personnel['id'],)
    ).fetchall()
    return [r['classe'] for r in rows]


def log_action(user, action, entite, entite_id=None, details=None):
    """Enregistre une entrée dans le journal d'audit (fondation du point 6 du cahier des charges).
    `user` est le dict g.user (issu du JWT) ou None pour une action système.
    Cette fonction ne doit jamais lever d'exception qui bloquerait l'opération principale.
    """
    try:
        import json as _json
        uid = user.get('id') if user else None
        uname = user.get('name') if user else 'Système'
        det = _json.dumps(details, ensure_ascii=False, default=str) if details is not None else None
        db.execute(
            "INSERT INTO journal_audit (id,user_id,user_nom,action,entite,entite_id,details) VALUES (?,?,?,?,?,?,?)",
            (gen_id('jrn'), uid, uname, action, entite, entite_id, det),
        )
        db.commit()
    except Exception as e:
        print(f"[journal_audit] Erreur d'enregistrement (non bloquante): {e}")
