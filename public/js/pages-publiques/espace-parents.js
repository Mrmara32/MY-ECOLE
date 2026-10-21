const API = '/api';
let TOKEN = localStorage.getItem('ep_tok') || null;
let ENFANTS = [];
let ENFANT_ACTIF = null;

// Code établissement détecté depuis l'URL (/ecole/CODE/espace-parents) — indispensable
// pour savoir dans quelle école chercher l'identifiant du parent à la connexion.
function codeEcoleDepuisURL() {
  const m = window.location.pathname.match(/^\/ecole\/([^/]+)/);
  return m ? m[1] : null;
}
const CODE_ECOLE = codeEcoleDepuisURL();
if (CODE_ECOLE) {
  document.querySelectorAll('a[href="/vitrine.html"]').forEach(a => a.href = `/ecole/${CODE_ECOLE}/vitrine`);
  fetch(API + '/settings?ecole=' + encodeURIComponent(CODE_ECOLE))
    .then(r => r.json())
    .then(s => {
      if (s.ecole_nom) {
        const el = document.getElementById('nom-ecole-contexte');
        el.textContent = s.ecole_nom;
        el.style.display = 'block';
      }
    })
    .catch(() => {});
}

function afficherOngletParent(onglet) {
  const btnConnexion = document.getElementById('tab-btn-connexion');
  const btnInscription = document.getElementById('tab-btn-inscription');
  const styleActif = 'flex:1;padding:10px;border:none;border-radius:999px;font-weight:700;font-size:13px;cursor:pointer;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08)';
  const styleInactif = 'flex:1;padding:10px;border:none;border-radius:999px;font-weight:700;font-size:13px;cursor:pointer;background:transparent;color:#6B7280';
  if (onglet === 'connexion') {
    document.getElementById('onglet-connexion').style.display = '';
    document.getElementById('onglet-inscription').style.display = 'none';
    btnConnexion.style.cssText = styleActif;
    btnInscription.style.cssText = styleInactif;
  } else {
    document.getElementById('onglet-connexion').style.display = 'none';
    document.getElementById('onglet-inscription').style.display = '';
    btnConnexion.style.cssText = styleInactif;
    btnInscription.style.cssText = styleActif;
  }
}

document.getElementById('inscription-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = document.getElementById('inscription-btn');
  const errBox = document.getElementById('inscription-err');
  errBox.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Création…';
  try {
    const body = {
      nom_complet: document.getElementById('i-nom').value.trim(),
      matricule_enfant: document.getElementById('i-matricule').value.trim(),
      email: document.getElementById('i-email').value.trim(),
      username: document.getElementById('i-user').value.trim(),
      password: document.getElementById('i-pass').value,
      accepte_conditions: document.getElementById('i-cgu').checked,
    };
    if (CODE_ECOLE) body.code_ecole = CODE_ECOLE;
    const r = await fetch(API + '/parent/inscription', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Erreur');
    document.getElementById('inscription-form').style.display = 'none';
    document.getElementById('inscription-ok').style.display = 'block';
    document.getElementById('inscription-ok-texte').textContent = d.message;
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = '';
    btn.disabled = false;
    btn.textContent = 'Créer mon compte';
  }
});

async function apiFetch(path, opts = {}) {
  const r = await fetch(API + path, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(TOKEN ? { 'Authorization': 'Bearer ' + TOKEN } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || 'Erreur');
  return d;
}

document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = document.getElementById('login-btn');
  const errBox = document.getElementById('login-err');
  errBox.style.display = 'none';
  btn.disabled = true; btn.textContent = 'Connexion…';
  try {
    const r = await fetch(API + '/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: document.getElementById('l-user').value.trim(),
        password: document.getElementById('l-pass').value,
        ...(CODE_ECOLE ? { code_ecole: CODE_ECOLE } : {}),
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Identifiant ou mot de passe incorrect');
    if (d.user.role !== 'parent') throw new Error("Cet espace est réservé aux comptes parents.");
    TOKEN = d.token;
    localStorage.setItem('ep_tok', TOKEN);
    localStorage.setItem('ep_user', JSON.stringify(d.user));
    await demarrerDashboard(d.user);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = 'block';
  } finally {
    btn.disabled = false; btn.textContent = 'Se connecter';
  }
});

document.getElementById('logout-btn').addEventListener('click', () => {
  localStorage.removeItem('ep_tok'); localStorage.removeItem('ep_user');
  location.reload();
});

async function demarrerDashboard(user) {
  document.getElementById('login-wrap').style.display = 'none';
  document.getElementById('dash-wrap').style.display = 'block';
  const civ = user.civilite ? user.civilite + ' ' : '';
  document.getElementById('dash-nom-parent').textContent = civ + (user.full_name || user.username);

  try {
    ENFANTS = await apiFetch('/parent/mes-enfants');
  } catch (err) {
    document.getElementById('dash-contenu').innerHTML = `<div class="section-card"><p class="empty">Impossible de charger vos informations : ${err.message}</p></div>`;
    return;
  }
  afficherMessages();
  if (!ENFANTS.length) {
    document.getElementById('dash-contenu').insertAdjacentHTML('beforeend',
      `<div class="section-card"><p class="empty">Aucun élève n'est encore lié à votre compte. Contactez l'établissement pour associer votre/vos enfant(s).</p></div>`);
    return;
  }
  document.getElementById('enfants-tabs').innerHTML = ENFANTS.map((e, i) => `
    <button class="enfant-tab ${i===0?'active':''}" data-id="${e.id}" onclick="choisirEnfant('${e.id}')">${e.prenom} ${e.nom}</button>
  `).join('');
  choisirEnfant(ENFANTS[0].id);
}

async function afficherMessages() {
  try {
    const messages = await apiFetch('/parent/messages');
    const zone = document.getElementById('messages-zone');
    if (!messages.length) return; // Pas de bandeau si aucun message
    zone.innerHTML = `
      <div class="section-card">
        <h2>✉️ Messages de l'établissement</h2>
        ${messages.map(m => `
          <div class="devoir-item">
            <div class="titre">${esc(m.sujet || 'Message')}</div>
            <div class="meta">${m.expediteur_nom ? 'De ' + esc(m.expediteur_nom) + ' · ' : ''}${fmtDate(m.date_envoi)}</div>
            <div style="font-size:13.5px;margin-top:6px">${esc(m.contenu)}</div>
          </div>
        `).join('')}
      </div>`;
  } catch (_) { /* silencieux : la messagerie ne doit pas bloquer le reste du tableau de bord */ }
}

async function choisirEnfant(eleveId) {
  ENFANT_ACTIF = ENFANTS.find(e => e.id === eleveId);
  document.querySelectorAll('.enfant-tab').forEach(b => b.classList.toggle('active', b.dataset.id === eleveId));
  const zone = document.getElementById('dash-contenu');
  zone.innerHTML = `<p class="empty">Chargement…</p>`;

  const [notes, absences, devoirs, resultats, viescolaire] = await Promise.all([
    apiFetch('/notes?eleve_id=' + eleveId).catch(() => []),
    apiFetch('/absences?eleve_id=' + eleveId).catch(() => []),
    apiFetch('/devoirs?classe=' + encodeURIComponent(ENFANT_ACTIF.classe || '')).catch(() => []),
    apiFetch('/discipline?eleve_id=' + eleveId).catch(() => []),
    // Résultats officiels calculés par l'école (coefficients, rang, mention) pour chaque période
    Promise.all(['1', '2', '3', 'annee'].map(per =>
      apiFetch('/bulletins/eleve/' + eleveId + '?periode=' + per).then(r => ({ per, r })).catch(() => ({ per, r: null })))),
  ]);
  const libPer = { '1': 'Trimestre 1', '2': 'Trimestre 2', '3': 'Trimestre 3', 'annee': 'Année' };
  const lignesResultats = resultats.filter(x => x.r && x.r.eleve && x.r.eleve.moyenne_generale != null).map(({ per, r }) => {
    const l = r.eleve;
    return `<tr><td><strong>${libPer[per]}</strong></td><td>${l.moyenne_generale.toFixed(2)}/20</td>
      <td>${l.rang != null ? l.rang + (l.rang === 1 ? 'er' : 'e') + ' / ' + l.effectif : '—'}</td>
      <td>${r.moyenne_classe != null ? r.moyenne_classe.toFixed(2) : '—'}</td><td>${esc(l.mention || '—')}</td></tr>`;
  }).join('');

  // Regrouper les notes par matière pour calculer une moyenne simple
  const parMatiere = {};
  notes.forEach(n => {
    if (!parMatiere[n.matiere]) parMatiere[n.matiere] = [];
    parMatiere[n.matiere].push(n);
  });
  const classeNote = (note, max) => {
    const pct = (note / (max || 20)) * 100;
    return pct >= 60 ? 'note-bonne' : pct >= 40 ? 'note-moyenne' : 'note-faible';
  };

  const lignesNotes = Object.entries(parMatiere).map(([matiere, liste]) => {
    const moyenne = liste.reduce((s, n) => s + (n.note / (n.note_max || 20)) * 20, 0) / liste.length;
    const details = liste.map(n => `<span class="note-val ${classeNote(n.note, n.note_max)}">${n.note}/${n.note_max||20}</span>`).join(' · ');
    return `<tr><td><strong>${esc(matiere)}</strong></td><td>${details}</td>
      <td class="note-val ${classeNote(moyenne, 20)}">${moyenne.toFixed(1)}/20</td></tr>`;
  }).join('');

  const nbAbsInjust = absences.filter(a => !a.justifie).length;

  zone.innerHTML = `
    ${lignesResultats ? `<div class="section-card"><h2>🏅 Résultats</h2>
      <table><thead><tr><th>Période</th><th>Moyenne générale</th><th>Rang</th><th>Moyenne de la classe</th><th>Mention</th></tr></thead>
      <tbody>${lignesResultats}</tbody></table></div>` : ''}
    <div class="section-card">
      <h2>📊 Notes — ${esc(ENFANT_ACTIF.classe || '')}</h2>
      ${notes.length ? `
        <table><thead><tr><th>Matière</th><th>Notes obtenues</th><th>Moyenne</th></tr></thead>
        <tbody>${lignesNotes}</tbody></table>
        <button id="btn-imprimer" onclick="window.print()">🖨️ Imprimer ce relevé</button>
      ` : '<p class="empty">Aucune note enregistrée pour le moment.</p>'}
    </div>

    ${viescolaire.length ? `<div class="section-card"><h2>🧑‍⚖️ Vie scolaire</h2>
      <table><thead><tr><th>Date</th><th>Nature</th><th>Motif</th><th>Suite donnée</th></tr></thead><tbody>${viescolaire.map(f => `
        <tr><td>${fmtDate(f.date_fait)}</td><td>${({felicitations:'🏆 Félicitations',observation:'Observation',avertissement:'⚠️ Avertissement',retenue:'Retenue',blame:'Blâme',exclusion_temporaire:'Exclusion temporaire'})[f.type] || esc(f.type)}${f.nb_jours ? ' (' + f.nb_jours + ' j)' : ''}</td>
        <td>${esc(f.motif)}</td><td>${esc(f.sanction || '—')}</td></tr>`).join('')}</tbody></table></div>` : ''}

    <div class="section-card">
      <h2>📅 Absences ${nbAbsInjust ? `<span class="badge badge-injust">${nbAbsInjust} non justifiée${nbAbsInjust>1?'s':''}</span>` : ''}</h2>
      ${absences.length ? `
        <table><thead><tr><th>Date</th><th>Type</th><th>Motif</th><th>Statut</th></tr></thead>
        <tbody>${absences.map(a => `
          <tr><td>${fmtDate(a.date_abs)}</td><td>${a.type==='retard'?'Retard':'Absence'}</td>
          <td>${esc(a.motif||'—')}</td>
          <td><span class="badge ${a.justifie?'badge-just':'badge-injust'}">${a.justifie?'Justifiée':'Non justifiée'}</span></td></tr>
        `).join('')}</tbody></table>
      ` : '<p class="empty">Aucune absence enregistrée. 🎉</p>'}
    </div>

    <div class="section-card">
      <h2>📝 Devoirs et exercices</h2>
      ${devoirs.length ? devoirs.map(d => `
        <div class="devoir-item">
          <div class="titre">${esc(d.titre)}</div>
          <div class="meta">${esc(d.matiere||'')} ${d.date_remise ? '· À rendre le ' + fmtDate(d.date_remise) : ''} · ${esc(d.statut||'')}</div>
          ${d.description ? `<div style="font-size:13px;margin-top:6px;color:var(--ink-soft)">${esc(d.description)}</div>` : ''}
        </div>
      `).join('') : '<p class="empty">Aucun devoir en cours pour cette classe.</p>'}
    </div>
  `;
}

function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function fmtDate(d) { if (!d) return '—'; const dt = new Date(d); return isNaN(dt) ? d : dt.toLocaleDateString('fr-FR'); }

// Restaurer la session si un jeton valide existe déjà
(async () => {
  if (TOKEN) {
    try {
      const user = JSON.parse(localStorage.getItem('ep_user') || '{}');
      await demarrerDashboard(user);
    } catch (_) {
      localStorage.removeItem('ep_tok'); localStorage.removeItem('ep_user');
    }
  }
})();
