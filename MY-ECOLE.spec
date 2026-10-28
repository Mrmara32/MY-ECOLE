# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de configuration PyInstaller — génère MY-ECOLE.exe, un exécutable
Windows autonome (aucune installation de Python requise sur le poste final).

UTILISATION (sur une machine Windows, PAS depuis Linux/Mac — voir COMMENT-CONSTRUIRE.txt) :
    pip install pyinstaller
    pyinstaller MY-ECOLE.spec

Le résultat se trouve dans dist/MY-ECOLE/MY-ECOLE.exe — copiez tout le dossier
dist/MY-ECOLE/ (pas seulement le .exe) sur le poste final, la base de données
et les fichiers uploadés seront créés à côté de l'exécutable au premier lancement.
"""

bloc_analyse = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('public', 'public'),       # HTML/CSS/JS/images de l'application
        ('.env.example', '.'),      # modèle de configuration (à copier en .env si besoin)
    ],
    hiddenimports=[
        # Les blueprints sont importés dynamiquement à l'intérieur de create_app() ;
        # PyInstaller les détecte normalement tout seul, mais on les liste ici en
        # filet de sécurité pour ne jamais se retrouver avec un module manquant
        # une fois l'exécutable construit (erreur bien plus difficile à diagnostiquer
        # après coup que d'ajouter la ligne ici).
        'routes.auth_routes', 'routes.users_routes', 'routes.settings_routes',
        'routes.eleves_routes', 'routes.scolarite_routes', 'routes.finances_routes',
        'routes.communication_routes', 'routes.classes_routes', 'routes.journal_routes',
        'routes.articles_routes', 'routes.eleve_du_mois_routes', 'routes.revision_routes',
        'routes.salles_routes', 'routes.paie_routes', 'routes.candidatures_routes',
        'routes.parent_routes', 'routes.ecoles_routes', 'routes.licence_routes',
        'routes.fournisseurs_routes', 'routes.logistique_routes', 'routes.permissions_routes',
        'routes.systeme_routes', 'routes.resultats_routes', 'routes.discipline_routes', 'routes.bibliotheque_routes', 'routes.examens_routes', 'routes.donnees_personnelles_routes', 'securite_http', 'retention', 'auth', 'database', 'double_authentification', 'base_sante', 'pg_compat', 'pg_migration', 'psycopg', 'bulletins', 'routes.import_eleves_routes', 'import_eleves',
        'routes.pointage_routes', 'coffre', 'cryptography.fernet',
        'permissions', 'offline_sync', 'licence', 'email_service', 'sauvegarde', 'sauvegarde_externe', 'whatsapp_service', 'sms_service', 'orange_money_service', 'routes.orange_money_routes', 'routes.whatsapp_routes', 'routes.sms_routes', 'routes.aide_routes', 'conditions', 'releve_bancaire', 'contact_parent',
        # Vérification des licences par clé publique (licence.py).
        'cryptography.hazmat.primitives.asymmetric.ed25519',
        'engineio.async_drivers.threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dépendances optionnelles de pandas/openpyxl jamais utilisées par cette
        # application (ni graphiques, ni traitement d'image, ni calcul scientifique
        # avancé) — les exclure réduit la taille de l'exécutable d'environ 150 Mo
        # sans rien retirer de fonctionnel.
        'matplotlib', 'scipy', 'PIL', 'Pillow', 'kiwisolver', 'lxml', 'yaml',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter', 'IPython', 'notebook',
        'pytest', 'sphinx',
        # pandas n'est plus utilisé (relevés bancaires lus par releve_bancaire.py)
        'pandas', 'numpy',
    ],
    noarchive=False,
    optimize=0,
)

bloc_python = PYZ(bloc_analyse.pure)

exe = EXE(
    bloc_python,
    bloc_analyse.scripts,
    [],
    exclude_binaries=True,
    name='MY-ECOLE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # fenêtre noire visible (logs utiles en cas de souci) ; passer à
                     # False une fois l'application bien stabilisée si non désiré.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,      # ex: icon='public/favicon.ico' si une icône est ajoutée au projet
)

collection = COLLECT(
    exe,
    bloc_analyse.binaries,
    bloc_analyse.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MY-ECOLE',
)
