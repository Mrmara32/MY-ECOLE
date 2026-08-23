/* ============================================================
   UTILITAIRES UI
============================================================ */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'className') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2).toLowerCase(), v);
    else e.setAttribute(k, v);
  }
  children.flat().forEach(c => c != null && e.append(typeof c === 'string' ? document.createTextNode(c) : c));
  return e;
};

/* ── Escaping ── */
function esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* Échappement pour un texte inséré comme argument JS entre guillemets simples
   à l'intérieur d'un attribut onclick="...('...')" (ex: onclick="fn('${escJs(x)}')").
   esc() seul ne suffit pas : il protège l'attribut HTML, mais une apostrophe réelle
   (très fréquente en français : "d'inscription", "d'accès", "l'école"…) redevient un
   caractère brut une fois l'attribut décodé par le navigateur avant exécution du JS,
   ce qui casse la chaîne JS et empêche silencieusement le clic de fonctionner. */
function escJs(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
    .replace(/\\/g,'\\\\').replace(/'/g,"\\'")
    .replace(/\n/g,'\\n').replace(/\r/g,'\\r');
}

/* Génère un QR code en SVG autonome, entièrement local (bibliothèque embarquée,
   aucune requête réseau). Remplace l'ancien recours à une API externe (api.qrserver.com)
   qui échouait silencieusement sans connexion internet, provoquant un mauvais rendu
   sur les documents imprimés. */
function genererQrSvg(texte, cellSize = 4, margin = 4) {
  try {
    const qr = qrcode(0, 'M');
    qr.addData(texte);
    qr.make();
    return qr.createSvgTag(cellSize, margin);
  } catch (e) {
    console.error('Erreur génération QR code:', e);
    return '';
  }
}
window.genererQrSvg = genererQrSvg;

/* ── Formatage ── */
const fmtMoney = n => Number(n || 0).toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + ' GNF';
const fmtDate  = d => { if (!d) return '—'; try { return new Date(d).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' }); } catch { return d; } };
const fmtDateLong = d => { if (!d) return '—'; try { return new Date(d).toLocaleDateString('fr-FR', { weekday:'short', day:'2-digit', month:'long', year:'numeric' }); } catch { return d; } };
const today = () => new Date().toISOString().split('T')[0];
const anneeCourante = () => { const n=new Date(); const y=n.getMonth()>=8?n.getFullYear():n.getFullYear()-1; return `${y}-${y+1}`; };
const moisCourant = () => new Date().toISOString().slice(0,7);

function jresteText(dateRemise) {
  const diff = Math.ceil((new Date(dateRemise) - new Date()) / 86400000);
  if (diff < 0) return { txt: `${Math.abs(diff)}j de retard`, cls: 'bdg-err' };
  if (diff === 0) return { txt: 'Aujourd\'hui', cls: 'bdg-warn' };
  if (diff <= 2) return { txt: `${diff}j restant`, cls: 'bdg-warn' };
  return { txt: `${diff}j restants`, cls: 'bdg-ok' };
}

/* ── Toast ── */
function toast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = 'toast ' + (type === 'success' ? 'ok' : type === 'error' ? 'err' : type === 'warning' ? 'warn' : '');
  t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

/* ── Modal (déplaçable + réductible) ── */
let _modalDragOffset = null;
/* ===================== FENÊTRES MODALES — PLUSIEURS À LA FOIS =====================
   Une seule fenêtre est "active" (premier plan, ids canoniques #modal-bg/#modal-box/…),
   ce qui garantit que tout le code existant ($('#modal-body')=…, closeModal(), etc.)
   continue de fonctionner sans changement. Les autres fenêtres ouvertes restent dans le
   DOM (donc leurs gestionnaires d'événements — attachés par référence, pas par id —
   restent pleinement fonctionnels), simplement dépourvues de leurs ids canoniques et
   réduites dans le plateau #modal-tray, d'où on peut les rappeler au premier plan. */
let _modalMinimized = false;
let _minimizedStack = []; // [{ bg: HTMLElement, title: string }]

function _elementsCanoniques(bg) {
  return {
    bg,
    box: bg.querySelector('.modal-box-el'),
    head: bg.querySelector('.modal-head-el'),
    title: bg.querySelector('.modal-title-el'),
    body: bg.querySelector('.modal-body-el'),
    maxBtn: bg.querySelector('.modal-maxbtn-el'),
  };
}
function _appliquerIdsCanoniques(bg) {
  const el = _elementsCanoniques(bg);
  el.bg.id = 'modal-bg'; el.box.id = 'modal-box'; el.head.id = 'modal-head';
  el.title.id = 'modal-title'; el.body.id = 'modal-body';
  if (el.maxBtn) el.maxBtn.id = 'modal-maximize-btn';
}
function _retirerIdsCanoniques(bg) {
  const el = _elementsCanoniques(bg);
  [el.bg, el.box, el.head, el.title, el.body, el.maxBtn].forEach(e => e && e.removeAttribute('id'));
}
function _construireModalBg() {
  const bg = document.createElement('div');
  bg.style.display = 'none';
  bg.innerHTML = `
    <div class="modal-box-el" onclick="event.stopPropagation()">
      <div class="modal-head modal-head-el">
        <h3 class="modal-title-el">—</h3>
        <div class="flex gap-2">
          <button class="icon-btn" onclick="minimizeModal(event)" title="Réduire">━</button>
          <button class="icon-btn modal-maxbtn-el" onclick="toggleMaximizeModal(event)" title="Agrandir">⛶</button>
          <button class="icon-btn" onclick="closeModal(event)" title="Fermer">✕</button>
        </div>
      </div>
      <div class="modal-body modal-body-el"></div>
    </div>`;
  document.body.appendChild(bg);
  return bg;
}
/* Retrouve l'élément #modal-bg concerné par un clic sur un bouton de contrôle
   (Réduire/Agrandir/Fermer), pour que ces boutons agissent toujours sur LEUR
   propre fenêtre même si elle n'est plus "active" au sens des ids canoniques. */
function _modalBgDepuisEvenement(event) {
  if (event && event.currentTarget) {
    const bg = event.currentTarget.closest('#modal-bg') || event.currentTarget.closest('div[style*="display"]');
    if (bg) return bg;
  }
  return $('#modal-bg');
}
function _rendreTray() {
  const tray = $('#modal-tray');
  if (!tray) return;
  tray.innerHTML = _minimizedStack.map((m, i) => `
    <div class="modal-tray-pill" onclick="restaurerModal(${i})">
      <span>${esc(m.title)}</span>
      <button class="icon-btn" onclick="event.stopPropagation();fermerDepuisTray(${i})" title="Fermer">✕</button>
    </div>`).join('');
}

function openModal(title, html, { wide = false, narrow = false } = {}) {
  // Motif très répandu dans l'application : une fenêtre se "rafraîchit" en se
  // rouvrant elle-même après une action (même titre) — ce n'est PAS une nouvelle
  // fenêtre distincte, juste une mise à jour de son contenu en place. Seule une
  // fenêtre au titre VRAIMENT différent passe à l'arrière-plan (plateau).
  const bgActuel = document.getElementById('modal-bg');
  const estRafraichissement = bgActuel && bgActuel.style.display !== 'none' && bgActuel.dataset.titre === title;

  let bg;
  if (estRafraichissement) {
    bg = bgActuel;
  } else {
    if (bgActuel && bgActuel.style.display !== 'none' && !_modalMinimized) {
      _mettreEnArrierePlan(bgActuel);
    }
    bg = _construireModalBg();
    _appliquerIdsCanoniques(bg);
  }
  const box = $('#modal-box');
  box.className = 'modal-box-el' + (wide ? ' wide' : narrow ? ' narrow' : '');
  $('#modal-title').textContent = title;
  $('#modal-body').innerHTML = html;
  bg.style.display = 'flex';
  bg.dataset.titre = title;
  _modalMinimized = false;
  initModalDrag();
}

function _mettreEnArrierePlan(bg) {
  const titre = bg.dataset.titre || _elementsCanoniques(bg).title?.textContent || '—';
  _retirerIdsCanoniques(bg);
  bg.style.display = 'none';
  bg.classList.remove('bg-transparent');
  _minimizedStack.push({ bg, title: titre });
  _rendreTray();
}

function closeModal(event) {
  const bg = _modalBgDepuisEvenement(event);
  if (!bg) return;
  if (bg.id === 'modal-bg' && _cameraStream) { _cameraStream.getTracks().forEach(t => t.stop()); _cameraStream = null; }
  bg.remove();
  _minimizedStack = _minimizedStack.filter(m => m.bg !== bg);
  _rendreTray();
  if (bg.id === 'modal-bg') _modalMinimized = false;
}
window.closeModal = closeModal;

/* Agrandit la fenêtre modale active pour occuper (presque) tout l'écran, ou la
   restaure à sa taille normale (point 11 du cahier des charges) */
function toggleMaximizeModal(event) {
  const bg = _modalBgDepuisEvenement(event);
  const box = bg.querySelector('.modal-box-el');
  const btn = bg.querySelector('.modal-maxbtn-el');
  const nowMaximized = box.classList.toggle('maximized');
  if (nowMaximized) {
    box.classList.remove('dragging-mode');
    box.style.left = ''; box.style.top = '';
    if (btn) { btn.textContent = '❐'; btn.title = 'Restaurer'; }
  } else {
    if (btn) { btn.textContent = '⛶'; btn.title = 'Agrandir'; }
  }
}
window.toggleMaximizeModal = toggleMaximizeModal;

/* Réduit une fenêtre dans le plateau, sans en fermer d'autres déjà réduites
   (point 3 du cahier des charges : plusieurs fenêtres ouvertes à la fois) */
function minimizeModal(event) {
  const bg = _modalBgDepuisEvenement(event);
  _mettreEnArrierePlan(bg);
  if (bg.id === 'modal-bg' || !document.getElementById('modal-bg')) _modalMinimized = true;
}
window.minimizeModal = minimizeModal;

/* Rappelle au premier plan une fenêtre du plateau ; la fenêtre active éventuelle
   passe elle-même dans le plateau (permutation), aucune n'est perdue. */
function restaurerModal(index) {
  const entree = _minimizedStack[index];
  if (!entree) return;
  const bgActuel = document.getElementById('modal-bg');
  if (bgActuel && bgActuel !== entree.bg) _mettreEnArrierePlan(bgActuel);

  _minimizedStack = _minimizedStack.filter((_, i) => i !== index);
  _rendreTray();
  _appliquerIdsCanoniques(entree.bg);
  entree.bg.style.display = 'flex';
  entree.bg.classList.remove('bg-transparent');
  _modalMinimized = false;
  initModalDrag();
}
window.restaurerModal = restaurerModal;

function fermerDepuisTray(index) {
  const entree = _minimizedStack[index];
  if (!entree) return;
  entree.bg.remove();
  _minimizedStack = _minimizedStack.filter((_, i) => i !== index);
  _rendreTray();
}
window.fermerDepuisTray = fermerDepuisTray;

// Alias conservés pour compatibilité (anciens noms encore référencés ailleurs)
function restoreModal() { if (_minimizedStack.length) restaurerModal(_minimizedStack.length - 1); }
function closeModalFromMinimized() { if (_minimizedStack.length) fermerDepuisTray(_minimizedStack.length - 1); }
window.closeModalFromMinimized = closeModalFromMinimized;

/* Rend la fenêtre déplaçable en glissant sur son en-tête (souris + tactile) */
let _modalDragInitialized = false;
let _dragGlobalInitialized = false;
let _currentDragBox = null;

function initModalDrag() {
  // Ré-attaché à chaque nouvelle fenêtre (chacune a sa propre tête/boîte, créées
  // dynamiquement pour permettre plusieurs fenêtres ouvertes en même temps).
  const head = $('#modal-head');
  const box = $('#modal-box');
  if (!head || !box) return;

  const startDrag = (clientX, clientY) => {
    if (box.classList.contains('maximized')) return; // pas de déplacement en mode agrandi
    const rect = box.getBoundingClientRect();
    _modalDragOffset = { x: clientX - rect.left, y: clientY - rect.top };
    _currentDragBox = box;
    if (!box.classList.contains('dragging-mode')) {
      box.classList.add('dragging-mode');
      box.style.left = rect.left + 'px';
      box.style.top = rect.top + 'px';
    }
  };

  head.addEventListener('mousedown', e => {
    if (e.target.closest('button')) return; // ne pas démarrer le drag depuis les boutons
    startDrag(e.clientX, e.clientY);
  });
  head.addEventListener('touchstart', e => {
    if (e.target.closest('button')) return;
    const t = e.touches[0];
    startDrag(t.clientX, t.clientY);
  }, { passive: true });

  // Les écouteurs au niveau du document (déplacement/relâchement) ne doivent en
  // revanche être attachés qu'UNE seule fois : ils agissent toujours sur la boîte
  // actuellement en cours de glissement, via _currentDragBox.
  if (_dragGlobalInitialized) return;
  _dragGlobalInitialized = true;

  const moveDrag = (clientX, clientY) => {
    if (!_modalDragOffset || !_currentDragBox) return;
    const maxLeft = window.innerWidth - 60;
    const maxTop = window.innerHeight - 40;
    let left = clientX - _modalDragOffset.x;
    let top = clientY - _modalDragOffset.y;
    left = Math.max(-_currentDragBox.offsetWidth + 80, Math.min(left, maxLeft));
    top = Math.max(0, Math.min(top, maxTop));
    _currentDragBox.style.left = left + 'px';
    _currentDragBox.style.top = top + 'px';
  };
  const endDrag = () => { _modalDragOffset = null; _currentDragBox = null; };

  document.addEventListener('mousemove', e => moveDrag(e.clientX, e.clientY));
  document.addEventListener('mouseup', endDrag);
  document.addEventListener('touchmove', e => {
    if (!_modalDragOffset) return;
    const t = e.touches[0];
    moveDrag(t.clientX, t.clientY);
  }, { passive: true });
  document.addEventListener('touchend', endDrag);
}

/* ── Confirm ── */
const confirmDel = msg => confirm(msg || 'Supprimer cet élément ?');

/* ── Empty state ── */
const emptyHtml = (icon, title, hint = '') =>
  `<div class="empty"><div class="empty-icon">${icon}</div><div class="empty-title">${esc(title)}</div>${hint ? `<div class="empty-hint">${esc(hint)}</div>` : ''}</div>`;

/* ── Badge note ── */
function noteBadge(n) {
  if (n == null) return '<span class="badge bdg-gray">—</span>';
  const c = n >= 16 ? 'bdg-ok' : n >= 12 ? 'bdg-info' : n >= 10 ? 'bdg-warn' : 'bdg-err';
  return `<span class="badge ${c}">${Number(n).toFixed(2)}</span>`;
}

/* ── Photo d'un élève ── */
function elevePhoto(e, size = 36) {
  if (e.photo_url) return `<img src="${esc(e.photo_url)}" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;border:2px solid #E5E7EB" onerror="this.style.display='none'">`;
  const initials = ((e.prenom||'?').charAt(0) + (e.nom||'?').charAt(0)).toUpperCase();
  return `<div class="avatar" style="width:${size}px;height:${size}px;font-size:${Math.round(size*0.4)}px">${esc(initials)}</div>`;
}

/* ── Options select ── */
function optionsHtml(values, selected = '', withEmpty = true) {
  const e = withEmpty ? '<option value="">— Sélectionner —</option>' : '';
  return e + values.map(v => {
    const val = typeof v === 'object' ? v.value : v;
    const lbl = typeof v === 'object' ? v.label : v;
    return `<option value="${esc(val)}" ${val == selected ? 'selected' : ''}>${esc(lbl)}</option>`;
  }).join('');
}

/* ── Constantes partagées ── */
/* CLASSES est maintenant chargée dynamiquement depuis l'API (voir refreshClasses() dans app.js).
   On garde un tableau vide par défaut ; il est rempli juste après la connexion. */
let CLASSES = [];
let CLASSES_FULL = []; // objets complets {id, nom, cycle, ordre, active}
async function refreshClasses() {
  try {
    CLASSES_FULL = await apiGetClassesFull();
    CLASSES = CLASSES_FULL.map(c => c.nom);
  } catch(e) { console.warn('Impossible de charger les classes', e); }
}
function cycleDeClasse(nom) {
  const c = CLASSES_FULL.find(c => c.nom === nom);
  return c ? c.cycle : null;
}
const CYCLE_LABELS = { maternelle:'Maternelle', primaire:'Primaire', college:'Collège', lycee:'Lycée' };
const MATIERES = ['Mathématiques','Français','Anglais','Histoire-Géographie','SVT','Physique-Chimie','EPS','Arts Plastiques','Musique','Éducation Civique','Philosophie','Espagnol','Informatique','Arabe'];
const POSTES = ['Directeur Général','Directeur des Études','Enseignant','Comptable','Secrétaire','Surveillant','Documentaliste','Personnel de service','Chauffeur','Infirmier(ère)','Autre'];
const GROUPES_SANGUINS = ['A+','A-','B+','B-','AB+','AB-','O+','O-','Inconnu'];
const MOYENS_PAIEMENT = ['Espèces','Virement bancaire','Chèque','Mobile Money (Orange)','Mobile Money (MTN)','Mobile Money (Moov)'];
const CAT_ENTREE = ["Frais de scolarité","Frais d'inscription","Frais de réinscription","Cantine","Cours de révision","Transport scolaire","Uniformes / Fournitures","Autres recettes"];
const CAT_SORTIE = ['Salaires','Fournitures scolaires','Loyer','Électricité / Eau / Internet','Entretien / Réparations','Matériel pédagogique','Transport','Alimentation cantine','Impôts / Taxes','Autres dépenses'];
const JOURS = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
let CRENEAUX = ['07h30 - 09h30','09h30 - 11h30','11h30 - 13h30','14h00 - 16h00','16h00 - 18h00'];
async function refreshCreneaux() {
  try {
    const s = await apiGetSettings();
    if (s.creneaux_horaires) CRENEAUX = JSON.parse(s.creneaux_horaires);
  } catch(e) { console.warn('Impossible de charger les créneaux horaires', e); }
}
const COULEURS_EDT = ['#2563EB','#059669','#D97706','#7C3AED','#DC2626','#0891B2','#0D9488','#B45309','#6366F1'];
const ROLES = { admin:'Administrateur', directeur:'Directeur', directeur_etudes:'Directeur des Études', comptable:'Comptable', enseignant:'Enseignant', secretaire:'Secrétaire', charge_communication:'Chargé de communication' };

/* ── Couleur EDT par matière ── */
const _matColors = {};
function matColor(matiere) {
  if (!_matColors[matiere]) {
    const idx = Object.keys(_matColors).length % COULEURS_EDT.length;
    _matColors[matiere] = COULEURS_EDT[idx];
  }
  return _matColors[matiere];
}

/* ── Mini spinner ── */
const loadingHtml = '<div style="text-align:center;padding:40px;color:var(--g5);font-size:13px">Chargement…</div>';

/* ============================================================
   CONVERSION D'UN MONTANT EN TOUTES LETTRES (français)
   Utilisé sur tous les documents financiers imprimés (reçus, bulletins…)
============================================================ */
function nombreEnLettresFr(nombre) {
  nombre = Math.round(nombre);
  if (nombre === 0) return 'zéro';
  if (nombre < 0) return 'moins ' + nombreEnLettresFr(-nombre);

  const UNITES = ['zéro','un','deux','trois','quatre','cinq','six','sept','huit','neuf','dix',
    'onze','douze','treize','quatorze','quinze','seize','dix-sept','dix-huit','dix-neuf'];
  const DIZAINES = ['','','vingt','trente','quarante','cinquante','soixante','soixante-dix','quatre-vingt','quatre-vingt-dix'];

  function deuxChiffres(n, suivi) {
    if (n < 20) return UNITES[n];
    const d = Math.floor(n / 10), u = n % 10;
    if (d === 7 || d === 9) {
      const base = d === 7 ? 'soixante' : 'quatre-vingt';
      if (u === 1 && d === 7) return base + ' et onze';
      return base + '-' + UNITES[10 + u];
    }
    if (u === 0) return (d === 8 && !suivi) ? 'quatre-vingts' : DIZAINES[d];
    if (u === 1 && d !== 8) return DIZAINES[d] + ' et un';
    return DIZAINES[d] + '-' + UNITES[u];
  }

  function troisChiffres(n, suivi) {
    const c = Math.floor(n / 100), reste = n % 100;
    let s = '';
    if (c > 0) {
      s = (c === 1 ? 'cent' : UNITES[c] + ' cent');
      if (c > 1 && reste === 0 && !suivi) s += 's';
      if (reste > 0) s += ' ' + deuxChiffres(reste, suivi);
    } else {
      s = deuxChiffres(reste, suivi);
    }
    return s.trim();
  }

  const tranches = [
    { valeur: 1000000000, singulier: 'milliard', pluriel: 'milliards' },
    { valeur: 1000000, singulier: 'million', pluriel: 'millions' },
    { valeur: 1000, singulier: 'mille', pluriel: 'mille' },
  ];

  let reste = nombre;
  const mots = [];
  for (const tranche of tranches) {
    const q = Math.floor(reste / tranche.valeur);
    if (q > 0) {
      const suiteRestante = reste % tranche.valeur;
      if (tranche.valeur === 1000) {
        mots.push(q === 1 ? 'mille' : troisChiffres(q, true) + ' mille');
      } else {
        const base = q === 1 ? 'un' : troisChiffres(q, true);
        mots.push(base + ' ' + (q > 1 ? tranche.pluriel : tranche.singulier));
      }
      reste = suiteRestante;
    }
  }
  if (reste > 0 || mots.length === 0) mots.push(troisChiffres(reste, false));

  return mots.join(' ').replace(/\s+/g, ' ').trim();
}

function montantEnLettres(montant) {
  const lettres = nombreEnLettresFr(montant);
  const capital = lettres.charAt(0).toUpperCase() + lettres.slice(1);
  return `${capital} francs guinéens`;
}
window.nombreEnLettresFr = nombreEnLettresFr;
window.montantEnLettres = montantEnLettres;

/* ============================================================
   REÇU DE PAIEMENT GÉNÉRIQUE (points 5/6 du cahier des charges)
   Utilisable pour : versements scolarité, cantine, cours de révision,
   et paiements à un prestataire de service (dépenses).
============================================================ */

/* Lance l'impression d'une fenêtre seulement une fois les polices REELLEMENT
   chargées (document.fonts.ready), au lieu d'un délai fixe arbitraire qui peut
   s'avérer trop court sur une connexion lente — auquel cas la police demandée
   n'est pas encore prête et le navigateur retombe sur une police de secours du
   système, ce qui peut afficher des caractères incorrects (ex: accents mal
   rendus) sur les documents imprimés. Une limite de sécurité (2.5s) évite un
   blocage si jamais l'événement de chargement ne se déclenche pas. */
function imprimerFenetre(win) {
  let dejaImprime = false;
  const lancer = () => {
    if (dejaImprime) return;
    dejaImprime = true;
    win.focus();
    win.print();
  };
  try {
    if (win.document.fonts && win.document.fonts.ready) {
      win.document.fonts.ready.then(lancer).catch(lancer);
    } else {
      lancer();
    }
  } catch (_) {
    lancer();
  }
  setTimeout(lancer, 2500); // filet de sécurité si l'événement ne se déclenche jamais
}

async function imprimerRecu({ type, nom, description, montant, date, moyenPaiement, reference, recuPar }) {
  const settings = await apiGetSettings();
  const numeroRecu = reference || ('REC-' + Date.now().toString(36).toUpperCase());
  // La mention de non-remboursement ne concerne que les paiements REÇUS de la part
  // des élèves/parents (frais d'inscription, scolarité…) — jamais les paiements
  // versés À un enseignant, un employé ou un prestataire (avances, salaires, etc.)
  const afficherMentionInscription = type !== 'sortie';
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Reçu — ${esc(nom)}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:Georgia,'Times New Roman',Arial,Helvetica,sans-serif;font-size:13px;color:#1F2937;margin:0;padding:26px;background:#F3F4F6}
    .recu{max-width:520px;margin:0 auto;background:#fff;border:1px solid #D1D5DB;border-radius:4px;padding:0;
      box-shadow:0 4px 18px rgba(0,0,0,.08)}
    .bandeau{height:6px;display:flex}
    .bandeau div{flex:1}
    .inner{padding:28px 32px}
    .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111827;padding-bottom:16px;margin-bottom:20px}
    .header .ecole{display:flex;gap:12px;align-items:center}
    .header img{max-height:50px}
    .header h1{font-size:15px;margin:0 0 2px;color:#111827;font-family:Arial,sans-serif;font-weight:700}
    .header p{margin:1px 0;font-size:10.5px;color:#6B7280;font-family:Arial,sans-serif}
    .header .recu-meta{text-align:right;font-family:Arial,sans-serif}
    .header .recu-meta .num{font-size:11px;color:#6B7280}
    .header .recu-meta .num b{color:#111827;font-family:monospace}
    .titre-recu{text-align:center;font-size:16px;font-weight:700;margin:0 0 22px;color:#111827;
      text-transform:uppercase;letter-spacing:2px;font-family:Arial,sans-serif}
    .tbl{width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:12.5px;margin-bottom:20px}
    .tbl td{padding:8px 0;border-bottom:1px solid #F0F1F3;vertical-align:top}
    .tbl td:first-child{color:#6B7280;width:40%}
    .tbl td:last-child{font-weight:700;color:#111827;text-align:right}
    .montant-box{background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;padding:18px 20px;margin-bottom:20px;font-family:Arial,sans-serif}
    .montant-box .lbl{font-size:10.5px;color:#6B7280;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
    .montant-box .chiffres{font-size:24px;font-weight:800;color:#111827;font-family:monospace;margin-bottom:8px}
    .montant-box .lettres{font-size:11.5px;color:#374151;font-style:italic;border-top:1px dashed #D1D5DB;padding-top:8px}
    .sig{margin-top:38px;display:flex;justify-content:space-between;align-items:flex-end;font-family:Arial,sans-serif}
    .sig .sig-col{width:44%;text-align:center}
    .sig .cachet-img{max-height:55px;max-width:110px;display:block;margin:0 auto 2px}
    .sig .signature-img{max-height:35px;max-width:110px;display:block;margin:0 auto 2px}
    .sig .sig-label{border-top:1px solid #9CA3AF;padding-top:6px;font-size:10.5px;color:#4B5563;margin-top:6px}
    .footer-note{text-align:center;font-size:10px;color:#9CA3AF;margin-top:24px;font-family:Arial,sans-serif}
    .mention-legale{text-align:center;font-size:10px;color:#92400E;background:#FFFBEB;border:1px solid #FDE68A;
      border-radius:6px;padding:9px 12px;margin-top:16px;line-height:1.45;font-family:Arial,sans-serif}
    .credit{text-align:center;font-size:8.5px;color:#C0C4CC;margin-top:10px;font-family:Arial,sans-serif}
  </style></head><body>
  <div class="recu">
    <div class="bandeau"><div style="background:#CE1126"></div><div style="background:#FCD116"></div><div style="background:#009460"></div></div>
    <div class="inner">
      <div class="header">
        <div class="ecole">
          ${settings.ecole_logo?`<img src="${settings.ecole_logo}">`:''}
          <div>
            <h1>${esc(settings.ecole_nom||'Groupe Scolaire Elhadji Mountaga Djély')}</h1>
            <p>${esc(settings.ecole_adresse||'')}</p>
            ${settings.ecole_telephone?`<p>Tél : ${esc(settings.ecole_telephone)}</p>`:''}
          </div>
        </div>
        <div class="recu-meta">
          <div class="num">N° <b>${esc(numeroRecu)}</b></div>
          <div class="num">${fmtDate(date)}</div>
        </div>
      </div>
      <div class="titre-recu">Reçu de paiement</div>
      <table class="tbl">
        <tr><td>${type==='sortie'?'Bénéficiaire':'Reçu de'}</td><td>${esc(nom)}</td></tr>
        <tr><td>Motif</td><td>${esc(description)}</td></tr>
        <tr><td>Moyen de paiement</td><td>${esc(moyenPaiement||'Espèces')}</td></tr>
        ${recuPar ? `<tr><td>${type==='sortie'?'Payé par':'Reçu par'}</td><td>${esc(recuPar)}</td></tr>` : ''}
      </table>
      <div class="montant-box">
        <div class="lbl">${type==='sortie'?'Montant versé':'Montant reçu'}</div>
        <div class="chiffres">${fmtMoney(montant)}</div>
        <div class="lettres">Arrêté la présente somme à : ${montantEnLettres(montant)}.</div>
      </div>
      <div class="sig">
        <div class="sig-col">
          ${settings.ecole_cachet?`<img class="cachet-img" src="${settings.ecole_cachet}">`:''}
          ${settings.signature_directeur?`<img class="signature-img" src="${settings.signature_directeur}">`:''}
          <div class="sig-label">Signature (École)</div>
        </div>
        <div class="sig-col"><div class="sig-label" style="margin-top:auto">Signature (${type==='sortie'?'Bénéficiaire':'Payeur'})</div></div>
      </div>
      ${afficherMentionInscription ? `<div class="mention-legale"><strong>Important :</strong> Toute somme versée est due et non remboursable après la validation de l'inscription.</div>` : ''}
      <div class="footer-note">Ce reçu fait foi de paiement — à conserver</div>
      <div class="credit">Application développée par Actif System Groupe — Tél : 661-97-43-43</div>
    </div>
  </div>
  </body></html>`;
  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  imprimerFenetre(win);
}
window.imprimerRecu = imprimerRecu;

/* ============================================================
   CAPTURE PHOTO DIRECTE (webcam ordinateur ou caméra téléphone)
   Utilisé partout où une photo peut être ajoutée (élèves, personnel, badges…)
============================================================ */
function photoCaptureWidgetHtml(inputIdPrefix) {
  return `
    <div class="flex gap-2 flex-wrap">
      <label class="btn btn-outline btn-sm" style="cursor:pointer">
        📁 Choisir un fichier
        <input type="file" id="${inputIdPrefix}-file" accept="image/*" style="display:none">
      </label>
      <button type="button" class="btn btn-outline btn-sm" onclick="openCameraCapture('${inputIdPrefix}')">📷 Prendre une photo</button>
      <label class="btn btn-outline btn-sm" style="cursor:pointer">
        📱 Caméra du téléphone
        <input type="file" id="${inputIdPrefix}-mobile" accept="image/*" capture="environment" style="display:none">
      </label>
    </div>`;
}

let _cameraStream = null;
async function openCameraCapture(targetPrefix) {
  openModal('📷 Prendre une photo', `
    <div style="text-align:center">
      <video id="cam-video" autoplay playsinline style="width:100%;max-width:480px;border-radius:8px;background:#000"></video>
      <div class="mt-3 flex gap-2 justify-between" style="justify-content:center">
        <button class="btn btn-primary" onclick="capturerPhoto('${targetPrefix}')">📸 Capturer</button>
        <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      </div>
      <div id="cam-error" class="alert alert-danger mt-3" style="display:none"></div>
    </div>`, { narrow: true });
  try {
    _cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
    $('#cam-video').srcObject = _cameraStream;
  } catch(err) {
    $('#cam-error').style.display = 'block';
    $('#cam-error').textContent = "Impossible d'accéder à la caméra : " + err.message + " (vérifiez les autorisations du navigateur)";
  }
}

function capturerPhoto(targetPrefix) {
  const video = $('#cam-video');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  canvas.toBlob(blob => {
    if (_cameraStream) { _cameraStream.getTracks().forEach(t => t.stop()); _cameraStream = null; }
    closeModal();
    const file = new File([blob], 'photo-capturee.jpg', { type: 'image/jpeg' });
    window.dispatchEvent(new CustomEvent('photo-captured-' + targetPrefix, { detail: file }));
  }, 'image/jpeg', 0.92);
}

// Note : la fermeture de la caméra (si active) est déjà gérée directement dans closeModal() ci-dessus.
window.openCameraCapture = openCameraCapture;
window.capturerPhoto = capturerPhoto;

/* Branche les 3 méthodes (fichier / webcam / mobile) sur un callback commun */
function wirePhotoCapture(inputIdPrefix, onFile) {
  $(`#${inputIdPrefix}-file`)?.addEventListener('change', e => { if (e.target.files[0]) onFile(e.target.files[0]); });
  $(`#${inputIdPrefix}-mobile`)?.addEventListener('change', e => { if (e.target.files[0]) onFile(e.target.files[0]); });
  window.addEventListener('photo-captured-' + inputIdPrefix, e => onFile(e.detail));
}

/* ============================================================
   TRI DE TABLEAU RÉUTILISABLE — clic sur un en-tête <th> pour trier.
   theadSelector : sélecteur CSS du <thead> (ou de la ligne d'en-têtes)
   dataGetter    : fonction retournant le tableau de données ACTUEL (après filtre/recherche)
   renderFn      : fonction qui réaffiche les lignes à partir des données triées
   keyMap        : tableau parallèle aux <th>, chaque entrée étant soit :
                   - null/undefined (colonne non triable, ex: Actions)
                   - une chaîne = nom de propriété à utiliser pour trier
                   - une fonction(row) => valeur comparable
============================================================ */
function makeSortableTable(theadSelector, dataGetter, renderFn, keyMap) {
  const thead = document.querySelector(theadSelector);
  if (!thead) return;
  const ths = thead.querySelectorAll('th');
  const state = { idx: null, dir: 1 };

  ths.forEach((th, idx) => {
    if (keyMap[idx] === null || keyMap[idx] === undefined) return;
    th.style.cursor = 'pointer';
    th.style.userSelect = 'none';
    if (!th.querySelector('.sort-ind')) {
      th.innerHTML += ' <span class="sort-ind" style="opacity:.35;font-size:10px">⇅</span>';
    }
    th.onclick = () => {
      state.dir = (state.idx === idx) ? state.dir * -1 : 1;
      state.idx = idx;
      const data = dataGetter();
      const keyFn = typeof keyMap[idx] === 'function' ? keyMap[idx] : (row => row ? row[keyMap[idx]] : null);
      data.sort((a, b) => {
        let va = keyFn(a), vb = keyFn(b);
        if (va == null) va = '';
        if (vb == null) vb = '';
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return -1 * state.dir;
        if (va > vb) return 1 * state.dir;
        return 0;
      });
      renderFn(data);
      ths.forEach((t, i) => {
        const ind = t.querySelector('.sort-ind');
        if (ind) ind.textContent = i === idx ? (state.dir === 1 ? '▲' : '▼') : '⇅';
      });
    };
  });
}

/* ── Champ "motif de la modification" réutilisable (traçabilité — point 1) ──
   À insérer dans tout formulaire d'ÉDITION (pas de création). Le champ est
   obligatoire : chaque modification doit être justifiée pour le journal d'audit. */
const motifFieldHtml = () => `
  <div class="fg">
    <label>Motif de la modification*</label>
    <input name="motif" required placeholder="Ex : correction d'une erreur de saisie, mise à jour suite à un changement…">
  </div>`;
