/* ===================== ÉLÈVES ===================== */
let _elevesList = [];

async function pageEleves() {
  $('#content').innerHTML = loadingHtml;
  try {
    _elevesList = await apiGetEleves();
    renderElevesTable(_elevesList);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function renderElevesTable(list) {
  const classes = [...new Set(list.map(e=>e.classe).filter(Boolean))].sort();
  $('#content').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">🎓 Élèves (${list.length})</span>
      <div style="display:flex;gap:8px">
        ${['admin','directeur','secretaire'].includes(currentUser?.role) ? '<button class="btn btn-outline btn-sm" onclick="modalImportEleves()">📥 Importer (Excel / CSV)</button>' : ''}
        <button class="btn btn-primary btn-sm" onclick="modalEleve()">+ Inscrire un élève</button>
      </div>
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-elv" placeholder="Nom, prénom, matricule…"></div>
      <div class="fg"><label>Classe</label><select id="f-cls"><option value="">Toutes</option>${classes.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
      <div class="fg"><label>Statut</label><select id="f-stat">
        <option value="">Tous</option>
        <option value="actif">Actif</option>
        <option value="inactif">Inactif</option>
        <option value="exclu">Exclu</option>
        <option value="transfere">Transféré</option>
      </select></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr id="th-eleves"><th>Photo</th><th>Matricule</th><th>Nom & Prénom</th><th>Classe</th><th>Né(e) le</th><th>Contact parent</th><th>Statut</th><th>Actions</th></tr></thead>
      <tbody id="tb-eleves"></tbody>
    </table></div>
    <div id="pag-eleves"></div>
  </div>`;
  let curr = list;
  getPaginator('eleves').onChange = () => renderElevesRows(curr);
  renderElevesRows(curr);
  const filter = () => {
    const q = $('#q-elv').value.toLowerCase();
    const cls = $('#f-cls').value;
    const stat = $('#f-stat').value;
    curr = _elevesList.filter(e => {
      const txt = `${e.nom} ${e.prenom} ${e.matricule||''}`.toLowerCase();
      return (!q||txt.includes(q)) && (!cls||e.classe===cls) && (!stat||e.statut===stat);
    });
    resetPaginator('eleves');
    renderElevesRows(curr);
  };
  $('#q-elv').addEventListener('input', filter);
  $('#f-cls').addEventListener('change', filter);
  $('#f-stat').addEventListener('change', filter);

  makeSortableTable('#th-eleves', () => curr, renderElevesRows,
    [null, 'matricule', 'nom', 'classe', 'date_naissance', 'pere_telephone', 'statut', null]);
}

const STATUT_COLORS = { actif:'bdg-ok', inactif:'bdg-gray', exclu:'bdg-err', transfere:'bdg-warn', reinsrit:'bdg-info', preinscrit:'bdg-warn' };
const STATUT_LABELS_ELV = { actif:'Actif', inactif:'Inactif', exclu:'Exclu', transfere:'Transféré', reinsrit:'Réinscrit', preinscrit:'⏳ Préinscrit (à valider)' };

function renderElevesRows(list) {
  const { items, page, totalPages, total } = paginate('eleves', list);
  $('#tb-eleves').innerHTML = items.length ? items.map(e => `<tr>
    <td>${elevePhoto(e, 34)}</td>
    <td class="mono">${esc(e.matricule||'—')}</td>
    <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong></td>
    <td><span class="badge bdg-primary">${esc(e.classe||'—')}</span></td>
    <td>${fmtDate(e.date_naissance)} ${e.lieu_naissance?`<span class="text-muted">(${esc(e.lieu_naissance)})</span>`:''}</td>
    <td>${esc(e.pere_telephone||e.mere_telephone||e.tuteur_telephone||'—')}</td>
    <td><span class="badge ${STATUT_COLORS[e.statut]||'bdg-gray'}">${esc(STATUT_LABELS_ELV[e.statut]||e.statut||'actif')}</span></td>
    <td><div class="td-actions">
      ${e.statut==='preinscrit' && ['admin','directeur','comptable'].includes(currentUser.role) ? `<button class="btn btn-ok btn-xs" onclick="modalValiderPreinscription('${escJs(e.id)}','${escJs(e.prenom)} ${escJs(e.nom)}')" title="Valider la préinscription">✔ Valider</button>` : ''}
      <button class="btn btn-outline btn-xs" onclick="imprimerCarteScolaire('${escJs(e.id)}')" title="Carte scolaire sécurisée (QR + hologramme)">🪪</button>
      ${cycleDeClasse(e.classe)==='maternelle' ? `<button class="btn btn-outline btn-xs" onclick="imprimerCarteRetrait('${escJs(e.id)}')" title="Carte de retrait">🧸</button>` : ''}
      <button class="btn btn-outline btn-xs" onclick="ficheEleve('${escJs(e.id)}')" title="Fiche complète">📋</button>
      <button class="btn btn-outline btn-xs" onclick="modalEleve('${escJs(e.id)}')" title="Modifier">✏️</button>
      <button class="btn btn-danger btn-xs" onclick="delEleve('${escJs(e.id)}')" title="Supprimer">🗑</button>
    </div></td>
  </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('🎓','Aucun élève trouvé','Inscrivez le premier élève via le bouton + ci-dessus')}</td></tr>`;
  $('#pag-eleves').innerHTML = paginationHtml('eleves', page, totalPages, total);
}

/* ── Formulaire d'inscription ── */
async function modalEleve(id = null) {
  const data = id ? await apiGetEleve(id) : {};
  const titre = id ? `Modifier — ${data.prenom} ${data.nom}` : 'Inscrire un nouvel élève';
  openModal(titre, `
    <div class="tabs" id="elv-tabs">
      <div class="tab active" onclick="switchTab('t-id')">🆔 Identité</div>
      <div class="tab" onclick="switchTab('t-fil')">👨‍👩‍👧 Filiation</div>
      <div class="tab" onclick="switchTab('t-san')">🏥 Santé</div>
      ${id?'<div class="tab" onclick="switchTab(\'t-photo\')">📷 Photo</div>':''}
    </div>
    <form id="f-eleve">
    <!-- IDENTITÉ -->
    <div class="tab-pane active" id="t-id">
      <div class="form-section-title">Informations de base</div>
      <div class="form-3">
        <div class="fg"><label>Prénom*</label><input name="prenom" value="${esc(data.prenom||'')}" required></div>
        <div class="fg"><label>Nom de famille*</label><input name="nom" value="${esc(data.nom||'')}" required></div>
        <div class="fg"><label>Matricule</label><input name="matricule" value="${esc(data.matricule||'')}" placeholder="Auto-généré"></div>
      </div>
      <div class="form-3 mt-3">
        <div class="fg"><label>Date de naissance</label><input type="date" name="date_naissance" value="${esc(data.date_naissance||'')}"></div>
        <div class="fg"><label>Lieu de naissance</label><input name="lieu_naissance" value="${esc(data.lieu_naissance||'')}" placeholder="Conakry"></div>
        <div class="fg"><label>Sexe</label><select name="sexe">
          <option value="">—</option>
          <option value="M" ${data.sexe==='M'?'selected':''}>Masculin</option>
          <option value="F" ${data.sexe==='F'?'selected':''}>Féminin</option>
        </select></div>
      </div>
      <div class="form-3 mt-3">
        <div class="fg"><label>Nationalité</label><input name="nationalite" value="${esc(data.nationalite||'Guinéenne')}"></div>
        <div class="fg"><label>Classe</label><select name="classe">${optionsHtml(CLASSES, data.classe||'')}</select></div>
        <div class="fg"><label>Année scolaire</label><input name="annee_scolaire" value="${esc(data.annee_scolaire||anneeCourante())}"></div>
      </div>
      <div class="form-2 mt-3">
        <div class="fg"><label>Statut</label><select name="statut">
          <option value="actif" ${(!data.statut||data.statut==='actif')?'selected':''}>Actif</option>
          <option value="inactif" ${data.statut==='inactif'?'selected':''}>Inactif</option>
          <option value="exclu" ${data.statut==='exclu'?'selected':''}>Exclu</option>
          <option value="transfere" ${data.statut==='transfere'?'selected':''}>Transféré</option>
        </select></div>
        <div class="fg"><label>Adresse</label><input name="adresse" value="${esc(data.adresse||'')}"></div>
        <div class="form-2">
          <div class="fg"><label>Contact d'urgence — Nom</label><input name="contact_urgence_nom" value="${esc(data.contact_urgence_nom||'')}" placeholder="Nom de la personne à contacter"></div>
          <div class="fg"><label>Contact d'urgence — Téléphone</label><input name="contact_urgence_telephone" value="${esc(data.contact_urgence_telephone||'')}" placeholder="622 00 00 00"></div>
        </div>
      </div>
    </div>

    <!-- FILIATION -->
    <div class="tab-pane" id="t-fil">
      <div class="form-section-title">Père</div>
      <div class="form-3">
        <div class="fg"><label>Prénom</label><input name="pere_prenom" value="${esc(data.pere_prenom||'')}"></div>
        <div class="fg"><label>Nom</label><input name="pere_nom" value="${esc(data.pere_nom||'')}"></div>
        <div class="fg"><label>Profession</label><input name="pere_profession" value="${esc(data.pere_profession||'')}"></div>
      </div>
      <div class="form-2 mt-3">
        <div class="fg"><label>Téléphone père</label><input name="pere_telephone" value="${esc(data.pere_telephone||'')}"></div>
        <div class="fg"><label>Email père</label><input type="email" name="pere_email" value="${esc(data.pere_email||'')}"></div>
      </div>
      <div class="form-section-title mt-4">Mère</div>
      <div class="form-3">
        <div class="fg"><label>Prénom</label><input name="mere_prenom" value="${esc(data.mere_prenom||'')}"></div>
        <div class="fg"><label>Nom</label><input name="mere_nom" value="${esc(data.mere_nom||'')}"></div>
        <div class="fg"><label>Profession</label><input name="mere_profession" value="${esc(data.mere_profession||'')}"></div>
      </div>
      <div class="form-2 mt-3">
        <div class="fg"><label>Téléphone mère</label><input name="mere_telephone" value="${esc(data.mere_telephone||'')}"></div>
        <div class="fg"><label>Email mère</label><input type="email" name="mere_email" value="${esc(data.mere_email||'')}"></div>
      </div>
      <div class="form-section-title mt-4">Tuteur légal (si différent des parents)</div>
      <div class="form-3">
        <div class="fg"><label>Prénom</label><input name="tuteur_prenom" value="${esc(data.tuteur_prenom||'')}"></div>
        <div class="fg"><label>Nom</label><input name="tuteur_nom" value="${esc(data.tuteur_nom||'')}"></div>
        <div class="fg"><label>Relation</label><input name="tuteur_relation" value="${esc(data.tuteur_relation||'')}" placeholder="Oncle, Tante…"></div>
      </div>
      <div class="form-2 mt-3">
        <div class="fg"><label>Téléphone tuteur</label><input name="tuteur_telephone" value="${esc(data.tuteur_telephone||'')}"></div>
        <div class="fg"><label>Email tuteur</label><input type="email" name="tuteur_email" value="${esc(data.tuteur_email||'')}"></div>
      </div>
    </div>

    <!-- SANTÉ -->
    <div class="tab-pane" id="t-san">
      <div class="form-section-title">Informations médicales</div>
      <div class="form-3">
        <div class="fg"><label>Groupe sanguin</label><select name="groupe_sanguin">${optionsHtml(GROUPES_SANGUINS, data.groupe_sanguin||'')}</select></div>
        <div class="fg"><label>Médecin traitant</label><input name="medecin_nom" value="${esc(data.medecin_nom||'')}"></div>
        <div class="fg"><label>Tél. médecin</label><input name="medecin_telephone" value="${esc(data.medecin_telephone||'')}"></div>
      </div>
      <div class="fg mt-3"><label>Allergies connues</label>
        <textarea name="allergies" rows="2">${esc(data.allergies||'')}</textarea></div>
      <div class="fg mt-3"><label>Maladies chroniques</label>
        <textarea name="maladies_chroniques" rows="2">${esc(data.maladies_chroniques||'')}</textarea></div>
      <div class="fg mt-3"><label>Médicaments réguliers</label>
        <textarea name="medicaments" rows="2">${esc(data.medicaments||'')}</textarea></div>
      <div class="fg mt-3"><label>Handicap / Besoin spécifique</label>
        <textarea name="handicap" rows="2">${esc(data.handicap||'')}</textarea></div>
      <div class="form-section-title mt-4">Assurance</div>
      <div class="form-2">
        <div class="fg"><label>Compagnie d'assurance</label><input name="assurance_nom" value="${esc(data.assurance_nom||'')}"></div>
        <div class="fg"><label>N° Police</label><input name="assurance_numero" value="${esc(data.assurance_numero||'')}"></div>
      </div>
      <div class="fg mt-3"><label>Vaccins effectués</label>
        <textarea name="vaccins" rows="2" placeholder="BCG, Polio, Hépatite B…">${esc(data.vaccins||'')}</textarea></div>
    </div>

    <!-- PHOTO (si édition) -->
    ${id ? `<div class="tab-pane" id="t-photo">
      <div style="text-align:center;padding:20px">
        <div id="photo-prev" class="mb-3">${elevePhoto(data, 120)}</div>
        ${photoCaptureWidgetHtml('eleve-photo')}
        <div class="text-muted mt-2" style="font-size:12px">JPG ou PNG · Max 5 Mo · Photo, fichier ou caméra</div>
      </div>
    </div>` : ''}

    ${id ? `<div class="form-section-title mt-3">Traçabilité</div>${motifFieldHtml()}` : ''}

    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button type="submit" class="btn btn-primary">💾 ${id?'Enregistrer':'Inscrire l\'élève'}</button>
    </div>
    </form>
  `, { wide: true });

  // Upload photo (fichier, webcam, ou caméra mobile)
  if (id) {
    wirePhotoCapture('eleve-photo', async (file) => {
      const fd = new FormData();
      fd.append('photo', file);
      try {
        const r = await apiUploadPhoto(id, fd);
        $('#photo-prev').innerHTML = `<img src="${r.photo_url}" style="width:120px;height:120px;border-radius:8px;object-fit:cover;border:2px solid #E5E7EB">`;
        toast('Photo mise à jour', 'success');
        _elevesList = await apiGetEleves();
      } catch(err) { toast(err.message, 'error'); }
    });
  }

  $('#f-eleve').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      if (id) await apiUpdateEleve(id, fd); else await apiCreateEleve(fd);
      toast(id?'Élève mis à jour':'Élève inscrit','success');
      closeModal(); pageEleves();
    } catch(err) { toast(err.message,'error'); }
  };
}

function switchTab(panelId) {
  $$('.tab').forEach(t => t.classList.remove('active'));
  $$('.tab-pane').forEach(p => p.classList.remove('active'));
  $('#'+panelId)?.classList.add('active');
  // Activer l'onglet correspondant
  const idx = ['t-id','t-fil','t-san','t-photo'].indexOf(panelId);
  const tabs = $$('#elv-tabs .tab');
  if (tabs[idx]) tabs[idx].classList.add('active');
}
window.switchTab = switchTab;

/* ── Fiche complète d'un élève ── */
async function ficheEleve(id) {
  const e = await apiGetEleve(id);
  const abs = await apiStatsAbsences(id).catch(()=>({total_absences:0,total_retards:0}));
  const solde = await apiSoldePaiements(id).catch(()=>({total_du:0,total_paye:0,reste:0}));

  const ligneInfo = (lbl, val) => val ? `<div><strong class="text-muted">${esc(lbl)} :</strong> ${esc(String(val))}</div>` : '';
  openModal(`📋 Fiche — ${e.prenom} ${e.nom}`, `
    <div style="display:flex;gap:20px;margin-bottom:20px">
      <div>${elevePhoto(e, 80)}</div>
      <div>
        <h2 style="font-size:20px;margin-bottom:4px">${esc(e.prenom)} ${esc(e.nom)}</h2>
        <div class="text-muted" style="font-size:13px">Matricule : <span class="mono">${esc(e.matricule||'—')}</span></div>
        <div class="mt-2"><span class="badge bdg-primary">${esc(e.classe||'—')}</span> <span class="badge ${STATUT_COLORS[e.statut]||'bdg-gray'}">${esc(e.statut)}</span></div>
      </div>
    </div>
    <div class="tabs" id="fiche-tabs">
      <div class="tab active" onclick="switchFicheTab('ft-id')">Identité</div>
      <div class="tab" onclick="switchFicheTab('ft-fil')">Filiation</div>
      <div class="tab" onclick="switchFicheTab('ft-san')">Santé</div>
      <div class="tab" onclick="switchFicheTab('ft-abs')">Absences</div>
      <div class="tab" onclick="switchFicheTab('ft-fin')">Finances</div>
    </div>
    <div class="tab-pane active" id="ft-id">
      ${ligneInfo('Date de naissance', fmtDate(e.date_naissance))}
      ${ligneInfo('Lieu de naissance', e.lieu_naissance)}
      ${ligneInfo('Nationalité', e.nationalite)}
      ${ligneInfo('Sexe', e.sexe==='M'?'Masculin':'Féminin')}
      ${ligneInfo('Adresse', e.adresse)}
      ${ligneInfo('Année scolaire', e.annee_scolaire)}
    </div>
    <div class="tab-pane" id="ft-fil">
      ${e.pere_nom||e.pere_prenom ? `<div class="form-section-title">Père</div>${ligneInfo('Nom complet',`${e.pere_prenom||''} ${e.pere_nom||''}`)}${ligneInfo('Profession',e.pere_profession)}${ligneInfo('Téléphone',e.pere_telephone)}${ligneInfo('Email',e.pere_email)}` : '<p class="text-muted">Aucune information sur le père</p>'}
      ${e.mere_nom||e.mere_prenom ? `<div class="form-section-title mt-3">Mère</div>${ligneInfo('Nom complet',`${e.mere_prenom||''} ${e.mere_nom||''}`)}${ligneInfo('Profession',e.mere_profession)}${ligneInfo('Téléphone',e.mere_telephone)}${ligneInfo('Email',e.mere_email)}` : ''}
      ${e.tuteur_nom||e.tuteur_prenom ? `<div class="form-section-title mt-3">Tuteur</div>${ligneInfo('Nom complet',`${e.tuteur_prenom||''} ${e.tuteur_nom||''}`)}${ligneInfo('Relation',e.tuteur_relation)}${ligneInfo('Téléphone',e.tuteur_telephone)}${ligneInfo('Email',e.tuteur_email)}` : ''}
    </div>
    <div class="tab-pane" id="ft-san">
      ${ligneInfo('Groupe sanguin', e.groupe_sanguin)}
      ${ligneInfo('Allergies', e.allergies)}
      ${ligneInfo('Maladies chroniques', e.maladies_chroniques)}
      ${ligneInfo('Médicaments', e.medicaments)}
      ${ligneInfo('Handicap / besoin spécifique', e.handicap)}
      ${ligneInfo('Médecin traitant', e.medecin_nom)}
      ${ligneInfo('Tél. médecin', e.medecin_telephone)}
      ${ligneInfo('Assurance', e.assurance_nom + (e.assurance_numero?' — N° '+e.assurance_numero:''))}
      ${ligneInfo('Vaccins', e.vaccins)}
    </div>
    <div class="tab-pane" id="ft-abs">
      <div class="stats-grid" style="grid-template-columns:repeat(4,1fr)">
        <div class="stat"><div class="stat-icon">❌</div><div class="stat-label">Total absences</div><div class="stat-val">${abs.total_absences||0}</div></div>
        <div class="stat"><div class="stat-icon">⏰</div><div class="stat-label">Retards</div><div class="stat-val">${abs.total_retards||0}</div></div>
        <div class="stat"><div class="stat-icon">✅</div><div class="stat-label">Justifiées</div><div class="stat-val">${abs.justifiees||0}</div></div>
        <div class="stat"><div class="stat-icon">⚠️</div><div class="stat-label">Non justifiées</div><div class="stat-val">${abs.non_justifiees||0}</div></div>
      </div>
      <button class="btn btn-outline btn-sm mt-3" onclick="closeModal();navigate('absences')">Voir toutes les absences →</button>
    </div>
    <div class="tab-pane" id="ft-fin">
      <div class="stats-grid" style="grid-template-columns:repeat(3,1fr)">
        <div class="stat"><div class="stat-label">Total dû</div><div class="stat-val" style="font-size:16px">${fmtMoney(solde.total_du)}</div></div>
        <div class="stat"><div class="stat-label">Total payé</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(solde.total_paye)}</div></div>
        <div class="stat"><div class="stat-label">Reste à payer</div><div class="stat-val text-err" style="font-size:16px">${fmtMoney(solde.reste)}</div></div>
      </div>
      <button class="btn btn-outline btn-sm mt-3" onclick="closeModal();navigate('paiements')">Voir les paiements →</button>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
      <button class="btn btn-primary" onclick="closeModal();modalEleve('${escJs(id)}')">✏️ Modifier</button>
      <button class="btn btn-accent" onclick="closeModal();imprimerBulletin('${escJs(id)}')">🖨 Bulletin</button>
      ${['admin','directeur','secretaire'].includes(currentUser?.role) ? `<button class="btn btn-outline" onclick="closeModal();modalParcours('${escJs(id)}')">📚 Parcours scolaire</button>` : ''}
      ${['admin','directeur','secretaire'].includes(currentUser?.role) ? `<button class="btn btn-outline" onclick="closeModal();imprimerAttestation('${escJs(id)}')">📄 Attestation de scolarité</button>` : ''}
    </div>
  `, { wide: true });
}

function switchFicheTab(panelId) {
  $$('.tab-pane').forEach(p => p.classList.remove('active'));
  $('#'+panelId)?.classList.add('active');
  const idx = ['ft-id','ft-fil','ft-san','ft-abs','ft-fin'].indexOf(panelId);
  const tabs = $$('#fiche-tabs .tab');
  if (tabs[idx]) { $$('#fiche-tabs .tab').forEach(t=>t.classList.remove('active')); tabs[idx].classList.add('active'); }
}

async function delEleve(id) {
  if (!confirmDel('Supprimer définitivement cet élève et toutes ses données ?')) return;
  try { await apiDeleteEleve(id); toast('Élève supprimé','success'); pageEleves(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalEleve = modalEleve;
window.ficheEleve = ficheEleve;
window.delEleve = delEleve;
window.switchFicheTab = switchFicheTab;

/* ── BULLETIN ── */
async function imprimerBulletin(eleveId, tri = 1, annee = '') {
  tri = String(tri);
  const libellePeriode = tri === 'annee' ? 'ANNÉE SCOLAIRE (moyenne annuelle)' : `TRIMESTRE ${tri}`;
  const eleve = await apiGetEleve(eleveId);
  const settings = await apiGetSettings();
  // Tous les calculs (coefficients, moyenne de classe, rang, mention) viennent du serveur :
  // le bulletin imprimé, l'écran des notes et le portail parents affichent donc les mêmes chiffres.
  let res;
  try { res = await apiGetBulletinEleve(eleveId, tri, annee); }
  catch (e) { toast(e.message, 'error'); return; }
  const l = res.eleve;
  const statsMat = Object.fromEntries(res.matieres.map(m => [m.matiere, m]));
  const lignesMat = Object.entries(l.moyennes).map(([mat, moy]) => ({ mat, moy, st: statsMat[mat] || {} }))
    .sort((x, y) => x.mat.localeCompare(y.mat));
  const moyGen = l.moyenne_generale;
  const rangText = l.rang != null ? `${l.rang}${l.rang === 1 ? 'er' : 'e'} / ${l.effectif}` : '—';
  const apprec = esc(l.appreciation || '');
  const mention = l.mention || '—';
  const decisionTxt = (tri === 'annee' && l.decision)
    ? ({ admis: `Admis(e) en classe supérieure${l.decision.classe_suivante ? ' (' + esc(l.decision.classe_suivante) + ')' : ''}`,
         redouble: 'Redouble sa classe', exclu: 'Exclu(e)' })[l.decision.decision] : '';

  const bulletinHtml = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Bulletin — ${eleve.prenom} ${eleve.nom}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body{font-family:'Inter',sans-serif;font-size:13px;color:#111;background:#fff;margin:0;padding:20px}
    .header{text-align:center;border-bottom:3px double #1E3A8A;padding-bottom:14px;margin-bottom:18px}
    .header h1{color:#1E3A8A;font-size:20px;margin:0 0 4px}
    .header p{margin:2px 0;color:#555}
    .header img{max-height:60px;margin:0 auto 8px;display:block}
    .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;background:#F9FAFB;padding:12px;border-radius:6px;margin-bottom:16px}
    .info-grid div{font-size:12px}strong{color:#555}
    table{width:100%;border-collapse:collapse;margin-bottom:16px}
    th{background:#1E3A8A;color:#fff;padding:8px 10px;text-align:left;font-size:11px}
    td{padding:8px 10px;border-bottom:1px solid #E5E7EB;font-size:12px}
    tr:nth-child(even) td{background:#F9FAFB}
    .summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:14px;background:#EEF2FF;border-radius:6px;text-align:center;margin-bottom:14px}
    .summary .sl{font-size:10px;color:#555;text-transform:uppercase}
    .summary .sv{font-size:20px;font-weight:700;color:#1E3A8A;font-family:monospace}
    .apprec{background:#FFFBEB;padding:12px;border-radius:6px;font-style:italic;font-size:12px}
    .sig{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:30px}
    .sig div{border-top:1px solid #333;padding-top:8px;text-align:center;font-size:11px}
    @media print{body{padding:0}}
  </style></head><body>
  <div class="doc">
  <div class="header">
    ${settings.ecole_logo?`<img src="${settings.ecole_logo}" alt="Logo">`:''}
    <h1>${settings.ecole_nom||'MY-ECOLE'}</h1>
    ${settings.ecole_adresse?`<p>${settings.ecole_adresse}</p>`:''}
    ${settings.ecole_telephone?`<p>Tél : ${settings.ecole_telephone}</p>`:''}
    <h2 style="margin-top:8px;font-size:15px;color:#374151">BULLETIN DE NOTES — ${libellePeriode}</h2>
    <p style="font-size:12px;color:#555">Année scolaire : ${res.annee_scolaire||settings.annee_scolaire||eleve.annee_scolaire||'—'}</p>
  </div>
  <div class="info-grid">
    <div><strong>Nom & Prénom :</strong> ${eleve.prenom} ${eleve.nom}</div>
    <div><strong>Matricule :</strong> ${eleve.matricule||'—'}</div>
    <div><strong>Classe :</strong> ${eleve.classe||'—'}</div>
    <div><strong>Né(e) le :</strong> ${fmtDate(eleve.date_naissance)} ${eleve.lieu_naissance?'à '+eleve.lieu_naissance:''}</div>
  </div>
  <table>
    <thead><tr><th>Matière</th><th style="text-align:center">Coef.</th><th style="text-align:center">Moyenne /20</th><th style="text-align:center">Moy. classe</th><th style="text-align:center">Min / Max</th></tr></thead>
    <tbody>
      ${lignesMat.length ? lignesMat.map(x => `<tr>
        <td>${esc(x.mat)}</td>
        <td style="text-align:center">${x.st.coefficient ?? 1}</td>
        <td style="text-align:center;font-weight:600;color:${x.moy>=10?'#059669':'#DC2626'}">${x.moy.toFixed(2)}</td>
        <td style="text-align:center">${x.st.moyenne_classe != null ? x.st.moyenne_classe.toFixed(2) : '—'}</td>
        <td style="text-align:center">${x.st.min != null ? x.st.min.toFixed(2) + ' / ' + x.st.max.toFixed(2) : '—'}</td>
      </tr>`).join('') : '<tr><td colspan="5" style="text-align:center;color:#999">Aucune note enregistrée pour cette période</td></tr>'}
    </tbody>
  </table>
  <div class="summary">
    <div><div class="sl">Moy. générale</div><div class="sv" style="color:${moyGen!=null&&moyGen>=10?'#059669':'#DC2626'}">${moyGen!=null?moyGen.toFixed(2)+'/ 20':'—'}</div></div>
    <div><div class="sl">Rang</div><div class="sv">${rangText}</div></div>
    <div><div class="sl">Mention</div><div class="sv" style="font-size:14px">${mention}</div></div>
    <div><div class="sl">Moy. de la classe</div><div class="sv" style="font-size:16px">${res.moyenne_classe != null ? res.moyenne_classe.toFixed(2) : '—'}</div></div>
  </div>
  <div class="apprec"><strong>Appréciation générale :</strong> ${apprec}</div>
  ${decisionTxt ? `<p style="margin:12px 0;font-weight:700;color:#1E3A8A">Décision du conseil de classe : ${decisionTxt}</p>` : ''}
  <div class="sig">
    <div>Le Directeur</div>
    <div>Signature des parents</div>
  </div>
  </div>
  </body></html>`;

  const win = ouvrirDocumentImprimable(bulletinHtml);
  finaliserDocumentPartageable(win, '.doc', {
    filenameBase: `bulletin_${eleve.prenom}_${eleve.nom}_${tri === 'annee' ? 'annuel' : 'T' + tri}`,
    sujetEmail: `Bulletin de notes — ${eleve.prenom} ${eleve.nom} (${tri === 'annee' ? 'année' : 'trimestre ' + tri})`,
    messageEmail: `Veuillez trouver ci-joint le bulletin de notes (${tri === 'annee' ? 'annuel' : 'trimestre ' + tri}).`,
    destinataireDefaut: eleve.email_parent || '',
  });
}
window.imprimerBulletin = imprimerBulletin;

/* ===================== CARTE SCOLAIRE ===================== */
async function imprimerCarteScolaire(eleveId) {
  return imprimerBadgeEleve(eleveId);
}
async function _ancienneCarteScolaire(eleveId) {
  const e = await apiGetEleve(eleveId);
  const settings = await apiGetSettings();
  const contact = e.contact_urgence_nom || e.contact_urgence_telephone
    ? `${e.contact_urgence_nom||''}${e.contact_urgence_nom&&e.contact_urgence_telephone?' — ':''}${e.contact_urgence_telephone||''}`
    : (e.pere_telephone || e.mere_telephone || e.tuteur_telephone || '—');
  const ecoleNomAffiche = settings.ecole_nom || "MY-ECOLE";
  const ecoleLieuAffiche = settings.ecole_adresse || "Yattaya · Commune de Sonfonia";

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Carte scolaire — ${e.prenom} ${e.nom}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Mono:wght@500&family=Nunito+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box}
    body{font-family:'Nunito Sans',Arial,sans-serif;margin:0;padding:24px;background:#E8E4DC;display:flex;justify-content:center;align-items:flex-start}
    .carte{width:7cm;min-height:12cm;background:#F4EFE2;position:relative;overflow:hidden;border-radius:0.28cm;
      box-shadow:0 0.3cm 0.7cm rgba(30,25,15,.3);border:1px solid #D8D0BC;
      background-image:radial-gradient(#DCD5C2 0.4px, transparent 0.4px);background-size:8px 8px;
      display:flex;flex-direction:column}
    .flag-bar{height:4.5%;display:flex;flex-shrink:0}
    .flag-bar div{flex:1}
    .header{text-align:center;padding:5% 6% 3%;border-bottom:1px solid #B91C1C;flex-shrink:0}
    .header .pays{font-family:'Playfair Display',serif;font-size:14px;font-weight:700;color:#1E2A4A;letter-spacing:.02em}
    .header .devise{font-family:'Playfair Display',serif;font-style:italic;font-size:9.5px;color:#7A5416;margin-top:1px}
    .header .ministere{font-size:9px;font-weight:700;color:#3A3A3A;margin-top:5px;letter-spacing:.03em}
    .titre-carte-wrap{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:8px}
    .titre-carte-wrap .ln{height:1px;width:22px;background:#B91C1C}
    .header .titre-carte{font-size:12.5px;font-weight:800;color:#B91C1C;letter-spacing:.18em}
    .header .ecole-nom{font-family:'Playfair Display',serif;font-size:13px;font-weight:700;color:#1E2A4A;margin-top:8px;line-height:1.25}
    .header .ecole-lieu{font-size:9px;color:#000;font-weight:600;margin-top:2px;letter-spacing:.03em}
    .header .ecole-tel{font-size:8.5px;color:#000;font-weight:600;margin-top:1px;letter-spacing:.03em}
    .corps{padding:6% 6% 2%;display:flex;gap:10px;flex:1;position:relative}
    .photo-frame{width:42%;aspect-ratio:3/3.8;background:#fff;border:1.5px solid #1E2A4A;border-radius:3px;
      display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;position:relative}
    .photo-frame img{width:100%;height:100%;object-fit:cover;object-position:center top}
    .photo-frame .no-photo{color:#D1D5DB;width:100%;height:100%;display:flex;align-items:center;justify-content:center}
    .infos{flex:1;display:flex;flex-direction:column;justify-content:center;gap:9px;padding-top:2%}
    .infos .lbl{font-size:8.5px;color:#7A5416;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
    .infos .val{font-family:'Playfair Display',serif;font-weight:700;font-size:14px;color:#1E2A4A;margin-top:1px}
    .sig-line{position:absolute;left:6%;bottom:3%;width:38%;border-top:1px solid #B8AF95}
    .matricule-bar{background:#1E2A4A;color:#fff;display:flex;align-items:center;justify-content:space-between;
      padding:2.5% 6%;flex-shrink:0;margin-top:auto}
    .matricule-bar .lbl{font-size:9px;letter-spacing:.08em;font-weight:600;color:#DCE4F2}
    .matricule-bar .val{font-family:'DM Mono',monospace;font-size:15px;letter-spacing:.06em}
    .footer-info{padding:4% 6%;font-size:9px;color:#000;flex-shrink:0}
    .footer-info .lbl{font-size:7.5px;color:#000;font-weight:800;text-transform:uppercase;letter-spacing:.04em}
    .footer-info .fval{font-weight:700;margin-bottom:5px;font-size:9.5px;color:#000}
    .mention{padding:0 6% 3%;display:flex;justify-content:space-between;align-items:flex-end;gap:6px;flex-shrink:0}
    .mention .txt{font-size:6.8px;color:#5A5039;line-height:1.4;font-style:italic}
    .mention .directeur{text-align:center;font-size:7.5px;color:#3A3A3A;flex-shrink:0}
    .mention .directeur .cachet-img{max-height:24px;max-width:38px;display:block;margin:0 auto 1px}
    .mention .directeur .signature-img{max-height:14px;max-width:38px;display:block;margin:0 auto 1px}
    .mention .directeur .ln{border-top:1px solid #B8AF95;width:26px;margin:0 auto 3px}
    @media print{
      @page{ size:7cm 12cm; margin:0; }
      body{background:#fff;padding:0;align-items:stretch}
      .carte{box-shadow:none;border:none;border-radius:0}
    }
  </style></head><body>
  <div class="carte">
    <div class="flag-bar"><div style="background:#1E2A4A"></div><div style="background:#F39200"></div><div style="background:#1E2A4A"></div></div>
    <div class="header">
      ${settings.ecole_logo ? `<img src="${esc(settings.ecole_logo)}" alt="" style="height:1.9cm;width:1.9cm;object-fit:contain;display:block;margin:0 auto 2px">` : ''}
      <div class="titre-carte-wrap"><div class="ln"></div><div class="titre-carte">CARTE SCOLAIRE</div><div class="ln"></div></div>
      <div class="ecole-nom">${esc(ecoleNomAffiche)}</div>
      <div class="ecole-lieu">${esc(ecoleLieuAffiche)}</div>
      ${settings.ecole_telephone ? `<div class="ecole-tel">Tél : ${esc(settings.ecole_telephone)}</div>` : ''}
    </div>
    <div class="corps">
      <div class="photo-frame">
        ${e.photo_url?`<img src="${esc(e.photo_url)}">`:'<div class="no-photo"><svg viewBox="0 0 24 24" fill="currentColor" width="60%" height="60%"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-9 2.2-9 5v2h18v-2c0-2.8-4.6-5-9-5z"/></svg></div>'}
      </div>
      <div class="infos">
        <div><div class="lbl">Prénom(s)</div><div class="val">${esc(e.prenom)}</div></div>
        <div><div class="lbl">Nom</div><div class="val">${esc((e.nom||'').toUpperCase())}</div></div>
        <div><div class="lbl">Classe</div><div class="val">${esc(e.classe||'—')}</div></div>
      </div>
      <div class="sig-line"></div>
    </div>
    <div class="matricule-bar"><span class="lbl">MATRICULE</span><span class="val">${esc(e.matricule||'—')}</span></div>
    <div class="footer-info">
      <div class="lbl">Date et lieu de naissance</div>
      <div class="fval">${fmtDate(e.date_naissance)}${e.lieu_naissance?' à '+esc(e.lieu_naissance):''}</div>
      <div class="lbl">Contact d'urgence</div>
      <div class="fval" style="margin-bottom:0">${esc(contact)}</div>
    </div>
    <div class="mention">
      <div class="txt">Valable pour l'année scolaire en cours.<br>Propriété du ${esc(ecoleNomAffiche)}.</div>
      <div class="directeur">
        ${settings.ecole_cachet?`<img class="cachet-img" src="${settings.ecole_cachet}">`:''}
        ${settings.signature_directeur?`<img class="signature-img" src="${settings.signature_directeur}">`:''}
        <div class="ln"></div>Le Directeur
      </div>
    </div>
  </div>
  </body></html>`;

  const win = ouvrirDocumentImprimable(html);
  finaliserCarteImprimable(win, '.carte', `carte_scolaire_${(e.matricule||e.nom||'eleve')}.png`);
}
window.imprimerCarteScolaire = imprimerCarteScolaire;


/* ===================== BADGE ÉLÈVE SÉCURISÉ =====================
   Carte au format ID-1 (8,56 × 5,40 cm), recto/verso. Éléments de sécurité :
   fond guilloché, photo + photo fantôme, micro-texte, hologramme, QR code signé (vérifiable en ligne),
   ligne lisible par machine, numéro de série et date d'expiration. */
function _guilloche(couleur, w, h) {
  let d = '';
  for (let i = 0; i < 26; i++) {
    const ph = i * 0.42, amp = 5 + (i % 5) * 1.6, y0 = h * (0.04 + i * 0.037);
    let path = '';
    for (let x = 0; x <= w; x += 4) {
      const y = y0 + Math.sin(x / 11 + ph) * amp + Math.sin(x / 27 + ph * 1.7) * amp * 0.7;
      path += (x ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    }
    d += `<path d="${path}" fill="none" stroke="${couleur}" stroke-width=".35" opacity="${(0.22 + (i % 3) * 0.08).toFixed(2)}"/>`;
  }
  let ros = '';
  for (let k = 0; k < 14; k++) ros += `<ellipse cx="0" cy="0" rx="26" ry="9" transform="rotate(${k * 12.857})" fill="none" stroke="${couleur}" stroke-width=".3" opacity=".3"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%">${d}<g transform="translate(${w * 0.72} ${h * 0.55})">${ros}</g></svg>`;
}
function _microtexte(texte, largeur, id) {
  const t = (texte + ' • ').repeat(40);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${largeur} 3" style="display:block;width:100%;height:.12cm"><text x="0" y="2.3" font-size="2.2" font-family="Arial" fill="#1b3a5c" textLength="${largeur}" lengthAdjust="spacing">${t.replace(/&/g,'&amp;')}</text></svg>`;
}
function _ligneMachine(s, n = 34) {
  return String(s).toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Z0-9]+/g, '<').padEnd(n, '<').slice(0, n);
}

async function imprimerBadgeEleve(eleveId) {
  const [e, settings, sec] = await Promise.all([apiGetEleve(eleveId), apiGetSettings(), apiBadgeSecurise(eleveId)]);
  const ecole = settings.ecole_nom || 'MY-ECOLE';
  const lieu = (settings.ecole_adresse || '').replace(/[,;\s-]*république de guinée/i, '').trim();
  const initiales = ecole.split(/\s+/).filter(m => m.length > 2).map(m => m[0]).join('').slice(0, 3).toUpperCase() || 'ME';
  // La fenêtre d'impression est une page « blob: » : les adresses relatives (/uploads/…) n'y
  // fonctionnent pas, d'où le logo ou la photo manquants. On les rend absolues.
  const absolue = u => !u ? '' : esc(/^(data:|https?:|blob:)/i.test(u) ? u : window.location.origin + (u.startsWith('/') ? '' : '/') + u);
  const photo = absolue(e.photo_url);
  const logo = absolue(settings.ecole_logo);
  const nomMaj = (e.nom || '').toUpperCase();
  const expireFr = fmtDate(sec.expire);
  const mrz1 = _ligneMachine(`BDG<${nomMaj}<<${e.prenom || ''}`);
  const mrz2 = _ligneMachine(`${e.matricule || ''}<${(sec.annee || '').replace(/\D/g, '')}<${(e.classe || '')}<${sec.signature.slice(0, 6)}`);
  const silhouette = '<svg viewBox="0 0 24 24" fill="#9aa8b8" width="70%" height="70%"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-9 2.2-9 5v2h18v-2c0-2.8-4.6-5-9-5z"/></svg>';
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Badge — ${esc(e.prenom)} ${esc(e.nom)}</title>
  <link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&family=DM+Mono:wght@500&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box}
    body{font-family:'Nunito Sans',Arial,sans-serif;margin:0;padding:24px;background:#dfe5ec}
    .planche{display:flex;flex-direction:column;gap:.6cm;align-items:center}
    .carte{width:8.56cm;height:5.4cm;position:relative;overflow:hidden;border-radius:.32cm;background:#f6fbfb;
      border:1px solid #b9c8d6;box-shadow:0 .2cm .5cm rgba(20,40,60,.28)}
    .fond{position:absolute;inset:0;background:linear-gradient(115deg,#eaf6f6 0%,#f7f3e6 52%,#e8eef9 100%)}
    .arc-en-ciel{position:absolute;left:0;right:0;top:0;height:.16cm;background:linear-gradient(90deg,#1b6ca8,#12a594,#e8b923,#e2574c,#8e5bd0,#1b6ca8)}
    .entete{position:absolute;left:.3cm;right:.3cm;top:.26cm;display:flex;justify-content:space-between;align-items:flex-start}
    .logo-ec{mix-blend-mode:multiply;height:.78cm;width:.78cm;object-fit:contain;flex-shrink:0;margin-right:.15cm}
    .filigrane-logo{mix-blend-mode:multiply;position:absolute;left:3.9cm;top:1.2cm;width:2.6cm;height:2.6cm;object-fit:contain;opacity:.07}
    .entete .ec{font-weight:800;font-size:9.5px;color:#12365a;line-height:1.1;max-width:5.3cm}
    .entete .sc{font-size:6px;color:#4a5d70;font-weight:700;letter-spacing:.06em;margin-top:1px}
    .titre{font-size:7px;font-weight:800;letter-spacing:.2em;color:#0f7a6c;text-align:right}
    .micro{position:absolute;left:.3cm;right:.3cm}
    .photo{position:absolute;left:.3cm;top:1.2cm;width:2.05cm;height:2.6cm;border:1.2px solid #12365a;border-radius:2px;background:#fff;overflow:hidden;display:flex;align-items:center;justify-content:center}
    .photo img{width:100%;height:100%;object-fit:cover;object-position:center top}
    .fantome{position:absolute;left:2.5cm;top:2.5cm;width:1.05cm;height:1.3cm;border-radius:2px;overflow:hidden;opacity:.55;filter:grayscale(1) contrast(1.1);border:.5px solid #9fb0c2;background:#fff}
    .fantome img{width:100%;height:100%;object-fit:cover;object-position:center top}
    .fantome-grand{position:absolute;right:.35cm;top:1.05cm;width:2.6cm;height:3.1cm;opacity:.10;filter:grayscale(1)}
    .fantome-grand img{width:100%;height:100%;object-fit:cover;object-position:center top}
    .infos{position:absolute;left:3.7cm;top:1.2cm;right:1.9cm;display:grid;gap:.13cm}
    .lbl{font-size:5.2px;color:#0f7a6c;font-weight:800;letter-spacing:.07em;text-transform:uppercase}
    .val{font-size:10.5px;font-weight:800;color:#12365a;line-height:1.1;overflow-wrap:anywhere}
    .val.p{font-size:9px;font-weight:700}
    .deux{display:flex;gap:.3cm}
    .holo{position:absolute;right:.33cm;bottom:1.42cm;width:1.25cm;height:1.25cm;border-radius:50%;
      background:linear-gradient(135deg,#ff7ac6 0%,#ffd86b 22%,#7dffb8 45%,#63c7ff 68%,#b58cff 100%);
      border:.6px solid rgba(255,255,255,.9);box-shadow:inset 0 0 .22cm rgba(255,255,255,.9);display:flex;align-items:center;justify-content:center;overflow:hidden}
    .holo:before{content:'';position:absolute;inset:0;background:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 1px,transparent 1px 3px);mix-blend-mode:overlay}
    .holo span{position:relative;font-weight:800;font-size:8px;color:#12365a;letter-spacing:.03em;text-shadow:0 0 2px #fff}
    .serie{position:absolute;left:.3cm;bottom:1.05cm;font-family:'DM Mono',monospace;font-size:7px;color:#12365a}
    .mrz{position:absolute;left:0;right:0;bottom:0;height:.88cm;background:rgba(255,255,255,.82);padding:.08cm .3cm;font-family:'DM Mono','Courier New',monospace;font-size:7px;letter-spacing:.07em;color:#111;line-height:1.35;border-top:.5px solid #b9c8d6}
    .valid{position:absolute;left:3.7cm;bottom:1.05cm;font-size:6px;color:#4a5d70;font-weight:700}
    .verso .qr{position:absolute;left:.35cm;top:.55cm;width:2.5cm;height:2.5cm;background:#fff;padding:.1cm;border:.6px solid #12365a;border-radius:3px}
    .verso .qr svg{width:100%;height:100%}
    .verso .txt{position:absolute;left:3.1cm;right:.35cm;top:.4cm;font-size:6.1px;color:#1f2f40;line-height:1.45}
    .verso .txt b{color:#12365a}
    .verso .urgence{position:absolute;left:.35cm;right:2.9cm;top:3.2cm;font-size:7px;color:#1f2f40;line-height:1.4}
    .verso .sig{position:absolute;right:.35cm;top:3.3cm;width:2.4cm;text-align:center;font-size:5.5px;color:#4a5d70}
    .verso .sig img{max-height:.7cm;max-width:2.1cm;display:block;margin:0 auto 1px}
    .verso .sig .ln{border-top:.5px solid #8a9aab;margin-bottom:1px}
    .verso .pied{position:absolute;left:.35cm;right:.35cm;bottom:.22cm;font-size:5.4px;color:#4a5d70;text-align:center}
    @media print{
      @page{size:8.56cm 5.4cm;margin:0}
      body{background:#fff;padding:0}
      .planche{gap:0;display:block}
      .carte{box-shadow:none;border:none;border-radius:0;page-break-after:always;break-after:page}
      .carte:last-child{page-break-after:auto;break-after:auto}
    }
  </style></head><body><div class="planche">
  <div class="carte recto">
    <div class="fond"></div>${_guilloche('#2f8f9d', 160, 100)}
    <div class="arc-en-ciel"></div>
    <div class="entete"><div style="display:flex;align-items:center">${logo?`<img class="logo-ec" src="${logo}" alt="">`:''}<div><div class="ec">${esc(ecole)}</div><div class="sc">${esc(lieu)}</div></div></div><div class="titre">BADGE ÉLÈVE<br>${esc(sec.annee||'')}</div></div>
    <div class="micro" style="top:.95cm">${_microtexte(ecole.toUpperCase() + ' • BADGE ÉLÈVE • ' + (sec.annee||''), 400)}</div>
    ${logo ? `<img class="filigrane-logo" src="${logo}" alt="">` : ''}
    ${photo ? `<div class="fantome-grand"><img src="${photo}"></div>` : ''}
    <div class="photo">${photo ? `<img src="${photo}">` : silhouette}</div>
    ${photo ? `<div class="fantome"><img src="${photo}"></div>` : ''}
    <div class="infos">
      <div><div class="lbl">Nom</div><div class="val">${esc(nomMaj)}</div></div>
      <div><div class="lbl">Prénom(s)</div><div class="val p">${esc(e.prenom||'')}</div></div>
      <div class="deux"><div><div class="lbl">Classe</div><div class="val p">${esc(e.classe||'—')}</div></div>
        <div><div class="lbl">Né(e) le</div><div class="val p">${fmtDate(e.date_naissance)}</div></div></div>
      <div><div class="lbl">Matricule</div><div class="val p" style="font-family:'DM Mono',monospace">${esc(e.matricule||'—')}</div></div>
    </div>
    <div class="holo"><span>${esc(initiales)}</span></div>
    <div class="serie">N° ${esc(sec.numero)}</div>
    <div class="valid">Expire le ${esc(expireFr)}</div>
    <div class="mrz">${esc(mrz1)}<br>${esc(mrz2)}</div>
  </div>
  <div class="carte verso">
    <div class="fond"></div>${_guilloche('#7a8fc4', 160, 100)}
    <div class="arc-en-ciel"></div>
    ${logo ? `<img src="${logo}" alt="" style="mix-blend-mode:multiply;position:absolute;right:.35cm;bottom:.55cm;width:1.1cm;height:1.1cm;object-fit:contain">` : ''}
    <div class="qr">${sec.qr_svg}</div>
    <div class="txt"><b>Vérifier l'authenticité :</b> scannez le QR code avec un téléphone. Une page officielle de ${esc(ecole)} confirme l'identité et la validité du badge. Un badge dont le QR ne confirme pas l'identité affichée est un faux.<br><br>
      <b>Contrôle manuel</b> sur le site de l'école, rubrique « Vérifier un badge » : matricule <b>${esc(e.matricule||'')}</b> · code <b>${esc(sec.code_controle||'')}</b><br><br>
      <b>Valable</b> pour l'année scolaire ${esc(sec.annee||'en cours')} — jusqu'au ${esc(expireFr)}.</div>
    <div class="urgence"><b>En cas d'urgence :</b> ${esc([e.contact_urgence_nom, e.contact_urgence_telephone].filter(Boolean).join(' — ') || e.pere_telephone || e.mere_telephone || e.tuteur_telephone || '—')}<br>
      <b>Si trouvé, merci de le rapporter à :</b> ${esc(ecole)}${settings.ecole_telephone?' — Tél '+esc(settings.ecole_telephone):''}</div>
    <div class="sig">${settings.signature_directeur?`<img src="${settings.signature_directeur}">`:''}<div class="ln"></div>Le Directeur</div>
    <div class="micro" style="bottom:.48cm">${_microtexte(ecole.toUpperCase() + ' • DOCUMENT PERSONNEL ET NON CESSIBLE', 400)}</div>
    <div class="pied">Document personnel et non cessible — ${esc(sec.numero)}</div>
  </div>
  </div></body></html>`;
  const win = ouvrirDocumentImprimable(html);
  finaliserCarteImprimable(win, '.planche', `badge_${(e.matricule||e.nom||'eleve')}.png`);
}
window.imprimerBadgeEleve = imprimerBadgeEleve;

/* ── Carte de retrait (maternelle) : identifie les personnes autorisées à venir
   chercher l'enfant à la sortie des classes. Basée sur les contacts déjà
   enregistrés (père, mère, tuteur, contact d'urgence). ── */
async function imprimerCarteRetrait(eleveId) {
  const e = await apiGetEleve(eleveId);
  const settings = await apiGetSettings();
  const ecoleNomAffiche = settings.ecole_nom || "MY-ECOLE";

  const personnes = [
    e.pere_nom ? { role: 'Père', nom: e.pere_nom, tel: e.pere_telephone } : null,
    e.mere_nom ? { role: 'Mère', nom: e.mere_nom, tel: e.mere_telephone } : null,
    e.tuteur_nom ? { role: 'Tuteur/Tutrice', nom: e.tuteur_nom, tel: e.tuteur_telephone } : null,
    e.contact_urgence_nom ? { role: "Contact d'urgence", nom: e.contact_urgence_nom, tel: e.contact_urgence_telephone } : null,
  ].filter(Boolean);

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Carte de retrait — ${e.prenom} ${e.nom}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Nunito+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box}
    body{font-family:'Nunito Sans',Arial,sans-serif;margin:0;padding:24px;background:#E8E4DC;display:flex;justify-content:center;align-items:flex-start}
    .carte{width:9cm;min-height:13.5cm;background:#FFF9EC;position:relative;overflow:hidden;border-radius:0.4cm;
      box-shadow:0 0.3cm 0.7cm rgba(30,25,15,.3);border:2px solid #F5A623;display:flex;flex-direction:column}
    .banniere{background:#F5A623;color:#fff;text-align:center;padding:14px 10px 10px;flex-shrink:0}
    .banniere .titre{font-family:'Playfair Display',serif;font-size:20px;font-weight:700;letter-spacing:.02em}
    .banniere .soustitre{font-size:12px;font-weight:600;margin-top:3px;opacity:.95}
    .ecole{text-align:center;padding:12px 14px 6px;border-bottom:2px dashed #E8C27A;flex-shrink:0}
    .ecole .nom{font-family:'Playfair Display',serif;font-size:15px;font-weight:700;color:#8A4B00}
    .ecole .lieu{font-size:11px;color:#7A6A50;margin-top:2px}
    .corps{display:flex;gap:14px;padding:16px 16px 8px;flex-shrink:0}
    .photo-frame{width:2.6cm;height:3.1cm;background:#fff;border:2px solid #F5A623;border-radius:6px;
      display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0}
    .photo-frame img{width:100%;height:100%;object-fit:cover}
    .photo-frame .no-photo{color:#E8C27A;width:100%;height:100%;display:flex;align-items:center;justify-content:center}
    .infos{flex:1;display:flex;flex-direction:column;justify-content:center;gap:8px}
    .infos .lbl{font-size:10px;color:#B8860B;font-weight:800;text-transform:uppercase;letter-spacing:.05em}
    .infos .val{font-family:'Playfair Display',serif;font-weight:700;font-size:16px;color:#4A3A20;margin-top:1px}
    .section-titre{background:#4A3A20;color:#FFF3D6;font-size:12.5px;font-weight:800;letter-spacing:.06em;
      text-transform:uppercase;padding:8px 16px;margin-top:6px;flex-shrink:0}
    .personnes{padding:10px 16px;flex:1;overflow:hidden}
    .personne{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #EEDFC0}
    .personne:last-child{border-bottom:none}
    .personne .role{font-size:11.5px;color:#B8860B;font-weight:800;text-transform:uppercase;letter-spacing:.03em;min-width:2.6cm}
    .personne .nom{font-size:14px;font-weight:700;color:#3A2E18;flex:1}
    .personne .tel{font-family:'DM Mono',monospace;font-size:12px;color:#4A3A20;font-weight:600}
    .aucune{font-size:12px;color:#A9835A;font-style:italic;padding:10px 0}
    .avertissement{background:#FFF3D6;margin:8px 16px;padding:10px 12px;border-radius:8px;border:1.5px solid #F5A623;
      font-size:11px;color:#6B4A00;font-weight:700;text-align:center;line-height:1.4;flex-shrink:0}
    .footer{padding:8px 16px 14px;font-size:9.5px;color:#8A7A5A;text-align:center;flex-shrink:0}
    @media print{
      @page{ size:9cm 13.5cm; margin:0; }
      body{background:#fff;padding:0;align-items:stretch}
      .carte{box-shadow:none;border-radius:0}
    }
  </style></head><body>
  <div class="carte">
    <div class="banniere">
      <div class="titre">🧸 CARTE DE RETRAIT</div>
      <div class="soustitre">Section Maternelle</div>
    </div>
    <div class="ecole">
      <div class="nom">${esc(ecoleNomAffiche)}</div>
      <div class="lieu">${esc(settings.ecole_adresse || 'Yattaya · Commune de Ratoma')}</div>
    </div>
    <div class="corps">
      <div class="photo-frame">
        ${e.photo_url?`<img src="${esc(e.photo_url)}">`:'<div class="no-photo"><svg viewBox="0 0 24 24" fill="currentColor" width="60%" height="60%"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-9 2.2-9 5v2h18v-2c0-2.8-4.6-5-9-5z"/></svg></div>'}
      </div>
      <div class="infos">
        <div><div class="lbl">Enfant</div><div class="val">${esc(e.prenom)} ${esc((e.nom||'').toUpperCase())}</div></div>
        <div><div class="lbl">Classe</div><div class="val">${esc(e.classe||'—')}</div></div>
      </div>
    </div>
    <div class="section-titre">Personnes autorisées à récupérer l'enfant</div>
    <div class="personnes">
      ${personnes.length ? personnes.map(p=>`<div class="personne">
        <span class="role">${esc(p.role)}</span>
        <span class="nom">${esc(p.nom)}</span>
        <span class="tel">${esc(p.tel||'—')}</span>
      </div>`).join('') : '<div class="aucune">Aucune personne enregistrée — veuillez compléter le dossier de l\'élève.</div>'}
    </div>
    <div class="avertissement">⚠ Cette carte doit être présentée à chaque sortie.<br>Aucun enfant ne sera remis à une personne non listée ci-dessus sans autorisation écrite.</div>
    <div class="footer">Valable pour l'année scolaire ${esc(settings.annee_scolaire||'en cours')} — ${esc(ecoleNomAffiche)}</div>
  </div>
  </body></html>`;

  const win = ouvrirDocumentImprimable(html);
  finaliserCarteImprimable(win, '.carte', `carte_retrait_${(e.matricule||e.nom||'eleve')}.png`);
}
window.imprimerCarteRetrait = imprimerCarteRetrait;

/* ── Validation de la préinscription (point 7 : par le comptable après paiement) ── */
function modalValiderPreinscription(eleveId, nom) {
  openModal(`✔ Valider la préinscription — ${nom}`, `
    <div class="alert alert-info">Cet élève passera au statut <strong>Actif</strong> une fois cette préinscription validée.</div>
    <form id="f-validpre" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Montant des frais d'inscription/réinscription reçu (GNF)</label>
        <input type="number" name="montant" min="0" step="1" placeholder="Laisser vide si non applicable">
      </div>
      <div class="form-2">
        <div class="fg"><label>Date du paiement</label><input type="date" name="date_paiement" value="${today()}"></div>
        <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
      </div>
      <div class="fg"><label>Référence / N° reçu</label><input name="reference" placeholder="REC-001…"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-ok">✔ Valider la préinscription</button>
      </div>
    </form>`, { narrow: true });
  $('#f-validpre').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (fd.montant) fd.montant = parseFloat(fd.montant); else delete fd.montant;
    try {
      const resultat = await apiValiderPreinscription(eleveId, fd);
      toast('Préinscription validée ✅ — Élève actif','success');
      closeModal();
      if (fd.montant) {
        imprimerRecu({
          type: 'entree', nom, description: "Frais d'inscription", montant: fd.montant,
          date: fd.date_paiement, moyenPaiement: fd.moyen_paiement, reference: resultat?.numero_recu || fd.reference,
          recuPar: currentUser?.full_name,
        });
      }
      pageEleves();
    } catch(err) { toast(err.message,'error'); }
  };
}
window.modalValiderPreinscription = modalValiderPreinscription;


/* ===================== IMPORT D'ÉLÈVES (Excel / CSV) ===================== */
function modalImportEleves() {
  openModal('Importer des élèves', `
    <p class="text-muted" style="font-size:13px">Reprenez vos listes existantes : un fichier Excel (.xlsx) ou CSV avec une ligne de titres
      (au minimum <strong>Nom</strong> et <strong>Prénom</strong> ; aussi : Date de naissance, Sexe, Classe, Père, Téléphone père, Mère, Téléphone mère, Adresse…).
      Les classes doivent déjà exister. Rien n'est enregistré avant votre confirmation.</p>
    <p><a href="#" id="imp-modele">⬇ Télécharger le fichier modèle</a></p>
    <div class="fg"><label>Fichier</label><input type="file" id="imp-fichier" accept=".xlsx,.csv"></div>
    <div id="imp-resultat" style="margin-top:12px"></div>
    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button>
      <button type="button" class="btn btn-outline" id="imp-verifier">🔍 Vérifier le fichier</button>
      <button type="button" class="btn btn-primary" id="imp-confirmer" disabled>Importer</button>
    </div>`, { wide: true });
  $('#imp-modele').onclick = e => { e.preventDefault(); apiTelechargerFichier('/import-eleves/modele', 'modele-import-eleves.csv'); };
  const zone = $('#imp-resultat');
  const fichier = () => $('#imp-fichier').files[0];
  const afficher = r => {
    const err = r.erreurs.map(p => `<li>Ligne ${p.ligne}${p.nom ? ' (' + esc(p.nom) + ')' : ''} : ${p.erreurs.map(esc).join(' ; ')}</li>`).join('');
    const dbl = r.doublons.map(d => `<li>Ligne ${d.ligne} : ${esc(d.nom)}</li>`).join('');
    zone.innerHTML = `
      <div class="alert ${r.importes ? 'alert-success' : 'alert-info'}">
        ${r.simulation ? '<strong>Vérification :</strong> ' : '<strong>Terminé :</strong> '}
        ${r.lignes_lues} ligne(s) lue(s) — <strong>${r.simulation ? r.a_importer + ' prête(s) à importer' : r.importes + ' élève(s) importé(s)'}</strong>,
        ${r.erreurs.length} en erreur, ${r.doublons.length} déjà présent(s).</div>
      ${err ? `<details open><summary>Lignes en erreur (ignorées)</summary><ul style="font-size:12px">${err}</ul></details>` : ''}
      ${dbl ? `<details><summary>Élèves déjà présents (ignorés)</summary><ul style="font-size:12px">${dbl}</ul></details>` : ''}`;
  };
  $('#imp-fichier').onchange = () => { $('#imp-confirmer').disabled = true; zone.innerHTML = ''; };
  $('#imp-verifier').onclick = async () => {
    if (!fichier()) { toast('Choisissez un fichier', 'error'); return; }
    try { const r = await apiImporterEleves(fichier(), true); afficher(r); $('#imp-confirmer').disabled = r.a_importer === 0; }
    catch (e) { zone.innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
  };
  $('#imp-confirmer').onclick = async () => {
    $('#imp-confirmer').disabled = true;
    try { const r = await apiImporterEleves(fichier(), false); afficher(r); toast(`${r.importes} élève(s) importé(s)`, 'success'); _elevesList = await apiGetEleves(); renderElevesTable(_elevesList); }
    catch (e) { toast(e.message, 'error'); }
  };
}
window.modalImportEleves = modalImportEleves;

/* ===================== ATTESTATION DE SCOLARITÉ ===================== */
async function imprimerAttestation(eleveId) {
  let att;
  try { att = await apiDelivrerAttestation(eleveId); } catch (e) { toast(e.message, 'error'); return; }
  const e = att.eleve, settings = await apiGetSettings();
  const dateFr = iso => iso ? new Date(iso + 'T00:00:00').toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : '—';
  const annee = settings.annee_scolaire || e.annee_scolaire || '—';
  const sexeF = e.sexe === 'F';
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Attestation de scolarité — ${esc(e.prenom)} ${esc(e.nom)}</title>
  <style>
    body{font-family:Georgia,'Times New Roman',serif;color:#111;margin:0;padding:40px;background:#fff}
    .doc{max-width:720px;margin:0 auto}
    .header{text-align:center;border-bottom:3px double #1E3A8A;padding-bottom:14px;margin-bottom:34px}
    .header h1{color:#1E3A8A;font-size:22px;margin:0 0 4px}.header p{margin:2px 0;color:#555;font-size:13px}
    .header img{max-height:70px;display:block;margin:0 auto 8px}
    h2{text-align:center;letter-spacing:2px;font-size:20px;margin:0 0 6px}
    .ref{text-align:center;font-size:13px;color:#555;margin-bottom:34px}
    p.corps{font-size:16px;line-height:1.9;text-align:justify}
    .sig{display:flex;justify-content:space-between;margin-top:60px;font-size:14px}
    .sig div{width:45%;text-align:center}.sig .ligne{margin-top:60px;border-top:1px solid #333;padding-top:6px;font-size:12px;color:#555}
    .pied{margin-top:40px;font-size:11px;color:#777;text-align:center;border-top:1px solid #ddd;padding-top:8px}
    @media print{body{padding:20px}}
  </style></head><body><div class="doc">
  <div class="header">
    ${settings.ecole_logo ? `<img src="${settings.ecole_logo}" alt="Logo">` : ''}
    <h1>${esc(settings.ecole_nom || 'MY-ECOLE')}</h1>
    ${settings.ecole_adresse ? `<p>${esc(settings.ecole_adresse)}</p>` : ''}
    ${settings.ecole_telephone ? `<p>Tél : ${esc(settings.ecole_telephone)}</p>` : ''}
  </div>
  <h2>ATTESTATION DE SCOLARITÉ</h2>
  <div class="ref">N° ${esc(att.numero)}</div>
  <p class="corps">Je soussigné(e), Directeur(trice) de <strong>${esc(settings.ecole_nom || "l'établissement")}</strong>, atteste que
    ${sexeF ? 'l\'élève' : 'l\'élève'} <strong>${esc(e.prenom)} ${esc((e.nom || '').toUpperCase())}</strong>,
    ${sexeF ? 'née' : 'né'} le <strong>${dateFr(e.date_naissance)}</strong>${e.lieu_naissance ? ' à <strong>' + esc(e.lieu_naissance) + '</strong>' : ''},
    matricule <strong>${esc(e.matricule || '—')}</strong>, est régulièrement ${sexeF ? 'inscrite' : 'inscrit'} dans notre établissement
    en classe de <strong>${esc(e.classe || '—')}</strong> pour l'année scolaire <strong>${esc(annee)}</strong>.</p>
  <p class="corps">La présente attestation est délivrée à l'intéressé(e) pour servir et valoir ce que de droit.</p>
  <div class="sig"><div>Fait à ${esc((settings.ecole_adresse || '').split(',').pop().trim() || '………………')}, le ${dateFr(att.date)}</div>
    <div>Le Directeur<div class="ligne">Signature et cachet</div></div></div>
  <div class="pied">Attestation n° ${esc(att.numero)} — enregistrée dans le registre de l'établissement</div>
  </div></body></html>`;
  const win = ouvrirDocumentImprimable(html);
  finaliserDocumentPartageable(win, '.doc', {
    filenameBase: `attestation_${e.prenom}_${e.nom}`.replace(/\s+/g, '_'),
    sujetEmail: `Attestation de scolarité — ${e.prenom} ${e.nom}`,
    messageEmail: 'Veuillez trouver ci-joint l\'attestation de scolarité.',
    destinataireDefaut: e.email_parent || '',
  });
}
window.imprimerAttestation = imprimerAttestation;


/* ===================== PARCOURS SCOLAIRE (historique pluriannuel) ===================== */
async function modalParcours(eleveId) {
  let p;
  try { p = await apiGetParcours(eleveId); } catch (e) { toast(e.message, 'error'); return; }
  const lib = { admis: '✅ Admis(e)', redouble: '🔁 Redouble', exclu: '⛔ Exclu(e)' };
  openModal(`Parcours scolaire — ${p.eleve.prenom} ${p.eleve.nom}`, `
    <p class="text-muted" style="font-size:12px">Classe actuelle : <strong>${esc(p.eleve.classe || '—')}</strong> · Décisions du conseil de classe enregistrées, année par année.</p>
    ${p.annees.length ? `<div class="tbl-wrap"><table><thead><tr><th>Année</th><th>Classe</th><th>Moyenne annuelle</th><th>Décision</th><th>Classe suivante</th></tr></thead><tbody>
      ${p.annees.map(a => `<tr><td>${esc(a.annee_scolaire)}</td><td>${esc(a.classe_origine)}</td><td>${a.moyenne_annuelle != null ? a.moyenne_annuelle.toFixed(2) + ' / 20' : '—'}</td>
        <td>${lib[a.decision] || esc(a.decision)}</td><td>${esc(a.classe_suivante || '—')}</td></tr>`).join('')}</tbody></table></div>`
      : '<p class="empty">Aucune décision de fin d\'année enregistrée pour cet élève.</p>'}
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>`);
}
window.modalParcours = modalParcours;
