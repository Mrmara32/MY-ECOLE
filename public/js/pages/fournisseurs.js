/* ===================== FOURNISSEURS ===================== */
async function pageFournisseurs() {
  $('#content').innerHTML = loadingHtml;
  const fournisseurs = await apiGetFournisseurs();

  $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">🏭 Fournisseurs (${fournisseurs.length})</span>
        <div class="card-actions">
          ${['admin','directeur','comptable'].includes(currentUser.role) ? `<button class="btn btn-primary btn-sm" onclick="modalFournisseur()">+ Nouveau fournisseur</button>` : ''}
        </div>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-four" placeholder="Nom du fournisseur…" oninput="filtrerFournisseurs()"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Nom</th><th>Catégorie</th><th>Contact</th><th class="text-right">Total payé</th><th class="text-right">Opérations</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-four">${renderLignesFournisseurs(fournisseurs)}</tbody>
      </table></div>
    </div>`;
  window._fournisseursCache = fournisseurs;
}
window.pageFournisseurs = pageFournisseurs;

function renderLignesFournisseurs(liste) {
  if (!liste.length) return `<tr><td colspan="7">${emptyHtml('🏭', 'Aucun fournisseur enregistré', 'Ajoutez vos fournisseurs pour suivre facilement ce que vous leur payez.')}</td></tr>`;
  return liste.map(f => `<tr>
    <td><strong>${esc(f.nom)}</strong></td>
    <td>${f.categorie ? `<span class="badge bdg-gray">${esc(f.categorie)}</span>` : '—'}</td>
    <td class="text-muted" style="font-size:12px">${esc(f.telephone||f.email||'—')}</td>
    <td class="text-right mono fw-600">${fmtMoney(f.total_paye)}</td>
    <td class="text-right">${f.nb_transactions}</td>
    <td>${f.actif ? '<span class="badge bdg-ok">Actif</span>' : '<span class="badge bdg-gray">Inactif</span>'}</td>
    <td class="td-actions">
      <button class="btn btn-outline btn-xs" onclick="modalDetailFournisseur('${escJs(f.id)}')">👁 Détail</button>
      ${['admin','directeur','comptable'].includes(currentUser.role) ? `<button class="btn btn-outline btn-xs" onclick="modalFournisseur('${escJs(f.id)}')">✏️</button>` : ''}
    </td>
  </tr>`).join('');
}

function filtrerFournisseurs() {
  const q = $('#q-four').value.trim().toLowerCase();
  const filtres = (window._fournisseursCache||[]).filter(f => f.nom.toLowerCase().includes(q));
  $('#tb-four').innerHTML = renderLignesFournisseurs(filtres);
}
window.filtrerFournisseurs = filtrerFournisseurs;

async function modalFournisseur(id) {
  const data = id ? await apiGetFournisseur(id) : {};
  openModal(id ? 'Modifier le fournisseur' : 'Nouveau fournisseur', `
    <form id="f-four" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Nom*</label><input name="nom" value="${esc(data.nom||'')}" required placeholder="Ex : Papeterie Centrale"></div>
      <div class="form-2">
        <div class="fg"><label>Catégorie</label><input name="categorie" value="${esc(data.categorie||'')}" placeholder="Ex : Fournitures, Alimentation…"></div>
        <div class="fg"><label>Téléphone</label><input name="telephone" value="${esc(data.telephone||'')}"></div>
      </div>
      <div class="fg"><label>Email</label><input type="email" name="email" value="${esc(data.email||'')}"></div>
      <div class="fg"><label>Adresse</label><input name="adresse" value="${esc(data.adresse||'')}"></div>
      <div class="fg"><label>Notes</label><textarea name="notes" rows="2">${esc(data.notes||'')}</textarea></div>
      ${id ? `<div class="fg"><label style="display:flex;align-items:center;gap:8px;font-weight:400">
        <input type="checkbox" name="actif" ${data.actif?'checked':''} style="width:auto"> Fournisseur actif
      </label></div>` : ''}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);

  $('#f-four').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.actif = $('#f-four [name="actif"]') ? $('#f-four [name="actif"]').checked : true;
    try {
      if (id) await apiUpdateFournisseur(id, fd);
      else await apiCreateFournisseur(fd);
      toast('Fournisseur enregistré', 'success');
      closeModal();
      pageFournisseurs();
    } catch (err) { toast(err.message, 'error'); }
  };
}
window.modalFournisseur = modalFournisseur;

async function modalDetailFournisseur(id) {
  const f = await apiGetFournisseur(id);
  openModal(`🏭 ${esc(f.nom)}`, `
    <div style="display:flex;flex-direction:column;gap:16px">
      <div class="stats-grid" style="grid-template-columns:repeat(2,1fr)">
        <div class="stat"><div class="stat-label">Total payé</div><div class="stat-val" style="font-size:16px">${fmtMoney(f.total_paye)}</div></div>
        <div class="stat"><div class="stat-label">Opérations</div><div class="stat-val" style="font-size:16px">${f.historique.length}</div></div>
      </div>
      ${f.telephone||f.email ? `<div class="text-muted" style="font-size:12.5px">${esc(f.telephone||'')} ${f.email?' · '+esc(f.email):''}</div>` : ''}
      <div>
        <div style="font-weight:700;font-size:13px;margin-bottom:8px">Historique des paiements</div>
        <div class="tbl-wrap" style="max-height:300px;overflow-y:auto"><table>
          <thead><tr><th>Date</th><th>Description</th><th class="text-right">Montant</th></tr></thead>
          <tbody>
            ${f.historique.length ? f.historique.map(t => `<tr>
              <td>${fmtDate(t.date_op)}</td>
              <td>${esc(t.description||t.categorie||'—')}</td>
              <td class="text-right mono">${fmtMoney(t.montant)}</td>
            </tr>`).join('') : `<tr><td colspan="3" class="text-muted text-center">Aucune opération encore</td></tr>`}
          </tbody>
        </table></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button>
      </div>
    </div>`);
}
window.modalDetailFournisseur = modalDetailFournisseur;
