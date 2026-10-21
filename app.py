"""
MY-ECOLE — Serveur Python (Flask)
Remplace la version Node.js pour éviter les problèmes de compilation native
(better-sqlite3) rencontrés lors de l'installation sur certains postes Windows.
"""
import os
import sys
import hashlib
import secrets
import traceback
import webbrowser
import threading
from datetime import datetime
from flask import Flask, Response, jsonify, send_from_directory
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


def calculer_version_interface():
    """Empreinte courte de tous les fichiers de l'interface (public/). Elle change
    toute seule dès qu'un fichier de l'interface est modifié : c'est elle qui permet
    aux navigateurs de savoir qu'une nouvelle version a été déployée (voir sw.js)."""
    empreinte = hashlib.sha1()
    for dossier, sous_dossiers, fichiers in os.walk(PUBLIC_DIR):
        sous_dossiers.sort()
        for nom in sorted(fichiers):
            chemin = os.path.join(dossier, nom)
            empreinte.update(os.path.relpath(chemin, PUBLIC_DIR).replace(os.sep, '/').encode('utf-8'))
            with open(chemin, 'rb') as f:
                empreinte.update(f.read())
    return empreinte.hexdigest()[:10]


def diagnostic_stockage(emplacements):
    """Affiche au démarrage (journaux Render / fenêtre noire) où sont réellement rangées
    les données. Sur Render, seul le disque persistant survit aux redéploiements : un
    dossier resté sur le disque système de l'application est EFFACÉ à chaque mise à
    jour — d'où l'avertissement explicite si c'est le cas."""
    sur_render = bool(os.environ.get('RENDER'))
    try:
        disque_application = os.stat(BASE_DIR).st_dev
    except OSError:
        disque_application = None
    for libelle, chemin, variable in emplacements:
        persistant = None
        if sur_render and disque_application is not None:
            try:
                persistant = os.stat(chemin).st_dev != disque_application
            except OSError:
                persistant = False
        if persistant is False:
            print(f"[stockage] ⚠️  {libelle} : {chemin} — NON PERSISTANT (effacé à chaque déploiement). "
                  f"Définir la variable d'environnement {variable} vers le disque Render (/var/data/...).", flush=True)
        else:
            print(f"[stockage] {libelle} : {chemin}" + ("  (disque persistant ✔)" if persistant else ""), flush=True)


def _reference_erreur():
    """Code court à communiquer au support : il figure aussi dans les journaux,
    ce qui permet de retrouver immédiatement le détail technique de l'erreur."""
    return f"ERR-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2).upper()}"


def _journaliser_erreur(titre, reference, methode, chemin):
    horodatage = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message_complet = (f"\n{'='*70}\n[{horodatage}] {titre} {reference} sur {methode} {chemin}\n{'='*70}\n"
                       f"{traceback.format_exc()}")
    # 1) Toujours affiché dans la console (journaux Render / fenêtre noire)
    print(message_complet, file=sys.stderr, flush=True)
    # 2) Toujours conservé dans un fichier, pour pouvoir le retrouver et le transmettre au support
    try:
        with open(ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(message_complet)
    except Exception:
        pass  # ne jamais faire planter la réponse d'erreur à cause de la journalisation elle-même


def _reponse_erreur_interne(reference):
    detail = f"Si le problème persiste, communiquez ce code au support technique (Actif System Groupe) : {reference}"
    if not os.environ.get('RENDER'):
        # Version installée sur un poste : le fichier de journal est accessible sur place.
        detail += " — le détail complet est enregistré dans le fichier logs/erreurs.log."
    return jsonify({
        'error': "Une erreur inattendue s'est produite : l'opération n'a pas pu aboutir.",
        'detail': detail,
        'reference': reference,
    }), 500


def create_app():
    # Initialiser la base de données (doit être fait avant d'importer les routes,
    # car elles importent `db` depuis database.py)
    import database
    from flask import request
    database.init_db()
    import auth
    if database.USE_PG:
        import pg_migration
        pg_migration.migrer_au_demarrage()

    import sauvegarde
    diagnostic_stockage([
        ('Base de données', database.DATA_DIR, 'GS_DATA_DIR'),
        ('Fichiers téléversés (photos, logos, CV)', UPLOAD_DIR, 'GS_UPLOADS_DIR'),
        ('Journaux d\'erreurs', LOGS_DIR, 'GS_LOGS_DIR'),
        ('Sauvegardes automatiques', sauvegarde.preparer_dossier(), 'GS_DATA_DIR'),
    ])

    app = Flask(__name__, static_folder=None)
    app.config['UPLOAD_DIR'] = UPLOAD_DIR
    app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024  # 60 Mo max (photos + courtes vidéos)
    app.config['APP_VERSION'] = calculer_version_interface()
    print(f"[version] Interface MY-ECOLE : {app.config['APP_VERSION']}", flush=True)
    import securite_http
    CORS(app, origins=securite_http.origines_cors())
    securite_http.installer_en_tetes(app)

    # ── Écritures une par une, lectures en parallèle (voir database.verrou_ecritures) ──
    # Exception : l'envoi d'un relevé par e-mail n'écrit rien en base ; il ne doit
    # pas faire attendre les autres pendant l'échange avec le serveur d'e-mail.
    SANS_VERROU_ECRITURE = {'finances_routes.envoyer_releve_email', 'orange_money_routes.creer_lien',
                            'orange_money_routes.notification', 'orange_money_routes.retour',
                            'orange_money_routes.verifier', 'orange_money_routes.payer_public'}
    ATTENTE_MAX_VERROU_S = 90

    @app.before_request
    def ecritures_une_par_une():
        from flask import request, g
        if request.method in ('GET', 'HEAD', 'OPTIONS') or request.endpoint in SANS_VERROU_ECRITURE:
            return None
        # Le contenu envoyé (formulaire, fichier, photo) est d'abord entièrement reçu :
        # une connexion lente ou un gros fichier ne bloque pas les autres utilisateurs.
        if request.mimetype in ('multipart/form-data', 'application/x-www-form-urlencoded'):
            _ = request.form
        else:
            request.get_data(cache=True)
        if not database.verrou_ecritures.acquire(timeout=ATTENTE_MAX_VERROU_S):
            return jsonify({'error': "Le serveur est très sollicité en ce moment : merci de réessayer dans un instant."}), 503
        g.verrou_ecritures_pris = True
        try:
            database.prendre_verrou_ecritures_global()
        except Exception:
            database.verrou_ecritures.release()
            g.pop('verrou_ecritures_pris', None)
            raise
        return None

    # Fin de chaque requête : valide les écritures restées en attente, ou les annule
    # si la requête a échoué (voir database.terminer_requete), puis libère le verrou.
    @app.teardown_request
    def finaliser_base(erreur=None):
        from flask import g
        try:
            database.terminer_requete(erreur)
        finally:
            if g.pop('verrou_ecritures_pris', False):
                try:
                    database.liberer_verrou_ecritures_global()
                finally:
                    database.verrou_ecritures.release()

    # ── Fichiers statiques (équivalent express.static) ──
    @app.route('/uploads/<path:filename>')
    def serve_uploads(filename):
        # Photos d'élèves, du personnel, justificatifs : jamais sans connexion. Seules restent
        # publiques les images de l'établissement affichées avant la connexion (logo, fond)
        # et les médias des actualités.
        url = '/uploads/' + filename
        public = (database.db.execute("SELECT 1 FROM settings WHERE valeur=? LIMIT 1", (url,)).fetchone()
                  or database.db.execute("SELECT 1 FROM articles_media WHERE url=? LIMIT 1", (url,)).fetchone())
        if not public:
            entete = request.headers.get('Authorization', '')
            jeton = entete[7:] if entete.startswith('Bearer ') else request.cookies.get('gs_media', '')
            payload, erreur = auth.charger_session(jeton) if jeton else (None, 'x')
            if erreur or payload.get('mdp_provisoire'):
                return jsonify({'error': 'Non authentifié'}), 401
        reponse = send_from_directory(UPLOAD_DIR, filename)
        reponse.headers['Cache-Control'] = 'private, max-age=3600' if not public else 'public, max-age=3600'
        return reponse

    @app.after_request
    def poser_cookie_medias(reponse):
        # Les <img> ne peuvent pas envoyer l'en-tête Authorization : le jeton de session est
        # aussi déposé dans un cookie HttpOnly limité à /uploads (jamais lisible par un script).
        entete = request.headers.get('Authorization', '')
        if request.path.startswith('/api/') and entete.startswith('Bearer ') and reponse.status_code < 400 \
                and request.path not in ('/api/auth/logout', '/api/auth/logout-all'):
            jeton = entete[7:]
            if request.cookies.get('gs_media') != jeton:
                reponse.set_cookie('gs_media', jeton, max_age=12 * 3600, path='/uploads',
                                   httponly=True, samesite='Strict', secure=request.is_secure)
        return reponse

    @app.route('/css/<path:filename>')
    def serve_css(filename):
        return send_from_directory(os.path.join(PUBLIC_DIR, 'css'), filename)

    @app.route('/js/<path:filename>')
    def serve_js(filename):
        return send_from_directory(os.path.join(PUBLIC_DIR, 'js'), filename)

    with open(os.path.join(PUBLIC_DIR, 'sw.js'), encoding='utf-8') as f:
        contenu_service_worker = f.read().replace('__VERSION__', app.config['APP_VERSION'])

    @app.route('/sw.js')
    def serve_service_worker():
        # Servi depuis la racine (et non /js/) pour que son "scope" par défaut
        # couvre bien TOUTE l'application (nécessaire pour intercepter /, /css/…
        # et pas seulement les fichiers sous /js/).
        # Le numéro de version de l'interface y est inséré : à chaque déploiement qui
        # modifie l'interface, le navigateur détecte un nouveau Service Worker, remet
        # son cache à jour et l'application propose « Nouvelle version — Recharger ».
        response = Response(contenu_service_worker, mimetype='application/javascript')
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache'
        return response

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

    # ── Page publique « Payer la scolarité » (Orange Money), accessible sans connexion ──
    @app.route('/payer.html')
    @app.route('/payer')
    @app.route('/ecole/<code_ecole>/payer')
    def serve_payer(code_ecole=None):
        return send_from_directory(PUBLIC_DIR, 'payer.html')

    # ── Page publique de pré-inscription élève (accessible sans connexion) ──
    @app.route('/preinscription.html')
    @app.route('/preinscription')
    @app.route('/ecole/<code_ecole>/preinscription')
    def serve_preinscription(code_ecole=None):
        return send_from_directory(PUBLIC_DIR, 'preinscription.html')

    # ── Politique de protection des données personnelles (publique) ──
    @app.route('/confidentialite.html')
    @app.route('/confidentialite')
    def serve_confidentialite():
        return send_from_directory(PUBLIC_DIR, 'confidentialite.html')

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

    # ── Santé (publique) ── utilisée par Render pour vérifier que le service répond
    # (Health Check Path = /api/health) : vérifie aussi que la base de données répond.
    @app.route('/api/health')
    def health():
        from datetime import timezone
        try:
            database.db.execute("SELECT 1").fetchone()
        except Exception:
            return jsonify({'ok': False, 'error': 'Base de données indisponible'}), 503
        return jsonify({'ok': True, 'ts': datetime.now(timezone.utc).isoformat(),
                        'version': app.config['APP_VERSION']})

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
    from routes.logistique_routes import bp as logistique_bp
    from routes.permissions_routes import bp as permissions_bp
    from routes.systeme_routes import bp as systeme_bp
    from routes.resultats_routes import bp as resultats_bp
    from routes.discipline_routes import bp as discipline_bp
    from routes.bibliotheque_routes import bp as bibliotheque_bp
    from routes.examens_routes import bp as examens_bp
    from routes.donnees_personnelles_routes import bp as donnees_perso_bp
    from routes.import_eleves_routes import bp as import_eleves_bp
    from routes.pointage_routes import bp as pointage_bp, bp_zk as pointage_zk_bp
    from routes.whatsapp_routes import bp as whatsapp_bp
    from routes.sms_routes import bp as sms_bp
    from routes.orange_money_routes import bp as orange_money_bp

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
    app.register_blueprint(logistique_bp)
    app.register_blueprint(permissions_bp)
    app.register_blueprint(systeme_bp)
    app.register_blueprint(resultats_bp)
    app.register_blueprint(discipline_bp)
    app.register_blueprint(bibliotheque_bp)
    app.register_blueprint(examens_bp)
    app.register_blueprint(donnees_perso_bp)
    app.register_blueprint(import_eleves_bp)
    app.register_blueprint(pointage_bp)
    app.register_blueprint(pointage_zk_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(sms_bp)
    app.register_blueprint(orange_money_bp)

    # Copie automatique quotidienne de la base (voir sauvegarde.py)
    sauvegarde.demarrer_sauvegardes_automatiques()

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
    # L'utilisateur reçoit un message clair en français et un code de référence ; le
    # détail technique complet (trace) part dans les journaux, retrouvable grâce à ce code.
    # Les écritures en cours sont annulées : une opération interrompue par une erreur
    # n'est jamais enregistrée à moitié.
    @app.errorhandler(500)
    def server_error(e):
        from flask import request
        database.annuler_transaction_en_cours()
        reference = _reference_erreur()
        _journaliser_erreur('ERREUR 500', reference, request.method, request.path)
        return _reponse_erreur_interne(reference)

    # ── Filet de sécurité global : capture même les exceptions qui ne passeraient pas
    # par errorhandler(500) (comportement qui varie selon les versions de Flask/Werkzeug) ──
    @app.errorhandler(Exception)
    def handle_uncaught_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        from flask import request
        database.annuler_transaction_en_cours()
        reference = _reference_erreur()
        _journaliser_erreur('EXCEPTION NON GÉRÉE', reference, request.method, request.path)
        return _reponse_erreur_interne(reference)

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

    print(f"\n🎓 MY-ECOLE — Serveur sur http://localhost:{PORT}\n")

    # Ouvre le navigateur automatiquement en mode desktop (GS_AUTO_OPEN=1),
    # ou automatiquement aussi lorsqu'il s'agit d'un exécutable autonome (PyInstaller),
    # puisque dans ce cas il n'y a pas de script de lancement séparé pour le faire.
    if os.environ.get('GS_AUTO_OPEN') == '1' or getattr(sys, 'frozen', False):
        open_browser(f"http://127.0.0.1:{PORT}")

    app.run(host=HOST, port=PORT, debug=False, threaded=True)
