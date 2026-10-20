/* ===================== POINTAGE (biométrique / badge) ===================== */
/* Les empreintes et visages restent dans l'appareil : l'application ne reçoit que
   « le numéro N est passé à telle heure ». */
let _ptOnglet = 'jour';
let _ptRapport = null;

const PT_STATUT = {
  present:        ['bdg-ok',   'Présent'],
  retard:         ['bdg-warn', 'En retard'],
  absent:         ['bdg-err',  'Absent'],
  absent_signale: ['bdg-gray', 'Absence signalée'],
  non_pointe:     ['bdg-gray', 'Pas encore pointé'],
};

async function pagePointage() {
  const gestion = ['admin', 'directeur'].includes(currentUser.role);
  $('#content').innerHTML = `
    <div class="tabs" id="pt-tabs">
      <div class="tab" data-onglet="jour" onclick="setPtOnglet('jour')">📅 Journée</div>
      <div class="tab" data-onglet="mois" onclick="setPtOnglet('mois')">📊 Mois</div>
      ${gestion ? `<div class="tab" data-onglet="numeros" onclick="setPtOnglet('numeros')">🔢 Numéros</div>
      <div class="tab" data-onglet="appareils" onclick="setPtOnglet('appareils')">🪪 Appareils</div>
      <div class="tab" data-onglet="reglages" onclick="setPtOnglet('reglages')">⚙ Réglages</div>` : ''}
    </div>
    <div id="pt-corps"></div>`;
  setPtOnglet(gestion ? _ptOnglet : 'jour');
}

function setPtOnglet(nom) {
  _ptOnglet = nom;
  $$('#pt-tabs .tab').forEach(t => t.classList.toggle('active', t.dataset.onglet === nom));
  ({ jour: ptJour, mois: ptMois, numeros: ptNumeros, appareils: ptAppareils, reglages: ptReglages })[nom]();
}

/* ---------- Journée ---------- */
async function ptJour() {
  const gestion = ['admin', 'directeur'].includes(currentUser.role);
  $('#pt-corps').innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">📅 Présences du jour</span>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="ptModalManuel()">✍ Saisie manuelle</button>
          ${gestion ? `<button class="btn btn-primary btn-sm" onclick="ptCloturer()" title="Crée une absence pour chaque élève qui n'a pas pointé">🔒 Clôturer la journée</button>` : ''}
        </div>
      </div>
      <div class="filters">
        <div class="fg"><label>Date</label><input type="date" id="pt-date" value="${today()}" max="${today()}"></div>
        <div class="fg"><label>Classe</label><select id="pt-classe"><option value="">Toutes</option></select></div>
        <div class="fg"><label>Afficher</label><select id="pt-filtre">
          <option value="">Tous</option><option value="present">Présents</option><option value="retard">En retard</option>
          <option value="absent">Absents</option><option value="non_pointe">Pas encore pointés</option></select></div>
        <button class="btn btn-outline btn-sm" onclick="ptCharger()">🔄 Actualiser</button>
      </div>
      <div id="pt-resume" class="mb-4"></div>
      <div id="pt-eleves"></div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="card-header"><span class="card-title">👨‍🏫 Enseignants et personnel</span></div>
      <div id="pt-personnel"></div>
    </div>`;
  ['#pt-date', '#pt-classe', '#pt-filtre'].forEach(s => $(s).addEventListener('change', () => ptCharger(s === '#pt-filtre' ? false : true)));
  await ptCharger(true);
}

async function ptCharger(rechargerServeur = true) {
  try {
    if (rechargerServeur || !_ptRapport) {
      const qs = [`date=${$('#pt-date').value}`];
      if ($('#pt-classe').value) qs.push(`classe=${encodeURIComponent($('#pt-classe').value)}`);
      _ptRapport = await apiPointageJour(qs.join('&'));
      // La liste des classes se remplit une seule fois, à partir des élèves reçus sans filtre.
      const sel = $('#pt-classe');
      if (sel.options.length === 1) {
        const tous = await apiPointageJour(`date=${_ptRapport.date}`);
        [...new Set(tous.eleves.map(e => e.classe).filter(Boolean))].sort()
          .forEach(c => sel.insertAdjacentHTML('beforeend', `<option>${esc(c)}</option>`));
      }
    }
  } catch (e) { $('#pt-corps').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  const r = _ptRapport;
  const t = r.resume;
  const tuile = (lib, val, cls = '') => `<div class="stat"><div class="stat-label">${lib}</div><div class="stat-val ${cls}" style="font-size:18px">${val}</div></div>`;
  $('#pt-resume').innerHTML = `
    <div class="stats-grid" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr))">
      ${tuile('Élèves présents', t.eleves.present, 'text-ok')}
      ${tuile('Retards', t.eleves.retard, 'text-warn')}
      ${tuile('Absents', t.eleves.absent, 'text-err')}
      ${tuile('Pas encore pointés', t.eleves.non_pointe)}
      ${tuile('Personnel présent', t.personnel.present + t.personnel.retard + ' / ' + t.personnel.total)}
    </div>
    ${r.nb_passages === 0 ? `<div class="alert alert-warn" style="margin-top:10px">Aucun passage reçu ce jour-là. Si l'appareil est installé, vérifiez qu'il est allumé et connecté (onglet Appareils).</div>` : ''}`;

  const filtre = $('#pt-filtre').value;
  const eleves = r.eleves.filter(e => !filtre || e.statut === filtre);
  $('#pt-eleves').innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr><th>Élève</th><th>Classe</th><th>Arrivée</th><th>Départ</th><th>Statut</th><th>Parent</th></tr></thead>
    <tbody>${eleves.length ? eleves.map(e => `<tr>
      <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong><br><span class="text-muted" style="font-size:11px">${esc(e.matricule || '')}</span></td>
      <td>${esc(e.classe || '—')}</td>
      <td class="mono">${esc(e.arrivee || '—')}</td><td class="mono">${esc(e.depart || '—')}</td>
      <td>${ptBadge(e.statut)}${e.statut === 'absent' && e.justifie ? ' <span class="text-muted" style="font-size:11px">(justifiée)</span>' : ''}</td>
      <td>${e.absence_id && e.contact
        ? `<button class="btn btn-outline btn-xs" title="${e.parent_prevenu_le ? 'Parent déjà prévenu' : 'Prévenir le parent'}" onclick="modalPrevenirParent('${escJs(e.absence_id)}')">${e.parent_prevenu_le ? '✅' : '📲'} Prévenir</button>`
        : (e.absence_id ? '<span class="text-muted" style="font-size:11px">Pas de numéro</span>' : '')}</td>
    </tr>`).join('') : `<tr><td colspan="6">${emptyHtml('🪪', 'Aucun élève pour ce filtre')}</td></tr>`}</tbody></table></div>`;
  // « Prévenir » réutilise la fenêtre de la page Absences, qui lit cette liste.
  _absAffichees = r.eleves.filter(e => e.absence_id).map(e => ({
    id: e.absence_id, type: e.absence_type, date_abs: r.date, nom: e.nom, prenom: e.prenom, classe: e.classe,
    duree: e.duree, motif: e.motif, contact: e.contact, parent_prevenu_le: e.parent_prevenu_le }));

  const pers = r.personnel.filter(p => !filtre || p.statut === filtre || (filtre === 'absent' && p.statut === 'absent_signale'));
  $('#pt-personnel').innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr><th>Nom</th><th>Poste</th><th>Arrivée</th><th>Départ</th><th>Statut</th></tr></thead>
    <tbody>${pers.length ? pers.map(p => `<tr>
      <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong></td><td>${esc(p.poste || '—')}</td>
      <td class="mono">${esc(p.arrivee || '—')}</td><td class="mono">${esc(p.depart || '—')}</td>
      <td>${ptBadge(p.statut)}</td></tr>`).join('') : `<tr><td colspan="5">${emptyHtml('👨‍🏫', 'Aucune personne pour ce filtre')}</td></tr>`}</tbody></table></div>`;
}

function ptBadge(statut) {
  const [cls, lib] = PT_STATUT[statut] || ['bdg-gray', statut];
  return `<span class="badge ${cls}">${lib}</span>`;
}

async function ptCloturer() {
  const jour = $('#pt-date').value;
  if (!confirm(`Clôturer la journée du ${fmtDate(jour)} ?\n\nChaque élève qui n'a pas pointé recevra une absence « non justifiée » (modifiable ensuite dans Absences).`)) return;
  try {
    const res = await apiPointageCloture({ date: jour });
    toast(`${res.absences_creees} absence(s) créée(s)`, 'success');
    ptCharger(true);
  } catch (e) { toast(e.message, 'error'); }
}

async function ptModalManuel() {
  const r = _ptRapport;
  if (!r) return;
  const jour = $('#pt-date').value || today();
  openModal('✍ Saisie manuelle d\'un passage', `
    <form id="f-ptman" style="display:flex;flex-direction:column;gap:12px">
      <div class="alert alert-info" style="font-size:12px">À utiliser si l'appareil est en panne ou si un badge est oublié. Le motif est obligatoire et la saisie est tracée.</div>
      <div class="fg"><label>Qui ?</label><select name="qui" required>
        <optgroup label="Personnel">${r.personnel.map(p => `<option value="personnel|${esc(p.id)}">${esc(p.prenom)} ${esc(p.nom)}</option>`).join('')}</optgroup>
        <optgroup label="Élèves">${r.eleves.map(e => `<option value="eleve|${esc(e.id)}">${esc(e.prenom)} ${esc(e.nom)} (${esc(e.classe || '')})</option>`).join('')}</optgroup>
      </select></div>
      <div class="fg"><label>Date et heure d'arrivée</label><input type="datetime-local" name="horodatage" required value="${jour}T07:45"></div>
      <div class="fg"><label>Motif*</label><input name="motif" required minlength="5" placeholder="Ex : pointeur en panne, badge oublié…"></div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button></div>
    </form>`, { narrow: true });
  $('#f-ptman').onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    const [type, id] = f.get('qui').split('|');
    try {
      await apiPointageManuel({ personne_type: type, personne_id: id, horodatage: f.get('horodatage'), motif: f.get('motif') });
      toast('Passage enregistré', 'success'); closeModal(); ptCharger(true);
    } catch (err) { toast(err.message, 'error'); }
  };
}

/* ---------- Mois : ponctualité et assiduité ---------- */
let _ptMois = null;
async function ptMois() {
  const moisCourant = today().slice(0, 7);
  $('#pt-corps').innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">📊 Ponctualité du mois</span>
        <div class="card-actions"><button class="btn btn-outline btn-sm" onclick="ptExporterMois()">⬇ Télécharger (Excel/CSV)</button></div></div>
      <div class="filters">
        <div class="fg"><label>Mois</label><input type="month" id="pt-mois" value="${moisCourant}" max="${moisCourant}"></div>
        <div class="fg"><label>Qui ?</label><select id="pt-mois-type"><option value="eleve">Élèves</option><option value="personnel">Enseignants et personnel</option></select></div>
        <div class="fg" id="pt-mois-classe-wrap"><label>Classe</label><input id="pt-mois-classe" placeholder="Toutes (ex : CE2)"></div>
      </div>
      <div id="pt-mois-resume" class="text-muted" style="font-size:12px;margin:0 16px 8px"></div>
      <div id="pt-mois-corps"></div>
    </div>`;
  $('#pt-mois').addEventListener('change', ptChargerMois);
  $('#pt-mois-classe').addEventListener('change', ptChargerMois);
  $('#pt-mois-type').addEventListener('change', ptDessinerMois);
  ptChargerMois();
}

async function ptChargerMois() {
  $('#pt-mois-corps').innerHTML = loadingHtml;
  try {
    const classe = $('#pt-mois-classe').value.trim();
    _ptMois = await apiPointageMensuel(`mois=${$('#pt-mois').value}${classe ? '&classe=' + encodeURIComponent(classe) : ''}`);
  } catch (e) { $('#pt-mois-corps').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  ptDessinerMois();
}

function ptDessinerMois() {
  if (!_ptMois) return;
  const eleve = $('#pt-mois-type').value === 'eleve';
  $('#pt-mois-classe-wrap').style.display = eleve ? '' : 'none';
  const lignes = eleve ? _ptMois.eleves : _ptMois.personnel;
  const jours = eleve ? _ptMois.jours_classe : _ptMois.jours_service;
  $('#pt-mois-resume').textContent = jours
    ? `${jours} jour(s) ${eleve ? 'de classe' : 'de service'} ce mois-ci (jours où au moins une personne a pointé).`
    : 'Aucun passage reçu ce mois-ci.';
  const taux = t => t === null ? '—' : `<span class="${t >= 90 ? 'text-ok' : t >= 75 ? 'text-warn' : 'text-err'}">${t} %</span>`;
  $('#pt-mois-corps').innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr><th>${eleve ? 'Élève' : 'Nom'}</th><th>${eleve ? 'Classe' : 'Poste'}</th><th class="text-right">Présences</th>
      <th class="text-right">Retards</th><th class="text-right">Absences</th>${eleve ? '<th class="text-right">dont justifiées</th>' : '<th class="text-right">Heures de présence</th>'}
      <th class="text-right">Taux</th></tr></thead>
    <tbody>${lignes.length ? lignes.map(l => `<tr>
      <td><strong>${esc(l.prenom)} ${esc(l.nom)}</strong></td><td>${esc((eleve ? l.classe : l.poste) || '—')}</td>
      <td class="mono text-right">${l.presents}</td><td class="mono text-right">${l.retards}</td><td class="mono text-right">${l.absents}</td>
      <td class="mono text-right">${eleve ? l.absences_justifiees : l.heures_presence}</td>
      <td class="mono text-right">${taux(l.taux_presence)}</td></tr>`).join('')
      : `<tr><td colspan="7">${emptyHtml('📊', 'Aucune donnée')}</td></tr>`}</tbody></table></div>`;
}

function ptExporterMois() {
  if (!_ptMois) return;
  const eleve = $('#pt-mois-type').value === 'eleve';
  const lignes = eleve ? _ptMois.eleves : _ptMois.personnel;
  const entete = eleve ? ['Nom', 'Prénom', 'Classe', 'Matricule', 'Présences', 'Retards', 'Absences', 'Absences justifiées', 'Taux de présence (%)']
                       : ['Nom', 'Prénom', 'Poste', 'Présences', 'Retards', 'Absences', 'Heures de présence', 'Taux de présence (%)'];
  const cellule = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const corps = lignes.map(l => (eleve
    ? [l.nom, l.prenom, l.classe, l.matricule, l.presents, l.retards, l.absents, l.absences_justifiees, l.taux_presence]
    : [l.nom, l.prenom, l.poste, l.presents, l.retards, l.absents, l.heures_presence, l.taux_presence]).map(cellule).join(';'));
  // BOM + point-virgule : s'ouvre correctement dans Excel en français (accents compris).
  const blob = new Blob(['﻿' + [entete.map(cellule).join(';'), ...corps].join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const lien = document.createElement('a');
  lien.href = URL.createObjectURL(blob);
  lien.download = `pointage-${_ptMois.mois}-${eleve ? 'eleves' : 'personnel'}.csv`;
  document.body.appendChild(lien); lien.click(); lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 1000);
}

/* ---------- Numéros ---------- */
let _ptTypeNumeros = 'eleve';
async function ptNumeros() {
  $('#pt-corps').innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">🔢 Numéros de pointage</span>
        <div class="card-actions"><button class="btn btn-primary btn-sm" onclick="ptCodesAuto()">⚡ Attribuer les numéros manquants</button></div></div>
      <div class="alert alert-info" style="font-size:12px;margin:0 16px 10px">Chaque personne a un numéro. C'est ce même numéro que vous enregistrez avec son empreinte, son visage ou son badge dans l'appareil.</div>
      <div class="filters">
        <div class="fg"><label>Qui ?</label><select id="pt-type"><option value="eleve">Élèves</option><option value="personnel">Enseignants et personnel</option></select></div>
        <div class="fg" id="pt-classe-wrap"><label>Classe</label><input id="pt-nclasse" placeholder="Toutes (ex : CE2)"></div>
        <div class="fg grow"><label>Recherche</label><input id="pt-nq" placeholder="Nom, prénom…"></div>
      </div>
      <div id="pt-liste-codes"></div>
    </div>`;
  $('#pt-type').value = _ptTypeNumeros;
  $('#pt-type').addEventListener('change', e => { _ptTypeNumeros = e.target.value; ptListeCodes(); });
  $('#pt-nclasse').addEventListener('change', ptListeCodes);
  $('#pt-nq').addEventListener('input', ptFiltrerCodes);
  ptListeCodes();
}

let _ptPersonnes = [];
async function ptListeCodes() {
  const type = $('#pt-type').value;
  $('#pt-classe-wrap').style.display = type === 'eleve' ? '' : 'none';
  $('#pt-liste-codes').innerHTML = loadingHtml;
  try {
    const classe = type === 'eleve' ? $('#pt-nclasse').value.trim() : '';
    _ptPersonnes = await apiPointagePersonnes(`type=${type}${classe ? '&classe=' + encodeURIComponent(classe) : ''}`);
  } catch (e) { $('#pt-liste-codes').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  ptFiltrerCodes();
}

function ptFiltrerCodes() {
  const q = ($('#pt-nq').value || '').toLowerCase().trim();
  const type = $('#pt-type').value;
  const liste = _ptPersonnes.filter(p => !q || `${p.nom} ${p.prenom}`.toLowerCase().includes(q));
  const sans = _ptPersonnes.filter(p => !p.code).length;
  $('#pt-liste-codes').innerHTML = `
    <div class="text-muted" style="font-size:12px;margin:0 16px 6px">${_ptPersonnes.length} personne(s) · ${sans} sans numéro</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Nom</th><th>${type === 'eleve' ? 'Classe' : 'Poste'}</th><th style="width:160px">Numéro</th></tr></thead>
      <tbody>${liste.length ? liste.map(p => `<tr>
        <td><strong>${esc(p.prenom)} ${esc(p.nom)}</strong></td><td>${esc(p.detail || '—')}</td>
        <td><input class="mono" style="width:110px" value="${esc(p.code || '')}" placeholder="—"
             onchange="ptEnregistrerCode('${escJs(type)}','${escJs(p.id)}',this)"></td></tr>`).join('')
        : `<tr><td colspan="3">${emptyHtml('🔢', 'Aucune personne trouvée')}</td></tr>`}</tbody></table></div>`;
}

async function ptEnregistrerCode(type, id, champ) {
  const ancien = (_ptPersonnes.find(p => p.id === id) || {}).code || '';
  try {
    const res = await apiPointageDefinirCode({ personne_type: type, personne_id: id, code: champ.value.trim() });
    const p = _ptPersonnes.find(x => x.id === id);
    if (p) p.code = res.code;
    champ.value = res.code || '';
    toast(res.code ? `Numéro ${res.code} enregistré` : 'Numéro retiré', 'success');
  } catch (e) { champ.value = ancien; toast(e.message, 'error'); }
}

async function ptCodesAuto() {
  const type = $('#pt-type').value;
  if (!confirm(`Attribuer un numéro libre à toutes les personnes (${type === 'eleve' ? 'élèves' : 'personnel'}) qui n'en ont pas encore ?`)) return;
  try {
    const res = await apiPointageCodesAuto(type);
    toast(`${res.attribues} numéro(s) attribué(s)`, 'success');
    ptListeCodes();
  } catch (e) { toast(e.message, 'error'); }
}

/* ---------- Appareils ---------- */
async function ptAppareils() {
  $('#pt-corps').innerHTML = loadingHtml;
  let appareils, passages;
  try { [appareils, passages] = await Promise.all([apiPointageAppareils(), apiPointagePassages(`date=${today()}`)]); }
  catch (e) { $('#pt-corps').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  $('#pt-corps').innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">🪪 Appareils de pointage</span>
        <div class="card-actions"><button class="btn btn-primary btn-sm" onclick="ptModalAppareil()">+ Ajouter un appareil</button></div></div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Nom</th><th>N° de série</th><th>Dernier message reçu</th><th>État</th><th>Actions</th></tr></thead>
        <tbody>${appareils.length ? appareils.map(a => `<tr>
          <td><strong>${esc(a.nom)}</strong></td><td class="mono">${esc(a.numero_serie || '—')}</td>
          <td>${a.derniere_activite ? esc(a.derniere_activite) : '<span class="text-muted">Jamais</span>'}</td>
          <td><span class="badge ${a.actif ? 'bdg-ok' : 'bdg-gray'}">${a.actif ? 'Actif' : 'Désactivé'}</span></td>
          <td><div class="td-actions">
            <button class="btn btn-outline btn-xs" onclick="ptBasculerAppareil('${escJs(a.id)}',${a.actif ? 0 : 1})">${a.actif ? 'Désactiver' : 'Réactiver'}</button>
            <button class="btn btn-outline btn-xs" onclick="ptNouvelleCle('${escJs(a.id)}','${escJs(a.nom)}')">🔑 Nouvelle clé</button>
            <button class="btn btn-danger btn-xs" onclick="ptSupprimerAppareil('${escJs(a.id)}','${escJs(a.nom)}')">🗑</button>
          </div></td></tr>`).join('') : `<tr><td colspan="5">${emptyHtml('🪪', 'Aucun appareil enregistré')}</td></tr>`}</tbody></table></div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="card-header"><span class="card-title">🧾 Passages reçus aujourd'hui</span></div>
      <div class="text-muted" style="font-size:12px;margin:0 16px 6px">Un numéro « inconnu » signale un numéro mal saisi dans l'appareil ou pas encore associé à une personne (onglet Numéros).</div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Heure</th><th>Numéro</th><th>Personne</th><th>Source</th></tr></thead>
        <tbody>${passages.length ? passages.map(p => `<tr>
          <td class="mono">${esc(p.horodatage.slice(11, 19))}</td><td class="mono">${esc(p.source === 'manuel' ? '—' : p.code)}</td>
          <td>${p.personne ? esc(p.personne) : '<span class="badge bdg-warn">Numéro inconnu</span>'}</td>
          <td>${p.source === 'manuel' ? `Saisie manuelle <span class="text-muted" style="font-size:11px">(${esc(p.motif || '')})</span>` : esc(p.appareil || '—')}</td></tr>`).join('')
          : `<tr><td colspan="4">${emptyHtml('🧾', "Aucun passage aujourd'hui")}</td></tr>`}</tbody></table></div>
    </div>`;
}

function ptInstructionsAppareil(cle, serie) {
  const adresse = location.origin;
  return `
    <div class="alert alert-warn"><strong>Notez cette clé maintenant</strong> : elle ne sera plus jamais affichée.<br>
      <input readonly class="mono" style="width:100%;margin-top:6px" value="${esc(cle)}" onclick="this.select()"></div>
    <p style="margin:8px 0 4px"><strong>Appareil ZKTeco (envoi direct)</strong>${serie ? '' : ' — renseignez son numéro de série pour l\'utiliser'} :</p>
    <p class="text-muted" style="font-size:12px;margin:0 0 8px">Dans le menu de l'appareil (Communication → Serveur cloud / ADMS), saisissez le serveur
      <span class="mono">${esc(location.hostname)}</span>, le port <span class="mono">${esc(location.port || (location.protocol === 'https:' ? '443' : '80'))}</span>${location.protocol === 'https:' ? ' avec HTTPS activé' : ''}.
      Le menu exact varie selon le modèle.</p>
    <p style="margin:8px 0 4px"><strong>Programme relais ou autre appareil</strong> :</p>
    <p class="text-muted" style="font-size:12px;margin:0">Envoyer en POST vers <span class="mono">${esc(adresse)}/api/pointage/passages</span> avec l'en-tête
      <span class="mono">X-Cle-Appareil: (la clé ci-dessus)</span> et le corps
      <span class="mono">{"passages":[{"code":"42","horodatage":"2026-10-20 07:52:10"}]}</span>.</p>`;
}

function ptModalAppareil() {
  openModal('Ajouter un appareil', `
    <form id="f-ptapp" style="display:flex;flex-direction:column;gap:12px">
      <div class="fg"><label>Nom*</label><input name="nom" required placeholder="Ex : Portail principal"></div>
      <div class="fg"><label>Numéro de série (appareils ZKTeco)</label><input name="numero_serie" placeholder="Visible dans le menu « Info » de l'appareil"></div>
      <div class="modal-footer"><button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Créer</button></div>
    </form>`, { narrow: true });
  $('#f-ptapp').onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const res = await apiPointageCreerAppareil({ nom: f.get('nom'), numero_serie: f.get('numero_serie') });
      openModal('Appareil créé', ptInstructionsAppareil(res.cle, res.numero_serie) +
        `<div class="modal-footer"><button class="btn btn-primary" onclick="closeModal();ptAppareils()">J'ai noté la clé</button></div>`);
    } catch (err) { toast(err.message, 'error'); }
  };
}

async function ptBasculerAppareil(id, actif) {
  try { await apiPointageModifierAppareil(id, { actif: !!actif }); ptAppareils(); } catch (e) { toast(e.message, 'error'); }
}

async function ptNouvelleCle(id, nom) {
  if (!confirm(`Générer une nouvelle clé pour « ${nom} » ?\nL'ancienne clé cessera de fonctionner immédiatement.`)) return;
  try {
    const res = await apiPointageModifierAppareil(id, { regenerer_cle: true });
    openModal('Nouvelle clé', ptInstructionsAppareil(res.cle, true) + `<div class="modal-footer"><button class="btn btn-primary" onclick="closeModal()">J'ai noté la clé</button></div>`);
  } catch (e) { toast(e.message, 'error'); }
}

async function ptSupprimerAppareil(id, nom) {
  if (!confirm(`Supprimer l'appareil « ${nom} » ? Les passages déjà reçus sont conservés.`)) return;
  try { await apiPointageSupprimerAppareil(id); ptAppareils(); } catch (e) { toast(e.message, 'error'); }
}

/* ---------- Réglages ---------- */
async function ptReglages() {
  $('#pt-corps').innerHTML = loadingHtml;
  let p;
  try { p = await apiPointageParametres(); } catch (e) { $('#pt-corps').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; return; }
  $('#pt-corps').innerHTML = `
    <div class="card"><div class="card-header"><span class="card-title">⚙ Horaires de pointage</span></div>
      <form id="f-ptreg" style="padding:0 16px 16px;display:flex;flex-direction:column;gap:12px;max-width:520px">
        <div class="alert alert-info" style="font-size:12px">Une arrivée après « heure de début + tolérance » compte comme un retard. Pour les élèves, un retard est enregistré automatiquement dans Absences.</div>
        <div class="fg"><label>Élèves — début des cours</label><input type="time" name="pointage_eleves_heure_debut" value="${esc(p.pointage_eleves_heure_debut)}" required></div>
        <div class="fg"><label>Élèves — tolérance (minutes)</label><input type="number" min="0" max="240" name="pointage_eleves_tolerance_min" value="${esc(p.pointage_eleves_tolerance_min)}" required></div>
        <div class="fg"><label>Personnel — début de service</label><input type="time" name="pointage_personnel_heure_debut" value="${esc(p.pointage_personnel_heure_debut)}" required></div>
        <div class="fg"><label>Personnel — tolérance (minutes)</label><input type="number" min="0" max="240" name="pointage_personnel_tolerance_min" value="${esc(p.pointage_personnel_tolerance_min)}" required></div>
        <div><button class="btn btn-primary" type="submit">Enregistrer</button></div>
      </form></div>`;
  $('#f-ptreg').onsubmit = async e => {
    e.preventDefault();
    try { await apiPointageSauverParametres(Object.fromEntries(new FormData(e.target))); toast('Horaires enregistrés', 'success'); }
    catch (err) { toast(err.message, 'error'); }
  };
}

Object.assign(window, { ptExporterMois, pagePointage, setPtOnglet, ptCharger, ptCloturer, ptModalManuel, ptCodesAuto, ptEnregistrerCode,
  ptModalAppareil, ptBasculerAppareil, ptNouvelleCle, ptSupprimerAppareil });
