"""
Gestion Scolaire — Serveur Python (Flask)
Remplace la version Node.js pour éviter les problèmes de compilation native
(better-sqlite3) rencontrés lors de l'installation sur certains postes Windows.
"""
import os
import sys
import traceback
import webbrowser
import threading
from datetime import datetime
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Compatibilité PyInstaller : lorsque l'application est empaquetée en exécutable unique,
# les fichiers statiques (public/) sont extraits dans un dossier temporaire (sys._MEIPASS),
# tandis que les données persistantes (base de données, journaux) doivent rester à côté
# du véritable exécutable pour survivre aux redémarrages et aux mises à jour.
if getattr(sys, 'frozen', False):
    RESOURCES_DIR = getattr(sys, '_MEIPASS', BASE_DIR)
    PERSIST_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    RESOURCES_DIR = BASE_DIR
    PERSIST_DIR = BASE_DIR
PUBLIC_DIR = os.path.join(RESOURCES_DIR, 'public')
UPLOAD_DIR = os.environ.get('GS_UPLOADS_DIR') or os.path.join(PERSIST_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Répertoire de journaux d'erreurs — même emplacement que les données (portable/desktop) —
# pour pouvoir retrouver et transmettre facilement le détail d'une erreur 500.
LOGS_DIR = os.environ.get('GS_LOGS_DIR') or os.path.join(PERSIST_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)
ERROR_LOG_PATH = os.path.join(LOGS_DIR, 'erreurs.log')


def create_app():
    # Initialiser la base de données (doit être fait avant d'importer les routes,
    # car elles importent `db` déjà connecté depuis database.py)
    import database
    database.init_db()

    app = Flask(__name__, static_folder=None)
    app.config['UPLOAD_DIR'] = UPLOAD_DIR
    app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024  # 60 Mo max (photos + courtes vidéos)
    CORS(app)

    # ── Fichiers statiques (équivalent express.static) ──
    @app.route('/uploads/<path:filename>')
    def serve_uploads(filename):
        return send_from_directory(UPLOAD_DIR, filename)

    @app.route('/css/<path:filename>')
    def serve_css(filename):
        return send_from_directory(os.path.join(PUBLIC_DIR, 'css'), filename)

    @app.route('/js/<path:filename>')
    def serve_js(filename):
        return send_from_directory(os.path.join(PUBLIC_DIR, 'js'), filename)

    # ── Page publique de candidature enseignant (accessible sans connexion) ──
    @app.route('/postuler.html')
    @app.route('/postuler')
    @app.route('/ecole/<code_ecole>/postuler')
    def serve_postuler(code_ecole=None):
        return send_from_directory(PUBLIC_DIR, 'postuler.html')

    # ── Site vitrine public de l'école (accessible sans connexion) ──
    @app.route('/vitrine.html')
    @app.route('/vitrine')
    @app.route('/ecole/<code_ecole>')
    @app.route('/ecole/<code_ecole>/')
    @app.route('/ecole/<code_ecole>/vitrine')
    def serve_vitrine(code_ecole=None):
        return send_from_directory(PUBLIC_DIR, 'vitrine.html')

    # ── Page publique de pré-inscription élève (accessible sans connexion) ──
    @app.route('/preinscription.html')
    @app.route('/preinscription')
    @app.route('/ecole/<code_ecole>/preinscription')
    def serve_preinscription(code_ecole=None):
        return send_from_directory(PUBLIC_DIR, 'preinscription.html')

    # ── Espace parents (connexion propre au compte parent, requise dans la page) ──
    @app.route('/espace-parents.html')
    @app.route('/espace-parents')
    @app.route('/ecole/<code_ecole>/espace-parents')
    def serve_espace_parents(code_ecole=None):
        return send_from_directory(PUBLIC_DIR, 'espace-parents.html')

    # ── Inscription d'une nouvelle école cliente (accessible sans connexion) ──
    @app.route('/inscription-ecole.html')
    @app.route('/inscription-ecole')
    def serve_inscription_ecole():
        return send_from_directory(PUBLIC_DIR, 'inscription-ecole.html')

    # ── Annuaire public des écoles clientes (page d'accueil générale) ──
    @app.route('/nos-ecoles.html')
    @app.route('/nos-ecoles')
    def serve_nos_ecoles():
        return send_from_directory(PUBLIC_DIR, 'nos-ecoles.html')

    # ── Santé (publique) ──
    @app.route('/api/health')
    def health():
        import datetime
        return jsonify({'ok': True, 'ts': datetime.datetime.now(datetime.timezone.utc).isoformat()})

    # ── Blueprints (routes API) ──
    from routes.auth_routes import bp as auth_bp
    from routes.users_routes import bp as users_bp
    from routes.settings_routes import bp as settings_bp
    from routes.eleves_routes import bp as eleves_bp
    from routes.scolarite_routes import bp as scolarite_bp
    from routes.finances_routes import bp as finances_bp
    from routes.communication_routes import bp as communication_bp
    from routes.classes_routes import bp as classes_bp
    from routes.journal_routes import bp as journal_bp
    from routes.articles_routes import bp as articles_bp
    from routes.eleve_du_mois_routes import bp as eleve_du_mois_bp
    from routes.revision_routes import bp as revision_bp
    from routes.salles_routes import bp as salles_bp
    from routes.paie_routes import bp as paie_bp
    from routes.candidatures_routes import bp as candidatures_bp
    from routes.parent_routes import bp as parent_bp
    from routes.ecoles_routes import bp as ecoles_bp
    from routes.licence_routes import bp as licence_bp
    from routes.fournisseurs_routes import bp as fournisseurs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(eleves_bp)
    app.register_blueprint(scolarite_bp)
    app.register_blueprint(finances_bp)
    app.register_blueprint(communication_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(journal_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(eleve_du_mois_bp)
    app.register_blueprint(revision_bp)
    app.register_blueprint(salles_bp)
    app.register_blueprint(paie_bp)
    app.register_blueprint(candidatures_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(ecoles_bp)
    app.register_blueprint(licence_bp)
    app.register_blueprint(fournisseurs_bp)

    # ── Page principale + SPA fallback ──
    @app.route('/')
    def index():
        return send_from_directory(PUBLIC_DIR, 'index.html')

    @app.errorhandler(404)
    def not_found(e):
        from flask import request
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Endpoint introuvable'}), 404
        return send_from_directory(PUBLIC_DIR, 'index.html')

    # ── Erreurs ──
    @app.errorhandler(500)
    def server_error(e):
        from flask import request
        # Récupère la VRAIE exception d'origine (Flask enveloppe souvent l'erreur
        # réelle dans l'objet HTTPException générique) pour ne rien perdre du détail.
        original = getattr(e, 'original_exception', None) or e
        trace_txt = traceback.format_exc()
        horodatage = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entete = f"\n{'='*70}\n[{horodatage}] ERREUR 500 sur {request.method} {request.path}\n{'='*70}\n"
        message_complet = entete + trace_txt

        # 1) Toujours affiché dans la console (fenêtre noire) pour un diagnostic immédiat
        print(message_complet, file=sys.stderr)

        # 2) Toujours conservé dans un fichier, pour pouvoir le retrouver et le transmettre au support
        try:
            with open(ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(message_complet)
        except Exception:
            pass  # ne jamais faire planter la réponse d'erreur à cause de la journalisation elle-même

        return jsonify({
            'error': str(original) or 'Erreur serveur interne',
            'detail': "Le détail complet de cette erreur a été enregistré dans le fichier logs/erreurs.log — "
                      "merci de le transmettre au support technique (Actif System Groupe) si le problème persiste.",
        }), 500

    # ── Filet de sécurité global : capture même les exceptions qui ne passeraient pas
    # par errorhandler(500) (comportement qui varie selon les versions de Flask/Werkzeug) ──
    @app.errorhandler(Exception)
    def handle_uncaught_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        from flask import request
        trace_txt = traceback.format_exc()
        horodatage = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message_complet = f"\n{'='*70}\n[{horodatage}] EXCEPTION NON GÉRÉE sur {request.method} {request.path}\n{'='*70}\n{trace_txt}"
        print(message_complet, file=sys.stderr)
        try:
            with open(ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(message_complet)
        except Exception:
            pass
        return jsonify({
            'error': str(e) or 'Erreur serveur interne',
            'detail': "Le détail complet de cette erreur a été enregistré dans le fichier logs/erreurs.log.",
        }), 500

    # ── Logging simple des requêtes ──
    @app.after_request
    def log_request(response):
        from flask import request
        print(f"{request.method} {request.path} → {response.status_code}")
        return response

    return app


def open_browser(url, delay=1.5):
    def _open():
        import time
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


# Créée au niveau du module (et non uniquement dans `if __name__ == '__main__'`)
# pour qu'un serveur de production comme gunicorn puisse l'importer directement
# via `gunicorn app:app`, en plus du mode développement/desktop habituel.
app = create_app()

if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 3000))
    HOST = os.environ.get('HOST', '0.0.0.0')

    print(f"\n🎓 Gestion Scolaire — Serveur sur http://localhost:{PORT}\n")

    # Ouvre le navigateur automatiquement en mode desktop (GS_AUTO_OPEN=1),
    # ou automatiquement aussi lorsqu'il s'agit d'un exécutable autonome (PyInstaller),
    # puisque dans ce cas il n'y a pas de script de lancement séparé pour le faire.
    if os.environ.get('GS_AUTO_OPEN') == '1' or getattr(sys, 'frozen', False):
        open_browser(f"http://127.0.0.1:{PORT}")

    app.run(host=HOST, port=PORT, debug=False, threaded=True)
