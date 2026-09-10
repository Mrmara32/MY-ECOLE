/* ===================== RÉINSCRIPTIONS ===================== */
let _reinscEleves = [];
let _reinscListe = [];
async function pageReinscriptions() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [reinscriptions, eleves] = await Promise.all([apiGetReinscriptions(), apiGetEleves()]);
    _reinscEleves = eleves;
    _reinscListe = reinscriptions;
    const en_attente = reinscriptions.filter(r=>r.statut==='en_attente').length;
    let curr = reinscriptions;

    const RCOLOR = { en_attente:'bdg-warn', validee:'bdg-ok', refusee:'bdg-err' };
    const RLABEL = { en_attente:'En attente', validee:'Validée', refusee:'Refusée' };

    const render = data => {
      const { items, page, totalPages, total } = paginate('reinsc', data);
      $('#tb-reinsc').innerHTML = items.length ? items.map(r => `<tr>
        <td><strong>${esc(r.prenom)} ${esc(r.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(r.matricule||'')}</span></td>
        <td><span class="badge bdg-gray">${esc(r.classe_precedente||'—')}</span></td>
        <td><span class="badge bdg-primary">${esc(r.classe_nouvelle||'—')}</span></td>
        <td>${esc(r.annee_scolaire)}</td>
        <td>${fmtDate(r.date_demande)}</td>
        <td><span class="badge ${RCOLOR[r.statut]||'bdg-gray'}">${RLABEL[r.statut]||r.statut}</span></td>
        <td class="text-muted" style="font-size:11px">${esc(r.validee_par_nom||'—')}</td>
        <td><div class="td-actions">
          ${r.statut==='en_attente'?`
            <button class="btn btn-ok btn-xs" onclick="validerReinsc('${escJs(r.id)}','validee')">✔ Valider</button>
            <button class="btn btn-danger btn-xs" onclick="validerReinsc('${escJs(r.id)}','refusee')">✕ Refuser</button>`
          : `<button class="btn btn-outline btn-xs" onclick="validerReinsc('${escJs(r.id)}','en_attente')">↩ Réinitialiser</button>`}
          <button class="btn btn-danger btn-xs" onclick="delReinsc('${escJs(r.id)}')">🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('🔄','Aucune réinscription')}</td></tr>`;
      $('#pag-reinsc').innerHTML = paginationHtml('reinsc', page, totalPages, total);
    };

    $('#content').innerHTML = `
    ${en_attente > 0 ? `<div class="alert alert-warn mb-4">⚠️ <strong>${en_attente}</strong> réinscription${en_attente>1?'s':''} en attente de validation</div>` : ''}
    <div class="card">
      <div class="card-header">
        <span class="card-title">🔄 Réinscriptions (${reinscriptions.length})</span>
        <button class="btn btn-primary btn-sm" onclick="modalReinscription()">+ Nouvelle demande</button>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-reinsc" placeholder="Nom, prénom, matricule…"></div>
        <div class="fg"><label>Année scolaire</label><input id="f-rann" placeholder="${anneeCourante()}"></div>
        <div class="fg"><label>Statut</label><select id="f-rstat">
          <option value="">Tous</option><option value="en_attente">En attente</option>
          <option value="validee">Validée</option><option value="refusee">Refusée</option>
        </select></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-reinsc"><th>Élève</th><th>Classe précédente</th><th>Nouvelle classe</th><th>Année</th><th>Demandé le</th><th>Statut</th><th>Validé par</th><th>Actions</th></tr></thead>
        <tbody id="tb-reinsc"></tbody>
      </table></div>
      <div id="pag-reinsc"></div>
    </div>`;

    getPaginator('reinsc').onChange = () => render(curr);
    render(curr);
    const refilter = async () => {
      const ann = $('#f-rann').value;
      const stat = $('#f-rstat').value;
      const q = $('#q-reinsc').value.toLowerCase();
      let qs = [];
      if (ann) qs.push(`annee_scolaire=${ann}`);
      if (stat) qs.push(`statut=${stat}`);
      try {
        let data = await apiGetReinscriptions(qs.join('&'));
        if (q) data = data.filter(r => `${r.nom} ${r.prenom} ${r.matricule||''}`.toLowerCase().includes(q));
        curr = data;
        _reinscListe = data;
        resetPaginator('reinsc');
        render(curr);
      }
      catch(e) { toast(e.message,'error'); }
    };
    $('#q-reinsc').addEventListener('input', refilter);
    makeSortableTable('#th-reinsc', () => curr, render,
      [row => `${row.prenom} ${row.nom}`, 'classe_precedente', 'classe_nouvelle', 'annee_scolaire', 'date_demande', 'statut', 'validee_par_nom', null]);
    ['#f-rann','#f-rstat'].forEach(s => $(s).addEventListener('change', refilter));
    $('#f-rann').addEventListener('blur', refilter);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function modalReinscription() {
  const eleves = _reinscEleves;
  const STATUT_LABEL = { actif:'Actif', inactif:'Ancien élève', exclu:'Exclu', transfere:'Transféré', reinsrit:'Réinscrit' };
  const sorted = [...eleves].sort((a,b) => (a.statut==='actif'?0:1) - (b.statut==='actif'?0:1));
  openModal('Demande de réinscription', `
    <form id="f-reinsc" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Élève*</label>
        <select name="eleve_id" required id="reinsc-eleve-sel">
          <option value="">— Choisir un élève —</option>
          ${sorted.map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} — ${e.statut==='actif'?`Actuellement en ${esc(e.classe||'?')}`:`${STATUT_LABEL[e.statut]||e.statut} (dernière classe : ${esc(e.classe||'?')})`}</option>`).join('')}
        </select>
        <div class="text-muted mt-2" style="font-size:12px">💡 Les anciens élèves (inactifs, transférés) apparaissent aussi dans cette liste — les réinscrire les remettra automatiquement au statut "actif".</div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Nouvelle classe*</label><select name="classe_nouvelle" required>${optionsHtml(CLASSES)}</select></div>
        <div class="fg"><label>Année scolaire*</label><input name="annee_scolaire" value="${anneeCourante()}" required></div>
      </div>
      <div class="fg"><label>Notes / observations</label><textarea name="notes" rows="2" placeholder="Informations complémentaires…"></textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer la demande</button>
      </div>
    </form>`, { narrow: true });
  $('#f-reinsc').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { await apiCreateReinscription(fd); toast('Demande enregistrée','success'); closeModal(); pageReinscriptions(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function validerReinsc(id, statut) {
  if (statut === 'validee') {
    modalValiderReinsc(id);
    return;
  }
  try {
    const r = await apiValiderReinscription(id, { statut });
    toast(statut === 'refusee' ? 'Réinscription refusée' : 'Réinscription réinitialisée', 'warning');
    pageReinscriptions();
  } catch(e) { toast(e.message,'error'); }
}

function modalValiderReinsc(id) {
  const r = _reinscListe.find(x => x.id === id);
  if (!r) { toast('Introuvable', 'error'); return; }
  const classeParDefaut = r.classe_nouvelle || r.classe_precedente || '';
  openModal('Valider la réinscription', `
    <div class="alert alert-info" style="margin-bottom:14px">
      <strong>${esc(r.prenom)} ${esc(r.nom)}</strong> — actuellement en <strong>${esc(r.classe_precedente||'—')}</strong>
    </div>
    <form id="f-valider-reinsc" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Classe pour la nouvelle année*</label>
        <select name="classe_nouvelle" required>${optionsHtml(CLASSES, classeParDefaut)}</select>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-ok">✔ Valider la réinscription</button>
      </div>
    </form>`, { narrow: true });
  $('#f-valider-reinsc').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      const res = await apiValiderReinscription(id, { statut: 'validee', classe_nouvelle: fd.classe_nouvelle });
      closeModal();
      if (res.avertissement_paiement) {
        toast(`Réinscription validée, mais paiement non généré : ${res.avertissement_paiement}`, 'warning');
      } else {
        toast(`Réinscription validée ✅ — ${fd.classe_nouvelle}`, 'success');
      }
      pageReinscriptions();
    } catch(err) { toast(err.message,'error'); }
  };
}
window.modalValiderReinsc = modalValiderReinsc;

async function delReinsc(id) {
  if (!confirmDel()) return;
  try { await apiDeleteReinscription(id); toast('Supprimée','success'); pageReinscriptions(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalReinscription = modalReinscription;
window.validerReinsc = validerReinsc;
window.delReinsc = delReinsc;
