"""
Réglages du serveur de production (gunicorn), lus automatiquement au démarrage
par la commande de Render « gunicorn app:app » — rien à changer sur Render.

- UN SEUL processus : la base SQLite, le verrou des matricules et les sauvegardes
  automatiques supposent un processus unique (le disque persistant de Render
  n'autorise de toute façon qu'une seule instance du service).
- PLUSIEURS threads : plusieurs requêtes sont traitées en même temps. Avant, un
  envoi d'e-mail ou un export un peu long bloquait toute l'école pendant ce temps.
  Les consultations (pages, listes, tableaux de bord) se font en parallèle ; les
  enregistrements restent traités un par un (voir database.verrou_ecritures).
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# SQLite : un seul processus. PostgreSQL : GUNICORN_WORKERS peut être augmenté (les écritures restent
# sérialisées entre processus par un verrou PostgreSQL, voir database.prendre_verrou_ecritures_global).
workers = int(os.environ.get('GUNICORN_WORKERS', '1')) if os.environ.get('DATABASE_URL') else 1
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', '8'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))  # exports et e-mails lents
graceful_timeout = 30
keepalive = 5
