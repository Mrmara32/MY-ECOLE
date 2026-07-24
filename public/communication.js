/* ===================== COMMUNICATION ===================== */
let _commAnnonces = [];
let _commEleves = [];
let _commClasses = [];

async function pageCommunication() {
  $('#content').innerHTML = loadingHtml;
  const [annonces, messages, eleves] = await Promise.all([
    apiGetAnnonces(), apiGetMessages(), apiGetEleves()
  ]);
  _commAnnonces = annonces;
  _commEleves = eleves;
  _commClasses = [...new Set(eleves.map(e=>e.classe).filter(Boolean))].sort();

  let activeTab = 'annonces';
  $('#content').innerHTML = `
  <div class="tabs" id="comm-tabs">
    <div class="tab active" onclick="setCommTab('annonces')">📢 Annonces (${annonces.length})</div>
    <div class="tab" onclick="setCommTab('messages')">✉️ Messages (${messages.length})</div>
  </div>
  <div id="comm-body"></div>`;

  window.setCommTab = (tab) => {
    activeTab = tab;
    $$('#comm-tabs .tab').forEach((t,i) => t.classList.toggle('active', i===(tab==='annonces'?0:1)));
    if (tab==='annonces') renderAnnonces(annonces);
    else renderMessages(messages);
  };
  renderAnnonces(annonces);
}

function renderAnnonces(annonces) {
  const render = data => {
    $('#ann-list').innerHTML = data.length ? data.map(a => `
    <div class="card mb-3" style="border-left:3px solid var(--c-primary)">
      <div class="card-body">
        <div class="flex justify-between items-center mb-2">
          <h3 style="font-size:15px;font-weight:600">${esc(a.titre)}</h3>
          <div class="td-actions">
            <button class="btn btn-outline btn-xs" onclick="modalAnnonce('${escJs(a.id)}')">✏️</button>
            <button class="btn btn-danger btn-xs" onclick="delAnnonce('${escJs(a.id)}')">🗑</button>
          </div>
        </div>
        <div class="text-muted" style="font-size:12px;margin-bottom:10px">
          ✍️ ${esc(a.auteur_nom||'Système')} · 📅 ${fmtDateLong(a.date_publication)}
          ${a.cible&&a.cible!=='tous'?`· 🎯 ${esc(a.cible)}`:''}
        </div>
        <div style="font-size:13px;white-space:pre-line">${esc(a.contenu)}</div>
      </div>
    </div>`).join('') : emptyHtml('📢','Aucune annonce publiée','Utilisez le bouton + pour publier une annonce');
  };

  $('#comm-body').innerHTML = `
  <div class="card-header" style="background:#fff;padding:14px 0;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center">
    <div></div>
    <button class="btn btn-primary btn-sm" onclick="modalAnnonce()">+ Publier une annonce</button>
  </div>
  <div id="ann-list"></div>`;
  render(annonces);
}

function modalAnnonce(id = null) {
  const data = id ? _commAnnonces.find(a => a.id === id) : null;
  const isEdit = !!data;
  openModal(isEdit?'Modifier l\'annonce':'Publier une annonce', `
    <form id="f-ann" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Titre*</label><input name="titre" value="${esc((data&&data.titre)||'')}" required placeholder="Réunion des parents d'élèves…"></div>
      <div class="fg"><label>Cible</label><select name="cible">
        <option value="tous" ${(!data||!data.cible||data.cible==='tous')?'selected':''}>Tout le monde</option>
        <option value="parents" ${data&&data.cible==='parents'?'selected':''}>Parents d'élèves</option>
        <option value="enseignants" ${data&&data.cible==='enseignants'?'selected':''}>Enseignants</option>
        <option value="eleves" ${data&&data.cible==='eleves'?'selected':''}>Élèves</option>
      </select></div>
      <div class="fg"><label>Contenu*</label><textarea name="contenu" rows="6" required placeholder="Détails de l'annonce…">${esc((data&&data.contenu)||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${isEdit?'Enregistrer':'Publier'}</button>
      </div>
    </form>`);
  $('#f-ann').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      if (isEdit) await apiUpdateAnnonce(data.id, fd); else await apiCreateAnnonce(fd);
      toast(isEdit?'Annonce modifiée':'Annonce publiée','success'); closeModal(); pageCommunication();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delAnnonce(id) {
  if (!confirmDel('Supprimer cette annonce ?')) return;
  try { await apiDeleteAnnonce(id); toast('Annonce supprimée','success'); pageCommunication(); }
  catch(e) { toast(e.message,'error'); }
}

function renderMessages(messages) {
  const render = data => {
    $('#tb-msg').innerHTML = data.length ? data.map(m => `<tr>
        <td>${esc(m.expediteur_nom||'Système')}</td>
        <td><span class="badge ${m.destinataire_type==='tous'||m.destinataire_type==='tous_parents'?'bdg-err':m.destinataire_type==='classe'?'bdg-primary':'bdg-gray'}">
          ${m.destinataire_type==='classe'?'Classe '+esc(m.destinataire_id||'?'):m.destinataire_type==='eleve'?'Élève':m.destinataire_type==='tous_parents'?'Tous les parents':'Tous'}
        </span></td>
        <td><strong>${esc(m.sujet||'(Sans objet)')}</strong><br><span class="text-muted" style="font-size:11px">${esc((m.contenu||'').substring(0,80))}…</span></td>
        <td style="font-size:12px;white-space:nowrap">${fmtDate(m.date_envoi)}</td>
        <td><button class="btn btn-danger btn-xs" onclick="delMsg('${escJs(m.id)}')">🗑</button></td>
      </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('✉️','Aucun message envoyé')}</td></tr>`;
  };

  $('#comm-body').innerHTML = `
  <div class="card-header" style="background:#fff;padding:14px 0;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center">
    <div class="fg" style="min-width:260px"><input id="q-msg" placeholder="🔍 Rechercher un message…"></div>
    <button class="btn btn-primary btn-sm" onclick="modalMessage()">+ Nouveau message</button>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr id="th-msg"><th>De</th><th>À</th><th>Sujet</th><th>Date</th><th>Actions</th></tr></thead>
    <tbody id="tb-msg"></tbody>
  </table></div>`;

  let curr = messages;
  render(curr);
  $('#q-msg').addEventListener('input', () => {
    const q = $('#q-msg').value.toLowerCase();
    curr = messages.filter(m => `${m.sujet||''} ${m.contenu||''} ${m.expediteur_nom||''}`.toLowerCase().includes(q));
    render(curr);
  });
  makeSortableTable('#th-msg', () => curr, render, ['expediteur_nom', 'destinataire_type', 'sujet', 'date_envoi', null]);
}

function modalMessage() {
  const eleves = _commEleves, classes = _commClasses;
  openModal('Envoyer un message aux parents', `
    <form id="f-msg" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Destinataire*</label>
        <select name="destinataire_type" id="msg-dest-type" required onchange="updateMsgDest()">
          <option value="tous_parents">Tous les parents d'élèves</option>
          <option value="classe">Une classe spécifique</option>
          <option value="eleve">Un élève spécifique</option>
        </select>
      </div>
      <div id="msg-dest-extra" style="display:none" class="fg">
        <label id="msg-dest-lbl">Choisir</label>
        <select id="msg-dest-val"></select>
      </div>
      <div class="fg"><label>Sujet</label><input name="sujet" placeholder="Objet du message…"></div>
      <div class="fg"><label>Message*</label><textarea name="contenu" rows="5" required placeholder="Chers parents…"></textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">📤 Envoyer</button>
      </div>
    </form>`);

  window.updateMsgDest = () => {
    const type = $('#msg-dest-type').value;
    const extra = $('#msg-dest-extra');
    const sel = $('#msg-dest-val');
    if (type === 'tous_parents') { extra.style.display='none'; return; }
    extra.style.display='block';
    if (type === 'classe') {
      $('#msg-dest-lbl').textContent = 'Classe';
      sel.innerHTML = classes.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
    } else {
      $('#msg-dest-lbl').textContent = 'Élève';
      sel.innerHTML = eleves.filter(e=>e.statut==='actif').map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)}</option>`).join('');
    }
  };

  $('#f-msg').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const type = $('#msg-dest-type').value;
    const destId = type !== 'tous_parents' ? $('#msg-dest-val').value : null;
    try {
      await apiCreateMessage({ destinataire_type: type, destinataire_id: destId, sujet: fd.sujet, contenu: fd.contenu });
      toast('Message envoyé ✅','success'); closeModal(); pageCommunication();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delMsg(id) {
  if (!confirmDel()) return;
  try { await apiDeleteMessage(id); toast('Supprimé','success'); pageCommunication(); }
  catch(e) { toast(e.message,'error'); }
}
window.modalAnnonce = modalAnnonce;
window.delAnnonce = delAnnonce;
window.modalMessage = modalMessage;
window.delMsg = delMsg;
