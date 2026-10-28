/* ===================== PAIEMENTS ===================== */
let _paiEleves = [];
async function pagePaiements() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [paiements, eleves] = await Promise.all([apiGetPaiements(), apiGetEleves()]);
    _paiEleves = eleves;
    const classes = [...new Set(eleves.map(e=>e.classe).filter(Boolean))].sort();

    const render = data => {
      const total_du   = data.reduce((s,p)=>s+p.montant_du,0);
      const total_paye = data.reduce((s,p)=>s+p.montant_paye,0);
      const reste      = total_du - total_paye;
      $('#pai-summary').innerHTML = `
        <div class="stats-grid" style="grid-template-columns:repeat(3,1fr)">
          <div class="stat"><div class="stat-label">Total dû</div><div class="stat-val" style="font-size:16px">${fmtMoney(total_du)}</div></div>
          <div class="stat"><div class="stat-label">Perçu</div><div class="stat-val text-ok" style="font-size:16px">${fmtMoney(total_paye)}</div></div>
          <div class="stat"><div class="stat-label">Reste impayé</div><div class="stat-val text-err" style="font-size:16px">${fmtMoney(reste)}</div></div>
        </div>`;
      const SCOLOR = { paye:'bdg-ok', partiel:'bdg-warn', a_payer:'bdg-err', en_retard:'bdg-err' };
      const SLABEL = { paye:'Payé', partiel:'Partiel', a_payer:'À payer', en_retard:'En retard' };
      const { items, page, totalPages, total } = paginate('paiements', data);
      $('#tb-pai').innerHTML = items.length ? items.map(p => {
        const pct = p.montant_du > 0 ? Math.round(p.montant_paye/p.montant_du*100) : 0;
        return `<tr>
          <td>${elevePhoto({photo_url:null,nom:p.nom,prenom:p.prenom},28)}</td>
          <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(p.matricule||'')} · ${esc(p.classe||'')}</span></td>
          <td>${esc(p.libelle||p.type_frais||'—')}</td>
          <td class="mono text-right">${fmtMoney(p.montant_du)}</td>
          <td>
            <div class="progress mb-2" style="width:80px"><div class="progress-bar ${pct>=100?'':'warn'}" style="width:${pct}%"></div></div>
            <span class="text-muted" style="font-size:11px">${fmtMoney(p.montant_paye)} (${pct}%)</span>
          </td>
          <td class="mono text-right text-err">${fmtMoney(p.montant_du-p.montant_paye)}</td>
          <td>${fmtDate(p.date_echeance)}</td>
          <td><span class="badge ${SCOLOR[p.statut]||'bdg-gray'}">${SLABEL[p.statut]||p.statut}</span></td>
          <td><div class="td-actions">
            ${p.statut!=='paye' && ['admin','comptable'].includes(currentUser.role)?`<button class="btn btn-ok btn-xs" onclick="modalVerser('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}',${p.montant_du-p.montant_paye},'${escJs(p.libelle||'Scolarité')}')">💰 Payer</button>`:''}
            ${currentUser.role==='admin'?`<button class="btn btn-danger btn-xs" title="Supprimer (motif obligatoire)" onclick="delPaiement('${escJs(p.id)}','${escJs(p.prenom)} ${escJs(p.nom)}','${escJs(p.libelle||p.type_frais||'Paiement')}',${Number(p.montant_du)||0},${Number(p.montant_paye)||0})">🗑</button>`:''}
          </div></td>
        </tr>`;
      }).join('') : `<tr><td colspan="9">${emptyHtml('💰','Aucun paiement')}</td></tr>`;
      $('#pag-pai').innerHTML = paginationHtml('paiements', page, totalPages, total);
    };

    $('#content').innerHTML = `
    <div id="pai-summary" class="mb-4"></div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">💰 Paiements & Frais de scolarité</span>
        <div class="card-actions">
          ${['admin','directeur','comptable'].includes(currentUser.role)?`<button class="btn btn-outline btn-sm" onclick="modalPaiementsSupprimes()" title="Paiements supprimés : qui, quand, pourquoi">🗂 Supprimés</button>`:''}
          ${['admin','directeur','comptable','secretaire'].includes(currentUser.role)?`<button class="btn btn-outline btn-sm" style="border-color:#ff7900;color:#A04400" onclick="modalOrangeMoney()" title="Paiements reçus par Orange Money (QR marchand de l'école)">🟠 Orange Money</button>`:''}
          ${['admin','directeur','comptable'].includes(currentUser.role)?`<button class="btn btn-outline btn-sm" onclick="modalRelances()" title="Parents à relancer par WhatsApp ou SMS">📣 Relances</button>`:''}
          <button class="btn btn-outline btn-sm" onclick="modalGenPaiements()">⚡ Générer échéances</button>
          <button class="btn btn-primary btn-sm" onclick="modalBaremes()">⚙ Barèmes</button>
        </div>
      </div>
      <div class="filters">
        <div class="fg grow"><label>Recherche</label><input id="q-pai" placeholder="Nom, prénom, matricule…"></div>
        <div class="fg"><label>Classe</label><select id="f-pcls"><option value="">Toutes</option>${classes.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
        <div class="fg"><label>Statut</label><select id="f-pstat">
          <option value="">Tous</option><option value="a_payer">À payer</option>
          <option value="partiel">Partiel</option><option value="paye">Payé</option>
        </select></div>
        <div class="fg"><label>Année</label><input id="f-pann" value="${anneeCourante()}" placeholder="${anneeCourante()}"></div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr id="th-pai"><th></th><th>Élève</th><th>Libellé</th><th class="text-right">Montant dû</th><th>Progression</th><th class="text-right">Reste</th><th>Échéance</th><th>Statut</th><th>Actions</th></tr></thead>
        <tbody id="tb-pai"></tbody>
      </table></div>
      <div id="pag-pai"></div>
    </div>`;

    let curr = paiements;
    getPaginator('paiements').onChange = () => render(curr);
    render(curr);
    const refilter = async () => {
      const cls = $('#f-pcls').value;
      const stat = $('#f-pstat').value;
      const ann = $('#f-pann').value;
      const q = $('#q-pai').value.toLowerCase();
      let qs = [];
      if (cls) qs.push(`classe=${encodeURIComponent(cls)}`);
      if (stat) qs.push(`statut=${stat}`);
      if (ann) qs.push(`annee_scolaire=${ann}`);
      try {
        let data = await apiGetPaiements(qs.join('&'));
        if (q) data = data.filter(p => `${p.nom} ${p.prenom} ${p.matricule||''}`.toLowerCase().includes(q));
        curr = data;
        resetPaginator('paiements');
        render(curr);
      } catch(e) { toast(e.message,'error'); }
    };
    ['#f-pcls','#f-pstat'].forEach(s => $(s).addEventListener('change', refilter));
    $('#f-pann').addEventListener('blur', refilter);
    $('#q-pai').addEventListener('input', refilter);

    makeSortableTable('#th-pai', () => curr, render,
      [null, row => `${row.prenom} ${row.nom}`, 'libelle', 'montant_du', null, row => row.montant_du - row.montant_paye, 'date_echeance', 'statut', null]);
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function modalVerser(paiementId, eleveName, reste, libelle = 'Scolarité') {
  reste = Math.max(0, Math.round(reste));
  openModal(`Enregistrer un paiement — ${eleveName}`, `
    <form id="f-vers" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">Reste à payer : <strong>${fmtMoney(reste)}</strong></div>
      <div class="fg"><label>Montant versé (GNF)*</label>
        <input type="number" name="montant" required min="1" step="1" value="${reste || ''}" placeholder="${reste || 'Montant'}">
      </div>
      <div class="form-2">
        <div class="fg"><label>Moyen de paiement</label><select name="moyen_paiement">${MOYENS_PAIEMENT.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
        <div class="fg"><label>Date</label><input type="date" name="date_vers" value="${today()}"></div>
      </div>
      <div class="fg"><label>Référence / N° reçu</label><input name="reference" placeholder="REC-001…"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-ok">✅ Valider le paiement</button>
      </div>
    </form>`, { narrow: true });
  $('#f-vers').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.montant = parseFloat(fd.montant);
    try {
      const resultat = await apiVerserPaiement(paiementId, fd);
      toast('Paiement enregistré ✅','success'); closeModal(); pagePaiements();
      imprimerRecu({
        type: 'entree', nom: eleveName, description: libelle, montant: fd.montant,
        date: fd.date_vers || today(), moyenPaiement: fd.moyen_paiement,
        // Numéro officiel attribué par le serveur (le même qu'en comptabilité)
        reference: resultat?.numero_recu || fd.reference,
        recuPar: currentUser?.full_name,
      });
    }
    catch(err) { toast(err.message,'error'); }
  };
}

async function modalGenPaiements() {
  const eleves = _paiEleves;
  openModal('Générer les échéances de scolarité', `
    <form id="f-gen" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">Génère automatiquement le frais d'entrée (inscription ou réinscription) et les tranches de scolarité selon le barème de la classe.</div>
      <div class="fg"><label>Élève*</label>
        <select name="eleve_id" required>
          <option value="">— Choisir —</option>
          ${eleves.filter(e=>e.statut==='actif').map(e=>`<option value="${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} — ${esc(e.classe||'?')}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Type*</label>
        <select name="type_inscription" required>
          <option value="nouvelle">Frais d'inscription (nouvel élève)</option>
          <option value="reinscription">Frais de réinscription (ancien élève)</option>
        </select>
      </div>
      <div class="form-2">
        <div class="fg"><label>Année scolaire*</label><input name="annee_scolaire" value="${anneeCourante()}" required></div>
        <div class="fg"><label>Date de début</label><input type="date" name="date_debut" value="${today()}"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">⚡ Générer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-gen').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { const r = await apiGenPaiements(fd); toast(`${r.count} échéances générées`,'success'); closeModal(); pagePaiements(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function modalBaremes() {
  const frais = await apiGetFrais().catch(()=>[]);
  openModal('⚙ Barèmes des frais de scolarité', `
    <div class="mb-3 flex" style="justify-content:flex-end">
      <button class="btn btn-primary btn-sm" onclick="modalAddBareme()">+ Ajouter un barème</button>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Classe</th><th>Année</th><th class="text-right">Inscription</th><th class="text-right">Réinscription</th><th class="text-right">Scolarité</th><th>Tranches</th><th>Actions</th></tr></thead>
      <tbody>
      ${frais.length ? frais.map(f=>`<tr>
        <td><span class="badge bdg-primary">${esc(f.classe)}</span></td>
        <td>${esc(f.annee_scolaire)}</td>
        <td class="mono text-right">${fmtMoney(f.frais_inscription)}</td>
        <td class="mono text-right">${fmtMoney(f.frais_reinscription)}</td>
        <td class="mono text-right">${fmtMoney(f.scolarite_annuelle)}</td>
        <td class="text-center"><span class="badge bdg-primary">45% / 40% / 15%</span></td>
        <td><div class="td-actions">
          <button class="btn btn-outline btn-xs" onclick="modalEditBareme('${escJs(f.id)}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="delBareme('${escJs(f.id)}')" ${currentUser.role!=='admin'?'style="display:none"':''}>🗑</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('⚙','Aucun barème défini')}</td></tr>`}
      </tbody>
    </table></div>`, { wide: true });
}

async function modalAddBareme() {
  openModal('Ajouter un barème', `
    <form id="f-bar" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Classe*</label><select name="classe" required>${optionsHtml(CLASSES)}</select></div>
        <div class="fg"><label>Année scolaire*</label><input name="annee_scolaire" value="${anneeCourante()}" required></div>
      </div>
      <div class="form-2">
        <div class="fg"><label>Frais d'inscription (GNF)</label><input type="number" name="frais_inscription" value="0"></div>
        <div class="fg"><label>Frais de réinscription (GNF)</label><input type="number" name="frais_reinscription" value="0"></div>
      </div>
      <div class="fg"><label>Scolarité annuelle (GNF)</label><input type="number" name="scolarite_annuelle" value="0"></div>
      <div class="alert alert-info">💡 Le <strong>frais d'inscription</strong> s'applique à un nouvel élève, le <strong>frais de réinscription</strong> à un élève qui revient. La scolarité annuelle est automatiquement répartie en 3 tranches : <strong>45%</strong>, <strong>40%</strong> puis <strong>15%</strong>.</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="modalBaremes()">Retour</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);
  $('#f-bar').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.frais_inscription = parseFloat(fd.frais_inscription)||0;
    fd.frais_reinscription = parseFloat(fd.frais_reinscription)||0;
    fd.scolarite_annuelle = parseFloat(fd.scolarite_annuelle)||0;
    try { await apiCreateFrais(fd); toast('Barème ajouté','success'); modalBaremes(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function modalEditBareme(id) {
  const frais = await apiGetFrais();
  const f = frais.find(x=>x.id===id);
  if (!f) return;
  openModal('Modifier le barème', `
    <form id="f-ebar" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info">Classe : <strong>${esc(f.classe)}</strong> — Année : <strong>${esc(f.annee_scolaire)}</strong></div>
      <div class="form-2">
        <div class="fg"><label>Frais d'inscription (GNF)</label><input type="number" name="frais_inscription" value="${f.frais_inscription||0}"></div>
        <div class="fg"><label>Frais de réinscription (GNF)</label><input type="number" name="frais_reinscription" value="${f.frais_reinscription||0}"></div>
      </div>
      <div class="fg"><label>Scolarité annuelle (GNF)</label><input type="number" name="scolarite_annuelle" value="${f.scolarite_annuelle||0}"></div>
      <div class="alert alert-info">💡 Répartition fixe : <strong>45%</strong> / <strong>40%</strong> / <strong>15%</strong> sur 3 tranches.</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="modalBaremes()">Retour</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);
  $('#f-ebar').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.frais_inscription = parseFloat(fd.frais_inscription)||0;
    fd.frais_reinscription = parseFloat(fd.frais_reinscription)||0;
    fd.scolarite_annuelle = parseFloat(fd.scolarite_annuelle)||0;
    try { await apiUpdateFrais(id, fd); toast('Barème mis à jour','success'); modalBaremes(); }
    catch(err) { toast(err.message,'error'); }
  };
}

async function delBareme(id) {
  if (!confirmDel()) return;
  try { await apiDeleteFrais(id); toast('Supprimé','success'); modalBaremes(); }
  catch(e) { toast(e.message,'error'); }
}

function delPaiement(id, eleveNom = '', libelle = 'Paiement', montantDu = 0, montantPaye = 0) {
  const avertissement = montantPaye > 0
    ? `<div class="alert alert-warn">⚠️ <strong>${fmtMoney(montantPaye)}</strong> ont déjà été encaissés sur ce paiement.
         Les versements seront archivés avec la ligne ; les recettes déjà passées en comptabilité (et leurs reçus) ne sont pas modifiées.</div>`
    : '';
  openModal('Supprimer une ligne de paiement', `
    <form id="f-delpai" style="display:flex;flex-direction:column;gap:14px">
      <div class="alert alert-info"><strong>${esc(eleveNom)}</strong> — ${esc(libelle)} · dû : ${fmtMoney(montantDu)}</div>
      ${avertissement}
      <div class="fg">
        <label>Motif de la suppression*</label>
        <input name="motif" required minlength="5" placeholder="Ex : paiement créé en double, mauvais élève, erreur de montant…">
      </div>
      <p class="text-muted" style="font-size:12px;margin:0">Le paiement et ses versements sont conservés dans l'archive
        « 🗂 Supprimés », avec votre nom, la date et ce motif.</p>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-danger">🗑 Supprimer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-delpai').onsubmit = async e => {
    e.preventDefault();
    const motif = new FormData(e.target).get('motif').trim();
    if (motif.length < 5) { toast('Précisez le motif (au moins 5 caractères)', 'error'); return; }
    try { await apiDeletePaiement(id, motif); toast('Paiement supprimé et archivé', 'success'); closeModal(); pagePaiements(); }
    catch(err) { toast(err.message, 'error'); }
  };
}

async function modalPaiementsSupprimes() {
  openModal('🗂 Paiements supprimés', loadingHtml, { wide: true });
  try {
    const lignes = await apiGetPaiementsSupprimes();
    const corps = lignes.length ? lignes.map(l => `<tr>
        <td>${fmtDate((l.supprime_le || '').slice(0, 10))}</td>
        <td>${esc(l.eleve_nom || '—')}</td>
        <td>${esc(l.libelle || '—')}</td>
        <td class="mono text-right">${fmtMoney(l.montant_du)}</td>
        <td class="mono text-right">${fmtMoney(l.montant_paye)}${l.nb_versements ? `<br><span class="text-muted" style="font-size:11px">${l.nb_versements} versement(s)</span>` : ''}</td>
        <td>${esc(l.supprime_par_nom || '—')}</td>
        <td>${esc(l.motif)}</td>
      </tr>`).join('') : `<tr><td colspan="7">${emptyHtml('🗂', 'Aucun paiement supprimé')}</td></tr>`;
    $('#modal-body').innerHTML = `
      <div class="tbl-wrap"><table>
        <thead><tr><th>Date</th><th>Élève</th><th>Libellé</th><th class="text-right">Dû</th><th class="text-right">Déjà payé</th><th>Supprimé par</th><th>Motif</th></tr></thead>
        <tbody>${corps}</tbody>
      </table></div>
      <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>`;
  } catch (e) { $('#modal-body').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
window.modalVerser = modalVerser;
window.modalGenPaiements = modalGenPaiements;
window.modalBaremes = modalBaremes;
window.modalAddBareme = modalAddBareme;
window.modalEditBareme = modalEditBareme;
window.delBareme = delBareme;
window.delPaiement = delPaiement;
window.modalPaiementsSupprimes = modalPaiementsSupprimes;

/* ---------- Relances d'impayés (WhatsApp / SMS / appel, sans abonnement) ---------- */
const RELANCE_MODELE_DEFAUT =
  "Bonjour {parent}, {ecole} vous rappelle que la scolarité de {eleve} ({classe}) présente un solde de {montant}. " +
  "Merci de bien vouloir régulariser. {paiement} Cordialement.";
let _relances = [];
let _nomEcoleRelance = '';

function messageRelance(el, modele) {
  const parent = el.contact && el.contact.nom ? el.contact.nom : 'Madame, Monsieur';
  const montant = fmtMoney(el.reste_en_retard > 0 ? el.reste_en_retard : el.reste);
  return modele
    .replaceAll('{parent}', parent)
    .replaceAll('{eleve}', `${el.prenom} ${el.nom}`)
    .replaceAll('{classe}', el.classe || '')
    .replaceAll('{montant}', montant)
    .replaceAll('{ecole}', _nomEcoleRelance || 'Groupe scolaire')
    .replaceAll('{paiement}', _omConfigRelance && (_omConfigRelance.qr_url || _omConfigRelance.code)
      ? `Vous pouvez payer par Orange Money (Paiement marchand${_omConfigRelance.code ? ', code ' + _omConfigRelance.code : ''}${_omConfigRelance.nom ? ' : ' + _omConfigRelance.nom : ''}). Page de paiement : ${location.origin}/payer` : '')
    .replace(/ {2,}/g, ' ').trim();
}

let _waAutoRel = false, _smsAutoRel = false, _omRel = false, _omConfigRelance = null;
async function modalRelances() {
  openModal('📣 Relances des impayés', loadingHtml, { wide: true });
  try {
    const [impayes, parametres] = await Promise.all([apiGetImpayes(), apiGetSettings().catch(() => ({}))]);
    _waAutoRel = await whatsappAutoActif();
    _smsAutoRel = await smsAutoActif();
    _omConfigRelance = await apiFetch('/orange-money/config').catch(() => null);
    _omRel = await orangeMoneyActif() && ['admin', 'directeur', 'comptable'].includes(currentUser.role);
    _relances = impayes;
    _nomEcoleRelance = (parametres && parametres.ecole_nom) || '';
  } catch (e) { $('#modal-body').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  let modele = RELANCE_MODELE_DEFAUT;
  try { modele = localStorage.getItem('gs_modele_relance') || modele; } catch (e) { /* stockage indisponible */ }
  const classes = [...new Set(_relances.map(r => r.classe).filter(Boolean))].sort();
  $('#modal-body').innerHTML = `
    <div class="alert alert-info" style="font-size:12px">Choisissez un parent : WhatsApp ou SMS s'ouvre avec le message déjà écrit,
      il ne reste qu'à l'envoyer. Chaque relance est enregistrée dans le journal.</div>
    <div class="fg"><label>Message type — {parent} {eleve} {classe} {montant} {ecole}</label>
      <textarea id="rel-modele" rows="3">${esc(modele)}</textarea></div>
    <div class="filters">
      <div class="fg grow"><label>Recherche</label><input id="rel-q" placeholder="Nom, prénom, matricule…"></div>
      <div class="fg"><label>Classe</label><select id="rel-cls"><option value="">Toutes</option>${classes.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
      <div class="fg"><label>Afficher</label><select id="rel-retard">
        <option value="1">En retard seulement</option><option value="0">Tous les soldes</option></select></div>
    </div>
    <div id="rel-resume" class="text-muted" style="font-size:12px;margin:6px 0"></div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Élève</th><th class="text-right">Solde</th><th>Parent à contacter</th><th>Dernière relance</th><th>Relancer</th></tr></thead>
      <tbody id="rel-corps"></tbody>
    </table></div>
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button></div>`;

  const dessiner = () => {
    const q = $('#rel-q').value.toLowerCase().trim();
    const cls = $('#rel-cls').value;
    const retardSeul = $('#rel-retard').value === '1';
    const liste = _relances.filter(r =>
      (!cls || r.classe === cls) && (!retardSeul || r.reste_en_retard > 0) &&
      (!q || `${r.nom} ${r.prenom} ${r.matricule || ''}`.toLowerCase().includes(q)));
    const total = liste.reduce((s, r) => s + (retardSeul ? r.reste_en_retard : r.reste), 0);
    $('#rel-resume').textContent = `${liste.length} élève(s) · ${fmtMoney(total)} à recouvrer`;
    $('#rel-corps').innerHTML = liste.length ? liste.map(r => {
      const i = _relances.indexOf(r);
      const intl = r.contact ? numeroInternational(r.contact.telephone) : '';
      const actions = r.contact ? `
        ${_omRel ? `<button class="btn btn-outline btn-xs" style="border-color:#ff7900;color:#A04400" onclick="lienOrangeMoney(${i})">🟠 Lien de paiement</button>` : ''}
        ${intl && _smsAutoRel ? `<button class="btn btn-primary btn-xs" onclick="envoyerRelanceSmsAuto(${i})">📨 SMS auto</button>` : ''}
        ${intl && _waAutoRel ? `<button class="btn btn-primary btn-xs" onclick="envoyerRelanceAuto(${i})">📤 Auto</button>` : ''}
        ${intl ? `<button class="btn btn-ok btn-xs" onclick="envoyerRelance(${i},'whatsapp')">WhatsApp</button>` : ''}
        <button class="btn btn-outline btn-xs" onclick="envoyerRelance(${i},'sms')">SMS</button>
        <button class="btn btn-outline btn-xs" onclick="envoyerRelance(${i},'appel')">Appeler</button>
        <button class="btn btn-outline btn-xs" onclick="envoyerRelance(${i},'copie')">Copier</button>`
        : '<span class="text-muted" style="font-size:12px">Aucun numéro enregistré</span>';
      return `<tr>
        <td><strong>${esc(r.prenom)} ${esc(r.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(r.matricule || '')} · ${esc(r.classe || '')}</span></td>
        <td class="mono text-right text-err">${fmtMoney(r.reste)}${r.reste_en_retard > 0 && r.reste_en_retard !== r.reste
          ? `<br><span style="font-size:11px">dont ${fmtMoney(r.reste_en_retard)} en retard</span>` : ''}</td>
        <td>${r.contact ? `${esc(r.contact.nom || r.contact.lien)} <span class="text-muted" style="font-size:11px">(${esc(r.contact.lien)})</span><br><span class="mono" style="font-size:12px">${esc(r.contact.telephone)}</span>` : '—'}</td>
        <td id="rel-der-${i}">${r.derniere_relance ? `${fmtDate(r.derniere_relance.slice(0, 10))}${r.nb_relances > 1 ? ` <span class="text-muted" style="font-size:11px">(${r.nb_relances}×)</span>` : ''}` : '<span class="text-muted">Jamais</span>'}</td>
        <td><div class="td-actions">${actions}</div></td></tr>`;
    }).join('') : `<tr><td colspan="5">${emptyHtml('✅', 'Aucun impayé pour ce filtre')}</td></tr>`;
  };
  ['#rel-q'].forEach(s => $(s).addEventListener('input', dessiner));
  ['#rel-cls', '#rel-retard'].forEach(s => $(s).addEventListener('change', dessiner));
  $('#rel-modele').addEventListener('change', e => {
    try { localStorage.setItem('gs_modele_relance', e.target.value); } catch (err) { /* sans importance */ }
  });
  dessiner();
}

async function envoyerRelance(i, canal) {
  const el = _relances[i];
  if (!el || !el.contact) return;
  const modeleSaisi = $('#rel-modele');
  const texte = messageRelance(el, (modeleSaisi && modeleSaisi.value.trim()) || RELANCE_MODELE_DEFAUT);
  const intl = numeroInternational(el.contact.telephone);
  const tel = String(el.contact.telephone).replace(/[^\d+]/g, '');
  if (canal === 'whatsapp') window.open(`https://wa.me/${intl}?text=${encodeURIComponent(texte)}`, '_blank', 'noopener');
  else if (canal === 'sms') window.location.href = `sms:${tel}?body=${encodeURIComponent(texte)}`;
  else if (canal === 'appel') window.location.href = `tel:${tel}`;
  else {
    try { await navigator.clipboard.writeText(texte); toast('Message copié', 'success'); }
    catch (e) { toast('Copie impossible : sélectionnez le message à la main', 'error'); return; }
  }
  try {
    await apiEnregistrerRelance(el.eleve_id, { canal, reste: el.reste });
    el.derniere_relance = new Date().toISOString();
    el.nb_relances = (el.nb_relances || 0) + 1;
    const cellule = $(`#rel-der-${i}`);
    if (cellule) cellule.innerHTML = `${fmtDate(el.derniere_relance.slice(0, 10))} <span class="text-muted" style="font-size:11px">(${el.nb_relances}×)</span>`;
  } catch (e) { toast('Relance faite, mais non enregistrée dans le journal : ' + e.message, 'warning'); }
}
window.modalRelances = modalRelances;
window.envoyerRelance = envoyerRelance;


async function envoyerRelanceAuto(i) {
  const el = _relances[i];
  if (!el || !confirm(`Envoyer la relance WhatsApp à ${el.contact.nom || el.contact.lien} (${fmtMoney(el.reste)}) ?`)) return;
  try {
    await apiWhatsappRelance(el.eleve_id);
    el.derniere_relance = new Date().toISOString(); el.nb_relances = (el.nb_relances || 0) + 1;
    const c = $('#rel-der-' + i); if (c) c.textContent = fmtDate(el.derniere_relance.slice(0, 10));
    toast('Relance WhatsApp envoyée', 'success');
  } catch (e) { toast(e.message, 'error'); }
}
window.envoyerRelanceAuto = envoyerRelanceAuto;


async function envoyerRelanceSmsAuto(i) {
  const el = _relances[i];
  if (!el || !confirm(`Envoyer la relance par SMS à ${el.contact.nom || el.contact.lien} (${fmtMoney(el.reste)}) ?`)) return;
  const message = messageRelance(el, ($('#rel-modele').value || '').trim() || RELANCE_MODELE_DEFAUT);
  try {
    await apiSmsRelance(el.eleve_id, message);
    el.derniere_relance = new Date().toISOString(); el.nb_relances = (el.nb_relances || 0) + 1;
    const c = $('#rel-der-' + i); if (c) c.textContent = fmtDate(el.derniere_relance.slice(0, 10));
    toast('Relance SMS envoyée', 'success');
  } catch (e) { toast(e.message, 'error'); }
}
window.envoyerRelanceSmsAuto = envoyerRelanceSmsAuto;


/* Lien de paiement Orange Money : le parent paie depuis son téléphone, le versement et le reçu
   s'enregistrent tout seuls dès la confirmation d'Orange. */
async function lienOrangeMoney(i) {
  const el = _relances[i];
  if (!el) return;
  const saisie = prompt(`Montant à faire payer à ${el.prenom} ${el.nom} (GNF)\nSolde dû : ${el.reste}`, String(Math.round(el.reste)));
  if (saisie === null) return;
  let lien;
  try { lien = await apiOrangeMoneyLien(el.eleve_id, saisie.replace(/\s/g, '')); }
  catch (e) { return toast(e.message, 'error'); }
  const texte = `${_nomEcoleRelance || 'École'} : pour régler ${fmtMoney(lien.montant)} de la scolarité de ${el.prenom} ${el.nom}, payez avec Orange Money : ${lien.payment_url}`;
  window._omTexte = texte;
  const intl = el.contact ? numeroInternational(el.contact.telephone) : '';
  openModal('🟠 Lien de paiement Orange Money', `
    <div class="alert alert-info" style="font-size:12px">Le lien est valable pour ce montant. Le versement et le reçu seront enregistrés automatiquement dès qu'Orange confirme le paiement.</div>
    <div class="fg"><label>Message à envoyer au parent</label><textarea id="om-texte" rows="4" readonly>${esc(texte)}</textarea></div>
    <div class="modal-footer" style="flex-wrap:wrap;gap:8px">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
      <button class="btn btn-outline" onclick="navigator.clipboard.writeText(window._omTexte).then(()=>toast('Message copié','success'))">Copier</button>
      ${intl ? `<button class="btn btn-ok" onclick="window.open('https://wa.me/${intl}?text='+encodeURIComponent(window._omTexte),'_blank','noopener')">WhatsApp</button>
      <button class="btn btn-primary" onclick="window.location.href='sms:${esc(String(el.contact.telephone).replace(/[^\d+]/g, ''))}?body='+encodeURIComponent(window._omTexte)">SMS</button>` : ''}
    </div>`);
}
window.lienOrangeMoney = lienOrangeMoney;


/* ---------- Orange Money : paiement marchand par QR ----------
   Le parent scanne le QR « Paiement marchand » de l'école avec son application Orange Money, puis
   reçoit un SMS avec un numéro de transaction. On l'enregistre ici : il est unique, le versement
   et le reçu suivent. */
let _omConfig = {}, _omEleves = [];
const OM_ONGLETS = [['encaisser', 'Enregistrer un paiement'], ['valider', 'À valider'], ['qr', 'QR de l\'école'], ['export', 'Rapport mensuel']];

async function modalOrangeMoney(onglet = 'encaisser') {
  openModal('🟠 Orange Money', loadingHtml, { wide: true });
  try {
    [_omConfig, _omEleves] = await Promise.all([apiFetch('/orange-money/config'), apiGetEleves()]);
  } catch (e) { $('#modal-body').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  omAfficher(onglet);
}

function omAfficher(onglet) {
  const gestion = ['admin', 'directeur', 'comptable'].includes(currentUser.role);
  $('#modal-body').innerHTML = `
    <div class="tabs" style="margin-bottom:12px">${OM_ONGLETS.filter(o => gestion || !['valider', 'export'].includes(o[0])).map(o =>
      `<div class="tab ${o[0] === onglet ? 'active' : ''}" onclick="omAfficher('${o[0]}')">${o[1]}</div>`).join('')}</div>
    <div id="om-corps"></div>`;
  ({ encaisser: omEncaisser, valider: omValider, qr: omQr, export: omExport })[onglet]();
}

function omExport() {
  const mois = new Date().toISOString().slice(0, 7);
  $('#om-corps').innerHTML = `
    <div class="alert alert-info" style="font-size:12px">Liste des paiements Orange Money comptabilisés dans le mois (date de validation), avec le total, à remettre à la comptabilité. Les lignes « À vérifier » ont été reçues mais pas encore imputées sur une échéance.</div>
    <div class="form-2"><div class="fg"><label>Mois</label><input id="om-mois" type="month" value="${mois}"></div></div>
    <div id="om-resume" class="text-muted" style="margin:8px 0"></div>
    <button class="btn btn-primary" id="om-dl">⬇ Télécharger (Excel / CSV)</button>`;
  const maj = async () => {
    try {
      const r = await apiFetch('/orange-money/export?format=json&mois=' + $('#om-mois').value);
      $('#om-resume').innerHTML = `<b>${r.nombre}</b> paiement(s) — total <b>${fmtMoney(r.total)}</b>` + (r.a_verifier ? ` — <span style="color:#c0392b">${r.a_verifier} à vérifier</span>` : '');
    } catch (e) { $('#om-resume').textContent = e.message; }
  };
  $('#om-mois').onchange = maj; maj();
  $('#om-dl').onclick = async () => {
    try { const m = $('#om-mois').value; await apiTelechargerFichier('/orange-money/export?mois=' + m, `orange-money-${m}.csv`); }
    catch (e) { toast(e.message, 'error'); }
  };
}

function omEncaisser() {
  const gestion = ['admin', 'directeur', 'comptable'].includes(currentUser.role);
  $('#om-corps').innerHTML = `
    <div class="alert alert-info" style="font-size:12px">Le parent a payé en scannant le QR de l'école. Recopiez le <strong>numéro de transaction</strong>
      du SMS de confirmation Orange Money (ou de votre application Orange Money Marchand). Un même numéro ne peut être enregistré qu'une fois.</div>
    <datalist id="om-eleves">${_omEleves.map(e => `<option value="${esc((e.matricule || '') + ' — ' + e.prenom + ' ' + e.nom)}"></option>`).join('')}</datalist>
    <div class="form-2">
      <div class="fg"><label>Élève</label><input id="om-eleve" list="om-eleves" placeholder="Matricule ou nom…"></div>
      <div class="fg"><label>Montant payé (GNF)</label><input id="om-montant" type="number" min="1000"></div>
      <div class="fg"><label>N° de transaction</label><input id="om-trans" placeholder="ex. MP261020.2345.A12345"></div>
      <div class="fg"><label>Téléphone du payeur (facultatif)</label><input id="om-tel"></div>
    </div>
    ${gestion ? `<label style="display:flex;gap:8px;align-items:center;margin:8px 0"><input type="checkbox" id="om-valider" checked> J'ai vérifié le paiement chez Orange : l'enregistrer tout de suite et émettre le reçu</label>` : '<div class="text-muted" style="font-size:12px;margin:8px 0">Le paiement sera à valider par la comptabilité.</div>'}
    <div class="modal-footer"><button class="btn btn-outline" onclick="closeModal()">Fermer</button>
      <button class="btn btn-primary" onclick="omEnregistrer()">Enregistrer</button></div>`;
}

async function omEnregistrer() {
  const saisie = $('#om-eleve').value.trim();
  const eleve = _omEleves.find(e => ((e.matricule || '') + ' — ' + e.prenom + ' ' + e.nom) === saisie);
  if (!eleve) return toast('Choisissez un élève dans la liste proposée', 'error');
  try {
    const r = await apiFetch('/orange-money/declarations', { method: 'POST', body: {
      eleve_id: eleve.id, montant: $('#om-montant').value, transaction_id: $('#om-trans').value,
      telephone: $('#om-tel').value, valider: $('#om-valider') ? $('#om-valider').checked : false } });
    toast(r.statut === 'valide' ? `Paiement enregistré — reçu ${r.numero_recu}`
      : r.statut === 'a_verifier' ? 'Paiement reçu mais aucun solde à imputer : à vérifier' : 'Enregistré : en attente de validation', 'success');
    closeModal();
    if (typeof pagePaiements === 'function') pagePaiements();
  } catch (e) { toast(e.message, 'error'); }
}

async function omValider() {
  $('#om-corps').innerHTML = loadingHtml;
  let liste;
  try { liste = await apiFetch('/orange-money/declarations?statut=a_valider'); }
  catch (e) { $('#om-corps').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  $('#om-corps').innerHTML = `<div class="alert alert-info" style="font-size:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span>Gagnez du temps : importez le relevé d'opérations téléchargé depuis Orange Money Marchand (Excel ou CSV). Un paiement est confirmé si son numéro de transaction <strong>et</strong> son montant figurent sur la même ligne.</span>
      <label class="btn btn-outline btn-sm" style="cursor:pointer">📎 Rapprocher avec le relevé<input type="file" id="om-releve" accept=".csv,.xlsx" style="display:none"></label></div>
    <div id="om-rapprochement"></div>` + (liste.length ? `<div class="tbl-wrap"><table><thead><tr><th>Date</th><th>Élève</th><th>Montant</th><th>N° transaction</th><th></th></tr></thead><tbody>
    ${liste.map(d => `<tr><td>${fmtDate(String(d.created_at).slice(0, 10))}</td><td>${esc(d.prenom)} ${esc(d.nom)}<br><span class="text-muted" style="font-size:11px">${esc(d.classe || '')}</span></td>
      <td class="mono">${fmtMoney(d.montant)}</td><td class="mono">${esc(d.transaction_id)}</td>
      <td><button class="btn btn-ok btn-xs" onclick="omDecider('${escJs(d.id)}','valider')">✔ Valider</button>
          <button class="btn btn-danger btn-xs" onclick="omDecider('${escJs(d.id)}','rejeter')">✖ Rejeter</button></td></tr>`).join('')}
    </tbody></table></div>` : emptyHtml('✅', 'Aucun paiement en attente de validation'));
  $('#om-releve').addEventListener('change', e => omRapprocher(e.target.files[0], false));
}

const OM_ETATS = { confirme: ['✅ Confirmé', 'bdg-ok'], valide: ['✅ Validé', 'bdg-ok'], a_verifier: ['⚠ À vérifier', 'bdg-warn'],
                   montant_different: ['⚠ Montant différent', 'bdg-warn'], introuvable: ['❌ Introuvable', 'bdg-err'] };
let _omReleve = null;
async function omRapprocher(fichier, appliquer) {
  if (!fichier) return;
  _omReleve = fichier;
  const fd = new FormData(); fd.append('fichier', fichier); fd.append('appliquer', appliquer ? '1' : '0');
  let r;
  try { r = await apiUpload('/orange-money/declarations/rapprocher', fd); } catch (e) { return toast(e.message, 'error'); }
  const c = r.compte;
  $('#om-rapprochement').innerHTML = `
    <div style="margin:10px 0"><strong>${appliquer ? `${r.valides} paiement(s) validé(s)` : `${c.confirme} confirmé(s) sur le relevé`}</strong>
      · ${c.montant_different} montant différent · ${c.introuvable} introuvable(s)
      ${!appliquer && c.confirme ? `<button class="btn btn-ok btn-sm" style="margin-left:10px" onclick="omRapprocher(_omReleve, true)">✔ Valider les ${c.confirme} confirmés</button>` : ''}</div>
    <div class="tbl-wrap"><table><thead><tr><th>Élève</th><th>Montant</th><th>N° transaction</th><th>Résultat</th></tr></thead><tbody>
    ${r.resultat.map(x => `<tr><td>${esc(x.eleve)}</td><td class="mono">${fmtMoney(x.montant)}</td><td class="mono">${esc(x.transaction_id)}</td>
      <td><span class="badge ${OM_ETATS[x.etat][1]}">${OM_ETATS[x.etat][0]}</span>${x.etat === 'montant_different' && x.montants_releve.length ? ` <span class="text-muted" style="font-size:11px">relevé : ${x.montants_releve.map(fmtMoney).join(', ')}</span>` : ''}</td></tr>`).join('')}
    </tbody></table></div>`;
}
window.omRapprocher = omRapprocher;

async function omDecider(id, action) {
  try {
    if (action === 'valider') {
      const r = await apiFetch(`/orange-money/declarations/${id}/valider`, { method: 'POST' });
      toast(`Validé — reçu ${r.numero_recu}`, 'success');
    } else {
      const motif = prompt('Motif du rejet (ex. transaction introuvable chez Orange) :');
      if (!motif) return;
      await apiFetch(`/orange-money/declarations/${id}/rejeter`, { method: 'POST', body: { motif } });
      toast('Rejeté', 'success');
    }
    omValider();
  } catch (e) { toast(e.message, 'error'); }
}

function omQr() {
  const admin = ['admin', 'directeur'].includes(currentUser.role);
  const c = _omConfig;
  $('#om-corps').innerHTML = `
    <div style="text-align:center">
      ${c.qr_url ? `<img src="${esc(c.qr_url)}" style="max-width:320px;max-height:320px;border:1px solid #E5E7EB;border-radius:12px"><br>` : '<div class="text-muted" style="margin:20px 0">Aucun QR enregistré</div>'}
      <div style="margin:10px 0"><strong>${esc(c.nom || '')}</strong>${c.code ? `<br>Code marchand : <span class="mono">${esc(c.code)}</span>` : ''}</div>
      <div class="text-muted" style="font-size:13px;white-space:pre-line">${esc(c.instructions || '')}</div>
      <div class="alert alert-info" style="font-size:12px;margin-top:12px">Lien à donner aux parents (il saisit nom, prénom et matricule puis paie) : <strong>${esc(location.origin)}/payer</strong></div>
      ${c.qr_url ? `<button class="btn btn-outline btn-sm" style="margin-top:10px" onclick="omImprimerQr()">🖨 Imprimer l'affiche</button>` : ''}
    </div>
    ${admin ? `<hr><div class="form-section-title">Réglages (administrateur)</div>
      <div class="form-2">
        <div class="fg"><label>Nom du compte marchand</label><input id="omc-nom" value="${esc(c.nom || '')}"></div>
        <div class="fg"><label>Code marchand (facultatif)</label><input id="omc-code" value="${esc(c.code || '')}"></div>
      </div>
      <div class="fg"><label>Instructions affichées sur l'affiche et dans les relances</label>
        <textarea id="omc-instr" rows="3" placeholder="Ouvrez Orange Money → Paiement marchand → Scanner le code QR. Gardez le SMS de confirmation.">${esc(c.instructions || '')}</textarea></div>
      <div class="flex gap-2" style="flex-wrap:wrap">
        <label class="btn btn-outline btn-sm" style="cursor:pointer">📷 Importer le QR (capture « Ma carte QR »)<input type="file" id="omc-fichier" accept="image/*" style="display:none"></label>
        <button class="btn btn-primary btn-sm" onclick="omSauverConfig()">Enregistrer</button>
      </div>` : ''}`;
  const f = $('#omc-fichier');
  if (f) f.addEventListener('change', async e => {
    if (!e.target.files[0]) return;
    const fd = new FormData(); fd.append('qr', e.target.files[0]);
    try { const r = await apiUpload('/orange-money/qr', fd); _omConfig.qr_url = r.qr_url; toast('QR enregistré', 'success'); omQr(); }
    catch (err) { toast(err.message, 'error'); }
  });
}

async function omSauverConfig() {
  try {
    _omConfig = await apiFetch('/orange-money/config', { method: 'PUT', body: { nom: $('#omc-nom').value, code: $('#omc-code').value, instructions: $('#omc-instr').value } });
    _omConfigRelance = null;
    toast('Enregistré', 'success'); omQr();
  } catch (e) { toast(e.message, 'error'); }
}

function omImprimerQr() {
  const c = _omConfig;
  const w = window.open('', '_blank');
  if (!w) return toast('Autorisez les fenêtres pour imprimer', 'error');
  w.document.write(`<!doctype html><meta charset="utf-8"><title>Payer par Orange Money</title><body style="font-family:Arial,sans-serif;text-align:center;padding:30px">
    <h1 style="color:#ff7900">Payez la scolarité avec Orange Money</h1><h2>${esc(c.nom || '')}</h2>
    <img src="${esc(c.qr_url)}" style="width:360px"><p style="font-size:20px">${c.code ? 'Code marchand : <b>' + esc(c.code) + '</b>' : ''}</p>
    <p style="font-size:18px;white-space:pre-line">${esc(c.instructions || 'Orange Money → Paiement marchand → Scanner le code QR.\nGardez le SMS de confirmation et présentez-le à l\'école.')}</p>
    </body>`);
  w.document.close();
  setTimeout(() => w.print(), 400);
}
window.modalOrangeMoney = modalOrangeMoney; window.omAfficher = omAfficher; window.omEnregistrer = omEnregistrer;
window.omDecider = omDecider; window.omSauverConfig = omSauverConfig; window.omImprimerQr = omImprimerQr;
