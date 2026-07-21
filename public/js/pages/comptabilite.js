/* ===================== COMPTABILITÉ ===================== */
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
      $('#tb-compta').innerHTML = data.length ? data.map(t => `<tr>
        <td>${fmtDate(t.date_op)}</td>
        <td><span class="badge ${t.type==='entree'?'bdg-ok':'bdg-err'}">${t.type==='entree'?'➕ Recette':'➖ Dépense'}</span></td>
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
          <button class="btn btn-ok btn-sm" onclick="modalTransaction('entree')">+ Recette</button>
          <button class="btn btn-danger btn-sm" onclick="modalTransaction('sortie')">− Dépense</button>
        </div>
      </div>
      <div class="filters">
        <div class="fg"><label>Du</label><input type="date" id="f-tdeb" value="${new Date(new Date().getFullYear(),0,1).toISOString().split('T')[0]}"></div>
        <div class="fg"><label>Au</label><input type="date" id="f-tfin" value="${today()}"></div>
        <div class="fg"><label>Type</label><select id="f-ttype"><option value="">Tous</option><option value="entree">Recettes</option><option value="sortie">Dépenses</option></select></div>
        <div class="fg grow"><label>Recherche</label><input id="q-t" placeholder="Description, référence…"></div>
        <button class="btn btn-outline btn-sm" style="align-self:flex-end" onclick="reloadTransactions()">🔍</button>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-compta"><th>Date</th><th>Type</th><th>Description</th><th>Catégorie</th><th>Moyen</th><th class="text-right">Montant</th><th>Statut</th><th>Créé par</th><th>Lié / Actions</th></tr></thead>
        <tbody id="tb-compta"></tbody>
      </table></div>
    </div>`;

    render(transactions);

    makeSortableTable('#th-compta', () => curr, render,
      ['date_op', 'type', 'description', 'categorie', 'moyen_paiement', 'montant', 'statut_validation', 'cree_par_nom', null]);

    window.reloadTransactions = async () => {
      const deb = $('#f-tdeb').value;
      const fin = $('#f-tfin').value;
      const type = $('#f-ttype').value;
      const q = $('#q-t').value;
      let qs = [];
      if (deb) qs.push(`date_debut=${deb}`);
      if (fin) qs.push(`date_fin=${fin}`);
      if (type) qs.push(`type=${type}`);
      if (q) qs.push(`q=${encodeURIComponent(q)}`);
      try { curr = await apiGetTransactions(qs.join('&')); render(curr); }
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
        <div class="fg"><label>Catégorie</label><select name="categorie" id="tr-cat" onchange="updateCatOptions()">
          ${(typeDefaut==='entree'?CAT_ENTREE:CAT_SORTIE).map(c=>`<option>${esc(c)}</option>`).join('')}
        </select></div>
        <div class="fg"><label>Montant (GNF)*</label><input type="number" name="montant" required min="1" step="1"></div>
      </div>
      <div class="fg" id="tr-benef-wrap" style="display:${typeDefaut==='sortie'?'':'none'}">
        <label id="tr-benef-label">Bénéficiaire / Prestataire de service</label>
        <div id="tr-benef-field"><input name="beneficiaire" placeholder="Nom de la personne ou de l'entreprise payée"></div>
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
    } else if (benefField.querySelector('select')) {
      $('#tr-benef-label').textContent = 'Bénéficiaire / Prestataire de service';
      benefField.innerHTML = `<input name="beneficiaire" placeholder="Nom de la personne ou de l'entreprise payée">`;
    }
  };
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
            <h1>${esc(settings.ecole_nom||'Groupe Scolaire Elhadji Mountaga Djély')}</h1>
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
  win.focus();
  setTimeout(() => win.print(), 700);
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
