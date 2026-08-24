/* ============================================================
   CLIENT API — toutes les requêtes vers le backend
============================================================ */
const API_BASE = '/api';
let _token = localStorage.getItem('gs_tok') || null;

async function apiFetch(path, opts = {}) {
  const init = {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(_token ? { Authorization: 'Bearer ' + _token } : {}) },
  };
  if (opts.body !== undefined) init.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
  const res = await fetch(API_BASE + path, init);
  if (res.status === 401) { authLogout(); throw new Error('Session expirée'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data.error || `Erreur ${res.status}`) + (data.detail ? '\n\n' + data.detail : ''));
  return data;
}

async function apiUpload(path, formData) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: _token ? { Authorization: 'Bearer ' + _token } : {},
    body: formData,
  });
  if (res.status === 401) { authLogout(); throw new Error('Session expirée'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data.error || 'Erreur upload') + (data.detail ? '\n\n' + data.detail : ''));
  return data;
}

/* ── Auth ── */
async function apiLogin(username, password, codeEcole) {
  const body = { username, password };
  if (codeEcole) body.code_ecole = codeEcole;
  const r = await fetch(API_BASE + '/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || 'Erreur');
  return d;
}
const apiMe = () => apiFetch('/auth/me');
function authLogout() {
  _token = null;
  localStorage.removeItem('gs_tok');
  localStorage.removeItem('gs_user');
  location.reload();
}
function apiSetToken(tok) { _token = tok; localStorage.setItem('gs_tok', tok); }

/* ── Settings ── */
const apiGetSettings  = ()  => apiFetch('/settings');

/* ── Licence (installation autonome / version .exe uniquement) ── */
const apiGetStatutLicence = () => apiFetch('/licence/statut');
const apiActiverLicence   = (cle) => apiFetch('/licence/activer', { method:'POST', body:{cle} });

/* ── Supervision des écoles clientes (super-administrateur) ── */
const apiGetEcoles     = () => apiFetch('/ecoles');
const apiGetEcole      = (id) => apiFetch(`/ecoles/${id}`);
const apiUpdateEcole   = (id, d) => apiFetch(`/ecoles/${id}`, { method:'PUT', body:d });
const apiDeleteEcole   = (id) => apiFetch(`/ecoles/${id}`, { method:'DELETE' });
const apiSaveSettings = (b) => apiFetch('/settings', { method: 'PUT', body: b });

/* ── Users ── */
const apiGetUsers    = ()     => apiFetch('/users');
const apiCreateUser  = (b)    => apiFetch('/users', { method: 'POST', body: b });
const apiUpdateUser  = (id,b) => apiFetch(`/users/${id}`, { method: 'PUT', body: b });
const apiDeleteUser  = (id)   => apiFetch(`/users/${id}`, { method: 'DELETE' });
const apiResetPwd    = (id,p) => apiFetch(`/users/${id}/reset-password`, { method: 'POST', body: { newPassword: p } });
const apiChangePwd   = (o,n)  => apiFetch('/auth/change-password', { method: 'POST', body: { oldPassword: o, newPassword: n } });

/* ── Personnel ── */
const apiGetPersonnel    = ()     => apiFetch('/personnel');
const apiCreatePersonnel = (b)    => apiFetch('/personnel', { method: 'POST', body: b });
const apiUpdatePersonnel = (id,b) => apiFetch(`/personnel/${id}`, { method: 'PUT', body: b });
const apiDeletePersonnel = (id)   => apiFetch(`/personnel/${id}`, { method: 'DELETE' });

/* ── Élèves ── */
const apiGetEleves    = (q='')    => apiFetch('/eleves' + (q?'?'+q:''));
const apiGetEleve     = (id)      => apiFetch(`/eleves/${id}`);
const apiCreateEleve  = (b)       => apiFetch('/eleves', { method: 'POST', body: b });
const apiUpdateEleve  = (id,b)    => apiFetch(`/eleves/${id}`, { method: 'PUT', body: b });
const apiDeleteEleve  = (id)      => apiFetch(`/eleves/${id}`, { method: 'DELETE' });
const apiUploadPhoto  = (id,fd)   => apiUpload(`/eleves/${id}/photo`, fd);
const apiValiderPreinscription = (id,b) => apiFetch(`/eleves/${id}/valider-preinscription`, { method: 'PUT', body: b });
const apiGetClasses   = ()        => apiFetch('/eleves/meta/classes');

/* ── Notes ── */
const apiGetNotes    = (q='')    => apiFetch('/notes'+(q?'?'+q:''));
const apiCreateNote  = (b)       => apiFetch('/notes', { method: 'POST', body: b });
const apiUpdateNote  = (id,b)    => apiFetch(`/notes/${id}`, { method: 'PUT', body: b });
const apiDeleteNote  = (id)      => apiFetch(`/notes/${id}`, { method: 'DELETE' });

/* ── Devoirs ── */
const apiGetDevoirs    = (q='')    => apiFetch('/devoirs'+(q?'?'+q:''));
const apiCreateDevoir  = (b)       => apiFetch('/devoirs', { method: 'POST', body: b });
const apiUpdateDevoir  = (id,b)    => apiFetch(`/devoirs/${id}`, { method: 'PUT', body: b });
const apiDeleteDevoir  = (id)      => apiFetch(`/devoirs/${id}`, { method: 'DELETE' });

/* ── Emploi du temps ── */
const apiGetEdt    = (q='')    => apiFetch('/emploi-du-temps'+(q?'?'+q:''));
const apiCreateEdt = (b)       => apiFetch('/emploi-du-temps', { method: 'POST', body: b });
const apiUpdateEdt = (id,b)    => apiFetch(`/emploi-du-temps/${id}`, { method: 'PUT', body: b });
const apiDeleteEdt = (id)      => apiFetch(`/emploi-du-temps/${id}`, { method: 'DELETE' });

/* ── Absences ── */
const apiGetAbsences    = (q='')    => apiFetch('/absences'+(q?'?'+q:''));
const apiCreateAbsence  = (b)       => apiFetch('/absences', { method: 'POST', body: b });
const apiUpdateAbsence  = (id,b)    => apiFetch(`/absences/${id}`, { method: 'PUT', body: b });
const apiDeleteAbsence  = (id)      => apiFetch(`/absences/${id}`, { method: 'DELETE' });
const apiStatsAbsences  = (id)      => apiFetch(`/absences/stats/${id}`);

/* ── Absences du personnel (point 6) ── */
const apiGetAbsencesPersonnel       = (q='') => apiFetch('/absences-personnel'+(q?'?'+q:''));
const apiGetAbsencesPersonnelAujourdhui = () => apiFetch('/absences-personnel/aujourd-hui');
const apiSignalerAbsencePersonnel   = (b)    => apiFetch('/absences-personnel', { method: 'POST', body: b });
const apiUpdateAbsencePersonnel     = (id,b) => apiFetch(`/absences-personnel/${id}`, { method: 'PUT', body: b });
const apiDeleteAbsencePersonnel     = (id)   => apiFetch(`/absences-personnel/${id}`, { method: 'DELETE' });

/* ── Réinscriptions ── */
const apiGetReinscriptions   = (q='')    => apiFetch('/reinscriptions'+(q?'?'+q:''));
const apiCreateReinscription = (b)       => apiFetch('/reinscriptions', { method: 'POST', body: b });
const apiValiderReinscription= (id,b)    => apiFetch(`/reinscriptions/${id}/valider`, { method: 'PUT', body: b });
const apiDeleteReinscription = (id)      => apiFetch(`/reinscriptions/${id}`, { method: 'DELETE' });

/* ── Transactions ── */
const apiGetTransactions    = (q='')    => apiFetch('/transactions'+(q?'?'+q:''));

/* ── Fournisseurs ── */
const apiGetFournisseurs    = (q='')    => apiFetch('/fournisseurs'+(q?'?'+q:''));
const apiGetFournisseur     = (id)      => apiFetch(`/fournisseurs/${id}`);
const apiCreateFournisseur  = (d)       => apiFetch('/fournisseurs', { method:'POST', body:d });
const apiUpdateFournisseur  = (id,d)    => apiFetch(`/fournisseurs/${id}`, { method:'PUT', body:d });
const apiDeleteFournisseur  = (id)      => apiFetch(`/fournisseurs/${id}`, { method:'DELETE' });

const apiGetTransactionsRecurrentes = () => apiFetch('/transactions-recurrentes');
const apiCreateTransactionRecurrente = (d) => apiFetch('/transactions-recurrentes', { method:'POST', body:d });
const apiUpdateTransactionRecurrente = (id,d) => apiFetch(`/transactions-recurrentes/${id}`, { method:'PUT', body:d });
const apiDeleteTransactionRecurrente = (id) => apiFetch(`/transactions-recurrentes/${id}`, { method:'DELETE' });

const apiGetBudgets = (mois='') => apiFetch('/budgets'+(mois?'?mois='+mois:''));
const apiSaveBudget = (d) => apiFetch('/budgets', { method:'POST', body:d });
const apiDeleteBudget = (id) => apiFetch(`/budgets/${id}`, { method:'DELETE' });
const apiComparaisonBudget = (mois) => apiFetch('/budgets/comparaison?mois='+mois);
const apiAnalyseComptable = (mois) => apiFetch('/analyse-comptable?mois='+mois);

function apiAnalyserRapprochement(fichier) {
  const fd = new FormData();
  fd.append('fichier', fichier);
  return apiUpload('/rapprochement/analyser', fd);
}
const apiValiderRapprochement = (id) => apiFetch(`/rapprochement/valider/${id}`, { method:'PUT' });
const apiAnnulerRapprochement = (id) => apiFetch(`/rapprochement/annuler/${id}`, { method:'PUT' });
const apiEtatRapprochement = (q='') => apiFetch('/rapprochement/etat'+(q?'?'+q:''));
function apiExportTransactionsExcel(q='') {
  const url = API_BASE + '/transactions/export' + (q?'?'+q:'');
  fetch(url, { headers: { 'Authorization': 'Bearer ' + _token } })
    .then(r => { if (!r.ok) return r.json().then(d => { throw new Error(d.error||'Erreur'); }); return r.blob(); })
    .then(blob => {
      const a = document.createElement('a');
      const objUrl = URL.createObjectURL(blob);
      a.href = objUrl; a.download = 'Journal-Comptable.xlsx';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(objUrl);
    })
    .catch(err => toast(err.message, 'error'));
}
const apiCreateTransaction  = (b)       => apiFetch('/transactions', { method: 'POST', body: b });
const apiDeleteTransaction  = (id)      => apiFetch(`/transactions/${id}`, { method: 'DELETE' });

/* ── Frais ── */
const apiGetFrais    = ()     => apiFetch('/frais');
const apiCreateFrais = (b)    => apiFetch('/frais', { method: 'POST', body: b });
const apiUpdateFrais = (id,b) => apiFetch(`/frais/${id}`, { method: 'PUT', body: b });
const apiDeleteFrais = (id)   => apiFetch(`/frais/${id}`, { method: 'DELETE' });

/* ── Paiements ── */
const apiGetPaiements  = (q='')  => apiFetch('/paiements'+(q?'?'+q:''));
const apiGenPaiements  = (b)     => apiFetch('/paiements/generer', { method: 'POST', body: b });
const apiCreatePaiement= (b)     => apiFetch('/paiements', { method: 'POST', body: b });
const apiDeletePaiement= (id)    => apiFetch(`/paiements/${id}`, { method: 'DELETE' });
const apiVerserPaiement= (id,b)  => apiFetch(`/paiements/${id}/verser`, { method: 'POST', body: b });
const apiSoldePaiements= (id)    => apiFetch(`/paiements/solde/${id}`);
const apiSoldesTous    = ()      => apiFetch('/paiements/soldes');
const apiVersementsEleve= (id)   => apiFetch(`/versements/${id}`);

/* ── Cantine ── */
const apiGetMenus    = (q='')    => apiFetch('/cantine/menus'+(q?'?'+q:''));
const apiCreateMenu  = (b)       => apiFetch('/cantine/menus', { method: 'POST', body: b });
const apiUpdateMenu  = (id,b)    => apiFetch(`/cantine/menus/${id}`, { method: 'PUT', body: b });
const apiDeleteMenu  = (id)      => apiFetch(`/cantine/menus/${id}`, { method: 'DELETE' });
const apiGetAbons    = (q='')    => apiFetch('/cantine/abonnements'+(q?'?'+q:''));
const apiCreateAbon  = (b)       => apiFetch('/cantine/abonnements', { method: 'POST', body: b });
const apiUpdateAbon  = (id,b)    => apiFetch(`/cantine/abonnements/${id}`, { method: 'PUT', body: b });
const apiPayerAbon   = (id,b)    => apiFetch(`/cantine/abonnements/${id}/payer`, { method: 'POST', body: b });
const apiDeleteAbon  = (id)      => apiFetch(`/cantine/abonnements/${id}`, { method: 'DELETE' });

/* ── Communication ── */
const apiGetAnnonces    = ()     => apiFetch('/annonces');
const apiCreateAnnonce  = (b)    => apiFetch('/annonces', { method: 'POST', body: b });
const apiUpdateAnnonce  = (id,b) => apiFetch(`/annonces/${id}`, { method: 'PUT', body: b });
const apiDeleteAnnonce  = (id)   => apiFetch(`/annonces/${id}`, { method: 'DELETE' });
const apiGetMessages    = (q='') => apiFetch('/messages'+(q?'?'+q:''));
const apiCreateMessage  = (b)    => apiFetch('/messages', { method: 'POST', body: b });
const apiDeleteMessage  = (id)   => apiFetch(`/messages/${id}`, { method: 'DELETE' });

/* ── Dashboard ── */
const apiGetDashboard = () => apiFetch('/dashboard');

/* ── Classes ── */
const apiGetClassesFull = (q='') => apiFetch('/classes'+(q?'?'+q:''));
const apiCreateClasse   = (b)    => apiFetch('/classes', { method: 'POST', body: b });
const apiUpdateClasse   = (id,b) => apiFetch(`/classes/${id}`, { method: 'PUT', body: b });
const apiDeleteClasse   = (id)   => apiFetch(`/classes/${id}`, { method: 'DELETE' });

/* ── Approbation comptable ── */
const apiTransactionsEnAttente = () => apiFetch('/transactions/en-attente');
const apiApprouverTransaction  = (id)   => apiFetch(`/transactions/${id}/approuver`, { method: 'PUT' });
const apiRejeterTransaction    = (id,b) => apiFetch(`/transactions/${id}/rejeter`, { method: 'PUT', body: b });
const apiUpdateTransaction     = (id,b) => apiFetch(`/transactions/${id}`, { method: 'PUT', body: b });
const apiUpdateSeuils          = (b)    => apiFetch('/settings/seuils-approbation', { method: 'PUT', body: b });

/* ── Journal d'audit ── */
const apiGetJournal  = (q='') => apiFetch('/journal'+(q?'?'+q:''));
const apiJournalMeta = ()     => apiFetch('/journal/entites');

/* ── Heures d'enseignement (personnel horaire) ── */
const apiGetHeuresPersonnel = (id)   => apiFetch(`/personnel/${id}/heures`);
const apiSaisirHeures       = (id,b) => apiFetch(`/personnel/${id}/heures`, { method: 'POST', body: b });

/* ── Séances de cours (traçabilité + validation direction) ── */
const apiGetSeancesCours     = (q='') => apiFetch('/seances-cours'+(q?'?'+q:''));
const apiCreateSeanceCours   = (b)    => apiFetch('/seances-cours', { method: 'POST', body: b });
const apiValiderSeanceCours  = (id)   => apiFetch(`/seances-cours/${id}/valider`, { method: 'PUT' });
const apiValiderGroupeSeances= (b)    => apiFetch('/seances-cours/valider-groupe', { method: 'PUT', body: b });
const apiRejeterSeanceCours  = (id,b) => apiFetch(`/seances-cours/${id}/rejeter`, { method: 'PUT', body: b });
const apiDeleteSeanceCours   = (id)   => apiFetch(`/seances-cours/${id}`, { method: 'DELETE' });
const apiCreneauxEmploiTemps = (pid)  => apiFetch(`/personnel/${pid}/creneaux-emploi-temps`);
const apiUploadPhotoPersonnel = (id,fd) => apiUpload(`/personnel/${id}/photo`, fd);

/* ── Articles / Actualités ── */
const apiGetArticles      = (q='') => apiFetch('/articles'+(q?'?'+q:''));
const apiGetArticlesAdmin = ()     => apiFetch('/articles/admin');
const apiGetArticle       = (id)   => apiFetch(`/articles/${id}`);
const apiCreateArticle    = (b)    => apiFetch('/articles', { method: 'POST', body: b });
const apiUpdateArticle    = (id,b) => apiFetch(`/articles/${id}`, { method: 'PUT', body: b });
const apiDeleteArticle    = (id)   => apiFetch(`/articles/${id}`, { method: 'DELETE' });
const apiUploadArticleMedia = (id,fd) => apiUpload(`/articles/${id}/media`, fd);
const apiDeleteArticleMedia = (id)    => apiFetch(`/articles/media/${id}`, { method: 'DELETE' });

/* ── Élève du mois ── */
const apiGetEleveDuMoisAll = () => apiFetch('/eleve-du-mois');
const apiGetEleveDuMoisActuel = () => apiFetch('/eleve-du-mois/actuel');
const apiDesignerEleveDuMois  = (b) => apiFetch('/eleve-du-mois', { method: 'POST', body: b });
const apiDeleteEleveDuMois    = (id) => apiFetch(`/eleve-du-mois/${id}`, { method: 'DELETE' });

/* ── Salles ── */
const apiGetSalles    = (q='') => apiFetch('/salles'+(q?'?'+q:''));
const apiCreateSalle  = (b)    => apiFetch('/salles', { method: 'POST', body: b });
const apiUpdateSalle  = (id,b) => apiFetch(`/salles/${id}`, { method: 'PUT', body: b });
const apiDeleteSalle  = (id)   => apiFetch(`/salles/${id}`, { method: 'DELETE' });

/* ── Paie / bulletins de salaire ── */
const apiCalculPaie      = (personnelId, mois) => apiFetch(`/paie/calcul/${personnelId}?mois=${mois}`);
const apiListePaie       = (mois) => apiFetch(`/paie/liste?mois=${mois}`);
const apiGenererBulletin = (b)    => apiFetch('/paie/bulletins', { method: 'POST', body: b });
const apiGetBulletins    = (q='') => apiFetch('/paie/bulletins'+(q?'?'+q:''));
const apiGetBulletin     = (id)   => apiFetch(`/paie/bulletins/${id}`);
const apiDeleteBulletin  = (id)   => apiFetch(`/paie/bulletins/${id}`, { method: 'DELETE' });

/* ── Types de primes (liste déroulante modifiable) ── */
const apiGetTypesPrimes    = (q='') => apiFetch('/paie/types-primes'+(q?'?'+q:''));
const apiCreateTypePrime   = (b)    => apiFetch('/paie/types-primes', { method: 'POST', body: b });
const apiUpdateTypePrime   = (id,b) => apiFetch(`/paie/types-primes/${id}`, { method: 'PUT', body: b });
const apiDeleteTypePrime   = (id)   => apiFetch(`/paie/types-primes/${id}`, { method: 'DELETE' });

/* ── Avances sur salaire (plafond 40%) ── */
const apiGetAvances        = (q='') => apiFetch('/paie/avances'+(q?'?'+q:''));
const apiPlafondAvance     = (personnelId) => apiFetch(`/paie/avances/plafond/${personnelId}`);
const apiCreateAvance      = (b)    => apiFetch('/paie/avances', { method: 'POST', body: b });
const apiAnnulerAvance     = (id)   => apiFetch(`/paie/avances/${id}/annuler`, { method: 'PUT' });

/* ── Validation de la masse salariale (comptable → directeur → admin) ── */
const apiGetValidationPaie   = (mois) => apiFetch(`/paie/validation?mois=${mois}`);
const apiSoumettreValidation = (b)    => apiFetch('/paie/validation', { method: 'POST', body: b });
const apiValiderDirecteur    = (id,b={}) => apiFetch(`/paie/validation/${id}/valider-directeur`, { method: 'PUT', body: b });
const apiValiderAdminPaie    = (id,b={}) => apiFetch(`/paie/validation/${id}/valider-admin`, { method: 'PUT', body: b });

/* ── Candidatures enseignants ── */
const apiSoumettreCandidature = (b) => apiFetch('/candidatures', { method: 'POST', body: b });
const apiGetCandidatures  = (q='') => apiFetch('/candidatures'+(q?'?'+q:''));
const apiGetCandidature   = (id)   => apiFetch(`/candidatures/${id}`);
const apiApprouverCandidature = (id) => apiFetch(`/candidatures/${id}/approuver`, { method: 'PUT' });
const apiRejeterCandidature   = (id,b) => apiFetch(`/candidatures/${id}/rejeter`, { method: 'PUT', body: b });
const apiDeleteCandidature = (id) => apiFetch(`/candidatures/${id}`, { method: 'DELETE' });

/* ── Enseignants / séances des cours de révision ── */
const apiGetEnseignantsCours = (coursId) => apiFetch(`/cours-revision/${coursId}/enseignants`);
const apiAssignerEnseignant  = (coursId,b) => apiFetch(`/cours-revision/${coursId}/enseignants`, { method: 'POST', body: b });
const apiRetirerEnseignant   = (ceId) => apiFetch(`/cours-revision/enseignants/${ceId}`, { method: 'DELETE' });
const apiGetSeances          = (coursId) => apiFetch(`/cours-revision/${coursId}/seances`);
const apiEnregistrerSeance   = (coursId,b) => apiFetch(`/cours-revision/${coursId}/seances`, { method: 'POST', body: b });
const apiDeleteSeance        = (sId) => apiFetch(`/cours-revision/seances/${sId}`, { method: 'DELETE' });
const apiCalculRedistribution = (mois) => apiFetch(`/cours-revision/redistribution?mois=${mois}`);
const apiVerserRedistribution = (b) => apiFetch('/cours-revision/redistribution/verser', { method: 'POST', body: b });

/* ── Cours de révision (payants, ouverts aux externes, avec évaluation) ── */
const apiGetCoursRevision      = (q='') => apiFetch('/cours-revision'+(q?'?'+q:''));
const apiGetCoursRevisionOne   = (id)   => apiFetch(`/cours-revision/${id}`);
const apiCreateCoursRevision   = (b)    => apiFetch('/cours-revision', { method: 'POST', body: b });
const apiUpdateCoursRevision   = (id,b) => apiFetch(`/cours-revision/${id}`, { method: 'PUT', body: b });
const apiDeleteCoursRevision   = (id)   => apiFetch(`/cours-revision/${id}`, { method: 'DELETE' });
const apiGetRevisionParticipants = (coursId) => apiFetch(`/cours-revision/${coursId}/participants`);
const apiAddRevisionParticipant  = (coursId,b) => apiFetch(`/cours-revision/${coursId}/participants`, { method: 'POST', body: b });
const apiDeleteRevisionParticipant = (pId) => apiFetch(`/cours-revision/participants/${pId}`, { method: 'DELETE' });
const apiPayerRevisionParticipant  = (pId,b) => apiFetch(`/cours-revision/participants/${pId}/payer`, { method: 'POST', body: b });
const apiGetRevisionEvaluations = (pId) => apiFetch(`/cours-revision/participants/${pId}/evaluations`);
const apiCreateRevisionEvaluation = (pId,b) => apiFetch(`/cours-revision/participants/${pId}/evaluations`, { method: 'POST', body: b });
const apiDeleteRevisionEvaluation = (eId) => apiFetch(`/cours-revision/evaluations/${eId}`, { method: 'DELETE' });
