/* ===================== DASHBOARD ===================== */
async function pageDashboard() {
  $('#content').innerHTML = loadingHtml;
  try {
    const d = await apiGetDashboard();
    const {
      stats, finances_mois, eleves_classe, dernieres_transactions, prochains_devoirs,
      dernieres_annonces, personnel_absent_jour, recouvrement_par_classe,
      recettes_par_categorie, eleves_impayes_liste,
    } = d;

    // Un enseignant ne doit jamais voir la situation financière de l'école (demande explicite)
    const peutVoirFinances = currentUser.role !== 'enseignant';

    // Sous-titre topbar : année scolaire + bouton Actualiser
    const s = await apiGetSettings().catch(() => ({}));
    $('#pg-sub').innerHTML = `${esc(s.annee_scolaire||'')} <button class="btn btn-outline btn-xs" style="margin-left:8px" onclick="pageDashboard()">🔄 Actualiser</button>`;

    $('#content').innerHTML = `
    ${personnel_absent_jour && personnel_absent_jour.length ? `
    <div class="alert alert-warn mb-4">
      👨‍🏫 <strong>${personnel_absent_jour.length}</strong> membre${personnel_absent_jour.length>1?'s':''} du personnel actuellement absent${personnel_absent_jour.length>1?'s':''} :
      ${personnel_absent_jour.map(p=>`<strong>${esc(p.prenom)} ${esc(p.nom)}</strong>${p.matiere?` (${esc(p.matiere)})`:''}`).join(', ')}
      <button class="btn btn-outline btn-xs" style="margin-left:10px" onclick="navigate('absences')">Voir</button>
    </div>` : ''}

    <div class="stats-grid">
      <div class="stat">
        <div class="stat-icon">🎓</div><div class="stat-label">Élèves inscrits</div>
        <div class="stat-val">${stats.eleves}</div>
        <div class="stat-hint">dont ${stats.eleves_filles} filles</div>
      </div>
      ${peutVoirFinances ? `
      <div class="stat"><div class="stat-icon">💰</div><div class="stat-label">Recettes encaissées</div><div class="stat-val" style="font-size:18px">${fmtMoney(stats.recettes)}</div></div>
      <div class="stat"><div class="stat-icon">⚠️</div><div class="stat-label">Reste à recouvrer</div><div class="stat-val" style="font-size:18px;color:var(--c-err)">${fmtMoney(stats.impayes)}</div></div>
      <div class="stat">
        <div class="stat-icon">📈</div><div class="stat-label">Taux de recouvrement</div>
        <div class="stat-val">${stats.taux_recouvrement} %</div>
        <div class="progress mt-2"><div class="progress-bar ${stats.taux_recouvrement>=80?'':stats.taux_recouvrement>=50?'warn':'err'}" style="width:${Math.min(stats.taux_recouvrement,100)}%"></div></div>
      </div>
      <div class="stat"><div class="stat-icon">👨‍🏫</div><div class="stat-label">Salaires versés</div><div class="stat-val" style="font-size:18px">${fmtMoney(stats.salaires_verses)}</div></div>
      <div class="stat">
        <div class="stat-icon" style="color:${stats.solde_caisse>=0?'var(--c-ok)':'var(--c-err)'}">💳</div><div class="stat-label">Solde de caisse</div>
        <div class="stat-val" style="font-size:18px;color:${stats.solde_caisse>=0?'var(--c-ok)':'var(--c-err)'}">${fmtMoney(stats.solde_caisse)}</div>
        <div class="stat-hint">recettes − salaires − charges</div>
      </div>
      <div class="stat"><div class="stat-icon">📤</div><div class="stat-label">Dépenses</div><div class="stat-val" style="font-size:18px">${fmtMoney(stats.depenses)}</div></div>
      ` : ''}
      <div class="stat"><div class="stat-icon">🚨</div><div class="stat-label">Absences aujourd'hui</div><div class="stat-val">${stats.absences_jour}</div></div>
      <div class="stat"><div class="stat-icon">👨‍🏫</div><div class="stat-label">Personnel absent</div><div class="stat-val" style="color:${stats.personnel_absent_jour>0?'var(--c-err)':'inherit'}">${stats.personnel_absent_jour||0}</div></div>
      <div class="stat"><div class="stat-icon">🔄</div><div class="stat-label">Réinscriptions en attente</div><div class="stat-val">${stats.reinsc_attente}</div></div>
    </div>

    ${peutVoirFinances ? `
    <div class="charts-row">
      <div class="chart-box">
        <h3>📊 Recettes / dépenses par mois (GNF)</h3>
        <div class="chart-wrap"><canvas id="ch-fin"></canvas></div>
        <div class="text-muted mt-2" style="font-size:11px">vertes = recettes • rouges = dépenses (salaires + charges)</div>
      </div>
      <div class="chart-box">
        <h3>🏫 Recouvrement par classe</h3>
        <div class="tbl-wrap" style="max-height:240px;overflow-y:auto">
          <table>
            <thead><tr><th>Classe</th><th class="text-right">Élèves</th><th class="text-right">Dû</th><th class="text-right">Payé</th><th class="text-right">Reste</th></tr></thead>
            <tbody>
              ${recouvrement_par_classe.length ? recouvrement_par_classe.map(r => `<tr>
                <td>${esc(r.classe)}</td>
                <td class="text-right mono">${r.nb_eleves}</td>
                <td class="text-right mono">${fmtMoney(r.montant_du)}</td>
                <td class="text-right mono text-ok">${fmtMoney(r.montant_paye)}</td>
                <td class="text-right mono ${r.montant_reste>0?'text-err':''}">${fmtMoney(r.montant_reste)}</td>
              </tr>`).join('') : `<tr><td colspan="5">${emptyHtml('🏫','Aucune donnée')}</td></tr>`}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="grid2">
      <div class="card">
        <div class="card-header"><span class="card-title">💰 Recettes par catégorie</span></div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Catégorie</th><th class="text-right">Montant (GNF)</th></tr></thead>
          <tbody>${recettes_par_categorie.length ? recettes_par_categorie.map(c => `
            <tr><td>${esc(c.categorie)}</td><td class="text-right mono text-ok">${fmtMoney(c.montant)}</td></tr>
          `).join('') : `<tr><td colspan="2">${emptyHtml('💰','Aucune opération enregistrée pour le moment')}</td></tr>`}
          </tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">👥 Effectifs par classe</span></div>
        <div class="chart-wrap" style="height:220px"><canvas id="ch-cls"></canvas></div>
      </div>
    </div>
    ` : `
    <div class="card mb-4">
      <div class="card-header"><span class="card-title">👥 Effectifs par classe</span></div>
      <div class="chart-wrap" style="height:220px"><canvas id="ch-cls"></canvas></div>
    </div>
    `}

    <div class="grid2">
      ${peutVoirFinances ? `
      <div class="card">
        <div class="card-header"><span class="card-title">📋 Dernières transactions</span></div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Date</th><th>Description</th><th>Montant</th></tr></thead>
          <tbody>${dernieres_transactions.length ? dernieres_transactions.map(t => `
            <tr>
              <td>${fmtDate(t.date_op)}</td>
              <td>${esc(t.description||t.categorie||'—')}</td>
              <td class="mono text-right ${t.type==='entree'?'text-ok':'text-err'}">${t.type==='entree'?'+':'−'}${fmtMoney(t.montant)}</td>
            </tr>`).join('') : `<tr><td colspan="3">${emptyHtml('📋','Aucune transaction')}</td></tr>`}
          </tbody>
        </table></div>
      </div>` : ''}

      <div class="card">
        <div class="card-header"><span class="card-title">📚 Prochains devoirs</span></div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Devoir</th><th>Classe</th><th>Remise</th></tr></thead>
          <tbody>${prochains_devoirs.length ? prochains_devoirs.map(dv => {
            const jr = dv.date_remise ? jresteText(dv.date_remise) : null;
            return `<tr>
              <td><strong>${esc(dv.titre)}</strong><br><span class="text-muted" style="font-size:11px">${esc(dv.matiere||'')}</span></td>
              <td><span class="badge bdg-primary">${esc(dv.classe||'—')}</span></td>
              <td>${jr ? `<span class="badge ${jr.cls}">${jr.txt}</span>` : '—'}</td>
            </tr>`;
          }).join('') : `<tr><td colspan="3">${emptyHtml('📚','Aucun devoir à venir')}</td></tr>`}
          </tbody>
        </table></div>
      </div>
    </div>

    ${peutVoirFinances ? `
    <div class="card mt-4">
      <div class="card-header"><span class="card-title">⚠️ Élèves avec impayés (${stats.eleves_avec_impayes})</span></div>
      <div class="card-body">
        ${eleves_impayes_liste.length ? `
        <div class="tbl-wrap"><table>
          <thead><tr><th>Élève</th><th>Classe</th><th>Matricule</th><th class="text-right">Reste dû</th></tr></thead>
          <tbody>${eleves_impayes_liste.map(e => `<tr>
            <td><strong>${esc(e.prenom)} ${esc(e.nom)}</strong></td>
            <td><span class="badge bdg-primary">${esc(e.classe||'—')}</span></td>
            <td class="mono text-muted">${esc(e.matricule||'—')}</td>
            <td class="text-right mono text-err fw-600">${fmtMoney(e.reste)}</td>
          </tr>`).join('')}</tbody>
        </table></div>
        <button class="btn btn-outline btn-sm mt-3" onclick="navigate('paiements')">Voir tous les paiements →</button>
        ` : `<div class="text-ok" style="font-size:14px">✅ Aucun impayé — bravo !</div>`}
      </div>
    </div>` : ''}

    ${dernieres_annonces.length ? `
    <div class="card mt-4">
      <div class="card-header"><span class="card-title">📢 Dernières annonces</span></div>
      <div class="card-body">
        ${dernieres_annonces.map(a => `
          <div class="mb-3" style="border-left:3px solid var(--c-primary);padding-left:12px">
            <div class="fw-600">${esc(a.titre)}</div>
            <div class="text-muted" style="font-size:12px;margin:4px 0">${esc(a.auteur_nom||'')} · ${fmtDate(a.date_publication)}</div>
            <div style="font-size:13px">${esc(a.contenu).substring(0,160)}${(a.contenu||'').length>160?'…':''}</div>
          </div>
        `).join('')}
      </div>
    </div>` : ''}
    `;

    // Graphiques — isolés dans leur propre try/catch : si Chart.js ne charge pas
    // (CDN bloqué, hors-ligne...), le reste du tableau de bord reste fonctionnel.
    try {
      if (typeof Chart === 'undefined') throw new Error('Chart.js indisponible');

      if (peutVoirFinances) {
        const labels = finances_mois.map(r => r.mois);
        new Chart($('#ch-fin'), {
          type: 'bar',
          data: {
            labels,
            datasets: [
              { label:'Recettes', data: finances_mois.map(r=>r.recettes), backgroundColor:'rgba(5,150,105,.7)' },
              { label:'Dépenses', data: finances_mois.map(r=>r.depenses), backgroundColor:'rgba(220,38,38,.7)' },
            ]
          },
          options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'top' } }, scales:{ y:{ beginAtZero:true } } }
        });
      }

      new Chart($('#ch-cls'), {
        type: 'doughnut',
        data: {
          labels: eleves_classe.map(r=>r.classe),
          datasets: [{ data: eleves_classe.map(r=>r.n), backgroundColor: COULEURS_EDT }]
        },
        options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'right', labels:{ font:{ size:11 } } } } }
      });
    } catch(chartErr) {
      console.warn('Graphiques indisponibles :', chartErr.message);
      ['#ch-fin','#ch-cls'].forEach(sel => {
        const el = $(sel);
        if (el && el.parentElement) el.parentElement.innerHTML = '<div class="text-muted" style="text-align:center;padding:40px;font-size:12px">📊 Graphique indisponible (bibliothèque non chargée)</div>';
      });
    }
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
