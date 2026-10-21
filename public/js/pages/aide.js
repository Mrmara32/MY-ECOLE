/* ===================== AIDE ET À PROPOS ===================== */
let _aideInfo = null;

async function chargerInfoAide() {
  if (!_aideInfo) _aideInfo = await apiFetch('/aide/info');
  return _aideInfo;
}

function _aideMessageLicence(l, ecoleNom) {
  const etat = l.type === 'locale'
    ? ({ licenciee: 'licence active', essai: `essai (${l.jours_restants} jour(s) restant(s))`, essai_expire: 'essai terminé' }[l.mode] || l.mode)
    : ({ essai: 'essai', active: 'active', expiree: 'expirée', suspendue: 'suspendue' }[l.statut] || l.statut || '');
  return `Bonjour Actif System, je souhaite activer ou renouveler la licence MY-ECOLE de l'établissement « ${ecoleNom || l.ecole || ''} »`
    + (l.code ? ` (code ${l.code})` : '') + `. État actuel : ${etat}` + (l.expiration ? `, expiration : ${l.expiration}` : '') + '.';
}

function _aideLicenceHtml(l, ed, ecoleNom) {
  let etat, classe = 'alert-info';
  if (l.type === 'locale') {
    if (l.mode === 'licenciee') etat = `✅ Licence active ${l.expiration === 'PERPETUEL' ? '(perpétuelle)' : l.expiration ? `jusqu'au ${esc(l.expiration.replace(/^(\d{4})(\d{2})(\d{2})$/, '$3/$2/$1'))}` : ''}`;
    else if (l.mode === 'essai') { etat = `⏳ Période d'essai : ${l.jours_restants} jour(s) restant(s)`; classe = 'alert-warn'; }
    else { etat = '🔒 Période d\'essai terminée : une licence est nécessaire'; classe = 'alert-danger'; }
  } else {
    const j = l.jours_restants;
    if (l.statut === 'active') { etat = `✅ Licence active${l.expiration ? ` jusqu'au ${esc(fmtDate(l.expiration))}` : ''}`; if (j != null && j <= 30 && j >= 0) { etat += ` — expire dans ${j} jour(s) : pensez à la renouveler`; classe = 'alert-warn'; } }
    else if (l.statut === 'essai') { etat = `⏳ Période d'essai${l.expiration ? ` jusqu'au ${esc(fmtDate(l.expiration))}` : ''}${j != null ? ` (${Math.max(j, 0)} jour(s) restant(s))` : ''}`; classe = 'alert-warn'; }
    else if (l.statut === 'suspendue') { etat = '⛔ Licence suspendue : contactez l\'éditeur'; classe = 'alert-danger'; }
    else { etat = '🔒 Licence expirée : renouvelez-la pour continuer'; classe = 'alert-danger'; }
  }
  const msg = encodeURIComponent(_aideMessageLicence(l, ecoleNom));
  const boutons = `
    <a class="btn btn-primary btn-sm" href="https://wa.me/${esc(ed.whatsapp)}?text=${msg}" target="_blank" rel="noopener">💬 WhatsApp : demander l'activation / le renouvellement</a>
    <a class="btn btn-outline btn-sm" href="tel:${esc(ed.telephone.replace(/\D/g, ''))}">📞 Appeler ${esc(ed.telephone)}</a>
    ${ed.email ? `<a class="btn btn-outline btn-sm" href="mailto:${esc(ed.email)}?subject=${encodeURIComponent('Licence MY-ECOLE')}&body=${msg}">✉️ Écrire par e-mail</a>` : ''}`;
  const cle = l.type === 'locale' ? `
    <form id="aide-form-licence" style="margin-top:12px">
      <div class="fg"><label>Clé de licence reçue de l'éditeur</label>
        <input id="aide-cle" placeholder="ECOLE-PERPETUEL-…" autocomplete="off" style="font-family:monospace;text-transform:uppercase"></div>
      <button class="btn btn-ok btn-sm" type="submit">Activer ma licence</button>
    </form>` : `<div class="text-muted" style="font-size:12px;margin-top:10px">La licence de la plateforme en ligne est activée ou renouvelée par l'éditeur après votre demande ; elle prend effet dès l'enregistrement, sans réinstallation.</div>`;
  return `<div class="alert ${classe}" style="margin-bottom:10px">${etat}</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px">${boutons}</div>${cle}`;
}

async function pageAide() {
  $('#content').innerHTML = loadingHtml;
  try {
    const ed0 = await chargerInfoAide();
    const gestion = ['admin', 'directeur'].includes(currentUser.role);
    let licence = null;
    if (gestion) { try { licence = await apiFetch('/aide/licence'); } catch (_) { /* facultatif */ } }
    const ecoleNom = ($('#sb-ecole-nom') || {}).textContent || '';
    const ed = ed0.editeur;
    const faq = [
      ['J\'ai oublié mon mot de passe', 'Demandez à l\'administrateur de votre établissement de le réinitialiser (Utilisateurs). Un nouveau mot de passe provisoire vous sera donné ; vous le changerez à la prochaine connexion.'],
      ['Comment encaisser un paiement ?', 'Menu Paiements : choisissez l\'élève, saisissez le montant ; un reçu est généré. Pour Orange Money : bouton « 🟠 Orange Money ».'],
      ['Comment prévenir un parent d\'une absence ?', 'Menu Absences → « 📲 Prévenir » (ou « Prévenir tous » si l\'envoi automatique est activé).'],
      ['Comment sauvegarder mes données ?', 'Paramètres → Sauvegardes : téléchargez une copie et rangez-la hors de l\'ordinateur (clé USB, Drive). Une copie automatique quotidienne existe aussi.'],
      ['L\'application ne répond plus', 'Rechargez la page. Si un bandeau « Nouvelle version » apparaît, cliquez sur Recharger. Si le problème continue, relevez le code ERR-… affiché et transmettez-le à l\'éditeur.'],
      ['Mes données sont-elles protégées ?', 'Oui : accès limité par fonction, mots de passe protégés, journal des actions, sauvegardes. Voir la politique de confidentialité ci-dessous.'],
    ];
    $('#content').innerHTML = `
      <div class="card"><div class="card-header"><span class="card-title">ℹ️ À propos de MY-ECOLE</span></div>
        <div class="card-body">
          <p style="margin-top:0"><b>MY-ECOLE</b> — gestion d'établissement scolaire : élèves, notes, absences, pointage, paiements (Orange Money), personnel, communication avec les familles.</p>
          <div class="text-muted" style="font-size:13px">Version de l'application : <b>${esc(ed0.version || '—')}</b> · Conditions en vigueur : ${esc(ed0.version_conditions)}<br>
            Éditeur : <b>${esc(ed.nom)}</b></div>
          <div style="margin-top:10px;display:flex;gap:14px;flex-wrap:wrap;font-size:13px">
            <a href="/conditions.html" target="_blank" rel="noopener">📄 Conditions d'utilisation</a>
            <a href="/confidentialite.html" target="_blank" rel="noopener">🔐 Politique de confidentialité</a></div>
        </div></div>
      ${licence ? `<div class="card" style="margin-top:16px"><div class="card-header"><span class="card-title">🔑 Ma licence</span></div>
        <div class="card-body">${_aideLicenceHtml(licence, ed, ecoleNom)}</div></div>` : ''}
      <div class="card" style="margin-top:16px"><div class="card-header"><span class="card-title">📞 Contacter ${esc(ed.nom)}</span></div>
        <div class="card-body" style="font-size:14px">
          <div>Téléphone : <a href="tel:${esc(ed.telephone.replace(/\D/g, ''))}"><b>${esc(ed.telephone)}</b></a></div>
          <div>WhatsApp : <a href="https://wa.me/${esc(ed.whatsapp)}" target="_blank" rel="noopener">${esc(ed.telephone)}</a></div>
          ${ed.email ? `<div>E-mail : <a href="mailto:${esc(ed.email)}">${esc(ed.email)}</a></div>` : ''}
          <div class="text-muted" style="font-size:12px;margin-top:6px">Pour un problème technique, indiquez la page concernée et, si elle s'affiche, la référence ERR-… de l'erreur.</div>
        </div></div>
      <div class="card" style="margin-top:16px"><div class="card-header"><span class="card-title">❓ Questions fréquentes</span></div>
        <div class="card-body">${faq.map(([q, r]) => `<details style="margin:6px 0"><summary style="cursor:pointer;font-weight:600">${esc(q)}</summary><p style="margin:6px 0 4px 16px;font-size:13px">${esc(r)}</p></details>`).join('')}</div></div>`;
    const f = $('#aide-form-licence');
    if (f) f.addEventListener('submit', async e => {
      e.preventDefault();
      try { await apiActiverLicence($('#aide-cle').value.trim()); toast('Licence activée avec succès !', 'success'); pageAide(); }
      catch (err) { toast(err.message, 'error'); }
    });
  } catch (e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

/* Acceptation des conditions d'utilisation : demandée une fois par version à chaque utilisateur connecté. */
async function exigerAcceptationConditions() {
  let etat;
  try { etat = await apiFetch('/aide/conditions'); } catch (_) { return; }
  if (etat.acceptees) return;
  await new Promise(resolve => {
    const voile = document.createElement('div');
    voile.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,.65);z-index:10000;display:flex;align-items:center;justify-content:center;padding:16px';
    voile.innerHTML = `<div style="background:#fff;color:#1f2937;max-width:460px;width:100%;border-radius:14px;padding:22px;box-shadow:0 10px 40px rgba(0,0,0,.3)">
      <h2 style="margin:0 0 8px;font-size:18px">Conditions d'utilisation</h2>
      <p style="font-size:13.5px;line-height:1.5">Pour continuer, veuillez lire et accepter les conditions d'utilisation et la politique de confidentialité de MY-ECOLE.</p>
      <label style="display:flex;gap:8px;align-items:flex-start;font-size:13px;margin:12px 0"><input type="checkbox" id="cgu-ok" style="width:auto;margin-top:3px"><span>J'ai lu et j'accepte les <a href="/conditions.html" target="_blank" rel="noopener">conditions d'utilisation</a> et la <a href="/confidentialite.html" target="_blank" rel="noopener">politique de confidentialité</a>.</span></label>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn btn-outline btn-sm" id="cgu-non">Se déconnecter</button>
        <button class="btn btn-primary btn-sm" id="cgu-oui" disabled>Accepter et continuer</button></div></div>`;
    document.body.appendChild(voile);
    const ok = voile.querySelector('#cgu-ok'), oui = voile.querySelector('#cgu-oui');
    ok.addEventListener('change', () => { oui.disabled = !ok.checked; });
    voile.querySelector('#cgu-non').addEventListener('click', () => { voile.remove(); logout(); resolve(); });
    oui.addEventListener('click', async () => {
      try { await apiFetch('/aide/conditions', { method: 'POST', body: JSON.stringify({ accepte_conditions: true }) }); voile.remove(); resolve(); }
      catch (e) { toast(e.message, 'error'); }
    });
  });
}
