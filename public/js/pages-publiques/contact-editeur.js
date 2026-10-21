// Remplit les coordonnées de l'éditeur (Actif System Groupe) sur les pages légales.
fetch('/api/aide/info').then(r => r.json()).then(d => {
  const e = d.editeur || {};
  document.querySelectorAll('[data-contact="tel"]').forEach(n => { n.textContent = e.telephone || ''; n.href = 'tel:' + (e.telephone || '').replace(/\D/g, ''); });
  document.querySelectorAll('[data-contact="mail"]').forEach(n => {
    if (e.email) { n.textContent = e.email; n.href = 'mailto:' + e.email; } else { n.closest('[data-ligne-mail]')?.remove(); }
  });
}).catch(() => {});
