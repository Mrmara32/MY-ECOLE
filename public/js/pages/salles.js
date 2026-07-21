/* ===================== SALLES ===================== */
let _sallesCache = [];

async function refreshSalles() {
  try { _sallesCache = await apiGetSalles('actives=0'); } catch(e) { console.warn('Impossible de charger les salles', e); }
}

async function pageSalles() {
  $('#content').innerHTML = loadingHtml;
  try {
    const salles = await apiGetSalles('actives=0');
    _sallesCache = salles;

    const render = data => {
      $('#tb-salles').innerHTML = data.length ? data.map(s => `<tr>
        <td><strong>${esc(s.nom)}</strong></td>
        <td>${s.capacite ?? '—'}</td>
        <td>${esc(s.batiment||'—')}</td>
        <td><span class="badge ${s.active?'bdg-ok':'bdg-gray'}">${s.active?'Active':'Désactivée'}</span></td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalSalle('${escJs(s.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delSalle('${escJs(s.id)}')">🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('🏫','Aucune salle')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">🏫 Salles de classe (${salles.length})</span>
        <button class="btn btn-primary btn-sm" onclick="modalSalle()">+ Ajouter une salle</button>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-salle" placeholder="Nom de la salle…"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-salles"><th>Nom</th><th>Capacité</th><th>Bâtiment</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-salles"></tbody>
      </table></div>
    </div>`;

    let curr = salles;
    render(curr);
    $('#q-salle').addEventListener('input', () => {
      const q = $('#q-salle').value.toLowerCase();
      curr = salles.filter(s => s.nom.toLowerCase().includes(q));
      render(curr);
    });
    makeSortableTable('#th-salles', () => curr, render, ['nom', 'capacite', 'batiment', 'active', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function modalSalle(id = null) {
  const data = id ? _sallesCache.find(s => s.id === id) || {} : {};
  openModal(id ? 'Modifier la salle' : 'Ajouter une salle', `
    <form id="f-salle" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Nom de la salle*</label><input name="nom" value="${esc(data.nom||'')}" required placeholder="Ex : Salle 12"></div>
      <div class="form-2">
        <div class="fg"><label>Capacité</label><input type="number" name="capacite" value="${data.capacite??''}" placeholder="35"></div>
        <div class="fg"><label>Bâtiment</label><input name="batiment" value="${esc(data.batiment||'')}" placeholder="Bâtiment A"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-salle').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (fd.capacite) fd.capacite = parseInt(fd.capacite); else delete fd.capacite;
    try {
      if (id) await apiUpdateSalle(id, fd); else await apiCreateSalle(fd);
      toast(id?'Modifiée':'Ajoutée','success'); closeModal();
      await refreshSalles();
      pageSalles();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delSalle(id) {
  if (!confirmDel('Supprimer cette salle ?')) return;
  try { await apiDeleteSalle(id); toast('Supprimée','success'); await refreshSalles(); pageSalles(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalSalle = modalSalle;
window.delSalle = delSalle;
