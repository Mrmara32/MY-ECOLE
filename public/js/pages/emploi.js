/* ===================== EMPLOI DU TEMPS ===================== */
let _edtClasse = '', _edtData = [];

async function pageEmploi() {
  const classes = await apiGetClasses().catch(() => CLASSES);
  _edtClasse = _edtClasse || (classes[0] || '');
  await loadEdt();
}

async function loadEdt() {
  $('#content').innerHTML = loadingHtml;
  if (!_edtClasse) {
    $('#content').innerHTML = `
    <div class="card"><div class="card-header"><span class="card-title">📅 Emploi du temps</span>
      <select id="edt-cls-sel" onchange="_edtClasse=this.value;loadEdt()">${CLASSES.map(c=>`<option value="${esc(c)}" ${c===_edtClasse?'selected':''}>${esc(c)}</option>`).join('')}</select>
    </div><div class="card-body">${emptyHtml('📅','Choisissez une classe')}</div></div>`;
    return;
  }
  try {
    _edtData = await apiGetEdt(`classe=${encodeURIComponent(_edtClasse)}`);
    renderEdt();
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function renderEdt() {
  const byJourCreneau = {};
  _edtData.forEach(e => { byJourCreneau[`${e.jour}|${e.creneau}`] = e; });

  const gridCells = JOURS.map(jour =>
    CRENEAUX.map(cren => {
      const key = `${jour}|${cren}`;
      const course = byJourCreneau[key];
      if (course) {
        const c = matColor(course.matiere||'');
        return `<div class="edt-cell edt-filled">
          <div class="edt-course" style="background:${c}">
            <div class="edt-mat">${esc(course.matiere||'—')}</div>
            ${course.salle?`<div class="edt-salle">🚪 ${esc(course.salle)}</div>`:''}
            <div style="margin-top:4px;display:flex;gap:4px">
              <button onclick="modalEdtAdd('${escJs(jour)}','${escJs(cren)}','${escJs(course.id)}')" style="background:rgba(0,0,0,.25);border:none;color:#fff;border-radius:4px;padding:1px 5px;cursor:pointer;font-size:10px">✏️</button>
              <button onclick="delEdt('${escJs(course.id)}')" style="background:rgba(0,0,0,.25);border:none;color:#fff;border-radius:4px;padding:1px 5px;cursor:pointer;font-size:10px">✕</button>
            </div>
          </div>
        </div>`;
      }
      return `<div class="edt-cell" onclick="modalEdtAdd('${escJs(jour)}','${escJs(cren)}')">
        <div style="text-align:center;padding-top:20px;color:#D1D5DB;font-size:18px">+</div>
      </div>`;
    })
  );

  $('#content').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">📅 Emploi du temps — Classe <span class="badge bdg-primary">${esc(_edtClasse)}</span></span>
      <div class="card-actions">
        <select id="edt-cls-sel" onchange="_edtClasse=this.value;loadEdt()">${CLASSES.map(c=>`<option value="${esc(c)}" ${c===_edtClasse?'selected':''}>${esc(c)}</option>`).join('')}</select>
        ${['admin','directeur'].includes(currentUser.role) ? `<button class="btn btn-outline btn-sm" onclick="modalGererCreneaux()">🕐 Gérer les créneaux</button>` : ''}
      </div>
    </div>
    <div class="card-body" style="overflow-x:auto">
      <div class="edt-grid">
        <div class="edt-head">Horaire</div>
        ${JOURS.map(j=>`<div class="edt-head">${j}</div>`).join('')}
        ${CRENEAUX.map((cren, ci) => `
          <div class="edt-time"><div>${esc(cren)}</div></div>
          ${JOURS.map((_, ji) => gridCells[ji][ci]).join('')}
        `).join('')}
      </div>
    </div>
  </div>`;
}

async function modalEdtAdd(jour, creneau, editId = null) {
  const personnel = await apiGetPersonnel().catch(()=>[]);
  const profs = personnel.filter(p => p.poste === 'Enseignant' || p.matiere);
  if (!_sallesCache.length) await refreshSalles();
  const salles = _sallesCache.filter(s=>s.active);
  const existing = editId ? _edtData.find(e => e.id === editId) : null;
  openModal(`${editId?'Modifier':'Ajouter'} un cours — ${jour} ${creneau}`, `
    <form id="f-edt" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Matière*</label><select name="matiere" required>${optionsHtml(MATIERES, existing?.matiere||'')}</select></div>
      <div class="fg"><label>Professeur</label><select name="professeur_id">
        <option value="">— Sélectionner —</option>
        ${profs.map(p=>`<option value="${esc(p.id)}" ${existing?.professeur_id===p.id?'selected':''}>${esc(p.prenom)} ${esc(p.nom)} ${p.matiere?'('+p.matiere+')':''}</option>`).join('')}
      </select></div>
      <div class="fg"><label>Salle</label><select name="salle">
        <option value="">— Aucune —</option>
        ${salles.map(s=>`<option value="${esc(s.nom)}" ${existing?.salle===s.nom?'selected':''}>${esc(s.nom)}</option>`).join('')}
      </select></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        ${editId ? `<button type="button" class="btn btn-danger" onclick="delEdt('${escJs(editId)}');closeModal()">🗑 Supprimer</button>` : ''}
        <button type="submit" class="btn btn-primary">${editId?'Enregistrer':'Ajouter'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-edt').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.jour = jour; fd.creneau = creneau; fd.classe = _edtClasse;
    try {
      if (editId) await apiUpdateEdt(editId, fd); else await apiCreateEdt(fd);
      toast(editId?'Cours modifié':'Cours ajouté','success'); closeModal(); loadEdt();
    }
    catch(err) { toast(err.message,'error'); }
  };
}

/* ── Gestion des créneaux horaires (modifiable par admin/directeur) ── */
function modalGererCreneaux() {
  openModal('🕐 Gérer les créneaux horaires', `
    <div id="creneaux-list" style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px">
      ${CRENEAUX.map((c, i) => `
        <div class="flex gap-2" style="align-items:center">
          <input class="creneau-input" data-idx="${i}" value="${esc(c)}" style="flex:1">
          <button type="button" class="btn btn-danger btn-xs" onclick="this.parentElement.remove()">🗑</button>
        </div>`).join('')}
    </div>
    <button type="button" class="btn btn-outline btn-sm" onclick="ajouterLigneCreneau()">+ Ajouter un créneau</button>
    <div class="alert alert-info mt-3" style="font-size:12px">💡 Ces créneaux s'appliquent à l'emploi du temps de toutes les classes.</div>
    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button type="button" class="btn btn-primary" onclick="enregistrerCreneaux()">Enregistrer</button>
    </div>
  `, { narrow: true });
}
function ajouterLigneCreneau() {
  const div = document.createElement('div');
  div.className = 'flex gap-2';
  div.style.alignItems = 'center';
  div.innerHTML = `<input class="creneau-input" value="" placeholder="Ex : 18h00 - 20h00" style="flex:1">
    <button type="button" class="btn btn-danger btn-xs" onclick="this.parentElement.remove()">🗑</button>`;
  $('#creneaux-list').appendChild(div);
}
async function enregistrerCreneaux() {
  const valeurs = $$('.creneau-input').map(i => i.value.trim()).filter(Boolean);
  if (!valeurs.length) { toast('Au moins un créneau est requis','error'); return; }
  try {
    await apiSaveSettings({ creneaux_horaires: JSON.stringify(valeurs) });
    await refreshCreneaux();
    toast('Créneaux mis à jour ✅','success');
    closeModal();
    loadEdt();
  } catch(e) { toast(e.message,'error'); }
}
window.modalGererCreneaux = modalGererCreneaux;
window.ajouterLigneCreneau = ajouterLigneCreneau;
window.enregistrerCreneaux = enregistrerCreneaux;

async function delEdt(id) {
  try { await apiDeleteEdt(id); toast('Supprimé','success'); loadEdt(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalEdtAdd = modalEdtAdd;
window.delEdt = delEdt;
