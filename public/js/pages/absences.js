/* ===================== ABSENCES (ÉLÈVES + PERSONNEL) ===================== */
let _absEleves = [];
let _absPersonnel = [];
let _absAffichees = [];
let _nomEcoleAbs = '';

async function pageAbsences() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [absences, eleves, absPersonnel, personnel] = await Promise.all([
      apiGetAbsences(), apiGetEleves(), apiGetAbsencesPersonnel(), apiGetPersonnel()
    ]);
    _absEleves = eleves;
    _absPersonnel = personnel;

    $('#content').innerHTML = `
    <div class="tabs" id="abs-tabs">
      <div class="tab active" onclick="setAbsTab('eleves')">🎓 Élèves (${absences.length})</div>
      <div class="tab" onclick="setAbsTab('personnel')">👨‍🏫 Personnel (${absPersonnel.filter(a=>!a.date_fin || a.date_fin>=today()).length} en cours)</div>
    </div>
    <div id="abs-body"></div>`;

    window.setAbsTab = (tab) => {
      $$('#abs-tabs .tab').forEach((t,i) => t.classList.toggle('active', i===(tab==='eleves'?0:1)));
      if (tab === 'eleves') renderAbsEleves(absences, eleves);
      else renderAbsPersonnel(absPersonnel, personnel);
    };
    renderAbsEleves(absences, eleves);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function renderAbsEleves(absences, eleves) {
  const classes = [...new Set(eleves.map(e=>e.classe).filter(Boolean))].sort();

  const render = data => {
    _absAffichees = data;
    const { items, page, totalPages, total } = paginate('abs-eleves', data);
    $('#tb-abs').innerHTML = items.length ? items.map(a => `<tr>
      <td>${fmtDate(a.date_abs)}</td>
      <td><strong>${esc(a.prenom)} ${esc(a.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(a.matricule||'')}</span></td>
      <td><span class="badge bdg-primary">${esc(a.classe||'—')}</span></td>
      <td><span class="badge ${a.type==='absence'?'bdg-err':'bdg-warn'}">${a.type==='absence'?'Absence':'Retard'}</span></td>
      <td>${esc(a.duree||'journée')}</td>
      <td><span class="badge ${a.justifie?'bdg-ok':'bdg-gray'}">${a.justifie?'Justifiée':'Non justifiée'}</span></td>
      <td class="text-muted">${esc(a.motif||'—')}</td>
      <td><div class="td-actions">
        ${a.contact?`<button class="btn btn-outline btn-xs" title="${a.parent_prevenu_le?'Parent déjà prévenu le '+fmtDate(String(a.parent_prevenu_le).slice(0,10)):'Prévenir le parent'}" onclick="modalPrevenirParent('${escJs(a.id)}')">${a.parent_prevenu_le?'✅':'📲'} Prévenir</button>`:''}
        ${!a.justifie?`<button class="btn btn-ok btn-xs" onclick="justifierAbs('${escJs(a.id)}')">✔ Justifier</button>`:''}
        ${currentUser.role !== 'enseignant' ? `<button class="btn btn-danger btn-xs" onclick="delAbs('${escJs(a.id)}')">🗑</button>` : ''}
      </div></td>
    </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('📅','Aucune absence trouvée')}</td></tr>`;
    $('#pag-abs').innerHTML = paginationHtml('abs-eleves', page, totalPages, total);
  };

  $('#abs-body').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">📅 Absences & Retards des élèves</span>
      <button class="btn btn-primary btn-sm" onclick="modalAbsence()">+ Enregistrer</button>
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-abs" placeholder="Nom, prénom, matricule…"></div>
      <div class="fg"><label>Date début</label><input type="date" id="f-adeb" value="${new Date(Date.now()-7*86400000).toISOString().split('T')[0]}"></div>
      <div class="fg"><label>Date fin</label><input type="date" id="f-afin" value="${today()}"></div>
      <div class="fg"><label>Classe</label><select id="f-acls"><option value="">Toutes</option>${classes.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
      <div class="fg"><label>Type</label><select id="f-atype"><option value="">Tous</option><option value="absence">Absence</option><option value="retard">Retard</option></select></div>
      <button class="btn btn-outline btn-sm" onclick="filterAbs()">🔍 Filtrer</button>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr id="th-abs"><th>Date</th><th>Élève</th><th>Classe</th><th>Type</th><th>Durée</th><th>Statut</th><th>Motif</th><th>Actions</th></tr></thead>
      <tbody id="tb-abs"></tbody>
    </table></div>
    <div id="pag-abs"></div>
  </div>`;

  let curr = absences;
  getPaginator('abs-eleves').onChange = () => render(curr);
  render(curr);

  window.filterAbs = async () => {
    const deb = $('#f-adeb').value;
    const fin = $('#f-afin').value;
    const cls = $('#f-acls').value;
    const type = $('#f-atype').value;
    const q = $('#q-abs').value.toLowerCase();
    let qs = '';
    if (deb) qs += `&date_debut=${deb}`;
    if (fin) qs += `&date_fin=${fin}`;
    if (cls) qs += `&classe=${encodeURIComponent(cls)}`;
    try {
      let data = await apiGetAbsences(qs.slice(1));
      if (type) data = data.filter(a=>a.type===type);
      if (q) data = data.filter(a => `${a.nom} ${a.prenom} ${a.matricule||''}`.toLowerCase().includes(q));
      curr = data;
      resetPaginator('abs-eleves');
      render(curr);
    } catch(e) { toast(e.message,'error'); }
  };
  $('#q-abs').addEventListener('input', filterAbs);

  makeSortableTable('#th-abs', () => curr, render,
    ['date_abs', row => `${row.prenom} ${row.nom}`, 'classe', 'type', 'duree', 'justifie', 'motif', null]);
}

function modalAbsence() {
  const eleves = _absEleves;
  openModal('Enregistrer une absence / retard', `
    <form id="f-abs" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Élève*</label>
        <select name="eleve_id" required>
          <option value="">— Chercher un élève —</option>
          ${eleves.filter(e=>e.statut==='actif').map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} (${esc(e.classe||'?')})</option>`).join('')}
        </select>
      </div>
      <div class="form-3">
        <div class="fg"><label>Date*</label><input type="date" name="date_abs" value="${today()}" required></div>
        <div class="fg"><label>Type</label><select name="type">
          <option value="absence">Absence</option>
          <option value="retard">Retard</option>
        </select></div>
        <div class="fg"><label>Durée</label><select name="duree">
          <option>journée</option><option>demi-journée matin</option><option>demi-journée après-midi</option>
        </select></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Justifiée ?</label><select name="justifie">
          <option value="0">Non justifiée</option>
          <option value="1">Justifiée</option>
        </select></div>
        <div class="fg"><label>Motif</label><input name="motif" placeholder="Maladie, famille…"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-abs').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.justifie = fd.justifie === '1';
    try { await apiCreateAbsence(fd); toast('Enregistrée','success'); closeModal(); pageAbsences(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function justifierAbs(id) {
  const motif = prompt('Motif de la justification :','');
  if (motif === null) return;
  try { await apiUpdateAbsence(id, { justifie: true, motif }); toast('Justifiée','success'); pageAbsences(); }
  catch(e) { toast(e.message,'error'); }
}

async function delAbs(id) {
  if (!confirmDel()) return;
  try { await apiDeleteAbsence(id); toast('Supprimée','success'); pageAbsences(); }
  catch(e) { toast(e.message,'error'); }
}

/* ===================== ABSENCES DU PERSONNEL (point 6) ===================== */
function renderAbsPersonnel(absPersonnel, personnel) {
  const enCours = a => !a.date_fin || a.date_fin >= today();

  const render = data => {
    const { items, page, totalPages, total } = paginate('abs-personnel', data);
    $('#tb-abs-per').innerHTML = items.length ? items.map(a => `<tr>
      <td>${enCours(a)?'<span class="badge bdg-err">🔴 En cours</span>':'<span class="badge bdg-gray">Terminée</span>'}</td>
      <td><strong>${esc(a.prenom)} ${esc(a.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(a.poste||'')}${a.matiere?' · '+esc(a.matiere):''}</span></td>
      <td>${fmtDate(a.date_debut)}</td>
      <td>${a.date_fin?fmtDate(a.date_fin):'<span class="text-muted">indéterminé</span>'}</td>
      <td class="text-muted">${esc(a.motif||'—')}</td>
      <td>${esc(a.remplace_par||'—')}</td>
      <td><div class="td-actions">
        ${enCours(a)?`<button class="btn btn-ok btn-xs" onclick="terminerAbsPersonnel('${escJs(a.id)}')">✔ Marquer de retour</button>`:''}
        <button class="btn btn-danger btn-xs" onclick="delAbsPersonnel('${escJs(a.id)}')">🗑</button>
      </div></td>
    </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('👨‍🏫','Aucune absence de personnel enregistrée')}</td></tr>`;
    $('#pag-abs-per').innerHTML = paginationHtml('abs-personnel', page, totalPages, total);
  };

  const absentsAujourdhui = absPersonnel.filter(enCours);

  $('#abs-body').innerHTML = `
  ${absentsAujourdhui.length ? `<div class="alert alert-warn mb-4">
    🔴 <strong>${absentsAujourdhui.length}</strong> membre${absentsAujourdhui.length>1?'s':''} du personnel actuellement absent${absentsAujourdhui.length>1?'s':''} :
    ${absentsAujourdhui.map(a=>`${esc(a.prenom)} ${esc(a.nom)}`).join(', ')}
  </div>` : `<div class="alert alert-ok mb-4">✅ Aucun enseignant absent actuellement.</div>`}
  <div class="card">
    <div class="card-header">
      <span class="card-title">👨‍🏫 Absences du personnel</span>
      ${currentUser.role !== 'enseignant' ? `<button class="btn btn-primary btn-sm" onclick="modalAbsPersonnel()">+ Signaler une absence</button>` : ''}
    </div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="q-absper" placeholder="Nom, prénom, poste…"></div>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr id="th-abs-per"><th>Statut</th><th>Personnel</th><th>Depuis le</th><th>Jusqu'au</th><th>Motif</th><th>Remplacé par</th><th>Actions</th></tr></thead>
      <tbody id="tb-abs-per"></tbody>
    </table></div>
    <div id="pag-abs-per"></div>
  </div>`;
  let curr = absPersonnel;
  getPaginator('abs-personnel').onChange = () => render(curr);
  render(curr);
  $('#q-absper').addEventListener('input', () => {
    const q = $('#q-absper').value.toLowerCase();
    curr = absPersonnel.filter(a => `${a.nom} ${a.prenom} ${a.poste||''}`.toLowerCase().includes(q));
    resetPaginator('abs-personnel');
    render(curr);
  });
  makeSortableTable('#th-abs-per', () => curr, render,
    [row => enCours(row) ? 0 : 1, row => `${row.prenom} ${row.nom}`, 'date_debut', 'date_fin', 'motif', 'remplace_par', null]);
}

function modalAbsPersonnel() {
  const personnel = _absPersonnel;
  openModal('Signaler une absence du personnel', `
    <form id="f-abs-per" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Membre du personnel*</label>
        <select name="personnel_id" required>
          <option value="">— Choisir —</option>
          ${personnel.map(p=>`<option value="${esc(p.id)}">${esc(p.prenom)} ${esc(p.nom)} — ${esc(p.poste||'?')}${p.matiere?' ('+esc(p.matiere)+')':''}</option>`).join('')}
        </select>
      </div>
      <div class="form-2">
        <div class="fg"><label>Absent depuis le*</label><input type="date" name="date_debut" value="${today()}" required></div>
        <div class="fg"><label>Jusqu'au (si connu)</label><input type="date" name="date_fin"></div>
      </div>
      <div class="fg"><label>Motif</label><input name="motif" placeholder="Maladie, formation, congé…"></div>
      <div class="fg"><label>Remplacé par (optionnel)</label><input name="remplace_par" placeholder="Nom du remplaçant"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Signaler</button>
      </div>
    </form>`, { narrow: true });
  $('#f-abs-per').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (!fd.date_fin) delete fd.date_fin;
    try { await apiSignalerAbsencePersonnel(fd); toast('Absence signalée','success'); closeModal(); pageAbsences(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function terminerAbsPersonnel(id) {
  try { await apiUpdateAbsencePersonnel(id, { date_fin: today() }); toast('Retour enregistré ✅','success'); pageAbsences(); }
  catch(e) { toast(e.message,'error'); }
}

async function delAbsPersonnel(id) {
  if (!confirmDel()) return;
  try { await apiDeleteAbsencePersonnel(id); toast('Supprimée','success'); pageAbsences(); }
  catch(e) { toast(e.message,'error'); }
}

window.modalAbsence = modalAbsence;
window.justifierAbs = justifierAbs;
window.delAbs = delAbs;
window.modalAbsPersonnel = modalAbsPersonnel;
window.terminerAbsPersonnel = terminerAbsPersonnel;
window.delAbsPersonnel = delAbsPersonnel;

/* ---------- Prévenir le parent d'une absence ou d'un retard (WhatsApp / SMS / appel) ---------- */
const ABS_MODELE_DEFAUT =
  "Bonjour {parent}, {ecole} vous informe que {eleve} ({classe}) {situation} le {date}{motif}. " +
  "Merci de nous contacter pour toute précision.";

function messageAbsence(a, modele) {
  const retard = a.type === 'retard';
  return modele
    .replaceAll('{parent}', a.contact && a.contact.nom ? a.contact.nom : 'Madame, Monsieur')
    .replaceAll('{eleve}', `${a.prenom} ${a.nom}`)
    .replaceAll('{classe}', a.classe || '')
    .replaceAll('{situation}', retard ? "est arrivé(e) en retard" : (a.duree && a.duree !== 'journée' ? `était absent(e) (${a.duree})` : 'était absent(e)'))
    .replaceAll('{date}', fmtDate(a.date_abs))
    .replaceAll('{motif}', a.motif ? ` — motif indiqué : ${a.motif}` : '')
    .replaceAll('{ecole}', _nomEcoleAbs || 'Votre école');
}

async function modalPrevenirParent(id) {
  const a = _absAffichees.find(x => x.id === id);
  if (!a || !a.contact) { toast('Aucun numéro de parent enregistré pour cet élève', 'error'); return; }
  if (!_nomEcoleAbs) { try { _nomEcoleAbs = (await apiGetSettings()).ecole_nom || ''; } catch (e) { /* nom par défaut */ } }
  let modele = ABS_MODELE_DEFAUT;
  try { modele = localStorage.getItem('gs_modele_absence') || modele; } catch (e) { /* stockage indisponible */ }
  const intl = numeroInternational(a.contact.telephone);
  const auto = intl && await whatsappAutoActif();
  const autoSms = intl && await smsAutoActif();
  openModal('📲 Prévenir le parent', `
    <div class="alert alert-info"><strong>${esc(a.prenom)} ${esc(a.nom)}</strong> — ${a.type === 'retard' ? 'Retard' : 'Absence'} du ${fmtDate(a.date_abs)}<br>
      ${esc(a.contact.nom || a.contact.lien)} <span class="text-muted">(${esc(a.contact.lien)})</span> · <span class="mono">${esc(a.contact.telephone)}</span></div>
    <div class="fg"><label>Message — {parent} {eleve} {classe} {situation} {date} {motif} {ecole}</label>
      <textarea id="abs-modele" rows="4">${esc(modele)}</textarea></div>
    <div class="modal-footer" style="flex-wrap:wrap;gap:8px">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
      ${auto ? `<button class="btn btn-primary" onclick="envoyerWhatsappAutoAbsence('${escJs(id)}')">📤 Envoyer automatiquement</button>` : ''}
      ${autoSms ? `<button class="btn btn-primary" onclick="envoyerSmsAutoAbsence('${escJs(id)}')">📨 SMS automatique</button>` : ''}
      ${intl ? `<button class="btn btn-ok" onclick="envoyerPrevenirParent('${escJs(id)}','whatsapp')">WhatsApp</button>` : ''}
      <button class="btn btn-primary" onclick="envoyerPrevenirParent('${escJs(id)}','sms')">SMS</button>
      <button class="btn btn-outline" onclick="envoyerPrevenirParent('${escJs(id)}','appel')">Appeler</button>
      <button class="btn btn-outline" onclick="envoyerPrevenirParent('${escJs(id)}','copie')">Copier</button>
    </div>`);
  $('#abs-modele').addEventListener('change', e => {
    try { localStorage.setItem('gs_modele_absence', e.target.value); } catch (err) { /* sans importance */ }
  });
}

async function envoyerPrevenirParent(id, canal) {
  const a = _absAffichees.find(x => x.id === id);
  if (!a || !a.contact) return;
  const texte = messageAbsence(a, ($('#abs-modele').value || '').trim() || ABS_MODELE_DEFAUT);
  const tel = String(a.contact.telephone).replace(/[^\d+]/g, '');
  if (canal === 'whatsapp') window.open(`https://wa.me/${numeroInternational(a.contact.telephone)}?text=${encodeURIComponent(texte)}`, '_blank', 'noopener');
  else if (canal === 'sms') window.location.href = `sms:${tel}?body=${encodeURIComponent(texte)}`;
  else if (canal === 'appel') window.location.href = `tel:${tel}`;
  else {
    try { await navigator.clipboard.writeText(texte); toast('Message copié', 'success'); }
    catch (e) { toast('Copie impossible : sélectionnez le message à la main', 'error'); return; }
  }
  try {
    await apiPrevenirParentAbsence(id, canal);
    a.parent_prevenu_le = new Date().toISOString();
    toast('Enregistré : parent prévenu', 'success');
  } catch (e) { toast("Message préparé, mais non enregistré dans le journal : " + e.message, 'warning'); }
}
window.modalPrevenirParent = modalPrevenirParent;
window.envoyerPrevenirParent = envoyerPrevenirParent;


async function envoyerWhatsappAutoAbsence(id) {
  const a = _absAffichees.find(x => x.id === id);
  if (!a || !confirm(`Envoyer le message WhatsApp à ${a.contact.nom || a.contact.lien} ?`)) return;
  try {
    await apiWhatsappAbsence(id);
    a.parent_prevenu_le = new Date().toISOString();
    toast('Message WhatsApp envoyé', 'success'); closeModal();
  } catch (e) { toast(e.message, 'error'); }
}
window.envoyerWhatsappAutoAbsence = envoyerWhatsappAutoAbsence;


async function envoyerSmsAutoAbsence(id) {
  const a = _absAffichees.find(x => x.id === id);
  if (!a || !confirm(`Envoyer le SMS à ${a.contact.nom || a.contact.lien} ?`)) return;
  const message = messageAbsence(a, ($('#abs-modele').value || '').trim() || ABS_MODELE_DEFAUT);
  try {
    await apiSmsAbsence(id, message);
    a.parent_prevenu_le = new Date().toISOString();
    toast('SMS envoyé', 'success'); closeModal();
  } catch (e) { toast(e.message, 'error'); }
}
window.envoyerSmsAutoAbsence = envoyerSmsAutoAbsence;
