const API = '/api';
let timerCode = null;

document.getElementById('nom_ecole').addEventListener('input', e => {
  clearTimeout(timerCode);
  const apercu = document.getElementById('apercu-code');
  const nom = e.target.value.trim();
  if (!nom) { apercu.textContent = ''; return; }
  const slug = nom.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-zA-Z0-9]+/g,'-').replace(/^-+|-+$/g,'').toLowerCase() || 'ecole';
  apercu.textContent = 'Votre code établissement sera proche de : ' + slug;
  apercu.className = 'disponibilite';
  timerCode = setTimeout(async () => {
    try {
      const r = await fetch(`${API}/ecoles/verifier-code?code=${encodeURIComponent(slug)}`);
      const d = await r.json();
      apercu.textContent = d.disponible
        ? `✔ Le code « ${slug} » est disponible`
        : `Ce code existe déjà — un suffixe sera ajouté automatiquement`;
      apercu.className = 'disponibilite ' + (d.disponible ? 'ok' : 'non');
    } catch(_) {}
  }, 500);
});

document.getElementById('form-inscription').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = document.getElementById('btn-submit');
  const errBox = document.getElementById('msg-err');
  errBox.style.display = 'none';
  btn.disabled = true; btn.textContent = 'Création en cours…';

  const fd = Object.fromEntries(new FormData(e.target));
  try {
    const r = await fetch(`${API}/ecoles/inscription`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fd),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Une erreur est survenue');

    document.getElementById('form-wrap').style.display = 'none';
    document.getElementById('msg-ok').style.display = 'block';
    document.getElementById('code-affiche').textContent = d.code;
    document.getElementById('essai-jusquau').textContent = `Votre période d'essai gratuite court jusqu'au ${new Date(d.essai_jusquau).toLocaleDateString('fr-FR')}.`;

    const emailStatut = document.getElementById('email-statut');
    const emailSaisi = fd.email_contact;
    if (d.email_envoye) {
      emailStatut.style.background = '#F0FDF4';
      emailStatut.style.color = '#166534';
      emailStatut.textContent = `✅ Un e-mail de confirmation vient d'être envoyé à ${emailSaisi} — cliquez sur le lien qu'il contient pour activer votre compte.`;
    } else {
      emailStatut.style.background = '#FEF2F2';
      emailStatut.style.color = '#DC2626';
      emailStatut.textContent = `⚠️ L'e-mail de confirmation n'a pas pu être envoyé à ${emailSaisi} — contactez le support pour activer votre compte.`;
    }
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = 'block';
    btn.disabled = false; btn.textContent = 'Créer mon espace gratuitement';
  }
});
