/* ===================== COMPTABILITÉ ===================== */
const JOURNAL_LABELS = {
  ventes: '<span class="badge bdg-ok">📥 Ventes</span>',
  achats: '<span class="badge bdg-err">📤 Achats</span>',
  salaires: '<span class="badge bdg-gray">💰 Salaires</span>',
  diverses: '<span class="badge bdg-gray">📋 Diverses</span>',
  a_nouveau: '<span class="badge bdg-gray">📅 À nouveau</span>',
};
const STATUT_VAL_BADGE = {
  auto: '', // pas de badge, opération normale déjà comptabilisée
  valide: '<span class="badge bdg-ok">✔ Validée</span>',
  attente_directeur: '<span class="badge bdg-warn">⏳ Attente directeur</span>',
  attente_admin: '<span class="badge bdg-warn">⏳ Attente admin</span>',
  rejete: '<span class="badge bdg-err">✕ Rejetée</span>',
};

async function pageComptabilite() {
  $('#content').innerHTML = loadingHtml;
  try {
    const transactions = await apiGetTransactions(`date_debut=${new Date(new Date().getFullYear(),0,1).toISOString().split('T')[0]}&date_fin=${today()}`);
    let enAttente = [];
    if (['admin','directeur'].includes(currentUser.role)) {
      try { enAttente = await apiTransactionsEnAttente(); } catch(_) {}
    }
    let curr = transactions;

    const render = data => {
      const { items, page, totalPages, total } = paginate('compta', data);
      // Les totaux n'incluent que les opérations effectivement comptabilisées (auto ou validées)
      const compte = t => t.statut_validation === 'auto' || t.statut_validation === 'valide';
      const r2 = data.filter(t=>t.type==='entree' && compte(t)).reduce((s,t)=>s+t.montant,0);
      const d2 = data.filter(t=>t.type==='sortie' && compte(t)).reduce((s,t)=>s+t.montant,0);
      $('#compta-summary').innerHTML = `
        <div class="stats-grid" style="grid-template-columns:repeat(4,1fr)">
          <div class="stat"><div class="stat-label">Recettes</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(r2)}</div></div>
          <div class="stat"><div class="stat-label">Dépenses</div><div class="stat-val text-err" style="font-size:16px">${fmtMoney(d2)}</div></div>
          <div class="stat"><div class="stat-label">Solde net</div><div class="stat-val" style="font-size:16px;color:${(r2-d2)>=0?'var(--c-ok)':'var(--c-err)'}">${fmtMoney(r2-d2)}</div></div>
          <div class="stat"><div class="stat-label">Transactions</div><div class="stat-val">${data.length}</div></div>
        </div>`;
      $('#tb-compta').innerHTML = data.length ? items.map(t => `<tr>
        <td>${fmtDate(t.date_op)}</td>
        <td><span class="badge ${t.type==='entree'?'bdg-ok':'bdg-err'}">${t.type==='entree'?'➕ Recette':'➖ Dépense'}</span></td>
        <td>${JOURNAL_LABELS[t.journal]||''}</td>
        <td>${esc(t.description||t.categorie||'—')}</td>
        <td><span class="badge bdg-gray">${esc(t.categorie||'—')}</span></td>
        <td>${esc(t.moyen_paiement||'—')}</td>
        <td class="mono text-right fw-600 ${t.type==='entree'?'text-ok':'text-err'}">${t.type==='entree'?'+':'−'}${fmtMoney(t.montant)}</td>
        <td>${STATUT_VAL_BADGE[t.statut_validation]||''}</td>
        <td class="text-muted" style="font-size:11px">${esc(t.cree_par_nom||'—')}</td>
        <td>
          ${t.eleve_nom?`<span class="text-muted" style="font-size:11px">${esc(t.eleve_prenom||'')} ${esc(t.eleve_nom||'')}</span><br>`:''}
          <div class="td-actions">
            ${(t.statut_validation==='auto'||t.statut_validation==='valide')?`<button class="btn btn-outline btn-xs" onclick="reimprimerTransaction('${escJs(t.id)}')" title="Réimprimer le reçu">🖨</button>`:''}
            ${currentUser.role==='admin'?`<button class="btn btn-danger btn-xs" onclick="delTransaction('${escJs(t.id)}')">🗑</button>`:''}
          </div>
        </td>
      </tr>`).join('') : `<tr><td colspan="9">${emptyHtml('💳','Aucune transaction pour cette période')}</td></tr>`;
      $('#pag-compta').innerHTML = paginationHtml('compta', page, totalPages, total);
    };
    window._comptaTransactionsCache = transactions;

    $('#content').innerHTML = `
    ${enAttente.length ? `<div class="alert alert-warn mb-4">
      ⏳ <strong>${enAttente.length}</strong> dépense${enAttente.length>1?'s':''} en attente de votre approbation
      <button class="btn btn-outline btn-xs" style="margin-left:10px" onclick="voirApprobations()">Voir</button>
    </div>` : ''}
    <div id="compta-summary" class="mb-4"></div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">💳 Journal comptable</span>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="modalLivreJournal()">📖 Livre Journal</button>
          <button class="btn btn-outline btn-sm" onclick="exporterJournalExcel()">📊 Export Excel</button>
          <button class="btn btn-outline btn-sm" onclick="pageBudget()">🎯 Budget prévisionnel</button>
          <button class="btn btn-outline btn-sm" onclick="pageAnalyseComptable()">📈 Tableau de bord</button>
          <button class="btn btn-outline btn-sm" onclick="pageBalance()">⚖️ Balance générale</button>
          <button class="btn btn-outline btn-sm" onclick="pageReleves()">📑 Relevés</button>
          <button class="btn btn-outline btn-sm" onclick="pageRapprochement()">🏦 Rapprochement bancaire</button>
          <button class="btn btn-outline btn-sm" onclick="modalTransactionsRecurrentes()">🔁 Récurrentes</button>
          ${['admin','comptable'].includes(currentUser.role)?`
          <button class="btn btn-ok btn-sm" onclick="modalTransaction('entree')">+ Recette</button>
          <button class="btn btn-danger btn-sm" onclick="modalTransaction('sortie')">− Dépense</button>
          `:''}
        </div>
      </div>
      <div class="filters">
        <div class="fg"><label>Du</label><input type="date" id="f-tdeb" value="${new Date(new Date().getFullYear(),0,1).toISOString().split('T')[0]}"></div>
        <div class="fg"><label>Au</label><input type="date" id="f-tfin" value="${today()}"></div>
        <div class="fg"><label>Type</label><select id="f-ttype"><option value="">Tous</option><option value="entree">Recettes</option><option value="sortie">Dépenses</option></select></div>
        <div class="fg"><label>Journal</label><select id="f-tjournal">
          <option value="">Tous</option>
          <option value="ventes">📥 Ventes</option><option value="achats">📤 Achats</option>
          <option value="salaires">💰 Salaires</option><option value="diverses">📋 Opérations diverses</option>
          <option value="a_nouveau">📅 À nouveau</option>
        </select></div>
        <div class="fg grow"><label>Recherche</label><input id="q-t" placeholder="Description, référence…"></div>
        <button class="btn btn-outline btn-sm" style="align-self:flex-end" onclick="reloadTransactions()">🔍</button>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-compta"><th>Date</th><th>Type</th><th>Journal</th><th>Description</th><th>Catégorie</th><th>Moyen</th><th class="text-right">Montant</th><th>Statut</th><th>Créé par</th><th>Lié / Actions</th></tr></thead>
        <tbody id="tb-compta"></tbody>
      </table></div>
      <div id="pag-compta"></div>
    </div>`;

    getPaginator('compta').onChange = () => render(curr);
    render(transactions);

    makeSortableTable('#th-compta', () => curr, render,
      ['date_op', 'type', 'journal', 'description', 'categorie', 'moyen_paiement', 'montant', 'statut_validation', 'cree_par_nom', null]);

    window.reloadTransactions = async () => {
      const deb = $('#f-tdeb').value;
      const fin = $('#f-tfin').value;
      const type = $('#f-ttype').value;
      const journal = $('#f-tjournal').value;
      const q = $('#q-t').value;
      let qs = [];
      if (deb) qs.push(`date_debut=${deb}`);
      if (fin) qs.push(`date_fin=${fin}`);
      if (type) qs.push(`type=${type}`);
      if (journal) qs.push(`journal=${journal}`);
      if (q) qs.push(`q=${encodeURIComponent(q)}`);
      try { curr = await apiGetTransactions(qs.join('&')); resetPaginator('compta'); render(curr); }
      catch(e) { toast(e.message,'error'); }
    };
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

async function voirApprobations() {
  const enAttente = await apiTransactionsEnAttente();
  openModal(`⏳ Dépenses en attente d'approbation (${enAttente.length})`, `
    ${enAttente.length ? `<div class="tbl-wrap"><table>
      <thead><tr><th>Date</th><th>Description</th><th class="text-right">Montant</th><th>Créé par</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody>
        ${enAttente.map(t => `<tr>
          <td>${fmtDate(t.date_op)}</td>
          <td>${esc(t.description||t.categorie||'—')}</td>
          <td class="mono text-right text-err fw-600">${fmtMoney(t.montant)}</td>
          <td class="text-muted" style="font-size:12px">${esc(t.cree_par_nom||'—')}</td>
          <td>${STATUT_VAL_BADGE[t.statut_validation]||''}</td>
          <td><div class="td-actions">
            <button class="btn btn-ok btn-xs" onclick="approuverTransaction('${escJs(t.id)}')">✔ Approuver</button>
            <button class="btn btn-danger btn-xs" onclick="rejeterTransactionPrompt('${escJs(t.id)}')">✕ Rejeter</button>
          </div></td>
        </tr>`).join('')}
      </tbody>
    </table></div>` : emptyHtml('✅','Aucune dépense en attente')}
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
  `, { wide: true });
}

async function approuverTransaction(id) {
  try { await apiApprouverTransaction(id); toast('Dépense approuvée ✅','success'); closeModal(); pageComptabilite(); }
  catch(e) { toast(e.message,'error'); }
}

async function rejeterTransactionPrompt(id) {
  const motif = prompt('Motif du rejet (optionnel) :');
  if (motif === null) return;
  try { await apiRejeterTransaction(id, { motif }); toast('Dépense rejetée','warning'); closeModal(); pageComptabilite(); }
  catch(e) { toast(e.message,'error'); }
}

async function modalTransaction(typeDefaut = 'entree') {
  const personnel = await apiGetPersonnel().catch(() => []);
  const fournisseurs = await apiGetFournisseurs('actifs=1').catch(() => []);
  openModal('Saisir une opération', `
    <form id="f-tr" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Type*</label><select name="type" required id="tr-type" onchange="updateCatOptions()">
          <option value="entree" ${typeDefaut==='entree'?'selected':''}>➕ Recette (entrée)</option>
          <option value="sortie" ${typeDefaut==='sortie'?'selected':''}>➖ Dépense (sortie)</option>
        </select></div>
        <div class="fg"><label>Date*</label><input type="date" name="date_op" value="${today()}" required></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Journal comptable*</label><select name="journal" id="tr-journal">
          ${optionsHtml([
            {value:'ventes',label:'📥 Journal des Ventes'},{value:'achats',label:'📤 Journal des Achats'},
            {value:'salaires',label:'💰 Journal Opérations Salaire'},{value:'diverses',label:'📋 Journal Opérations Diverses'},
            {value:'a_nouveau',label:'📅 Journal À Nouveau'},
          ], typeDefaut==='entree'?'ventes':'achats', false)}
        </select></div>
        <div class="fg"><label>Catégorie</label><select name="categorie" id="tr-cat" onchange="updateCatOptions()">
          ${(typeDefaut==='entree'?CAT_ENTREE:CAT_SORTIE).map(c=>`<option>${esc(c)}</option>`).join('')}
        </select></div>
      </div>
      <div class="fg"><label>Montant (GNF)*</label><input type="number" name="montant" required min="1" step="1"></div>
      <div class="fg" id="tr-benef-wrap" style="display:${typeDefaut==='sortie'?'':'none'}">
        <label id="tr-benef-label">Bénéficiaire / Prestataire de service</label>
        <div id="tr-benef-field"><input name="beneficiaire" placeholder="Nom de la personne ou de l'entreprise payée"></div>
      </div>
      <div class="fg" id="tr-fournisseur-wrap" style="display:none">
        <label>Fournisseur <span style="font-weight:400;color:#9CA3AF">(optionnel — pour suivre l'historique par fournisseur)</span></label>
        <select name="fournisseur_id">
          <option value="">— Aucun —</option>
          ${fournisseurs.map(f => `<option value="${esc(f.id)}">${esc(f.nom)}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Description</label><input name="description" placeholder="Détails de l'opération"></div>
      <div class="form-2">
        <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
        <div class="fg"><label>Référence</label><input name="reference" placeholder="N° chèque, reçu…"></div>
      </div>
      <div id="tr-approbation-hint"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);

  window.updateCatOptions = () => {
    const type = $('#tr-type').value;
    const cats = type === 'entree' ? CAT_ENTREE : CAT_SORTIE;
    if ($('#tr-cat').options.length === 0 || $('#tr-cat').dataset.type !== type) {
      $('#tr-cat').innerHTML = cats.map(c=>`<option>${esc(c)}</option>`).join('');
      $('#tr-cat').dataset.type = type;
    }
    $('#tr-benef-wrap').style.display = type === 'sortie' ? '' : 'none';

    // Journal : suggestion intelligente selon le type, modifiable librement par l'utilisateur.
    // On ne l'écrase que si l'utilisateur ne l'a pas déjà modifié lui-même.
    const journalSelect = $('#tr-journal');
    if (!journalSelect.dataset.modifieParUtilisateur) {
      journalSelect.value = type === 'entree' ? 'ventes' : 'achats';
    }

    // Catégorie "Salaires" : proposer directement la liste des employés, groupée par poste,
    // plutôt qu'un champ libre — plus rapide et évite les erreurs de saisie de nom.
    const cat = $('#tr-cat').value;
    const benefField = $('#tr-benef-field');
    if (type === 'sortie' && cat === 'Salaires') {
      $('#tr-benef-label').textContent = 'Employé concerné';
      const postes = [...new Set(personnel.map(p => p.poste || 'Autre'))].sort();
      benefField.innerHTML = `<select name="beneficiaire">
        <option value="">— Choisir un employé —</option>
        ${postes.map(poste => `<optgroup label="${esc(poste)}">
          ${personnel.filter(p => (p.poste||'Autre') === poste).map(p =>
            `<option value="${esc(p.prenom)} ${esc(p.nom)}">${esc(p.prenom)} ${esc(p.nom)}</option>`).join('')}
        </optgroup>`).join('')}
      </select>`;
      if (!journalSelect.dataset.modifieParUtilisateur) journalSelect.value = 'salaires';
    } else if (benefField.querySelector('select')) {
      $('#tr-benef-label').textContent = 'Bénéficiaire / Prestataire de service';
      benefField.innerHTML = `<input name="beneficiaire" placeholder="Nom de la personne ou de l'entreprise payée">`;
    }
    updateFournisseurVisibility();
  };
  window.updateFournisseurVisibility = () => {
    $('#tr-fournisseur-wrap').style.display = $('#tr-journal').value === 'achats' ? '' : 'none';
  };
  $('#tr-journal').addEventListener('change', () => {
    $('#tr-journal').dataset.modifieParUtilisateur = '1';
    updateFournisseurVisibility();
  });
  updateCatOptions();
  $('#f-tr').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant);
    const beneficiaire = fd.beneficiaire;
    delete fd.beneficiaire; // pas une colonne de la table transactions, juste pour le reçu
    try {
      const res = await apiCreateTransaction(fd);
      if (res._info) toast(res._info, 'warning'); else toast('Opération enregistrée','success');
      closeModal(); pageComptabilite();
      // Reçu de paiement pour un prestataire de service (point 6) — uniquement si la dépense
      // est déjà validée (pas en attente d'approbation) et qu'un bénéficiaire est renseigné.
      if (fd.type === 'sortie' && beneficiaire && res.statut_validation === 'auto') {
        imprimerRecu({
          type: 'sortie', nom: beneficiaire, description: fd.description || fd.categorie,
          montant: fd.montant, date: fd.date_op, moyenPaiement: fd.moyen_paiement,
          reference: fd.reference, recuPar: currentUser?.full_name,
        });
      }
    }
    catch(err) { toast(err.message,'error'); }
  };
}

/* ===================== LIVRE JOURNAL ===================== */
async function modalTransactionsRecurrentes() {
  const liste = await apiGetTransactionsRecurrentes();
  openModal('🔁 Transactions récurrentes automatiques', `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="text-muted" style="font-size:12.5px">Ces opérations (loyer, salaires fixes...) sont générées automatiquement chaque mois, dès le jour configuré atteint — plus besoin de les ressaisir.</div>
      <div id="rec-liste" style="display:flex;flex-direction:column;gap:8px">
        ${liste.length ? liste.map(t => `
          <div class="flex items-center gap-3" style="border:1px solid #E5E7EB;border-radius:8px;padding:10px 12px;${!t.actif?'opacity:.55':''}">
            <div style="flex:1">
              <strong>${esc(t.categorie)}</strong> — <span class="${t.type==='entree'?'text-ok':'text-err'}">${fmtMoney(t.montant)}</span>
              <div class="text-muted" style="font-size:11.5px">${t.type==='entree'?'Recette':'Dépense'} · le ${t.jour_du_mois} de chaque mois ${!t.actif?'· <strong>Inactive</strong>':''}</div>
            </div>
            <button type="button" class="btn btn-outline btn-xs" onclick="toggleRecurrente('${escJs(t.id)}',${t.actif?'false':'true'})">${t.actif?'⏸ Suspendre':'▶ Réactiver'}</button>
            <button type="button" class="btn btn-danger btn-xs" onclick="supprimerRecurrente('${escJs(t.id)}')">🗑</button>
          </div>`).join('') : '<span class="text-muted" style="font-size:13px">Aucune transaction récurrente configurée.</span>'}
      </div>
      <button type="button" class="btn btn-outline btn-sm" onclick="modalNouvelleRecurrente()">+ Ajouter une transaction récurrente</button>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
    </div>`);
}
window.modalTransactionsRecurrentes = modalTransactionsRecurrentes;

function modalNouvelleRecurrente() {
  openModal('+ Nouvelle transaction récurrente', `
    <form id="f-rec" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Type*</label><select name="type" required>
          <option value="sortie">Dépense</option><option value="entree">Recette</option>
        </select></div>
        <div class="fg"><label>Jour du mois*</label><input type="number" name="jour_du_mois" min="1" max="28" value="1" required></div>
      </div>
      <div class="fg"><label>Catégorie*</label><input name="categorie" required placeholder="Loyer, Salaires…"></div>
      <div class="fg"><label>Description</label><input name="description" placeholder="Loyer mensuel du local…"></div>
      <div class="form-2">
        <div class="fg"><label>Montant (GNF)*</label><input type="number" name="montant" min="1" required></div>
        <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="modalTransactionsRecurrentes()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });

  $('#f-rec').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant);
    fd.jour_du_mois = parseInt(fd.jour_du_mois);
    try {
      await apiCreateTransactionRecurrente(fd);
      toast('Transaction récurrente créée', 'success');
      modalTransactionsRecurrentes();
    } catch(err) { toast(err.message, 'error'); }
  };
}
window.modalNouvelleRecurrente = modalNouvelleRecurrente;

async function toggleRecurrente(id, actif) {
  try {
    await apiUpdateTransactionRecurrente(id, { actif: actif === 'true' });
    toast(actif==='true' ? 'Réactivée' : 'Suspendue', 'success');
    modalTransactionsRecurrentes();
  } catch(err) { toast(err.message, 'error'); }
}
window.toggleRecurrente = toggleRecurrente;

async function supprimerRecurrente(id) {
  if (!confirm('Supprimer définitivement cette transaction récurrente ?')) return;
  try {
    await apiDeleteTransactionRecurrente(id);
    toast('Supprimée', 'success');
    modalTransactionsRecurrentes();
  } catch(err) { toast(err.message, 'error'); }
}
window.supprimerRecurrente = supprimerRecurrente;

function exporterJournalExcel() {
  const deb = $('#f-tdeb')?.value, fin = $('#f-tfin')?.value;
  const params = new URLSearchParams();
  if (deb) params.set('date_debut', deb);
  if (fin) params.set('date_fin', fin);
  apiExportTransactionsExcel(params.toString());
  toast('Génération du fichier Excel…', 'success');
}
window.exporterJournalExcel = exporterJournalExcel;

function modalLivreJournal() {
  const debutMois = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
  openModal('📖 Livre Journal comptable', `
    <div class="alert alert-info" style="font-size:12.5px">Le livre journal recense, dans l'ordre chronologique, toutes les opérations effectivement comptabilisées (validées) sur la période choisie, avec le solde progressif — un document comptable officiel, imprimable.</div>
    <form id="f-livre" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Du</label><input type="date" name="date_debut" value="${debutMois}" required></div>
        <div class="fg"><label>Au</label><input type="date" name="date_fin" value="${today()}" required></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">📖 Générer le livre journal</button>
      </div>
    </form>`, { narrow: true });
  $('#f-livre').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { await imprimerLivreJournal(fd.date_debut, fd.date_fin); closeModal(); }
    catch(err) { toast(err.message, 'error'); }
  };
}
window.modalLivreJournal = modalLivreJournal;

async function imprimerLivreJournal(dateDebut, dateFin) {
  const compte = t => t.statut_validation === 'auto' || t.statut_validation === 'valide';

  // Solde d'ouverture = somme de toutes les opérations comptabilisées AVANT la période
  const veille = new Date(new Date(dateDebut).getTime() - 86400000).toISOString().split('T')[0];
  const avant = veille >= dateDebut ? [] : await apiGetTransactions(`date_fin=${veille}`);
  const soldeOuverture = avant.filter(compte).reduce((s,t) => s + (t.type==='entree'?t.montant:-t.montant), 0);

  // Opérations de la période, triées chronologiquement (du plus ancien au plus récent)
  const periode = (await apiGetTransactions(`date_debut=${dateDebut}&date_fin=${dateFin}`))
    .filter(compte)
    .sort((a,b) => (a.date_op+a.created_at).localeCompare(b.date_op+b.created_at));

  const settings = await apiGetSettings();
  let solde = soldeOuverture;
  const totalDebit = periode.filter(t=>t.type==='sortie').reduce((s,t)=>s+t.montant,0);
  const totalCredit = periode.filter(t=>t.type==='entree').reduce((s,t)=>s+t.montant,0);

  const lignes = periode.map(t => {
    solde += (t.type==='entree' ? t.montant : -t.montant);
    const libelle = t.eleve_nom ? `${t.description||t.categorie} — ${t.eleve_prenom||''} ${t.eleve_nom||''}` : (t.description || t.categorie || '—');
    return `<tr>
      <td>${fmtDate(t.date_op)}</td>
      <td>${esc(libelle)}</td>
      <td class="mono" style="font-size:9.5px">${esc(t.reference||'—')}</td>
      <td class="text-right mono">${t.type==='sortie'?Number(t.montant).toLocaleString('fr-FR'):''}</td>
      <td class="text-right mono">${t.type==='entree'?Number(t.montant).toLocaleString('fr-FR'):''}</td>
      <td class="text-right mono fw-600">${Number(solde).toLocaleString('fr-FR')}</td>
    </tr>`;
  }).join('');

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Livre Journal — ${dateDebut} au ${dateFin}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:Arial,sans-serif;font-size:11.5px;color:#1F2937;margin:0;padding:26px;background:#F3F4F6}
    .doc{max-width:1000px;margin:0 auto;background:#fff;border:1px solid #D1D5DB;border-radius:4px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
    .bandeau{height:6px;display:flex}
    .bandeau div{flex:1}
    .inner{padding:28px 32px}
    .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111827;padding-bottom:14px;margin-bottom:16px}
    .header .ecole{display:flex;gap:12px;align-items:center}
    .header img{max-height:46px}
    .header h1{font-size:14px;margin:0 0 2px;color:#111827;font-weight:700}
    .header p{margin:1px 0;font-size:10px;color:#6B7280}
    .titre-doc{text-align:center;margin:6px 0 18px}
    .titre-doc h2{font-size:17px;letter-spacing:2px;color:#111827;margin:0}
    .titre-doc p{font-size:11px;color:#6B7280;margin:3px 0 0}
    table{width:100%;border-collapse:collapse;font-size:10.5px}
    th{background:#111827;color:#fff;padding:7px 8px;text-align:left;font-size:9.5px;text-transform:uppercase}
    th.text-right{text-align:right}
    td{padding:6px 8px;border-bottom:1px solid #F0F1F3}
    .ouverture td{background:#F9FAFB;font-style:italic;color:#4B5563;font-weight:600}
    .totaux td{background:#EEF2FF;font-weight:800;border-top:2px solid #111827;border-bottom:none}
    .cloture td{background:#111827;color:#fff;font-weight:800}
    .signatures{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:44px}
    .signatures .col{text-align:center}
    .signatures .cachet-img{max-height:50px;max-width:100px;display:block;margin:0 auto 2px}
    .signatures .signature-img{max-height:32px;max-width:100px;display:block;margin:0 auto 2px}
    .signatures .lbl{border-top:1px solid #9CA3AF;padding-top:6px;font-size:10.5px;color:#4B5563;margin-top:6px}
    .credit{text-align:center;font-size:8.5px;color:#C0C4CC;margin-top:26px}
    @media print{ body{background:#fff;padding:0} .doc{box-shadow:none} @page{size:A4 landscape;margin:12mm} }
  </style></head><body>
  <div class="doc">
    <div class="bandeau"><div style="background:#CE1126"></div><div style="background:#FCD116"></div><div style="background:#009460"></div></div>
    <div class="inner">
      <div class="header">
        <div class="ecole">
          ${settings.ecole_logo?`<img src="${settings.ecole_logo}">`:''}
          <div>
            <h1>${esc(settings.ecole_nom||'MY-ECOLE')}</h1>
            <p>${esc(settings.ecole_adresse||'')}</p>
            ${settings.ecole_telephone?`<p>Tél : ${esc(settings.ecole_telephone)}</p>`:''}
          </div>
        </div>
        <div style="text-align:right;font-size:10px;color:#6B7280">Édité le ${fmtDate(today())}<br>Par ${esc(currentUser?.full_name||'')}</div>
      </div>
      <div class="titre-doc">
        <h2>LIVRE JOURNAL</h2>
        <p>Période du ${fmtDate(dateDebut)} au ${fmtDate(dateFin)}</p>
      </div>
      <table>
        <thead><tr><th>Date</th><th>Libellé</th><th>Référence</th><th class="text-right">Débit (GNF)</th><th class="text-right">Crédit (GNF)</th><th class="text-right">Solde (GNF)</th></tr></thead>
        <tbody>
          <tr class="ouverture"><td colspan="5">Solde d'ouverture au ${fmtDate(dateDebut)}</td><td class="text-right mono">${Number(soldeOuverture).toLocaleString('fr-FR')}</td></tr>
          ${lignes || `<tr><td colspan="6" style="text-align:center;color:#9CA3AF;padding:20px">Aucune opération comptabilisée sur cette période</td></tr>`}
          <tr class="totaux"><td colspan="3">TOTAUX DE LA PÉRIODE</td>
            <td class="text-right mono">${totalDebit.toLocaleString('fr-FR')}</td>
            <td class="text-right mono">${totalCredit.toLocaleString('fr-FR')}</td><td></td></tr>
          <tr class="cloture"><td colspan="5">SOLDE DE CLÔTURE au ${fmtDate(dateFin)}</td><td class="text-right mono">${Number(solde).toLocaleString('fr-FR')}</td></tr>
        </tbody>
      </table>
      <div class="signatures">
        <div class="col">
          ${settings.ecole_cachet?`<img class="cachet-img" src="${settings.ecole_cachet}">`:''}
          ${settings.signature_directeur?`<img class="signature-img" src="${settings.signature_directeur}">`:''}
          <div class="lbl">Le Directeur</div>
        </div>
        <div class="col"><div class="lbl">Le Comptable</div></div>
      </div>
      <div class="credit">Application développée par Actif System Groupe — Tél : 661-97-43-43</div>
    </div>
  </div>
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  imprimerFenetre(win);
}
window.imprimerLivreJournal = imprimerLivreJournal;

async function reimprimerTransaction(id) {
  let t = (window._comptaTransactionsCache || []).find(x => x.id === id);
  if (!t) {
    try { t = (await apiGetTransactions()).find(x => x.id === id); } catch(_) {}
  }
  if (!t) { toast('Transaction introuvable pour la réimpression','error'); return; }
  const nom = t.eleve_nom ? `${t.eleve_prenom||''} ${t.eleve_nom||''}`.trim() : (t.description || t.categorie || '—');
  imprimerRecu({
    type: t.type, nom, description: t.description || t.categorie,
    montant: t.montant, date: t.date_op, moyenPaiement: t.moyen_paiement,
    reference: t.reference, recuPar: t.cree_par_nom || currentUser?.full_name,
  });
}
window.reimprimerTransaction = reimprimerTransaction;

async function delTransaction(id) {
  if (!confirmDel('Supprimer cette transaction ?')) return;
  try { await apiDeleteTransaction(id); toast('Supprimée','success'); pageComptabilite(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalTransaction = modalTransaction;
window.delTransaction = delTransaction;
window.voirApprobations = voirApprobations;
window.approuverTransaction = approuverTransaction;
window.rejeterTransactionPrompt = rejeterTransactionPrompt;

/* ===================== BUDGET PRÉVISIONNEL ===================== */
async function pageBudget(mois) {
  mois = mois || new Date().toISOString().slice(0, 7);
  $('#content').innerHTML = loadingHtml;
  const data = await apiComparaisonBudget(mois);
  const lignes = data.lignes;

  const totalPrevu = lignes.reduce((s, l) => s + (l.type === 'sortie' ? l.montant_prevu : 0), 0);
  const totalRealise = lignes.reduce((s, l) => s + (l.type === 'sortie' ? l.montant_realise : 0), 0);

  $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">🎯 Budget prévisionnel</span>
        <div class="card-actions">
          <input type="month" id="budget-mois" value="${mois}" onchange="pageBudget(this.value)">
          <button class="btn btn-primary btn-sm" onclick="modalNouveauBudget('${mois}')">+ Définir un budget</button>
          <button class="btn btn-outline btn-sm" onclick="pageComptabilite()">← Retour</button>
        </div>
      </div>
      <div class="card-body">
        <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:20px">
          <div class="stat"><div class="stat-label">Budget dépenses prévu</div><div class="stat-val" style="font-size:16px">${fmtMoney(totalPrevu)}</div></div>
          <div class="stat"><div class="stat-label">Dépenses réalisées</div><div class="stat-val ${totalRealise>totalPrevu?'text-err':'text-ok'}" style="font-size:16px">${fmtMoney(totalRealise)}</div></div>
          <div class="stat"><div class="stat-label">Écart</div><div class="stat-val ${totalRealise>totalPrevu?'text-err':'text-ok'}" style="font-size:16px">${totalRealise>totalPrevu?'+':''}${fmtMoney(totalRealise-totalPrevu)}</div></div>
        </div>
        ${lignes.length ? `
        <table class="table">
          <thead><tr><th>Catégorie</th><th>Type</th><th>Prévu</th><th>Réalisé</th><th>Écart</th><th>Progression</th><th></th></tr></thead>
          <tbody>
            ${lignes.map(l => {
              const pct = l.pourcentage;
              const depasse = l.type === 'sortie' && pct !== null && pct > 100;
              const barColor = depasse ? 'var(--c-err)' : (pct !== null && pct > 80 ? 'var(--c-warn)' : 'var(--c-ok)');
              return `<tr>
                <td><strong>${esc(l.categorie)}</strong></td>
                <td>${l.type==='entree'?'Recette':'Dépense'}</td>
                <td>${fmtMoney(l.montant_prevu)}</td>
                <td>${fmtMoney(l.montant_realise)}</td>
                <td class="${l.ecart>0 && l.type==='sortie'?'text-err':'text-ok'}">${l.ecart>0?'+':''}${fmtMoney(l.ecart)}</td>
                <td style="min-width:120px">
                  ${pct!==null ? `
                    <div class="progress">
                      <div class="progress-bar" style="width:${Math.min(pct,100)}%;background:${barColor}"></div>
                    </div>
                    <div class="text-muted" style="font-size:11px;margin-top:2px">${pct}%</div>
                  ` : '<span class="text-muted" style="font-size:11px">Pas de budget</span>'}
                </td>
                <td><button class="btn btn-danger btn-xs" onclick="supprimerBudgetLigne('${escJs(l.categorie)}','${l.type}','${mois}')">🗑</button></td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>` : emptyHtml('🎯', 'Aucun budget ni transaction pour ce mois. Définissez un premier budget pour commencer le suivi.')}
      </div>
    </div>`;
}
window.pageBudget = pageBudget;

function modalNouveauBudget(mois) {
  openModal('🎯 Définir un budget', `
    <form id="f-budget" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Mois*</label><input type="month" name="mois" value="${mois}" required></div>
      <div class="form-2">
        <div class="fg"><label>Type*</label><select name="type" required>
          <option value="sortie">Dépense</option><option value="entree">Recette</option>
        </select></div>
        <div class="fg"><label>Catégorie*</label><input name="categorie" required placeholder="Fournitures scolaires…"></div>
      </div>
      <div class="fg"><label>Montant prévu (GNF)*</label><input type="number" name="montant_prevu" min="0" required></div>
      <div class="text-muted" style="font-size:11.5px">Si un budget existe déjà pour cette catégorie et ce mois, il sera simplement mis à jour.</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="pageBudget('${mois}')">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });

  $('#f-budget').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant_prevu = parseFloat(fd.montant_prevu);
    try {
      await apiSaveBudget(fd);
      toast('Budget enregistré', 'success');
      closeModal();
      pageBudget(fd.mois);
    } catch(err) { toast(err.message, 'error'); }
  };
}
window.modalNouveauBudget = modalNouveauBudget;

async function supprimerBudgetLigne(categorie, type, mois) {
  if (!confirm(`Retirer le budget prévu pour « ${categorie} » ?`)) return;
  const tous = await apiGetBudgets(mois);
  const ligne = tous.find(b => b.categorie === categorie && b.type === type);
  if (!ligne) { pageBudget(mois); return; }
  try {
    await apiDeleteBudget(ligne.id);
    toast('Budget retiré', 'success');
    pageBudget(mois);
  } catch(err) { toast(err.message, 'error'); }
}
window.supprimerBudgetLigne = supprimerBudgetLigne;

/* ===================== TABLEAU DE BORD COMPTABLE (GRAPHIQUES) ===================== */
let _chartsComptables = [];
async function pageAnalyseComptable(mois) {
  mois = mois || new Date().toISOString().slice(0, 7);
  $('#content').innerHTML = loadingHtml;
  const data = await apiAnalyseComptable(mois);

  _chartsComptables.forEach(c => c.destroy());
  _chartsComptables = [];

  $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">📈 Tableau de bord comptable</span>
        <div class="card-actions">
          <input type="month" value="${mois}" onchange="pageAnalyseComptable(this.value)">
          <button class="btn btn-outline btn-sm" onclick="pageComptabilite()">← Retour</button>
        </div>
      </div>
      <div class="card-body">
        <h4 style="margin:0 0 10px">Évolution sur 12 mois</h4>
        <div style="height:280px;margin-bottom:28px"><canvas id="ch-tendance"></canvas></div>
        <div class="form-2">
          <div>
            <h4 style="margin:0 0 10px">Répartition des dépenses — ${mois}</h4>
            <div style="height:260px">
              ${data.repartition_depenses.length ? '<canvas id="ch-depenses"></canvas>' : emptyHtml('📉','Aucune dépense ce mois-ci')}
            </div>
          </div>
          <div>
            <h4 style="margin:0 0 10px">Répartition des recettes — ${mois}</h4>
            <div style="height:260px">
              ${data.repartition_recettes.length ? '<canvas id="ch-recettes"></canvas>' : emptyHtml('📈','Aucune recette ce mois-ci')}
            </div>
          </div>
        </div>
      </div>
    </div>`;

  try {
    if (typeof Chart === 'undefined') throw new Error('Chart.js indisponible');
    const COULEURS = ['#F0703F','#164B41','#5296C5','#F2B134','#8B5CF6','#EC4899','#14B8A6','#F97316','#6366F1','#84CC16'];

    _chartsComptables.push(new Chart($('#ch-tendance'), {
      type: 'bar',
      data: {
        labels: data.tendance.map(t => t.mois),
        datasets: [
          { label: 'Recettes', data: data.tendance.map(t => t.recettes), backgroundColor: 'rgba(5,150,105,.75)' },
          { label: 'Dépenses', data: data.tendance.map(t => t.depenses), backgroundColor: 'rgba(220,38,38,.75)' },
        ]
      },
      options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'top'}}, scales:{y:{beginAtZero:true}} }
    }));

    if (data.repartition_depenses.length) {
      _chartsComptables.push(new Chart($('#ch-depenses'), {
        type: 'doughnut',
        data: {
          labels: data.repartition_depenses.map(d => d.categorie),
          datasets: [{ data: data.repartition_depenses.map(d => d.total), backgroundColor: COULEURS }]
        },
        options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'right',labels:{boxWidth:12,font:{size:11}}}} }
      }));
    }
    if (data.repartition_recettes.length) {
      _chartsComptables.push(new Chart($('#ch-recettes'), {
        type: 'doughnut',
        data: {
          labels: data.repartition_recettes.map(d => d.categorie),
          datasets: [{ data: data.repartition_recettes.map(d => d.total), backgroundColor: COULEURS }]
        },
        options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'right',labels:{boxWidth:12,font:{size:11}}}} }
      }));
    }
  } catch (e) { console.warn('Graphiques indisponibles :', e); }
}
window.pageAnalyseComptable = pageAnalyseComptable;

/* ===================== BALANCE GÉNÉRALE ===================== */
function _synthesesCategoriesHtml(lignes) {
  const trouve = (nom) => lignes.find(l => l.categorie === nom);
  const inscription = trouve("Frais d'inscription");
  const reinscription = trouve('Frais de réinscription');
  const scolarite = trouve('Frais de scolarité');
  const totalRecettes = lignes.reduce((s, l) => s + (l.credit_periode || 0), 0);
  const totalDepenses = lignes.reduce((s, l) => s + (l.debit_periode || 0), 0);
  const carte = (label, montant, cls = '') => `<div class="stat">
    <div class="stat-label">${esc(label)}</div>
    <div class="stat-val ${cls}" style="font-size:18px">${fmtMoney(montant || 0)}</div>
  </div>`;
  return `<div class="stats-grid">
    ${carte("Frais d'inscription (période)", inscription ? inscription.credit_periode : 0)}
    ${carte('Frais de réinscription (période)', reinscription ? reinscription.credit_periode : 0)}
    ${carte('Frais de scolarité (période)', scolarite ? scolarite.credit_periode : 0)}
    ${carte('Total recettes (période)', totalRecettes, 'text-ok')}
    ${carte('Total dépenses (période)', totalDepenses, 'text-err')}
  </div>`;
}

async function pageBalance(dateDebut, dateFin) {
  dateDebut = dateDebut || `${new Date().getFullYear()}-01-01`;
  dateFin = dateFin || today();
  $('#content').innerHTML = loadingHtml;
  try {
    const data = await apiGetBalance(dateDebut, dateFin);

    $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">⚖️ Balance générale</span>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="imprimerBalance('${dateDebut}','${dateFin}')">🖨 Imprimer</button>
          <button class="btn btn-outline btn-sm" onclick="pageComptabilite()">← Retour</button>
        </div>
      </div>
      <div class="filters">
        <div class="fg"><label>Du</label><input type="date" id="f-baldeb" value="${dateDebut}"></div>
        <div class="fg"><label>Au</label><input type="date" id="f-balfin" value="${dateFin}"></div>
        <button class="btn btn-outline btn-sm" style="align-self:flex-end" onclick="pageBalance($('#f-baldeb').value,$('#f-balfin').value)">🔍 Actualiser</button>
      </div>
      <div class="alert alert-info">💡 Le <strong>solde initial</strong> reprend l'ensemble des opérations comptabilisées avant le ${fmtDate(dateDebut)} pour chaque catégorie (report à nouveau). Le <strong>solde final</strong> = solde initial + crédit (recettes) − débit (dépenses) de la période.</div>
      ${_synthesesCategoriesHtml(data.lignes)}
      <div class="tbl-wrap"><table>
        <thead><tr>
          <th>Catégorie</th>
          <th class="text-right">Solde initial</th>
          <th class="text-right">Débit (période)</th>
          <th class="text-right">Crédit (période)</th>
          <th class="text-right">Solde final</th>
        </tr></thead>
        <tbody>
          ${data.lignes.length ? data.lignes.map(l => `<tr>
            <td><strong>${esc(l.categorie)}</strong></td>
            <td class="mono text-right ${l.solde_initial<0?'text-err':''}">${fmtMoney(l.solde_initial)}</td>
            <td class="mono text-right text-err">${l.debit_periode>0?fmtMoney(l.debit_periode):'—'}</td>
            <td class="mono text-right text-ok">${l.credit_periode>0?fmtMoney(l.credit_periode):'—'}</td>
            <td class="mono text-right fw-600 ${l.solde_final<0?'text-err':'text-ok'}">${fmtMoney(l.solde_final)}</td>
          </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('⚖️','Aucun mouvement sur cette période')}</td></tr>`}
        </tbody>
        ${data.lignes.length ? `<tfoot><tr style="background:var(--g1);font-weight:800">
          <td>TOTAL</td>
          <td class="mono text-right">${fmtMoney(data.totaux.solde_initial)}</td>
          <td class="mono text-right text-err">${fmtMoney(data.totaux.debit_periode)}</td>
          <td class="mono text-right text-ok">${fmtMoney(data.totaux.credit_periode)}</td>
          <td class="mono text-right ${data.totaux.solde_final<0?'text-err':'text-ok'}">${fmtMoney(data.totaux.solde_final)}</td>
        </tr></tfoot>` : ''}
      </table></div>
    </div>`;
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
window.pageBalance = pageBalance;

function _syntheseImprimeeHtml(lignes) {
  const trouve = (nom) => lignes.find(l => l.categorie === nom);
  const inscription = trouve("Frais d'inscription");
  const reinscription = trouve('Frais de réinscription');
  const scolarite = trouve('Frais de scolarité');
  const bloc = (label, montant) => `<div style="flex:1;text-align:center;padding:10px;border:1px solid #E5E7EB;border-radius:4px">
    <div style="font-size:9px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em">${esc(label)}</div>
    <div style="font-size:15px;font-weight:800;color:#111827;margin-top:3px">${Number((montant||0)).toLocaleString('fr-FR')} GNF</div>
  </div>`;
  return `<div style="display:flex;gap:10px;margin-bottom:18px">
    ${bloc("Frais d'inscription", inscription?inscription.credit_periode:0)}
    ${bloc('Frais de réinscription', reinscription?reinscription.credit_periode:0)}
    ${bloc('Frais de scolarité', scolarite?scolarite.credit_periode:0)}
  </div>`;
}

async function imprimerBalance(dateDebut, dateFin) {
  const data = await apiGetBalance(dateDebut, dateFin);
  const settings = await apiGetSettings();

  const lignesHtml = data.lignes.map(l => `<tr>
    <td>${esc(l.categorie)}</td>
    <td class="text-right mono">${Number(l.solde_initial).toLocaleString('fr-FR')}</td>
    <td class="text-right mono">${l.debit_periode>0?Number(l.debit_periode).toLocaleString('fr-FR'):''}</td>
    <td class="text-right mono">${l.credit_periode>0?Number(l.credit_periode).toLocaleString('fr-FR'):''}</td>
    <td class="text-right mono fw-600">${Number(l.solde_final).toLocaleString('fr-FR')}</td>
  </tr>`).join('');

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Balance générale — ${dateDebut} au ${dateFin}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:Arial,sans-serif;font-size:11.5px;color:#1F2937;margin:0;padding:26px;background:#F3F4F6}
    .doc{max-width:1000px;margin:0 auto;background:#fff;border:1px solid #D1D5DB;border-radius:4px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
    .bandeau{height:6px;display:flex}
    .bandeau div{flex:1}
    .inner{padding:28px 32px}
    .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111827;padding-bottom:14px;margin-bottom:16px}
    .header .ecole{display:flex;gap:12px;align-items:center}
    .header img{max-height:46px}
    .header h1{font-size:14px;margin:0 0 2px;color:#111827;font-weight:700}
    .header p{margin:1px 0;font-size:10px;color:#6B7280}
    .titre-doc{text-align:center;margin:6px 0 18px}
    .titre-doc h2{font-size:17px;letter-spacing:2px;color:#111827;margin:0}
    .titre-doc p{font-size:11px;color:#6B7280;margin:3px 0 0}
    table{width:100%;border-collapse:collapse;font-size:10.5px}
    th{background:#111827;color:#fff;padding:7px 8px;text-align:left;font-size:9.5px;text-transform:uppercase}
    th.text-right{text-align:right}
    td{padding:6px 8px;border-bottom:1px solid #F0F1F3}
    .totaux td{background:#EEF2FF;font-weight:800;border-top:2px solid #111827;border-bottom:none}
    .signatures{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:44px}
    .signatures .col{text-align:center}
    .signatures .cachet-img{max-height:50px;max-width:100px;display:block;margin:0 auto 2px}
    .signatures .signature-img{max-height:32px;max-width:100px;display:block;margin:0 auto 2px}
    .signatures .lbl{border-top:1px solid #9CA3AF;padding-top:6px;font-size:10.5px;color:#4B5563;margin-top:6px}
    .credit{text-align:center;font-size:8.5px;color:#C0C4CC;margin-top:26px}
    @media print{ body{background:#fff;padding:0} .doc{box-shadow:none} @page{size:A4;margin:14mm} }
  </style></head><body>
  <div class="doc">
    <div class="bandeau"><div style="background:#CE1126"></div><div style="background:#FCD116"></div><div style="background:#009460"></div></div>
    <div class="inner">
      <div class="header">
        <div class="ecole">
          ${settings.ecole_logo?`<img src="${settings.ecole_logo}">`:''}
          <div>
            <h1>${esc(settings.ecole_nom||'MY-ECOLE')}</h1>
            <p>${esc(settings.ecole_adresse||'')}</p>
            ${settings.ecole_telephone?`<p>Tél : ${esc(settings.ecole_telephone)}</p>`:''}
          </div>
        </div>
        <div style="text-align:right;font-size:10px;color:#6B7280">Édité le ${fmtDate(today())}<br>Par ${esc(currentUser?.full_name||'')}</div>
      </div>
      <div class="titre-doc">
        <h2>BALANCE GÉNÉRALE</h2>
        <p>Période du ${fmtDate(dateDebut)} au ${fmtDate(dateFin)}</p>
      </div>
      ${_syntheseImprimeeHtml(data.lignes)}
      <table>
        <thead><tr><th>Catégorie</th><th class="text-right">Solde initial</th><th class="text-right">Débit</th><th class="text-right">Crédit</th><th class="text-right">Solde final</th></tr></thead>
        <tbody>
          ${lignesHtml || `<tr><td colspan="5" style="text-align:center;color:#9CA3AF;padding:20px">Aucun mouvement sur cette période</td></tr>`}
          <tr class="totaux"><td>TOTAL</td>
            <td class="text-right mono">${Number(data.totaux.solde_initial).toLocaleString('fr-FR')}</td>
            <td class="text-right mono">${Number(data.totaux.debit_periode).toLocaleString('fr-FR')}</td>
            <td class="text-right mono">${Number(data.totaux.credit_periode).toLocaleString('fr-FR')}</td>
            <td class="text-right mono">${Number(data.totaux.solde_final).toLocaleString('fr-FR')}</td>
          </tr>
        </tbody>
      </table>
      <div class="signatures">
        <div class="col">
          ${settings.ecole_cachet?`<img class="cachet-img" src="${settings.ecole_cachet}">`:''}
          ${settings.signature_directeur?`<img class="signature-img" src="${settings.signature_directeur}">`:''}
          <div class="lbl">Le Directeur</div>
        </div>
        <div class="col"><div class="lbl">Le Comptable</div></div>
      </div>
      <div class="credit">Application développée par Actif System Groupe — Tél : 661-97-43-43</div>
    </div>
  </div>
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  finaliserDocumentPartageable(win, '.doc', {
    filenameBase: `balance_generale_${dateDebut}_${dateFin}`,
    sujetEmail: `Balance générale — du ${dateDebut} au ${dateFin}`,
    messageEmail: 'Veuillez trouver ci-joint la balance générale.',
  });
}
window.imprimerBalance = imprimerBalance;

/* ===================== RAPPROCHEMENT BANCAIRE ===================== */
let _dernierAnalyseRapprochement = null;

async function pageRapprochement() {
  const deb = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
  const fin = today();
  const etat = await apiEtatRapprochement(`date_debut=${deb}&date_fin=${fin}`);

  $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">🏦 Rapprochement bancaire</span>
        <button class="btn btn-outline btn-sm" onclick="pageComptabilite()">← Retour</button>
      </div>
      <div class="card-body">
        <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:20px">
          <div class="stat"><div class="stat-label">Opérations du mois</div><div class="stat-val" style="font-size:16px">${etat.total}</div></div>
          <div class="stat"><div class="stat-label">Rapprochées</div><div class="stat-val text-ok" style="font-size:16px">${etat.rapprochees}</div></div>
          <div class="stat"><div class="stat-label">Non rapprochées</div><div class="stat-val ${etat.non_rapprochees?'text-warn':''}" style="font-size:16px">${etat.non_rapprochees}</div></div>
        </div>

        <div class="form-section" style="border:1px dashed var(--c-line);border-radius:var(--r);padding:16px;margin-bottom:20px">
          <div class="form-section-title">Importer un relevé bancaire</div>
          <p class="text-muted" style="font-size:12px;margin:0 0 10px">Fichier CSV ou Excel avec 3 colonnes dans cet ordre : <strong>Date</strong>, <strong>Description</strong>, <strong>Montant</strong> (positif pour un crédit, négatif pour un débit).</p>
          <input type="file" id="fichier-releve" accept=".csv,.xlsx,.xls">
          <button class="btn btn-primary btn-sm" style="margin-top:10px" onclick="analyserReleve()">🔍 Analyser le relevé</button>
        </div>

        <div id="resultats-rapprochement"></div>

        <h4 style="margin:20px 0 10px">Opérations non rapprochées (${etat.non_rapprochees})</h4>
        <table class="table">
          <thead><tr><th>Date</th><th>Type</th><th>Catégorie</th><th>Montant</th><th></th></tr></thead>
          <tbody>
            ${etat.transactions.filter(t=>!t.rapproche).map(t => `
              <tr>
                <td>${fmtDate(t.date_op)}</td>
                <td><span class="badge ${t.type==='entree'?'bdg-ok':'bdg-err'}">${t.type==='entree'?'Recette':'Dépense'}</span></td>
                <td>${esc(t.categorie||'—')}</td>
                <td>${fmtMoney(t.montant)}</td>
                <td><button class="btn btn-outline btn-xs" onclick="confirmerRapprochementManuel('${escJs(t.id)}')">✔ Rapprocher manuellement</button></td>
              </tr>`).join('') || `<tr><td colspan="5">${emptyHtml('✅','Tout est déjà rapproché pour cette période')}</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>`;
}
window.pageRapprochement = pageRapprochement;

async function analyserReleve() {
  const fichier = $('#fichier-releve').files[0];
  if (!fichier) { toast('Choisissez un fichier', 'error'); return; }
  try {
    const d = await apiAnalyserRapprochement(fichier);
    _dernierAnalyseRapprochement = d;
    const zone = $('#resultats-rapprochement');
    zone.innerHTML = `
      <div class="alert alert-info">${d.nb_correspondances} correspondance(s) trouvée(s) sur ${d.nb_lignes_releve} ligne(s) du relevé.</div>
      <table class="table">
        <thead><tr><th>Ligne du relevé</th><th>Montant</th><th>Correspondance trouvée</th><th></th></tr></thead>
        <tbody>
          ${d.resultats.map((r, i) => `
            <tr>
              <td>${fmtDate(r.releve.date)} — ${esc(r.releve.description)}</td>
              <td>${fmtMoney(r.releve.montant)}</td>
              <td>${r.transaction_suggeree
                ? `${fmtDate(r.transaction_suggeree.date_op)} · ${esc(r.transaction_suggeree.categorie||'')} · ${fmtMoney(r.transaction_suggeree.montant)}`
                : '<span class="text-muted">Aucune correspondance dans le système</span>'}</td>
              <td>${r.transaction_suggeree
                ? `<button class="btn btn-ok btn-xs" onclick="confirmerRapprochementSuggere('${escJs(r.transaction_suggeree.id)}', this)">✔ Confirmer</button>`
                : ''}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  } catch(err) { toast(err.message, 'error'); }
}
window.analyserReleve = analyserReleve;

async function confirmerRapprochementSuggere(transactionId, btn) {
  try {
    await apiValiderRapprochement(transactionId);
    toast('Rapprochement confirmé', 'success');
    btn.closest('tr').style.opacity = '.4';
    btn.outerHTML = '✅ Rapproché';
  } catch(err) { toast(err.message, 'error'); }
}
window.confirmerRapprochementSuggere = confirmerRapprochementSuggere;

async function confirmerRapprochementManuel(transactionId) {
  if (!confirm('Marquer cette opération comme rapprochée avec le relevé bancaire ?')) return;
  try {
    await apiValiderRapprochement(transactionId);
    toast('Rapprochée', 'success');
    pageRapprochement();
  } catch(err) { toast(err.message, 'error'); }
}
window.confirmerRapprochementManuel = confirmerRapprochementManuel;

/* ===================== RELEVÉS ===================== */
async function pageReleves() {
  $('#content').innerHTML = loadingHtml;
  const eleves = await apiGetEleves();
  const anneeCourante = new Date().getFullYear();

  $('#content').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">📑 Relevés</span>
      <button class="btn btn-outline btn-sm" onclick="pageComptabilite()">← Retour</button>
    </div>
    <div class="alert alert-info">💡 Générez un relevé pour un ou plusieurs élèves, une transaction précise, ou un relevé général — sur n'importe quelle période. Le document généré peut être imprimé, téléchargé en PDF, ou partagé par WhatsApp / e-mail.</div>

    <div class="fg"><label>Type de relevé</label>
      <select id="rel-type" onchange="majFormReleve()">
        <option value="eleves">Relevé d'un ou plusieurs élèves</option>
        <option value="transaction">Détail d'une transaction précise</option>
        <option value="general">Relevé général (toutes les transactions)</option>
      </select>
    </div>

    <div id="rel-bloc-eleves" class="fg">
      <label>Élève(s)*</label>
      <input type="text" id="rel-eleves-recherche" placeholder="Rechercher un élève par nom ou matricule…" oninput="filtrerRelEleves()">
      <select id="rel-eleves" multiple size="8" style="margin-top:6px">
        ${eleves.map(e => `<option value="${esc(e.id)}" data-txt="${esc((e.prenom+' '+e.nom+' '+(e.matricule||'')).toLowerCase())}">${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')} (${esc(e.matricule||'—')})</option>`).join('')}
      </select>
      <div class="text-muted" style="font-size:11.5px;margin-top:4px">Maintenez Ctrl (ou Cmd sur Mac) pour sélectionner plusieurs élèves.</div>
    </div>

    <div id="rel-bloc-transaction" class="fg" style="display:none">
      <label>Transaction*</label>
      <input type="text" id="rel-trans-recherche" placeholder="Rechercher par description, référence, élève…" oninput="rechercherTransactionReleve()">
      <div id="rel-trans-resultats" class="tbl-wrap" style="max-height:260px;overflow-y:auto;margin-top:6px"></div>
      <input type="hidden" id="rel-trans-id">
      <div id="rel-trans-choisie" class="alert alert-info" style="display:none;margin-top:8px"></div>
    </div>

    <div id="rel-bloc-periode">
      <div class="fg"><label>Période</label>
        <select id="rel-periode" onchange="majPeriodeReleve()">
          <option value="mois" selected>Un mois précis</option>
          <option value="annee">Une année précise</option>
          <option value="libre">Dates personnalisées</option>
          <option value="tout">Toute la période (depuis toujours)</option>
        </select>
      </div>
      <div id="rel-periode-mois" class="form-2">
        <div class="fg"><label>Mois</label><select id="rel-mois">${['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'].map((m,i)=>`<option value="${i+1}" ${i+1===new Date().getMonth()+1?'selected':''}>${m}</option>`).join('')}</select></div>
        <div class="fg"><label>Année</label><input type="number" id="rel-annee-mois" value="${anneeCourante}"></div>
      </div>
      <div id="rel-periode-annee" class="fg" style="display:none">
        <label>Année scolaire</label>
        <select id="rel-annee">${anneesScolairesOptions()}</select>
        <div class="text-muted" style="font-size:11.5px;margin-top:4px">💡 Couvre toute l'année scolaire (ex : de septembre 2026 à juillet 2027), y compris les tranches à cheval sur deux années civiles.</div>
      </div>
      <div id="rel-periode-libre" class="form-2" style="display:none">
        <div class="fg"><label>Du</label><input type="date" id="rel-date-debut"></div>
        <div class="fg"><label>Au</label><input type="date" id="rel-date-fin" value="${today()}"></div>
      </div>
    </div>

    <div class="modal-footer" style="justify-content:flex-start">
      <button class="btn btn-primary" onclick="genererReleve()">📑 Générer le relevé</button>
    </div>
  </div>`;
  majFormReleve();
}
window.pageReleves = pageReleves;

function majFormReleve() {
  const type = $('#rel-type').value;
  $('#rel-bloc-eleves').style.display = type === 'eleves' ? '' : 'none';
  $('#rel-bloc-transaction').style.display = type === 'transaction' ? '' : 'none';
  $('#rel-bloc-periode').style.display = type === 'transaction' ? 'none' : '';
}
window.majFormReleve = majFormReleve;

function majPeriodeReleve() {
  const p = $('#rel-periode').value;
  $('#rel-periode-mois').style.display = p === 'mois' ? 'flex' : 'none';
  $('#rel-periode-annee').style.display = p === 'annee' ? '' : 'none';
  $('#rel-periode-libre').style.display = p === 'libre' ? 'flex' : 'none';
}
window.majPeriodeReleve = majPeriodeReleve;

function filtrerRelEleves() {
  const q = $('#rel-eleves-recherche').value.toLowerCase();
  $$('#rel-eleves option').forEach(o => { o.style.display = o.dataset.txt.includes(q) ? '' : 'none'; });
}
window.filtrerRelEleves = filtrerRelEleves;

let _relTransactionsCache = null;
async function rechercherTransactionReleve() {
  const q = $('#rel-trans-recherche').value.toLowerCase().trim();
  if (q.length < 2) { $('#rel-trans-resultats').innerHTML = ''; return; }
  if (!_relTransactionsCache) _relTransactionsCache = await apiGetTransactions('');
  const resultats = _relTransactionsCache.filter(t =>
    `${t.description||''} ${t.reference||''} ${t.categorie||''}`.toLowerCase().includes(q)
  ).slice(0, 30);
  $('#rel-trans-resultats').innerHTML = resultats.length ? `<table><tbody>
    ${resultats.map(t => `<tr style="cursor:pointer" onclick="choisirTransactionReleve('${escJs(t.id)}','${escJs(t.description||'')}','${escJs(fmtDate(t.date_op))}','${escJs(fmtMoney(t.montant))}')">
      <td>${fmtDate(t.date_op)}</td>
      <td>${esc(t.description||'—')}</td>
      <td class="mono text-right ${t.type==='entree'?'text-ok':'text-err'}">${fmtMoney(t.montant)}</td>
    </tr>`).join('')}
  </tbody></table>` : `<div class="text-muted" style="padding:8px;font-size:12.5px">Aucune correspondance</div>`;
}
window.rechercherTransactionReleve = rechercherTransactionReleve;

function choisirTransactionReleve(id, description, date, montant) {
  $('#rel-trans-id').value = id;
  $('#rel-trans-choisie').style.display = '';
  $('#rel-trans-choisie').innerHTML = `Transaction sélectionnée : <strong>${esc(description)}</strong> — ${esc(date)} — ${esc(montant)}`;
  $('#rel-trans-resultats').innerHTML = '';
  $('#rel-trans-recherche').value = '';
}
window.choisirTransactionReleve = choisirTransactionReleve;

function anneesScolairesOptions() {
  const maintenant = new Date();
  const anneeDebutCourante = maintenant.getMonth() >= 8 ? maintenant.getFullYear() : maintenant.getFullYear() - 1; // rentrée en septembre (mois index 8)
  const options = [];
  for (let decalage = 1; decalage >= -2; decalage--) {
    const debut = anneeDebutCourante + decalage;
    options.push(`${debut}-${debut+1}`);
  }
  return options.map(a => `<option value="${a}" ${a === `${anneeDebutCourante}-${anneeDebutCourante+1}` ? 'selected' : ''}>${a}</option>`).join('');
}

function _periodeReleveActuelle() {
  const p = $('#rel-periode')?.value;
  if (!p || p === 'tout') return { date_debut: '', date_fin: '', annee_scolaire: '' };
  if (p === 'mois') {
    const mois = parseInt($('#rel-mois').value), annee = parseInt($('#rel-annee-mois').value);
    const dernierJour = new Date(annee, mois, 0).getDate();
    return { date_debut: `${annee}-${String(mois).padStart(2,'0')}-01`, date_fin: `${annee}-${String(mois).padStart(2,'0')}-${dernierJour}`, annee_scolaire: '' };
  }
  if (p === 'annee') {
    const anneeScolaire = $('#rel-annee').value; // ex: "2026-2027"
    const debut = parseInt(anneeScolaire.split('-')[0]);
    // Date range de secours pour le relevé général (qui filtre par date réelle de
    // transaction, sans notion d'année scolaire) : du 1er septembre au 31 août suivant.
    return { date_debut: `${debut}-09-01`, date_fin: `${debut+1}-08-31`, annee_scolaire: anneeScolaire };
  }
  return { date_debut: $('#rel-date-debut').value, date_fin: $('#rel-date-fin').value, annee_scolaire: '' };
}

async function genererReleve() {
  const type = $('#rel-type').value;
  const settings = await apiGetSettings();

  if (type === 'transaction') {
    const tid = $('#rel-trans-id').value;
    if (!tid) { toast('Sélectionnez une transaction dans la liste', 'error'); return; }
    const data = await apiGetReleve({ transaction_id: tid });
    imprimerReleveTransaction(data.transaction, settings);
    return;
  }

  const { date_debut, date_fin, annee_scolaire } = _periodeReleveActuelle();

  if (type === 'eleves') {
    const ids = $$('#rel-eleves option:checked').map(o => o.value);
    if (!ids.length) { toast('Sélectionnez au moins un élève', 'error'); return; }
    const params = { eleve_ids: ids.join(',') };
    // Priorité à l'année scolaire (couvre les tranches à cheval sur deux années
    // civiles) — sinon on retombe sur une plage de dates classique.
    if (annee_scolaire) params.annee_scolaire = annee_scolaire;
    else { if (date_debut) params.date_debut = date_debut; if (date_fin) params.date_fin = date_fin; }
    const data = await apiGetReleve(params);
    imprimerReleveEleves(data, settings);
    return;
  }

  // Général
  const params = {};
  if (date_debut) params.date_debut = date_debut;
  if (date_fin) params.date_fin = date_fin;
  const data = await apiGetReleve(params);
  imprimerReleveGeneral(data, settings);
}
window.genererReleve = genererReleve;

function _enteteReleveHtml(settings, titre, sousTitre) {
  return `
    <div class="bandeau"><div style="background:#CE1126"></div><div style="background:#FCD116"></div><div style="background:#009460"></div></div>
    <div class="inner">
      <div class="header">
        <div class="ecole">
          ${settings.ecole_logo?`<img src="${settings.ecole_logo}">`:''}
          <div>
            <h1>${esc(settings.ecole_nom||'MY-ECOLE')}</h1>
            <p>${esc(settings.ecole_adresse||'')}</p>
            ${settings.ecole_telephone?`<p>Tél : ${esc(settings.ecole_telephone)}</p>`:''}
          </div>
        </div>
        <div style="text-align:right;font-size:10px;color:#6B7280">Édité le ${fmtDate(today())}<br>Par ${esc(currentUser?.full_name||'')}</div>
      </div>
      <div class="titre-doc"><h2>${esc(titre)}</h2><p>${esc(sousTitre)}</p></div>`;
}

const RELEVE_DOC_STYLE = `
  *{box-sizing:border-box}
  body{font-family:Arial,sans-serif;font-size:11.5px;color:#1F2937;margin:0;padding:26px;background:#F3F4F6}
  .doc{max-width:1000px;margin:0 auto;background:#fff;border:1px solid #D1D5DB;border-radius:4px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
  .bandeau{height:6px;display:flex} .bandeau div{flex:1}
  .inner{padding:28px 32px}
  .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111827;padding-bottom:14px;margin-bottom:16px}
  .header .ecole{display:flex;gap:12px;align-items:center}
  .header img{max-height:46px}
  .header h1{font-size:14px;margin:0 0 2px;color:#111827;font-weight:700}
  .header p{margin:1px 0;font-size:10px;color:#6B7280}
  .titre-doc{text-align:center;margin:6px 0 18px}
  .titre-doc h2{font-size:17px;letter-spacing:2px;color:#111827;margin:0}
  .titre-doc p{font-size:11px;color:#6B7280;margin:3px 0 0}
  table{width:100%;border-collapse:collapse;font-size:10.5px;margin-bottom:18px}
  th{background:#111827;color:#fff;padding:7px 8px;text-align:left;font-size:9.5px;text-transform:uppercase}
  th.text-right{text-align:right}
  td{padding:6px 8px;border-bottom:1px solid #F0F1F3}
  .totaux td{background:#EEF2FF;font-weight:800;border-top:2px solid #111827;border-bottom:none}
  .bloc-eleve{margin-bottom:26px;page-break-inside:avoid}
  .bloc-eleve h3{font-size:12.5px;background:#F3F4F6;padding:8px 10px;border-radius:4px;margin:0 0 8px}
  .signatures{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:34px}
  .signatures .col{text-align:center}
  .signatures .cachet-img{max-height:50px;max-width:100px;display:block;margin:0 auto 2px}
  .signatures .signature-img{max-height:32px;max-width:100px;display:block;margin:0 auto 2px}
  .signatures .lbl{border-top:1px solid #9CA3AF;padding-top:6px;font-size:10.5px;color:#4B5563;margin-top:6px}
  .credit{text-align:center;font-size:8.5px;color:#C0C4CC;margin-top:26px}
  @media print{ body{background:#fff;padding:0} .doc{box-shadow:none} @page{size:A4;margin:14mm} }`;

function _piedSignaturesHtml(settings) {
  return `
      <div class="signatures">
        <div class="col">
          ${settings.ecole_cachet?`<img class="cachet-img" src="${settings.ecole_cachet}">`:''}
          ${settings.signature_directeur?`<img class="signature-img" src="${settings.signature_directeur}">`:''}
          <div class="lbl">Le Directeur</div>
        </div>
        <div class="col"><div class="lbl">Le Comptable</div></div>
      </div>
      <div class="credit">Application développée par Actif System Groupe — Tél : 661-97-43-43</div>
    </div>`;
}

function _libellePeriode(dateDebut, dateFin, anneeScolaire) {
  if (anneeScolaire) return `Année scolaire ${anneeScolaire}`;
  if (!dateDebut && !dateFin) return 'Toute la période';
  return `Période du ${fmtDate(dateDebut)} au ${fmtDate(dateFin)}`;
}

function imprimerReleveEleves(data, settings) {
  const blocs = data.resultats.map(r => {
    const e = r.eleve;
    const lignesPaiements = r.paiements.map(p => `<tr>
      <td>${fmtDate(p.date_echeance)}</td>
      <td>${esc(p.libelle)}</td>
      <td class="text-right mono">${Number(p.montant_du).toLocaleString('fr-FR')}</td>
      <td class="text-right mono">${Number(p.montant_paye).toLocaleString('fr-FR')}</td>
      <td class="text-right mono ${p.montant_du-p.montant_paye>0?'':''}">${Number(p.montant_du-p.montant_paye).toLocaleString('fr-FR')}</td>
      <td>${p.statut==='paye'?'Payé':p.statut==='partiel'?'Partiel':p.statut==='en_retard'?'En retard':'À payer'}</td>
    </tr>`).join('');
    return `<div class="bloc-eleve">
      <h3>🎓 ${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')} (Matricule : ${esc(e.matricule||'—')})</h3>
      <table>
        <thead><tr><th>Échéance</th><th>Libellé</th><th class="text-right">Dû</th><th class="text-right">Payé</th><th class="text-right">Restant</th><th>Statut</th></tr></thead>
        <tbody>${lignesPaiements || `<tr><td colspan="6" style="text-align:center;color:#9CA3AF;padding:14px">Aucun paiement sur cette période</td></tr>`}
        <tr class="totaux"><td colspan="2">TOTAL</td>
          <td class="text-right mono">${Number(r.totaux.total_du).toLocaleString('fr-FR')}</td>
          <td class="text-right mono">${Number(r.totaux.total_paye).toLocaleString('fr-FR')}</td>
          <td class="text-right mono">${Number(r.totaux.solde_restant).toLocaleString('fr-FR')}</td>
          <td></td>
        </tr></tbody>
      </table>
    </div>`;
  }).join('');

  const nbEleves = data.resultats.length;
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Relevé élève(s)</title>
  <style>${RELEVE_DOC_STYLE}</style></head><body><div class="doc">
    ${_enteteReleveHtml(settings, 'RELEVÉ DE COMPTE', `${nbEleves} élève${nbEleves>1?'s':''} — ${_libellePeriode(data.date_debut, data.date_fin, data.annee_scolaire)}`)}
    ${blocs}
    ${_piedSignaturesHtml(settings)}
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  const nomEleve = nbEleves === 1 ? `${data.resultats[0].eleve.prenom}_${data.resultats[0].eleve.nom}` : `${nbEleves}_eleves`;
  finaliserDocumentPartageable(win, '.doc', {
    filenameBase: `releve_${nomEleve}`,
    sujetEmail: `Relevé de compte — ${nomEleve.replace(/_/g,' ')}`,
    messageEmail: `Veuillez trouver ci-joint le relevé de compte scolaire.`,
    destinataireDefaut: nbEleves === 1 ? (data.resultats[0].eleve.email_parent || '') : '',
  });
}
window.imprimerReleveEleves = imprimerReleveEleves;

function imprimerReleveTransaction(t, settings) {
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Détail transaction</title>
  <style>${RELEVE_DOC_STYLE}</style></head><body><div class="doc">
    ${_enteteReleveHtml(settings, 'DÉTAIL DE TRANSACTION', `Référence : ${t.reference||t.id}`)}
    <table>
      <tbody>
        <tr><td style="font-weight:700;width:200px">Date</td><td>${fmtDate(t.date_op)}</td></tr>
        <tr><td style="font-weight:700">Type</td><td>${t.type==='entree'?'Recette (entrée)':'Dépense (sortie)'}</td></tr>
        <tr><td style="font-weight:700">Description</td><td>${esc(t.description||'—')}</td></tr>
        <tr><td style="font-weight:700">Catégorie</td><td>${esc(t.categorie||'—')}</td></tr>
        <tr><td style="font-weight:700">Montant</td><td class="mono" style="font-size:15px;font-weight:800">${Number(t.montant).toLocaleString('fr-FR')} GNF</td></tr>
        <tr><td style="font-weight:700">Moyen de paiement</td><td>${esc(t.moyen_paiement||'—')}</td></tr>
        ${t.eleve ? `<tr><td style="font-weight:700">Élève concerné</td><td>${esc(t.eleve.prenom)} ${esc(t.eleve.nom)} — ${esc(t.eleve.classe||'')} (${esc(t.eleve.matricule||'')})</td></tr>` : ''}
        ${t.fournisseur_nom ? `<tr><td style="font-weight:700">Fournisseur</td><td>${esc(t.fournisseur_nom)}</td></tr>` : ''}
        <tr><td style="font-weight:700">Statut</td><td>${esc(t.statut_validation)}</td></tr>
      </tbody>
    </table>
    ${_piedSignaturesHtml(settings)}
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  finaliserDocumentPartageable(win, '.doc', {
    filenameBase: `transaction_${t.reference||t.id}`,
    sujetEmail: `Détail de transaction — ${t.reference||t.id}`,
    messageEmail: 'Veuillez trouver ci-joint le détail de la transaction demandée.',
  });
}
window.imprimerReleveTransaction = imprimerReleveTransaction;

function imprimerReleveGeneral(data, settings) {
  const lignes = data.transactions.map(t => `<tr>
    <td>${fmtDate(t.date_op)}</td>
    <td>${esc(t.description||'—')}${t.eleve_nom?` — ${esc(t.eleve_nom)}`:''}</td>
    <td>${esc(t.categorie||'—')}</td>
    <td class="text-right mono">${t.type==='entree'?Number(t.montant).toLocaleString('fr-FR'):''}</td>
    <td class="text-right mono">${t.type==='sortie'?Number(t.montant).toLocaleString('fr-FR'):''}</td>
  </tr>`).join('');

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Relevé général</title>
  <style>${RELEVE_DOC_STYLE}</style></head><body><div class="doc">
    ${_enteteReleveHtml(settings, 'RELEVÉ GÉNÉRAL', _libellePeriode(data.date_debut, data.date_fin))}
    <table>
      <thead><tr><th>Date</th><th>Description</th><th>Catégorie</th><th class="text-right">Recette</th><th class="text-right">Dépense</th></tr></thead>
      <tbody>${lignes || `<tr><td colspan="5" style="text-align:center;color:#9CA3AF;padding:20px">Aucun mouvement sur cette période</td></tr>`}
      <tr class="totaux"><td colspan="3">TOTAL</td>
        <td class="text-right mono">${Number(data.totaux.entrees).toLocaleString('fr-FR')}</td>
        <td class="text-right mono">${Number(data.totaux.sorties).toLocaleString('fr-FR')}</td>
      </tr></tbody>
    </table>
    ${_piedSignaturesHtml(settings)}
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  finaliserDocumentPartageable(win, '.doc', {
    filenameBase: `releve_general_${data.date_debut||'debut'}_${data.date_fin||'fin'}`,
    sujetEmail: 'Relevé général des transactions',
    messageEmail: 'Veuillez trouver ci-joint le relevé général des transactions.',
  });
}
window.imprimerReleveGeneral = imprimerReleveGeneral;
