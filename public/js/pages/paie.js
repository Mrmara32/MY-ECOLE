/* ===================== PAIE & BULLETINS DE SALAIRE ===================== */
async function pagePaieList(mois = null) {
  mois = mois || moisCourant();
  window._paieMoisActuel = mois;
  $('#content').innerHTML = loadingHtml;
  try {
    const [data, validation] = await Promise.all([
      apiListePaie(mois), apiGetValidationPaie(mois).catch(() => null)
    ]);
    window._paieValidationActuelle = validation;

    const render = list => {
      $('#tb-paie').innerHTML = list.length ? list.map(p => `<tr>
        <td>${elevePhoto({photo_url:p.photo_url, prenom:p.prenom, nom:p.nom}, 32)}</td>
        <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(p.poste||'')}</span></td>
        <td><span class="badge ${p.type_remuneration==='horaire'?'bdg-info':'bdg-gray'}">${p.type_remuneration==='horaire'?'Horaire':'Mensuel'}</span></td>
        <td class="text-center">${p.type_remuneration==='horaire' ? `${p.heures||0}h × ${fmtMoney(p.taux_horaire||0)}${p.source_heures==='seances'?' <span class="badge bdg-ok" style="font-size:9px" title="Heures issues des séances validées">séances</span>':(p.heures>0?' <span class="badge bdg-gray" style="font-size:9px" title="Saisie manuelle historique">manuel</span>':'')}` : '—'}</td>
        <td class="text-right">${p.prime_revision>0 ? `<span class="badge bdg-ok">+${fmtMoney(p.prime_revision)}</span>` : '—'}</td>
        <td class="mono text-right fw-600">${fmtMoney(p.salaire_base + (p.prime_revision||0))}</td>
        <td><span class="badge ${p.deja_paye?'bdg-ok':'bdg-warn'}">${p.deja_paye?'✔ Payé':'À payer'}</span></td>
        <td><div class="td-actions">
          ${['admin','comptable'].includes(currentUser.role)?`<button class="btn btn-outline btn-xs" onclick="modalAccorderAvance('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}')">💵 Avance</button>`:''}
          ${p.deja_paye
            ? `<button class="btn btn-outline btn-xs" onclick="imprimerBulletinSalaire('${escJs(p.bulletin_id)}')">🖨 Bulletin</button>`
            : `<button class="btn btn-ok btn-xs" onclick="modalPayerSalaire('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}')">💰 Payer</button>`}
        </div></td>
      </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('👨‍🏫','Aucun personnel')}</td></tr>`;
    };

    const masseTotal = data.masse_salariale_totale;
    const dejaVerse = data.personnel.filter(p=>p.deja_paye).reduce((s,p) => s + p.salaire_base + (p.prime_revision||0), 0);

    $('#content').innerHTML = `
    ${renderBandeauValidation(validation, mois)}
    <div class="stats-grid" style="grid-template-columns:repeat(3,1fr)">
      <div class="stat"><div class="stat-label">Masse salariale du mois</div><div class="stat-val" style="font-size:18px">${fmtMoney(masseTotal)}</div></div>
      <div class="stat"><div class="stat-label">Déjà versé</div><div class="stat-val text-ok" style="font-size:18px">${fmtMoney(dejaVerse)}</div></div>
      <div class="stat"><div class="stat-label">Restant à verser</div><div class="stat-val text-err" style="font-size:18px">${fmtMoney(masseTotal-dejaVerse)}</div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">💰 Paie du mois</span>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="pageAvances()">💵 Avances sur salaire</button>
          <button class="btn btn-outline btn-sm" onclick="modalTypesPrimes()">🏷️ Types de primes</button>
          <input type="month" id="f-paiemois" value="${mois}" onchange="pagePaieList(this.value)">
        </div>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-paie" placeholder="Nom, prénom…"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-paie"><th>Photo</th><th>Nom</th><th>Type</th><th>Détail</th><th class="text-right">Prime révision</th><th class="text-right">Montant</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-paie"></tbody>
      </table></div>
    </div>`;

    let curr = data.personnel;
    render(curr);
    $('#q-paie').addEventListener('input', () => {
      const q = $('#q-paie').value.toLowerCase();
      curr = data.personnel.filter(p => `${p.nom} ${p.prenom}`.toLowerCase().includes(q));
      render(curr);
    });
    makeSortableTable('#th-paie', () => curr, render,
      [null, row => `${row.prenom} ${row.nom}`, 'type_remuneration', null, 'prime_revision', row => row.salaire_base+(row.prime_revision||0), 'deja_paye', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

/* ── Bandeau de validation de la masse salariale (comptable → directeur → admin) ── */
function renderBandeauValidation(validation, mois) {
  const role = currentUser.role;
  if (!validation) {
    if (role === 'comptable') {
      return `<div class="alert alert-warn mb-4">
        ⚠️ La masse salariale de <strong>${mois}</strong> n'a pas encore été soumise pour validation.
        Vous devez la soumettre avant de pouvoir payer les salaires de ce mois.
        <button class="btn btn-primary btn-xs" style="margin-left:10px" onclick="soumettreMasseSalariale('${mois}')">📤 Soumettre pour validation</button>
      </div>`;
    }
    return '';
  }
  if (validation.statut === 'attente_directeur') {
    if (role === 'directeur' || role === 'admin') {
      return `<div class="alert alert-warn mb-4">
        ⏳ Masse salariale de <strong>${mois}</strong> (${fmtMoney(validation.masse_salariale_totale)}) soumise par
        <strong>${esc(validation.soumis_par_nom||'—')}</strong> — en attente de votre pré-validation.
        <button class="btn btn-ok btn-xs" style="margin-left:10px" onclick="validerMasseSalarialeDirecteur('${validation.id}')">✔ Pré-valider</button>
        <button class="btn btn-danger btn-xs" onclick="rejeterMasseSalariale('${validation.id}','directeur')">✕ Rejeter</button>
      </div>`;
    }
    return `<div class="alert alert-warn mb-4">⏳ Masse salariale en attente de pré-validation par le directeur.</div>`;
  }
  if (validation.statut === 'attente_admin') {
    if (role === 'admin') {
      return `<div class="alert alert-warn mb-4">
        ⏳ Masse salariale de <strong>${mois}</strong> (${fmtMoney(validation.masse_salariale_totale)}) pré-validée par le directeur
        (<strong>${esc(validation.valide_directeur_par_nom||'—')}</strong>) — en attente de votre approbation finale pour autoriser le décaissement.
        <button class="btn btn-ok btn-xs" style="margin-left:10px" onclick="validerMasseSalarialeAdmin('${validation.id}')">✔ Approuver définitivement</button>
        <button class="btn btn-danger btn-xs" onclick="rejeterMasseSalariale('${validation.id}','admin')">✕ Rejeter</button>
      </div>`;
    }
    return `<div class="alert alert-warn mb-4">⏳ Masse salariale pré-validée par le directeur, en attente d'approbation finale de l'administrateur.</div>`;
  }
  if (validation.statut === 'approuve') {
    return `<div class="alert alert-ok mb-4">✅ Masse salariale de <strong>${mois}</strong> approuvée par l'administrateur — le paiement des salaires est autorisé.</div>`;
  }
  if (validation.statut === 'rejete') {
    const peutResoumetre = role === 'comptable' || role === 'admin' || role === 'directeur';
    return `<div class="alert alert-danger mb-4">
      ❌ Soumission rejetée${validation.motif_rejet?` : ${esc(validation.motif_rejet)}`:''}.
      ${peutResoumetre ? `<button class="btn btn-outline btn-xs" style="margin-left:10px" onclick="soumettreMasseSalariale('${mois}')">📤 Soumettre à nouveau</button>` : ''}
    </div>`;
  }
  return '';
}

async function soumettreMasseSalariale(mois) {
  if (!confirm(`Soumettre la masse salariale de ${mois} pour validation ?`)) return;
  try { await apiSoumettreValidation({ mois }); toast('Soumis pour validation','success'); pagePaieList(mois); }
  catch(e) { toast(e.message,'error'); }
}
async function validerMasseSalarialeDirecteur(id) {
  if (!confirm('Confirmer la pré-validation de cette masse salariale ?')) return;
  try { await apiValiderDirecteur(id); toast('Pré-validé ✅','success'); pagePaieList(window._paieMoisActuel); }
  catch(e) { toast(e.message,'error'); }
}
async function validerMasseSalarialeAdmin(id) {
  if (!confirm('Confirmer l\'approbation finale ? Ceci autorisera le décaissement des salaires.')) return;
  try { await apiValiderAdminPaie(id); toast('Approuvé définitivement ✅','success'); pagePaieList(window._paieMoisActuel); }
  catch(e) { toast(e.message,'error'); }
}
async function rejeterMasseSalariale(id, niveau) {
  const motif = prompt('Motif du rejet :', '');
  if (motif === null) return;
  try {
    if (niveau === 'directeur') await apiValiderDirecteur(id, { rejeter: true, motif });
    else await apiValiderAdminPaie(id, { rejeter: true, motif });
    toast('Rejeté','warning'); pagePaieList(window._paieMoisActuel);
  } catch(e) { toast(e.message,'error'); }
}
window.soumettreMasseSalariale = soumettreMasseSalariale;
window.validerMasseSalarialeDirecteur = validerMasseSalarialeDirecteur;
window.validerMasseSalarialeAdmin = validerMasseSalarialeAdmin;
window.rejeterMasseSalariale = rejeterMasseSalariale;

/* ── Paiement d'un salaire (calcul automatique) ── */
async function modalPayerSalaire(personnelId, nom) {
  const mois = window._paieMoisActuel || moisCourant();
  const calc = await apiCalculPaie(personnelId, mois);
  const typesPrimes = await apiGetTypesPrimes();

  openModal(`💰 Payer le salaire — ${nom}`, `
    <div class="alert alert-info">
      Mois : <strong>${mois}</strong><br>
      ${calc.type_remuneration==='horaire'
        ? `Rémunération horaire : <strong>${calc.heures}h</strong> × <strong>${fmtMoney(calc.taux_horaire)}</strong> = <strong>${fmtMoney(calc.salaire_base)}</strong>`
        : `Salaire mensuel fixe : <strong>${fmtMoney(calc.salaire_base)}</strong>`}
      ${calc.prime_revision>0 ? `<br>🎓 Prime cours de révision (${calc.heures_revision}h) : <strong class="text-ok">+${fmtMoney(calc.prime_revision)}</strong>` : ''}
      ${calc.avance_en_attente ? `<br>💵 Avance sur salaire à déduire : <strong class="text-err">−${fmtMoney(calc.avance_en_attente.montant)}</strong>` : ''}
    </div>
    <form id="f-paysal" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Prime additionnelle (GNF)</label><input type="number" name="primes" value="0" min="0"></div>
        <div class="fg"><label>Déductions (GNF)</label><input type="number" name="deductions" value="0" min="0"></div>
      </div>
      <div class="fg"><label>Détail de la prime additionnelle</label>
        <select name="primes_detail">
          <option value="">— Aucune —</option>
          ${typesPrimes.map(t=>`<option value="${esc(t.nom)}">${esc(t.nom)}</option>`).join('')}
        </select>
        <div class="text-muted mt-1" style="font-size:11px">Besoin d'un nouveau type ? <a href="#" onclick="event.preventDefault();modalTypesPrimes()">Gérer les types de primes</a></div>
      </div>
      <div class="fg"><label>Date de paiement</label><input type="date" name="date_paiement" value="${today()}"></div>
      <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
      <div id="net-preview" class="alert alert-ok" style="font-size:16px;font-weight:700"></div>
      <input type="hidden" name="personnel_id" value="${esc(personnelId)}">
      <input type="hidden" name="mois" value="${esc(mois)}">
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">💾 Générer et payer</button>
      </div>
    </form>`, { narrow: true });

  const avanceDeduite = calc.avance_en_attente ? calc.avance_en_attente.montant : 0;
  const updatePreview = () => {
    const primes = parseFloat($('input[name=primes]').value) || 0;
    const deductions = parseFloat($('input[name=deductions]').value) || 0;
    const net = calc.salaire_base + calc.prime_revision + primes - deductions - avanceDeduite;
    $('#net-preview').textContent = `Montant net à payer : ${fmtMoney(net)}`;
  };
  updatePreview();
  $('input[name=primes]').addEventListener('input', updatePreview);
  $('input[name=deductions]').addEventListener('input', updatePreview);

  $('#f-paysal').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.primes = parseFloat(fd.primes) || 0;
    fd.deductions = parseFloat(fd.deductions) || 0;
    try {
      const bulletin = await apiGenererBulletin(fd);
      toast('Salaire payé ✅ Bulletin généré','success');
      closeModal();
      imprimerBulletinSalaire(bulletin.id);
      pagePaieList(mois);
    } catch(err) { toast(err.message,'error'); }
  };
}

/* ── Avances sur salaire ── */
async function modalAccorderAvance(personnelId, nom) {
  const plafondData = await apiPlafondAvance(personnelId);
  openModal(`💵 Accorder une avance — ${nom}`, `
    <div class="alert alert-info">
      Salaire de référence : <strong>${fmtMoney(plafondData.salaire_reference||0)}</strong><br>
      Plafond autorisé (40%) : <strong>${fmtMoney(plafondData.plafond||0)}</strong><br>
      Déjà engagé : <strong>${fmtMoney(plafondData.deja_engage||0)}</strong><br>
      <strong class="text-ok">Disponible : ${fmtMoney(plafondData.disponible||0)}</strong>
    </div>
    ${plafondData.disponible > 0 ? `
    <form id="f-avance" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Montant de l'avance (GNF)*</label>
        <input type="number" name="montant" required min="1" max="${plafondData.disponible}" step="1">
      </div>
      <div class="fg"><label>Motif</label><input name="motif" placeholder="Ex : urgence familiale, santé…"></div>
      <div class="form-2">
        <div class="fg"><label>Date de l'avance</label><input type="date" name="date_avance" value="${today()}"></div>
        <div class="fg"><label>Mois de remboursement (déduction du bulletin)</label><input type="month" name="mois_remboursement" value="${moisCourant()}"></div>
      </div>
      <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
      <input type="hidden" name="personnel_id" value="${esc(personnelId)}">
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Accorder l'avance</button>
      </div>
    </form>` : `<div class="alert alert-danger">Aucun montant disponible : le plafond de 40% est déjà atteint pour cet employé.</div>
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>`}
  `, { narrow: true });

  const f = $('#f-avance');
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant);
    try {
      await apiCreateAvance(fd);
      toast('Avance accordée ✅','success');
      closeModal();
      imprimerRecu({
        type: 'sortie', nom, description: `Avance sur salaire${fd.motif?' — '+fd.motif:''}`,
        montant: fd.montant, date: fd.date_avance, moyenPaiement: fd.moyen_paiement, recuPar: currentUser?.full_name,
      });
      pagePaieList(window._paieMoisActuel);
    } catch(err) { toast(err.message,'error'); }
  };
}
window.modalAccorderAvance = modalAccorderAvance;

async function pageAvances() {
  const avances = await apiGetAvances();
  openModal('💵 Avances sur salaire — Historique', `
    <div class="tbl-wrap"><table>
      <thead><tr><th>Employé</th><th>Montant</th><th>Motif</th><th>Date</th><th>Remboursement</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody>
        ${avances.length ? avances.map(a => `<tr>
          <td>${esc(a.prenom)} ${esc(a.nom)}</td>
          <td class="mono text-right">${fmtMoney(a.montant)}</td>
          <td style="font-size:12px">${esc(a.motif||'—')}</td>
          <td>${fmtDate(a.date_avance)}</td>
          <td>${esc(a.mois_remboursement)}</td>
          <td><span class="badge ${a.statut==='remboursee'?'bdg-ok':a.statut==='annulee'?'bdg-gray':'bdg-warn'}">
            ${a.statut==='remboursee'?'✔ Remboursée':a.statut==='annulee'?'Annulée':'En cours'}
          </span></td>
          <td>${a.statut==='en_cours' && currentUser.role==='admin'?`<button class="btn btn-danger btn-xs" onclick="annulerAvance('${escJs(a.id)}')">Annuler</button>`:'—'}</td>
        </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('💵','Aucune avance enregistrée')}</td></tr>`}
      </tbody>
    </table></div>
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
  `, { wide: true });
}
async function annulerAvance(id) {
  if (!confirmDel('Annuler cette avance ?')) return;
  try { await apiAnnulerAvance(id); toast('Avance annulée','success'); pageAvances(); }
  catch(e) { toast(e.message,'error'); }
}
window.pageAvances = pageAvances;
window.annulerAvance = annulerAvance;

/* ── Types de primes (liste déroulante modifiable) ── */
async function modalTypesPrimes() {
  const types = await apiGetTypesPrimes('actives=0');
  openModal('🏷️ Types de primes', `
    <form id="f-newtype" style="display:flex;gap:10px;margin-bottom:16px">
      <input name="nom" placeholder="Nouveau type de prime…" required style="flex:1">
      <button type="submit" class="btn btn-primary btn-sm">+ Ajouter</button>
    </form>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Nom</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody>
        ${types.map(t => `<tr>
          <td>${esc(t.nom)}</td>
          <td><span class="badge ${t.active?'bdg-ok':'bdg-gray'}">${t.active?'Actif':'Désactivé'}</span></td>
          <td><div class="td-actions">
            <button class="btn btn-outline btn-xs" onclick="toggleTypePrime('${escJs(t.id)}',${t.active?0:1})">${t.active?'Désactiver':'Activer'}</button>
            <button class="btn btn-danger btn-xs" onclick="delTypePrime('${escJs(t.id)}')">🗑</button>
          </div></td>
        </tr>`).join('')}
      </tbody>
    </table></div>
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
  `, { narrow: true });
  $('#f-newtype').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { await apiCreateTypePrime(fd); toast('Type ajouté','success'); modalTypesPrimes(); }
    catch(err) { toast(err.message,'error'); }
  };
}
async function toggleTypePrime(id, active) {
  try { await apiUpdateTypePrime(id, { active }); modalTypesPrimes(); }
  catch(e) { toast(e.message,'error'); }
}
async function delTypePrime(id) {
  if (!confirmDel('Supprimer ce type de prime ?')) return;
  try { await apiDeleteTypePrime(id); toast('Supprimé','success'); modalTypesPrimes(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalTypesPrimes = modalTypesPrimes;
window.toggleTypePrime = toggleTypePrime;
window.delTypePrime = delTypePrime;

/* ── Impression du bulletin de salaire ── */
async function imprimerBulletinSalaire(bulletinId) {
  const b = await apiGetBulletin(bulletinId);
  const settings = await apiGetSettings();

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Bulletin de salaire — ${b.prenom} ${b.nom}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:Arial,sans-serif;font-size:13px;color:#1F2937;margin:0;padding:26px;background:#F3F4F6}
    .doc{max-width:620px;margin:0 auto;background:#fff;border:1px solid #D1D5DB;border-radius:4px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
    .bandeau{height:6px;display:flex}
    .bandeau div{flex:1}
    .inner{padding:30px 34px}
    .header{text-align:center;border-bottom:2px solid #111827;padding-bottom:16px;margin-bottom:18px}
    .header img{max-height:56px;margin:0 auto 8px;display:block}
    .header h1{color:#111827;font-size:17px;margin:0 0 3px}
    .header h2{font-size:14px;margin-top:10px;color:#374151;letter-spacing:1px}
    .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;background:#F9FAFB;border:1px solid #F0F1F3;padding:14px 16px;border-radius:6px;margin-bottom:18px;font-size:12px}
    table{width:100%;border-collapse:collapse;margin-bottom:6px}
    th{background:#111827;color:#fff;padding:9px 12px;text-align:left;font-size:11px;font-weight:600}
    td{padding:9px 12px;border-bottom:1px solid #F0F1F3;font-size:12.5px}
    .total-row td{font-weight:800;font-size:14.5px;background:#F9FAFB;border-top:2px solid #111827}
    .lettres-box{background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;padding:12px 16px;margin:16px 0 22px;font-size:11.5px;font-style:italic;color:#374151}
    .sig{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:36px;align-items:end}
    .sig .sig-col{text-align:center}
    .sig .cachet-img{max-height:55px;max-width:110px;display:block;margin:0 auto 2px}
    .sig .signature-img{max-height:35px;max-width:110px;display:block;margin:0 auto 2px}
    .sig .sig-label{border-top:1px solid #9CA3AF;padding-top:8px;text-align:center;font-size:11px;color:#4B5563;margin-top:6px}
    .credit{text-align:center;font-size:8.5px;color:#C0C4CC;margin-top:22px}
  </style></head><body>
  <div class="doc">
    <div class="bandeau"><div style="background:#CE1126"></div><div style="background:#FCD116"></div><div style="background:#009460"></div></div>
    <div class="inner">
      <div class="header">
        ${settings.ecole_logo?`<img src="${settings.ecole_logo}">`:''}
        <h1>${esc(settings.ecole_nom||'Groupe Scolaire')}</h1>
        <p style="font-size:11.5px;color:#6B7280;margin:2px 0">${esc(settings.ecole_adresse||'')}</p>
        ${settings.ecole_telephone?`<p style="font-size:11.5px;color:#6B7280;margin:2px 0">Tél : ${esc(settings.ecole_telephone)}</p>`:''}
        <h2>BULLETIN DE SALAIRE — ${esc(b.mois)}</h2>
      </div>
      <div class="info-grid">
        <div><strong>Nom &amp; Prénom :</strong> ${esc(b.prenom)} ${esc(b.nom)}</div>
        <div><strong>Poste :</strong> ${esc(b.poste||'—')}</div>
        <div><strong>Type de rémunération :</strong> ${b.type_remuneration==='horaire'?'Horaire':'Mensuel'}</div>
        <div><strong>Date de paiement :</strong> ${fmtDate(b.date_paiement)}</div>
      </div>
      <table>
        <thead><tr><th>Élément</th><th style="text-align:right">Montant (GNF)</th></tr></thead>
        <tbody>
          ${b.type_remuneration==='horaire' ? `<tr><td>Heures enseignées (${b.heures}h × ${Number(b.taux_horaire).toLocaleString('fr-FR')} GNF)</td><td style="text-align:right">${Number(b.salaire_base).toLocaleString('fr-FR')}</td></tr>`
            : `<tr><td>Salaire de base</td><td style="text-align:right">${Number(b.salaire_base).toLocaleString('fr-FR')}</td></tr>`}
          ${b.prime_revision>0 ? `<tr><td>Prime cours de révision (${b.heures_revision}h)</td><td style="text-align:right">+${Number(b.prime_revision).toLocaleString('fr-FR')}</td></tr>` : ''}
          ${b.primes>0 ? `<tr><td>Primes${b.primes_detail?' — '+esc(b.primes_detail):''}</td><td style="text-align:right">+${Number(b.primes).toLocaleString('fr-FR')}</td></tr>` : ''}
          ${b.deductions>0 ? `<tr><td>Déductions</td><td style="text-align:right">−${Number(b.deductions).toLocaleString('fr-FR')}</td></tr>` : ''}
          ${b.avance_deduite>0 ? `<tr><td>Avance sur salaire déduite</td><td style="text-align:right">−${Number(b.avance_deduite).toLocaleString('fr-FR')}</td></tr>` : ''}
          <tr class="total-row"><td>MONTANT NET À PAYER</td><td style="text-align:right">${Number(b.montant_net).toLocaleString('fr-FR')} GNF</td></tr>
        </tbody>
      </table>
      <div class="lettres-box">Arrêté le présent bulletin à la somme nette de : ${montantEnLettres(b.montant_net)}.</div>
      <div class="sig">
        <div class="sig-col">
          ${settings.ecole_cachet?`<img class="cachet-img" src="${settings.ecole_cachet}">`:''}
          ${settings.signature_directeur?`<img class="signature-img" src="${settings.signature_directeur}">`:''}
          <div class="sig-label">Signature de l'employeur</div>
        </div>
        <div class="sig-col"><div class="sig-label">Signature de l'employé</div></div>
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
window.pagePaieList = pagePaieList;
window.modalPayerSalaire = modalPayerSalaire;
window.imprimerBulletinSalaire = imprimerBulletinSalaire;
