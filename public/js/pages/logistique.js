/* ===================== LOGISTIQUE ===================== */
let _logProduits = [];
let _logFournisseurs = [];
let _logVehicules = [];
let _logSalles = [];
let _logPersonnel = [];
let _logEleves = [];

const CAT_LABELS = { materiel:'Matériel', fourniture:'Fourniture', alimentaire:'Alimentaire', entretien:'Entretien', autre:'Autre' };
const PRIO_BADGE = { basse:'bdg-gray', normale:'bdg-primary', haute:'bdg-warn', urgente:'bdg-err' };
const PRIO_LABEL = { basse:'Basse', normale:'Normale', haute:'Haute', urgente:'Urgente' };
const MSTATUT_BADGE = { signalee:'bdg-err', en_cours:'bdg-warn', resolue:'bdg-ok', annulee:'bdg-gray' };
const MSTATUT_LABEL = { signalee:'Signalée', en_cours:'En cours', resolue:'Résolue', annulee:'Annulée' };
const CSTATUT_BADGE = { brouillon:'bdg-gray', envoyee:'bdg-warn', recue:'bdg-ok', annulee:'bdg-err' };
const CSTATUT_LABEL = { brouillon:'Brouillon', envoyee:'Envoyée', recue:'Reçue', annulee:'Annulée' };

async function pageLogistique() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [produits, fournisseurs, vehicules, salles, personnel, eleves] = await Promise.all([
      apiGetStockProduits(), apiGetFournisseurs(), apiGetVehicules(), apiGetSalles('actives=0'), apiGetPersonnel(), apiGetEleves(),
    ]);
    _logProduits = produits; _logFournisseurs = fournisseurs; _logVehicules = vehicules;
    _logSalles = salles; _logPersonnel = personnel; _logEleves = eleves;
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }

  let activeTab = 'stocks';
  const renderContent = () => {
    if (activeTab === 'stocks') renderLogStocks();
    else if (activeTab === 'achats') renderLogAchats();
    else if (activeTab === 'maintenance') renderLogMaintenance();
    else renderLogTransport();
  };

  $('#content').innerHTML = `
  <div class="tabs" id="log-tabs">
    <div class="tab active" onclick="setLogTab('stocks')">📦 Stocks</div>
    <div class="tab" onclick="setLogTab('achats')">🧾 Achats</div>
    <div class="tab" onclick="setLogTab('maintenance')">🔧 Maintenance</div>
    <div class="tab" onclick="setLogTab('transport')">🚌 Transport</div>
  </div>
  <div id="log-body"></div>`;

  window.setLogTab = (tab) => {
    activeTab = tab;
    $$('#log-tabs .tab').forEach((t,i) => t.classList.toggle('active', i===['stocks','achats','maintenance','transport'].indexOf(tab)));
    renderContent();
  };
  renderContent();
}

/* ───────────── STOCKS ───────────── */
async function renderLogStocks() {
  let curr = _logProduits;
  const render = data => {
    const { items, page, totalPages, total } = paginate('log-stock', data);
    $('#tb-stock').innerHTML = items.length ? items.map(p => {
      const alerte = p.quantite <= p.seuil_alerte;
      return `<tr${alerte?' style="background:rgba(220,38,38,.06)"':''}>
        <td><strong>${esc(p.nom)}</strong></td>
        <td><span class="badge bdg-primary">${esc(CAT_LABELS[p.categorie]||p.categorie)}</span></td>
        <td class="mono text-right">${p.quantite} ${esc(p.unite)}</td>
        <td class="mono text-right">${p.seuil_alerte} ${esc(p.unite)}</td>
        <td class="mono text-right">${fmtMoney(p.prix_unitaire)}</td>
        <td>${alerte?'<span class="badge bdg-err">⚠ Stock bas</span>':'<span class="badge bdg-ok">OK</span>'}</td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalMouvementStock('${escJs(p.id)}')">↕ Mouvement</button>
          <button class="btn btn-outline btn-xs" onclick="modalStockProduit('${escJs(p.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delStockProduit('${escJs(p.id)}')">🗑</button>
        </div></td>
      </tr>`;
    }).join('') : `<tr><td colspan="7">${emptyHtml('📦','Aucun produit en stock')}</td></tr>`;
    $('#pag-stock').innerHTML = paginationHtml('log-stock', page, totalPages, total);
  };
  const nbAlertes = _logProduits.filter(p=>p.quantite<=p.seuil_alerte).length;
  $('#log-body').innerHTML = `
  ${nbAlertes ? `<div class="alert alert-danger mb-3">⚠ ${nbAlertes} produit(s) sous le seuil d'alerte</div>` : ''}
  <div class="card">
    <div class="card-header">
      <span class="card-title">📦 Stock & fournitures (${_logProduits.length})</span>
      <button class="btn btn-primary btn-sm" onclick="modalStockProduit()">+ Produit</button>
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-stock" placeholder="Nom du produit…"></div>
      <div class="fg"><label>Catégorie</label><select id="f-stockcat"><option value="">Toutes</option>${Object.entries(CAT_LABELS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Produit</th><th>Catégorie</th><th class="text-right">Quantité</th><th class="text-right">Seuil</th><th class="text-right">Prix unit.</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody id="tb-stock"></tbody>
    </table></div>
    <div id="pag-stock"></div>
  </div>`;
  getPaginator('log-stock').onChange = () => render(curr);
  render(curr);
  const filter = () => {
    const q = $('#q-stock').value.toLowerCase();
    const cat = $('#f-stockcat').value;
    curr = _logProduits.filter(p => p.nom.toLowerCase().includes(q) && (!cat || p.categorie===cat));
    resetPaginator('log-stock');
    render(curr);
  };
  $('#q-stock').addEventListener('input', filter);
  $('#f-stockcat').addEventListener('change', filter);
}

function modalStockProduit(id = null) {
  const data = id ? _logProduits.find(p=>p.id===id) || {} : {};
  openModal(id?'Modifier le produit':'Ajouter un produit', `
    <form id="f-prod" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Nom du produit*</label><input name="nom" value="${esc(data.nom||'')}" required placeholder="Ex : Craie blanche"></div>
      <div class="form-2">
        <div class="fg"><label>Catégorie*</label><select name="categorie" required>${Object.entries(CAT_LABELS).map(([k,v])=>`<option value="${k}" ${data.categorie===k?'selected':''}>${v}</option>`).join('')}</select></div>
        <div class="fg"><label>Unité</label><input name="unite" value="${esc(data.unite||'unité')}" placeholder="boîte, sac, litre…"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Seuil d'alerte</label><input type="number" name="seuil_alerte" value="${data.seuil_alerte??0}" min="0"></div>
        <div class="fg"><label>Prix unitaire (GNF)</label><input type="number" name="prix_unitaire" value="${data.prix_unitaire??0}" min="0"></div>
      </div>
      ${!id ? `<div class="fg"><label>Quantité initiale</label><input type="number" name="quantite" value="0" min="0"></div>` : ''}
      <div class="fg"><label>Notes</label><textarea name="notes" rows="2">${esc(data.notes||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-prod').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.seuil_alerte = parseFloat(fd.seuil_alerte)||0;
    fd.prix_unitaire = parseFloat(fd.prix_unitaire)||0;
    if (fd.quantite !== undefined) fd.quantite = parseFloat(fd.quantite)||0;
    try {
      if (id) await apiUpdateStockProduit(id, fd); else await apiCreateStockProduit(fd);
      toast(id?'Produit modifié':'Produit ajouté','success'); closeModal();
      _logProduits = await apiGetStockProduits(); renderLogStocks();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delStockProduit(id) {
  if (!confirmDel('Supprimer ce produit du stock ?')) return;
  try { await apiDeleteStockProduit(id); toast('Supprimé','success'); _logProduits = await apiGetStockProduits(); renderLogStocks(); }
  catch(e) { toast(e.message,'error'); }
}

async function modalMouvementStock(produitId) {
  const p = _logProduits.find(x=>x.id===produitId);
  const mouvements = await apiGetStockMouvements(`produit_id=${produitId}`);
  openModal(`Mouvements — ${esc(p.nom)}`, `
    <div style="margin-bottom:16px">
      <div class="stats-grid" style="grid-template-columns:1fr">
        <div class="stat"><div class="stat-label">Quantité actuelle</div><div class="stat-val">${p.quantite} ${esc(p.unite)}</div></div>
      </div>
    </div>
    <form id="f-mvt" style="display:flex;gap:10px;align-items:flex-end;margin-bottom:16px;flex-wrap:wrap">
      <div class="fg"><label>Type*</label><select name="type" required><option value="entree">Entrée</option><option value="sortie">Sortie</option></select></div>
      <div class="fg"><label>Quantité*</label><input type="number" name="quantite" min="0.01" step="0.01" required style="width:100px"></div>
      <div class="fg grow"><label>Motif</label><input name="motif" placeholder="Distribution, casse, achat…"></div>
      <button type="submit" class="btn btn-primary">Enregistrer</button>
    </form>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Date</th><th>Type</th><th class="text-right">Quantité</th><th>Motif</th></tr></thead>
      <tbody>${mouvements.length ? mouvements.map(m=>`<tr>
        <td>${fmtDate(m.date_mouvement)}</td>
        <td><span class="badge ${m.type==='entree'?'bdg-ok':'bdg-warn'}">${m.type==='entree'?'Entrée':'Sortie'}</span></td>
        <td class="mono text-right">${m.type==='entree'?'+':'-'}${m.quantite}</td>
        <td>${esc(m.motif||'—')}</td>
      </tr>`).join('') : `<tr><td colspan="4">${emptyHtml('↕','Aucun mouvement')}</td></tr>`}</tbody>
    </table></div>`, { wide: true });
  $('#f-mvt').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.produit_id = produitId;
    fd.quantite = parseFloat(fd.quantite)||0;
    try {
      await apiCreateStockMouvement(fd);
      toast('Mouvement enregistré','success'); closeModal();
      _logProduits = await apiGetStockProduits(); renderLogStocks();
    } catch(err) { toast(err.message,'error'); }
  };
}

/* ───────────── ACHATS ───────────── */
let _achatLignesCount = 0;
async function renderLogAchats() {
  const commandes = await apiGetCommandes();
  let curr = commandes;
  const render = data => {
    const { items, page, totalPages, total } = paginate('log-cmd', data);
    $('#tb-cmd').innerHTML = items.length ? items.map(c => `<tr>
      <td>${esc(c.numero||'—')}</td>
      <td>${esc(c.fournisseur_nom||'—')}</td>
      <td>${fmtDate(c.date_commande)}</td>
      <td class="mono text-right">${fmtMoney(c.montant_total)}</td>
      <td>${c.nb_lignes} article(s)</td>
      <td><span class="badge ${CSTATUT_BADGE[c.statut]||'bdg-gray'}">${CSTATUT_LABEL[c.statut]||c.statut}</span></td>
      <td><div class="td-actions">
        <button class="btn btn-outline btn-xs" onclick="modalDetailCommande('${escJs(c.id)}')">👁</button>
        ${c.statut==='brouillon' || c.statut==='envoyee' ? `<button class="btn btn-ok btn-xs" onclick="receptionnerCmd('${escJs(c.id)}')">✅ Réceptionner</button>`:''}
        ${c.statut==='brouillon' ? `<button class="btn btn-danger btn-xs" onclick="delCommande('${escJs(c.id)}')">🗑</button>`:''}
      </div></td>
    </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('🧾','Aucune commande')}</td></tr>`;
    $('#pag-cmd').innerHTML = paginationHtml('log-cmd', page, totalPages, total);
  };
  $('#log-body').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">🧾 Bons de commande (${commandes.length})</span>
      <button class="btn btn-primary btn-sm" onclick="modalCommande()">+ Nouvelle commande</button>
    </div>
    <div class="filters">
      <div class="fg"><label>Statut</label><select id="f-cmdstatut"><option value="">Tous</option>${Object.entries(CSTATUT_LABEL).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>N°</th><th>Fournisseur</th><th>Date</th><th class="text-right">Montant</th><th>Contenu</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody id="tb-cmd"></tbody>
    </table></div>
    <div id="pag-cmd"></div>
  </div>`;
  getPaginator('log-cmd').onChange = () => render(curr);
  render(curr);
  $('#f-cmdstatut').addEventListener('change', async () => {
    const s = $('#f-cmdstatut').value;
    curr = await apiGetCommandes(s?`statut=${s}`:'');
    resetPaginator('log-cmd');
    render(curr);
  });
}

function _ligneCommandeHtml(idx, l = {}) {
  return `<div class="form-4" id="ligne-${idx}" style="align-items:flex-end">
    <div class="fg grow"><label>Désignation*</label><input name="designation_${idx}" value="${esc(l.designation||'')}" required placeholder="Article, produit du stock…" list="dl-produits"></div>
    <div class="fg" style="max-width:90px"><label>Qté*</label><input type="number" name="quantite_${idx}" value="${l.quantite||1}" min="0.01" step="0.01" required></div>
    <div class="fg" style="max-width:130px"><label>Prix unit. (GNF)</label><input type="number" name="prix_${idx}" value="${l.prix_unitaire||0}" min="0"></div>
    <button type="button" class="btn btn-danger btn-xs" onclick="document.getElementById('ligne-${idx}').remove()">✕</button>
  </div>`;
}

function modalCommande() {
  _achatLignesCount = 1;
  openModal('Nouvelle commande', `
    <form id="f-cmd" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Fournisseur</label><select name="fournisseur_id"><option value="">— Aucun —</option>${_logFournisseurs.map(f=>`<option value="${esc(f.id)}">${esc(f.nom)}</option>`).join('')}</select></div>
        <div class="fg"><label>N° de commande</label><input name="numero" placeholder="CMD-2026-001"></div>
      </div>
      <datalist id="dl-produits">${_logProduits.map(p=>`<option value="${esc(p.nom)}">`).join('')}</datalist>
      <label>Articles</label>
      <div id="lignes-cmd">${_ligneCommandeHtml(0)}</div>
      <button type="button" class="btn btn-outline btn-sm" onclick="document.getElementById('lignes-cmd').insertAdjacentHTML('beforeend', _ligneCommandeHtml(_achatLignesCount++))">+ Ajouter une ligne</button>
      <div class="fg"><label>Notes</label><textarea name="notes" rows="2"></textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Créer la commande</button>
      </div>
    </form>`, { wide: true });
  $('#f-cmd').onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const lignes = [];
    $$('#lignes-cmd > div').forEach(div => {
      const idx = div.id.split('-')[1];
      const designation = fd.get(`designation_${idx}`);
      if (designation) {
        const produitCorrespondant = _logProduits.find(p=>p.nom===designation);
        lignes.push({
          produit_id: produitCorrespondant ? produitCorrespondant.id : null,
          designation, quantite: parseFloat(fd.get(`quantite_${idx}`))||1, prix_unitaire: parseFloat(fd.get(`prix_${idx}`))||0,
        });
      }
    });
    if (!lignes.length) { toast('Ajoutez au moins un article','error'); return; }
    try {
      await apiCreateCommande({ fournisseur_id: fd.get('fournisseur_id')||null, numero: fd.get('numero'), notes: fd.get('notes'), lignes });
      toast('Commande créée','success'); closeModal(); renderLogAchats();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function modalDetailCommande(id) {
  const c = await apiGetCommande(id);
  openModal(`Commande ${esc(c.numero||c.id)}`, `
    <div class="form-2" style="margin-bottom:14px">
      <div><strong>Fournisseur :</strong> ${esc(c.fournisseur_nom||'—')}</div>
      <div><strong>Statut :</strong> <span class="badge ${CSTATUT_BADGE[c.statut]||'bdg-gray'}">${CSTATUT_LABEL[c.statut]||c.statut}</span></div>
      <div><strong>Date :</strong> ${fmtDate(c.date_commande)}</div>
      <div><strong>Total :</strong> ${fmtMoney(c.montant_total)}</div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Désignation</th><th class="text-right">Qté</th><th class="text-right">Prix unit.</th><th class="text-right">Total</th></tr></thead>
      <tbody>${c.lignes.map(l=>`<tr>
        <td>${esc(l.designation)}</td>
        <td class="mono text-right">${l.quantite}</td>
        <td class="mono text-right">${fmtMoney(l.prix_unitaire)}</td>
        <td class="mono text-right">${fmtMoney(l.montant_ligne)}</td>
      </tr>`).join('')}</tbody>
    </table></div>
    ${c.notes ? `<div class="alert alert-info mt-3">${esc(c.notes)}</div>` : ''}
    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button>
    </div>`, { wide: true });
}

async function receptionnerCmd(id) {
  if (!confirm('Confirmer la réception ? Le stock des produits liés sera automatiquement mis à jour.')) return;
  try { await apiReceptionnerCommande(id); toast('Commande réceptionnée, stock mis à jour','success'); renderLogAchats(); }
  catch(e) { toast(e.message,'error'); }
}

async function delCommande(id) {
  if (!confirmDel('Supprimer cette commande ?')) return;
  try { await apiDeleteCommande(id); toast('Supprimée','success'); renderLogAchats(); }
  catch(e) { toast(e.message,'error'); }
}

/* ───────────── MAINTENANCE ───────────── */
async function renderLogMaintenance() {
  const interventions = await apiGetMaintenance();
  let curr = interventions;
  const render = data => {
    const { items, page, totalPages, total } = paginate('log-maint', data);
    $('#tb-maint').innerHTML = items.length ? items.map(m => `<tr>
      <td><strong>${esc(m.titre)}</strong>${m.equipement?`<br><span class="text-muted" style="font-size:11px">${esc(m.equipement)}</span>`:''}</td>
      <td>${esc(m.salle_nom||m.lieu||'—')}</td>
      <td><span class="badge ${PRIO_BADGE[m.priorite]||'bdg-gray'}">${PRIO_LABEL[m.priorite]||m.priorite}</span></td>
      <td>${esc(m.assigne_nom||'—')}</td>
      <td>${fmtDate(m.date_signalement)}</td>
      <td><span class="badge ${MSTATUT_BADGE[m.statut]||'bdg-gray'}">${MSTATUT_LABEL[m.statut]||m.statut}</span></td>
      <td><div class="td-actions">
        <button class="btn btn-outline btn-xs" onclick="modalMaintenance('${escJs(m.id)}')">✏️</button>
        <button class="btn btn-danger btn-xs" onclick="delMaintenance('${escJs(m.id)}')">🗑</button>
      </div></td>
    </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('🔧','Aucune intervention')}</td></tr>`;
    $('#pag-maint').innerHTML = paginationHtml('log-maint', page, totalPages, total);
  };
  $('#log-body').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">🔧 Maintenance des locaux & équipements (${interventions.length})</span>
      <button class="btn btn-primary btn-sm" onclick="modalMaintenance()">+ Signaler un problème</button>
    </div>
    <div class="filters">
      <div class="fg"><label>Statut</label><select id="f-maintstatut"><option value="">Tous</option>${Object.entries(MSTATUT_LABEL).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Problème</th><th>Lieu</th><th>Priorité</th><th>Assigné à</th><th>Signalé le</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody id="tb-maint"></tbody>
    </table></div>
    <div id="pag-maint"></div>
  </div>`;
  getPaginator('log-maint').onChange = () => render(curr);
  render(curr);
  $('#f-maintstatut').addEventListener('change', async () => {
    const s = $('#f-maintstatut').value;
    curr = await apiGetMaintenance(s?`statut=${s}`:'');
    resetPaginator('log-maint');
    render(curr);
  });
}

async function modalMaintenance(id = null) {
  let data = {};
  if (id) { const all = await apiGetMaintenance(); data = all.find(m=>m.id===id)||{}; }
  openModal(id?'Modifier l\'intervention':'Signaler un problème', `
    <form id="f-maint" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Titre*</label><input name="titre" value="${esc(data.titre||'')}" required placeholder="Ex : Fuite d'eau, climatiseur en panne…"></div>
      <div class="form-2">
        <div class="fg"><label>Salle concernée</label><select name="salle_id"><option value="">— Aucune —</option>${_logSalles.map(s=>`<option value="${esc(s.id)}" ${data.salle_id===s.id?'selected':''}>${esc(s.nom)}</option>`).join('')}</select></div>
        <div class="fg"><label>Lieu (texte libre)</label><input name="lieu" value="${esc(data.lieu||'')}" placeholder="Cour, bloc administratif…"></div>
      </div>
      <div class="fg"><label>Équipement concerné</label><input name="equipement" value="${esc(data.equipement||'')}" placeholder="Climatiseur, robinet, portail…"></div>
      <div class="fg"><label>Description</label><textarea name="description" rows="2">${esc(data.description||'')}</textarea></div>
      <div class="form-2">
        <div class="fg"><label>Priorité</label><select name="priorite">${Object.entries(PRIO_LABEL).map(([k,v])=>`<option value="${k}" ${(data.priorite||'normale')===k?'selected':''}>${v}</option>`).join('')}</select></div>
        <div class="fg"><label>Assigné à (personnel)</label><select name="assigne_a"><option value="">— Non assigné —</option>${_logPersonnel.map(p=>`<option value="${esc(p.id)}" ${data.assigne_a===p.id?'selected':''}>${esc(p.prenom)} ${esc(p.nom)}</option>`).join('')}</select></div>
      </div>
      ${id ? `<div class="form-2">
        <div class="fg"><label>Statut</label><select name="statut">${Object.entries(MSTATUT_LABEL).map(([k,v])=>`<option value="${k}" ${data.statut===k?'selected':''}>${v}</option>`).join('')}</select></div>
        <div class="fg"><label>Coût (GNF)</label><input type="number" name="cout" value="${data.cout??0}" min="0"></div>
      </div>` : ''}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Signaler'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-maint').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (fd.cout !== undefined) fd.cout = parseFloat(fd.cout)||0;
    try {
      if (id) await apiUpdateMaintenance(id, fd); else await apiCreateMaintenance(fd);
      toast(id?'Modifiée':'Problème signalé','success'); closeModal(); renderLogMaintenance();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delMaintenance(id) {
  if (!confirmDel('Supprimer cette intervention ?')) return;
  try { await apiDeleteMaintenance(id); toast('Supprimée','success'); renderLogMaintenance(); }
  catch(e) { toast(e.message,'error'); }
}

/* ───────────── TRANSPORT ───────────── */
async function renderLogTransport() {
  const [vehicules, itineraires] = await Promise.all([apiGetVehicules(), apiGetItineraires()]);
  _logVehicules = vehicules;
  $('#log-body').innerHTML = `
  <div class="card mb-4">
    <div class="card-header">
      <span class="card-title">🚐 Véhicules (${vehicules.length})</span>
      <button class="btn btn-primary btn-sm" onclick="modalVehicule()">+ Véhicule</button>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Immatriculation</th><th>Modèle</th><th>Capacité</th><th>Chauffeur</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody>${vehicules.length ? vehicules.map(v=>`<tr>
        <td><strong>${esc(v.immatriculation)}</strong></td>
        <td>${esc(v.marque_modele||'—')}</td>
        <td>${v.capacite||'—'} places</td>
        <td>${esc(v.chauffeur_nom||'—')}</td>
        <td><span class="badge ${v.statut==='actif'?'bdg-ok':v.statut==='maintenance'?'bdg-warn':'bdg-err'}">${v.statut==='actif'?'Actif':v.statut==='maintenance'?'En maintenance':'Hors service'}</span></td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalVehicule('${escJs(v.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delVehicule('${escJs(v.id)}')">🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="6">${emptyHtml('🚐','Aucun véhicule')}</td></tr>`}</tbody>
    </table></div>
  </div>
  <div class="card">
    <div class="card-header">
      <span class="card-title">🗺️ Itinéraires (${itineraires.length})</span>
      <button class="btn btn-primary btn-sm" onclick="modalItineraire()">+ Itinéraire</button>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Nom</th><th>Zone</th><th>Véhicule</th><th>Élèves</th><th>Actions</th></tr></thead>
      <tbody>${itineraires.length ? itineraires.map(it=>`<tr>
        <td><strong>${esc(it.nom)}</strong></td>
        <td>${esc(it.zone||'—')}</td>
        <td>${esc(it.vehicule_immat||'—')}</td>
        <td>${it.nb_eleves} élève(s)</td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalEleveTransport('${escJs(it.id)}','${escJs(it.nom)}')">🎓 Élèves</button>
          <button class="btn btn-outline btn-xs" onclick="modalItineraire('${escJs(it.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delItineraire('${escJs(it.id)}')">🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('🗺️','Aucun itinéraire')}</td></tr>`}</tbody>
    </table></div>
  </div>`;
}

function modalVehicule(id = null) {
  const data = id ? _logVehicules.find(v=>v.id===id) || {} : {};
  openModal(id?'Modifier le véhicule':'Ajouter un véhicule', `
    <form id="f-veh" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Immatriculation*</label><input name="immatriculation" value="${esc(data.immatriculation||'')}" required placeholder="RC-1234-AB"></div>
      <div class="form-2">
        <div class="fg"><label>Marque / Modèle</label><input name="marque_modele" value="${esc(data.marque_modele||'')}" placeholder="Toyota Coaster"></div>
        <div class="fg"><label>Capacité (places)</label><input type="number" name="capacite" value="${data.capacite??''}" min="0"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Chauffeur</label><select name="chauffeur_id"><option value="">— Aucun —</option>${_logPersonnel.map(p=>`<option value="${esc(p.id)}" ${data.chauffeur_id===p.id?'selected':''}>${esc(p.prenom)} ${esc(p.nom)}</option>`).join('')}</select></div>
        <div class="fg"><label>Statut</label><select name="statut">
          <option value="actif" ${(data.statut||'actif')==='actif'?'selected':''}>Actif</option>
          <option value="maintenance" ${data.statut==='maintenance'?'selected':''}>En maintenance</option>
          <option value="hors_service" ${data.statut==='hors_service'?'selected':''}>Hors service</option>
        </select></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-veh').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (fd.capacite) fd.capacite = parseInt(fd.capacite); else delete fd.capacite;
    try {
      if (id) await apiUpdateVehicule(id, fd); else await apiCreateVehicule(fd);
      toast(id?'Modifié':'Ajouté','success'); closeModal(); renderLogTransport();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delVehicule(id) {
  if (!confirmDel('Supprimer ce véhicule ?')) return;
  try { await apiDeleteVehicule(id); toast('Supprimé','success'); renderLogTransport(); }
  catch(e) { toast(e.message,'error'); }
}

async function modalItineraire(id = null) {
  let data = {};
  if (id) { const all = await apiGetItineraires(); data = all.find(i=>i.id===id)||{}; }
  openModal(id?'Modifier l\'itinéraire':'Ajouter un itinéraire', `
    <form id="f-itin" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Nom*</label><input name="nom" value="${esc(data.nom||'')}" required placeholder="Ex : Circuit Ratoma-Centre"></div>
      <div class="form-2">
        <div class="fg"><label>Zone / Quartier</label><input name="zone" value="${esc(data.zone||'')}" placeholder="Ratoma, Yattaya…"></div>
        <div class="fg"><label>Véhicule</label><select name="vehicule_id"><option value="">— Aucun —</option>${_logVehicules.map(v=>`<option value="${esc(v.id)}" ${data.vehicule_id===v.id?'selected':''}>${esc(v.immatriculation)}</option>`).join('')}</select></div>
      </div>
      <div class="fg"><label>Description</label><textarea name="description" rows="2">${esc(data.description||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-itin').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      if (id) await apiUpdateItineraire(id, fd); else await apiCreateItineraire(fd);
      toast(id?'Modifié':'Ajouté','success'); closeModal(); renderLogTransport();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delItineraire(id) {
  if (!confirmDel('Supprimer cet itinéraire ?')) return;
  try { await apiDeleteItineraire(id); toast('Supprimé','success'); renderLogTransport(); }
  catch(e) { toast(e.message,'error'); }
}

async function modalEleveTransport(itineraireId, nomItineraire) {
  const affectations = await apiGetTransportEleves(`itineraire_id=${itineraireId}`);
  const elevesDejaAffectes = new Set(affectations.map(a=>a.eleve_id));
  const dispo = _logEleves.filter(e=>e.statut==='actif' && !elevesDejaAffectes.has(e.id));
  openModal(`Élèves — ${esc(nomItineraire)}`, `
    <form id="f-affect" style="display:flex;gap:10px;align-items:flex-end;margin-bottom:16px;flex-wrap:wrap">
      <div class="fg grow"><label>Ajouter un élève</label>
        <select name="eleve_id" required>
          <option value="">— Choisir —</option>
          ${dispo.map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Point de montée</label><input name="point_montee" placeholder="Marché, carrefour…"></div>
      <button type="submit" class="btn btn-primary">+ Affecter</button>
    </form>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Élève</th><th>Classe</th><th>Point de montée</th><th>Actions</th></tr></thead>
      <tbody id="tb-affect">${affectations.length ? affectations.map(a=>`<tr>
        <td>${esc(a.eleve_prenom)} ${esc(a.eleve_nom)}</td>
        <td>${esc(a.eleve_classe||'—')}</td>
        <td>${esc(a.point_montee||'—')}</td>
        <td><button class="btn btn-danger btn-xs" onclick="retirerEleveTransport('${escJs(a.id)}','${escJs(itineraireId)}','${escJs(nomItineraire)}')">🗑</button></td>
      </tr>`).join('') : `<tr><td colspan="4">${emptyHtml('🎓','Aucun élève affecté')}</td></tr>`}</tbody>
    </table></div>`, { wide: true });
  $('#f-affect').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.itineraire_id = itineraireId;
    try { await apiAssignTransportEleve(fd); toast('Élève affecté','success'); closeModal(); renderLogTransport(); modalEleveTransport(itineraireId, nomItineraire); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function retirerEleveTransport(affectationId, itineraireId, nomItineraire) {
  if (!confirmDel('Retirer cet élève de l\'itinéraire ?')) return;
  try { await apiUnassignTransportEleve(affectationId); toast('Retiré','success'); closeModal(); renderLogTransport(); modalEleveTransport(itineraireId, nomItineraire); }
  catch(e) { toast(e.message,'error'); }
}

window.modalStockProduit = modalStockProduit;
window.delStockProduit = delStockProduit;
window.modalMouvementStock = modalMouvementStock;
window.modalCommande = modalCommande;
window.modalDetailCommande = modalDetailCommande;
window.receptionnerCmd = receptionnerCmd;
window.delCommande = delCommande;
window.modalMaintenance = modalMaintenance;
window.delMaintenance = delMaintenance;
window.modalVehicule = modalVehicule;
window.delVehicule = delVehicule;
window.modalItineraire = modalItineraire;
window.delItineraire = delItineraire;
window.modalEleveTransport = modalEleveTransport;
window.retirerEleveTransport = retirerEleveTransport;
