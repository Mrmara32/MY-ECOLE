/* ===================== CANDIDATURES ENSEIGNANTS ===================== */
async function pageCandidatures() {
  $('#content').innerHTML = loadingHtml;
  try {
    const candidatures = await apiGetCandidatures();
    const enAttente = candidatures.filter(c => c.statut === 'en_attente').length;

    const STATUT_BADGE = {
      en_attente: '<span class="badge bdg-warn">⏳ En attente</span>',
      approuvee: '<span class="badge bdg-ok">✔ Approuvée</span>',
      rejetee: '<span class="badge bdg-err">✕ Rejetée</span>',
    };

    const render = data => {
      $('#tb-cand').innerHTML = data.length ? data.map(c => `<tr>
        <td><strong>${esc(c.prenom)} ${esc(c.nom)}</strong></td>
        <td>${esc(c.telephone||'—')}${c.email?'<br><span class="text-muted" style="font-size:11px">'+esc(c.email)+'</span>':''}</td>
        <td><span class="badge bdg-primary">${esc(CYCLE_LABELS[c.cycle]||c.cycle||'—')}</span></td>
        <td style="max-width:220px;font-size:12px">${esc(c.matieres||'—')}</td>
        <td style="max-width:200px;font-size:12px">${esc(c.disponibilites||'—')}</td>
        <td>${fmtDate(c.date_candidature)}</td>
        <td>${STATUT_BADGE[c.statut]||''}</td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="voirCandidature('${escJs(c.id)}')">👁</button>
          ${c.statut==='en_attente' ? `
            <button class="btn btn-ok btn-xs" onclick="approuverCand('${escJs(c.id)}')">✔ Approuver</button>
            <button class="btn btn-danger btn-xs" onclick="rejeterCandPrompt('${escJs(c.id)}')">✕ Rejeter</button>
          ` : `<button class="btn btn-danger btn-xs" onclick="delCandidature('${escJs(c.id)}')">🗑</button>`}
        </div></td>
      </tr>`).join('') : `<tr><td colspan="8">${emptyHtml('📋','Aucune candidature reçue')}</td></tr>`;
    };

    $('#content').innerHTML = `
    <div class="alert alert-info mb-4">
      💡 Partagez ce lien avec les candidats enseignants pour qu'ils postulent en ligne eux-mêmes :
      <br><code style="background:#fff;padding:4px 8px;border-radius:4px;display:inline-block;margin-top:6px">${location.origin}/postuler.html</code>
      <button class="btn btn-outline btn-xs" style="margin-left:8px" onclick="copierLienCandidature()">📋 Copier le lien</button>
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">📋 Candidatures (${candidatures.length}) ${enAttente>0?`— <span class="text-warn">${enAttente} en attente</span>`:''}</span>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-cand" placeholder="Nom, prénom, matières…"></div>
        <div class="fg"><label>Statut</label><select id="f-candstat">
          <option value="">Tous</option><option value="en_attente">En attente</option>
          <option value="approuvee">Approuvée</option><option value="rejetee">Rejetée</option>
        </select></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-cand"><th>Candidat</th><th>Contact</th><th>Cycle</th><th>Matières</th><th>Disponibilités</th><th>Date</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-cand"></tbody>
      </table></div>
    </div>`;

    let curr = candidatures;
    render(curr);
    const filter = () => {
      const q = $('#q-cand').value.toLowerCase();
      const stat = $('#f-candstat').value;
      curr = candidatures.filter(c => {
        const txt = `${c.nom} ${c.prenom} ${c.matieres||''}`.toLowerCase();
        return (!q||txt.includes(q)) && (!stat||c.statut===stat);
      });
      render(curr);
    };
    $('#q-cand').addEventListener('input', filter);
    $('#f-candstat').addEventListener('change', filter);
    makeSortableTable('#th-cand', () => curr, render,
      [row => `${row.prenom} ${row.nom}`, 'telephone', 'cycle', 'matieres', null, 'date_candidature', 'statut', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function copierLienCandidature() {
  navigator.clipboard.writeText(location.origin + '/postuler.html')
    .then(() => toast('Lien copié ✅','success'))
    .catch(() => toast('Impossible de copier automatiquement','warning'));
}

async function voirCandidature(id) {
  const c = await apiGetCandidature(id);
  openModal(`Candidature — ${c.prenom} ${c.nom}`, `
    <div style="display:flex;flex-direction:column;gap:10px;font-size:13px">
      <div><strong class="text-muted">Téléphone :</strong> ${esc(c.telephone||'—')}</div>
      <div><strong class="text-muted">Email :</strong> ${esc(c.email||'—')}</div>
      <div><strong class="text-muted">Cycle souhaité :</strong> ${esc(CYCLE_LABELS[c.cycle]||c.cycle||'—')}</div>
      <div><strong class="text-muted">Matières :</strong> ${esc(c.matieres||'—')}</div>
      <div><strong class="text-muted">Disponibilités :</strong> ${esc(c.disponibilites||'—')}</div>
      <div><strong class="text-muted">Message :</strong> ${esc(c.message||'—')}</div>
      <div><strong class="text-muted">Reçue le :</strong> ${fmtDateLong(c.date_candidature)}</div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
      ${c.statut==='en_attente' ? `
        <button class="btn btn-danger" onclick="rejeterCandPrompt('${escJs(c.id)}')">✕ Rejeter</button>
        <button class="btn btn-ok" onclick="approuverCand('${escJs(c.id)}')">✔ Approuver</button>
      ` : ''}
    </div>`, { narrow: true });
}

async function approuverCand(id) {
  if (!confirm("Approuver cette candidature ? Une fiche personnel sera automatiquement créée avec les matières et le cycle indiqués (modifiables ensuite librement).")) return;
  try { await apiApprouverCandidature(id); toast('Candidature approuvée ✅ — Personnel créé','success'); closeModal(); pageCandidatures(); }
  catch(e) { toast(e.message,'error'); }
}

async function rejeterCandPrompt(id) {
  const motif = prompt('Motif du rejet (optionnel) :', '');
  if (motif === null) return;
  try { await apiRejeterCandidature(id, { motif }); toast('Candidature rejetée','warning'); closeModal(); pageCandidatures(); }
  catch(e) { toast(e.message,'error'); }
}

async function delCandidature(id) {
  if (!confirmDel('Supprimer cette candidature ?')) return;
  try { await apiDeleteCandidature(id); toast('Supprimée','success'); pageCandidatures(); }
  catch(e) { toast(e.message,'error'); }
}

window.copierLienCandidature = copierLienCandidature;
window.voirCandidature = voirCandidature;
window.approuverCand = approuverCand;
window.rejeterCandPrompt = rejeterCandPrompt;
window.delCandidature = delCandidature;
