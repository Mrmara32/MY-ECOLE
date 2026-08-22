/* ===================== COURS DE RÉVISION ===================== */
async function pageRevision() {
  $('#content').innerHTML = loadingHtml;
  try {
    if (!_sallesCache.length) await refreshSalles();
    const cours = await apiGetCoursRevision();
    const estEnseignant = currentUser.role === 'enseignant';

    const render = data => {
      $('#tb-revision').innerHTML = data.length ? data.map(c => {
        if (estEnseignant) {
          // Vue restreinte enseignant : titre, matière, date, nombre d'élèves, niveau, statut, enseignants
          return `<tr>
          <td><strong>${esc(c.titre)}</strong></td>
          <td><span class="badge bdg-primary">${esc(c.matiere||'—')}</span></td>
          <td>${esc(c.niveau||'—')}</td>
          <td>${fmtDate(c.date_debut)} ${c.date_fin?'→ '+fmtDate(c.date_fin):''}</td>
          <td class="text-center">${c.nb_participants||0}${c.capacite_max?` / ${c.capacite_max}`:''}</td>
          <td><span class="badge ${c.statut==='actif'?'bdg-ok':c.statut==='termine'?'bdg-gray':'bdg-err'}">${esc(c.statut)}</span></td>
          <td style="font-size:12px">${esc(c.noms_enseignants||'—')}</td>
          <td><button class="btn btn-primary btn-xs" onclick="ouvrirCours('${escJs(c.id)}')">👁 Voir</button></td>
        </tr>`;
        }
        return `<tr>
        <td><strong>${esc(c.titre)}</strong>${c.description?`<br><span class="text-muted" style="font-size:11px">${esc(c.description.substring(0,70))}${c.description.length>70?'…':''}</span>`:''}</td>
        <td><span class="badge bdg-primary">${esc(c.matiere||'—')}</span></td>
        <td>${esc(c.niveau||'—')}</td>
        <td>${fmtDate(c.date_debut)} ${c.date_fin?'→ '+fmtDate(c.date_fin):''}</td>
        <td class="mono text-right fw-600">${fmtMoney(c.prix)}</td>
        <td class="text-center">${c.nb_participants||0}${c.capacite_max?` / ${c.capacite_max}`:''}</td>
        <td class="mono text-right text-ok">${fmtMoney(c.total_paye||0)}</td>
        <td><span class="badge ${c.statut==='actif'?'bdg-ok':c.statut==='termine'?'bdg-gray':'bdg-err'}">${esc(c.statut)}</span></td>
        <td><div class="td-actions">
          <button class="btn btn-primary btn-xs" onclick="ouvrirCours('${escJs(c.id)}')">👁 Gérer</button>
          <button class="btn btn-danger btn-xs" onclick="delCoursRevision('${escJs(c.id)}')">🗑</button>
        </div></td>
      </tr>`;
      }).join('') : `<tr><td colspan="9">${emptyHtml('📖','Aucun cours de révision programmé')}</td></tr>`;
    };

    const theadHtml = estEnseignant
      ? `<tr id="th-revision"><th>Titre</th><th>Matière</th><th>Niveau</th><th>Date</th><th>Nb élèves</th><th>Statut</th><th>Enseignants</th><th>Actions</th></tr>`
      : `<tr id="th-revision"><th>Titre</th><th>Matière</th><th>Niveau</th><th>Dates</th><th class="text-right">Prix</th><th>Participants</th><th class="text-right">Perçu</th><th>Statut</th><th>Actions</th></tr>`;

    $('#content').innerHTML = `
    <div class="alert alert-info mb-4">
      💡 Les cours de révision sont <strong>payants</strong> et ouverts aux élèves d'autres écoles.
      Chaque participant doit obligatoirement recevoir une <strong>évaluation</strong> à l'issue du cours.
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">📖 Cours de révision (${cours.length})</span>
        ${!estEnseignant ? `<div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="modalRedistribution()">💰 Redistribution mensuelle</button>
          <button class="btn btn-primary btn-sm" onclick="modalCoursRevision()">+ Programmer un cours</button>
        </div>` : ''}
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-rev" placeholder="Titre, matière, niveau…"></div>
        <div class="fg"><label>Statut</label><select id="f-revstat">
          <option value="">Tous</option><option value="actif">Actif</option>
          <option value="termine">Terminé</option><option value="annule">Annulé</option>
        </select></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead>${theadHtml}</thead>
        <tbody id="tb-revision"></tbody>
      </table></div>
    </div>`;

    let curr = cours;
    render(curr);
    const filter = () => {
      const q = $('#q-rev').value.toLowerCase();
      const stat = $('#f-revstat').value;
      curr = cours.filter(c => {
        const txt = `${c.titre} ${c.matiere||''} ${c.niveau||''}`.toLowerCase();
        return (!q || txt.includes(q)) && (!stat || c.statut === stat);
      });
      render(curr);
    };
    $('#q-rev').addEventListener('input', filter);
    $('#f-revstat').addEventListener('change', filter);

    makeSortableTable('#th-revision', () => curr, render,
      estEnseignant
        ? ['titre', 'matiere', 'niveau', 'date_debut', 'nb_participants', 'statut', 'noms_enseignants', null]
        : ['titre', 'matiere', 'niveau', 'date_debut', 'prix', 'nb_participants', 'total_paye', 'statut', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function modalCoursRevision(id = null, data = {}) {
  const salles = _sallesCache.length ? _sallesCache.filter(s=>s.active) : [];
  openModal(id ? 'Modifier le cours de révision' : 'Programmer un cours de révision', `
    <div class="alert alert-info" style="font-size:12px">💡 Un cours de révision se programme par <strong>niveau</strong> (ex : 10ème Année, 9ème, 6ème…). Les élèves de ce niveau ne paient qu'<strong>un seul forfait mensuel</strong>, quel que soit le nombre d'enseignants qui interviennent (généralement 3 à 4), chacun selon son jour et son horaire disponible.</div>
    <form id="f-rev" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Titre*</label><input name="titre" value="${esc(data.titre||'')}" required placeholder="Ex : Révisions Brevet - Mathématiques"></div>
      <div class="form-3">
        <div class="fg"><label>Matière</label><select name="matiere">${optionsHtml(MATIERES, data.matiere||'')}</select></div>
        <div class="fg"><label>Niveau ciblé</label>
          <input name="niveau" value="${esc(data.niveau||'')}" list="niveaux-suggestions" placeholder="Ex : 10ème Année, 9ème, 6ème…">
          <datalist id="niveaux-suggestions">
            ${['10ème Année','9ème','8ème','7ème','6ème','5ème','4ème','3ème','2nde','1ère','Terminale'].map(n=>`<option value="${n}">`).join('')}
          </datalist>
        </div>
        <div class="fg"><label>Prix mensuel par élève (GNF)*</label><input type="number" name="prix" value="${data.prix??''}" min="0" step="1" required placeholder="60000"></div>
      </div>
      <div class="form-3">
        <div class="fg"><label>Date de début</label><input type="date" name="date_debut" value="${esc(data.date_debut||today())}"></div>
        <div class="fg"><label>Date de fin</label><input type="date" name="date_fin" value="${esc(data.date_fin||'')}"></div>
        <div class="fg"><label>Places maximum</label><input type="number" name="capacite_max" value="${data.capacite_max??''}" min="1" placeholder="Illimité si vide"></div>
      </div>
      <div class="form-3">
        <div class="fg"><label>Salle</label><select name="salle">
          <option value="">— Aucune —</option>
          ${salles.map(s=>`<option value="${esc(s.nom)}" ${data.salle===s.nom?'selected':''}>${esc(s.nom)}</option>`).join('')}
        </select></div>
        <div class="fg"><label>Durée d'une séance</label><select name="duree_seance">
          ${[0.5,1,1.5,2,2.5,3,4].map(h=>`<option value="${h}" ${(data.duree_seance||1)==h?'selected':''}>${h}h</option>`).join('')}
        </select></div>
        ${id ? `<div class="fg"><label>Statut</label><select name="statut">
          <option value="actif" ${data.statut==='actif'?'selected':''}>Actif</option>
          <option value="termine" ${data.statut==='termine'?'selected':''}>Terminé</option>
          <option value="annule" ${data.statut==='annule'?'selected':''}>Annulé</option>
        </select></div>` : '<div></div>'}
      </div>
      <div class="fg"><label>Description</label><textarea name="description" rows="3">${esc(data.description||'')}</textarea></div>
      ${id ? motifFieldHtml() : ''}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Programmer'}</button>
      </div>
    </form>`, { narrow: true });
  $('#f-rev').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.prix = parseFloat(fd.prix) || 0;
    fd.duree_seance = parseFloat(fd.duree_seance) || 1;
    if (fd.capacite_max) fd.capacite_max = parseInt(fd.capacite_max); else delete fd.capacite_max;
    try {
      if (id) await apiUpdateCoursRevision(id, fd); else await apiCreateCoursRevision(fd);
      toast(id?'Modifié':'Cours programmé','success'); closeModal(); pageRevision();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delCoursRevision(id) {
  if (!confirmDel("Supprimer ce cours de révision et tous ses participants ?")) return;
  try { await apiDeleteCoursRevision(id); toast('Supprimé','success'); pageRevision(); }
  catch(e) { toast(e.message,'error'); }
}

/* ── Gestion d'un cours : participants (internes + externes) + paiement + évaluation ── */
let _revCoursActuel = null;
let _revParticipantsCache = [];

async function ouvrirCours(coursId) {
  const [cours, participants, eleves] = await Promise.all([
    apiGetCoursRevisionOne(coursId), apiGetRevisionParticipants(coursId), apiGetEleves('statut=actif')
  ]);
  _revCoursActuel = cours;
  _revParticipantsCache = participants;
  window._revEleves = eleves;
  const estEnseignant = currentUser.role === 'enseignant';

  const render = data => {
    $('#tb-rev-part').innerHTML = data.length ? data.map(p => {
      const reste = (cours.prix||0) - p.montant_paye;
      const SCOLOR = { paye:'bdg-ok', partiel:'bdg-warn', impaye:'bdg-err' };
      return `<tr>
        <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong></td>
        <td>${p.est_externe ? `<span class="badge bdg-warn">🏫 Externe</span><br><span class="text-muted" style="font-size:11px">${esc(p.ecole_origine||'')}</span>` : '<span class="badge bdg-primary">Interne</span>'}</td>
        <td>${esc(p.telephone||'—')}</td>
        ${!estEnseignant ? `<td><span class="badge ${SCOLOR[p.statut_paiement]||'bdg-gray'}">${p.statut_paiement==='paye'?'Payé':p.statut_paiement==='partiel'?'Partiel':'Impayé'}</span><br>
          <span class="text-muted" style="font-size:11px">${fmtMoney(p.montant_paye)} / ${fmtMoney(cours.prix||0)}</span></td>` : ''}
        <td class="text-center">
          ${p.nb_evaluations>0 ? `<span class="badge bdg-ok">✔ Évalué (${p.nb_evaluations})</span>` : '<span class="badge bdg-err">⚠ Non évalué</span>'}
        </td>
        <td><div class="td-actions">
          ${!estEnseignant && ['admin','comptable'].includes(currentUser.role)?`<button class="btn btn-ok btn-xs" onclick="modalPayerRevision('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}',${reste})">💰 Payer</button>`:''}
          <button class="btn btn-outline btn-xs" onclick="modalEvaluerRevision('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}')">📝 Évaluer</button>
          ${!estEnseignant ? `<button class="btn btn-danger btn-xs" onclick="delRevisionParticipant('${escJs(p.id)}','${escJs(coursId)}')">🗑</button>` : ''}
        </div></td>
      </tr>`;
    }).join('') : `<tr><td colspan="${estEnseignant?5:6}">${emptyHtml('👥','Aucun participant inscrit')}</td></tr>`;
  };

  const nbNonEvalues = participants.filter(p => !p.nb_evaluations).length;
  const enseignantsCours = cours.enseignants || [];
  const seances = estEnseignant ? [] : await apiGetSeances(coursId);
  const totalHeures = seances.reduce((s,x) => s + x.duree_heures, 0);

  openModal(`📖 ${cours.titre}`, `
    <div class="stats-grid" style="grid-template-columns:repeat(${estEnseignant?2:4},1fr)">
      ${!estEnseignant ? `
      <div class="stat"><div class="stat-label">Prix / séance ${cours.duree_seance}h</div><div class="stat-val" style="font-size:16px">${fmtMoney(cours.prix)}</div></div>
      ` : ''}
      <div class="stat"><div class="stat-label">Participants</div><div class="stat-val">${cours.nb_participants||0}${cours.capacite_max?` / ${cours.capacite_max}`:''}</div></div>
      ${!estEnseignant ? `<div class="stat"><div class="stat-label">Total perçu</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(cours.total_paye||0)}</div></div>` : ''}
      <div class="stat"><div class="stat-label">Non évalués</div><div class="stat-val ${nbNonEvalues>0?'text-err':'text-ok'}">${nbNonEvalues}</div></div>
    </div>
    ${cours.salle ? `<div class="text-muted mb-2" style="font-size:12px">🏫 Salle : <strong>${esc(cours.salle)}</strong></div>` : ''}
    ${nbNonEvalues>0?`<div class="alert alert-warn">⚠️ <strong>${nbNonEvalues}</strong> participant(s) n'ont pas encore été évalué(s). Chaque participant doit obligatoirement recevoir une évaluation.</div>`:''}

    <div class="tabs" id="cours-tabs">
      <div class="tab active" onclick="switchCoursTab('participants')">👥 Participants</div>
      ${!estEnseignant ? `
      <div class="tab" onclick="switchCoursTab('enseignants')">👨‍🏫 Enseignants (${enseignantsCours.length})</div>
      <div class="tab" onclick="switchCoursTab('seances')">🕐 Séances (${totalHeures}h)</div>
      ` : ''}
    </div>

    <div class="tab-pane active" id="ct-participants">
      <div class="flex justify-between items-center mb-3">
        <span class="fw-600">Participants</span>
        <button class="btn btn-primary btn-sm" onclick="modalAjouterParticipant('${escJs(coursId)}')">+ Inscrire un participant</button>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Participant</th><th>Origine</th><th>Téléphone</th>${!estEnseignant?'<th>Paiement</th>':''}<th>Évaluation</th><th>Actions</th></tr></thead>
        <tbody id="tb-rev-part"></tbody>
      </table></div>
    </div>
    ${estEnseignant && enseignantsCours.length ? `
    <div class="text-muted mt-3" style="font-size:12px">👨‍🏫 Enseignants assignés : ${enseignantsCours.map(e=>`${esc(e.prenom)} ${esc(e.nom)}`).join(', ')}</div>
    ` : ''}

    ${!estEnseignant ? `
    <div class="tab-pane" id="ct-enseignants">
      <div class="flex justify-between items-center mb-3">
        <span class="fw-600">Enseignants assignés à ce cours</span>
        <button class="btn btn-primary btn-sm" onclick="modalAssignerEnseignant('${escJs(coursId)}')">+ Assigner un enseignant</button>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Enseignant</th><th>Matière</th><th>Jour / Créneau</th><th>Téléphone</th><th>Actions</th></tr></thead>
        <tbody>
          ${enseignantsCours.length ? enseignantsCours.map(e => `<tr>
            <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong></td>
            <td><span class="badge bdg-primary">${esc(e.matiere||cours.matiere||'—')}</span></td>
            <td style="font-size:12px">${e.jour?esc(e.jour):'—'}${e.creneau?' · '+esc(e.creneau):''}</td>
            <td>${esc(e.telephone||'—')}</td>
            <td><button class="btn btn-danger btn-xs" onclick="retirerEnseignantCours('${escJs(e.id)}','${escJs(coursId)}')">🗑</button></td>
          </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('👨‍🏫','Aucun enseignant assigné')}</td></tr>`}
        </tbody>
      </table></div>
    </div>

    <div class="tab-pane" id="ct-seances">
      <div class="flex justify-between items-center mb-3">
        <span class="fw-600">Séances enseignées (durée standard : ${cours.duree_seance}h)</span>
        <button class="btn btn-primary btn-sm" onclick="modalEnregistrerSeance('${escJs(coursId)}')">+ Enregistrer une séance</button>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Date</th><th>Enseignant</th><th class="text-right">Durée</th><th>Redistribué</th><th>Actions</th></tr></thead>
        <tbody>
          ${seances.length ? seances.map(s => `<tr>
            <td>${fmtDate(s.date_seance)}</td>
            <td>${esc(s.prenom)} ${esc(s.nom)}</td>
            <td class="text-right mono">${s.duree_heures}h</td>
            <td><span class="badge ${s.redistribue?'bdg-ok':'bdg-gray'}">${s.redistribue?'✔ Oui':'Non'}</span></td>
            <td><button class="btn btn-danger btn-xs" onclick="delSeanceRevision('${escJs(s.id)}','${escJs(coursId)}')">🗑</button></td>
          </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('🕐','Aucune séance enregistrée')}</td></tr>`}
        </tbody>
      </table></div>
      <div class="text-muted mt-2" style="font-size:12px">💡 Les heures saisies ici servent au calcul de la redistribution mensuelle de 60% aux enseignants (page Comptabilité → Redistribution).</div>
    </div>
    ` : ''}

    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
  `, { wide: true });
  render(participants);

  window.switchCoursTab = (tab) => {
    const idx = ['participants','enseignants','seances'].indexOf(tab);
    $$('#cours-tabs .tab').forEach((t,i) => t.classList.toggle('active', i===idx));
    $$('.tab-pane').forEach(p => p.classList.remove('active'));
    $(`#ct-${tab}`)?.classList.add('active');
  };
}

async function modalAssignerEnseignant(coursId) {
  const personnel = await apiGetPersonnel();
  openModal("Assigner un enseignant", `
    <form id="f-assign-ens" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Enseignant*</label>
        <select name="personnel_id" required>
          <option value="">— Choisir —</option>
          ${personnel.map(p=>`<option value="${esc(p.id)}">${esc(p.prenom)} ${esc(p.nom)} — ${esc(p.poste||'?')}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Matière enseignée dans ce cours</label><select name="matiere">${optionsHtml(MATIERES)}</select></div>
      <div class="alert alert-info" style="font-size:12px">💡 Pour un cours de niveau (ex : 10ème Année), plusieurs enseignants (3 ou 4) peuvent intervenir, chacun selon son jour et son horaire disponible.</div>
      <div class="form-2">
        <div class="fg"><label>Jour</label><select name="jour">
          <option value="">— Non précisé —</option>
          ${JOURS.map(j=>`<option>${esc(j)}</option>`).join('')}
        </select></div>
        <div class="fg"><label>Créneau horaire</label><select name="creneau">
          <option value="">— Non précisé —</option>
          ${CRENEAUX.map(c=>`<option>${esc(c)}</option>`).join('')}
        </select></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="ouvrirCours('${escJs(coursId)}')">Annuler</button>
        <button type="submit" class="btn btn-primary">Assigner</button>
      </div>
    </form>`, { narrow: true });
  $('#f-assign-ens').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { await apiAssignerEnseignant(coursId, fd); toast('Enseignant assigné','success'); ouvrirCours(coursId); pageRevision(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function retirerEnseignantCours(ceId, coursId) {
  if (!confirmDel('Retirer cet enseignant du cours ?')) return;
  try { await apiRetirerEnseignant(ceId); toast('Retiré','success'); ouvrirCours(coursId); }
  catch(e) { toast(e.message,'error'); }
}

async function modalEnregistrerSeance(coursId) {
  const enseignants = await apiGetEnseignantsCours(coursId);
  const cours = await apiGetCoursRevisionOne(coursId);
  openModal("Enregistrer une séance enseignée", `
    <form id="f-seance" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Enseignant*</label>
        <select name="personnel_id" required>
          <option value="">— Choisir —</option>
          ${enseignants.map(e=>`<option value="${esc(e.personnel_id)}">${esc(e.prenom)} ${esc(e.nom)}</option>`).join('')}
        </select>
        ${!enseignants.length ? `<div class="text-muted mt-1" style="font-size:12px">⚠️ Assignez d'abord un enseignant à ce cours (onglet Enseignants).</div>` : ''}
      </div>
      <div class="form-2">
        <div class="fg"><label>Date de la séance*</label><input type="date" name="date_seance" value="${today()}" required></div>
        <div class="fg"><label>Durée (heures)*</label><input type="number" name="duree_heures" value="${cours.duree_seance||1}" min="0.5" step="0.5" required></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="ouvrirCours('${escJs(coursId)}')">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-seance').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.duree_heures = parseFloat(fd.duree_heures);
    try { await apiEnregistrerSeance(coursId, fd); toast('Séance enregistrée','success'); ouvrirCours(coursId); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function delSeanceRevision(sId, coursId) {
  if (!confirmDel()) return;
  try { await apiDeleteSeance(sId); toast('Supprimée','success'); ouvrirCours(coursId); }
  catch(e) { toast(e.message,'error'); }
}

function modalAjouterParticipant(coursId) {
  const eleves = window._revEleves || [];
  openModal("Inscrire un participant", `
    <div class="tabs" id="part-tabs">
      <div class="tab active" onclick="switchPartTab('interne')">🎓 Élève de notre école</div>
      <div class="tab" onclick="switchPartTab('externe')">🏫 Élève d'une autre école</div>
    </div>
    <form id="f-part" style="display:flex;flex-direction:column;gap:14px">
      <div class="tab-pane active" id="part-interne">
        <div class="fg"><label>Élève*</label>
          <select id="part-eleve-sel">
            <option value="">— Choisir un élève —</option>
            ${eleves.map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="tab-pane" id="part-externe">
        <div class="form-2">
          <div class="fg"><label>Prénom*</label><input id="part-prenom"></div>
          <div class="fg"><label>Nom*</label><input id="part-nom"></div>
        </div>
        <div class="fg"><label>École d'origine*</label><input id="part-ecole" placeholder="Nom de l'école fréquentée"></div>
      </div>
      <div class="fg"><label>Téléphone</label><input id="part-telephone" placeholder="Contact du participant ou d'un parent"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="ouvrirCours('${escJs(coursId)}')">Annuler</button>
        <button type="submit" class="btn btn-primary">Inscrire</button>
      </div>
    </form>`, { narrow: true });

  window.switchPartTab = (tab) => {
    $$('#part-tabs .tab').forEach((t,i) => t.classList.toggle('active', i===(tab==='interne'?0:1)));
    $('#part-interne').classList.toggle('active', tab==='interne');
    $('#part-externe').classList.toggle('active', tab==='externe');
  };

  $('#f-part').onsubmit = async e => {
    e.preventDefault();
    const externeActive = $('#part-externe').classList.contains('active');
    const body = { telephone: $('#part-telephone').value };
    if (externeActive) {
      body.nom = $('#part-nom').value;
      body.prenom = $('#part-prenom').value;
      body.ecole_origine = $('#part-ecole').value;
      if (!body.nom || !body.prenom || !body.ecole_origine) { toast('Nom, prénom et école requis','error'); return; }
    } else {
      body.eleve_id = $('#part-eleve-sel').value;
      if (!body.eleve_id) { toast('Veuillez choisir un élève','error'); return; }
    }
    try {
      await apiAddRevisionParticipant(coursId, body);
      toast('Participant inscrit','success');
      ouvrirCours(coursId);
      pageRevision();
    } catch(err) { toast(err.message,'error'); }
  };
}

function modalPayerRevision(participantId, nom, reste) {
  const montantSuggere = reste > 0.01 ? reste : (_revCoursActuel.prix || '');
  openModal(`💰 Paiement — ${nom}`, `
    <form id="f-revpay" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">${reste>0.01?`Reste dû sur le mois en cours : <strong>${fmtMoney(reste)}</strong>`:`Forfait mensuel : <strong>${fmtMoney(_revCoursActuel.prix||0)}</strong> — ce paiement correspond à un nouveau mois de cours.`}</div>
      <div class="fg"><label>Montant versé (GNF)*</label><input type="number" name="montant" required min="1" step="1" value="${montantSuggere}"></div>
      <div class="text-muted" style="font-size:11.5px">Le cours de révision est un forfait mensuel récurrent : vous pouvez enregistrer n'importe quel montant, y compris pour un nouveau mois une fois le mois précédent déjà réglé.</div>
      <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
      <div class="fg"><label>Référence</label><input name="reference" placeholder="N° reçu…"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="ouvrirCours('${escJs(_revCoursActuel.id)}')">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer le paiement</button>
      </div>
    </form>`, { narrow: true });
  $('#f-revpay').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant);

    // Si le mois en cours est déjà réglé, ce paiement correspond à un mois
    // supplémentaire (2ème, 3ème…) — on demande confirmation avant d'enregistrer,
    // pour éviter tout doublon accidentel.
    if (reste <= 0.01 && _revCoursActuel.prix > 0) {
      const montantDejaPaye = _revCoursActuel.prix - reste;
      const numeroMois = Math.floor(montantDejaPaye / _revCoursActuel.prix) + 1;
      const ordinal = { 2: 'un 2ème', 3: 'un 3ème', 4: 'un 4ème' }[numeroMois] || `un ${numeroMois}ème`;
      if (!confirm(`${nom} a déjà réglé le(s) mois précédent(s) de ce cours de révision.\n\nVoulez-vous enregistrer ceci comme ${ordinal} paiement (nouveau mois) ?`)) {
        return;
      }
    }

    try {
      await apiPayerRevisionParticipant(participantId, fd);
      toast('Paiement enregistré ✅','success');
      ouvrirCours(_revCoursActuel.id);
      pageRevision();
      imprimerRecu({
        type: 'entree', nom, description: `Cours de révision`, montant: fd.montant,
        date: today(), moyenPaiement: fd.moyen_paiement, reference: fd.reference, recuPar: currentUser?.full_name,
      });
    } catch(err) { toast(err.message,'error'); }
  };
}

async function modalEvaluerRevision(participantId, nom) {
  const evaluations = await apiGetRevisionEvaluations(participantId);
  openModal(`📝 Évaluation — ${nom}`, `
    <form id="f-reveval" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Date*</label><input type="date" name="date_evaluation" value="${today()}" required></div>
        <div class="fg"><label>Note (/20)*</label><input type="number" name="note" min="0" max="20" step="0.25" required></div>
      </div>
      <div class="fg"><label>Appréciation</label><textarea name="appreciation" rows="3" placeholder="Commentaire sur la performance du participant…"></textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="ouvrirCours('${escJs(_revCoursActuel.id)}')">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer l'évaluation</button>
      </div>
    </form>
    <div class="sep"></div>
    <div class="form-section-title">Évaluations précédentes</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Date</th><th>Note</th><th>Appréciation</th><th>Par</th><th></th></tr></thead>
      <tbody>
        ${evaluations.length ? evaluations.map(ev => `<tr>
          <td>${fmtDate(ev.date_evaluation)}</td>
          <td>${noteBadge(ev.note)}</td>
          <td style="font-size:12px">${esc(ev.appreciation||'—')}</td>
          <td class="text-muted" style="font-size:11px">${esc(ev.evaluateur_nom||'—')}</td>
          <td><button class="btn btn-danger btn-xs" onclick="delRevisionEvaluation('${escJs(ev.id)}','${escJs(participantId)}','${escJs(nom)}')">🗑</button></td>
        </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('📝','Aucune évaluation enregistrée')}</td></tr>`}
      </tbody>
    </table></div>
  `, { wide: true });
  $('#f-reveval').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.note = parseFloat(fd.note);
    try {
      await apiCreateRevisionEvaluation(participantId, fd);
      toast('Évaluation enregistrée ✅','success');
      modalEvaluerRevision(participantId, nom);
      ouvrirCours(_revCoursActuel.id);
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delRevisionEvaluation(evalId, participantId, nom) {
  if (!confirmDel()) return;
  try { await apiDeleteRevisionEvaluation(evalId); toast('Supprimée','success'); modalEvaluerRevision(participantId, nom); }
  catch(e) { toast(e.message,'error'); }
}

async function delRevisionParticipant(participantId, coursId) {
  if (!confirmDel('Retirer ce participant du cours ?')) return;
  try { await apiDeleteRevisionParticipant(participantId); toast('Retiré','success'); ouvrirCours(coursId); pageRevision(); }
  catch(e) { toast(e.message,'error'); }
}

window.modalCoursRevision = modalCoursRevision;
window.delCoursRevision = delCoursRevision;
window.ouvrirCours = ouvrirCours;
window.modalAjouterParticipant = modalAjouterParticipant;
window.modalPayerRevision = modalPayerRevision;
window.modalEvaluerRevision = modalEvaluerRevision;
window.delRevisionEvaluation = delRevisionEvaluation;
window.delRevisionParticipant = delRevisionParticipant;
async function modalRedistribution(mois = null) {
  mois = mois || moisCourant();
  const data = await apiCalculRedistribution(mois);
  openModal(`💰 Redistribution mensuelle — ${mois}`, `
    <div class="fg mb-3"><label>Mois</label><input type="month" id="redist-mois" value="${mois}" onchange="modalRedistribution(this.value)"></div>
    <div class="stats-grid" style="grid-template-columns:repeat(3,1fr)">
      <div class="stat"><div class="stat-label">Recettes cours de révision</div><div class="stat-val" style="font-size:16px">${fmtMoney(data.total_recettes)}</div></div>
      <div class="stat"><div class="stat-label">Pool à redistribuer (60%)</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(data.pool_60pct)}</div></div>
      <div class="stat"><div class="stat-label">Total heures enseignées</div><div class="stat-val">${data.total_heures}h</div></div>
    </div>
    <div class="alert alert-info">💡 Le pool de 60% est réparti entre les enseignants au prorata des heures de séances qu'ils ont assurées ce mois-ci.</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Enseignant</th><th class="text-right">Heures</th><th class="text-right">Part (60%)</th><th class="text-right">Déjà versé</th><th class="text-right">À verser</th><th>Actions</th></tr></thead>
      <tbody>
        ${data.enseignants.length ? data.enseignants.map(e => `<tr>
          <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong></td>
          <td class="text-right mono">${e.total_heures}h</td>
          <td class="text-right mono">${fmtMoney(e.part)}</td>
          <td class="text-right mono text-muted">${fmtMoney(e.part - e.montant_a_verser)}</td>
          <td class="text-right mono fw-600 ${e.montant_a_verser>0?'text-ok':''}">${fmtMoney(e.montant_a_verser)}</td>
          <td>${e.montant_a_verser>0 ? `<button class="btn btn-ok btn-xs" onclick="verserRedistributionEnseignant('${escJs(e.personnel_id)}','${mois}',${e.montant_a_verser},'${escJs(e.prenom)} ${escJs(e.nom)}')">💰 Verser</button>` : '<span class="badge bdg-ok">✔ Soldé</span>'}</td>
        </tr>`).join('') : `<tr><td colspan="6">${emptyHtml('👨‍🏫','Aucune séance enregistrée ce mois')}</td></tr>`}
      </tbody>
    </table></div>
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>
  `, { wide: true });
}

async function verserRedistributionEnseignant(personnelId, mois, montant, nom) {
  if (!confirm(`Confirmer le versement de ${fmtMoney(montant)} à ${nom} pour ${mois} ?`)) return;
  try {
    await apiVerserRedistribution({ personnel_id: personnelId, mois, montant });
    toast('Redistribution versée ✅','success');
    modalRedistribution(mois);
    imprimerRecu({
      type: 'sortie', nom, description: `Redistribution cours de révision — ${mois}`,
      montant, date: today(), moyenPaiement: 'Espèces', recuPar: currentUser?.full_name,
    });
  } catch(e) { toast(e.message,'error'); }
}

window.modalRedistribution = modalRedistribution;
window.verserRedistributionEnseignant = verserRedistributionEnseignant;
window.modalAssignerEnseignant = modalAssignerEnseignant;
window.retirerEnseignantCours = retirerEnseignantCours;
window.modalEnregistrerSeance = modalEnregistrerSeance;
window.delSeanceRevision = delSeanceRevision;
