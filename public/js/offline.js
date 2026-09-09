/* ============================================================
   MODE HORS LIGNE — cache de lecture + file d'attente de synchronisation
   ============================================================
   Principe :
   - Les réponses GET des endpoints "consultables hors ligne" (liste définie
     dans ENDPOINTS_CACHABLES) sont automatiquement sauvegardées dans IndexedDB
     à chaque succès réseau, pour pouvoir être relues si la connexion tombe.
   - Les requêtes d'écriture (POST/PUT/DELETE) qui échouent par absence de
     réseau sont placées dans une file d'attente (sync_queue) plutôt que de
     faire planter l'écran. Une mise à jour "optimiste" du cache local est
     appliquée immédiatement pour que l'utilisateur voie son changement tout
     de suite (ex : une absence marquée hors ligne apparaît aussitôt dans la
     liste), avant même la synchronisation réelle.
   - Dès que la connexion revient (événement 'online', ou vérification
     périodique), la file est rejouée dans l'ordre contre le vrai serveur.
   Ce fichier ne dépend de rien d'autre ; api.js l'utilise comme filet de
   sécurité quand fetch() échoue pour cause de réseau. */

const OFFLINE_DB_NAME = 'my_ecole_offline';
const OFFLINE_DB_VERSION = 1;
const STORE_CACHE = 'cache_lecture';
const STORE_QUEUE = 'file_attente';

// Endpoints dont la dernière réponse GET connue est gardée pour consultation
// hors ligne. Volontairement limité aux données les plus utiles au quotidien
// (pas tout : ça reste un cache, pas une base complète dupliquée).
const ENDPOINTS_CACHABLES = ['/eleves', '/personnel', '/classes', '/salles', '/paiements', '/absences', '/frais', '/settings', '/auth/me'];

let _offlineDbPromise = null;
function _ouvrirDB() {
  if (_offlineDbPromise) return _offlineDbPromise;
  _offlineDbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_CACHE)) db.createObjectStore(STORE_CACHE, { keyPath: 'cle' });
      if (!db.objectStoreNames.contains(STORE_QUEUE)) db.createObjectStore(STORE_QUEUE, { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _offlineDbPromise;
}

async function _store(nom, mode) {
  const db = await _ouvrirDB();
  return db.transaction(nom, mode).objectStore(nom);
}

function _requetePromise(req) {
  return new Promise((resolve, reject) => { req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error); });
}

/* ── Cache de lecture ── */
function _endpointCachable(path) {
  // On ne cache que le chemin de base (sans query string) parmi la liste autorisée.
  const base = path.split('?')[0];
  return ENDPOINTS_CACHABLES.some(e => base === e || base.startsWith(e + '/'));
}

async function offlineSauverCache(path, data) {
  if (!_endpointCachable(path)) return;
  try {
    const s = await _store(STORE_CACHE, 'readwrite');
    s.put({ cle: path, data, date: Date.now() });
  } catch (e) { console.warn('offlineSauverCache', e); }
}

async function offlineLireCache(path) {
  try {
    const s = await _store(STORE_CACHE, 'readonly');
    const r = await _requetePromise(s.get(path));
    return r ? r.data : undefined;
  } catch (e) { console.warn('offlineLireCache', e); return undefined; }
}

/* Applique fnPatch(donneesActuelles) -> nouvellesDonnees à TOUTES les entrées du
   cache dont la clé commence par basePath (ex: '/absences' correspond aussi à
   '/absences?classe=CM2'). Nécessaire car une même liste peut être mise en cache
   sous plusieurs variantes filtrées — sans ça, une action hors ligne n'apparaîtrait
   pas immédiatement si un filtre était actif au moment de la consultation précédente. */
async function offlinePatcherVariantes(basePath, fnPatch) {
  try {
    const db = await _ouvrirDB();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CACHE, 'readwrite');
      const store = tx.objectStore(STORE_CACHE);
      const curseur = store.openCursor();
      curseur.onsuccess = (ev) => {
        const c = ev.target.result;
        if (!c) { resolve(); return; }
        if (c.value.cle === basePath || c.value.cle.startsWith(basePath + '?') || c.value.cle.startsWith(basePath + '/')) {
          try {
            const nouvelles = fnPatch(c.value.data);
            store.put({ cle: c.value.cle, data: nouvelles, date: Date.now() });
          } catch (e) { console.warn('offlinePatcherVariantes fnPatch', e); }
        }
        c.continue();
      };
      curseur.onerror = () => reject(curseur.error);
    });
  } catch (e) { console.warn('offlinePatcherVariantes', e); }
}

/* ── File d'attente de synchronisation ── */
async function offlineAjouterFile(entree) {
  const s = await _store(STORE_QUEUE, 'readwrite');
  return _requetePromise(s.add({ ...entree, date: Date.now() }));
}

async function offlineListeFile() {
  const s = await _store(STORE_QUEUE, 'readonly');
  return _requetePromise(s.getAll());
}

async function offlineRetirerFile(id) {
  const s = await _store(STORE_QUEUE, 'readwrite');
  return _requetePromise(s.delete(id));
}

async function offlineCompteFile() {
  const liste = await offlineListeFile();
  return liste.length;
}

/* ── Génération d'identifiants temporaires côté client ──
   Utilisé pour qu'une création faite hors ligne (ex: nouvelle absence) ait
   un identifiant utilisable immédiatement dans l'interface, avant que le
   serveur n'assigne le vrai identifiant lors de la synchronisation. */
function offlineIdTemporaire() {
  return 'tmp_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

/* ── État réseau + indicateur visuel ── */
let _enLigne = navigator.onLine;
const _ecouteursEtat = [];
function offlineEcouterEtat(fn) { _ecouteursEtat.push(fn); }
function _notifierEtat() { _ecouteursEtat.forEach(fn => { try { fn(_enLigne); } catch (_) {} }); }

async function offlineMajIndicateur() {
  const n = await offlineCompteFile();
  const el = document.getElementById('offline-indicateur');
  if (!el) return;
  if (_enLigne && n === 0) {
    el.style.display = 'none';
    el.onclick = null;
  } else {
    el.style.display = 'flex';
    el.className = 'offline-indicateur ' + (_enLigne ? 'sync' : 'hors-ligne');
    el.style.cursor = _enLigne && n ? 'pointer' : 'default';
    el.innerHTML = _enLigne
      ? `⏳ Synchronisation en cours… (${n} en attente — cliquez pour relancer)`
      : `🔴 Hors ligne${n ? ` — ${n} modification(s) en attente de synchronisation` : ''}`;
    el.onclick = _enLigne && n ? () => offlineSynchroniser() : null;
  }
}

window.addEventListener('online', async () => {
  _enLigne = true;
  toast('Connexion rétablie — synchronisation en cours…', 'info');
  await offlineMajIndicateur();
  _notifierEtat();
  await offlineSynchroniser();
});
window.addEventListener('offline', () => {
  _enLigne = false;
  toast('Connexion perdue — vos actions seront synchronisées automatiquement au retour du réseau.', 'warning');
  offlineMajIndicateur();
  _notifierEtat();
});

/* ── Rejeu de la file d'attente ── */
let _synchronisationEnCours = false;
async function offlineSynchroniser() {
  if (_synchronisationEnCours || !navigator.onLine) return;
  _synchronisationEnCours = true;
  try {
    const file = await offlineListeFile();
    file.sort((a, b) => a.date - b.date);
    let succes = 0, echecs = 0;
    for (const entree of file) {
      try {
        const init = {
          method: entree.method,
          headers: { 'Content-Type': 'application/json', ...(_token ? { Authorization: 'Bearer ' + _token } : {}) },
        };
        if (entree.body !== undefined) init.body = entree.body;
        const res = await fetch(API_BASE + entree.path, init);
        if (res.ok) {
          await offlineRetirerFile(entree.id);
          succes++;
        } else {
          // Erreur métier (ex: doublon, validation) : on retire de la file pour ne
          // pas boucler indéfiniment, et on prévient l'utilisateur pour action manuelle.
          const data = await res.json().catch(() => ({}));
          await offlineRetirerFile(entree.id);
          echecs++;
          toast(`Une action hors ligne (${entree.description || entree.path}) n'a pas pu être synchronisée : ${data.error || 'erreur serveur'}`, 'error');
        }
      } catch (e) {
        // Toujours pas de réseau en réalité (faux positif de l'événement 'online') : on
        // arrête là, on réessaiera au prochain événement 'online' ou à la prochaine action.
        break;
      }
      await offlineMajIndicateur();
    }
    if (succes > 0) toast(`✅ ${succes} action(s) synchronisée(s) avec succès`, 'success');
  } finally {
    _synchronisationEnCours = false;
    offlineMajIndicateur();
  }
}
window.offlineSynchroniser = offlineSynchroniser;

/* Vérification périodique en complément de l'événement 'online' (certains
   navigateurs/réseaux ne déclenchent pas l'événement de façon fiable). */
setInterval(() => { if (navigator.onLine) offlineSynchroniser(); }, 30000);

document.addEventListener('DOMContentLoaded', offlineMajIndicateur);

/* ── Enregistrement du Service Worker (mise en cache de l'application elle-même,
   pour qu'elle se charge même sans aucune connexion) ── */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((e) => console.warn('Service Worker non enregistré :', e));
  });
}
