let TOUTES_LES_ECOLES = [];

function initiales(nom) {
  return (nom || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(m => m[0]).join('').toUpperCase();
}

function carteEcole(e) {
  const logo = e.logo_url
    ? `<img class="ecole-logo" src="${e.logo_url}" alt="">`
    : `<div class="ecole-logo-fallback">${initiales(e.nom)}</div>`;
  const contact = [e.telephone_contact, e.email_contact].filter(Boolean).join(' · ');
  return `
    <a class="ecole-card" href="/ecole/${encodeURIComponent(e.code)}">
      ${logo}
      <div class="ecole-nom">${e.nom}</div>
      ${contact ? `<div class="ecole-contact">${contact}</div>` : ''}
      <div class="ecole-cta">Visiter le site →</div>
    </a>`;
}

function afficher(liste) {
  const grid = document.getElementById('grid');
  if (!liste.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="icon">🔎</div>Aucune école ne correspond à votre recherche.</div>`;
    return;
  }
  grid.innerHTML = liste.map(carteEcole).join('');
}

async function charger() {
  const grid = document.getElementById('grid');
  try {
    const res = await fetch('/api/ecoles/publique');
    TOUTES_LES_ECOLES = await res.json();
    if (!TOUTES_LES_ECOLES.length) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="icon">🏫</div>Aucune école n'est encore inscrite sur la plateforme.</div>`;
      return;
    }
    afficher(TOUTES_LES_ECOLES);
  } catch (e) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1">Impossible de charger la liste des écoles pour le moment.</div>`;
  }
}

document.getElementById('recherche').addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase();
  afficher(q ? TOUTES_LES_ECOLES.filter(x => x.nom.toLowerCase().includes(q)) : TOUTES_LES_ECOLES);
});

charger();
