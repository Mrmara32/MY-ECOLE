/* ============================================================
   APP.JS — Navigation principale, Login, Init
============================================================ */

/* ── Définition des pages ── */
const PAGES = {
  dashboard:       { icon:'🏠', labelKey:'nav_dashboard',    fn: pageDashboard,       roles:['admin','directeur','comptable','enseignant','secretaire','charge_communication'] },
  eleves:          { icon:'🎓', labelKey:'nav_eleves',              fn: pageEleves,          roles:['admin','directeur','enseignant','secretaire','comptable'] },
  eleveDuMois:     { icon:'⭐', labelKey:'nav_eleve_du_mois',       fn: pageEleveDuMois,     roles:['admin','directeur','enseignant','secretaire'] },
  notes:           { icon:'📊', labelKey:'nav_notes',   fn: pageNotes,           roles:['admin','directeur','enseignant','secretaire'] },
  devoirs:         { icon:'📚', labelKey:'nav_devoirs',             fn: pageDevoirs,         roles:['admin','directeur','enseignant','secretaire'] },
  emploi:          { icon:'📅', labelKey:'nav_emploi',     fn: pageEmploi,          roles:['admin','directeur','enseignant','secretaire'] },
  seances:         { icon:'📋', labelKey:'nav_seances',    fn: pageSeances,         roles:['admin','directeur','directeur_etudes','enseignant','secretaire'] },
  absences:        { icon:'📋', labelKey:'nav_absences',            fn: pageAbsences,        roles:['admin','directeur','enseignant','secretaire'] },
  bibliotheque:    { icon:'📚', labelKey:'nav_bibliotheque',      fn: pageBibliotheque,    roles:['admin','directeur','secretaire','enseignant'] },
  examens:         { icon:'📝', labelKey:'nav_examens',           fn: pageExamens,         roles:['admin','directeur','secretaire','enseignant'] },
  discipline:      { icon:'🧑‍⚖️', labelKey:'nav_discipline',         fn: pageDiscipline,      roles:['admin','directeur','enseignant','secretaire'] },
  pointage:        { icon:'🪪', labelKey:'nav_pointage',            fn: pagePointage,        roles:['admin','directeur','secretaire'] },
  classes:         { icon:'🏫', labelKey:'nav_classes',              fn: pageClasses,        roles:['admin','directeur'] },
  salles:          { icon:'🚪', labelKey:'nav_salles',                fn: pageSalles,         roles:['admin','directeur','secretaire'] },
  paiements:       { icon:'💰', labelKey:'nav_paiements',           fn: pagePaiements,       roles:['admin','directeur','comptable','secretaire'] },
  cantine:         { icon:'🍽️', labelKey:'nav_cantine',            fn: pageCantine,         roles:['admin','directeur','comptable','secretaire'] },
  comptabilite:    { icon:'💳', labelKey:'nav_comptabilite',        fn: pageComptabilite,    roles:['admin','directeur','comptable'] },
  fournisseurs:    { icon:'🏭', labelKey:'nav_fournisseurs',        fn: pageFournisseurs,    roles:['admin','directeur','comptable'] },
  logistique:      { icon:'🚚', labelKey:'nav_logistique',          fn: pageLogistique,      roles:['admin','directeur','secretaire','comptable'] },
  revision:        { icon:'📖', labelKey:'nav_revision',            fn: pageRevision,        roles:['admin','directeur','comptable','enseignant','secretaire'] },
  paie:            { icon:'💵', labelKey:'nav_paie',                 fn: pagePaieList,        roles:['admin','directeur','comptable'] },
  reinscriptions:  { icon:'🔄', labelKey:'nav_reinscriptions',      fn: pageReinscriptions,  roles:['admin','directeur','secretaire'] },
  communication:   { icon:'📢', labelKey:'nav_communication',        fn: pageCommunication,  roles:['admin','directeur','secretaire','charge_communication'] },
  actualites:      { icon:'📰', labelKey:'nav_actualites', fn: pageActualites,     roles:['admin','directeur','secretaire','charge_communication'] },
  personnel:       { icon:'👨‍🏫', labelKey:'nav_personnel',          fn: pagePersonnel,       roles:['admin','directeur','secretaire','comptable'] },
  candidatures:    { icon:'📋', labelKey:'nav_candidatures',         fn: pageCandidatures,    roles:['admin','directeur'] },
  users:           { icon:'👥', labelKey:'nav_users',         fn: pageUsers,           roles:['admin'] },
  journal:         { icon:'🗂️', labelKey:'nav_journal',     fn: pageJournal,         roles:['admin'] },
  parametres:      { icon:'🔐', labelKey:'nav_parametres',        fn: pageParametres,      roles:['admin','directeur'] },
  settings:        { icon:'⚙️', labelKey:'nav_settings',          fn: pageSettings,        roles:['admin','directeur'] },
  aide:            { icon:'❓', labelKey:'nav_aide',                 fn: pageAide,            roles:['admin','directeur','comptable','enseignant','secretaire','charge_communication','directeur_etudes','parent'] },
  ecoles:          { icon:'🏢', labelKey:'nav_ecoles',             fn: pageEcoles,          superAdminOnly:true },
};

// Groupes de navigation
const NAV_GROUPS = [
  { labelKey: null, pages: ['dashboard'] },
  { labelKey: 'nav_section_scolarite', pages: ['eleves','eleveDuMois','notes','devoirs','emploi','seances','absences','pointage','discipline','examens','bibliotheque','classes','salles','reinscriptions'] },
  { labelKey: 'nav_section_finances', pages: ['paiements','cantine','comptabilite','fournisseurs','logistique','revision','paie'] },
  { labelKey: 'nav_section_vie_ecole', pages: ['communication','actualites','personnel'] },
  { labelKey: 'nav_section_administration', pages: ['parametres','users','journal','settings'] },
  { labelKey: 'nav_section_super_admin', pages: ['ecoles'] },
  { labelKey: null, pages: ['aide'] },
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

  // Par défaut (aucun code établissement saisi), la page affiche l'identité
  // générique MY-ECOLE — jamais celle d'une école en particulier. Ce n'est
  // qu'une fois qu'un code établissement valide est entré que le nom et le
  // logo réels de CETTE école s'affichent (voir _appliquerBrandingLogin ci-dessous).
  document.title = 'MY-ECOLE — Connexion';
  const _brandingParDefaut = () => {
    $('#login-ecole-nom').textContent = 'MY-ECOLE';
    $('#login-logo').style.display = 'none';
    $('#login-logo-default').style.display = '';
    document.title = 'MY-ECOLE — Connexion';
  };
  _brandingParDefaut();

  let _timerBrandingLogin = null;
  const _appliquerBrandingLogin = async (codeEcole) => {
    if (!codeEcole) { _brandingParDefaut(); return; }
    try {
      const s = await apiGetSettings('ecole=' + encodeURIComponent(codeEcole));
      if (s.ecole_nom) {
        $('#login-ecole-nom').textContent = s.ecole_nom;
        document.title = s.ecole_nom + ' — Connexion';
      } else {
        _brandingParDefaut();
      }
      if (s.ecole_logo) {
        $('#login-logo').src = s.ecole_logo;
        $('#login-logo').style.display = '';
        $('#login-logo-default').style.display = 'none';
      } else {
        $('#login-logo').style.display = 'none';
        $('#login-logo-default').style.display = '';
      }
    } catch(_) { _brandingParDefaut(); }
  };
  $('#l-code-ecole')?.addEventListener('input', (e) => {
    clearTimeout(_timerBrandingLogin);
    const valeur = e.target.value.trim();
    _timerBrandingLogin = setTimeout(() => _appliquerBrandingLogin(valeur), 400);
  });

  // Code établissement pré-rempli : depuis le lien de l'école (…/?ecole=CODE, utilisé
  // par le bouton « Espace personnel » du site vitrine) ou, à défaut, le dernier code
  // utilisé sur cet appareil — le personnel des écoles clientes n'a plus à le
  // retaper à chaque connexion.
  const _codeDepuisLien = new URLSearchParams(window.location.search).get('ecole');
  let _codeMemorise = null;
  try { _codeMemorise = localStorage.getItem('gs_code_ecole'); } catch (_) { /* stockage indisponible */ }
  const _codeInitial = (_codeDepuisLien || _codeMemorise || '').trim();
  if (_codeInitial && $('#l-code-ecole') && !$('#l-code-ecole').value) {
    $('#l-code-ecole').value = _codeInitial;
    _appliquerBrandingLogin(_codeInitial);
  }

  $('#login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const username = $('#l-user').value.trim();
    const password = $('#l-pass').value;
    const codeEcole = $('#l-code-ecole').value.trim();
    const btn = $('#login-btn');
    btn.disabled = true;
    btn.textContent = 'Connexion…';
    $('#login-err').style.display = 'none';
    try {
      let rep = await apiLogin(username, password, codeEcole);
      if (rep.requires_2fa) {
        // Mot de passe correct : le compte demande aussi le code de l'application d'authentification.
        const code = await demanderCode2fa();
        if (!code) { btn.disabled = false; btn.textContent = 'Se connecter'; return; }
        rep = await apiLogin(username, password, codeEcole, code);
      }
      const { token, user } = rep;
      apiSetToken(token);
      currentUser = user;
      localStorage.setItem('gs_user', JSON.stringify(user));
      try {
        if (codeEcole) localStorage.setItem('gs_code_ecole', codeEcole);
        else localStorage.removeItem('gs_code_ecole');
      } catch (_) { /* stockage indisponible : simple confort, sans conséquence */ }
      await startApp();
      if (user.doit_changer_mot_de_passe) showPwdModal(true);
      if (user.codes_secours_restants !== undefined) toast(`Code de secours utilisé — il vous en reste ${user.codes_secours_restants}.`, 'warning');
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

  // Les 4 chargements de démarrage partent EN MÊME TEMPS (avant : l'un après l'autre,
  // chaque aller-retour réseau s'ajoutait aux autres et l'ouverture était lente).
  const pSettings = apiGetSettings().catch(() => null);
  const pClasses = refreshClasses();
  const pCreneaux = refreshCreneaux();
  const pLicence = apiGetStatutLicence().catch(() => null);

  const s = await pSettings;
  if (s) { applyBranding(s); $('#sb-annee').textContent = s.annee_scolaire || ''; }
  await pClasses;
  await pCreneaux;

  // Bannière de période d'essai (installation autonome uniquement — sans effet
  // sur la plateforme web, qui renvoie toujours 'illimitee').
  try {
    const statut = await pLicence;
    if (!statut) throw new Error('indisponible');
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

  await exigerAcceptationConditions();
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

  if (page !== currentPage) window._pagePrecedente = currentPage;
  currentPage = page;
  // Mettre à jour nav
  $$('.nav-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.page === page));
  // Titre
  $('#pg-title').textContent = `${pg.icon} ${t(pg.labelKey)}`;
  $('#pg-sub').textContent = '';
  // Fil d'Ariane : Accueil > Section > Page (le lien Accueil ramène toujours au tableau de bord)
  const groupe = NAV_GROUPS.find(g => g.pages.includes(page));
  const crumbs = [`<a href="#" onclick="navigate('dashboard');return false">🏠 ${esc(t('nav_dashboard'))}</a>`];
  if (page !== 'dashboard') {
    if (groupe && groupe.labelKey) crumbs.push(`<span>${esc(t(groupe.labelKey))}</span>`);
    crumbs.push(`<span class="breadcrumb-current">${esc(t(pg.labelKey))}</span>`);
  }
  $('#pg-breadcrumb').innerHTML = crumbs.join('<span class="breadcrumb-sep">›</span>');
  // Sur mobile, la sidebar est un tiroir : on la referme après avoir choisi une page
  toggleSidebar(false);
  // Charger la page
  try { pg.fn(); }
  catch(e) { console.error(e); $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
window.navigate = navigate;
function retourPage() { navigate(window._pagePrecedente && PAGES[window._pagePrecedente] ? window._pagePrecedente : 'dashboard'); }
window.retourPage = retourPage;

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
async function logoutPartout() {
  if (!confirm('Déconnecter tous vos appareils (téléphone, autres ordinateurs…) ?')) return;
  try { await apiFetch('/auth/logout-all', { method: 'POST' }); } catch (e) {}
  authLogout();
}
window.logoutPartout = logoutPartout;
window.logout = logout;

/* ── Modal mot de passe ── */
function showPwdModal(obligatoire = false) {
  if (obligatoire !== true) obligatoire = false;
  openModal(obligatoire ? 'Choisissez votre mot de passe' : 'Changer mon mot de passe', `
    ${obligatoire ? `<div class="alert alert-info" style="margin-bottom:12px">Votre mot de passe est provisoire : vous devez en choisir un nouveau, qui vous est personnel, avant de continuer.</div>` : ''}
    <form id="f-cpwd" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>${obligatoire ? 'Mot de passe provisoire (actuel)' : 'Ancien mot de passe'}</label><input type="password" id="cpwd-old" required autocomplete="current-password"></div>
      <div class="fg"><label>Nouveau mot de passe (8 caractères min., avec lettres et chiffres)</label><input type="password" id="cpwd-new" required minlength="8" autocomplete="new-password"></div>
      <div class="fg"><label>Confirmer le nouveau mot de passe</label><input type="password" id="cpwd-conf" required autocomplete="new-password"></div>
      <div class="modal-footer">
        ${obligatoire ? '' : '<button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>'}
        <button type="submit" class="btn btn-primary">${obligatoire ? 'Enregistrer et continuer' : 'Changer'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-cpwd').onsubmit = async e => {
    e.preventDefault();
    const oldPwd = $('#cpwd-old').value;
    const newPwd = $('#cpwd-new').value;
    const conf = $('#cpwd-conf').value;
    if (newPwd !== conf) { toast('Les mots de passe ne correspondent pas','error'); return; }
    try {
      const r = await apiChangePwd(oldPwd, newPwd);
      if (r && r.token) apiSetToken(r.token);          // jeton sans la mention « mot de passe provisoire »
      toast('Mot de passe modifié ✅','success'); closeModal();
      if (obligatoire) { try { currentUser.doit_changer_mot_de_passe = false; localStorage.setItem('gs_user', JSON.stringify(currentUser)); } catch (_) {} navigate && navigate('dashboard'); }
    } catch(err) { toast(err.message,'error'); }
  };
}
window.showPwdModal = showPwdModal;

/* ── Double authentification ── */
function demanderCode2fa() {
  return new Promise(resolve => {
    openModal('Vérification en deux étapes', `
      <form id="f-2fa" style="display:flex;flex-direction:column;gap:14px">
        <div class="alert alert-info">Saisissez le code à 6 chiffres affiché par votre application d'authentification (ou un code de secours).</div>
        <div class="fg"><label>Code de vérification</label>
          <input id="c2fa" required autocomplete="one-time-code" inputmode="text" maxlength="12" style="font-size:1.4rem;letter-spacing:.2em;text-align:center"></div>
        <div class="modal-footer"><button type="button" class="btn btn-outline" id="c2fa-x">Annuler</button>
          <button class="btn btn-primary" type="submit">Valider</button></div>
      </form>`, { narrow: true });
    setTimeout(() => { const i = $('#c2fa'); i && i.focus(); }, 50);
    $('#c2fa-x').onclick = () => { closeModal(); resolve(null); };
    $('#f-2fa').onsubmit = e => { e.preventDefault(); const v = $('#c2fa').value.trim(); closeModal(); resolve(v); };
  });
}

async function show2faModal() {
  let st;
  try { st = await api2faStatut(); } catch (err) { toast(err.message, 'error'); return; }
  if (st.actif) {
    openModal('Double authentification', `
      <div class="alert alert-success" style="margin-bottom:12px">✅ Active sur votre compte. Codes de secours restants : <b>${st.codes_secours_restants}</b>.</div>
      <form id="f-2fa-off" style="display:flex;flex-direction:column;gap:12px">
        <p class="text-muted" style="font-size:.85rem">Pour la désactiver, confirmez avec votre mot de passe et un code actuel.</p>
        <div class="fg"><label>Mot de passe</label><input type="password" id="off-pwd" required autocomplete="current-password"></div>
        <div class="fg"><label>Code de vérification</label><input id="off-code" required maxlength="6" inputmode="numeric"></div>
        <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button>
          <button class="btn btn-danger" type="submit">Désactiver</button></div>
      </form>`, { narrow: true });
    $('#f-2fa-off').onsubmit = async e => {
      e.preventDefault();
      try { await api2faDesactiver($('#off-pwd').value, $('#off-code').value); toast('Double authentification désactivée', 'success'); closeModal(); }
      catch (err) { toast(err.message, 'error'); }
    };
    return;
  }
  openModal('Activer la double authentification', `
    <div class="alert alert-info" style="margin-bottom:12px">Même si votre mot de passe est volé, personne ne pourra se connecter sans votre téléphone.</div>
    <div style="margin-bottom:12px"><b>1.</b> Installez une application d'authentification (Google Authenticator, Microsoft Authenticator, Aegis…).</div>
    <button class="btn btn-primary" id="btn-2fa-go">Commencer</button>`, { narrow: true });
  $('#btn-2fa-go').onclick = async () => {
    try {
      const p = await api2faPreparer();
      openModal('Activer la double authentification', `
        <div style="margin-bottom:8px"><b>2.</b> Scannez ce QR code avec l'application :</div>
        <div style="text-align:center">${genererQrSvg(p.uri, 5, 4)}</div>
        <div class="text-muted" style="font-size:.8rem;text-align:center;margin:6px 0 12px">Ou saisissez la clé : <code>${p.secret}</code></div>
        <form id="f-2fa-on" style="display:flex;flex-direction:column;gap:12px">
          <div class="fg"><label><b>3.</b> Saisissez le code à 6 chiffres affiché</label><input id="on-code" required maxlength="6" inputmode="numeric" autocomplete="one-time-code"></div>
          <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
            <button class="btn btn-primary" type="submit">Activer</button></div>
        </form>`, { narrow: true });
      $('#f-2fa-on').onsubmit = async e => {
        e.preventDefault();
        try {
          const r = await api2faActiver($('#on-code').value);
          openModal('Codes de secours', `
            <div class="alert alert-warning" style="margin-bottom:12px">Notez ces codes dans un endroit sûr. Chacun ne sert qu'une fois, si vous perdez votre téléphone. <b>Ils ne seront plus affichés.</b></div>
            <pre style="font-size:1.1rem;line-height:1.8;text-align:center">${r.codes_secours.join('\n')}</pre>
            <div class="modal-footer"><button class="btn btn-primary" onclick="closeModal()">J'ai noté mes codes</button></div>`, { narrow: true });
        } catch (err) { toast(err.message, 'error'); }
      };
    } catch (err) { toast(err.message, 'error'); }
  };
}
window.show2faModal = show2faModal;

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
  // Lancée en parallèle de la vérification du profil pour gagner un aller-retour réseau.
  const pMe = _token ? apiMe().catch(() => null) : null;
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
    const moi = await pMe;
    if (moi) {
      try {
        currentUser = moi;
        localStorage.setItem('gs_user', JSON.stringify(currentUser));
        await startApp();
        return;
      } catch (_) { /* retombe sur la connexion ci-dessous */ }
    }
    // Jeton invalide ou expiré : on nettoie et on retombe sur l'écran de connexion
    localStorage.removeItem('gs_user');
    localStorage.removeItem('gs_tok');
    _token = null;
  }
  initLogin();
}

function afficherEcranLicenceBloquee() {
  $('#licence-screen').style.display = 'flex';
  $('#login-screen').style.display = 'none';
  $('#app').style.display = 'none';
  fetch('/api/aide/info').then(r => r.json()).then(d => { const e = d.editeur || {}; if (e.email && $('#licence-contact-mail')) $('#licence-contact-mail').innerHTML = ' ou ' + '<a href="mailto:' + esc(e.email) + '">' + esc(e.email) + '</a>'; }).catch(() => {});
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
