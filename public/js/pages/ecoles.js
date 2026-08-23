/* ===================== SUPERVISION DES ÉCOLES (SUPER-ADMIN) ===================== */
const STATUT_LICENCE_BADGE = {
  essai:     '<span class="badge bdg-primary">🕐 Essai</span>',
  active:    '<span class="badge bdg-ok">✔ Active</span>',
  suspendue: '<span class="badge bdg-err">⏸ Suspendue</span>',
  expiree:   '<span class="badge bdg-err">✕ Expirée</span>',
};

async function pageEcoles() {
  $('#content').innerHTML = loadingHtml;
  const ecoles = await apiGetEcoles();

  $('#content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">🏢 Écoles clientes (${ecoles.length})</span>
        <div class="card-actions">
          <a class="btn btn-outline btn-sm" href="/inscription-ecole.html" target="_blank">+ Lien d'inscription</a>
        </div>
      </div>
      <div class="card-body">
        ${ecoles.length ? `
        <table class="table">
          <thead><tr><th>École</th><th>Code</th><th>Statut licence</th><th>Expiration</th><th>Utilisateurs</th><th>Élèves</th><th></th></tr></thead>
          <tbody>
            ${ecoles.map(e => `
              <tr>
                <td><strong>${esc(e.nom)}</strong>${e.email_contact ? `<div class="text-muted" style="font-size:11.5px">${esc(e.email_contact)}</div>` : ''}</td>
                <td class="mono">${esc(e.code)}</td>
                <td>${STATUT_LICENCE_BADGE[e.statut_licence] || esc(e.statut_licence)}</td>
                <td>${e.date_expiration_licence ? fmtDate(e.date_expiration_licence) : '—'}</td>
                <td>${e.nb_utilisateurs}</td>
                <td>${e.nb_eleves}</td>
                <td><button class="btn btn-outline btn-xs" onclick="modalDetailEcole(${e.id})">Gérer</button></td>
              </tr>`).join('')}
          </tbody>
        </table>` : emptyHtml('🏢', 'Aucune école cliente pour le moment', 'Partagez le lien d\'inscription pour accueillir votre première école.')}
      </div>
    </div>`;
}
window.pageEcoles = pageEcoles;

async function modalDetailEcole(ecoleId) {
  const e = await apiGetEcole(ecoleId);
  openModal(`🏢 ${e.nom}`, `
    <div style="display:flex;flex-direction:column;gap:16px">
      <div class="stats-grid" style="grid-template-columns:repeat(3,1fr)">
        <div class="stat"><div class="stat-label">Utilisateurs</div><div class="stat-val" style="font-size:16px">${e.nb_utilisateurs}</div></div>
        <div class="stat"><div class="stat-label">Élèves actifs</div><div class="stat-val" style="font-size:16px">${e.nb_eleves}</div></div>
        <div class="stat"><div class="stat-label">Personnel</div><div class="stat-val" style="font-size:16px">${e.nb_personnel}</div></div>
      </div>

      <form id="f-ecole" style="display:flex;flex-direction:column;gap:14px">
        <div class="fg"><label>Nom de l'école</label><input name="nom" value="${esc(e.nom)}"></div>
        <div class="form-2">
          <div class="fg"><label>Email de contact</label><input type="email" name="email_contact" value="${esc(e.email_contact||'')}"></div>
          <div class="fg"><label>Téléphone</label><input name="telephone_contact" value="${esc(e.telephone_contact||'')}"></div>
        </div>
        <div class="form-2">
          <div class="fg"><label>Statut de licence</label><select name="statut_licence">
            ${optionsHtml([
              {value:'essai',label:'Essai'},{value:'active',label:'Active'},
              {value:'suspendue',label:'Suspendue'},{value:'expiree',label:'Expirée'},
            ], e.statut_licence, false)}
          </select></div>
          <div class="fg"><label>Date d'expiration</label><input type="date" name="date_expiration_licence" value="${e.date_expiration_licence||''}"></div>
        </div>
        <div class="text-muted" style="font-size:11.5px">Code établissement : <strong class="mono">${esc(e.code)}</strong> · Créée le ${fmtDate(e.created_at)}</div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button>
          <button type="submit" class="btn btn-primary">Enregistrer</button>
        </div>
      </form>
      ${e.id !== 1 ? `
      <div style="border-top:1px solid var(--line,#E1E8E4);padding-top:14px;margin-top:2px">
        <div style="font-size:12px;font-weight:700;color:#DC2626;margin-bottom:8px">Zone de danger</div>
        <button type="button" class="btn btn-outline" style="width:100%;color:#DC2626;border-color:#FCA5A5" onclick="confirmerSuppressionEcole(${e.id}, '${escJs(e.nom)}', '${escJs(e.code)}')">🗑 Supprimer définitivement cette école</button>
        <div class="text-muted" style="font-size:11px;margin-top:6px">Supprime aussi toutes ses données : élèves, personnel, finances, tout. Action irréversible.</div>
      </div>` : ''}
    </div>`);

  $('#f-ecole').onsubmit = async ev => {
    ev.preventDefault();
    const fd = Object.fromEntries(new FormData(ev.target));
    try {
      await apiUpdateEcole(ecoleId, fd);
      toast('École mise à jour', 'success');
      closeModal();
      pageEcoles();
    } catch(err) { toast(err.message, 'error'); }
  };
}
window.modalDetailEcole = modalDetailEcole;

function confirmerSuppressionEcole(ecoleId, nom, code) {
  openModal(`⚠️ Supprimer « ${esc(nom)} » ?`, `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="background:#FEF2F2;border:1px solid #FCA5A5;color:#991B1B;padding:12px 14px;border-radius:10px;font-size:13px">
        Cette action supprime <strong>définitivement</strong> l'école « ${esc(nom)} » ainsi que
        <strong>toutes ses données</strong> : élèves, personnel, finances, utilisateurs — tout,
        sans possibilité de retour en arrière.
      </div>
      <div class="fg">
        <label>Pour confirmer, tapez le code établissement : <strong class="mono">${esc(code)}</strong></label>
        <input id="confirm-code-suppr" placeholder="${esc(code)}" autocomplete="off">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="button" class="btn" style="background:#DC2626;color:#fff" id="btn-confirmer-suppr" disabled>Supprimer définitivement</button>
      </div>
    </div>`);

  const input = $('#confirm-code-suppr');
  const btn = $('#btn-confirmer-suppr');
  input.addEventListener('input', () => { btn.disabled = input.value.trim() !== code; });
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = 'Suppression…';
    try {
      await apiDeleteEcole(ecoleId);
      toast('École supprimée', 'success');
      closeModal();
      pageEcoles();
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Supprimer définitivement';
    }
  });
}
window.confirmerSuppressionEcole = confirmerSuppressionEcole;
