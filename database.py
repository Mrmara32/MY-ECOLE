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
from werkzeug.security import generate_password_hash, check_password_hash

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

# PostgreSQL (hébergement multi-écoles) si DATABASE_URL est défini ; sinon SQLite (version .exe, développement).
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[len('postgres://'):]
USE_PG = DATABASE_URL.startswith('postgresql://')


# ================================================================
# CONNEXION À LA BASE — une connexion PAR FIL D'EXÉCUTION (thread)
# ----------------------------------------------------------------
# Auparavant, une connexion unique était partagée par toutes les requêtes. Dès que
# deux requêtes arrivaient en même temps, la validation (commit) de l'une pouvait
# enregistrer à moitié le travail de l'autre, ou provoquer l'erreur « cannot commit -
# no transaction is active » (reproduit par tests/test_parcours.py). Cela obligeait
# aussi le serveur à traiter les requêtes une par une : un simple envoi d'e-mail
# bloquait toute l'école pendant plusieurs secondes.
#
# Désormais, chaque thread du serveur possède sa propre connexion. L'objet `db`
# reste utilisable exactement comme avant (`from database import db`, puis
# db.execute(...), db.commit()) : il redirige simplement vers la connexion du
# thread courant.
# ================================================================
_local = threading.local()
DELAI_ATTENTE_VERROU_S = 30  # attente max. si un autre thread est en train d'écrire

# Les requêtes qui MODIFIENT des données (POST/PUT/DELETE) passent une par une, comme
# avant ; seules les lectures (affichage des pages, listes, tableaux de bord) se font
# en parallèle. Le code existant a été écrit pour un traitement une-par-une des
# écritures (« vérifier puis modifier » : déjà payé ?, déjà validé ?…) : ce verrou
# garantit qu'il continue de fonctionner exactement comme prévu — deux clics
# simultanés sur « Payer » ne peuvent pas encaisser deux fois. Voir app.py.
verrou_ecritures = threading.Lock()


def _ouvrir_connexion():
    if USE_PG:
        import pg_compat
        return pg_compat.ConnexionPg(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH, timeout=DELAI_ATTENTE_VERROU_S)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {DELAI_ATTENTE_VERROU_S * 1000}")
    return conn


def connexion_courante():
    """Connexion SQLite propre au thread courant (créée au premier besoin)."""
    conn = getattr(_local, 'conn', None)
    if conn is not None and USE_PG and conn.closed:
        conn = None          # connexion coupée par le serveur (redémarrage, inactivité) : on en rouvre une
    if conn is None:
        conn = _ouvrir_connexion()
        _local.conn = conn
    return conn


class _ConnexionDuThread:
    """Se comporte comme une connexion sqlite3 ordinaire, mais chaque thread
    travaille sur sa propre connexion (voir explication ci-dessus)."""

    def __getattr__(self, nom):
        return getattr(connexion_courante(), nom)

    def __setattr__(self, nom, valeur):
        setattr(connexion_courante(), nom, valeur)


db = _ConnexionDuThread()


def terminer_requete(erreur=None):
    """Appelée automatiquement à la fin de CHAQUE requête HTTP (voir app.py).
    Les écritures restées en attente sont validées — comme le faisait l'ancienne
    connexion partagée au commit suivant — sauf si la requête a échoué : elles
    sont alors annulées, pour ne jamais enregistrer une opération à moitié faite."""
    conn = getattr(_local, 'conn', None)
    if conn is None:
        return
    try:
        if conn.in_transaction:
            if erreur is not None:
                conn.rollback()
            else:
                conn.commit()
    except Exception as e:
        print(f"[base] Fin de requête : impossible de finaliser la transaction ({e})")
        try:
            conn.rollback()
        except Exception:
            pass


def prendre_verrou_ecritures_global():
    """PostgreSQL, plusieurs processus : le verrou des écritures (threading.Lock) ne protège qu'un seul
    processus ; on le double d'un verrou de session PostgreSQL pour garder « une écriture à la fois »."""
    if USE_PG:
        connexion_courante().execute("SELECT pg_advisory_lock(7002)")


def liberer_verrou_ecritures_global():
    if USE_PG:
        try:
            connexion_courante().execute("SELECT pg_advisory_unlock(7002)")
        except Exception:
            # connexion dans un état incertain : la fermer libère le verrou côté serveur
            try:
                _local.conn.close()
            except Exception:
                pass
            _local.conn = None


def debut_ecriture_exclusive():
    """Démarre une transaction en prenant IMMÉDIATEMENT le verrou d'écriture de la
    base (BEGIN IMMEDIATE). À utiliser avant un « lire puis modifier » sur une même
    donnée (ex : montant déjà payé d'un paiement) : deux requêtes simultanées
    s'exécutent alors l'une après l'autre au lieu de s'écraser mutuellement."""
    conn = connexion_courante()
    if conn.in_transaction:
        conn.commit()
    if USE_PG:
        # Verrou applicatif global, relâché à la fin de la transaction : équivalent de BEGIN IMMEDIATE,
        # y compris entre plusieurs processus/serveurs.
        conn.execute("SELECT pg_advisory_xact_lock(7001)")
        return
    conn.execute("BEGIN IMMEDIATE")


def annuler_transaction_en_cours():
    """Annule les écritures non validées du thread courant (utilisé par les
    gestionnaires d'erreur : une opération interrompue par une erreur ne doit
    pas être enregistrée à moitié)."""
    conn = getattr(_local, 'conn', None)
    if conn is not None and conn.in_transaction:
        try:
            conn.rollback()
        except Exception:
            pass


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
-- ═══════════════════════════════════════════════════════════════════
-- MULTI-ÉTABLISSEMENT — Fondations (Phase 1)
-- Chaque école est un espace totalement indépendant : sa propre administration,
-- ses propres données, sans aucune visibilité croisée avec une autre école,
-- même hébergées sur la même installation de l'application.
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ecoles (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  nom                 TEXT NOT NULL,
  code                TEXT UNIQUE NOT NULL,
  email_contact       TEXT,
  telephone_contact   TEXT,
  statut_licence      TEXT NOT NULL DEFAULT 'essai' CHECK(statut_licence IN ('essai','active','suspendue','expiree')),
  date_debut_licence   TEXT DEFAULT CURRENT_TIMESTAMP,
  date_expiration_licence TEXT,
  actif               INTEGER DEFAULT 1,
  email_confirme      INTEGER DEFAULT 0,
  jeton_confirmation  TEXT,
  created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
  ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  cle   TEXT NOT NULL,
  valeur TEXT,
  PRIMARY KEY (ecole_id, cle)
);

-- Compteurs internes (ex: dernier numéro de matricule utilisé), séparés des
-- paramètres exposés à l'utilisateur (table settings) pour éviter tout risque
-- de modification accidentelle depuis l'écran Paramètres. L'incrémentation
-- atomique de cette table (combinée au verrou applicatif matricule_lock) évite
-- toute collision, y compris sous forte charge concurrente, contrairement à un
-- calcul basé sur "le dernier matricule créé" (peu fiable : la résolution des
-- horodatages SQLite est à la seconde près, insuffisante en cas de créations
-- multiples la même seconde). Chaque école a sa propre numérotation, repartant
-- de zéro — la matricule M000001 de l'École A n'a aucun lien avec celle de l'École B.
CREATE TABLE IF NOT EXISTS sequences (
  ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  nom    TEXT NOT NULL,
  valeur INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ecole_id, nom)
);

CREATE TABLE IF NOT EXISTS users (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ecole_id     INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  username     TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  full_name    TEXT NOT NULL,
  role         TEXT NOT NULL CHECK(role IN ('admin','directeur','comptable','enseignant','secretaire','charge_communication','directeur_etudes','parent')),
  email        TEXT,
  telephone    TEXT,
  civilite     TEXT,
  est_super_admin INTEGER DEFAULT 0,
  active       INTEGER DEFAULT 1,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  last_login   TEXT,
  UNIQUE(ecole_id, username)
);

CREATE TABLE IF NOT EXISTS parents_eleves (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  eleve_id   TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, eleve_id)
);

CREATE TABLE IF NOT EXISTS classes (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  nom        TEXT NOT NULL,
  cycle      TEXT NOT NULL CHECK(cycle IN ('maternelle','primaire','college','lycee','superieur','formation')),
  ordre      INTEGER DEFAULT 0,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, nom)
);

CREATE TABLE IF NOT EXISTS personnel (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id                TEXT PRIMARY KEY,
  matricule         TEXT,
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
  created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, matricule)
);

CREATE TABLE IF NOT EXISTS notes (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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

-- Discipline et vie scolaire : observations, sanctions, félicitations, par élève.
CREATE TABLE IF NOT EXISTS discipline (
  ecole_id        INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id              TEXT PRIMARY KEY,
  eleve_id        TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  date_fait       TEXT NOT NULL,
  type            TEXT NOT NULL CHECK(type IN ('felicitations','observation','avertissement','retenue','blame','exclusion_temporaire')),
  motif           TEXT NOT NULL,
  description     TEXT,
  sanction        TEXT,
  nb_jours        INTEGER DEFAULT 0,
  visible_parents INTEGER DEFAULT 1,
  enregistre_par  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_discipline_eleve ON discipline(ecole_id, eleve_id, date_fait);

-- Échecs de connexion (blocage temporaire anti force brute, voir securite.py).
CREATE TABLE IF NOT EXISTS echecs_connexion (
  cle          TEXT PRIMARY KEY,
  nombre       INTEGER NOT NULL DEFAULT 0,
  debut        TEXT NOT NULL,
  bloque_jusqu TEXT
);

-- Matières enseignées dans chaque classe, avec leur coefficient (moyenne générale pondérée).
CREATE TABLE IF NOT EXISTS matieres_classe (
  ecole_id    INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id          TEXT PRIMARY KEY,
  classe      TEXT NOT NULL,
  matiere     TEXT NOT NULL,
  coefficient REAL NOT NULL DEFAULT 1 CHECK(coefficient > 0),
  UNIQUE(ecole_id, classe, matiere)
);

-- Appréciation du conseil de classe saisie à la main (remplace l'appréciation automatique).
CREATE TABLE IF NOT EXISTS appreciations_bulletin (
  ecole_id     INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  eleve_id     TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  periode      TEXT NOT NULL CHECK(periode IN ('1','2','3','annee')),
  appreciation TEXT,
  updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (eleve_id, periode)
);

-- Décision de fin d'année (conseil de classe) : admis, redouble, exclu.
CREATE TABLE IF NOT EXISTS decisions_annuelles (
  ecole_id         INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  eleve_id         TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  annee_scolaire   TEXT NOT NULL,
  classe_origine   TEXT NOT NULL,
  moyenne_annuelle REAL,
  decision         TEXT NOT NULL CHECK(decision IN ('admis','redouble','exclu')),
  classe_suivante  TEXT,
  decide_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (eleve_id, annee_scolaire)
);

CREATE TABLE IF NOT EXISTS devoirs (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id           TEXT PRIMARY KEY,
  jour         TEXT NOT NULL,
  creneau      TEXT NOT NULL,
  classe       TEXT NOT NULL,
  matiere      TEXT,
  professeur_id TEXT,
  salle        TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, jour, creneau, classe)
);

CREATE TABLE IF NOT EXISTS absences (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id           TEXT PRIMARY KEY,
  personnel_id TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  date_debut   TEXT NOT NULL,
  date_fin     TEXT,
  motif        TEXT,
  remplace_par TEXT,
  signale_par  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Pointage biométrique / par badge (élèves, enseignants, personnel administratif).
-- L'application ne garde JAMAIS d'empreinte ni de visage : ils restent dans l'appareil,
-- qui n'envoie qu'un numéro d'identifiant et une heure de passage.
CREATE TABLE IF NOT EXISTS appareils_pointage (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id                TEXT PRIMARY KEY,
  nom               TEXT NOT NULL,
  numero_serie      TEXT,
  cle_hash          TEXT,
  actif             INTEGER DEFAULT 1,
  derniere_activite TEXT,
  created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_appareils_serie
  ON appareils_pointage(numero_serie) WHERE numero_serie IS NOT NULL AND numero_serie <> '';

CREATE TABLE IF NOT EXISTS codes_pointage (
  ecole_id      INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  code          TEXT NOT NULL,
  personne_type TEXT NOT NULL CHECK(personne_type IN ('eleve','personnel')),
  personne_id   TEXT NOT NULL,
  PRIMARY KEY (ecole_id, code)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_codes_pointage_personne
  ON codes_pointage(ecole_id, personne_type, personne_id);

CREATE TABLE IF NOT EXISTS pointages (
  ecole_id      INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id            TEXT PRIMARY KEY,
  appareil_id   TEXT,
  code          TEXT NOT NULL,
  horodatage    TEXT NOT NULL,
  source        TEXT NOT NULL DEFAULT 'appareil',
  personne_type TEXT,
  personne_id   TEXT,
  saisi_par     TEXT,
  motif         TEXT,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pointages_doublon
  ON pointages(ecole_id, COALESCE(appareil_id, ''), code, horodatage);
CREATE INDEX IF NOT EXISTS idx_pointages_ecole_date ON pointages(ecole_id, horodatage);

CREATE TABLE IF NOT EXISTS fournisseurs (
  ecole_id      INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id            TEXT PRIMARY KEY,
  nom           TEXT NOT NULL,
  categorie     TEXT,
  telephone     TEXT,
  email         TEXT,
  adresse       TEXT,
  notes         TEXT,
  actif         INTEGER DEFAULT 1,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, nom)
);

CREATE TABLE IF NOT EXISTS transactions (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id             TEXT PRIMARY KEY,
  type           TEXT NOT NULL CHECK(type IN ('entree','sortie')),
  date_op        TEXT NOT NULL,
  description    TEXT,
  categorie      TEXT,
  moyen_paiement TEXT,
  montant        REAL NOT NULL,
  reference      TEXT,
  eleve_id       TEXT REFERENCES eleves(id) ON DELETE SET NULL,
  fournisseur_id TEXT REFERENCES fournisseurs(id) ON DELETE SET NULL,
  journal        TEXT NOT NULL DEFAULT 'diverses' CHECK(journal IN ('achats','ventes','salaires','diverses','a_nouveau')),
  cree_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  statut_validation TEXT NOT NULL DEFAULT 'auto' CHECK(statut_validation IN ('auto','attente_directeur','attente_admin','valide','rejete')),
  valide_par     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_validation TEXT,
  motif_rejet    TEXT,
  rapproche      INTEGER DEFAULT 0,
  date_rapprochement TEXT,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions_recurrentes (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id             TEXT PRIMARY KEY,
  type           TEXT NOT NULL CHECK(type IN ('entree','sortie')),
  categorie      TEXT NOT NULL,
  description    TEXT,
  montant        REAL NOT NULL,
  moyen_paiement TEXT,
  jour_du_mois   INTEGER NOT NULL DEFAULT 1 CHECK(jour_du_mois BETWEEN 1 AND 28),
  actif          INTEGER DEFAULT 1,
  dernier_mois_genere TEXT,
  cree_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS budgets (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  categorie  TEXT NOT NULL,
  type       TEXT NOT NULL CHECK(type IN ('entree','sortie')),
  mois       TEXT NOT NULL,
  montant_prevu REAL NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, categorie, type, mois)
);

CREATE TABLE IF NOT EXISTS journal_audit (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  type       TEXT NOT NULL CHECK(type IN ('photo','video')),
  url        TEXT NOT NULL,
  legende    TEXT,
  ordre      INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eleve_du_mois (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  eleve_id   TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  mois       TEXT NOT NULL,
  motif      TEXT,
  designe_par INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, mois)
);

CREATE TABLE IF NOT EXISTS salles (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  nom        TEXT NOT NULL,
  capacite   INTEGER,
  batiment   TEXT,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, nom)
);

CREATE TABLE IF NOT EXISTS cours_revision (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id             TEXT PRIMARY KEY,
  cours_id       TEXT NOT NULL REFERENCES cours_revision(id) ON DELETE CASCADE,
  personnel_id   TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  date_seance    TEXT NOT NULL,
  duree_heures   REAL NOT NULL DEFAULT 1,
  redistribue    INTEGER DEFAULT 0,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bulletins_salaire (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  nom        TEXT UNIQUE NOT NULL,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS validations_paie (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id              TEXT PRIMARY KEY,
  nom             TEXT NOT NULL,
  prenom          TEXT NOT NULL,
  telephone       TEXT,
  email           TEXT,
  matieres        TEXT,
  cycle           TEXT,
  disponibilites  TEXT,
  message         TEXT,
  username_souhaite TEXT,
  password_hash   TEXT,
  statut          TEXT DEFAULT 'en_attente' CHECK(statut IN ('en_attente','approuvee','rejetee')),
  personnel_id    TEXT REFERENCES personnel(id) ON DELETE SET NULL,
  approuve_par    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_approbation TEXT,
  date_candidature TEXT DEFAULT CURRENT_TIMESTAMP,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS revision_participants (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id                  TEXT PRIMARY KEY,
  classe              TEXT NOT NULL,
  annee_scolaire      TEXT NOT NULL,
  frais_inscription   REAL DEFAULT 0,
  frais_reinscription REAL DEFAULT 0,
  scolarite_annuelle  REAL DEFAULT 0,
  nombre_tranches     INTEGER DEFAULT 3,
  UNIQUE(ecole_id, classe, annee_scolaire)
);

CREATE TABLE IF NOT EXISTS paiements (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id         TEXT PRIMARY KEY,
  date_menu  TEXT NOT NULL UNIQUE,
  entree     TEXT,
  plat       TEXT,
  dessert    TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
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
  ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id               TEXT PRIMARY KEY,
  auteur_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  titre            TEXT NOT NULL,
  contenu          TEXT,
  date_publication TEXT DEFAULT CURRENT_TIMESTAMP,
  cible            TEXT DEFAULT 'tous',
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════ MODULE LOGISTIQUE ═══════════════════

CREATE TABLE IF NOT EXISTS stock_produits (
  ecole_id       INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id             TEXT PRIMARY KEY,
  nom            TEXT NOT NULL,
  categorie      TEXT NOT NULL DEFAULT 'materiel' CHECK(categorie IN ('materiel','fourniture','alimentaire','entretien','autre')),
  unite          TEXT NOT NULL DEFAULT 'unité',
  quantite       REAL NOT NULL DEFAULT 0,
  seuil_alerte   REAL NOT NULL DEFAULT 0,
  prix_unitaire  REAL DEFAULT 0,
  notes          TEXT,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, nom, categorie)
);

CREATE TABLE IF NOT EXISTS stock_mouvements (
  ecole_id      INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id            TEXT PRIMARY KEY,
  produit_id    TEXT NOT NULL REFERENCES stock_produits(id) ON DELETE CASCADE,
  type          TEXT NOT NULL CHECK(type IN ('entree','sortie')),
  quantite      REAL NOT NULL,
  motif         TEXT,
  commande_id   TEXT,
  cree_par      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_mouvement TEXT NOT NULL DEFAULT (date('now')),
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commandes (
  ecole_id       INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id             TEXT PRIMARY KEY,
  numero         TEXT,
  fournisseur_id TEXT REFERENCES fournisseurs(id) ON DELETE SET NULL,
  statut         TEXT NOT NULL DEFAULT 'brouillon' CHECK(statut IN ('brouillon','envoyee','recue','annulee')),
  date_commande  TEXT NOT NULL DEFAULT (date('now')),
  date_reception TEXT,
  montant_total  REAL NOT NULL DEFAULT 0,
  notes          TEXT,
  cree_par       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commande_lignes (
  id           TEXT PRIMARY KEY,
  commande_id  TEXT NOT NULL REFERENCES commandes(id) ON DELETE CASCADE,
  produit_id   TEXT REFERENCES stock_produits(id) ON DELETE SET NULL,
  designation  TEXT NOT NULL,
  quantite     REAL NOT NULL DEFAULT 1,
  prix_unitaire REAL NOT NULL DEFAULT 0,
  montant_ligne REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS maintenance_interventions (
  ecole_id         INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id               TEXT PRIMARY KEY,
  titre            TEXT NOT NULL,
  salle_id         TEXT REFERENCES salles(id) ON DELETE SET NULL,
  lieu             TEXT,
  equipement       TEXT,
  description      TEXT,
  priorite         TEXT NOT NULL DEFAULT 'normale' CHECK(priorite IN ('basse','normale','haute','urgente')),
  statut           TEXT NOT NULL DEFAULT 'signalee' CHECK(statut IN ('signalee','en_cours','resolue','annulee')),
  assigne_a        TEXT REFERENCES personnel(id) ON DELETE SET NULL,
  cout             REAL DEFAULT 0,
  signale_par      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  date_signalement TEXT NOT NULL DEFAULT (date('now')),
  date_resolution  TEXT,
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transport_vehicules (
  ecole_id       INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id             TEXT PRIMARY KEY,
  immatriculation TEXT NOT NULL,
  marque_modele  TEXT,
  capacite       INTEGER DEFAULT 0,
  statut         TEXT NOT NULL DEFAULT 'actif' CHECK(statut IN ('actif','maintenance','hors_service')),
  chauffeur_id   TEXT REFERENCES personnel(id) ON DELETE SET NULL,
  notes          TEXT,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ecole_id, immatriculation)
);

CREATE TABLE IF NOT EXISTS transport_itineraires (
  ecole_id     INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id           TEXT PRIMARY KEY,
  nom          TEXT NOT NULL,
  zone         TEXT,
  vehicule_id  TEXT REFERENCES transport_vehicules(id) ON DELETE SET NULL,
  description  TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transport_eleves (
  ecole_id      INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  id            TEXT PRIMARY KEY,
  eleve_id      TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
  itineraire_id TEXT NOT NULL REFERENCES transport_itineraires(id) ON DELETE CASCADE,
  point_montee  TEXT,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(itineraire_id, eleve_id)
);

CREATE INDEX IF NOT EXISTS idx_eleves_classe   ON eleves(classe);
CREATE INDEX IF NOT EXISTS idx_notes_eleve     ON notes(eleve_id);
CREATE INDEX IF NOT EXISTS idx_absences_eleve  ON absences(eleve_id);
CREATE INDEX IF NOT EXISTS idx_absences_date   ON absences(date_abs);
CREATE INDEX IF NOT EXISTS idx_paiements_eleve ON paiements(eleve_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date_op);
CREATE INDEX IF NOT EXISTS idx_reinsc_eleve    ON reinscriptions(eleve_id);
CREATE INDEX IF NOT EXISTS idx_stockmvt_produit ON stock_mouvements(produit_id);
CREATE INDEX IF NOT EXISTS idx_cmdlignes_cmd    ON commande_lignes(commande_id);
CREATE INDEX IF NOT EXISTS idx_maint_statut     ON maintenance_interventions(statut);
CREATE INDEX IF NOT EXISTS idx_transp_eleve     ON transport_eleves(eleve_id);

-- Clés d'idempotence : protège contre le double-traitement d'une action rejouée
-- par la synchronisation hors ligne (ex: la connexion tombe juste après un
-- versement traité mais avant que la confirmation n'arrive au navigateur — sans
-- cette protection, la resynchronisation encaisserait le même versement deux fois).
CREATE TABLE IF NOT EXISTS idempotency_keys (
  client_op_id   TEXT PRIMARY KEY,
  ecole_id       INTEGER NOT NULL,
  endpoint       TEXT NOT NULL,
  response_body  TEXT NOT NULL,
  response_status INTEGER NOT NULL,
  created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Permissions personnalisees par utilisateur, module par module. Ce systeme est
-- ADDITIF : tant qu'aucune ligne n'existe pour un (utilisateur, module) donne,
-- le comportement habituel base sur le role (@require_role) s'applique sans
-- aucun changement. Des qu'une ligne existe, elle fait autorite pour ce module
-- precis et cet utilisateur precis, independamment de son role. Un admin (ou
-- super-administrateur) n'est jamais restreint par ce systeme.
CREATE TABLE IF NOT EXISTS permissions_utilisateur (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ecole_id       INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  module         TEXT NOT NULL,
  peut_voir      INTEGER NOT NULL DEFAULT 1,
  peut_creer     INTEGER NOT NULL DEFAULT 0,
  peut_modifier  INTEGER NOT NULL DEFAULT 0,
  peut_supprimer INTEGER NOT NULL DEFAULT 0,
  modifie_par    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  modifie_le     TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, module)
);

-- Archive des paiements supprimés : une suppression ne fait plus disparaître
-- l'information. Le paiement et TOUS ses versements sont copiés ici (colonne
-- donnees, au format JSON), avec l'auteur, la date et le motif obligatoire.
CREATE TABLE IF NOT EXISTS paiements_supprimes (
  id               TEXT PRIMARY KEY,
  ecole_id         INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
  paiement_id      TEXT NOT NULL,
  eleve_id         TEXT,
  eleve_nom        TEXT,
  libelle          TEXT,
  montant_du       REAL,
  montant_paye     REAL,
  nb_versements    INTEGER DEFAULT 0,
  donnees          TEXT NOT NULL,
  motif            TEXT NOT NULL,
  supprime_par     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  supprime_par_nom TEXT,
  supprime_le      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_paiements_supprimes_ecole ON paiements_supprimes(ecole_id, supprime_le);
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
    'users': {
        'civilite': "TEXT",  # 'M.' ou 'Mme' — utilisé pour le message de bienvenue personnalisé
        'est_super_admin': "INTEGER DEFAULT 0",  # accès à la supervision de toutes les écoles clientes
        'email_confirme': "INTEGER DEFAULT 0",  # pour les comptes parents avec confirmation par e-mail
        'jeton_confirmation': "TEXT",
        'doit_changer_mdp': "INTEGER DEFAULT 0",  # mot de passe provisoire : à changer à la prochaine connexion
        'totp_secret': "TEXT",                    # double authentification (voir double_authentification.py)
        'totp_actif': "INTEGER DEFAULT 0",
        'totp_dernier_pas': "INTEGER DEFAULT 0",  # dernier code accepté : un code ne sert qu'une fois
        'codes_secours': "TEXT",                  # empreintes (SHA-256) des codes de secours restants
    },
    'notes': {
        'annee_scolaire': "TEXT",  # sans elle, les notes d'une année se mélangeraient à celles de la suivante
    },
    'ecoles': {
        'email_confirme': "INTEGER DEFAULT 0",
        'jeton_confirmation': "TEXT",
    },
    'candidatures_enseignants': {
        'username_souhaite': "TEXT",
        'password_hash': "TEXT",
    },
    'transactions': {
        'rapproche': "INTEGER DEFAULT 0",
        'date_rapprochement': "TEXT",
        'cree_par': "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        'statut_validation': "TEXT NOT NULL DEFAULT 'auto'",
        'valide_par': "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        'date_validation': "TEXT",
        'motif_rejet': "TEXT",
        'fournisseur_id': "TEXT REFERENCES fournisseurs(id) ON DELETE SET NULL",
        'journal': "TEXT NOT NULL DEFAULT 'diverses'",
    },
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
    'frais_scolarite': {
        # Frais dû par un élève qui se réinscrit (ancien élève), distinct des frais
        # d'inscription (nouvel élève) — les deux montants coexistent dans le même barème.
        'frais_reinscription': "REAL DEFAULT 0",
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


def _run_migrations_pg():
    """PostgreSQL : le schéma est créé à jour ; seules les colonnes ajoutées après coup (dictionnaire
    MIGRATIONS) restent à rattraper. Les reconstructions de tables propres à SQLite n'ont pas lieu d'être."""
    tables = {r['table_name'] for r in db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()}
    for table, colonnes in MIGRATIONS.items():
        if table not in tables:
            continue
        actuelles = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for colonne, definition in colonnes.items():
            if colonne not in actuelles:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {pg_compat_type(definition)}")
                print(f"[migration] Colonne ajoutée : {table}.{colonne}")
    db.commit()
    appliquer_migrations_versionnees()


def pg_compat_type(definition):
    import pg_compat
    return pg_compat.traduire_schema(definition)


def run_migrations():
    if USE_PG:
        return _run_migrations_pg()
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

    # Fondations multi-établissement : ajoute ecole_id (rattaché par défaut à l'école n°1,
    # celle existant avant cette évolution) à toutes les tables de données propres à une
    # école, si la colonne n'existe pas déjà. Boucle séparée du dictionnaire MIGRATIONS
    # ci-dessus pour ne jamais risquer d'interférer avec ses entrées existantes.
    TABLES_MULTI_ECOLE = [
        'parents_eleves', 'classes', 'personnel', 'heures_enseignement', 'seances_cours',
        'eleves', 'notes', 'devoirs', 'emploi_du_temps', 'absences', 'absences_personnel',
        'transactions', 'transactions_recurrentes', 'budgets', 'journal_audit', 'articles',
        'articles_media', 'eleve_du_mois', 'salles', 'cours_revision', 'cours_revision_enseignants',
        'revision_seances', 'bulletins_salaire', 'avances_salaire', 'types_primes', 'validations_paie',
        'candidatures_enseignants', 'revision_participants', 'revision_evaluations', 'frais_scolarite',
        'paiements', 'versements', 'reinscriptions', 'cantine_abonnements', 'cantine_menus',
        'messages', 'annonces', 'fournisseurs',
    ]
    for table in TABLES_MULTI_ECOLE:
        if table not in tables_existantes:
            continue
        colonnes_actuelles = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if 'ecole_id' not in colonnes_actuelles:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN ecole_id INTEGER NOT NULL DEFAULT 1")
                print(f"[migration] Colonne ajoutée : {table}.ecole_id (multi-établissement)")
            except Exception as e:
                print(f"[migration] Erreur sur {table}.ecole_id: {e}")
    db.commit()

    # Migration spéciale : certaines contraintes UNIQUE existaient AVANT l'ajout d'ecole_id
    # et ne portaient donc que sur des valeurs "ordinaires" (classe, mois...) qui peuvent
    # tout à fait se répéter d'une école à l'autre. Sans cette correction, une deuxième
    # école ne pourrait pas définir un barème pour "CM2" si la première l'a déjà fait.
    for table, nouveau_marqueur, nouvelle_creation in [
        ('classes', "'superieur'",
         "CREATE TABLE classes (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, nom TEXT NOT NULL, cycle TEXT NOT NULL CHECK(cycle IN ('maternelle','primaire','college','lycee','superieur','formation')), ordre INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(ecole_id, nom))"),
        ('classes', 'UNIQUE(ecole_id, nom)',
         "CREATE TABLE classes (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, nom TEXT NOT NULL, cycle TEXT NOT NULL CHECK(cycle IN ('maternelle','primaire','college','lycee','superieur','formation')), ordre INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(ecole_id, nom))"),
        ('salles', 'UNIQUE(ecole_id, nom)',
         "CREATE TABLE salles (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, nom TEXT NOT NULL, capacite INTEGER, batiment TEXT, active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(ecole_id, nom))"),
        ('frais_scolarite', 'UNIQUE(ecole_id, classe, annee_scolaire)',
         "CREATE TABLE frais_scolarite (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, classe TEXT NOT NULL, annee_scolaire TEXT NOT NULL, frais_inscription REAL DEFAULT 0, scolarite_annuelle REAL DEFAULT 0, nombre_tranches INTEGER DEFAULT 3, UNIQUE(ecole_id, classe, annee_scolaire))"),
        ('budgets', 'UNIQUE(ecole_id, categorie, type, mois)',
         "CREATE TABLE budgets (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, categorie TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('entree','sortie')), mois TEXT NOT NULL, montant_prevu REAL NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(ecole_id, categorie, type, mois))"),
        ('emploi_du_temps', 'UNIQUE(ecole_id, jour, creneau, classe)',
         "CREATE TABLE emploi_du_temps (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, jour TEXT NOT NULL, creneau TEXT NOT NULL, classe TEXT NOT NULL, matiere TEXT, professeur_id TEXT, salle TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(ecole_id, jour, creneau, classe))"),
        ('eleve_du_mois', 'UNIQUE(ecole_id, mois)',
         "CREATE TABLE eleve_du_mois (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, id TEXT PRIMARY KEY, eleve_id TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE, mois TEXT NOT NULL, motif TEXT, designe_par INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(ecole_id, mois))"),
    ]:
        table_sql_row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not table_sql_row or nouveau_marqueur in (table_sql_row['sql'] or ''):
            continue  # déjà à jour, ou table pas encore créée (sera créée directement avec la bonne contrainte)
        table_old = f"{table}_old_migration"
        try:
            print(f"[migration] Correction de la contrainte unique de {table} (multi-établissement)")
            db.execute("PRAGMA legacy_alter_table = ON")
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute(f"ALTER TABLE {table} RENAME TO {table_old}")
            db.execute(nouvelle_creation)
            colonnes = [r['name'] for r in db.execute(f"PRAGMA table_info({table_old})").fetchall()]
            colonnes_str = ",".join(colonnes)
            db.execute(f"INSERT INTO {table} ({colonnes_str}) SELECT {colonnes_str} FROM {table_old}")
            db.execute(f"DROP TABLE {table_old}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
            db.commit()
            print(f"[migration] Contrainte unique de {table} corrigée avec succès")
        except Exception as e:
            print(f"[migration] Erreur lors de la correction de {table} : {e}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA legacy_alter_table = OFF")
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

    # Migration de rattrapage : sur une installation déjà existante (avant l'introduction
    # du multi-établissement), le tout premier compte admin devient rétroactivement
    # super-administrateur — c'est lui qui gérait déjà seul l'installation jusqu'ici.
    if 'users' in tables_existantes:
        deja_super_admin = db.execute("SELECT 1 FROM users WHERE est_super_admin=1").fetchone()
        if not deja_super_admin:
            premier_admin = db.execute(
                "SELECT id FROM users WHERE role='admin' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if premier_admin:
                db.execute("UPDATE users SET est_super_admin=1 WHERE id=?", (premier_admin['id'],))
                db.commit()
                print(f"[migration] Compte admin #{premier_admin['id']} promu super-administrateur")

    # Migration de rattrapage : toute école déjà inscrite AVANT l'introduction de la
    # confirmation par e-mail est automatiquement considérée comme confirmée — sans
    # quoi des écoles déjà actives se retrouveraient bloquées du jour au lendemain.
    if 'ecoles' in tables_existantes:
        db.execute("UPDATE ecoles SET email_confirme=1 WHERE email_confirme=0 AND jeton_confirmation IS NULL")
        db.commit()

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
          ecole_id     INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
          username     TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          full_name    TEXT NOT NULL,
          role         TEXT NOT NULL CHECK(role IN ('admin','directeur','comptable','enseignant','secretaire','charge_communication','directeur_etudes','parent')),
          email        TEXT,
          telephone    TEXT,
          civilite     TEXT,
          active       INTEGER DEFAULT 1,
          created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
          last_login   TEXT,
          UNIQUE(ecole_id, username)
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

    if users_existe and users_existe['sql'] and 'ecole_id' not in users_existe['sql']:
        try:
            print("[migration] Mise à jour de la table utilisateurs (ajout directeur_etudes, parent, ecole_id — fondations multi-établissement)")
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

    # Migration spéciale : settings et sequences passent d'une clé primaire simple
    # à une clé composite (ecole_id, cle) / (ecole_id, nom) — fondations multi-établissement.
    # Même logique auto-réparatrice que pour users ci-dessus.
    for table, nouvelle_creation, ancien_nom_cle in [
        ('settings', "CREATE TABLE settings (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, cle TEXT NOT NULL, valeur TEXT, PRIMARY KEY (ecole_id, cle))", 'cle'),
        ('sequences', "CREATE TABLE sequences (ecole_id INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE, nom TEXT NOT NULL, valeur INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ecole_id, nom))", 'nom'),
    ]:
        table_old = f"{table}_old_migration"
        deja_migree = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        table_old_existe = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_old,)
        ).fetchone()

        if table_old_existe:
            try:
                print(f"[migration] Reprise d'une migration {table} interrompue précédemment...")
                db.execute("PRAGMA legacy_alter_table = ON")
                db.execute("PRAGMA foreign_keys=OFF")
                if not deja_migree:
                    db.execute(nouvelle_creation)
                nb = db.execute(f"SELECT COUNT(*) as n FROM {table}").fetchone()['n']
                if nb == 0:
                    colonnes = [r['name'] for r in db.execute(f"PRAGMA table_info({table_old})").fetchall()]
                    colonnes_str = ",".join(colonnes)
                    db.execute(f"INSERT INTO {table} (ecole_id,{colonnes_str}) SELECT 1,{colonnes_str} FROM {table_old}")
                db.execute(f"DROP TABLE {table_old}")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA legacy_alter_table = OFF")
                db.commit()
                print(f"[migration] Migration {table} réparée et terminée avec succès")
                deja_migree = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            except Exception as e:
                print(f"[migration] Erreur lors de la réparation de la migration {table} : {e}")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA legacy_alter_table = OFF")

        if deja_migree and deja_migree['sql'] and 'ecole_id' not in deja_migree['sql']:
            try:
                print(f"[migration] Ajout du multi-établissement à la table {table}")
                db.execute("PRAGMA legacy_alter_table = ON")
                db.execute("PRAGMA foreign_keys=OFF")
                db.execute(f"ALTER TABLE {table} RENAME TO {table_old}")
                db.execute(nouvelle_creation)
                colonnes = [r['name'] for r in db.execute(f"PRAGMA table_info({table_old})").fetchall()]
                colonnes_str = ",".join(colonnes)
                db.execute(f"INSERT INTO {table} (ecole_id,{colonnes_str}) SELECT 1,{colonnes_str} FROM {table_old}")
                db.execute(f"DROP TABLE {table_old}")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA legacy_alter_table = OFF")
                db.commit()
                print(f"[migration] Table {table} mise à jour avec succès (multi-établissement)")
            except Exception as e:
                print(f"[migration] Erreur lors de la mise à jour de {table} : {e}")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA legacy_alter_table = OFF")

    # Migration spéciale : ajout du statut 'preinscrit' à la contrainte CHECK de eleves
    # (nécessaire pour le point 7 du cahier des charges : préinscription par n'importe qui,
    # validée ensuite par le comptable une fois le paiement effectué).
    # Même logique auto-réparatrice que pour users ci-dessus (voir commentaire détaillé plus haut).
    NOUVEAU_SCHEMA_ELEVES = """
        CREATE TABLE eleves (
          id                TEXT PRIMARY KEY,
          ecole_id          INTEGER NOT NULL DEFAULT 1 REFERENCES ecoles(id) ON DELETE CASCADE,
          matricule         TEXT,
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
          created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(ecole_id, matricule)
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

    # Rattrapage : les paiements de réinscription réglés avant l'introduction de la
    # catégorie dédiée "Frais de réinscription" avaient été enregistrés sous le
    # libellé générique "Frais de scolarité", les rendant invisibles dans la Balance
    # générale sous leur propre ligne. On les retrouve via le versement (qui référence
    # le paiement) et on corrige rétroactivement la catégorie de la transaction liée.
    if {'transactions', 'versements', 'paiements'} <= tables_existantes:
        try:
            a_corriger = db.execute(
                """SELECT t.id as transaction_id FROM transactions t
                   JOIN versements v ON v.eleve_id = t.eleve_id AND v.date_vers = t.date_op AND v.montant = t.montant
                   JOIN paiements p ON p.id = v.paiement_id
                   WHERE p.type_frais = 'reinscription' AND t.categorie = 'Frais de scolarité'"""
            ).fetchall()
            if a_corriger:
                ids = [r['transaction_id'] for r in a_corriger]
                db.executemany("UPDATE transactions SET categorie='Frais de réinscription' WHERE id=?", [(i,) for i in ids])
                db.commit()
                print(f"[migration] {len(ids)} transaction(s) de réinscription reclassée(s) sous 'Frais de réinscription'")
        except Exception as e:
            print(f"[migration] Erreur lors du rattrapage des catégories de réinscription : {e}")

    appliquer_migrations_versionnees()


def _rattacher_a_la_bonne_ecole():
    """Rattrapage : la validation d'une préinscription enregistrait la recette
    correspondante sans préciser l'école — elle tombait donc par erreur dans la
    comptabilité de l'école n°1. Idem pour le lien parent ↔ élève. On rend chaque
    ligne à l'école de l'élève concerné (sans effet si tout est déjà correct)."""
    for table in ('transactions', 'parents_eleves'):
        try:
            cur = db.execute(f"""
                UPDATE {table} SET ecole_id = (SELECT e.ecole_id FROM eleves e WHERE e.id = {table}.eleve_id)
                WHERE ecole_id = 1 AND eleve_id IS NOT NULL
                  AND EXISTS (SELECT 1 FROM eleves e WHERE e.id = {table}.eleve_id AND e.ecole_id <> 1)""")
            if cur.rowcount:
                print(f"[migration] {cur.rowcount} ligne(s) de {table} rattachée(s) à leur véritable école")
            db.commit()
        except Exception as e:
            print(f"[migration] Erreur lors du rattachement des lignes de {table} : {e}")


# Index commençant par ecole_id : chaque écran ne lit que les données de SON école ;
# sans ces index, la base parcourt les données de TOUTES les écoles à chaque
# affichage, ce qui ralentit l'application au fur et à mesure qu'elle grossit.
INDEX_PAR_ECOLE = [
    ('idx_eleves_ecole_classe',       'eleves',        ('ecole_id', 'classe')),
    ('idx_paiements_ecole_eleve',     'paiements',     ('ecole_id', 'eleve_id')),
    ('idx_paiements_ecole_statut',    'paiements',     ('ecole_id', 'statut')),
    ('idx_versements_ecole_paiement', 'versements',    ('ecole_id', 'paiement_id')),
    ('idx_transactions_ecole_date',   'transactions',  ('ecole_id', 'date_op')),
    ('idx_notes_ecole_eleve',         'notes',         ('ecole_id', 'eleve_id')),
    ('idx_absences_ecole_date',       'absences',      ('ecole_id', 'date_abs')),
    ('idx_journal_audit_ecole_date',  'journal_audit', ('ecole_id', 'created_at')),
]


def _creer_index_par_ecole():
    for nom_index, table, colonnes in INDEX_PAR_ECOLE:
        try:
            existantes = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
            if not set(colonnes) <= existantes:
                continue
            db.execute(f"CREATE INDEX IF NOT EXISTS {nom_index} ON {table}({', '.join(colonnes)})")
        except Exception as e:
            print(f"[migration] Index {nom_index} non créé : {e}")
    db.commit()


# --- Migrations versionnées ------------------------------------------------------------
# Les anciennes migrations ci-dessus (colonnes ajoutées, tables reconstruites) vérifient
# l'état de la base à CHAQUE démarrage : elles restent en place, inchangées, et forment la
# « version 0 ». Toute évolution FUTURE de la base s'ajoute ici : une ligne
# (numéro, description, fonction) à la fin de la liste, jamais au milieu. Le numéro
# appliqué est mémorisé dans la base (PRAGMA user_version) : chaque étape ne s'exécute
# qu'UNE fois, dans l'ordre, et une copie de sécurité de la base est faite avant.
def _rattacher_notes_a_l_annee():
    """Les notes enregistrées avant l'introduction de l'année scolaire appartiennent, à ce jour, à l'année
    en cours de leur école (celle du paramètre « annee_scolaire »)."""
    for e in db.execute("SELECT DISTINCT ecole_id FROM notes WHERE annee_scolaire IS NULL").fetchall():
        r = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='annee_scolaire'", (e['ecole_id'],)).fetchone()
        if r and r['valeur']:
            db.execute("UPDATE notes SET annee_scolaire=? WHERE ecole_id=? AND annee_scolaire IS NULL", (r['valeur'], e['ecole_id']))


def _indexer_cles_etrangeres():
    import base_sante
    base_sante.indexer_cles_etrangeres(db)


MIGRATIONS_VERSIONNEES = [
    (1, "Rattacher chaque ligne à l'école de son élève", _rattacher_a_la_bonne_ecole),
    (2, "Index par école sur les grosses tables", _creer_index_par_ecole),
    (3, "Rattacher les notes existantes à l'année scolaire en cours de leur école", _rattacher_notes_a_l_annee),
    (4, "Index sur toutes les colonnes de jointure (école, élève, parent…)", _indexer_cles_etrangeres),
]


def version_base():
    return db.execute("PRAGMA user_version").fetchone()[0]


def _copie_avant_migration(ancienne, nouvelle):
    """Copie cohérente de la base juste avant d'appliquer des migrations (sauf base neuve)."""
    if USE_PG:
        return None      # PostgreSQL : sauvegardes assurées par le service d'hébergement de la base
    try:
        a_des_donnees = db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    except Exception:
        a_des_donnees = None
    if not a_des_donnees:
        return None
    dossier = os.path.join(DATA_DIR, 'sauvegardes')
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"avant-migration-v{ancienne}-vers-v{nouvelle}.db")
    source = sqlite3.connect(DB_PATH, timeout=DELAI_ATTENTE_VERROU_S)
    try:
        cible = sqlite3.connect(chemin)
        try:
            source.backup(cible)
        finally:
            cible.close()
    finally:
        source.close()
    return chemin


def appliquer_migrations_versionnees():
    actuelle = version_base()
    en_attente = sorted((m for m in MIGRATIONS_VERSIONNEES if m[0] > actuelle), key=lambda m: m[0])
    if not en_attente:
        return
    try:
        chemin = _copie_avant_migration(actuelle, en_attente[-1][0])
        if chemin:
            print(f"[migration] Copie de sécurité avant migration : {chemin}", flush=True)
    except Exception as e:
        print(f"[migration] Copie de sécurité impossible ({e}) — migration poursuivie", flush=True)
    for numero, description, fonction in en_attente:
        try:
            fonction()
            db.execute(f"PRAGMA user_version = {int(numero)}")
            db.commit()
            print(f"[migration] v{numero} appliquée : {description}", flush=True)
        except Exception as e:
            db.rollback()
            print(f"[migration] v{numero} ÉCHEC ({description}) : {e} — les suivantes sont reportées "
                  f"au prochain démarrage", flush=True)
            break


MOTS_DE_PASSE_PAR_DEFAUT_PUBLICS = ('Admin@2025!',)


def signaler_mots_de_passe_par_defaut():
    """Comptes administrateurs qui ont encore un mot de passe PUBLIÉ dans le code (ex. celui d'une
    installation ancienne) : ils passent en « mot de passe provisoire » et devront le changer à la
    prochaine connexion. Retourne le nombre de comptes signalés."""
    n = 0
    for u in db.execute("SELECT id, password_hash FROM users WHERE role='admin' AND COALESCE(doit_changer_mdp,0)=0").fetchall():
        if any(check_password_hash(u['password_hash'], m) for m in MOTS_DE_PASSE_PAR_DEFAUT_PUBLICS):
            db.execute("UPDATE users SET doit_changer_mdp=1 WHERE id=?", (u['id'],))
            n += 1
    if n:
        db.commit()
        print(f"[securite] {n} compte(s) administrateur avec le mot de passe par défaut : changement obligatoire à la prochaine connexion.", flush=True)
    return n


def init_db():
    db.executescript(SCHEMA)
    db.commit()

    # École par défaut (id=1) : représente l'établissement existant lors du passage
    # au multi-établissement, ou la première école créée sur une installation neuve.
    if not db.execute("SELECT 1 FROM ecoles WHERE id=1").fetchone():
        db.execute(
            "INSERT INTO ecoles (id, nom, code, statut_licence) VALUES (1, 'École principale', 'ecole-1', 'active')"
        )
        db.commit()

    run_migrations()
    try:
        import base_sante
        base_sante.optimiser(db)
    except Exception as e:
        print(f"[base] optimisation ignorée : {e}")

    # Licence (installation locale hors-ligne) : enregistre la date de première
    # utilisation, une seule fois — point de départ de la période d'essai de 14 jours.
    from licence import initialiser_date_installation
    initialiser_date_installation(db)

    # Paramètres par défaut
    defaults = {
        'ecole_nom': 'MY-ECOLE',
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

    # Compte admin initial — devient automatiquement super-administrateur (supervision
    # de toutes les écoles clientes), puisqu'il s'agit du tout premier compte créé sur
    # cette installation.
    count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    if count == 0:
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD', 'Admin@2025!')
        pwd_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (ecole_id,username,password_hash,full_name,role,email,est_super_admin,doit_changer_mdp) "
            "VALUES (?,?,?,?,?,?,?,?)",
            # mot de passe par défaut connu de tous (publié dans le code) : changement obligatoire à la 1re connexion
            (1, username, pwd_hash, 'Administrateur Principal', 'admin', 'admin@ecole.com', 1,
             0 if os.environ.get('ADMIN_PASSWORD') else 1),
        )
        db.commit()
        print("\n" + "=" * 48)
        print("  Compte administrateur créé")
        print(f"  Identifiant  : {username}")
        print(f"  Mot de passe : {password}")
        print("  Changez ce mot de passe rapidement !")
        print("=" * 48 + "\n")

    signaler_mots_de_passe_par_defaut()


def ecole_id_depuis_code(code_ecole, defaut=1):
    """Résout l'ecole_id à partir d'un code établissement (utilisé par les routes
    publiques du site vitrine : articles, préinscription, candidature...). Si le code
    est absent ou inconnu, retombe sur l'école n°1 (rétro-compatibilité mono-école)."""
    if not code_ecole:
        return defaut
    row = db.execute("SELECT id FROM ecoles WHERE code=?", (code_ecole,)).fetchone()
    return row['id'] if row else defaut


def get_settings(ecole_id=1):
    rows = db.execute("SELECT cle, valeur FROM settings WHERE ecole_id=?", (ecole_id,)).fetchall()
    return {r['cle']: r['valeur'] for r in rows}


def next_sequence(nom, prefixe, largeur, ecole_id=1):
    """Incrémente atomiquement et retourne le prochain identifiant séquentiel
    (ex: 'M000123'). Toujours utilisé à l'intérieur de matricule_lock par les
    appelants, pour une garantie totale d'unicité même sous forte charge
    concurrente (contrairement à un calcul basé sur le dernier enregistrement créé).
    Chaque école a sa propre numérotation, indépendante des autres."""
    # Incrément ATOMIQUE réalisé par la base elle-même (valeur = valeur + 1) : même
    # si deux requêtes arrivent au même instant, chacune obtient un numéro différent.
    # (L'ancienne version lisait la valeur puis la réécrivait : sans file d'attente,
    # deux reçus pouvaient recevoir le même numéro.)
    db.execute(
        "INSERT INTO sequences (ecole_id, nom, valeur) VALUES (?,?,1) "
        "ON CONFLICT(ecole_id, nom) DO UPDATE SET valeur = sequences.valeur + 1",
        (ecole_id, nom),
    )
    valeur = db.execute("SELECT valeur FROM sequences WHERE ecole_id=? AND nom=?", (ecole_id, nom)).fetchone()['valeur']
    db.commit()
    return prefixe + str(valeur).zfill(largeur)


def next_matricule_personnel(ecole_id=1):
    """Génère le prochain matricule personnel (P0001, P0002…), partagé par toutes les
    routes qui créent une fiche personnel (création directe, approbation de candidature)."""
    return next_sequence('matricule_personnel', 'P', 4, ecole_id=ecole_id)


def next_numero_recu(ecole_id=1):
    """Génère le prochain numéro de reçu/facture, au format REC-2026-00001 —
    séquentiel et remis à zéro chaque année civile (convention comptable standard).
    Remplace les anciens numéros improvisés (horodatage aléatoire côté client, ou
    identifiant technique du versement) qui n'étaient ni séquentiels ni stables :
    imprimer deux fois le même reçu pouvait même lui donner un numéro différent
    à chaque fois, ce qu'aucun document comptable/légal ne doit jamais faire."""
    from datetime import datetime
    annee = datetime.now().year
    return next_sequence(f'numero_recu_{annee}', f'REC-{annee}-', 5, ecole_id=ecole_id)


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
        ecole_id = user.get('ecole_id', 1) if user else 1
        det = _json.dumps(details, ensure_ascii=False, default=str) if details is not None else None
        db.execute(
            "INSERT INTO journal_audit (id,ecole_id,user_id,user_nom,action,entite,entite_id,details) VALUES (?,?,?,?,?,?,?,?)",
            (gen_id('jrn'), ecole_id, uid, uname, action, entite, entite_id, det),
        )
        db.commit()
    except Exception as e:
        print(f"[journal_audit] Erreur d'enregistrement (non bloquante): {e}")
