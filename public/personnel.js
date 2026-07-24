/* ===================== PERSONNEL ===================== */
async function pagePersonnel() {
  $('#content').innerHTML = loadingHtml;
  try {
    const moisCourantVal = moisCourant();
    let list = await apiGetPersonnel(`mois=${moisCourantVal}`);
    const masse = list.reduce((s,p) => s + (Number(p.salaire_calcule ?? p.salaire)||0), 0);

    const render = (data) => {
      $('#tb-personnel').innerHTML = data.length ? data.map(p => {
        const estHoraire = p.type_remuneration === 'horaire';
        return `<tr>
        <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong>${p.cycle_enseignement?`<br><span class="text-muted" style="font-size:11px">${p.cycle_enseignement.split(',').map(c=>esc(CYCLE_LABELS[c.trim()]||c.trim())).join(' · ')}</span>`:''}</td>
        <td><span class="badge bdg-primary">${esc(p.poste||'—')}</span></td>
        <td>${p.matiere ? p.matiere.split(',').map(m=>`<span class="badge bdg-primary" style="margin:1px">${esc(m.trim())}</span>`).join(' ') : '—'}</td>
        <td>${esc(p.telephone||'—')}</td>
        <td>
          ${estHoraire
            ? `<span class="badge bdg-info">${(p.heures_mois||0)}h × ${fmtMoney(p.taux_horaire||0)}</span>`
            : '<span class="badge bdg-gray">Mensuel</span>'}
        </td>
        <td class="mono text-right fw-600">${fmtMoney(p.salaire_calcule ?? p.salaire ?? 0)}</td>
        <td>${fmtDate(p.date_embauche)}</td>
        <td><div class="td-actions">
          ${estHoraire?`<button class="btn btn-outline btn-xs" onclick="modalHeures('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}',${p.taux_horaire||0})">🕐 Heures</button>`:''}
          <button class="btn btn-outline btn-xs" onclick="imprimerBadge('${escJs(p.id)}')">🪪 Badge</button>
          ${p.poste==='Enseignant'?`<button class="btn btn-outline btn-xs" onclick="imprimerCarteAcces('${escJs(p.id)}')">🚪 Accès salles</button>`:''}
          <button class="btn btn-outline btn-xs" onclick="modalPersonnel('${escJs(p.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delPersonnel('${escJs(p.id)}')">🗑</button>
        </div></td>
      </tr>`;
      }).join('') : `<tr><td colspan="8">${emptyHtml('👨‍🏫','Aucun membre du personnel')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">👨‍🏫 Personnel (${list.length}) — Masse salariale (${moisCourantVal}) : <span class="text-ok">${fmtMoney(masse)}</span></span>
        <button class="btn btn-primary btn-sm" onclick="modalPersonnel()">+ Ajouter</button>
      </div>
      <div class="card-body" style="padding-bottom:0">
        <div class="alert alert-info">💡 Les enseignants du <strong>collège</strong> et du <strong>lycée</strong> sont rémunérés à l'heure ;
        ceux de la <strong>maternelle</strong> et du <strong>primaire</strong> (et le personnel administratif) sont rémunérés au mois.</div>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-per" placeholder="Nom, prénom…"></div>
        <div class="fg"><label>Poste</label><select id="f-poste"><option value="">Tous</option>${POSTES.map(p=>`<option>${esc(p)}</option>`).join('')}</select></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-personnel"><th>Nom</th><th>Poste</th><th>Matière</th><th>Téléphone</th><th>Rémunération</th><th class="text-right">Montant (${moisCourantVal})</th><th>Embauché le</th><th>Actions</th></tr></thead>
        <tbody id="tb-personnel"></tbody>
      </table></div>
    </div>`;

    let curr = list;
    render(curr);
    const filter = () => {
      const q = $('#q-per').value.toLowerCase();
      const poste = $('#f-poste').value;
      curr = list.filter(p => {
        const txt = `${p.nom} ${p.prenom} ${p.email||''}`.toLowerCase();
        return (!q || txt.includes(q)) && (!poste || p.poste === poste);
      });
      render(curr);
    };
    $('#q-per').addEventListener('input', filter);
    $('#f-poste').addEventListener('change', filter);

    makeSortableTable('#th-personnel', () => curr, render,
      [row => `${row.prenom} ${row.nom}`, 'poste', 'matiere', 'telephone', null, row => row.salaire_calcule ?? row.salaire ?? 0, 'date_embauche', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

async function modalPersonnel(id = null) {
  let data = {};
  if (id) { const list = await apiGetPersonnel(); data = list.find(p => p.id === id) || {}; }
  const cycles = [...new Set(CLASSES_FULL.map(c=>c.cycle))];
  const matieresActuelles = (data.matiere||'').split(',').map(m=>m.trim()).filter(Boolean);
  const cyclesActuels = (data.cycle_enseignement||'').split(',').map(c=>c.trim()).filter(Boolean);
  openModal(id ? 'Modifier le membre du personnel' : 'Ajouter un membre du personnel', `
    <form id="f-per" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Prénom*</label><input name="prenom" value="${esc(data.prenom||'')}" required></div>
        <div class="fg"><label>Nom*</label><input name="nom" value="${esc(data.nom||'')}" required></div>
      </div>
      ${id ? `<div style="text-align:center;padding:10px">
        <div id="per-photo-prev" class="mb-2">${data.photo_url?`<img src="${esc(data.photo_url)}" style="width:90px;height:90px;border-radius:50%;object-fit:cover;border:2px solid #E5E7EB">`:'<div class="photo-placeholder" style="width:90px;height:90px;border-radius:50%;margin:0 auto">👤</div>'}</div>
        ${photoCaptureWidgetHtml('per-photo')}
        <div class="text-muted mt-1" style="font-size:11px">Utilisée pour le badge et le bulletin de salaire</div>
      </div>` : ''}
      <div class="form-2">
        <div class="fg"><label>Poste</label><select name="poste" id="per-poste">${optionsHtml(POSTES, data.poste||'')}</select></div>
        <div class="fg"><label>Téléphone</label><input name="telephone" value="${esc(data.telephone||'')}"></div>
      </div>
      <div class="fg">
        <label>Matière(s) enseignée(s) <span class="text-muted" style="font-weight:400">— un(e) enseignant(e) peut en enseigner plusieurs</span></label>
        <div class="check-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;background:var(--g0);padding:10px;border-radius:8px;max-height:150px;overflow-y:auto">
          ${MATIERES.map(m => `<label style="display:flex;align-items:center;gap:6px;font-weight:400;font-size:13px">
            <input type="checkbox" class="chk-matiere" value="${esc(m)}" ${matieresActuelles.includes(m)?'checked':''}> ${esc(m)}
          </label>`).join('')}
        </div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Email</label><input type="email" name="email" value="${esc(data.email||'')}"></div>
        <div class="fg"><label>Date d'embauche</label><input type="date" name="date_embauche" value="${esc(data.date_embauche||'')}"></div>
      </div>
      <div class="fg"><label>Adresse</label><input name="adresse" value="${esc(data.adresse||'')}" placeholder="Quartier, commune, ville…"></div>
      <div class="fg">
        <label>Niveau(x) / Cycle(s) d'enseignement <span class="text-muted" style="font-weight:400">— peut enseigner à plusieurs niveaux</span></label>
        <div style="display:flex;gap:14px;flex-wrap:wrap;background:var(--g0);padding:10px;border-radius:8px">
          ${cycles.map(c => `<label style="display:flex;align-items:center;gap:6px;font-weight:400;font-size:13px">
            <input type="checkbox" class="chk-cycle" value="${esc(c)}" ${cyclesActuels.includes(c)?'checked':''} onchange="updateRemunerationFields()"> ${esc(CYCLE_LABELS[c]||c)}
          </label>`).join('')}
        </div>
      </div>
      <div class="form-section-title">Rémunération</div>
      <div class="fg">
        <label><input type="checkbox" id="per-horaire" ${data.type_remuneration==='horaire'?'checked':''} onchange="updateRemunerationFields()"> Rémunéré(e) à l'heure (collège/lycée)</label>
        <input type="hidden" name="type_remuneration" id="per-type-rem" value="${esc(data.type_remuneration||'mensuel')}">
      </div>
      <div class="form-2" id="per-champs-mensuel">
        <div class="fg"><label>Salaire mensuel (GNF)</label><input type="number" name="salaire" value="${data.salaire||''}" placeholder="500000"></div>
        <div></div>
      </div>
      <div class="form-2" id="per-champs-horaire" style="display:none">
        <div class="fg"><label>Taux horaire (GNF/heure)</label><input type="number" name="taux_horaire" value="${data.taux_horaire||''}" placeholder="15000"></div>
        <div class="text-muted" style="font-size:12px;align-self:center">Les heures se saisissent ensuite chaque mois depuis la liste du personnel (bouton "🕐 Heures").</div>
      </div>
      ${id ? motifFieldHtml() : ''}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`);

  window.updateRemunerationFields = () => {
    const horaire = $('#per-horaire').checked;
    $('#per-type-rem').value = horaire ? 'horaire' : 'mensuel';
    $('#per-champs-mensuel').style.display = horaire ? 'none' : '';
    $('#per-champs-horaire').style.display = horaire ? '' : 'none';
  };
  // Pré-cocher automatiquement "à l'heure" si l'un des niveaux cochés est collège/lycée
  // et qu'aucune donnée existante ne dit le contraire
  if (!id) {
    $$('.chk-cycle').forEach(cb => cb.addEventListener('change', () => {
      const cyclesCoches = $$('.chk-cycle:checked').map(c => c.value);
      $('#per-horaire').checked = cyclesCoches.includes('college') || cyclesCoches.includes('lycee');
      updateRemunerationFields();
    }));
  }
  updateRemunerationFields();

  // Câblage de la capture photo (fichier / webcam / caméra mobile) — édition uniquement
  if (id) {
    wirePhotoCapture('per-photo', async (file) => {
      const fd = new FormData();
      fd.append('photo', file);
      try {
        const r = await apiUploadPhotoPersonnel(id, fd);
        $('#per-photo-prev').innerHTML = `<img src="${r.photo_url}" style="width:90px;height:90px;border-radius:50%;object-fit:cover;border:2px solid #E5E7EB">`;
        toast('Photo mise à jour', 'success');
      } catch(err) { toast(err.message, 'error'); }
    });
  }

  $('#f-per').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.matiere = $$('.chk-matiere:checked').map(c => c.value).join(', ') || null;
    fd.cycle_enseignement = $$('.chk-cycle:checked').map(c => c.value).join(', ') || null;
    try {
      if (id) await apiUpdatePersonnel(id, fd); else await apiCreatePersonnel(fd);
      toast(id ? 'Modifié' : 'Ajouté', 'success'); closeModal(); pagePersonnel();
    } catch(err) { toast(err.message, 'error'); }
  };
}

async function modalHeures(personnelId, nom, tauxHoraire) {
  const historique = await apiGetHeuresPersonnel(personnelId);
  const moisCourantVal = moisCourant();
  const dejaCeMois = historique.find(h => h.mois === moisCourantVal);
  openModal(`🕐 Heures d'enseignement — ${nom}`, `
    <form id="f-heures" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Mois*</label><input type="month" name="mois" value="${moisCourantVal}" required></div>
        <div class="fg"><label>Nombre d'heures*</label><input type="number" name="nombre_heures" step="0.5" min="0" value="${dejaCeMois?dejaCeMois.nombre_heures:''}" required></div>
      </div>
      <div class="text-muted" style="font-size:12px">Taux horaire actuel : <strong>${fmtMoney(tauxHoraire)}</strong> / heure</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>
    <div class="sep"></div>
    <div class="form-section-title">Historique</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Mois</th><th class="text-right">Heures</th><th class="text-right">Montant</th></tr></thead>
      <tbody>
        ${historique.length ? historique.map(h => `<tr>
          <td>${esc(h.mois)}</td>
          <td class="text-right mono">${h.nombre_heures}h</td>
          <td class="text-right mono fw-600">${fmtMoney(h.nombre_heures * tauxHoraire)}</td>
        </tr>`).join('') : `<tr><td colspan="3">${emptyHtml('🕐','Aucune heure saisie')}</td></tr>`}
      </tbody>
    </table></div>
  `, { narrow: true });
  $('#f-heures').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.nombre_heures = parseFloat(fd.nombre_heures);
    try { await apiSaisirHeures(personnelId, fd); toast('Heures enregistrées','success'); closeModal(); pagePersonnel(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function delPersonnel(id) {
  if (!confirmDel('Supprimer ce membre du personnel ?')) return;
  try { await apiDeletePersonnel(id); toast('Supprimé', 'success'); pagePersonnel(); }
  catch(e) { toast(e.message, 'error'); }
}
window.modalPersonnel = modalPersonnel;
window.modalHeures = modalHeures;
window.delPersonnel = delPersonnel;

/* ===================== CARTE D'ACCÈS AUX SALLES (enseignants) ===================== */
async function imprimerCarteAcces(personnelId) {
  const list = await apiGetPersonnel();
  const p = list.find(x => x.id === personnelId);
  if (!p) return;
  const settings = await apiGetSettings();
  const creneaux = await apiGetEdt('professeur_id=' + personnelId);
  const salles = [...new Set(creneaux.map(c => c.salle).filter(Boolean))];

  const ecoleNomAffiche = "Groupe Scolaire Elhadji Mountaga Djély";
  const [nomEcole1, ...resteNom] = ecoleNomAffiche.split(/\s+/);
  const initiales = ecoleNomAffiche.split(/\s+/).map(w=>w[0]).join('').substring(0,2).toUpperCase();
  const qrData = `${ecoleNomAffiche} | Accès salles | ${p.matricule||''} | ${p.prenom} ${p.nom}`;
  const qrSvg = genererQrSvg(qrData, 3, 2);

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Carte d'accès — ${p.prenom} ${p.nom}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700;9..144,800&family=Inter:wght@400;500;600;700;800;900&family=Space+Mono:wght@400;700&display=swap');
    :root{ --ink:#1B2A4A; --ink2:#233457; --paper:#FBF7EE; --gold:#B9922F; --red:#CE1126; --yellow:#F5C518; --green:#128142; }
    *{box-sizing:border-box}
    html,body{margin:0;padding:0;background:#dfe3ea;font-family:'Inter',sans-serif}
    .stage{padding:40px 20px;display:flex;flex-direction:column;align-items:center;gap:14px}
    .note{font-size:12.5px;color:#4c5566;max-width:460px;text-align:center;line-height:1.5}
    .preview-wrap{width:calc(10cm * 2.6);height:calc(6cm * 2.6);position:relative}
    .card{position:absolute;top:0;left:0;width:10cm;height:6cm;transform:scale(2.6);transform-origin:top left;
      background:var(--paper);border-radius:0.32cm;overflow:hidden;box-shadow:0 10px 26px rgba(20,30,50,.32);
      border:0.6pt solid rgba(27,42,74,.15)}
    .flagline{display:flex;height:0.09cm}
    .flagline span{flex:1}
    .flagline .r{background:var(--red)} .flagline .y{background:var(--yellow)} .flagline .g{background:var(--green)}
    .header{display:flex;align-items:center;justify-content:space-between;padding:0.18cm 0.32cm 0.02cm}
    .logo-row{display:flex;align-items:center;gap:0.14cm}
    .emblem{width:0.58cm;height:0.58cm;flex:0 0 auto}
    .wordmark .l1{font-family:'Fraunces',serif;font-weight:800;font-size:0.225cm;color:var(--ink);line-height:1.05}
    .wordmark .l2{font-family:'Inter',sans-serif;font-weight:700;font-size:0.105cm;letter-spacing:.06em;color:var(--gold);text-transform:uppercase;margin-top:0.03cm}
    .badge-type{background:var(--red);color:var(--paper);font-size:0.135cm;font-weight:800;letter-spacing:.08em;text-transform:uppercase;padding:0.06cm 0.18cm;border-radius:0.2cm}
    .body-row{display:flex;align-items:flex-start;gap:0.3cm;padding:0.08cm 0.32cm 0}
    .photo-frame{position:relative;width:1.95cm;height:2.35cm;background:var(--paper);border:0.045cm solid var(--ink);
      border-radius:0.14cm;padding:0.07cm;box-shadow:0.03cm 0.05cm 0 rgba(0,0,0,.12);flex:0 0 auto;margin-top:0.05cm}
    .photo-frame .inner{width:100%;height:100%;border-radius:0.08cm;overflow:hidden;background:#E4DCC7;display:flex;align-items:center;justify-content:center}
    .photo-frame .inner img{width:100%;height:100%;object-fit:cover}
    .photo-frame svg{width:70%;height:70%;color:var(--ink);opacity:.35}
    .id-text{padding-top:0.04cm}
    .id-text .nom{font-family:'Fraunces',serif;font-weight:800;font-size:0.4cm;color:var(--ink);line-height:.98}
    .id-text .prenom{font-family:'Fraunces',serif;font-weight:600;font-size:0.27cm;color:var(--ink2);line-height:1.1;margin-top:0.02cm}
    .id-text .fonction{font-size:0.17cm;color:var(--gold);opacity:.95;margin-top:0.08cm;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
    .pill{display:inline-flex;align-items:center;gap:0.1cm;background:var(--ink);color:var(--paper);border-radius:0.3cm;padding:0.06cm 0.2cm;margin-top:0.1cm}
    .pill .k{font-size:0.1cm;text-transform:uppercase;letter-spacing:.05em;color:var(--gold);font-weight:700}
    .pill .v{font-family:'Space Mono',monospace;font-weight:700;font-size:0.175cm}
    .infos-plus{margin-top:0.09cm;display:flex;flex-direction:column;gap:0.03cm}
    .infos-plus div{display:flex;align-items:baseline;gap:0.08cm}
    .infos-plus .k{font-size:0.095cm;text-transform:uppercase;letter-spacing:.04em;color:var(--ink);opacity:.55;font-weight:700;min-width:1.1cm}
    .infos-plus .v{font-size:0.135cm;color:var(--ink2);font-weight:600}
    .rooms{padding:0.14cm 0.32cm 0}
    .rooms .label{font-size:0.11cm;letter-spacing:.08em;text-transform:uppercase;color:var(--ink);opacity:.55;font-weight:700;margin-bottom:0.06cm}
    .rooms .chips{display:flex;flex-wrap:wrap;gap:0.09cm}
    .rooms .chip{background:rgba(27,42,74,.08);border:0.02cm solid rgba(27,42,74,.25);color:var(--ink);font-size:0.14cm;font-weight:700;padding:0.05cm 0.14cm;border-radius:0.18cm}
    .qr-wrap{position:absolute;top:1cm;right:0.32cm;background:var(--paper);padding:0.05cm;border-radius:0.08cm;box-shadow:0 0.04cm 0.1cm rgba(0,0,0,.18);text-align:center}
    .qr-wrap svg{display:block;width:0.78cm;height:0.78cm}
    .qr-wrap .cap{font-size:0.075cm;letter-spacing:.05em;text-transform:uppercase;color:var(--ink);opacity:.6;margin-top:0.03cm;font-weight:700}
    .footer-band{position:absolute;left:0;right:0;bottom:0;height:1.02cm;background:var(--ink);display:flex;align-items:center;justify-content:space-between;padding:0 0.32cm}
    .footer-band .valid{color:var(--paper);opacity:.85;font-size:0.135cm;font-weight:600}
    .footer-band .mention{color:var(--yellow);font-size:0.115cm;font-weight:700;text-transform:uppercase;letter-spacing:.01em;text-align:right;max-width:4.2cm;line-height:1.3}
    @media print{
      @page{ size:10cm 6cm; margin:0; }
      body{background:#fff} .stage{padding:0;gap:0} .note{display:none}
      .preview-wrap{width:10cm;height:6cm} .card{transform:none;box-shadow:none;border:none}
    }
  </style></head><body>
  <div class="stage">
    <div class="preview-wrap">
      <div class="card">
        <div class="flagline"><span class="r"></span><span class="y"></span><span class="g"></span></div>
        <div class="header">
          <div class="logo-row">
            <svg class="emblem" viewBox="0 0 60 60">
              <polygon points="30,4 52,17 52,43 30,56 8,43 8,17" fill="none" stroke="#1B2A4A" stroke-width="3"/>
              <polygon points="30,14 44,22 44,38 30,46 16,38 16,22" fill="none" stroke="#B9922F" stroke-width="2.5"/>
              <text x="30" y="36" text-anchor="middle" font-family="Fraunces, serif" font-weight="800" font-size="15" fill="#1B2A4A">${esc(initiales)}</text>
            </svg>
            <div class="wordmark">
              <div class="l1">${esc(nomEcole1||'Groupe Scolaire')}</div>
              <div class="l2">${esc(resteNom.join(' '))}</div>
            </div>
          </div>
          <div class="badge-type">Accès Salles</div>
        </div>

        <div class="qr-wrap">${qrSvg}<div class="cap">Scan accès</div></div>

        <div class="body-row">
          <div class="photo-frame">
            <div class="inner">
              ${p.photo_url ? `<img src="${esc(p.photo_url)}">` : `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-9 2.2-9 5v2h18v-2c0-2.8-4.6-5-9-5z"/></svg>`}
            </div>
          </div>
          <div class="id-text">
            <div class="nom">${esc((p.nom||'').toUpperCase())}</div>
            <div class="prenom">${esc(p.prenom||'')}</div>
            <div class="fonction">${esc((p.matiere||'').split(',').map(m=>m.trim()).filter(Boolean).join(' · ') || p.poste || 'Enseignant(e)')}</div>
            <div class="pill"><span class="k">Matricule</span><span class="v">${esc(p.matricule||'—')}</span></div>
            ${(p.telephone || p.date_embauche || p.adresse) ? `<div class="infos-plus">
              ${p.telephone ? `<div><span class="k">Téléphone</span><span class="v">${esc(p.telephone)}</span></div>` : ''}
              ${p.adresse ? `<div><span class="k">Adresse</span><span class="v">${esc(p.adresse)}</span></div>` : ''}
              ${p.date_embauche ? `<div><span class="k">Embauché(e) le</span><span class="v">${fmtDate(p.date_embauche)}</span></div>` : ''}
            </div>` : ''}
          </div>
        </div>

        <div class="rooms">
          <div class="label">Salles autorisées</div>
          <div class="chips">
            ${salles.length ? salles.map(sName => `<span class="chip">${esc(sName)}</span>`).join('') : '<span class="chip">Aucune salle assignée</span>'}
          </div>
        </div>

        <div class="footer-band">
          <div class="valid">${esc(settings.annee_scolaire ? 'Rentrée ' + settings.annee_scolaire : '')}</div>
          <div class="mention">Valable pour l'année scolaire en cours.<br>Propriété du ${esc(initiales)} ${esc(resteNom.join(' '))}.</div>
        </div>
      </div>
    </div>
    <div class="note">Carte d'accès aux salles de classe — dimensions réelles 10 cm × 6 cm.</div>
  </div>
  </body></html>`;

  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 700);
}
window.imprimerCarteAcces = imprimerCarteAcces;

async function imprimerBadge(personnelId) {
  const list = await apiGetPersonnel();
  const p = list.find(x => x.id === personnelId);
  if (!p) return;
  const settings = await apiGetSettings();

  // Récupère les cours de révision dispensés par cet enseignant (en plus de sa matière principale)
  let coursSupp = [];
  if (p.poste === 'Enseignant') {
    try {
      const tousCours = await apiGetCoursRevision();
      for (const c of tousCours) {
        const ens = await apiGetEnseignantsCours(c.id).catch(() => []);
        if (ens.some(e => e.personnel_id === personnelId)) coursSupp.push(c.titre);
      }
    } catch(_) {}
  }

  const matieresListe = (p.matiere||'').split(',').map(m=>m.trim()).filter(Boolean);
  const fonction = p.poste==='Enseignant' && (matieresListe.length || coursSupp.length)
    ? [...matieresListe, ...coursSupp.map(c=>c+' (révision)')].join(' · ')
    : (p.poste || 'Personnel de l\'établissement');

  const qrData = `${settings.ecole_nom||'École'} | ${p.matricule||''} | ${p.prenom} ${p.nom} | ${p.poste||''}`;
  const qrSvg = genererQrSvg(qrData, 3, 2);

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Badge — ${p.prenom} ${p.nom}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:Arial,'Segoe UI',sans-serif;margin:0;padding:20px;background:#E5E7EB;display:flex;justify-content:center}
    .badge{width:6cm;height:10cm;background:#fff;border-radius:0.3cm;position:relative;overflow:hidden;
      box-shadow:0 10px 30px rgba(0,0,0,.25)}
    .badge-top{position:relative;height:42%;padding:6% 6% 0}
    .brand{display:flex;align-items:center;gap:6px}
    .brand img.logo{height:15px;max-width:26px;object-fit:contain}
    .brand .logo-fallback{width:15px;height:15px;border-radius:4px;background:#1E3A8A;color:#fff;
      display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:800}
    .brand .ecole-nom{font-size:9.5px;font-weight:800;color:#111;line-height:1.15}
    .brand .ecole-adresse{font-size:5.5px;color:#6B7280;margin-top:1px}
    .qr{position:absolute;top:32%;right:6%;width:23%;aspect-ratio:1/1;background:#fff;border-radius:5px;
      display:flex;align-items:center;justify-content:center;overflow:hidden}
    .qr svg{width:100%;height:100%}
    .photo-wrap{position:absolute;left:5%;top:29%;width:50%;aspect-ratio:1/1;
      background:#fff;border-radius:8px;border:2px solid #fff;
      box-shadow:0 4px 10px rgba(0,0,0,.18);display:flex;align-items:center;justify-content:center;
      overflow:hidden;z-index:3}
    .photo-wrap img{width:100%;height:100%;object-fit:cover}
    .photo-wrap .no-photo{color:#D1D5DB;width:100%;height:100%;display:flex;align-items:center;justify-content:center}
    .badge-bottom{position:absolute;left:0;right:0;bottom:0;top:34%;
      background:linear-gradient(160deg,#312E81 0%,#1E3A8A 60%,#1E40AF 100%);
      clip-path:polygon(0% 12%, 100% 0%, 100% 100%, 0% 100%);
      padding:14% 6% 5%;color:#fff;z-index:2}
    .nom{font-size:14.5px;font-weight:900;line-height:1.1;letter-spacing:.3px}
    .prenom{font-size:10.5px;font-weight:700;opacity:.95;margin-bottom:6px}
    .fonction{font-size:7.5px;opacity:.9;margin-bottom:10px;line-height:1.3}
    .matricule-pill{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);
      border-radius:999px;padding:3px 9px;font-size:7px;font-weight:700;margin-bottom:10px}
    .contact{font-size:6px;opacity:.9;display:flex;flex-direction:column;gap:2px;position:absolute;bottom:5%;left:6%;right:6%}
    .contact div{display:flex;align-items:center;gap:4px}
    @media print{
      @page{ size:6cm 10cm; margin:0; }
      body{background:#fff;padding:0}
      .badge{box-shadow:none;border-radius:0}
    }
  </style></head><body>
  <div class="badge">
    <div class="badge-top">
      <div class="brand">
        ${settings.ecole_logo?`<img class="logo" src="${settings.ecole_logo}">`:`<div class="logo-fallback">GS</div>`}
        <div>
          <div class="ecole-nom">${esc(settings.ecole_nom||'Groupe Scolaire')}</div>
          ${settings.ecole_adresse?`<div class="ecole-adresse">${esc(settings.ecole_adresse)}</div>`:''}
        </div>
      </div>
      <div class="qr">${qrSvg}</div>
      <div class="photo-wrap">${p.photo_url?`<img src="${esc(p.photo_url)}">`:'<div class="no-photo"><svg viewBox="0 0 24 24" fill="currentColor" width="55%" height="55%"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-9 2.2-9 5v2h18v-2c0-2.8-4.6-5-9-5z"/></svg></div>'}</div>
    </div>
    <div class="badge-bottom">
      <div class="nom">${esc((p.nom||'').toUpperCase())}</div>
      <div class="prenom">${esc(p.prenom||'')}</div>
      <div class="fonction">${esc(fonction)}</div>
      <div class="matricule-pill">Matricule : ${esc(p.matricule||'—')}</div>
      <div class="contact">
        ${p.email?`<div>Email : ${esc(p.email)}</div>`:''}
        ${p.telephone?`<div>Tél : ${esc(p.telephone)}</div>`:''}
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
window.imprimerBadge = imprimerBadge;
