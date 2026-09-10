// Moteur de synchronisation hors-ligne.
//
// Ecoute les changements de connectivite du navigateur et, des que la connexion
// revient, envoie au serveur -- dans l'ordre -- chaque action mise en attente
// pendant la coupure. Chaque action porte deja son "client_op_id" (genere au
// moment ou l'utilisateur l'a faite, hors-ligne) : le serveur l'utilise pour ne
// jamais rejouer deux fois la meme action (voir offline_sync.py cote serveur).

const gsSync = {
  enSynchronisation: false,
  ecouteurs: [],

  // Permet a l'interface (barre superieure) de reagir aux changements
  // d'etat : connectivite retrouvee/perdue, nombre d'operations en attente,
  // debut/fin de synchronisation.
  surChangement(fn) { this.ecouteurs.push(fn); },
  _notifier(etat) { this.ecouteurs.forEach((fn) => { try { fn(etat); } catch (_) {} }); },

  async etatActuel() {
    return {
      enLigne: navigator.onLine,
      enAttente: await offlineDB.compterFileAttente(),
      enSynchronisation: this.enSynchronisation,
    };
  },

  async _rafraichirEtat() {
    this._notifier(await this.etatActuel());
  },

  // Met une action en attente puis tente une synchronisation immediate si la
  // connexion est presente (cas frequent : la coupure est tres courte, ou
  // navigator.onLine se trompe -- on verifie donc reellement en tentant l'envoi).
  async mettreEnAttente(type, endpoint, method, payload) {
    payload.client_op_id = payload.client_op_id || offlineDB.genererClientOpId();
    const operation = await offlineDB.ajouterAFileAttente(type, endpoint, method, payload);
    await this._rafraichirEtat();
    this.synchroniser(); // tentative immediate, sans bloquer l'appelant
    return operation;
  },

  // Envoie une a une les operations en attente, dans l'ordre. S'arrete des
  // qu'une operation echoue pour une raison reseau (probablement toujours hors-
  // ligne) mais continue en cas d'erreur applicative (ex: donnee invalide) pour
  // ne pas bloquer indefiniment les operations suivantes sur une seule erreur.
  async synchroniser() {
    if (this.enSynchronisation) return;
    this.enSynchronisation = true;
    await this._rafraichirEtat();

    try {
      const file = await offlineDB.listerFileAttente();
      for (const operation of file) {
        try {
          await apiFetch(operation.endpoint, { method: operation.method, body: operation.payload });
          await offlineDB.retirerDeFileAttente(operation.client_op_id);
          this._notifier({ ...(await this.etatActuel()), derniereSyncReussie: operation });
        } catch (erreur) {
          const probableHorsLigne = !navigator.onLine || erreur.message.includes('Failed to fetch') || erreur.message.includes('NetworkError');
          if (probableHorsLigne) {
            break; // on retentera au prochain passage ; inutile d'essayer les suivantes maintenant
          }
          // Erreur applicative (ex: validation refusee par le serveur) : on la
          // signale mais on continue avec les operations suivantes, pour ne pas
          // bloquer toute la file a cause d'une seule action problematique.
          await offlineDB.marquerEnErreur(operation.client_op_id, erreur.message);
        }
      }
    } finally {
      this.enSynchronisation = false;
      await this._rafraichirEtat();
    }
  },

  demarrer() {
    window.addEventListener('online', () => this.synchroniser());
    window.addEventListener('offline', () => this._rafraichirEtat());
    // Synchronisation periodique de securite (au cas ou l'evenement 'online'
    // ne se declencherait pas de facon fiable sur certains appareils/navigateurs).
    setInterval(() => { if (navigator.onLine) this.synchroniser(); }, 30000);
    this.synchroniser();
  },
};

window.gsSync = gsSync;
