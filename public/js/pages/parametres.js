/* ===================== PARAMÈTRES & SÉCURITÉ (hub à icônes, comme l'ERP) ===================== */
function _versCarteParametres(titre) {
  navigate('settings');
  let essais = 0;
  const chercher = () => {
    const carte = [...document.querySelectorAll('#content .card-title')].find(el => el.textContent.includes(titre));
    if (carte) carte.closest('.card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    else if (++essais < 15) setTimeout(chercher, 200);
  };
  setTimeout(chercher, 250);
}
window._versCarteParametres = _versCarteParametres;

function pageParametres() {
  const admin = currentUser.role === 'admin';
  const tuile = (ico, label, action) => `<div class="hub-tuile" role="button" tabindex="0" onclick="${action}"><div class="hub-ico">${ico}</div>${esc(label)}</div>`;
  const sections = [
    { titre: 'Établissement', tuiles: [
      tuile('🏫', "Établissement (logo, identité)", "_versCarteParametres('Paramètres de l\\'établissement')"),
      tuile('🔒', "Seuils d'approbation", "_versCarteParametres('Seuils d\\'approbation')"),
      tuile('🗄️', 'Conservation des données', "_versCarteParametres('Conservation des données')"),
    ] },
    { titre: 'Sécurité et accès', tuiles: [
      admin ? tuile('👥', 'Utilisateurs et droits', "navigate('users')") : '',
      tuile('🔑', 'Sécurité (2FA)', 'show2faModal()'),
      tuile('🔐', 'Mot de passe', 'showPwdModal()'),
      admin ? tuile('🕵️', "Journal d'audit", "navigate('journal')") : '',
      currentUser.est_super_admin ? tuile('💾', 'Sauvegarde', "_versCarteParametres('Sauvegardes')") : '',
    ] },
    { titre: 'Aide', tuiles: [
      tuile('🛟', 'Aide et support', "navigate('aide')"),
      tuile('ℹ️', 'À propos', "navigate('aide')"),
    ] },
  ];
  $('#content').innerHTML = `
    <div class="hub-nav">
      <button class="btn btn-outline btn-sm" onclick="retourPage()">← Retour</button>
      <button class="btn btn-outline btn-sm" onclick="navigate('dashboard')">🏠 Accueil</button>
    </div>
    <div class="hub-titre"><h2>🔐 Paramètres & Sécurité</h2></div>
    <div class="hub-sous">Établissement, utilisateurs, journal d'audit, sécurité et sauvegarde</div>
    ${sections.map(sec => `<div class="hub-section">${esc(sec.titre)}</div><div class="hub-grid">${sec.tuiles.join('')}</div>`).join('')}`;
}
window.pageParametres = pageParametres;
