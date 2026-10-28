document.addEventListener('keydown', e => { if (e.key === 'Escape') fermerArticle(); });
;
document.getElementById('year').textContent = new Date().getFullYear();

// Code établissement détecté depuis l'URL (/ecole/CODE/...) — permet à ce même site
// vitrine de servir plusieurs écoles clientes, chacune avec son propre contenu.
function codeEcoleDepuisURL() {
  const m = window.location.pathname.match(/^\/ecole\/([^/]+)/);
  return m ? m[1] : null;
}
const CODE_ECOLE = codeEcoleDepuisURL();
function avecCodeEcole(url) {
  if (!CODE_ECOLE) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}ecole=${encodeURIComponent(CODE_ECOLE)}`;
}
// Les liens vers les autres pages publiques (préinscription, candidature) doivent
// rester dans le contexte de la même école lors de la navigation.
if (CODE_ECOLE) {
  document.querySelectorAll('a[href="/postuler.html"]').forEach(a => a.href = `/ecole/${CODE_ECOLE}/postuler`);
  document.querySelectorAll('a[href="/preinscription.html"]').forEach(a => a.href = `/ecole/${CODE_ECOLE}/preinscription`);
  // « Espace personnel » : la page de connexion s'ouvre avec le code de CETTE école déjà rempli.
  document.querySelectorAll('a.staff-link[href="/"]').forEach(a => a.href = `/?ecole=${encodeURIComponent(CODE_ECOLE)}`);
}

async function chargerInfosEcole() {
  try {
    const res = await fetch(avecCodeEcole('/api/settings'));
    if (!res.ok) return;
    const s = await res.json();
    if (s.ecole_nom) {
      document.querySelectorAll('#brand-name').forEach(el => el.textContent = s.ecole_nom);
    }
    if (s.ecole_telephone) {
      document.getElementById('tb-phone').textContent = 'Tél : ' + s.ecole_telephone;
      document.getElementById('tb-phone').href = 'tel:' + s.ecole_telephone.replace(/\s/g,'');
      document.getElementById('c-tel').textContent = s.ecole_telephone;
      document.getElementById('foot-tel').textContent = s.ecole_telephone;
      document.getElementById('foot-tel').href = 'tel:' + s.ecole_telephone.replace(/\s/g,'');
    }
    if (s.ecole_email) {
      document.getElementById('tb-email').textContent = 'Email : ' + s.ecole_email;
      document.getElementById('tb-email').href = 'mailto:' + s.ecole_email;
      document.getElementById('c-mail').textContent = s.ecole_email;
      document.getElementById('foot-mail').textContent = s.ecole_email;
      document.getElementById('foot-mail').href = 'mailto:' + s.ecole_email;
    }
    if (s.ecole_adresse) document.getElementById('c-adresse').textContent = s.ecole_adresse;

    const socials = [
      ['reseau_facebook','📘'], ['reseau_instagram','📷'], ['reseau_youtube','▶️'],
      ['reseau_tiktok','🎵'], ['reseau_whatsapp','💬'],
    ];
    const tbSocial = document.getElementById('tb-social');
    const footSocial = document.getElementById('foot-social');
    socials.forEach(([key, icon]) => {
      if (s[key]) {
        tbSocial.innerHTML += `<a href="${s[key]}" target="_blank" rel="noopener">${icon}</a>`;
        footSocial.innerHTML += `<a href="${s[key]}" target="_blank" rel="noopener">${icon}</a>`;
      }
    });

    // Fond personnalisable du hero (modifiable à tout moment depuis Paramètres)
    if (s.ecole_fond_url) {
      document.querySelector('.hero').classList.add('has-fond');
      const fondImg = document.getElementById('hero-fond-img');
      fondImg.style.backgroundImage = `url('${s.ecole_fond_url}')`;
      fondImg.style.display = 'block';
      document.getElementById('hero-fond-overlay').style.display = 'block';
    }

    // Carrousel d'images (page vivante)
    let carouselImages = [];
    try { carouselImages = JSON.parse(s.carousel_images || '[]'); } catch(_) {}
    if (carouselImages.length) initCarousel(carouselImages);

    // Mot du Fondateur
    if (s.mot_fondateur && s.mot_fondateur.trim()) {
      document.getElementById('fondateur-texte').textContent = s.mot_fondateur;
      document.getElementById('fondateur').style.display = '';
    }

    // Vidéo de présentation
    if (s.video_presentation_youtube) {
      const id = extraireIdYoutube(s.video_presentation_youtube);
      if (id) {
        document.getElementById('video-wrap').innerHTML = `<iframe src="https://www.youtube.com/embed/${id}" allowfullscreen></iframe>`;
        document.getElementById('video-section').style.display = '';
      }
    }

    // Services « Au-delà des salles de classe » (remplace les 4 exemples par défaut si configurés)
    try {
      const services = JSON.parse(s.services_vie_scolaire || '[]');
      if (services.length) {
        document.getElementById('services-grid').innerHTML = services.map(sv => `
          <div class="svc"><div class="ic">${escHtml(sv.icone||'⭐')}</div><h4>${escHtml(sv.titre||'')}</h4><p>${escHtml(sv.description||'')}</p></div>
        `).join('');
      }
    } catch(_) {}

    // Section « Notre établissement »
    if (s.etablissement_titre) document.getElementById('etab-titre').textContent = s.etablissement_titre;
    if (s.etablissement_texte) document.getElementById('etab-texte').textContent = s.etablissement_texte;

    // Détail des cycles (Objectif / Pédagogie / Activités / Équipements) — rendu
    // entièrement dynamique : prend en compte les cycles ajoutés ou supprimés.
    try {
      const merged = { ...CYCLES_DEFAUT_PUBLIC, ...JSON.parse(s.cycles_detail || '{}') };
      window._cyclesData = Object.fromEntries(Object.entries(merged).filter(([_, c]) => !c._supprime));
      const row = document.getElementById('cycles-row');
      if (row) {
        row.innerHTML = Object.entries(window._cyclesData).map(([cle, c], i) => `
          <div class="path-step" onclick="ouvrirCycle('${cle}')"><div class="num">ÉTAPE ${String(i+1).padStart(2,'0')}</div><div class="ic">${escHtml(c.icone||'🎓')}</div><h4>${escHtml(c.titre||cle)}</h4><p>${escHtml(c.accroche||'')}</p></div>
        `).join('');
      }
    } catch(_) {}

    // Carte de localisation (« Venez nous rencontrer »)
    if (s.carte_latitude && s.carte_longitude) {
      const lat = parseFloat(s.carte_latitude), lon = parseFloat(s.carte_longitude);
      if (!isNaN(lat) && !isNaN(lon)) {
        const delta = 0.006;
        const bbox = `${lon-delta},${lat-delta},${lon+delta},${lat+delta}`;
        document.getElementById('contact-map').innerHTML =
          `<iframe src="https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&marker=${lat},${lon}" loading="lazy"></iframe>`;
      }
    }
  } catch(e) { console.warn('Infos école indisponibles', e); }
}

const CYCLES_DEFAUT_PUBLIC = {
  maternelle: { titre:'Maternelle', icone:'🧸', accroche:'Éveil, langage et premiers repères, dans un cadre rassurant.',
    presentation:"L'inscription en maternelle est essentielle dans le parcours scolaire d'un enfant : c'est ici qu'il fait ses premiers pas vers l'autonomie, le langage et la découverte du monde.",
    objectif:"Développer l'envie d'apprendre, assurer la maîtrise progressive du langage et préparer chaque enfant aux apprentissages fondamentaux, dans un cadre sécurisant.",
    pedagogie:"Une pédagogie par le jeu et les projets, un encadrement attentif par nos éducatrices, et une initiation progressive à la lecture et à l'écriture.",
    activites:"Éveil musical, arts plastiques, expression corporelle et ateliers de motricité pour un développement harmonieux.",
    equipements:"Salles adaptées aux tout-petits, aire de jeux sécurisée, matériel pédagogique et surveillance constante." },
  primaire: { titre:'Primaire', icone:'📘', accroche:'Lecture, écriture, calcul : les fondamentaux, bien ancrés.',
    presentation:"Le primaire installe durablement les savoirs fondamentaux — lire, écrire, compter — sur lesquels reposera toute la suite de la scolarité.",
    objectif:"Consolider la maîtrise de la langue française, les mathématiques et la méthode de travail, en vue d'une transition réussie vers le collège.",
    pedagogie:"Un suivi individualisé, des évaluations régulières et un accompagnement renforcé pour les élèves en difficulté.",
    activites:"Clubs de lecture, initiation aux sciences, activités sportives et culturelles régulières.",
    equipements:"Salles de classe équipées, bibliothèque, espace informatique d'initiation." },
  college: { titre:'Collège', icone:'🔬', accroche:"Ouverture disciplinaire et méthode de travail affirmée.",
    presentation:"Le collège élargit les horizons de l'élève à travers de nouvelles disciplines, tout en construisant son autonomie et sa rigueur de travail.",
    objectif:"Approfondir les savoirs disciplinaires et préparer les élèves au Brevet d'Études du Premier Cycle (BEPC) dans les meilleures conditions.",
    pedagogie:"Un enseignement par matière avec des professeurs spécialisés, un suivi des résultats et des séances de renforcement ciblées.",
    activites:"Cours de révision, clubs scientifiques et activités parascolaires variées.",
    equipements:"Laboratoire, salles spécialisées et matériel pédagogique adapté au secondaire." },
  lycee: { titre:'Lycée', icone:'🎓', accroche:"Préparation exigeante au baccalauréat et à l'après-bac.",
    presentation:"Le lycée accompagne chaque élève vers la réussite au baccalauréat et l'construction de son projet d'orientation post-bac.",
    objectif:"Garantir un excellent taux de réussite au baccalauréat et une préparation solide à l'enseignement supérieur.",
    pedagogie:"Un encadrement exigeant, des devoirs surveillés réguliers et un suivi individualisé de chaque filière.",
    activites:"Cours de révision intensifs, orientation post-bac et activités de leadership.",
    equipements:"Salles spécialisées par filière, bibliothèque et espaces de travail dédiés." },
};

function ouvrirCycle(cle) {
  const cycles = window._cyclesData || CYCLES_DEFAUT_PUBLIC;
  const c = { ...CYCLES_DEFAUT_PUBLIC[cle], ...(cycles[cle]||{}) };
  document.getElementById('cycle-modal-titre').textContent = (c.icone?c.icone+' ':'') + (c.titre||cle);
  document.getElementById('cycle-modal-presentation').textContent = c.presentation || '';
  const blocs = [
    ['🎯','Objectif', c.objectif], ['📚','Pédagogie', c.pedagogie],
    ['🎨','Activités', c.activites], ['🏫','Équipements', c.equipements],
  ].filter(b => b[2]);
  document.getElementById('cycle-modal-blocks').innerHTML = blocs.map(([ic,titre,texte]) => `
    <div class="cycle-detail-block"><h5>${ic} ${titre}</h5><p>${escHtml(texte)}</p></div>
  `).join('') || '<p style="color:var(--ink-soft)">Détails à venir.</p>';

  const ordre = Object.keys(cycles);
  document.getElementById('cycle-nav').innerHTML = ordre.map(k => {
    const cc = { ...CYCLES_DEFAUT_PUBLIC[k], ...(cycles[k]||{}) };
    return `<button class="${k===cle?'active':''}" onclick="ouvrirCycle('${k}')">${escHtml(cc.icone||'')} ${escHtml(cc.titre||k)}</button>`;
  }).join('');

  document.getElementById('cycle-modal').classList.add('show');
}
function fermerCycle() { document.getElementById('cycle-modal').classList.remove('show'); }
window.ouvrirCycle = ouvrirCycle;
window.fermerCycle = fermerCycle;

function extraireIdYoutube(url) {
  const m = url.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([a-zA-Z0-9_-]{11})/);
  return m ? m[1] : null;
}

/* ── Carrousel d'images ── */
let _carouselIndex = 0, _carouselTimer = null;
function initCarousel(images) {
  const track = document.getElementById('carousel-track');
  const dots = document.getElementById('carousel-dots');
  track.innerHTML = images.map(url => `<img src="${url}" alt="Photo de l'école">`).join('');
  dots.innerHTML = images.map((_, i) => `<button onclick="carouselAllerA(${i})"></button>`).join('');
  document.getElementById('carousel-section').style.display = 'block';
  carouselMettreAJour();
  _carouselTimer = setInterval(() => carouselAller(1), 5000);
}
function carouselMettreAJour() {
  const track = document.getElementById('carousel-track');
  const nb = track.children.length;
  if (!nb) return;
  track.style.transform = `translateX(-${_carouselIndex * 100}%)`;
  document.querySelectorAll('#carousel-dots button').forEach((d, i) => d.classList.toggle('active', i === _carouselIndex));
}
function carouselAller(delta) {
  const nb = document.getElementById('carousel-track').children.length;
  if (!nb) return;
  _carouselIndex = (_carouselIndex + delta + nb) % nb;
  carouselMettreAJour();
  clearInterval(_carouselTimer);
  _carouselTimer = setInterval(() => carouselAller(1), 5000);
}
function carouselAllerA(i) { _carouselIndex = i; carouselMettreAJour(); }
window.carouselAller = carouselAller;
window.carouselAllerA = carouselAllerA;

let _articlesCache = [];
async function chargerActualites() {
  const container = document.getElementById('news-container');
  try {
    const res = await fetch(avecCodeEcole('/api/articles'));
    if (!res.ok) throw new Error('erreur');
    const articles = await res.json();
    _articlesCache = articles;
    if (!articles.length) {
      container.innerHTML = '<div class="news-empty">Aucune actualité publiée pour le moment.</div>';
      return;
    }
    container.innerHTML = articles.slice(0, 6).map(a => {
      const premiereImage = extraireVignette(a.contenu);
      const extrait = extraireExtrait(a.contenu, 100);
      return `
      <div class="news-card" onclick="ouvrirArticle('${a.id}')">
        ${premiereImage ? `<img src="${premiereImage}" style="width:100%;height:150px;object-fit:cover;border-radius:12px 12px 0 0">` : `<div class="thumb">${a.type==='evenement'?'📅':'📰'}</div>`}
        <div class="body">
          <div class="date">${new Date(a.date_publication || a.created_at).toLocaleDateString('fr-FR', {day:'numeric',month:'long',year:'numeric'})}</div>
          <h4>${escHtml(a.titre)}</h4>
          <p>${escHtml(extrait)}</p>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = '<div class="news-empty">Actualités à venir.</div>';
  }
}
function escHtml(s){ const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

/* Le contenu d'un article peut contenir des repères [image:URL] et [video:ID_YOUTUBE]
   (insérés depuis l'espace de gestion) au milieu du texte libre. */
function extraireVignette(contenu) {
  const m = (contenu||'').match(/\[image:([^\]]+)\]/);
  return m ? m[1] : null;
}
function extraireExtrait(contenu, longueur) {
  const texte = (contenu||'').replace(/\[image:[^\]]+\]/g, '').replace(/\[video:[^\]]+\]/g, '').replace(/\n+/g, ' ').trim();
  return texte.length > longueur ? texte.substring(0, longueur) + '…' : texte;
}
function rendreContenuArticle(contenu) {
  return (contenu || '').split('\n').map(ligne => {
    const imgMatch = ligne.match(/^\[image:([^\]]+)\]$/);
    const vidMatch = ligne.match(/^\[video:([a-zA-Z0-9_-]{11})\]$/);
    if (imgMatch) return `<img src="${escAttr(imgMatch[1])}" alt="">`;
    if (vidMatch) return `<div class="video-wrap"><iframe src="https://www.youtube.com/embed/${vidMatch[1]}" allowfullscreen></iframe></div>`;
    if (!ligne.trim()) return '';
    return `<p>${escHtml(ligne)}</p>`;
  }).join('');
}
function escAttr(s){ return (s||'').replace(/"/g,'&quot;'); }

function ouvrirArticle(id) {
  const a = _articlesCache.find(x => x.id === id);
  if (!a) return;
  document.getElementById('article-modal-date').textContent = new Date(a.date_publication || a.created_at).toLocaleDateString('fr-FR', {day:'numeric',month:'long',year:'numeric'});
  document.getElementById('article-modal-titre').textContent = a.titre;
  document.getElementById('article-modal-corps').innerHTML = rendreContenuArticle(a.contenu);
  document.getElementById('article-modal').classList.add('show');
  document.body.style.overflow = 'hidden';
}
function fermerArticle() {
  document.getElementById('article-modal').classList.remove('show');
  document.body.style.overflow = '';
}
window.ouvrirArticle = ouvrirArticle;
window.fermerArticle = fermerArticle;

/* Si l'utilisateur a cliqué un lien de menu très vite après l'arrivée sur la page,
   le contenu chargé après coup (carrousel, actualités, vidéo…) peut décaler la section
   visée. Une fois tout ce contenu en place, on corrige la position si besoin. */
Promise.allSettled([chargerInfosEcole(), chargerActualites()]).then(() => {
  if (location.hash) {
    const cible = document.querySelector(location.hash);
    if (cible) setTimeout(() => cible.scrollIntoView({ behavior: 'auto', block: 'start' }), 50);
  }

  /* Légère apparition au défilement (titres de section + cartes), pour une lecture
     plus vivante. Mis en place APRÈS le contenu dynamique (services personnalisés,
     actualités…) pour ne manquer aucune carte, y compris celles ajoutées ensuite. */
  document.querySelectorAll(
    '.section .center, .about-grid, .path-step, .svc, .aud-card, .fondateur-card, .news-card'
  ).forEach(el => el.classList.add('reveal'));

  const _observateurApparition = new IntersectionObserver((entrees) => {
    entrees.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); _observateurApparition.unobserve(e.target); } });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  document.querySelectorAll('.reveal').forEach(el => _observateurApparition.observe(el));
});


/* ── Vérification d'un badge élève (saisie manuelle ou scan du QR code) ── */
(function () {
  const $ = id => document.getElementById(id);
  if (!$('vb-go')) return;
  const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function afficher(r) {
    const ok = r && r.valide;
    $('vb-resultat').innerHTML = ok
      ? `<div style="background:#16a34a;color:#fff;padding:10px;border-radius:8px;font-weight:700">✔ Badge authentique</div>
         <h4 style="margin:14px 0 4px">${esc(r.prenom)} ${esc((r.nom || '').toUpperCase())}</h4>
         <p>Classe : <b>${esc(r.classe || '—')}</b> · Matricule : <b>${esc(r.matricule || '—')}</b></p>
         <p>${esc(r.ecole || '')} — année ${esc(r.annee || '')}, valable jusqu'au ${esc(r.expire || '')}</p>`
      : `<div style="background:#dc2626;color:#fff;padding:10px;border-radius:8px;font-weight:700">✖ Badge non valide</div><p style="margin-top:8px">${esc((r && r.motif) || 'Vérification impossible.')}</p>`;
  }
  async function appeler(url) {
    $('vb-resultat').textContent = 'Vérification…';
    try { afficher(await (await fetch(url)).json()); } catch (_) { afficher({ valide: false, motif: 'Connexion impossible. Réessayez.' }); }
  }
  $('vb-go').onclick = () => {
    const m = $('vb-matricule').value.trim(), c = $('vb-code').value.trim();
    appeler(avecCodeEcole(`/api/verifier-badge-code?matricule=${encodeURIComponent(m)}&code=${encodeURIComponent(c)}`));
  };
  let flux = null;
  function arreter() { if (flux) flux.getTracks().forEach(t => t.stop()); flux = null; $('vb-video').style.display = 'none'; }
  function depuisQr(texte) {
    const c = String(texte).match(/\/v\/(\d+)\/([0-9a-f]{12})/i);
    if (c) { appeler(`/api/v/${c[1]}/${c[2]}`); return; }
    const m = String(texte).match(/\/verifier-badge\/(\d+)\/([^/]+)\/([^/]*)\/([0-9a-f]+)/i);
    if (!m) { afficher({ valide: false, motif: "Ce QR code n'est pas un badge de l'école." }); return; }
    appeler(`/api/verifier-badge/${m[1]}/${m[2]}/${m[3] || '-'}/${m[4]}`);
  }
  $('vb-scan').onclick = async () => {
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices) {
      afficher({ valide: false, motif: "Ce navigateur ne sait pas scanner. Scannez le QR avec l'appareil photo du téléphone (la page de vérification s'ouvre), ou saisissez le matricule et le code." });
      return;
    }
    try {
      flux = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      const v = $('vb-video'); v.srcObject = flux; v.style.display = 'block'; await v.play();
      const det = new BarcodeDetector({ formats: ['qr_code'] });
      const boucle = async () => {
        if (!flux) return;
        try { const r = await det.detect(v); if (r.length) { arreter(); depuisQr(r[0].rawValue); return; } } catch (_) {}
        setTimeout(boucle, 300);
      };
      boucle();
    } catch (_) { arreter(); afficher({ valide: false, motif: "Accès à la caméra refusé." }); }
  };
})();
