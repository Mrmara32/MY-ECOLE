/* ===================== EXAMENS & CONCOURS ===================== */
const EXAMEN_TYPES = { examen_national: 'Examen national', composition: 'Composition', examen_blanc: 'Examen blanc', concours_entree: "Concours d'entrée" };
const apiExamens = {
  liste: () => apiFetch('/examens'),
  creer: (b) => apiFetch('/examens', { method: 'POST', body: b }),
  suppr: (id) => apiFetch('/examens/' + encodeURIComponent(id), { method: 'DELETE' }),
  candidats: (id) => apiFetch('/examens/' + encodeURIComponent(id) + '/candidats'),
  inscrire: (id, b) => apiFetch('/examens/' + encodeURIComponent(id) + '/candidats', { method: 'POST', body: b }),
  retirer: (id, cid) => apiFetch('/examens/' + encodeURIComponent(id) + '/candidats/' + encodeURIComponent(cid), { method: 'DELETE' }),
  resultats: (id, r) => apiFetch('/examens/' + encodeURIComponent(id) + '/resultats', { method: 'PUT', body: { resultats: r } }),
  stats: (id) => apiFetch('/examens/' + encodeURIComponent(id) + '/statistiques'),
  cloturer: (id) => apiFetch('/examens/' + encodeURIComponent(id) + '/cloturer', { method: 'POST' }),
};

async function pageExamens() {
  $('#content').innerHTML = loadingHtml;
  const gere = ['admin', 'directeur', 'secretaire'].includes(currentUser?.role);
  let examens = [];
  const charger = async () => {
    try { examens = await apiExamens.liste(); } catch (e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
    $('#exa-body').innerHTML = examens.length ? examens.map(x => `<tr>
      <td><strong>${esc(x.nom)}</strong><div class="text-muted" style="font-size:11px">${esc(x.annee_scolaire || '')}${x.classe ? ' · ' + esc(x.classe) : ''}</div></td>
      <td>${EXAMEN_TYPES[x.type] || x.type}</td>
      <td>${fmtDate(x.date_debut)}${x.date_fin && x.date_fin !== x.date_debut ? ' → ' + fmtDate(x.date_fin) : ''}</td>
      <td>${x.nb_candidats}${x.nb_candidats ? ` <span class="text-muted">(${x.nb_admis} admis)</span>` : ''}</td>
      <td>${x.cloture ? '<span class="badge bdg-ok">Clôturé</span>' : '<span class="badge bdg-info">Ouvert</span>'}</td>
      <td><div class="td-actions"><button class="btn btn-primary btn-xs" onclick="ouvrirExamen('${escJs(x.id)}')">Ouvrir</button>
        ${gere && ['admin', 'directeur'].includes(currentUser.role) && !x.cloture ? `<button class="btn btn-outline btn-xs" onclick="supprimerExamen('${escJs(x.id)}')">🗑</button>` : ''}</div></td></tr>`).join('')
      : `<tr><td colspan="6">${emptyHtml('📝', 'Aucun examen ni concours')}</td></tr>`;
  };
  window._rechargerExamens = charger;
  $('#content').innerHTML = `<div class="card"><div class="card-header"><span class="card-title">📝 Examens & concours</span>
    ${gere ? '<button class="btn btn-primary btn-sm" onclick="modalExamen()">+ Nouvel examen</button>' : ''}</div>
    <div class="tbl-wrap"><table><thead><tr><th>Examen</th><th>Type</th><th>Date</th><th>Candidats</th><th>Statut</th><th></th></tr></thead><tbody id="exa-body"></tbody></table></div></div>`;
  charger();
}

function modalExamen() {
  openModal('Nouvel examen ou concours', `
    <form id="f-exa" style="display:flex;flex-direction:column;gap:12px">
      <div class="fg"><label>Nom*</label><input name="nom" required maxlength="150" placeholder="Ex. : BEPC 2026, Composition du 1er trimestre"></div>
      <div class="form-2">
        <div class="fg"><label>Type*</label><select name="type">${Object.entries(EXAMEN_TYPES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div>
        <div class="fg"><label>Classe concernée</label><input name="classe" placeholder="Ex. : 10ème"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Début*</label><input type="date" name="date_debut" value="${today()}" required></div>
        <div class="fg"><label>Fin</label><input type="date" name="date_fin"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Lieu</label><input name="lieu"></div>
        <div class="fg"><label>Moyenne minimale pour être admis (/20)</label><input type="number" name="seuil_admission" min="1" max="20" step="0.25" value="10"></div>
      </div>
      <div class="fg"><label>Nombre de places (concours d'entrée)</label><input type="number" name="places" min="1"></div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button><button class="btn btn-primary" type="submit">Créer</button></div>
    </form>`, { narrow: true });
  $('#f-exa').onsubmit = async e => {
    e.preventDefault();
    const b = Object.fromEntries(new FormData(e.target));
    try { await apiExamens.creer(b); toast('Examen créé', 'success'); closeModal(); window._rechargerExamens(); }
    catch (err) { toast(err.message, 'error'); }
  };
}
window.modalExamen = modalExamen;

async function supprimerExamen(id) {
  if (!confirmDel('Supprimer cet examen et tous ses candidats ?')) return;
  try { await apiExamens.suppr(id); toast('Supprimé', 'success'); window._rechargerExamens(); } catch (e) { toast(e.message, 'error'); }
}
window.supprimerExamen = supprimerExamen;

async function ouvrirExamen(id) {
  const gere = ['admin', 'directeur', 'secretaire'].includes(currentUser?.role);
  const direction = ['admin', 'directeur'].includes(currentUser?.role);
  const x = (await apiExamens.liste()).find(e => e.id === id);
  if (!x) return;
  const [cands, st] = await Promise.all([apiExamens.candidats(id), apiExamens.stats(id)]);
  const ouvert = !x.cloture && gere;
  const lib = { inscrit: '—', admis: '✅ Admis', ajourne: '❌ Ajourné', absent: 'Absent' };
  window._exaCands = cands;
  window._exaNom = x.nom;
  openModal(x.nom, `
    ${x.cloture ? '<div class="alert alert-info" style="margin-bottom:8px">🔒 Examen clôturé : résultats définitifs.</div>' : ''}
    <div class="stats-grid" style="margin-bottom:10px">
      ${[['Inscrits', st.inscrits], ['Présents', st.presents], ['Admis', st.admis], ['Réussite', st.taux_reussite == null ? '—' : st.taux_reussite + ' %'],
        ['Moyenne', st.moyenne_generale == null ? '—' : st.moyenne_generale]].map(([l, n]) => `<div class="stat"><div class="stat-val">${n}</div><div class="stat-label">${l}</div></div>`).join('')}
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
      ${ouvert ? `<button class="btn btn-outline btn-sm" onclick="modalInscrireExamen('${escJs(id)}')">+ Inscrire des candidats</button>
        <button class="btn btn-primary btn-sm" onclick="enregistrerResultatsExamen('${escJs(id)}')">💾 Enregistrer les résultats</button>` : ''}
      <button class="btn btn-outline btn-sm" onclick="imprimerExamen('${escJs(id)}','convocation')">🖨 Liste des candidats</button>
      <button class="btn btn-outline btn-sm" onclick="imprimerExamen('${escJs(id)}','resultats')">🖨 Procès-verbal des résultats</button>
      ${direction && !x.cloture ? `<button class="btn btn-outline btn-sm" onclick="cloturerExamen('${escJs(id)}')">🔒 Clôturer</button>` : ''}
    </div>
    <div class="tbl-wrap" style="max-height:50vh;overflow:auto"><table><thead><tr><th>N°</th><th>Candidat</th><th>Moyenne /20</th><th>Résultat</th><th></th></tr></thead><tbody>
    ${cands.length ? cands.map(c => `<tr><td>${esc(c.numero)}</td>
      <td>${esc(c.nom)} ${esc(c.prenom)}<div class="text-muted" style="font-size:11px">${c.eleve_id ? esc(c.classe || '') : 'Candidat externe'}</div></td>
      <td>${ouvert ? `<input type="number" min="0" max="20" step="0.01" data-cid="${esc(c.id)}" value="${c.moyenne ?? ''}" ${c.statut === 'absent' ? 'disabled' : ''} style="width:90px">
          <label style="font-size:11px"><input type="checkbox" data-abs="${esc(c.id)}" ${c.statut === 'absent' ? 'checked' : ''} onchange="this.closest('tr').querySelector('[data-cid]').disabled=this.checked"> absent</label>`
        : (c.moyenne ?? '—')}</td>
      <td>${lib[c.statut]}${c.mention && c.statut === 'admis' ? `<div class="text-muted" style="font-size:11px">${esc(c.mention)}</div>` : ''}</td>
      <td>${ouvert ? `<button class="btn btn-outline btn-xs" onclick="retirerCandidatExamen('${escJs(id)}','${escJs(c.id)}')">✕</button>` : ''}</td></tr>`).join('')
      : `<tr><td colspan="5">${emptyHtml('👥', 'Aucun candidat inscrit')}</td></tr>`}
    </tbody></table></div>`, { wide: true });
}
window.ouvrirExamen = ouvrirExamen;

async function enregistrerResultatsExamen(id) {
  const res = [];
  document.querySelectorAll('#modal-body [data-cid]').forEach(inp => {
    const cid = inp.dataset.cid, abs = document.querySelector(`#modal-body [data-abs="${cid}"]`)?.checked;
    res.push(abs ? { id: cid, absent: true } : { id: cid, moyenne: inp.value });
  });
  try { const r = await apiExamens.resultats(id, res); toast(`${r.enregistres} résultat(s) enregistré(s)`, 'success'); ouvrirExamen(id); window._rechargerExamens(); }
  catch (e) { toast(e.message, 'error'); }
}
window.enregistrerResultatsExamen = enregistrerResultatsExamen;

async function cloturerExamen(id) {
  if (!confirmDel('Clôturer définitivement cet examen ? Les résultats ne pourront plus être modifiés.')) return;
  try { await apiExamens.cloturer(id); toast('Examen clôturé', 'success'); ouvrirExamen(id); window._rechargerExamens(); } catch (e) { toast(e.message, 'error'); }
}
window.cloturerExamen = cloturerExamen;

async function retirerCandidatExamen(id, cid) {
  if (!confirmDel('Retirer ce candidat ?')) return;
  try { await apiExamens.retirer(id, cid); ouvrirExamen(id); window._rechargerExamens(); } catch (e) { toast(e.message, 'error'); }
}
window.retirerCandidatExamen = retirerCandidatExamen;

async function modalInscrireExamen(id) {
  let classes = [];
  try { classes = [...new Set((await apiGetEleves()).filter(e => e.statut === 'actif').map(e => e.classe).filter(Boolean))].sort(); } catch (_) {}
  openModal(window._exaNom || 'Examen', `
    <div style="font-weight:600;margin-bottom:8px">Inscrire des candidats</div>
    <form id="f-insc" style="display:flex;flex-direction:column;gap:12px">
      <div class="fg"><label>Toute une classe</label><select name="classe"><option value="">—</option>${classes.map(c => `<option>${esc(c)}</option>`).join('')}</select></div>
      <div style="text-align:center;color:#888">— ou candidat externe —</div>
      <div class="form-2"><div class="fg"><label>Nom</label><input name="nom"></div><div class="fg"><label>Prénom</label><input name="prenom"></div></div>
      <div class="form-2"><div class="fg"><label>Date de naissance</label><input type="date" name="date_naissance"></div><div class="fg"><label>Téléphone</label><input name="telephone"></div></div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="ouvrirExamen('${escJs(id)}')">Retour</button><button class="btn btn-primary" type="submit">Inscrire</button></div>
    </form>`, { narrow: true });
  $('#f-insc').onsubmit = async e => {
    e.preventDefault();
    const b = Object.fromEntries(new FormData(e.target)); Object.keys(b).forEach(k => { if (!b[k]) delete b[k]; });
    try { const r = await apiExamens.inscrire(id, b); toast(`${r.ajoutes} candidat(s) inscrit(s)`, 'success'); ouvrirExamen(id); window._rechargerExamens(); }
    catch (err) { toast(err.message, 'error'); }
  };
}
window.modalInscrireExamen = modalInscrireExamen;

async function imprimerExamen(id, mode) {
  const [x, cands, settings] = await Promise.all([apiExamens.liste().then(l => l.find(e => e.id === id)), apiExamens.candidats(id), apiGetSettings()]);
  const resultats = mode === 'resultats';
  const lib = { inscrit: '', admis: 'Admis', ajourne: 'Ajourné', absent: 'Absent' };
  const tri = resultats ? [...cands].sort((a, b) => (b.moyenne ?? -1) - (a.moyenne ?? -1)) : cands;
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>${resultats ? 'Procès-verbal' : 'Liste des candidats'} — ${esc(x.nom)}</title>
  <style>body{font-family:Arial,sans-serif;color:#111;padding:30px}.doc{max-width:800px;margin:0 auto}
  h1{font-size:20px;margin:0}h2{font-size:16px;margin:4px 0 16px;color:#1E3A8A}.hd{text-align:center;border-bottom:3px double #1E3A8A;padding-bottom:10px;margin-bottom:16px}
  table{width:100%;border-collapse:collapse;font-size:13px}th,td{border:1px solid #999;padding:6px 8px;text-align:left}th{background:#eef}
  .sig{margin-top:50px;text-align:right;font-size:13px}</style></head><body><div class="doc">
  <div class="hd"><h1>${esc(settings.ecole_nom || 'MY-ECOLE')}</h1></div>
  <h2>${resultats ? 'PROCÈS-VERBAL DES RÉSULTATS' : 'LISTE DES CANDIDATS'} — ${esc(x.nom)}</h2>
  <p style="font-size:13px">${EXAMEN_TYPES[x.type] || ''} · ${fmtDate(x.date_debut)}${x.date_fin ? ' au ' + fmtDate(x.date_fin) : ''}${x.lieu ? ' · ' + esc(x.lieu) : ''} · Admission à partir de ${x.seuil_admission}/20</p>
  <table><thead><tr><th>${resultats ? 'Rang' : 'N°'}</th>${resultats ? '<th>N°</th>' : ''}<th>Nom et prénom</th><th>${resultats ? 'Moyenne' : 'Classe / origine'}</th>${resultats ? '<th>Décision</th><th>Mention</th>' : '<th>Émargement</th>'}</tr></thead><tbody>
  ${tri.map((c, i) => `<tr><td>${resultats ? i + 1 : esc(c.numero)}</td>${resultats ? `<td>${esc(c.numero)}</td>` : ''}<td>${esc((c.nom || '').toUpperCase())} ${esc(c.prenom)}</td>
    <td>${resultats ? (c.moyenne ?? '—') : esc(c.eleve_id ? (c.classe || '') : 'Externe')}</td>
    ${resultats ? `<td>${lib[c.statut]}</td><td>${esc(c.statut === 'admis' ? (c.mention || '') : '')}</td>` : '<td style="width:140px"></td>'}</tr>`).join('')}
  </tbody></table><div class="sig">Le Directeur<br><br><br>Signature et cachet</div></div></body></html>`;
  const win = ouvrirDocumentImprimable(html);
  finaliserDocumentPartageable(win, '.doc', { filenameBase: `${resultats ? 'pv' : 'candidats'}_${x.nom}`.replace(/\s+/g, '_'), sujetEmail: x.nom, messageEmail: '', destinataireDefaut: '' });
}
window.imprimerExamen = imprimerExamen;
