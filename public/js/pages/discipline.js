/* ===================== DISCIPLINE & VIE SCOLAIRE ===================== */
const DISCIPLINE_TYPES = {
  felicitations:        { lib: '🏆 Félicitations',      cls: 'bdg-ok' },
  observation:          { lib: '👁 Observation',        cls: 'bdg-info' },
  avertissement:        { lib: '⚠️ Avertissement',     cls: 'bdg-warn' },
  retenue:              { lib: '⏳ Retenue',            cls: 'bdg-warn' },
  blame:                { lib: '📛 Blâme',              cls: 'bdg-err' },
  exclusion_temporaire: { lib: '🚫 Exclusion temporaire', cls: 'bdg-err' },
};
const apiGetDiscipline = (q = '') => apiFetch('/discipline' + (q ? '?' + q : ''));
const apiCreateDiscipline = (b) => apiFetch('/discipline', { method: 'POST', body: b });
const apiUpdateDiscipline = (id, b) => apiFetch('/discipline/' + encodeURIComponent(id), { method: 'PUT', body: b });
const apiDeleteDiscipline = (id) => apiFetch('/discipline/' + encodeURIComponent(id), { method: 'DELETE' });

async function pageDiscipline() {
  $('#content').innerHTML = loadingHtml;
  const estDirection = ['admin', 'directeur'].includes(currentUser?.role);
  let eleves = [], faits = [];
  const filtres = { classe: '', type: '', du: '', au: '' };
  try { eleves = await apiGetEleves(); } catch (e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  const classes = [...new Set(eleves.map(e => e.classe).filter(Boolean))].sort();

  const charger = async () => {
    const q = Object.entries(filtres).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    try { faits = await apiGetDiscipline(q); } catch (e) { toast(e.message, 'error'); faits = []; }
    afficher();
  };
  const afficher = () => {
    $('#dis-count').textContent = `(${faits.length})`;
    $('#dis-body').innerHTML = faits.length ? faits.map(f => {
      const t = DISCIPLINE_TYPES[f.type] || { lib: f.type, cls: '' };
      return `<tr>
        <td>${fmtDate(f.date_fait)}</td>
        <td><strong>${esc(f.prenom)} ${esc(f.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(f.classe || '')} · ${esc(f.matricule || '')}</span></td>
        <td><span class="badge ${t.cls}">${t.lib}</span>${f.nb_jours ? `<div class="text-muted" style="font-size:11px">${f.nb_jours} jour(s)</div>` : ''}</td>
        <td>${esc(f.motif)}${f.description ? `<div class="text-muted" style="font-size:12px">${esc(f.description)}</div>` : ''}</td>
        <td>${esc(f.sanction || '—')}</td>
        <td class="text-muted" style="font-size:12px">${esc(f.saisi_par || '—')}${f.visible_parents ? '' : '<br>🔒 interne'}</td>
        <td>${estDirection ? `<div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalDiscipline('${escJs(f.id)}')" title="Modifier">✏️</button>
          <button class="btn btn-outline btn-xs" onclick="supprimerDiscipline('${escJs(f.id)}')" title="Supprimer">🗑</button></div>` : ''}</td></tr>`;
    }).join('') : `<tr><td colspan="7">${emptyHtml('📋', 'Aucun fait enregistré')}</td></tr>`;
  };
  window._rechargerDiscipline = charger;
  window._disEleves = eleves;
  window._disFaits = () => faits;

  $('#content').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">🧑‍⚖️ Discipline & vie scolaire <span id="dis-count"></span></span>
      <button class="btn btn-primary btn-sm" onclick="modalDiscipline()">+ Signaler un fait</button>
    </div>
    <div class="filters">
      <div class="fg"><label>Classe</label><select id="dis-f-classe"><option value="">Toutes</option>${classes.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
      <div class="fg"><label>Type</label><select id="dis-f-type"><option value="">Tous</option>${Object.entries(DISCIPLINE_TYPES).map(([k, v]) => `<option value="${k}">${v.lib}</option>`).join('')}</select></div>
      <div class="fg"><label>Du</label><input type="date" id="dis-f-du"></div>
      <div class="fg"><label>Au</label><input type="date" id="dis-f-au"></div>
    </div>
    <div class="tbl-wrap"><table><thead><tr><th>Date</th><th>Élève</th><th>Type</th><th>Motif</th><th>Sanction</th><th>Saisi par</th><th></th></tr></thead>
    <tbody id="dis-body"></tbody></table></div>
  </div>`;
  [['dis-f-classe', 'classe'], ['dis-f-type', 'type'], ['dis-f-du', 'du'], ['dis-f-au', 'au']].forEach(([id, k]) =>
    $('#' + id).addEventListener('change', e => { filtres[k] = e.target.value; charger(); }));
  charger();
}

function modalDiscipline(id) {
  const estDirection = ['admin', 'directeur'].includes(currentUser?.role);
  const existant = id ? window._disFaits().find(f => f.id === id) : null;
  const types = Object.entries(DISCIPLINE_TYPES).filter(([k]) => estDirection || !['blame', 'exclusion_temporaire'].includes(k));
  const eleves = (window._disEleves || []).filter(e => e.statut === 'actif');
  openModal(existant ? 'Modifier le fait' : 'Signaler un fait', `
    <form id="f-dis" style="display:flex;flex-direction:column;gap:12px">
      ${existant ? `<div><strong>${esc(existant.prenom)} ${esc(existant.nom)}</strong></div>` : `
      <div class="fg"><label>Élève*</label><select name="eleve_id" required><option value="">— Choisir —</option>
        ${eleves.map(e => `<option value="${esc(e.id)}">${esc(e.nom)} ${esc(e.prenom)} — ${esc(e.classe || '')}</option>`).join('')}</select></div>`}
      <div class="form-2">
        <div class="fg"><label>Type*</label><select name="type" id="dis-type">${types.map(([k, v]) => `<option value="${k}" ${existant?.type === k ? 'selected' : ''}>${v.lib}</option>`).join('')}</select></div>
        <div class="fg"><label>Date*</label><input type="date" name="date_fait" value="${esc(existant?.date_fait || today())}" required></div>
      </div>
      <div class="fg"><label>Motif*</label><input name="motif" required maxlength="300" value="${esc(existant?.motif || '')}" placeholder="Ex. : bavardages répétés, retard, bagarre…"></div>
      <div class="fg"><label>Détails</label><textarea name="description" rows="3">${esc(existant?.description || '')}</textarea></div>
      <div class="form-2">
        <div class="fg"><label>Sanction / suite donnée</label><input name="sanction" value="${esc(existant?.sanction || '')}"></div>
        <div class="fg" id="dis-jours" style="display:none"><label>Durée d'exclusion (jours)*</label><input type="number" name="nb_jours" min="1" max="60" value="${existant?.nb_jours || ''}"></div>
      </div>
      <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" name="visible_parents" ${existant && !existant.visible_parents ? '' : 'checked'}> Visible par les parents</label>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);
  const majJours = () => { $('#dis-jours').style.display = $('#dis-type').value === 'exclusion_temporaire' ? '' : 'none'; };
  $('#dis-type').onchange = majJours; majJours();
  $('#f-dis').onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const corps = Object.fromEntries(fd);
    corps.visible_parents = fd.get('visible_parents') === 'on';
    if (corps.type !== 'exclusion_temporaire') delete corps.nb_jours; else corps.nb_jours = parseInt(corps.nb_jours || '0', 10);
    try {
      if (existant) { delete corps.eleve_id; await apiUpdateDiscipline(existant.id, corps); }
      else await apiCreateDiscipline(corps);
      toast('Enregistré', 'success'); closeModal(); window._rechargerDiscipline();
    } catch (err) { toast(err.message, 'error'); }
  };
}
window.modalDiscipline = modalDiscipline;

async function supprimerDiscipline(id) {
  if (!confirmDel('Supprimer définitivement ce fait ? (la suppression est tracée au journal)')) return;
  try { await apiDeleteDiscipline(id); toast('Supprimé', 'success'); window._rechargerDiscipline(); }
  catch (e) { toast(e.message, 'error'); }
}
window.supprimerDiscipline = supprimerDiscipline;
