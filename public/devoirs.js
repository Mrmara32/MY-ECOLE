/* ===================== DEVOIRS ===================== */
async function pageDevoirs() {
  $('#content').innerHTML = loadingHtml;
  try {
    let list = await apiGetDevoirs();
    const classes = [...new Set(list.map(d=>d.classe).filter(Boolean))].sort();

    const render = data => {
      $('#tb-devoirs').innerHTML = data.length ? data.map(dv => {
        const jr = dv.date_remise ? jresteText(dv.date_remise) : null;
        const sBadge = { 'En cours':'bdg-info', 'Rendu':'bdg-ok', 'Annulé':'bdg-err' };
        return `<tr>
          <td><strong>${esc(dv.titre)}</strong>${dv.description?`<div class="text-muted" style="font-size:11px;margin-top:2px">${esc(dv.description.substring(0,80))}…</div>`:''}</td>
          <td><span class="badge bdg-primary">${esc(dv.matiere||'—')}</span></td>
          <td><span class="badge bdg-gray">${esc(dv.classe||'—')}</span></td>
          <td>${fmtDate(dv.date_assignation)}</td>
          <td>${jr?`<span class="badge ${jr.cls}">${jr.txt}</span>`:fmtDate(dv.date_remise)}</td>
          <td><span class="badge ${sBadge[dv.statut]||'bdg-gray'}">${esc(dv.statut)}</span></td>
          <td><div class="td-actions">
            <button class="btn btn-outline btn-xs" onclick="modalDevoir('${escJs(dv.id)}')">✏️</button>
            <button class="btn btn-ok btn-xs" onclick="changerStatutDevoir('${escJs(dv.id)}','Rendu')" title="Marquer rendu">✔</button>
            <button class="btn btn-danger btn-xs" onclick="delDevoir('${escJs(dv.id)}')">🗑</button>
          </div></td>
        </tr>`;
      }).join('') : `<tr><td colspan="7">${emptyHtml('📚','Aucun devoir enregistré')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">📚 Devoirs (${list.length})</span>
        <button class="btn btn-primary btn-sm" onclick="modalDevoir()">+ Ajouter un devoir</button>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-dv" placeholder="Titre, matière…"></div>
        <div class="fg"><label>Classe</label><select id="f-dcls"><option value="">Toutes</option>${classes.map(c=>`<option>${esc(c)}</option>`).join('')}<option>—</option>${CLASSES.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
        <div class="fg"><label>Statut</label><select id="f-dstat">
          <option value="">Tous</option>
          <option value="En cours">En cours</option>
          <option value="Rendu">Rendu</option>
          <option value="Annulé">Annulé</option>
        </select></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-devoirs"><th>Titre</th><th>Matière</th><th>Classe</th><th>Assigné le</th><th>À rendre</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-devoirs"></tbody>
      </table></div>
    </div>`;

    let curr = list;
    render(curr);
    const filter = () => {
      const q = $('#q-dv').value.toLowerCase();
      const cls = $('#f-dcls').value;
      const stat = $('#f-dstat').value;
      curr = list.filter(d => {
        const txt = `${d.titre} ${d.matiere||''} ${d.description||''}`.toLowerCase();
        return (!q||txt.includes(q)) && (!cls||d.classe===cls) && (!stat||d.statut===stat);
      });
      render(curr);
    };
    ['#f-dcls','#f-dstat'].forEach(sel => $(sel).addEventListener('change', filter));
    $('#q-dv').addEventListener('input', filter);

    makeSortableTable('#th-devoirs', () => curr, render,
      ['titre', 'matiere', 'classe', 'date_assignation', 'date_remise', 'statut', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

async function modalDevoir(id = null) {
  let data = {};
  if (id) { const list = await apiGetDevoirs(); data = list.find(d=>d.id===id)||{}; }
  openModal(id?'Modifier le devoir':'Nouveau devoir', `
    <form id="f-dv" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Titre*</label><input name="titre" value="${esc(data.titre||'')}" required placeholder="Ex : Exercice page 45"></div>
      <div class="form-3">
        <div class="fg"><label>Matière</label><select name="matiere">${optionsHtml(MATIERES, data.matiere||'')}</select></div>
        <div class="fg"><label>Classe</label><select name="classe">${optionsHtml(CLASSES, data.classe||'')}</select></div>
        <div class="fg"><label>Statut</label><select name="statut">
          <option value="En cours" ${(!data.statut||data.statut==='En cours')?'selected':''}>En cours</option>
          <option value="Rendu" ${data.statut==='Rendu'?'selected':''}>Rendu</option>
          <option value="Annulé" ${data.statut==='Annulé'?'selected':''}>Annulé</option>
        </select></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Date assignation</label><input type="date" name="date_assignation" value="${esc(data.date_assignation||today())}"></div>
        <div class="fg"><label>Date de remise</label><input type="date" name="date_remise" value="${esc(data.date_remise||'')}"></div>
      </div>
      <div class="fg"><label>Description</label><textarea name="description" rows="3">${esc(data.description||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Créer'}</button>
      </div>
    </form>`);
  $('#f-dv').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      if (id) await apiUpdateDevoir(id, fd); else await apiCreateDevoir(fd);
      toast(id?'Modifié':'Devoir créé','success'); closeModal(); pageDevoirs();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function changerStatutDevoir(id, statut) {
  try { await apiUpdateDevoir(id, { statut }); toast('Statut mis à jour','success'); pageDevoirs(); }
  catch(e) { toast(e.message,'error'); }
}
async function delDevoir(id) {
  if (!confirmDel()) return;
  try { await apiDeleteDevoir(id); toast('Supprimé','success'); pageDevoirs(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalDevoir = modalDevoir;
window.changerStatutDevoir = changerStatutDevoir;
window.delDevoir = delDevoir;
