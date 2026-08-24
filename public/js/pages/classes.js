/* ===================== CLASSES ===================== */
async function pageClasses() {
  $('#content').innerHTML = loadingHtml;
  try {
    const classes = await apiGetClassesFull('actives=0');

    const render = (data) => {
      $('#tb-classes').innerHTML = data.length ? data.map(c => `<tr>
        <td><strong>${esc(c.nom)}</strong></td>
        <td><span class="badge bdg-primary">${esc(CYCLE_LABELS[c.cycle]||c.cycle)}</span></td>
        <td>${c.ordre}</td>
        <td><span class="badge ${c.active?'bdg-ok':'bdg-gray'}">${c.active?'Active':'Désactivée'}</span></td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalClasse('${escJs(c.id)}')">✏️</button>
          <button class="btn btn-outline btn-xs" onclick="toggleClasse('${escJs(c.id)}',${c.active?0:1})">${c.active?'⏸ Désactiver':'▶ Activer'}</button>
          <button class="btn btn-danger btn-xs" onclick="delClasse('${escJs(c.id)}')">🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('🏫','Aucune classe')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">🏫 Classes (${classes.length})</span>
        <button class="btn btn-primary btn-sm" onclick="modalClasse()">+ Ajouter une classe</button>
      </div>
      <div class="card-body" style="padding-bottom:0">
        <div class="alert alert-info">💡 Les classes sont regroupées en 6 cycles : Maternelle, Primaire, Collège, Lycée, Enseignement supérieur, Centre de formation.
        Le cycle détermine notamment le mode de rémunération des enseignants (mensuel pour maternelle/primaire, horaire pour les autres).</div>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-cls" placeholder="Nom de la classe…"></div>
        <div class="fg"><label>Cycle</label><select id="f-clscycle">
          <option value="">Tous</option>
          <option value="maternelle">Maternelle</option><option value="primaire">Primaire</option>
          <option value="college">Collège</option><option value="lycee">Lycée</option>
          <option value="superieur">Enseignement supérieur</option><option value="formation">Centre de formation</option>
        </select></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-classes"><th>Nom</th><th>Cycle</th><th>Ordre</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-classes"></tbody>
      </table></div>
    </div>`;
    let curr = classes;
    render(curr);
    const filter = () => {
      const q = $('#q-cls').value.toLowerCase();
      const cycle = $('#f-clscycle').value;
      curr = classes.filter(c => (!q || c.nom.toLowerCase().includes(q)) && (!cycle || c.cycle === cycle));
      render(curr);
    };
    $('#q-cls').addEventListener('input', filter);
    $('#f-clscycle').addEventListener('change', filter);

    makeSortableTable('#th-classes', () => curr, render, ['nom', 'cycle', 'ordre', 'active', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

async function modalClasse(id = null) {
  let data = {};
  if (id) {
    const all = await apiGetClassesFull('actives=0');
    data = all.find(c => c.id === id) || {};
  }
  openModal(id ? 'Modifier la classe' : 'Ajouter une classe', `
    <form id="f-classe" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Nom de la classe*</label><input name="nom" value="${esc(data.nom||'')}" required placeholder="Ex : 6ème C"></div>
      <div class="fg"><label>Cycle*</label><select name="cycle" required>
        <option value="maternelle" ${data.cycle==='maternelle'?'selected':''}>Maternelle</option>
        <option value="primaire" ${data.cycle==='primaire'?'selected':''}>Primaire</option>
        <option value="college" ${data.cycle==='college'?'selected':''}>Collège</option>
        <option value="lycee" ${data.cycle==='lycee'?'selected':''}>Lycée</option>
        <option value="superieur" ${data.cycle==='superieur'?'selected':''}>Enseignement supérieur</option>
        <option value="formation" ${data.cycle==='formation'?'selected':''}>Centre de formation</option>
      </select></div>
      <div class="fg"><label>Ordre d'affichage</label><input type="number" name="ordre" value="${data.ordre??''}" placeholder="0"></div>
      ${id ? motifFieldHtml() : ''}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-classe').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (fd.ordre === '') delete fd.ordre; else fd.ordre = parseInt(fd.ordre);
    try {
      if (id) await apiUpdateClasse(id, fd); else await apiCreateClasse(fd);
      toast(id?'Classe modifiée':'Classe ajoutée', 'success');
      closeModal();
      await refreshClasses();
      pageClasses();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function toggleClasse(id, active) {
  try { await apiUpdateClasse(id, { active }); toast(active?'Classe activée':'Classe désactivée','success'); await refreshClasses(); pageClasses(); }
  catch(e) { toast(e.message,'error'); }
}

async function delClasse(id) {
  if (!confirmDel('Supprimer définitivement cette classe ?')) return;
  try { await apiDeleteClasse(id); toast('Classe supprimée','success'); await refreshClasses(); pageClasses(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalClasse = modalClasse;
window.toggleClasse = toggleClasse;
window.delClasse = delClasse;
