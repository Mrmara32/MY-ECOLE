/* ===================== NOTES & BULLETINS ===================== */
const PERIODES_LIBELLES = { '1': 'Trimestre 1', '2': 'Trimestre 2', '3': 'Trimestre 3', 'annee': 'Année (moyenne annuelle)' };

function rangTexte(l) {
  if (l.rang == null) return '—';
  return `${l.rang}${l.rang === 1 ? 'er' : 'e'}`;
}

async function pageNotes() {
  $('#content').innerHTML = loadingHtml;
  const estDirection = ['admin', 'directeur'].includes(currentUser?.role);
  let classes = [];
  try { classes = (await apiGetClassesFull()).map(c => c.nom); } catch (_) {}
  let filtClasse = '', filtPer = '1', donnees = null, annees = { en_cours: null, annees: [] }, filtAnnee = '';
  try { annees = await apiGetAnnees(); filtAnnee = annees.en_cours || (annees.annees[0] || ''); } catch (_) {}

  const charger = async () => {
    if (!filtClasse) {
      donnees = null;
      $('#notes-head').innerHTML = '<th>Élève</th><th>Rang</th><th>Moy. gén.</th><th>Actions</th>';
      $('#notes-body').innerHTML = `<tr><td colspan="4">${emptyHtml('📊','Sélectionnez une classe et une période')}</td></tr>`;
      $('#notes-actions').innerHTML = '';
      return;
    }
    try { donnees = await apiGetBulletinsClasse(filtClasse, filtPer, filtAnnee); }
    catch (e) { toast(e.message, 'error'); return; }
    afficher();
  };

  const afficher = () => {
    const d = donnees;
    const mats = d.matieres.map(m => m.matiere);
    const tri = d.eleves.slice().sort((a, b) => (a.rang ?? 9999) - (b.rang ?? 9999) || a.nom.localeCompare(b.nom));
    $('#notes-actions').innerHTML = `
      ${estDirection ? `<button class="btn btn-outline btn-sm" onclick="modalCoefficients('${escJs(filtClasse)}')">⚖️ Matières & coefficients</button>` : ''}
      ${estDirection && filtPer === 'annee' ? `<button class="btn btn-primary btn-sm" onclick="modalFinAnnee('${escJs(filtClasse)}','${escJs(filtAnnee)}')">🎓 Conseil de classe / fin d'année</button>` : ''}
      <span class="text-muted" style="font-size:12px">Moyenne de classe : <strong>${d.moyenne_classe != null ? d.moyenne_classe.toFixed(2) : '—'}</strong> · Plus forte : ${d.moyenne_max ?? '—'} · Plus faible : ${d.moyenne_min ?? '—'}</span>`;
    if (!tri.length) {
      $('#notes-head').innerHTML = '<th>Élève</th><th>Rang</th><th>Moy. gén.</th><th>Actions</th>';
      $('#notes-body').innerHTML = `<tr><td colspan="4">${emptyHtml('📊','Aucun élève actif dans cette classe')}</td></tr>`;
      return;
    }
    const peutSaisir = filtPer !== 'annee' && (!annees.en_cours || filtAnnee === annees.en_cours);   // on ne saisit que dans l'année en cours
    $('#notes-head').innerHTML = `<th>Élève</th><th>Rang</th>${d.matieres.map(m =>
      `<th style="min-width:80px">${esc(m.matiere)}<br><span class="text-muted" style="font-size:10px;font-weight:400">coef. ${m.coefficient}</span></th>`).join('')}
      <th>Moy. gén.</th><th>Mention</th><th>Actions</th>`;
    $('#notes-body').innerHTML = tri.map(l => `<tr>
        <td><strong>${esc(l.prenom)} ${esc(l.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(l.matricule || '')}</span></td>
        <td class="text-center"><span class="badge bdg-primary">${rangTexte(l)}</span><div class="text-muted" style="font-size:10px">/ ${l.effectif}</div></td>
        ${mats.map(m => `<td class="text-center">${noteBadge(l.moyennes[m] ?? null)}</td>`).join('')}
        <td class="text-center">${noteBadge(l.moyenne_generale)}</td>
        <td class="text-center">${esc(l.mention || '—')}${l.decision ? `<div class="text-muted" style="font-size:10px">${esc(l.decision.decision)}</div>` : ''}</td>
        <td><div class="td-actions">
          ${peutSaisir ? `<button class="btn btn-outline btn-xs" onclick="modalSaisieNote('${escJs(l.eleve_id)}','${escJs(l.prenom)} ${escJs(l.nom)}','${escJs(filtClasse)}','${filtPer}')">+ Note</button>` : ''}
          <button class="btn btn-outline btn-xs" title="Appréciation du conseil de classe" onclick="modalAppreciation('${escJs(l.eleve_id)}','${escJs(l.prenom)} ${escJs(l.nom)}','${filtPer}')">✍</button>
          <button class="btn btn-accent btn-xs" onclick="imprimerBulletin('${escJs(l.eleve_id)}','${filtPer}','${escJs(filtAnnee)}')">🖨</button>
        </div></td>
      </tr>`).join('') + `
      <tr style="background:#F3F4F6;font-size:12px"><td colspan="2"><strong>Moyenne de la classe</strong></td>
        ${d.matieres.map(m => `<td class="text-center">${m.moyenne_classe ?? '—'}</td>`).join('')}
        <td class="text-center"><strong>${d.moyenne_classe ?? '—'}</strong></td><td colspan="2"></td></tr>`;
  };
  window._rechargerNotes = charger;

  $('#content').innerHTML = `
  <div class="card">
    <div class="card-header"><span class="card-title">📊 Notes & Bulletins</span></div>
    <div class="filters">
      <div class="fg"><label>Classe*</label>
        <select id="f-ncls"><option value="">— Choisir —</option>${classes.map(c => `<option>${esc(c)}</option>`).join('')}</select>
      </div>
      <div class="fg"><label>Année scolaire</label>
        <select id="f-nannee">${annees.annees.map(a => `<option ${a === filtAnnee ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select>
      </div>
      <div class="fg"><label>Période</label>
        <select id="f-ntri">${Object.entries(PERIODES_LIBELLES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select>
      </div>
    </div>
    <div id="notes-actions" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:0 16px 10px"></div>
    <div class="tbl-wrap" style="overflow-x:auto">
      <table><thead><tr id="notes-head"><th>Élève</th><th>Rang</th><th>Moy. gén.</th><th>Actions</th></tr></thead>
      <tbody id="notes-body"><tr><td colspan="4">${emptyHtml('📊','Sélectionnez une classe et une période')}</td></tr></tbody></table>
    </div>
  </div>`;
  $('#f-ncls').addEventListener('change', e => { filtClasse = e.target.value; charger(); });
  $('#f-ntri').addEventListener('change', e => { filtPer = e.target.value; charger(); });
  $('#f-nannee').addEventListener('change', e => { filtAnnee = e.target.value; charger(); });
}

/* ── Matières & coefficients d'une classe ── */
async function modalCoefficients(classe) {
  let lignes = [];
  try { lignes = (await apiGetMatieresClasse(classe)).map(m => ({ matiere: m.matiere, coefficient: m.coefficient })); } catch (_) {}
  const dessiner = () => {
    $('#coef-lignes').innerHTML = lignes.length ? lignes.map((l, i) => `<div style="display:flex;gap:8px;margin-bottom:6px">
        <input list="liste-matieres" value="${esc(l.matiere)}" style="flex:1" onchange="_coefLigne(${i},'matiere',this.value)" placeholder="Matière">
        <input type="number" min="0.5" max="20" step="0.5" value="${l.coefficient}" style="width:90px" onchange="_coefLigne(${i},'coefficient',this.value)">
        <button type="button" class="btn btn-outline btn-xs" onclick="_coefSupprimer(${i})">✕</button></div>`).join('')
      : '<p class="text-muted">Aucune matière définie : toutes les matières notées comptent avec le coefficient 1.</p>';
  };
  window._coefLigne = (i, k, v) => { lignes[i][k] = k === 'coefficient' ? parseFloat(v) : v; };
  window._coefSupprimer = i => { lignes.splice(i, 1); dessiner(); };
  openModal(`Matières & coefficients — ${classe}`, `
    <datalist id="liste-matieres">${MATIERES.map(m => `<option value="${esc(m)}">`).join('')}</datalist>
    <p class="text-muted" style="font-size:12px">La moyenne générale est la moyenne des matières pondérée par ces coefficients. Une matière sans note pour un élève est ignorée (elle ne compte pas comme 0).</p>
    <div id="coef-lignes"></div>
    <button type="button" class="btn btn-outline btn-sm" onclick="_coefAjouter()">+ Ajouter une matière</button>
    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button type="button" class="btn btn-primary" onclick="_coefEnregistrer()">Enregistrer</button>
    </div>`);
  window._coefAjouter = () => { lignes.push({ matiere: '', coefficient: 1 }); dessiner(); };
  window._coefEnregistrer = async () => {
    try {
      await apiSetMatieresClasse(classe, lignes.filter(l => (l.matiere || '').trim()));
      toast('Coefficients enregistrés', 'success'); closeModal(); window._rechargerNotes && window._rechargerNotes();
    } catch (e) { toast(e.message, 'error'); }
  };
  dessiner();
}
window.modalCoefficients = modalCoefficients;

/* ── Appréciation du conseil de classe ── */
async function modalAppreciation(eleveId, nom, periode) {   // appréciation : année en cours
  let courant = '';
  try { courant = (await apiGetBulletinEleve(eleveId, periode)).eleve.appreciation || ''; } catch (_) {}
  openModal(`Appréciation — ${nom}`, `
    <div class="fg"><label>Appréciation (laisser vide pour l'appréciation automatique)</label>
    <textarea id="apprec-txt" rows="4" maxlength="500">${esc(courant)}</textarea></div>
    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button type="button" class="btn btn-primary" id="apprec-ok">Enregistrer</button>
    </div>`, { narrow: true });
  $('#apprec-ok').onclick = async () => {
    try { await apiSetAppreciation(eleveId, periode, $('#apprec-txt').value); toast('Appréciation enregistrée', 'success'); closeModal(); window._rechargerNotes && window._rechargerNotes(); }
    catch (e) { toast(e.message, 'error'); }
  };
}
window.modalAppreciation = modalAppreciation;

/* ── Conseil de classe : décisions de fin d'année ── */
async function modalFinAnnee(classe, annee) {
  let d, toutesClasses = [];
  try { d = await apiGetFinAnnee(classe, annee); toutesClasses = (await apiGetClassesFull()).map(c => c.nom); }
  catch (e) { toast(e.message, 'error'); return; }
  const settings = await apiGetSettings().catch(() => ({}));
  const optsClasse = sel => `<option value="">—</option>` + toutesClasses.map(c => `<option ${c === sel ? 'selected' : ''}>${esc(c)}</option>`).join('');
  const lignes = d.eleves.map(l => {
    const dec = l.decision?.decision || l.decision_proposee || '';
    const suiv = dec === 'redouble' ? classe : dec === 'exclu' ? '' : (l.decision?.classe_suivante || d.classe_suivante_suggeree || '');
    return `<tr data-id="${esc(l.eleve_id)}">
      <td>${esc(l.prenom)} ${esc(l.nom)}</td>
      <td class="text-center">${l.moyenne_generale ?? '—'}</td>
      <td><select class="dec" onchange="_decChange(this)">${['', 'admis', 'redouble', 'exclu'].map(v => `<option value="${v}" ${v === dec ? 'selected' : ''}>${v || '— (non décidé)'}</option>`).join('')}</select></td>
      <td><select class="suiv">${optsClasse(suiv)}</select></td></tr>`;
  }).join('');
  openModal(`Conseil de classe — ${classe}`, `
    <p class="text-muted" style="font-size:12px">Décision proposée automatiquement : admis si la moyenne annuelle atteint ${d.seuil_passage}/20 (réglable dans le paramètre « seuil_passage »). Vous pouvez la modifier élève par élève.</p>
    <div class="tbl-wrap"><table><thead><tr><th>Élève</th><th>Moy. annuelle</th><th>Décision</th><th>Classe suivante</th></tr></thead><tbody>${lignes}</tbody></table></div>
    <div class="fg" style="margin-top:12px"><label>Année scolaire concernée</label><input id="fa-annee" value="${esc(d.annee_scolaire || settings.annee_scolaire || '')}" placeholder="2025-2026"></div>
    <div class="modal-footer">
      <button type="button" class="btn btn-outline" onclick="closeModal()">Fermer</button>
      <button type="button" class="btn btn-primary" id="fa-save">Enregistrer les décisions</button>
      <button type="button" class="btn btn-accent" id="fa-rei">Créer les réinscriptions…</button>
    </div>`, { wide: true });
  window._decChange = sel => {   // la classe suivante suit la décision choisie
    const cible = sel.closest('tr').querySelector('.suiv');
    if (sel.value === 'redouble') cible.value = classe;
    else if (sel.value === 'exclu') cible.value = '';
    else if (sel.value === 'admis') cible.value = d.classe_suivante_suggeree || '';
  };
  const collecter = () => [...document.querySelectorAll('tr[data-id]')].map(tr => ({
    eleve_id: tr.dataset.id, decision: tr.querySelector('.dec').value, classe_suivante: tr.querySelector('.suiv').value || undefined,
  })).filter(x => x.decision);
  const enregistrer = async () => {
    const annee = $('#fa-annee').value.trim();
    if (!annee) { toast("Indiquez l'année scolaire", 'error'); return false; }
    const decisions = collecter();
    if (!decisions.length) { toast('Aucune décision à enregistrer', 'error'); return false; }
    try { await apiSaveDecisions(annee, classe, decisions); toast(`${decisions.length} décision(s) enregistrée(s)`, 'success'); return annee; }
    catch (e) { toast(e.message, 'error'); return false; }
  };
  $('#fa-save').onclick = async () => { if (await enregistrer()) window._rechargerNotes && window._rechargerNotes(); };
  $('#fa-rei').onclick = async () => {
    const annee = await enregistrer(); if (!annee) return;
    const nouvelle = prompt(`Nouvelle année scolaire pour les réinscriptions (ex. suivante de ${annee}) :`);
    if (!nouvelle) return;
    try {
      const r = await apiProposerReinscriptions(annee, nouvelle.trim());
      toast(`${r.creees} réinscription(s) créée(s) en attente (${r.deja_existantes} déjà existante(s)) — à valider dans « Réinscriptions »`, 'success');
    } catch (e) { toast(e.message, 'error'); }
  };
}
window.modalFinAnnee = modalFinAnnee;

async function modalSaisieNote(eleveId, eleveName, classe, trimestre) {
  // Matières de la classe (définies avec leurs coefficients) ; liste générale à défaut.
  let matieresClasse = [];
  try { matieresClasse = (await apiGetMatieresClasse(classe)).map(m => m.matiere); } catch (_) {}
  const listeMatieres = matieresClasse.length ? matieresClasse : MATIERES;
  openModal(`Saisir une note — ${eleveName}`, `
    <form id="f-note" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Matière*</label><select name="matiere" required>${optionsHtml(listeMatieres)}</select></div>
        <div class="fg"><label>Type</label><select name="type">
          <option value="Devoir">Devoir</option>
          <option value="Composition">Composition</option>
          <option value="Interrogation">Interrogation</option>
          <option value="Examen">Examen</option>
        </select></div>
      </div>
      <div class="form-3">
        <div class="fg"><label>Note obtenue*</label><input type="number" name="note" min="0" step="0.25" required placeholder="12.5"></div>
        <div class="fg"><label>Sur (max)</label><input type="number" name="note_max" value="20" min="1" step="0.5"></div>
        <div class="fg"><label>Date</label><input type="date" name="date_note" value="${today()}"></div>
      </div>
      <input type="hidden" name="eleve_id" value="${esc(eleveId)}">
      <input type="hidden" name="trimestre" value="${esc(trimestre)}">
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer la note</button>
      </div>
    </form>`, { narrow: true });
  $('#f-note').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.note = parseFloat(fd.note);
    fd.note_max = parseFloat(fd.note_max);
    try { await apiCreateNote(fd); toast('Note enregistrée','success'); closeModal(); pageNotes(); }
    catch(err) { toast(err.message,'error'); }
  };
}
window.modalSaisieNote = modalSaisieNote;
