/* ===================== MODULES (écrans à tuiles, groupés par rubrique — comme l'ERP) ===================== */
const TOUS_ROLES = ['admin','directeur','comptable','enseignant','secretaire','charge_communication','directeur_etudes','parent'];

// Une tuile = { page } (ouvre une page existante) ou { icone, label, action, roles?, superAdmin? }.
const MODULES = {
  scolarite: { icone: '🎓', couleur: '#1d4ed8', titre: 'Scolarité & Pédagogie',
    desc: 'Élèves, classes, notes, emplois du temps, examens, discipline',
    rubriques: [
      { titre: 'Élèves et classes', tuiles: [{page:'eleves'},{page:'eleveDuMois'},{page:'reinscriptions'},{page:'classes'},{page:'salles'}] },
      { titre: 'Enseignement', tuiles: [{page:'notes'},{page:'devoirs'},{page:'emploi'},{page:'seances'},{page:'examens'},{page:'bibliotheque'}] },
      { titre: 'Vie scolaire', tuiles: [{page:'absences'},{page:'pointage'},{page:'discipline'}] },
    ] },
  finances: { icone: '💼', couleur: '#047857', titre: 'Finance-Comptabilité & Paie',
    desc: 'Frais de scolarité, cantine, comptabilité, fournisseurs, achats, paie',
    rubriques: [
      { titre: 'Encaissements', tuiles: [{page:'paiements'},{page:'cantine'},{page:'revision'}] },
      { titre: 'Comptabilité', tuiles: [{page:'comptabilite'},{page:'fournisseurs'}] },
      { titre: 'Achats et logistique', tuiles: [{page:'logistique'}] },
      { titre: 'Paie', tuiles: [{page:'paie'}] },
    ] },
  rh: { icone: '👫', couleur: '#b45309', titre: 'Ressources Humaines',
    desc: 'Personnel, candidatures, recrutement',
    rubriques: [ { titre: 'Personnel', tuiles: [{page:'personnel'},{page:'candidatures'}] } ] },
  communication: { icone: '📢', couleur: '#be185d', titre: 'Communication',
    desc: 'Annonces aux parents, actualités, réseaux',
    rubriques: [ { titre: 'Information et communication', tuiles: [{page:'communication'},{page:'actualites'}] } ] },
  admin: { icone: '🔐', couleur: '#6d28d9', titre: 'Paramètres & Sécurité',
    desc: 'Établissement, utilisateurs, journal d\'audit, sécurité, sauvegarde',
    rubriques: [
      { titre: 'Établissement', tuiles: [
        {icone:'🏫', label:'Établissement (logo, identité)', roles:['admin','directeur'], action:"_versCarteParametres('Paramètres de l\\'établissement')"},
        {icone:'🔒', label:"Seuils d'approbation", roles:['admin','directeur'], action:"_versCarteParametres('Seuils d\\'approbation')"},
        {icone:'🗄️', label:'Conservation des données', roles:['admin','directeur'], action:"_versCarteParametres('Conservation des données')"},
        {page:'ecoles'},
      ] },
      { titre: 'Sécurité et accès', tuiles: [
        {page:'users'},
        {icone:'🔑', label:'Sécurité (2FA)', roles:TOUS_ROLES, action:'show2faModal()'},
        {icone:'🔐', label:'Mot de passe', roles:TOUS_ROLES, action:'showPwdModal()'},
        {page:'journal'},
        {icone:'💾', label:'Sauvegarde', superAdmin:true, action:"_versCarteParametres('Sauvegardes')"},
      ] },
      { titre: 'Aide', tuiles: [{page:'aide'}] },
    ] },
};
const ORDRE_MODULES = ['scolarite','finances','rh','communication','admin'];

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

function _pageAccessible(k) {
  const pg = PAGES[k];
  if (!pg) return false;
  return pg.superAdminOnly ? !!currentUser.est_super_admin : (pg.roles || []).includes(currentUser.role);
}
// Tuiles d'une rubrique visibles pour l'utilisateur courant.
function _tuilesVisibles(rub) {
  return rub.tuiles.map(t0 => {
    if (t0.page) return _pageAccessible(t0.page) ? { icone: PAGES[t0.page].icon, label: t(PAGES[t0.page].labelKey), action: `navigate('${t0.page}')` } : null;
    if (t0.superAdmin) return currentUser.est_super_admin ? t0 : null;
    return (t0.roles || []).includes(currentUser.role) ? t0 : null;
  }).filter(Boolean);
}
function moduleAccessible(cle) {
  return MODULES[cle].rubriques.some(r => _tuilesVisibles(r).length);
}
window.moduleAccessible = moduleAccessible;

function _tuileHtml(t0) {
  return `<div class="hub-tuile" role="button" tabindex="0" onclick="${t0.action}"><div class="hub-ico">${t0.icone}</div>${esc(t0.label)}</div>`;
}

// Grandes cartes de modules (écran d'accueil, comme l'ERP)
function modulesCartesHtml() {
  const cartes = ORDRE_MODULES.filter(moduleAccessible).map(k => {
    const m = MODULES[k];
    return `<div class="hub-carte" style="--couleur:${m.couleur}" role="button" tabindex="0" onclick="navigate('mod_${k}')">
      <div class="hub-carte-ico">${m.icone}</div><div class="hub-carte-titre">${esc(m.titre)}</div><div class="hub-carte-desc">${esc(m.desc)}</div></div>`;
  });
  return cartes.length ? `<div class="hub-cartes">${cartes.join('')}</div>` : '';
}
window.modulesCartesHtml = modulesCartesHtml;

function pageModule(cle) {
  const m = MODULES[cle];
  const onglets = ORDRE_MODULES.filter(moduleAccessible).map(k =>
    `<button class="hub-onglet${k === cle ? ' actif' : ''}" style="--couleur:${MODULES[k].couleur}" onclick="navigate('mod_${k}')">${MODULES[k].icone} ${esc(MODULES[k].titre)}</button>`).join('');
  const rubriques = m.rubriques.map(r => ({ titre: r.titre, tuiles: _tuilesVisibles(r) })).filter(r => r.tuiles.length);
  $('#content').innerHTML = `
    <div class="hub-titre"><h2 style="color:${m.couleur}">${m.icone} ${esc(m.titre)}</h2></div>
    <div class="hub-sous">${esc(m.desc)}</div>
    <div class="hub-onglets">${onglets}</div>
    ${rubriques.length ? rubriques.map(r => `<div class="hub-section">${esc(r.titre)}</div><div class="hub-grid">${r.tuiles.map(_tuileHtml).join('')}</div>`).join('')
      : '<div class="alert alert-info">Aucune fonction de ce module n\'est accessible avec votre profil.</div>'}`;
}
window.pageModule = pageModule;
