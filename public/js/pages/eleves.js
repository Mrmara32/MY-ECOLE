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
      <button class="btn btn-primary btn-sm" onclick="modalEleve()">+ Inscrire un élève</button>
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-elv" placeholder="Nom, prénom, matricule…"></div>
      <div class="fg"><label>Classe</label><select id="f-cls"><option value="">Toutes</option>${classes.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
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
  </div>`;
  let curr = list;
  renderElevesRows(curr);
  const filter = () => {
    const q = $('#q-elv').value.toLowerCase();
    const cls = $('#f-cls').value;
    const stat = $('#f-stat').value;
    curr = _elevesList.filter(e => {
      const txt = `${e.nom} ${e.prenom} ${e.matricule||''}`.toLowerCase();
      return (!q||txt.includes(q)) && (!cls||e.classe===cls) && (!stat||e.statut===stat);
    });
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
  $('#tb-eleves').innerHTML = list.length ? list.map(e => `<tr>
    <td>${elevePhoto(e, 34)}</td>
    <td class="mono">${esc(e.matricule||'—')}</td>
    <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong></td>
    <td><span class="badge bdg-primary">${esc(e.classe||'—')}</span></td>
    <td>${fmtDate(e.date_naissance)} ${e.lieu_naissance?`<span class="text-muted">(${esc(e.lieu_naissance)})</span>`:''}</td>
    <td>${esc(e.pere_telephone||e.mere_telephone||e.tuteur_telephone||'—')}</td>
    <td><span class="badge ${STATUT_COLORS[e.statut]||'bdg-gray'}">${esc(STATUT_LABELS_ELV[e.statut]||e.statut||'actif')}</span></td>
    <td><div class="td-actions">
      ${e.statut==='preinscrit' && ['admin','directeur','comptable'].includes(currentUser.role) ? `<button class="btn btn-ok btn-xs" onclick="modalValiderPreinscription('${escJs(e.id)}','${escJs(e.prenom)} ${escJs(e.nom)}')" title="Valider la préinscription">✔ Valider</button>` : ''}
      <button class="btn btn-outline btn-xs" onclick="imprimerCarteScolaire('${escJs(e.id)}')" title="Carte scolaire">🪪</button>
      <button class="btn btn-outline btn-xs" onclick="ficheEleve('${escJs(e.id)}')" title="Fiche complète">📋</button>
      <button class="btn btn-outline btn-xs" onclick="modalEleve('${escJs(e.id)}')" title="Modifier">✏️</button>
      <button class="btn btn-danger btn-xs" onclick="delEleve('${escJs(e.id)}')" title="Supprimer">🗑</button>
    </div></td>
  </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('🎓','Aucun élève trouvé','Inscrivez le premier élève via le bouton + ci-dessus')}</td></tr>`;
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
async function imprimerBulletin(eleveId, tri = 1) {
  const eleve = await apiGetEleve(eleveId);
  const notes = await apiGetNotes(`eleve_id=${eleveId}&trimestre=${tri}`);
  const settings = await apiGetSettings();

  // Calcul des moyennes par matière
  const parMatiere = {};
  notes.forEach(n => {
    if (!parMatiere[n.matiere]) parMatiere[n.matiere] = [];
    parMatiere[n.matiere].push(n.note / (n.note_max||20) * 20);
  });
  const lignesMat = Object.entries(parMatiere).map(([mat, vals]) => {
    const moy = vals.reduce((a,b)=>a+b,0)/vals.length;
    return { mat, moy };
  });
  lignesMat.sort((a,b) => a.mat.localeCompare(b.mat));
  const moyGen = lignesMat.length ? lignesMat.reduce((s,l)=>s+l.moy,0)/lignesMat.length : null;

  // Calcul rang (tous élèves de la classe)
  let rangText = '—';
  try {
    const all = await apiGetNotes(`classe=${eleve.classe}&trimestre=${tri}`);
    const moyEleves = {};
    all.forEach(n => {
      if (!moyEleves[n.eleve_id]) moyEleves[n.eleve_id] = { vals:[], id:n.eleve_id };
      moyEleves[n.eleve_id].vals.push(n.note/(n.note_max||20)*20);
    });
    const ranked = Object.values(moyEleves).map(e => ({ id:e.id, moy:e.vals.reduce((a,b)=>a+b,0)/e.vals.length })).sort((a,b)=>b.moy-a.moy);
    const pos = ranked.findIndex(r=>r.id===eleveId);
    rangText = pos >= 0 ? `${pos+1}e / ${ranked.length}` : '—';
  } catch(_) {}

  const apprec = moyGen == null ? 'Pas assez de notes' : moyGen >= 18 ? 'Excellent travail ! Félicitations.' : moyGen >= 16 ? 'Très bon travail. Continuez ainsi.' : moyGen >= 14 ? 'Bon travail. Quelques efforts restent à fournir.' : moyGen >= 12 ? 'Travail satisfaisant. Des progrès sont possibles.' : moyGen >= 10 ? 'Résultats passables. Un effort supplémentaire est nécessaire.' : 'Résultats insuffisants. Un sérieux travail de rattrapage s\'impose.';

  const mention = moyGen == null ? '—' : moyGen >= 16 ? 'Très Bien' : moyGen >= 14 ? 'Bien' : moyGen >= 12 ? 'Assez Bien' : moyGen >= 10 ? 'Passable' : 'Insuffisant';

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
  <div class="header">
    ${settings.ecole_logo?`<img src="${settings.ecole_logo}" alt="Logo">`:''}
    <h1>${settings.ecole_nom||'Groupe Scolaire'}</h1>
    ${settings.ecole_adresse?`<p>${settings.ecole_adresse}</p>`:''}
    ${settings.ecole_telephone?`<p>Tél : ${settings.ecole_telephone}</p>`:''}
    <h2 style="margin-top:8px;font-size:15px;color:#374151">BULLETIN DE NOTES — TRIMESTRE ${tri}</h2>
    <p style="font-size:12px;color:#555">Année scolaire : ${settings.annee_scolaire||eleve.annee_scolaire||'—'}</p>
  </div>
  <div class="info-grid">
    <div><strong>Nom & Prénom :</strong> ${eleve.prenom} ${eleve.nom}</div>
    <div><strong>Matricule :</strong> ${eleve.matricule||'—'}</div>
    <div><strong>Classe :</strong> ${eleve.classe||'—'}</div>
    <div><strong>Né(e) le :</strong> ${fmtDate(eleve.date_naissance)} ${eleve.lieu_naissance?'à '+eleve.lieu_naissance:''}</div>
  </div>
  <table>
    <thead><tr><th>Matière</th><th>Moyenne /20</th><th>Appréciation</th></tr></thead>
    <tbody>
      ${lignesMat.length ? lignesMat.map(l => `<tr>
        <td>${l.mat}</td>
        <td style="font-weight:600;color:${l.moy>=10?'#059669':'#DC2626'}">${l.moy.toFixed(2)}</td>
        <td>${l.moy>=16?'Très bien':l.moy>=12?'Bien':l.moy>=10?'Passable':'Insuffisant'}</td>
      </tr>`).join('') : '<tr><td colspan="3" style="text-align:center;color:#999">Aucune note enregistrée pour ce trimestre</td></tr>'}
    </tbody>
  </table>
  <div class="summary">
    <div><div class="sl">Moy. générale</div><div class="sv" style="color:${moyGen!=null&&moyGen>=10?'#059669':'#DC2626'}">${moyGen!=null?moyGen.toFixed(2)+'/ 20':'—'}</div></div>
    <div><div class="sl">Rang</div><div class="sv">${rangText}</div></div>
    <div><div class="sl">Mention</div><div class="sv" style="font-size:14px">${mention}</div></div>
    <div><div class="sl">Trimestre</div><div class="sv">${tri}</div></div>
  </div>
  <div class="apprec"><strong>Appréciation générale :</strong> ${apprec}</div>
  <div class="sig">
    <div>Le Directeur</div>
    <div>Signature des parents</div>
  </div>
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(bulletinHtml);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 800);
}
window.imprimerBulletin = imprimerBulletin;

/* ===================== CARTE SCOLAIRE ===================== */
async function imprimerCarteScolaire(eleveId) {
  const e = await apiGetEleve(eleveId);
  const settings = await apiGetSettings();
  const contact = e.contact_urgence_nom || e.contact_urgence_telephone
    ? `${e.contact_urgence_nom||''}${e.contact_urgence_nom&&e.contact_urgence_telephone?' — ':''}${e.contact_urgence_telephone||''}`
    : (e.pere_telephone || e.mere_telephone || e.tuteur_telephone || '—');
  const ecoleNomAffiche = "Groupe Scolaire Privé El.M.Djély";
  const ecoleLieuAffiche = settings.ecole_adresse || "Yattaya · Commune de Sonfonia";

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Carte scolaire — ${e.prenom} ${e.nom}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Mono:wght@500&family=Nunito+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box}
    body{font-family:'Nunito Sans',Arial,sans-serif;margin:0;padding:24px;background:#E8E4DC;display:flex;justify-content:center;align-items:flex-start}
    .carte{width:6cm;height:10cm;background:#F4EFE2;position:relative;overflow:hidden;border-radius:0.28cm;
      box-shadow:0 0.3cm 0.7cm rgba(30,25,15,.3);border:1px solid #D8D0BC;
      background-image:radial-gradient(#DCD5C2 0.4px, transparent 0.4px);background-size:8px 8px;
      display:flex;flex-direction:column}
    .flag-bar{height:4.5%;display:flex;flex-shrink:0}
    .flag-bar div{flex:1}
    .header{text-align:center;padding:5% 6% 3%;border-bottom:1px solid #B91C1C;flex-shrink:0}
    .header .pays{font-family:'Playfair Display',serif;font-size:12.5px;font-weight:700;color:#1E2A4A;letter-spacing:.02em}
    .header .devise{font-family:'Playfair Display',serif;font-style:italic;font-size:8px;color:#9A6B1F;margin-top:1px}
    .header .ministere{font-size:7.5px;font-weight:700;color:#4B4B4B;margin-top:5px;letter-spacing:.03em}
    .titre-carte-wrap{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:8px}
    .titre-carte-wrap .ln{height:1px;width:22px;background:#B91C1C}
    .header .titre-carte{font-size:11px;font-weight:800;color:#B91C1C;letter-spacing:.18em}
    .header .ecole-nom{font-family:'Playfair Display',serif;font-size:11.5px;font-weight:700;color:#1E2A4A;margin-top:8px;line-height:1.25}
    .header .ecole-lieu{font-size:7px;color:#6B6558;margin-top:2px;letter-spacing:.03em}
    .header .ecole-tel{font-size:6.6px;color:#6B6558;margin-top:1px;letter-spacing:.03em}
    .corps{padding:6% 6% 2%;display:flex;gap:8px;flex:1;position:relative}
    .photo-frame{width:38%;aspect-ratio:3/3.7;background:#fff;border:1.5px solid #1E2A4A;border-radius:3px;
      display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;position:relative}
    .photo-frame img{width:100%;height:100%;object-fit:cover}
    .photo-frame .no-photo{color:#D1D5DB;width:100%;height:100%;display:flex;align-items:center;justify-content:center}
    .infos{flex:1;display:flex;flex-direction:column;justify-content:center;gap:7px;padding-top:2%}
    .infos .lbl{font-size:7px;color:#9A6B1F;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
    .infos .val{font-family:'Playfair Display',serif;font-weight:700;font-size:11px;color:#1E2A4A;margin-top:1px}
    .sig-line{position:absolute;left:6%;bottom:3%;width:38%;border-top:1px solid #B8AF95}
    .matricule-bar{background:#1E2A4A;color:#fff;display:flex;align-items:center;justify-content:space-between;
      padding:2.5% 6%;flex-shrink:0;margin-top:auto}
    .matricule-bar .lbl{font-size:7.5px;letter-spacing:.08em;font-weight:600;color:#C9D2E3}
    .matricule-bar .val{font-family:'DM Mono',monospace;font-size:13px;letter-spacing:.06em}
    .footer-info{padding:4% 6%;font-size:7.5px;color:#3A3A3A;flex-shrink:0}
    .footer-info .lbl{font-size:6.3px;color:#8A8370;text-transform:uppercase;font-weight:700;letter-spacing:.04em}
    .footer-info .fval{font-weight:700;margin-bottom:5px}
    .mention{padding:0 6% 3%;display:flex;justify-content:space-between;align-items:flex-end;gap:6px;flex-shrink:0}
    .mention .txt{font-size:5.6px;color:#8A8370;line-height:1.35;font-style:italic}
    .mention .directeur{text-align:center;font-size:6px;color:#4B4B4B;flex-shrink:0}
    .mention .directeur .cachet-img{max-height:24px;max-width:38px;display:block;margin:0 auto 1px}
    .mention .directeur .signature-img{max-height:14px;max-width:38px;display:block;margin:0 auto 1px}
    .mention .directeur .ln{border-top:1px solid #B8AF95;width:26px;margin:0 auto 3px}
    @media print{
      @page{ size:6cm 10cm; margin:0; }
      body{background:#fff;padding:0;align-items:stretch}
      .carte{box-shadow:none;border:none;border-radius:0}
    }
  </style></head><body>
  <div class="carte">
    <div class="flag-bar"><div style="background:#CE1126"></div><div style="background:#FCD116"></div><div style="background:#009460"></div></div>
    <div class="header">
      <div class="pays">République de Guinée</div>
      <div class="devise">Travail — Justice — Solidarité</div>
      <div class="ministere">MINISTÈRE DE L'ÉDUCATION NATIONALE</div>
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

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 700);
}
window.imprimerCarteScolaire = imprimerCarteScolaire;

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
      await apiValiderPreinscription(eleveId, fd);
      toast('Préinscription validée ✅ — Élève actif','success');
      closeModal();
      if (fd.montant) {
        imprimerRecu({
          type: 'entree', nom, description: "Frais d'inscription", montant: fd.montant,
          date: fd.date_paiement, moyenPaiement: fd.moyen_paiement, reference: fd.reference,
          recuPar: currentUser?.full_name,
        });
      }
      pageEleves();
    } catch(err) { toast(err.message,'error'); }
  };
}
window.modalValiderPreinscription = modalValiderPreinscription;
