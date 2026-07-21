/* ===================== NOTES & BULLETINS ===================== */
async function pageNotes() {
  $('#content').innerHTML = loadingHtml;
  const [eleves, notes] = await Promise.all([apiGetEleves(), apiGetNotes()]);
  let filtClasse = '', filtTri = '1';

  const classes = [...new Set(eleves.map(e=>e.classe).filter(Boolean))].sort();

  const renderTable = () => {
    const cls = filtClasse;
    const tri = filtTri;
    const filtEleves = eleves.filter(e => (!cls||e.classe===cls) && e.statut==='actif');
    const filtNotes  = notes.filter(n => (!cls||n.classe===cls) && String(n.trimestre)===String(tri));
    const matSet = new Set(filtNotes.map(n=>n.matiere));
    const mats = [...matSet].sort();

    // Tableau croisé
    const moyParEleve = {};
    filtEleves.forEach(e => {
      const enotes = filtNotes.filter(n=>n.eleve_id===e.id);
      const parMat = {};
      mats.forEach(m => {
        const mn = enotes.filter(n=>n.matiere===m);
        if (mn.length) parMat[m] = mn.reduce((s,n)=>s+(n.note/(n.note_max||20)*20),0)/mn.length;
        else parMat[m] = null;
      });
      const vals = Object.values(parMat).filter(v=>v!=null);
      moyParEleve[e.id] = { parMat, moy: vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null };
    });

    const sorted = [...filtEleves].sort((a,b) => {
      const ma = moyParEleve[a.id]?.moy ?? -1;
      const mb = moyParEleve[b.id]?.moy ?? -1;
      return mb - ma;
    });

    if (!filtEleves.length) {
      $('#notes-body').innerHTML = `<tr><td colspan="${mats.length+4}">${emptyHtml('📊','Sélectionnez une classe')}</td></tr>`;
      $('#notes-head').innerHTML = '<th>Élève</th><th>Rang</th><th>Moy. gén.</th><th>Actions</th>';
      return;
    }

    $('#notes-head').innerHTML = `<th>Élève</th><th>Rang</th>${mats.map(m=>`<th style="min-width:80px">${esc(m)}</th>`).join('')}<th>Moy. gén.</th><th>Actions</th>`;
    $('#notes-body').innerHTML = sorted.map((e, idx) => {
      const em = moyParEleve[e.id];
      return `<tr>
        <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(e.matricule||'')}</span></td>
        <td class="text-center"><span class="badge bdg-primary">${idx+1}e</span></td>
        ${mats.map(m=>`<td class="text-center">${noteBadge(em.parMat[m])}</td>`).join('')}
        <td class="text-center">${noteBadge(em.moy)}</td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalSaisieNote('${escJs(e.id)}','${escJs(e.prenom)} ${escJs(e.nom)}','${escJs(cls)}','${tri}')">+ Note</button>
          <button class="btn btn-accent btn-xs" onclick="imprimerBulletin('${escJs(e.id)}',${tri})">🖨</button>
        </div></td>
      </tr>`;
    }).join('');
  };

  $('#content').innerHTML = `
  <div class="card">
    <div class="card-header">
      <span class="card-title">📊 Notes & Bulletins</span>
    </div>
    <div class="filters">
      <div class="fg"><label>Classe*</label>
        <select id="f-ncls"><option value="">— Choisir —</option>${classes.map(c=>`<option>${esc(c)}</option>`).join('')}</select>
      </div>
      <div class="fg"><label>Trimestre</label>
        <select id="f-ntri"><option value="1">Trimestre 1</option><option value="2">Trimestre 2</option><option value="3">Trimestre 3</option></select>
      </div>
    </div>
    <div class="tbl-wrap" style="overflow-x:auto">
      <table><thead><tr id="notes-head"><th>Élève</th><th>Rang</th><th>Moy. gén.</th><th>Actions</th></tr></thead>
      <tbody id="notes-body"><tr><td colspan="4">${emptyHtml('📊','Sélectionnez une classe et un trimestre')}</td></tr></tbody></table>
    </div>
  </div>`;

  $('#f-ncls').addEventListener('change', e => { filtClasse=e.target.value; renderTable(); });
  $('#f-ntri').addEventListener('change', e => { filtTri=e.target.value; renderTable(); });
}

async function modalSaisieNote(eleveId, eleveName, classe, trimestre) {
  openModal(`Saisir une note — ${eleveName}`, `
    <form id="f-note" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Matière*</label><select name="matiere" required>${optionsHtml(MATIERES)}</select></div>
        <div class="fg"><label>Type</label><select name="type">
          <option value="Devoir">Devoir</option>
          <option value="Composition">Composition</option>
          <option value="Interrogation">Interrogation</option>
          <option value="Examen">Examen</option>
        </select></div>
      </div>
      <div class="form-3">
        <div class="fg"><label>Note obtenue*</label><input type="number" name="note" min="0" max="20" step="0.25" required placeholder="12.5"></div>
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
