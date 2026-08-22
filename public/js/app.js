/* ============================================================
   APP.JS — Navigation principale, Login, Init
============================================================ */

/* ── Définition des pages ── */
const PAGES = {
  dashboard:       { icon:'🏠', labelKey:'nav_dashboard',    fn: pageDashboard,       roles:['admin','directeur','comptable','enseignant','secretaire','charge_communication'] },
  eleves:          { icon:'🎓', labelKey:'nav_eleves',              fn: pageEleves,          roles:['admin','directeur','enseignant','secretaire'] },
  eleveDuMois:     { icon:'⭐', labelKey:'nav_eleve_du_mois',       fn: pageEleveDuMois,     roles:['admin','directeur','enseignant','secretaire'] },
  notes:           { icon:'📊', labelKey:'nav_notes',   fn: pageNotes,           roles:['admin','directeur','enseignant','secretaire'] },
  devoirs:         { icon:'📚', labelKey:'nav_devoirs',             fn: pageDevoirs,         roles:['admin','directeur','enseignant','secretaire'] },
  emploi:          { icon:'📅', labelKey:'nav_emploi',     fn: pageEmploi,          roles:['admin','directeur','enseignant','secretaire'] },
  seances:         { icon:'📋', labelKey:'nav_seances',    fn: pageSeances,         roles:['admin','directeur','directeur_etudes','enseignant','secretaire'] },
  absences:        { icon:'📋', labelKey:'nav_absences',            fn: pageAbsences,        roles:['admin','directeur','enseignant','secretaire'] },
  classes:         { icon:'🏫', labelKey:'nav_classes',              fn: pageClasses,        roles:['admin','directeur'] },
  salles:          { icon:'🚪', labelKey:'nav_salles',                fn: pageSalles,         roles:['admin','directeur','secretaire'] },
  paiements:       { icon:'💰', labelKey:'nav_paiements',           fn: pagePaiements,       roles:['admin','directeur','comptable','secretaire'] },
  cantine:         { icon:'🍽️', labelKey:'nav_cantine',            fn: pageCantine,         roles:['admin','directeur','comptable','secretaire'] },
  comptabilite:    { icon:'💳', labelKey:'nav_comptabilite',        fn: pageComptabilite,    roles:['admin','directeur','comptable'] },
  revision:        { icon:'📖', labelKey:'nav_revision',            fn: pageRevision,        roles:['admin','directeur','comptable','enseignant','secretaire'] },
  paie:            { icon:'💵', labelKey:'nav_paie',                 fn: pagePaieList,        roles:['admin','directeur','comptable'] },
  reinscriptions:  { icon:'🔄', labelKey:'nav_reinscriptions',      fn: pageReinscriptions,  roles:['admin','directeur','secretaire'] },
  communication:   { icon:'📢', labelKey:'nav_communication',        fn: pageCommunication,  roles:['admin','directeur','secretaire','charge_communication'] },
  actualites:      { icon:'📰', labelKey:'nav_actualites', fn: pageActualites,     roles:['admin','directeur','secretaire','charge_communication'] },
  personnel:       { icon:'👨‍🏫', labelKey:'nav_personnel',          fn: pagePersonnel,       roles:['admin','directeur','secretaire'] },
  candidatures:    { icon:'📋', labelKey:'nav_candidatures',         fn: pageCandidatures,    roles:['admin','directeur'] },
  users:           { icon:'👥', labelKey:'nav_users',         fn: pageUsers,           roles:['admin'] },
  journal:         { icon:'🗂️', labelKey:'nav_journal',     fn: pageJournal,         roles:['admin'] },
  settings:        { icon:'⚙️', labelKey:'nav_settings',          fn: pageSettings,        roles:['admin','directeur'] },
  ecoles:          { icon:'🏢', labelKey:'nav_ecoles',             fn: pageEcoles,          superAdminOnly:true },
};

// Groupes de navigation
const NAV_GROUPS = [
  { labelKey: null, pages: ['dashboard'] },
  { labelKey: 'nav_section_scolarite', pages: ['eleves','eleveDuMois','notes','devoirs','emploi','seances','absences','classes','salles','reinscriptions'] },
  { labelKey: 'nav_section_finances', pages: ['paiements','cantine','comptabilite','revision','paie'] },
  { labelKey: 'nav_section_vie_ecole', pages: ['communication','actualites','personnel'] },
  { labelKey: 'nav_section_administration', pages: ['users','journal','settings'] },
  { labelKey: 'nav_section_super_admin', pages: ['ecoles'] },
];

/* ── État ── */
let currentUser = null;
let currentPage = 'dashboard';

/* ── Login ── */
async function initLogin() {
  $('#login-screen').style.display = '';
  $('#licence-screen').style.display = 'none';
  $('#app').style.display = 'none';
  $('#login-lang-wrap').innerHTML = langSwitcherHtml(false, 'lang-switcher-login');
  applyLoginTranslations();
  try {
    const s = await apiGetSettings();
    if (s.ecole_nom) {
      $('#login-ecole-nom').textContent = s.ecole_nom;
      document.title = s.ecole_nom + ' — Connexion';
    }
    if (s.ecole_logo) {
      $('#login-logo').src = s.ecole_logo;
      $('#login-logo').style.display = '';
      $('#login-logo-default').style.display = 'none';
    }
  } catch(_) {}

  $('#login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const username = $('#l-user').value.trim();
    const password = $('#l-pass').value;
    const btn = $('#login-btn');
    btn.disabled = true;
    btn.textContent = 'Connexion…';
    $('#login-err').style.display = 'none';
    try {
      const { token, user } = await apiLogin(username, password);
      apiSetToken(token);
      currentUser = user;
      localStorage.setItem('gs_user', JSON.stringify(user));
      await startApp();
      const civ = user.civilite ? user.civilite + ' ' : '';
      toast(`Bienvenue ${civ}${user.full_name || user.username} 👋`, 'success');
    } catch(err) {
      $('#login-err').textContent = err.message;
      $('#login-err').style.display = '';
      btn.disabled = false;
      btn.textContent = 'Se connecter';
    }
  });
}

function togglePass() {
  const input = $('#l-pass');
  input.type = input.type === 'password' ? 'text' : 'password';
}
window.togglePass = togglePass;

/* ── Démarrer l'app ── */
async function startApp() {
  $('#login-screen').style.display = 'none';
  $('#app').style.display = '';
  $('#topbar-lang-wrap').innerHTML = langSwitcherHtml(true, 'lang-switcher-topbar');
  $('#pwd-btn').textContent = '🔒 ' + t('password_menu');
  $('#logout-btn').textContent = '⎋ ' + t('logout_btn');

  // Info utilisateur dans la sidebar
  const initials = ((currentUser.full_name||'?').split(' ').slice(0,2).map(s=>s[0]||'').join('')).toUpperCase();
  $('#sb-avatar').textContent = initials;
  $('#sb-name').textContent = currentUser.full_name || currentUser.username;
  $('#sb-role').textContent = t('role_' + currentUser.role) || ROLES[currentUser.role] || currentUser.role;

  // Charger et appliquer paramètres
  try {
    const s = await apiGetSettings();
    applyBranding(s);
    $('#sb-annee').textContent = s.annee_scolaire || '';
  } catch(_) {}

  // Charger la liste dynamique des classes (point 1 du cahier des charges)
  await refreshClasses();
  await refreshCreneaux();

  // Bannière de période d'essai (installation autonome uniquement — sans effet
  // sur la plateforme web, qui renvoie toujours 'illimitee').
  try {
    const statut = await apiGetStatutLicence();
    const banniere = $('#essai-banniere');
    if (statut.mode === 'essai') {
      banniere.style.display = 'flex';
      banniere.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:10px;background:#FFFBEB;color:#92400E;padding:9px 14px;font-size:13px;font-weight:600;border-bottom:1px solid #FDE68A';
      banniere.innerHTML = `⏳ Essai gratuit — ${statut.jours_restants} jour${statut.jours_restants>1?'s':''} restant${statut.jours_restants>1?'s':''}`
        + (currentUser.role === 'admin' ? ` <button id="btn-activer-licence" style="margin-left:6px;padding:4px 12px;font-size:12px;border-radius:999px;border:none;background:#92400E;color:#fff;cursor:pointer">Activer une licence</button>` : '');
      const btnActiver = $('#btn-activer-licence');
      if (btnActiver) btnActiver.addEventListener('click', () => {
        $('#app').style.display = 'none';
        afficherEcranLicenceBloquee();
      });
    } else {
      banniere.style.display = 'none';
    }
  } catch (_) {}

  buildNav();
  navigate('dashboard');
}

/* ── Navigation ── */
function buildNav() {
  const nav = $('#nav');
  nav.innerHTML = '';
  NAV_GROUPS.forEach(group => {
    const visiblePages = group.pages.filter(k => {
      const pg = PAGES[k];
      if (!pg) return false;
      return pg.superAdminOnly ? !!currentUser.est_super_admin : pg.roles.includes(currentUser.role);
    });
    if (!visiblePages.length) return;
    if (group.labelKey) {
      const title = document.createElement('div');
      title.className = 'nav-section-title';
      title.textContent = t(group.labelKey);
      nav.appendChild(title);
    }
    visiblePages.forEach(k => {
      const pg = PAGES[k];
      const btn = document.createElement('button');
      btn.className = 'nav-btn';
      btn.dataset.page = k;
      btn.innerHTML = `<span class="ni">${pg.icon}</span><span>${t(pg.labelKey)}</span>`;
      btn.addEventListener('click', () => navigate(k));
      nav.appendChild(btn);
    });
  });
}

function navigate(page) {
  if (!PAGES[page]) return;
  const pg = PAGES[page];
  const autorise = pg.superAdminOnly ? !!currentUser?.est_super_admin : pg.roles.includes(currentUser?.role);
  if (!autorise) { toast('Accès refusé','error'); return; }

  currentPage = page;
  // Mettre à jour nav
  $$('.nav-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.page === page));
  // Titre
  $('#pg-title').textContent = `${pg.icon} ${t(pg.labelKey)}`;
  $('#pg-sub').textContent = '';
  // Sur mobile, la sidebar est un tiroir : on la referme après avoir choisi une page
  toggleSidebar(false);
  // Charger la page
  try { pg.fn(); }
  catch(e) { console.error(e); $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
window.navigate = navigate;

/* ── Sidebar mobile (tiroir) ── */
function toggleSidebar(force) {
  const open = force !== undefined ? force : !document.getElementById('sidebar').classList.contains('open');
  document.getElementById('sidebar').classList.toggle('open', open);
  document.getElementById('sidebar-overlay').classList.toggle('show', open);
}
window.toggleSidebar = toggleSidebar;

/* ── Déconnexion ── */
function logout() {
  if (!confirm('Se déconnecter ?')) return;
  authLogout();
}
window.logout = logout;

/* ── Modal mot de passe ── */
function showPwdModal() {
  openModal('Changer mon mot de passe', `
    <form id="f-cpwd" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Ancien mot de passe</label><input type="password" id="cpwd-old" required></div>
      <div class="fg"><label>Nouveau mot de passe (min. 6 car.)</label><input type="password" id="cpwd-new" required minlength="6"></div>
      <div class="fg"><label>Confirmer le nouveau mot de passe</label><input type="password" id="cpwd-conf" required></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Changer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-cpwd').onsubmit = async e => {
    e.preventDefault();
    const oldPwd = $('#cpwd-old').value;
    const newPwd = $('#cpwd-new').value;
    const conf = $('#cpwd-conf').value;
    if (newPwd !== conf) { toast('Les mots de passe ne correspondent pas','error'); return; }
    try {
      await apiChangePwd(oldPwd, newPwd);
      toast('Mot de passe modifié ✅','success'); closeModal();
    } catch(err) { toast(err.message,'error'); }
  };
}
window.showPwdModal = showPwdModal;

/* ── Raccourci Escape ── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

/* ── DÉMARRAGE ── */
// La session survit désormais à une actualisation de la page : si un jeton encore
// valide existe, il est vérifié auprès du serveur (route /auth/me) et la session
// est restaurée directement, sans redemander les identifiants. Le jeton expire de
// lui-même au bout de 12h (voir auth.py), ce qui garantit une déconnexion naturelle
// et une traçabilité réelle sans imposer une reconnexion à chaque simple rafraîchissement.
async function init() {
  // Vérification de licence (n'a d'effet que sur une installation autonome / .exe ;
  // sans effet sur la plateforme web, qui renvoie toujours 'illimitee').
  try {
    const statut = await apiGetStatutLicence();
    if (statut.bloque) {
      afficherEcranLicenceBloquee();
      return;
    }
  } catch (_) {
    // En cas d'erreur reseau sur cette verification, on ne bloque jamais l'acces par prudence
  }

  if (_token) {
    try {
      currentUser = await apiMe();
      localStorage.setItem('gs_user', JSON.stringify(currentUser));
      await startApp();
      return;
    } catch (_) {
      // Jeton invalide ou expiré : on nettoie et on retombe sur l'écran de connexion
      localStorage.removeItem('gs_user');
      localStorage.removeItem('gs_tok');
      _token = null;
    }
  }
  initLogin();
}

function afficherEcranLicenceBloquee() {
  $('#licence-screen').style.display = 'flex';
  $('#login-screen').style.display = 'none';
  $('#app').style.display = 'none';
  const form = $('#licence-form');
  if (form.dataset.bound) return;
  form.dataset.bound = '1';
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = $('#licence-btn');
    const errBox = $('#licence-err');
    errBox.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Activation…';
    try {
      await apiActiverLicence($('#licence-cle-input').value.trim());
      toast('Licence activée avec succès !', 'success');
      $('#licence-screen').style.display = 'none';
      init();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = '';
      btn.disabled = false;
      btn.textContent = 'Activer ma licence';
    }
  });
}

init();
