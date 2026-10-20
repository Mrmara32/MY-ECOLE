/* ===================== BIBLIOTHÈQUE ===================== */
const apiBiblio = {
  livres: (q = '') => apiFetch('/bibliotheque/livres' + (q ? '?q=' + encodeURIComponent(q) : '')),
  creerLivre: (b) => apiFetch('/bibliotheque/livres', { method: 'POST', body: b }),
  majLivre: (id, b) => apiFetch('/bibliotheque/livres/' + encodeURIComponent(id), { method: 'PUT', body: b }),
  supprLivre: (id) => apiFetch('/bibliotheque/livres/' + encodeURIComponent(id), { method: 'DELETE' }),
  prets: (statut) => apiFetch('/bibliotheque/prets?statut=' + statut),
  preter: (b) => apiFetch('/bibliotheque/prets', { method: 'POST', body: b }),
  rendre: (id) => apiFetch('/bibliotheque/prets/' + encodeURIComponent(id) + '/retour', { method: 'POST' }),
  stats: () => apiFetch('/bibliotheque/stats'),
};

async function pageBibliotheque() {
  $('#content').innerHTML = loadingHtml;
  const gere = ['admin', 'directeur', 'secretaire'].includes(currentUser?.role);
  const etat = { onglet: 'livres', q: '', statut: 'en_cours', livres: [], prets: [] };

  const rendreStats = async () => {
    try {
      const s = await apiBiblio.stats();
      $('#bib-stats').innerHTML = [['📖 Titres', s.titres], ['📚 Exemplaires', s.exemplaires], ['🔄 Prêts en cours', s.prets_en_cours],
        ['⏰ En retard', s.en_retard]].map(([l, n]) => `<div class="stat"><div class="stat-val">${n}</div><div class="stat-label">${l}</div></div>`).join('');
    } catch (_) { /* statistiques facultatives */ }
  };
  const charger = async () => {
    try {
      if (etat.onglet === 'livres') etat.livres = await apiBiblio.livres(etat.q);
      else etat.prets = await apiBiblio.prets(etat.statut);
    } catch (e) { toast(e.message, 'error'); }
    afficher(); rendreStats();
  };
  window._rechargerBiblio = charger;
  window._biblioLivres = () => etat.livres;

  const afficher = () => {
    if (etat.onglet === 'livres') {
      $('#bib-corps').innerHTML = `<table><thead><tr><th>Titre</th><th>Auteur</th><th>Catégorie</th><th>Emplacement</th><th>Disponibles</th><th></th></tr></thead><tbody>` +
        (etat.livres.length ? etat.livres.map(l => `<tr>
          <td><strong>${esc(l.titre)}</strong>${l.isbn ? `<div class="text-muted" style="font-size:11px">ISBN ${esc(l.isbn)}</div>` : ''}</td>
          <td>${esc(l.auteur || '—')}</td><td>${esc(l.categorie || '—')}</td><td>${esc(l.emplacement || '—')}</td>
          <td><span class="badge ${l.disponibles ? 'bdg-ok' : 'bdg-err'}">${l.disponibles} / ${l.exemplaires}</span></td>
          <td>${gere ? `<div class="td-actions">
            <button class="btn btn-primary btn-xs" ${l.disponibles ? '' : 'disabled'} onclick="modalPret('${escJs(l.id)}')">Prêter</button>
            <button class="btn btn-outline btn-xs" onclick="modalLivre('${escJs(l.id)}')" title="Modifier">✏️</button>
            <button class="btn btn-outline btn-xs" onclick="supprimerLivre('${escJs(l.id)}')" title="Supprimer">🗑</button></div>` : ''}</td></tr>`).join('')
          : `<tr><td colspan="6">${emptyHtml('📚', 'Aucun livre au catalogue')}</td></tr>`) + `</tbody></table>`;
    } else {
      $('#bib-corps').innerHTML = `<table><thead><tr><th>Livre</th><th>Emprunteur</th><th>Prêté le</th><th>À rendre le</th><th>Statut</th><th></th></tr></thead><tbody>` +
        (etat.prets.length ? etat.prets.map(p => `<tr>
          <td><strong>${esc(p.titre)}</strong><div class="text-muted" style="font-size:11px">${esc(p.auteur || '')}</div></td>
          <td>${esc(p.emprunteur_nom)}<div class="text-muted" style="font-size:11px">${p.emprunteur_type === 'eleve' ? 'Élève' : 'Personnel'}</div></td>
          <td>${fmtDate(p.date_pret)}</td><td>${fmtDate(p.date_retour_prevue)}</td>
          <td>${p.date_retour ? `<span class="badge bdg-ok">Rendu le ${fmtDate(p.date_retour)}</span>${p.jours_retard ? `<div class="text-muted" style="font-size:11px">${p.jours_retard} j de retard</div>` : ''}`
              : p.en_retard ? `<span class="badge bdg-err">En retard (${p.jours_retard} j)</span>` : '<span class="badge bdg-info">En cours</span>'}</td>
          <td>${gere && !p.date_retour ? `<button class="btn btn-outline btn-xs" onclick="rendreLivre('${escJs(p.id)}')">↩ Retour</button>` : ''}</td></tr>`).join('')
          : `<tr><td colspan="6">${emptyHtml('🔄', 'Aucun prêt')}</td></tr>`) + `</tbody></table>`;
    }
  };

  $('#content').innerHTML = `
  <div id="bib-stats" class="stats-grid" style="margin-bottom:12px"></div>
  <div class="card">
    <div class="card-header">
      <span class="card-title">📚 Bibliothèque</span>
      ${gere ? '<button class="btn btn-primary btn-sm" onclick="modalLivre()">+ Ajouter un livre</button>' : ''}
    </div>
    <div class="filters">
      <div class="fg"><label>Affichage</label><select id="bib-onglet"><option value="livres">Catalogue</option><option value="prets">Prêts</option></select></div>
      <div class="fg" id="bib-f-q"><label>Recherche</label><input id="bib-q" placeholder="Titre, auteur, ISBN, catégorie…"></div>
      <div class="fg" id="bib-f-st" style="display:none"><label>Prêts</label><select id="bib-statut">
        <option value="en_cours">En cours</option><option value="retard">En retard</option><option value="rendu">Rendus</option><option value="tous">Tous</option></select></div>
    </div>
    <div class="tbl-wrap" id="bib-corps"></div>
  </div>`;
  $('#bib-onglet').onchange = e => {
    etat.onglet = e.target.value;
    $('#bib-f-q').style.display = etat.onglet === 'livres' ? '' : 'none';
    $('#bib-f-st').style.display = etat.onglet === 'prets' ? '' : 'none';
    charger();
  };
  $('#bib-statut').onchange = e => { etat.statut = e.target.value; charger(); };
  let minuteur;
  $('#bib-q').oninput = e => { clearTimeout(minuteur); minuteur = setTimeout(() => { etat.q = e.target.value.trim(); charger(); }, 300); };
  charger();
}

function modalLivre(id) {
  const l = id ? window._biblioLivres().find(x => x.id === id) : null;
  openModal(l ? 'Modifier le livre' : 'Ajouter un livre', `
    <form id="f-liv" style="display:flex;flex-direction:column;gap:12px">
      <div class="fg"><label>Titre*</label><input name="titre" required maxlength="200" value="${esc(l?.titre || '')}"></div>
      <div class="form-2">
        <div class="fg"><label>Auteur</label><input name="auteur" value="${esc(l?.auteur || '')}"></div>
        <div class="fg"><label>ISBN</label><input name="isbn" value="${esc(l?.isbn || '')}"></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Catégorie</label><input name="categorie" value="${esc(l?.categorie || '')}" placeholder="Roman, Sciences, Manuel…"></div>
        <div class="fg"><label>Emplacement</label><input name="emplacement" value="${esc(l?.emplacement || '')}" placeholder="Étagère B3"></div>
      </div>
      <div class="fg"><label>Nombre d'exemplaires*</label><input type="number" name="exemplaires" min="0" max="10000" required value="${l ? l.exemplaires : 1}"></div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button class="btn btn-primary" type="submit">Enregistrer</button></div>
    </form>`, { narrow: true });
  $('#f-liv').onsubmit = async e => {
    e.preventDefault();
    const b = Object.fromEntries(new FormData(e.target)); b.exemplaires = parseInt(b.exemplaires, 10);
    try { l ? await apiBiblio.majLivre(l.id, b) : await apiBiblio.creerLivre(b); toast('Enregistré', 'success'); closeModal(); window._rechargerBiblio(); }
    catch (err) { toast(err.message, 'error'); }
  };
}
window.modalLivre = modalLivre;

async function modalPret(livreId) {
  const l = window._biblioLivres().find(x => x.id === livreId);
  let eleves = [], personnel = [];
  try { eleves = (await apiGetEleves()).filter(e => e.statut === 'actif'); } catch (_) {}
  try { personnel = await apiFetch('/personnel'); } catch (_) {}
  const opts = (type) => (type === 'eleve' ? eleves.map(e => `<option value="${esc(e.id)}">${esc(e.nom)} ${esc(e.prenom)} — ${esc(e.classe || '')}</option>`)
    : (personnel || []).map(p => `<option value="${esc(p.id)}">${esc(p.nom)} ${esc(p.prenom)}</option>`)).join('');
  openModal('Prêter « ' + (l?.titre || '') + ' »', `
    <form id="f-pret" style="display:flex;flex-direction:column;gap:12px">
      <div class="fg"><label>Emprunteur</label><select id="pret-type" name="emprunteur_type"><option value="eleve">Élève</option><option value="personnel">Personnel</option></select></div>
      <div class="fg"><label>Nom*</label><select name="emprunteur_id" id="pret-emp" required></select></div>
      <div class="fg"><label>Durée du prêt (jours)</label><input type="number" name="jours" min="1" max="120" value="14"></div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button class="btn btn-primary" type="submit">Enregistrer le prêt</button></div>
    </form>`, { narrow: true });
  const maj = () => { $('#pret-emp').innerHTML = '<option value="">— Choisir —</option>' + opts($('#pret-type').value); };
  $('#pret-type').onchange = maj; maj();
  $('#f-pret').onsubmit = async e => {
    e.preventDefault();
    const b = Object.fromEntries(new FormData(e.target)); b.livre_id = livreId; b.jours = parseInt(b.jours, 10);
    try { await apiBiblio.preter(b); toast('Prêt enregistré', 'success'); closeModal(); window._rechargerBiblio(); }
    catch (err) { toast(err.message, 'error'); }
  };
}
window.modalPret = modalPret;

async function rendreLivre(id) {
  try { await apiBiblio.rendre(id); toast('Retour enregistré', 'success'); window._rechargerBiblio(); }
  catch (e) { toast(e.message, 'error'); }
}
window.rendreLivre = rendreLivre;

async function supprimerLivre(id) {
  if (!confirmDel('Supprimer ce livre du catalogue ?')) return;
  try { await apiBiblio.supprLivre(id); toast('Supprimé', 'success'); window._rechargerBiblio(); }
  catch (e) { toast(e.message, 'error'); }
}
window.supprimerLivre = supprimerLivre;
