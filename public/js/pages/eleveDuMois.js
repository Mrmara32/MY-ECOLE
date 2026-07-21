/* ===================== ÉLÈVE DU MOIS ===================== */
async function pageEleveDuMois() {
  $('#content').innerHTML = loadingHtml;
  try {
    const historique = await apiGetEleveDuMoisAll();
    const actuel = historique[0];

    $('#content').innerHTML = `
    ${actuel ? `
    <div class="card mb-4" style="background:linear-gradient(135deg,var(--c-primary) 0%,#312E81 100%);color:#fff;overflow:hidden">
      <div class="card-body" style="display:flex;gap:24px;align-items:center">
        ${actuel.photo_url
          ? `<img src="${esc(actuel.photo_url)}" style="width:110px;height:110px;border-radius:50%;object-fit:cover;border:4px solid rgba(255,255,255,.4)">`
          : `<div style="width:110px;height:110px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;font-size:44px">⭐</div>`}
        <div>
          <div style="font-size:12px;text-transform:uppercase;letter-spacing:1px;opacity:.85">⭐ Élève du mois — ${esc(actuel.mois)}</div>
          <div style="font-size:24px;font-weight:700;margin:4px 0">${esc(actuel.prenom)} ${esc(actuel.nom)}</div>
          <div style="opacity:.9;margin-bottom:6px">Classe : ${esc(actuel.classe||'—')} · Matricule : ${esc(actuel.matricule||'—')}</div>
          ${actuel.motif ? `<div style="font-style:italic;opacity:.95">"${esc(actuel.motif)}"</div>` : ''}
        </div>
      </div>
    </div>` : `<div class="alert alert-info mb-4">Aucun élève du mois désigné pour l'instant.</div>`}

    <div class="card">
      <div class="card-header">
        <span class="card-title">⭐ Historique (${historique.length})</span>
        ${currentUser.role !== 'enseignant' ? `<button class="btn btn-primary btn-sm" onclick="modalEleveDuMois()">+ Désigner l'élève du mois</button>` : ''}
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-edm" placeholder="Nom, prénom, classe…"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-edm"><th>Photo</th><th>Mois</th><th>Élève</th><th>Classe</th><th>Motif</th><th>Désigné par</th><th>Actions</th></tr></thead>
        <tbody id="tb-edm"></tbody>
      </table></div>
    </div>`;

    const render = data => {
      $('#tb-edm').innerHTML = data.length ? data.map(h => `<tr>
            <td>${elevePhoto(h, 36)}</td>
            <td><span class="badge bdg-primary">${esc(h.mois)}</span></td>
            <td><strong>${esc(h.prenom)} ${esc(h.nom)}</strong></td>
            <td>${esc(h.classe||'—')}</td>
            <td style="max-width:260px;font-size:13px">${esc(h.motif||'—')}</td>
            <td class="text-muted" style="font-size:12px">${esc(h.designe_par_nom||'—')}</td>
            <td><button class="btn btn-danger btn-xs" onclick="delEleveDuMois('${escJs(h.id)}')">🗑</button></td>
          </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('⭐','Aucune désignation')}</td></tr>`;
    };

    let curr = historique;
    render(curr);
    $('#q-edm').addEventListener('input', () => {
      const q = $('#q-edm').value.toLowerCase();
      curr = historique.filter(h => `${h.nom} ${h.prenom} ${h.classe||''}`.toLowerCase().includes(q));
      render(curr);
    });
    makeSortableTable('#th-edm', () => curr, render,
      [null, 'mois', row => `${row.prenom} ${row.nom}`, 'classe', 'motif', 'designe_par_nom', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

async function modalEleveDuMois() {
  const eleves = await apiGetEleves('statut=actif');
  openModal('Désigner l\'élève du mois', `
    <form id="f-edm" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Mois*</label><input type="month" name="mois" value="${moisCourant()}" required></div>
      <div class="fg"><label>Élève*</label>
        <select name="eleve_id" required>
          <option value="">— Choisir un élève —</option>
          ${eleves.map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Motif / Citation</label><textarea name="motif" rows="3" placeholder="Ex : Pour son excellent comportement et ses résultats remarquables ce mois-ci"></textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Désigner</button>
      </div>
    </form>`, { narrow: true });
  $('#f-edm').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { await apiDesignerEleveDuMois(fd); toast('Élève du mois désigné ⭐','success'); closeModal(); pageEleveDuMois(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function delEleveDuMois(id) {
  if (!confirmDel('Retirer cette désignation ?')) return;
  try { await apiDeleteEleveDuMois(id); toast('Supprimé','success'); pageEleveDuMois(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalEleveDuMois = modalEleveDuMois;
window.delEleveDuMois = delEleveDuMois;
