/* ===================== JOURNAL D'AUDIT ===================== */
const ACTION_LABELS = {
  creation: '➕ Création', modification: '✏️ Modification', suppression: '🗑 Suppression',
  approbation: '✅ Approbation', rejet: '❌ Rejet', reinitialisation_mdp: '🔑 Mot de passe réinitialisé',
  validation_reinscription: '✅ Réinscription validée', refus_reinscription: '❌ Réinscription refusée',
  designation: '⭐ Désignation', saisie_heures: '🕐 Heures saisies',
};
const ENTITE_LABELS = {
  utilisateur: 'Utilisateur', transaction: 'Transaction', classe: 'Classe', personnel: 'Personnel',
  reinscription: 'Réinscription', article: 'Article', eleve_du_mois: 'Élève du mois',
  parametres_approbation: "Paramètres d'approbation",
};

async function pageJournal() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [entries, meta] = await Promise.all([apiGetJournal(), apiJournalMeta()]);
    let curr = entries;

    const render = data => {
      $('#tb-journal').innerHTML = data.length ? data.map(j => `<tr>
        <td class="text-muted" style="font-size:12px;white-space:nowrap">${fmtDate(j.created_at)} <span style="font-size:11px">${(j.created_at||'').split(' ')[1]||''}</span></td>
        <td><strong>${esc(j.user_nom||'Système')}</strong></td>
        <td><span class="badge bdg-primary">${ACTION_LABELS[j.action]||esc(j.action)}</span></td>
        <td>${esc(ENTITE_LABELS[j.entite]||j.entite)}</td>
        <td class="mono text-muted" style="font-size:11px">${esc(j.entite_id||'—')}</td>
        <td style="max-width:220px;font-size:12px">${j.details && j.details.motif ? esc(j.details.motif) : '<span class="text-muted">—</span>'}</td>
        <td>
          ${j.details ? `<button class="btn btn-outline btn-xs" onclick='voirDetailsJournal(${JSON.stringify(j.details).replace(/'/g,"&#39;")})'>👁 Détails</button>` : '—'}
        </td>
      </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('🗂️','Aucune entrée dans le journal')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div class="alert alert-info">🔒 Ce journal recense l'historique de toutes les actions sensibles effectuées dans l'application
    (créations, modifications, suppressions, approbations…) — il permet de reconstituer précisément qui a fait quoi et quand.
    Réservé à l'administrateur (fondateur).</div>
    <div class="card">
      <div class="card-header"><span class="card-title">🗂️ Journal d'audit (${entries.length} dernières entrées)</span></div>
      <div class="filters">
        <div class="fg"><label>Entité</label><select id="f-jent"><option value="">Toutes</option>${meta.entites.map(e=>`<option value="${esc(e)}">${esc(ENTITE_LABELS[e]||e)}</option>`).join('')}</select></div>
        <div class="fg"><label>Action</label><select id="f-jact"><option value="">Toutes</option>${meta.actions.map(a=>`<option value="${esc(a)}">${esc(ACTION_LABELS[a]||a)}</option>`).join('')}</select></div>
        <div class="fg"><label>Du</label><input type="date" id="f-jdeb"></div>
        <div class="fg"><label>Au</label><input type="date" id="f-jfin"></div>
        <div class="fg grow"><label>Recherche</label><input id="q-j" placeholder="Utilisateur, référence…"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-journal"><th>Date / Heure</th><th>Utilisateur</th><th>Action</th><th>Entité</th><th>Référence</th><th>Motif</th><th>Détails</th></tr></thead>
        <tbody id="tb-journal"></tbody>
      </table></div>
    </div>`;
    render(curr);

    makeSortableTable('#th-journal', () => curr, render,
      ['created_at', 'user_nom', 'action', 'entite', 'entite_id', row => (row.details && row.details.motif) || '', null]);

    const refilter = async () => {
      let qs = [];
      const ent = $('#f-jent').value, act = $('#f-jact').value, deb = $('#f-jdeb').value, fin = $('#f-jfin').value, q = $('#q-j').value;
      if (ent) qs.push(`entite=${ent}`);
      if (act) qs.push(`action=${act}`);
      if (deb) qs.push(`date_debut=${deb}`);
      if (fin) qs.push(`date_fin=${fin}`);
      if (q) qs.push(`q=${encodeURIComponent(q)}`);
      try { curr = await apiGetJournal(qs.join('&')); render(curr); }
      catch(e) { toast(e.message,'error'); }
    };
    ['#f-jent','#f-jact','#f-jdeb','#f-jfin'].forEach(s => $(s).addEventListener('change', refilter));
    $('#q-j').addEventListener('input', refilter);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function voirDetailsJournal(details) {
  const lignes = Object.entries(details).map(([k,v]) => `<div><strong class="text-muted">${esc(k)} :</strong> ${esc(typeof v==='object'?JSON.stringify(v):String(v))}</div>`).join('');
  openModal('Détails de l\'action', `<div style="display:flex;flex-direction:column;gap:6px;font-size:13px">${lignes || 'Aucun détail'}</div>
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>`, { narrow: true });
}
window.voirDetailsJournal = voirDetailsJournal;
