/* ===================== CANTINE ===================== */
let _cantineEleves = [];
async function pageCantine() {
  $('#content').innerHTML = loadingHtml;
  const [abons, menus, eleves] = await Promise.all([apiGetAbons(), apiGetMenus(), apiGetEleves()]);
  _cantineEleves = eleves;
  const classes = [...new Set(eleves.map(e=>e.classe).filter(Boolean))].sort();
  const moisDispos = [...new Set(abons.map(a=>a.mois))].sort().reverse();

  let activeTab = 'abonnements';
  const renderContent = () => {
    if (activeTab === 'abonnements') renderAbons(abons, eleves, classes);
    else renderMenus(menus);
  };

  $('#content').innerHTML = `
  <div class="tabs" id="cantine-tabs">
    <div class="tab active" onclick="setCantineTab('abonnements')">🍽️ Abonnements</div>
    <div class="tab" onclick="setCantineTab('menus')">📋 Menus</div>
  </div>
  <div id="cantine-body"></div>`;

  window.setCantineTab = (tab) => {
    activeTab = tab;
    $$('#cantine-tabs .tab').forEach((t,i) => t.classList.toggle('active', i===(tab==='abonnements'?0:1)));
    renderContent();
  };
  renderContent();
}

async function renderAbons(abons, eleves, classes) {
  const mois = moisCourant();
  const filtMois = abons.filter(a => a.mois === mois);
  const total = filtMois.reduce((s,a)=>s+a.montant,0);
  const payes = filtMois.filter(a=>a.paye).reduce((s,a)=>s+a.montant,0);
  let curr = filtMois;

  const render = data => {
    $('#tb-abons').innerHTML = data.length ? data.map(a => `<tr>
      <td><strong>${esc(a.prenom)} ${esc(a.nom)}</strong></td>
      <td><span class="badge bdg-primary">${esc(a.classe||'—')}</span></td>
      <td>${esc(a.mois)}</td>
      <td>${esc(a.formule||'—')}</td>
      <td class="mono text-right">${fmtMoney(a.montant)}</td>
      <td><span class="badge ${a.paye?'bdg-ok':'bdg-err'}">${a.paye?'Payé':'Impayé'}</span></td>
      <td><div class="td-actions">
        ${!a.paye?`<button class="btn btn-ok btn-xs" onclick="payerAbon('${escJs(a.id)}','${escJs(a.prenom)} ${escJs(a.nom)}',${a.montant},'${escJs(a.mois)}')">💰 Payer</button>`:''}
        <button class="btn btn-danger btn-xs" onclick="delAbon('${escJs(a.id)}')">🗑</button>
      </div></td>
    </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('🍽️','Aucun abonnement pour ce mois')}</td></tr>`;
  };

  $('#cantine-body').innerHTML = `
  <div class="stats-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
    <div class="stat"><div class="stat-label">Abonnés ce mois</div><div class="stat-val">${filtMois.length}</div></div>
    <div class="stat"><div class="stat-label">Total attendu</div><div class="stat-val" style="font-size:16px">${fmtMoney(total)}</div></div>
    <div class="stat"><div class="stat-label">Payé</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(payes)}</div></div>
    <div class="stat"><div class="stat-label">Impayé</div><div class="stat-val text-err" style="font-size:16px">${fmtMoney(total-payes)}</div></div>
  </div>
  <div class="card">
    <div class="card-header">
      <span class="card-title">🍽️ Abonnements cantine</span>
      <button class="btn btn-primary btn-sm" onclick="modalAbon()">+ Abonnement</button>
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-abons" placeholder="Nom, prénom…"></div>
      <div class="fg"><label>Mois</label><input type="month" id="f-mois" value="${mois}"></div>
      <div class="fg"><label>Classe</label><select id="f-ccls"><option value="">Toutes</option>${classes.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
      <div class="fg"><label>Statut</label><select id="f-cpaye"><option value="">Tous</option><option value="1">Payé</option><option value="0">Impayé</option></select></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr id="th-abons"><th>Élève</th><th>Classe</th><th>Mois</th><th>Formule</th><th class="text-right">Montant</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody id="tb-abons"></tbody>
    </table></div>
  </div>`;
  render(curr);
  const filter = async () => {
    const m = $('#f-mois').value;
    const cls = $('#f-ccls').value;
    const p = $('#f-cpaye').value;
    const q = $('#q-abons').value.toLowerCase();
    let qs = [];
    if (m) qs.push(`mois=${m}`);
    if (cls) qs.push(`classe=${encodeURIComponent(cls)}`);
    if (p !== '') qs.push(`paye=${p}`);
    try {
      let data = await apiGetAbons(qs.join('&'));
      if (q) data = data.filter(a => `${a.nom} ${a.prenom}`.toLowerCase().includes(q));
      curr = data;
      render(curr);
    }
    catch(e) { toast(e.message,'error'); }
  };
  $('#q-abons').addEventListener('input', filter);
  ['#f-mois','#f-ccls','#f-cpaye'].forEach(s => $(s).addEventListener('change', filter));
  makeSortableTable('#th-abons', () => curr, render,
    [row => `${row.prenom} ${row.nom}`, 'classe', 'mois', 'formule', 'montant', 'paye', null]);
}

function modalAbon() {
  const eleves = _cantineEleves;
  openModal('Nouvel abonnement cantine', `
    <form id="f-abon" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Élève*</label>
        <select name="eleve_id" required>
          <option value="">— Choisir —</option>
          ${eleves.filter(e=>e.statut==='actif').map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} (${esc(e.classe||'?')})</option>`).join('')}
        </select>
      </div>
      <div class="form-3">
        <div class="fg"><label>Mois*</label><input type="month" name="mois" value="${moisCourant()}" required></div>
        <div class="fg"><label>Formule</label><select name="formule">
          <option>complète</option><option>déjeuner</option><option>goûter</option>
        </select></div>
        <div class="fg"><label>Montant (GNF)</label><input type="number" name="montant" value="15000" min="0" step="1"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-abon').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant)||0;
    try { await apiCreateAbon(fd); toast('Abonnement créé','success'); closeModal(); pageCantine(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function payerAbon(id, nom, montant, mois) {
  const moyen = prompt('Moyen de paiement :', 'Espèces');
  if (!moyen) return;
  try {
    await apiPayerAbon(id, { moyen_paiement: moyen });
    toast('Paiement enregistré','success'); pageCantine();
    imprimerRecu({
      type: 'entree', nom: nom || 'Élève', description: `Cantine — ${mois||''}`, montant: montant||0,
      date: today(), moyenPaiement: moyen, recuPar: currentUser?.full_name,
    });
  }
  catch(e) { toast(e.message,'error'); }
}

async function delAbon(id) {
  if (!confirmDel()) return;
  try { await apiDeleteAbon(id); toast('Supprimé','success'); pageCantine(); }
  catch(e) { toast(e.message,'error'); }
}

function renderMenus(menus) {
  let curr = menus;
  const render = data => {
    $('#tb-menus').innerHTML = data.length ? data.map(m => `<tr>
      <td>${fmtDateLong(m.date_menu)}</td>
      <td>${esc(m.entree||'—')}</td>
      <td>${esc(m.plat||'—')}</td>
      <td>${esc(m.dessert||'—')}</td>
      <td><div class="td-actions">
        <button class="btn btn-outline btn-xs" onclick="modalMenu('${escJs(m.id)}')">✏️</button>
        <button class="btn btn-danger btn-xs" onclick="delMenu('${escJs(m.id)}')">🗑</button>
      </div></td>
    </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('📋','Aucun menu enregistré')}</td></tr>`;
  };

  $('#cantine-body').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">📋 Menus de la cantine</span>
      <button class="btn btn-primary btn-sm" onclick="modalMenu()">+ Ajouter un menu</button>
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-menus" placeholder="Plat, entrée, dessert…"></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr id="th-menus"><th>Date</th><th>Entrée</th><th>Plat principal</th><th>Dessert</th><th>Actions</th></tr></thead>
      <tbody id="tb-menus"></tbody>
    </table></div>
  </div>`;
  render(curr);
  $('#q-menus').addEventListener('input', () => {
    const q = $('#q-menus').value.toLowerCase();
    curr = menus.filter(m => `${m.entree||''} ${m.plat||''} ${m.dessert||''}`.toLowerCase().includes(q));
    render(curr);
  });
  makeSortableTable('#th-menus', () => curr, render, ['date_menu', 'entree', 'plat', 'dessert', null]);
}

async function modalMenu(id = null) {
  let data = {};
  if (id) { const menus = await apiGetMenus(); data = menus.find(m=>m.id===id)||{}; }
  openModal(id?'Modifier le menu':'Nouveau menu', `
    <form id="f-menu" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Date*</label><input type="date" name="date_menu" value="${esc(data.date_menu||today())}" required></div>
      <div class="fg"><label>Entrée</label><input name="entree" value="${esc(data.entree||'')}" placeholder="Salade composée…"></div>
      <div class="fg"><label>Plat principal</label><input name="plat" value="${esc(data.plat||'')}" placeholder="Riz sauce arachide, poulet braisé…"></div>
      <div class="fg"><label>Dessert</label><input name="dessert" value="${esc(data.dessert||'')}" placeholder="Fruit de saison…"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Créer'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-menu').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      if (id) await apiUpdateMenu(id, fd); else await apiCreateMenu(fd);
      toast(id?'Menu modifié':'Menu créé','success'); closeModal(); pageCantine();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delMenu(id) {
  if (!confirmDel()) return;
  try { await apiDeleteMenu(id); toast('Supprimé','success'); pageCantine(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalAbon = modalAbon;
window.payerAbon = payerAbon;
window.delAbon = delAbon;
window.modalMenu = modalMenu;
window.delMenu = delMenu;
