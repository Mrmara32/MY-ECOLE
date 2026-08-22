/* ===================== SÉANCES DE COURS ===================== */
const STATUT_SEANCE_COLORS = { en_attente:'bdg-warn', validee:'bdg-ok', rejetee:'bdg-err' };
const STATUT_SEANCE_LABELS = { en_attente:'⏳ En attente', validee:'✔ Validée', rejetee:'✕ Rejetée' };

async function pageSeances(mois = null) {
  mois = mois || moisCourant();
  window._seancesMoisActuel = mois;
  $('#content').innerHTML = loadingHtml;
  try {
    const [seances, personnelList] = await Promise.all([
      apiGetSeancesCours('mois=' + mois), apiGetPersonnel().catch(() => [])
    ]);
    const estEnseignant = currentUser.role === 'enseignant';
    const peutValider = ['admin', 'directeur', 'directeur_etudes'].includes(currentUser.role);
    const enseignants = personnelList.filter(p => p.poste === 'Enseignant' || p.type_remuneration === 'horaire');

    const render = data => {
      $('#tb-seances').innerHTML = data.length ? data.map(s => `<tr>
        <td>${fmtDate(s.date_seance)}<br><span class="text-muted" style="font-size:11px">${esc(s.jour||'')}</span></td>
        <td class="mono">${esc(s.creneau||'—')}</td>
        <td><strong>${esc(s.prenom)} ${esc(s.nom)}</strong></td>
        <td>${esc(s.classe||'—')}</td>
        <td>${s.salle?`<span class="badge bdg-primary">${esc(s.salle)}</span>`:'—'}</td>
        <td>${esc(s.matiere||'—')}</td>
        <td class="text-right mono">${s.duree_heures}h</td>
        <td><span class="badge ${STATUT_SEANCE_COLORS[s.statut]}">${STATUT_SEANCE_LABELS[s.statut]}</span>
          ${s.statut==='rejetee' && s.motif_rejet ? `<br><span class="text-muted" style="font-size:10.5px">${esc(s.motif_rejet)}</span>` : ''}</td>
        <td><div class="td-actions">
          ${peutValider && s.statut==='en_attente' ? `
            <button class="btn btn-ok btn-xs" onclick="validerSeance('${escJs(s.id)}')" title="Valider">✔</button>
            <button class="btn btn-danger btn-xs" onclick="rejeterSeance('${escJs(s.id)}')" title="Rejeter">✕</button>
          ` : ''}
          ${(currentUser.role==='admin'||currentUser.role==='directeur') && s.statut==='en_attente' ? `<button class="btn btn-outline btn-xs" onclick="delSeance('${escJs(s.id)}')" title="Supprimer">🗑</button>` : ''}
        </div></td>
      </tr>`).join('') : `<tr><td colspan="9">${emptyHtml('📋','Aucune séance déclarée pour ce mois')}</td></tr>`;
    };

    // Récapitulatif des heures validées par enseignant sur le mois
    const recap = {};
    seances.filter(s => s.statut === 'validee').forEach(s => {
      const key = s.personnel_id;
      if (!recap[key]) recap[key] = { nom: `${s.prenom} ${s.nom}`, heures: 0 };
      recap[key].heures += s.duree_heures;
    });
    const recapRows = Object.values(recap).sort((a,b) => b.heures - a.heures);
    const nbEnAttente = seances.filter(s => s.statut === 'en_attente').length;

    $('#content').innerHTML = `
    <div class="alert alert-info mb-4">💡 Chaque séance de cours donnée par un enseignant rémunéré à l'heure peut être déclarée ici, puis validée par la direction. Les heures validées alimentent <strong>automatiquement</strong> le calcul de la paie du mois — plus besoin de ressaisir un total manuellement.</div>

    ${recapRows.length ? `
    <div class="card mb-4">
      <div class="card-header"><span class="card-title">📊 Heures validées ce mois — ${mois}</span></div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Enseignant</th><th class="text-right">Heures validées</th></tr></thead>
        <tbody>${recapRows.map(r => `<tr><td>${esc(r.nom)}</td><td class="text-right mono fw-600">${r.heures}h</td></tr>`).join('')}</tbody>
      </table></div>
    </div>` : ''}

    <div class="card">
      <div class="card-header">
        <span class="card-title">📋 Séances de cours ${nbEnAttente>0?`<span class="badge bdg-warn">${nbEnAttente} en attente</span>`:''}</span>
        <div class="card-actions">
          <input type="month" id="f-seancemois" value="${mois}" onchange="pageSeances(this.value)">
          <button class="btn btn-primary btn-sm" onclick="modalDeclarerSeance()">+ Déclarer une séance</button>
        </div>
      </div>
      <div class="filters">
        ${!estEnseignant ? `<div class="fg"><label>Enseignant</label><select id="f-seance-ens">
          <option value="">Tous</option>
          ${enseignants.map(p=>`<option value="${esc(p.id)}">${esc(p.prenom)} ${esc(p.nom)}</option>`).join('')}
        </select></div>` : ''}
        <div class="fg"><label>Statut</label><select id="f-seance-statut">
          <option value="">Tous</option>
          <option value="en_attente">En attente</option>
          <option value="validee">Validée</option>
          <option value="rejetee">Rejetée</option>
        </select></div>
        ${peutValider ? `<div class="fg" style="align-self:flex-end"><button class="btn btn-ok btn-sm" onclick="validerToutesEnAttente()">✔ Tout valider ce mois</button></div>` : ''}
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Date</th><th>Créneau</th><th>Enseignant</th><th>Classe</th><th>Salle</th><th>Matière</th><th class="text-right">Durée</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-seances"></tbody>
      </table></div>
    </div>`;

    let curr = seances;
    render(curr);
    const refilter = () => {
      const ensSel = $('#f-seance-ens')?.value;
      const statutSel = $('#f-seance-statut')?.value;
      curr = seances.filter(s => (!ensSel || s.personnel_id === ensSel) && (!statutSel || s.statut === statutSel));
      render(curr);
    };
    $('#f-seance-ens')?.addEventListener('change', refilter);
    $('#f-seance-statut')?.addEventListener('change', refilter);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
window.pageSeances = pageSeances;

async function modalDeclarerSeance() {
  const estEnseignant = currentUser.role === 'enseignant';
  const personnelList = await apiGetPersonnel().catch(() => []);
  const enseignants = personnelList.filter(p => p.poste === 'Enseignant' || p.type_remuneration === 'horaire');
  let monPersonnelId = '';
  if (estEnseignant) {
    const moi = enseignants.find(p => p.user_id === currentUser.id);
    monPersonnelId = moi ? moi.id : '';
  }
  if (!estEnseignant && !_sallesCache.length) await refreshSalles();

  openModal("📋 Déclarer une séance de cours", `
    <form id="f-seance" style="display:flex;flex-direction:column;gap:14px">
      ${estEnseignant ? `<input type="hidden" name="personnel_id" value="${esc(monPersonnelId)}">` : `
      <div class="fg"><label>Enseignant*</label><select name="personnel_id" id="seance-ens-select" required>
        <option value="">— Choisir —</option>
        ${enseignants.map(p=>`<option value="${esc(p.id)}">${esc(p.prenom)} ${esc(p.nom)}</option>`).join('')}
      </select></div>`}
      <div class="form-2">
        <div class="fg"><label>Date*</label><input type="date" name="date_seance" id="seance-date" value="${today()}" required></div>
        <div class="fg"><label>Créneau*</label><select name="creneau" id="seance-creneau" required>
          ${CRENEAUX.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}
        </select></div>
      </div>
      <div id="seance-suggestions" class="text-muted" style="font-size:11.5px"></div>
      <div class="form-2">
        <div class="fg"><label>Classe*</label><select name="classe" id="seance-classe" required>${optionsHtml(CLASSES)}</select></div>
        <div class="fg"><label>Salle</label><select name="salle" id="seance-salle">
          <option value="">— Aucune —</option>
          ${(_sallesCache||[]).filter(s=>s.active).map(s=>`<option value="${esc(s.nom)}">${esc(s.nom)}</option>`).join('')}
        </select></div>
      </div>
      <div class="fg"><label>Matière*</label><select name="matiere" id="seance-matiere" required>${optionsHtml(MATIERES)}</select></div>
      <div class="fg"><label>Durée (heures)</label><input type="number" name="duree_heures" id="seance-duree" step="0.25" min="0.25" placeholder="Calculée automatiquement depuis le créneau"></div>
      <div class="alert alert-info" style="font-size:11.5px">Cette séance sera enregistrée « en attente » et devra être validée par la direction avant d'être comptabilisée en paie.</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Déclarer la séance</button>
      </div>
    </form>`, { narrow: true });

  // Charge les creneaux habituels (emploi du temps) de l'enseignant selectionne, pour suggestion rapide
  const chargerSuggestions = async (personnelId) => {
    if (!personnelId) { $('#seance-suggestions').innerHTML = ''; return; }
    const creneaux = await apiCreneauxEmploiTemps(personnelId).catch(() => []);
    if (!creneaux.length) { $('#seance-suggestions').innerHTML = ''; return; }
    $('#seance-suggestions').innerHTML = 'Créneaux habituels : ' + creneaux.map(c =>
      `<button type="button" class="btn btn-outline btn-xs" style="margin:2px" onclick='remplirDepuisSuggestion(${JSON.stringify(c)})'>${esc(c.jour)} ${esc(c.creneau)} · ${esc(c.classe)}</button>`
    ).join(' ');
  };
  window.remplirDepuisSuggestion = (c) => {
    $('#seance-creneau').value = c.creneau;
    $('#seance-classe').value = c.classe;
    if (c.salle) $('#seance-salle').value = c.salle;
    if (c.matiere) $('#seance-matiere').value = c.matiere;
  };

  if (estEnseignant) chargerSuggestions(monPersonnelId);
  else $('#seance-ens-select').addEventListener('change', e => chargerSuggestions(e.target.value));

  $('#f-seance').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (fd.duree_heures) fd.duree_heures = parseFloat(fd.duree_heures); else delete fd.duree_heures;
    try {
      await apiCreateSeanceCours(fd);
      toast('Séance déclarée ✅ (en attente de validation)', 'success');
      closeModal();
      pageSeances(window._seancesMoisActuel);
    } catch(err) { toast(err.message, 'error'); }
  };
}
window.modalDeclarerSeance = modalDeclarerSeance;

async function validerSeance(id) {
  try { await apiValiderSeanceCours(id); toast('Séance validée ✅', 'success'); pageSeances(window._seancesMoisActuel); }
  catch(e) { toast(e.message, 'error'); }
}
async function rejeterSeance(id) {
  const motif = prompt('Motif du rejet (optionnel) :', '');
  if (motif === null) return;
  try { await apiRejeterSeanceCours(id, { motif }); toast('Séance rejetée', 'warning'); pageSeances(window._seancesMoisActuel); }
  catch(e) { toast(e.message, 'error'); }
}
async function delSeance(id) {
  if (!confirmDel('Supprimer cette séance ?')) return;
  try { await apiDeleteSeanceCours(id); toast('Supprimée', 'success'); pageSeances(window._seancesMoisActuel); }
  catch(e) { toast(e.message, 'error'); }
}
async function validerToutesEnAttente() {
  const ensSel = $('#f-seance-ens')?.value;
  if (!ensSel) { toast('Choisissez un enseignant dans le filtre pour valider en groupe', 'error'); return; }
  if (!confirm('Valider toutes les séances en attente de cet enseignant pour ce mois ?')) return;
  try {
    const r = await apiValiderGroupeSeances({ personnel_id: ensSel, mois: window._seancesMoisActuel });
    toast(`${r.count} séance(s) validée(s) ✅`, 'success');
    pageSeances(window._seancesMoisActuel);
  } catch(e) { toast(e.message, 'error'); }
}
window.validerSeance = validerSeance;
window.rejeterSeance = rejeterSeance;
window.delSeance = delSeance;
window.validerToutesEnAttente = validerToutesEnAttente;
