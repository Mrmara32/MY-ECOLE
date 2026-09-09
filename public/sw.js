/* ============================================================
   SERVICE WORKER — permet à l'application de se CHARGER même sans
   connexion (l'app "shell" : HTML/CSS/JS). La logique de mise en
   cache des données et de synchronisation des actions hors ligne
   est gérée séparément, côté page, dans js/offline.js (IndexedDB) —
   ce fichier ne s'occupe que des fichiers statiques de l'application.
   ============================================================ */

const CACHE_NOM = 'my-ecole-shell-v1';

const FICHIERS_A_PRECACHER = [
  '/', '/index.html', '/css/style.css?v=2',
  '/js/i18n.js', '/js/api.js', '/js/offline.js', '/js/ui.js', '/js/app.js',
  '/js/vendor/qrcode.min.js',
  '/js/pages/dashboard.js', '/js/pages/users.js', '/js/pages/settings.js', '/js/pages/ecoles.js',
  '/js/pages/personnel.js', '/js/pages/eleves.js', '/js/pages/notes.js', '/js/pages/devoirs.js',
  '/js/pages/emploi.js', '/js/pages/seances.js', '/js/pages/absences.js', '/js/pages/paiements.js',
  '/js/pages/cantine.js', '/js/pages/comptabilite.js', '/js/pages/fournisseurs.js', '/js/pages/logistique.js',
  '/js/pages/revision.js', '/js/pages/paie.js', '/js/pages/candidatures.js', '/js/pages/reinscriptions.js',
  '/js/pages/communication.js', '/js/pages/classes.js', '/js/pages/salles.js', '/js/pages/journal.js',
  '/js/pages/actualites.js', '/js/pages/eleveDuMois.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NOM).then((cache) => cache.addAll(FICHIERS_A_PRECACHER)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((noms) => Promise.all(
      noms.filter((n) => n !== CACHE_NOM).map((n) => caches.delete(n))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Les appels /api/ ne sont JAMAIS interceptés ici : js/offline.js (IndexedDB)
  // gère déjà leur repli hors ligne avec une logique propre à chaque donnée
  // (cache de lecture + file d'attente de synchronisation). Le Service Worker
  // ne doit pas s'en mêler, sous peine de conflits entre deux caches différents.
  if (url.pathname.startsWith('/api/')) return;

  // Uniquement les requêtes de même origine (jamais les CDN externes type
  // Google Fonts ou jsDelivr, gérés par le navigateur lui-même).
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request).then((reponseCache) => {
      const fetchPromise = fetch(event.request).then((reponseReseau) => {
        // Recopie systématique dans le cache pour rester à jour dès qu'une
        // vraie connexion est disponible (stale-while-revalidate).
        if (reponseReseau && reponseReseau.status === 200) {
          const copie = reponseReseau.clone();
          caches.open(CACHE_NOM).then((cache) => cache.put(event.request, copie));
        }
        return reponseReseau;
      }).catch(() => reponseCache);
      // Sert immédiatement le cache s'il existe (rapide + fonctionne hors ligne),
      // tout en rafraîchissant en arrière-plan si le réseau est disponible.
      return reponseCache || fetchPromise;
    })
  );
});
