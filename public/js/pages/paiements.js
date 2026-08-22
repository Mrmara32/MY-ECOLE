/* ===================== PAIEMENTS ===================== */
let _paiEleves = [];
async function pagePaiements() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [paiements, eleves] = await Promise.all([apiGetPaiements(), apiGetEleves()]);
    _paiEleves = eleves;
    const classes = [...new Set(eleves.map(e=>e.classe).filter(Boolean))].sort();

    const render = data => {
      const total_du   = data.reduce((s,p)=>s+p.montant_du,0);
      const total_paye = data.reduce((s,p)=>s+p.montant_paye,0);
      const reste      = total_du - total_paye;
      $('#pai-summary').innerHTML = `
        <div class="stats-grid" style="grid-template-columns:repeat(3,1fr)">
          <div class="stat"><div class="stat-label">Total dû</div><div class="stat-val" style="font-size:16px">${fmtMoney(total_du)}</div></div>
          <div class="stat"><div class="stat-label">Perçu</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(total_paye)}</div></div>
          <div class="stat"><div class="stat-label">Reste impayé</div><div class="stat-val text-err" style="font-size:16px">${fmtMoney(reste)}</div></div>
        </div>`;
      const SCOLOR = { paye:'bdg-ok', partiel:'bdg-warn', a_payer:'bdg-err', en_retard:'bdg-err' };
      const SLABEL = { paye:'Payé', partiel:'Partiel', a_payer:'À payer', en_retard:'En retard' };
      $('#tb-pai').innerHTML = data.length ? data.map(p => {
        const pct = p.montant_du > 0 ? Math.round(p.montant_paye/p.montant_du*100) : 0;
        return `<tr>
          <td>${elevePhoto({photo_url:null,nom:p.nom,prenom:p.prenom},28)}</td>
          <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(p.matricule||'')} · ${esc(p.classe||'')}</span></td>
          <td>${esc(p.libelle||p.type_frais||'—')}</td>
          <td class="mono text-right">${fmtMoney(p.montant_du)}</td>
          <td>
            <div class="progress mb-2" style="width:80px"><div class="progress-bar ${pct>=100?'':'warn'}" style="width:${pct}%"></div></div>
            <span class="text-muted" style="font-size:11px">${fmtMoney(p.montant_paye)} (${pct}%)</span>
          </td>
          <td class="mono text-right text-err">${fmtMoney(p.montant_du-p.montant_paye)}</td>
          <td>${fmtDate(p.date_echeance)}</td>
          <td><span class="badge ${SCOLOR[p.statut]||'bdg-gray'}">${SLABEL[p.statut]||p.statut}</span></td>
          <td><div class="td-actions">
            ${p.statut!=='paye' && ['admin','comptable'].includes(currentUser.role)?`<button class="btn btn-ok btn-xs" onclick="modalVerser('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}',${p.montant_du-p.montant_paye},'${escJs(p.libelle||'Scolarité')}')">💰 Payer</button>`:''}
            ${currentUser.role==='admin'?`<button class="btn btn-danger btn-xs" onclick="delPaiement('${escJs(p.id)}')">🗑</button>`:''}
          </div></td>
        </tr>`;
      }).join('') : `<tr><td colspan="9">${emptyHtml('💰','Aucun paiement')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div id="pai-summary" class="mb-4"></div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">💰 Paiements & Frais de scolarité</span>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="modalGenPaiements()">⚡ Générer échéances</button>
          <button class="btn btn-primary btn-sm" onclick="modalBaremes()">⚙ Barèmes</button>
        </div>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-pai" placeholder="Nom, prénom, matricule…"></div>
        <div class="fg"><label>Classe</label><select id="f-pcls"><option value="">Toutes</option>${classes.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
        <div class="fg"><label>Statut</label><select id="f-pstat">
          <option value="">Tous</option><option value="a_payer">À payer</option>
          <option value="partiel">Partiel</option><option value="paye">Payé</option>
        </select></div>
        <div class="fg"><label>Année</label><input id="f-pann" value="${anneeCourante()}" placeholder="${anneeCourante()}"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-pai"><th></th><th>Élève</th><th>Libellé</th><th class="text-right">Montant dû</th><th>Progression</th><th class="text-right">Reste</th><th>Échéance</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-pai"></tbody>
      </table></div>
    </div>`;

    let curr = paiements;
    render(curr);
    const refilter = async () => {
      const cls = $('#f-pcls').value;
      const stat = $('#f-pstat').value;
      const ann = $('#f-pann').value;
      const q = $('#q-pai').value.toLowerCase();
      let qs = [];
      if (cls) qs.push(`classe=${encodeURIComponent(cls)}`);
      if (stat) qs.push(`statut=${stat}`);
      if (ann) qs.push(`annee_scolaire=${ann}`);
      try {
        let data = await apiGetPaiements(qs.join('&'));
        if (q) data = data.filter(p => `${p.nom} ${p.prenom} ${p.matricule||''}`.toLowerCase().includes(q));
        curr = data;
        render(curr);
      } catch(e) { toast(e.message,'error'); }
    };
    ['#f-pcls','#f-pstat'].forEach(s => $(s).addEventListener('change', refilter));
    $('#f-pann').addEventListener('blur', refilter);
    $('#q-pai').addEventListener('input', refilter);

    makeSortableTable('#th-pai', () => curr, render,
      [null, row => `${row.prenom} ${row.nom}`, 'libelle', 'montant_du', null, row => row.montant_du - row.montant_paye, 'date_echeance', 'statut', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function modalVerser(paiementId, eleveName, reste, libelle = 'Scolarité') {
  reste = Math.max(0, Math.round(reste));
  openModal(`Enregistrer un paiement — ${eleveName}`, `
    <form id="f-vers" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">Reste à payer : <strong>${fmtMoney(reste)}</strong></div>
      <div class="fg"><label>Montant versé (GNF)*</label>
        <input type="number" name="montant" required min="1" step="1" value="${reste || ''}" placeholder="${reste || 'Montant'}">
      </div>
      <div class="form-2">
        <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
        <div class="fg"><label>Date</label><input type="date" name="date_vers" value="${today()}"></div>
      </div>
      <div class="fg"><label>Référence / N° reçu</label><input name="reference" placeholder="REC-001…"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-ok">✅ Valider le paiement</button>
      </div>
    </form>`, { narrow: true });
  $('#f-vers').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant);
    try {
      await apiVerserPaiement(paiementId, fd);
      toast('Paiement enregistré ✅','success'); closeModal(); pagePaiements();
      imprimerRecu({
        type: 'entree', nom: eleveName, description: libelle, montant: fd.montant,
        date: fd.date_vers || today(), moyenPaiement: fd.moyen_paiement, reference: fd.reference,
        recuPar: currentUser?.full_name,
      });
    }
    catch(err) { toast(err.message,'error'); }
  };
}

async function modalGenPaiements() {
  const eleves = _paiEleves;
  openModal('Générer les échéances de scolarité', `
    <form id="f-gen" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">Génère automatiquement les frais d'inscription et les tranches de scolarité selon le barème de la classe.</div>
      <div class="fg"><label>Élève*</label>
        <select name="eleve_id" required>
          <option value="">— Choisir —</option>
          ${eleves.filter(e=>e.statut==='actif').map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')}</option>`).join('')}
        </select>
      </div>
      <div class="form-2">
        <div class="fg"><label>Année scolaire*</label><input name="annee_scolaire" value="${anneeCourante()}" required></div>
        <div class="fg"><label>Date de début</label><input type="date" name="date_debut" value="${today()}"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">⚡ Générer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-gen').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { const r = await apiGenPaiements(fd); toast(`${r.count} échéances générées`,'success'); closeModal(); pagePaiements(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function modalBaremes() {
  const frais = await apiGetFrais().catch(()=>[]);
  openModal('⚙ Barèmes des frais de scolarité', `
    <div class="mb-3 flex" style="justify-content:flex-end">
      <button class="btn btn-primary btn-sm" onclick="modalAddBareme()">+ Ajouter un barème</button>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Classe</th><th>Année</th><th class="text-right">Inscription</th><th class="text-right">Scolarité</th><th>Tranches</th><th>Actions</th></tr></thead>
      <tbody>
      ${frais.length ? frais.map(f=>`<tr>
        <td><span class="badge bdg-primary">${esc(f.classe)}</span></td>
        <td>${esc(f.annee_scolaire)}</td>
        <td class="mono text-right">${fmtMoney(f.frais_inscription)}</td>
        <td class="mono text-right">${fmtMoney(f.scolarite_annuelle)}</td>
        <td class="text-center"><span class="badge bdg-primary">45% / 40% / 15%</span></td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalEditBareme('${escJs(f.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delBareme('${escJs(f.id)}')" ${currentUser.role!=='admin'?'style="display:none"':''}>🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="6">${emptyHtml('⚙','Aucun barème défini')}</td></tr>`}
      </tbody>
    </table></div>`, { wide: true });
}

async function modalAddBareme() {
  openModal('Ajouter un barème', `
    <form id="f-bar" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Classe*</label><select name="classe" required>${optionsHtml(CLASSES)}</select></div>
        <div class="fg"><label>Année scolaire*</label><input name="annee_scolaire" value="${anneeCourante()}" required></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Frais d'inscription (GNF)</label><input type="number" name="frais_inscription" value="0"></div>
        <div class="fg"><label>Scolarité annuelle (GNF)</label><input type="number" name="scolarite_annuelle" value="0"></div>
      </div>
      <div class="alert alert-info">💡 La scolarité annuelle est automatiquement répartie en 3 tranches : <strong>45%</strong>, <strong>40%</strong> puis <strong>15%</strong>.</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="modalBaremes()">Retour</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);
  $('#f-bar').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.frais_inscription = parseFloat(fd.frais_inscription)||0;
    fd.scolarite_annuelle = parseFloat(fd.scolarite_annuelle)||0;
    try { await apiCreateFrais(fd); toast('Barème ajouté','success'); modalBaremes(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function modalEditBareme(id) {
  const frais = await apiGetFrais();
  const f = frais.find(x=>x.id===id);
  if (!f) return;
  openModal('Modifier le barème', `
    <form id="f-ebar" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">Classe : <strong>${esc(f.classe)}</strong> — Année : <strong>${esc(f.annee_scolaire)}</strong></div>
      <div class="form-2">
        <div class="fg"><label>Frais d'inscription (GNF)</label><input type="number" name="frais_inscription" value="${f.frais_inscription||0}"></div>
        <div class="fg"><label>Scolarité annuelle (GNF)</label><input type="number" name="scolarite_annuelle" value="${f.scolarite_annuelle||0}"></div>
      </div>
      <div class="alert alert-info">💡 Répartition fixe : <strong>45%</strong> / <strong>40%</strong> / <strong>15%</strong> sur 3 tranches.</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="modalBaremes()">Retour</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);
  $('#f-ebar').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.frais_inscription = parseFloat(fd.frais_inscription)||0;
    fd.scolarite_annuelle = parseFloat(fd.scolarite_annuelle)||0;
    try { await apiUpdateFrais(id, fd); toast('Barème mis à jour','success'); modalBaremes(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function delBareme(id) {
  if (!confirmDel()) return;
  try { await apiDeleteFrais(id); toast('Supprimé','success'); modalBaremes(); }
  catch(e) { toast(e.message,'error'); }
}

async function delPaiement(id) {
  if (!confirmDel('Supprimer cette ligne de paiement ?')) return;
  try { await apiDeletePaiement(id); toast('Supprimé','success'); pagePaiements(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalVerser = modalVerser;
window.modalGenPaiements = modalGenPaiements;
window.modalBaremes = modalBaremes;
window.modalAddBareme = modalAddBareme;
window.modalEditBareme = modalEditBareme;
window.delBareme = delBareme;
window.delPaiement = delPaiement;
