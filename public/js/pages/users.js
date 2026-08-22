/* ===================== UTILISATEURS ===================== */
async function pageUsers() {
  $('#content').innerHTML = loadingHtml;
  try {
    const users = await apiGetUsers();

    const render = data => {
      $('#tb-users').innerHTML = data.length ? data.map(u => `<tr>
            <td><strong>${esc(u.full_name)}</strong></td>
            <td class="mono">${esc(u.username)}</td>
            <td><span class="badge bdg-primary">${esc(ROLES[u.role]||u.role)}</span></td>
            <td>${esc(u.email||'—')}</td>
            <td>${esc(u.telephone||'—')}</td>
            <td><span class="badge ${u.active?'bdg-ok':'bdg-err'}">${u.active?'Actif':'Inactif'}</span></td>
            <td class="text-muted" style="font-size:12px">${u.last_login?fmtDate(u.last_login):'Jamais'}</td>
            <td><div class="td-actions">
              <button class="btn btn-outline btn-xs" onclick="modalEditUser(${u.id})">✏️</button>
              ${u.role==='parent'?`<button class="btn btn-outline btn-xs" onclick="modalEnfantsParent(${u.id}, '${escJs(u.full_name)}')" title="Gérer les enfants liés">👨‍👩‍👧</button>`:''}
              <button class="btn btn-outline btn-xs" onclick="modalResetPwd(${u.id}, '${escJs(u.username)}')">🔑</button>
              <button class="btn btn-danger btn-xs" onclick="deleteUser(${u.id})">🗑</button>
            </div></td>
          </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('👥','Aucun utilisateur')}</td></tr>`;
    };

    $('#content').innerHTML = `
      <div class="card">
        <div class="card-header">
          <span class="card-title">👥 Comptes utilisateurs (${users.length})</span>
          <button class="btn btn-primary btn-sm" onclick="modalAddUser()">+ Ajouter un utilisateur</button>
        </div>
        <div class="filters">
          <div class="fg grow"><label>Recherche</label><input id="q-usr" placeholder="Nom, identifiant, email…"></div>
          <div class="fg"><label>Rôle</label><select id="f-urole"><option value="">Tous</option>${Object.entries(ROLES).map(([v,l])=>`<option value="${esc(v)}">${esc(l)}</option>`).join('')}</select></div>
        </div>
        <div class="tbl-wrap"><table>
          <thead><tr id="th-users"><th>Nom complet</th><th>Identifiant</th><th>Rôle</th><th>Email</th><th>Téléphone</th><th>Actif</th><th>Dernière connexion</th><th>Actions</th></tr></thead>
          <tbody id="tb-users"></tbody>
        </table></div>
      </div>`;

    let curr = users;
    render(curr);
    const filter = () => {
      const q = $('#q-usr').value.toLowerCase();
      const role = $('#f-urole').value;
      curr = users.filter(u => {
        const txt = `${u.full_name} ${u.username} ${u.email||''}`.toLowerCase();
        return (!q || txt.includes(q)) && (!role || u.role === role);
      });
      render(curr);
    };
    $('#q-usr').addEventListener('input', filter);
    $('#f-urole').addEventListener('change', filter);

    makeSortableTable('#th-users', () => curr, render,
      ['full_name', 'username', 'role', 'email', 'telephone', 'active', 'last_login', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

window._usersCache = [];
async function modalAddUser() {
  openModal('Ajouter un utilisateur', `
    <form id="f-user" class="flex" style="flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Civilité</label><select name="civilite">
          <option value="">—</option><option value="M.">M.</option><option value="Mme">Mme</option>
        </select></div>
        <div class="fg"><label>Nom complet*</label><input name="full_name" required placeholder="Marie Camara"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Identifiant (login)*</label><input name="username" required placeholder="m.camara"></div>
        <div class="fg"><label>Mot de passe*</label><input type="password" name="password" required minlength="6" placeholder="Min. 6 caractères"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Rôle*</label><select name="role" required>
          ${optionsHtml(Object.entries(ROLES).map(([v,l])=>({value:v,label:l})))}
        </select></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Email</label><input type="email" name="email" placeholder="email@ecole.com"></div>
        <div class="fg"><label>Téléphone</label><input name="telephone" placeholder="+224 6XX XXX XXX"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Créer</button>
      </div>
    </form>
  `);
  $('#f-user').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try {
      await apiCreateUser(fd);
      toast('Utilisateur créé', 'success'); closeModal(); pageUsers();
    } catch(err) { toast(err.message, 'error'); }
  };
}

async function modalEditUser(id) {
  const users = await apiGetUsers();
  const u = users.find(x => x.id === id);
  if (!u) return;
  openModal('Modifier l\'utilisateur', `
    <form id="f-edit-user" class="flex" style="flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Civilité</label><select name="civilite">
          <option value="" ${!u.civilite?'selected':''}>—</option>
          <option value="M." ${u.civilite==='M.'?'selected':''}>M.</option>
          <option value="Mme" ${u.civilite==='Mme'?'selected':''}>Mme</option>
        </select></div>
        <div class="fg"><label>Nom complet*</label><input name="full_name" value="${esc(u.full_name)}" required></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Rôle*</label><select name="role" required>${optionsHtml(Object.entries(ROLES).map(([v,l])=>({value:v,label:l})), u.role, false)}</select></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Email</label><input type="email" name="email" value="${esc(u.email||'')}"></div>
        <div class="fg"><label>Téléphone</label><input name="telephone" value="${esc(u.telephone||'')}"></div>
      </div>
      <div class="fg"><label>Statut</label><select name="active">
        <option value="1" ${u.active?'selected':''}>Actif</option>
        <option value="0" ${!u.active?'selected':''}>Inactif (désactivé)</option>
      </select></div>
      ${motifFieldHtml()}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>
  `);
  $('#f-edit-user').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.active = fd.active === '1' ? 1 : 0;
    try {
      await apiUpdateUser(id, fd);
      toast('Modifié', 'success'); closeModal(); pageUsers();
    } catch(err) { toast(err.message, 'error'); }
  };
}

async function modalResetPwd(id, username) {
  openModal(`Réinitialiser le mot de passe — ${username}`, `
    <form id="f-rpwd">
      <div class="fg mb-3"><label>Nouveau mot de passe (min. 6 car.)</label>
        <input type="password" id="new-pwd" required minlength="6" placeholder="Nouveau mot de passe">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Réinitialiser</button>
      </div>
    </form>
  `, { narrow: true });
  $('#f-rpwd').onsubmit = async e => {
    e.preventDefault();
    try {
      await apiResetPwd(id, $('#new-pwd').value);
      toast('Mot de passe réinitialisé', 'success'); closeModal();
    } catch(err) { toast(err.message, 'error'); }
  };
}

async function deleteUser(id) {
  if (!confirmDel('Supprimer définitivement cet utilisateur ?')) return;
  try { await apiDeleteUser(id); toast('Supprimé', 'success'); pageUsers(); }
  catch(e) { toast(e.message, 'error'); }
}
window.modalAddUser = modalAddUser;
window.modalEditUser = modalEditUser;
window.modalResetPwd = modalResetPwd;
window.deleteUser = deleteUser;

async function modalEnfantsParent(userId, nomParent) {
  const enfants = await apiFetch(`/users/${userId}/enfants`);
  openModal(`👨‍👩‍👧 Enfants liés — ${nomParent}`, `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div id="enfants-liste" style="display:flex;flex-direction:column;gap:8px">
        ${enfants.length ? enfants.map(e => `
          <div class="flex items-center gap-3" style="border:1px solid #E5E7EB;border-radius:8px;padding:10px 12px">
            <div style="flex:1"><strong>${esc(e.prenom)} ${esc(e.nom)}</strong>
              <div class="text-muted" style="font-size:12px">${esc(e.matricule||'')} · ${esc(e.classe||'')}</div></div>
            <button type="button" class="btn btn-danger btn-xs" onclick="retirerEnfantParent(${userId},'${escJs(e.id)}','${escJs(nomParent)}')">🗑</button>
          </div>`).join('') : '<span class="text-muted" style="font-size:13px">Aucun enfant lié pour le moment.</span>'}
      </div>
      <div class="fg">
        <label>Ajouter un enfant (nom, prénom ou matricule)</label>
        <input id="recherche-eleve-parent" placeholder="Tapez pour rechercher…" autocomplete="off">
        <div id="resultats-eleve-parent" style="margin-top:6px;display:flex;flex-direction:column;gap:4px"></div>
      </div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
    </div>`);

  let timer = null;
  $('#recherche-eleve-parent').addEventListener('input', e => {
    clearTimeout(timer);
    const q = e.target.value.trim();
    if (q.length < 2) { $('#resultats-eleve-parent').innerHTML = ''; return; }
    timer = setTimeout(async () => {
      const res = await apiGetEleves(`q=${encodeURIComponent(q)}`);
      const dejaLies = new Set(enfants.map(x => x.id));
      $('#resultats-eleve-parent').innerHTML = res.slice(0, 8).map(e => `
        <div class="flex items-center gap-3" style="padding:6px 8px;border-radius:6px;background:var(--bg-tint)">
          <div style="flex:1;font-size:13px">${esc(e.prenom)} ${esc(e.nom)} — <span class="text-muted">${esc(e.classe||'')}</span></div>
          ${dejaLies.has(e.id)
            ? `<span class="text-muted" style="font-size:11px">Déjà lié</span>`
            : `<button type="button" class="btn btn-primary btn-xs" onclick="lierEnfantParent(${userId},'${escJs(e.id)}','${escJs(nomParent)}')">+ Lier</button>`}
        </div>`).join('') || '<span class="text-muted" style="font-size:12px">Aucun résultat.</span>';
    }, 300);
  });
}
window.modalEnfantsParent = modalEnfantsParent;

async function lierEnfantParent(userId, eleveId, nomParent) {
  try {
    await apiFetch(`/users/${userId}/enfants`, { method: 'POST', body: { eleve_id: eleveId } });
    toast('Enfant lié avec succès', 'success');
    modalEnfantsParent(userId, nomParent);
  } catch(err) { toast(err.message, 'error'); }
}
window.lierEnfantParent = lierEnfantParent;

async function retirerEnfantParent(userId, eleveId, nomParent) {
  if (!confirm("Retirer ce lien ? Le parent perdra l'accès aux informations de cet élève.")) return;
  try {
    await apiFetch(`/users/${userId}/enfants/${eleveId}`, { method: 'DELETE' });
    toast('Lien retiré', 'success');
    modalEnfantsParent(userId, nomParent);
  } catch(err) { toast(err.message, 'error'); }
}
window.retirerEnfantParent = retirerEnfantParent;
