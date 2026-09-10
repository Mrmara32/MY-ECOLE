// Base de données locale du navigateur (IndexedDB) pour le mode hors-ligne.
//
// Deux magasins de données :
//  - "outbox"        : file d'attente des actions faites hors-ligne (inscrire un
//                      élève, encaisser un versement...), envoyées au serveur dès
//                      que la connexion revient, dans l'ordre où elles ont été créées.
//  - "cache_eleves"  : copie locale de la liste des élèves, pour pouvoir la
//                      consulter même sans connexion. Rafraîchie à chaque fois
//                      qu'elle est chargée avec succès en ligne.
//
// Toutes les fonctions renvoient des Promises pour rester agréables à utiliser
// depuis le reste de l'application (qui est déjà écrite avec async/await).

const OFFLINE_DB_NOM = 'my_ecole_offline';
const OFFLINE_DB_VERSION = 1;

function ouvrirBase() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(OFFLINE_DB_NOM, OFFLINE_DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('outbox')) {
        const store = db.createObjectStore('outbox', { keyPath: 'client_op_id' });
        store.createIndex('par_date', 'cree_le');
      }
      if (!db.objectStoreNames.contains('cache_eleves')) {
        db.createObjectStore('cache_eleves', { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function genererClientOpId() {
  // crypto.randomUUID() est disponible sur tous les navigateurs modernes ;
  // repli simple si absent (ancien navigateur ou contexte non securise).
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return 'op_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
}

const offlineDB = {
  genererClientOpId,

  // ───────────── File d'attente (outbox) ─────────────

  // type : ex. 'creation_eleve', 'creation_paiement', 'versement_paiement'
  // endpoint / method : ce qu'il faudra rejouer contre l'API a la reconnexion
  // payload : le corps de la requete (contiendra deja client_op_id)
  async ajouterAFileAttente(type, endpoint, method, payload) {
    const db = await ouvrirBase();
    const operation = {
      client_op_id: payload.client_op_id,
      type, endpoint, method, payload,
      cree_le: new Date().toISOString(),
      statut: 'attente', // 'attente' | 'erreur'
      derniere_erreur: null,
    };
    return new Promise((resolve, reject) => {
      const tx = db.transaction('outbox', 'readwrite');
      tx.objectStore('outbox').put(operation);
      tx.oncomplete = () => resolve(operation);
      tx.onerror = () => reject(tx.error);
    });
  },

  async listerFileAttente() {
    const db = await ouvrirBase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('outbox', 'readonly');
      const req = tx.objectStore('outbox').index('par_date').getAll();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  },

  async compterFileAttente() {
    const liste = await this.listerFileAttente();
    return liste.length;
  },

  async retirerDeFileAttente(clientOpId) {
    const db = await ouvrirBase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('outbox', 'readwrite');
      tx.objectStore('outbox').delete(clientOpId);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },

  async marquerEnErreur(clientOpId, messageErreur) {
    const db = await ouvrirBase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('outbox', 'readwrite');
      const store = tx.objectStore('outbox');
      const req = store.get(clientOpId);
      req.onsuccess = () => {
        const op = req.result;
        if (op) { op.statut = 'erreur'; op.derniere_erreur = messageErreur; store.put(op); }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },

  // ───────────── Cache de consultation (élèves) ─────────────

  async remplacerCacheEleves(liste) {
    const db = await ouvrirBase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('cache_eleves', 'readwrite');
      const store = tx.objectStore('cache_eleves');
      store.clear();
      liste.forEach((e) => store.put(e));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },

  async ajouterEleveAuCache(eleve) {
    const db = await ouvrirBase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('cache_eleves', 'readwrite');
      tx.objectStore('cache_eleves').put(eleve);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },

  async listerElevesEnCache() {
    const db = await ouvrirBase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('cache_eleves', 'readonly');
      const req = tx.objectStore('cache_eleves').getAll();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  },
};

window.offlineDB = offlineDB;
