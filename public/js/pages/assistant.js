/* Assistante IA : panneau latéral ouvert depuis le bouton « 🤖 Assistante » de la barre du haut.
   La conversation reste en mémoire pendant la session (rien n'est enregistré sur le serveur). */
let _assistantMessages = [];
let _assistantOccupee = false;

const ASSISTANT_SUGGESTIONS_COMMUNES = [
  'Comment enregistrer un paiement de scolarité ?',
  'Prépare une fiche de cours sur la photosynthèse (6e)',
  "Résume l'histoire de l'indépendance de la Guinée",
  'Génère 5 exercices corrigés sur les fractions',
];
const ASSISTANT_SUGGESTIONS_DIRECTION = [
  "Fais le point sur l'école : effectifs, paiements, résultats",
  'Combien d\'élèves par niveau et combien sont à jour de leurs paiements ?',
  'Quelles classes et matières ont les résultats les plus faibles ? Que faire ?',
  'Comment améliorer le recouvrement et les recettes ?',
];
const ASSISTANT_SUGGESTIONS_ENSEIGNANT = [
  'Où en sont les résultats de mes classes ? Que me conseilles-tu ?',
  "Comment réduire les absences dans mes classes ?",
];
function _assistantSuggestions() {
  const r = currentUser && currentUser.role;
  if (['admin', 'directeur', 'directeur_etudes', 'comptable'].includes(r)) return ASSISTANT_SUGGESTIONS_DIRECTION.concat(ASSISTANT_SUGGESTIONS_COMMUNES.slice(0, 2));
  if (r === 'enseignant') return ASSISTANT_SUGGESTIONS_ENSEIGNANT.concat(ASSISTANT_SUGGESTIONS_COMMUNES.slice(1));
  return ASSISTANT_SUGGESTIONS_COMMUNES;
}
let ASSISTANT_SUGGESTIONS = [];

function _assistantFormater(texte) {
  // Échappe d'abord tout le HTML, puis applique un Markdown léger (gras, listes, titres, code).
  let h = esc(texte);
  h = h.replace(/```([\s\S]*?)```/g, (m, c) => '<pre>' + c.trim() + '</pre>');
  h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
  h = h.replace(/^#{1,4}\s*(.+)$/gm, '<b class="as-titre">$1</b>');
  h = h.replace(/^(?:[-*•])\s+(.+)$/gm, '<div class="as-li">• $1</div>');
  h = h.replace(/^(\d+)[.)]\s+(.+)$/gm, '<div class="as-li">$1. $2</div>');
  return h.replace(/\n/g, '<br>').replace(/(<br>)+(<div|<pre|<b class="as-titre)/g, '$2').replace(/(<\/div>|<\/pre>)<br>/g, '$1');
}

function _assistantRendu() {
  const zone = $('#as-messages');
  if (!zone) return;
  if (!_assistantMessages.length) {
    ASSISTANT_SUGGESTIONS = _assistantSuggestions();
    zone.innerHTML = `<div class="as-accueil"><div class="as-robot">🤖</div>
      <p><b>Bonjour ! Je suis l'Assistante MY-ECOLE.</b><br>Je vous aide à utiliser l'application, je suis la vie de l'école (effectifs, paiements, résultats, assiduité) pour vous proposer des actions, et je réponds à vos questions de sciences, langues, histoire, géographie… sur la Guinée, l'Afrique et le monde.</p>
      <div class="as-suggestions">${ASSISTANT_SUGGESTIONS.map((q, i) => `<button class="as-chip" onclick="assistantSuggestion(${i})">${esc(q)}</button>`).join('')}</div>
      <p class="as-note">Je ne consulte que des statistiques de l'école selon votre rôle, sans noms d'élèves. Ne saisissez pas de données personnelles dans vos questions. Vérifiez toujours les informations importantes.</p></div>`;
    return;
  }
  zone.innerHTML = _assistantMessages.map(m =>
    `<div class="as-msg as-${m.role}">${m.role === 'assistant' ? _assistantFormater(m.content) : esc(m.content).replace(/\n/g, '<br>')}</div>`).join('')
    + (_assistantOccupee ? '<div class="as-msg as-assistant as-attente">Je réfléchis…</div>' : '');
  zone.scrollTop = zone.scrollHeight;
}

function ouvrirAssistante() {
  let p = $('#assistant-panneau');
  if (!p) {
    p = document.createElement('aside');
    p.id = 'assistant-panneau';
    p.className = 'assistant-panneau';
    p.innerHTML = `<div class="as-entete"><b>🤖 Assistante MY-ECOLE</b>
        <span>${currentUser && ['admin','directeur'].includes(currentUser.role) ? '<button class="icon-btn" onclick="assistantReglage()" title="Activer / désactiver l\'assistante pour l\'établissement">⚙️</button>' : ''}
        ${currentUser && ['admin','directeur'].includes(currentUser.role) ? '<button class="icon-btn" onclick="assistantBilan()" title="Envoyer le bilan de l\'école par e-mail à la direction">✉️</button>' : ''}
        <button class="icon-btn" onclick="assistantNouvelle()" title="Nouvelle conversation">🗑️</button>
        <button class="icon-btn" onclick="fermerAssistante()" title="Fermer">✕</button></span></div>
      <div id="as-messages" class="as-messages"></div>
      <form id="as-form" class="as-form"><textarea id="as-saisie" rows="2" maxlength="4000" placeholder="Posez votre question…"></textarea>
        <button class="btn btn-primary" type="submit" id="as-envoyer">Envoyer</button></form>`;
    document.body.appendChild(p);
    $('#as-form').onsubmit = e => { e.preventDefault(); assistantEnvoyer(); };
    $('#as-saisie').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); assistantEnvoyer(); } });
  }
  p.classList.add('ouvert');
  _assistantRendu();
  setTimeout(() => { const i = $('#as-saisie'); i && i.focus(); }, 50);
}
function fermerAssistante() { const p = $('#assistant-panneau'); if (p) p.classList.remove('ouvert'); }
function assistantNouvelle() { _assistantMessages = []; _assistantRendu(); }
function assistantSuggestion(i) { const s = $('#as-saisie'); if (s) { s.value = ASSISTANT_SUGGESTIONS[i]; assistantEnvoyer(); } }

async function assistantEnvoyer() {
  const saisie = $('#as-saisie');
  const texte = (saisie.value || '').trim();
  if (!texte || _assistantOccupee) return;
  saisie.value = '';
  _assistantMessages.push({ role: 'user', content: texte });
  _assistantOccupee = true; _assistantRendu();
  try {
    const r = await apiFetch('/assistant/discuter', { method: 'POST', body: { messages: _assistantMessages, page: currentPage } });
    _assistantMessages.push({ role: 'assistant', content: r.reponse });
  } catch (err) {
    _assistantMessages.push({ role: 'assistant', content: '⚠️ ' + err.message });
  }
  _assistantOccupee = false; _assistantRendu();
}
window.ouvrirAssistante = ouvrirAssistante; window.fermerAssistante = fermerAssistante;
window.assistantNouvelle = assistantNouvelle; window.assistantSuggestion = assistantSuggestion;

/* « Le point de l'assistante » sur le tableau de bord : alertes calculées par le serveur selon le rôle. */
async function assistantPointAccueil() {
  const zone = $('#as-point');
  if (!zone) return;
  let liste = [];
  try { liste = (await apiFetch('/assistant/alertes')).alertes || []; } catch (_) { return; }
  if (!liste.length || !$('#as-point')) return;
  window._assistantAlertes = liste;
  const couleur = { rouge: '#dc2626', orange: '#d97706', info: '#2563eb' };
  $('#as-point').innerHTML = `<div class="card mb-4" style="border-left:4px solid var(--c-primary)">
    <div class="card-header"><b>🤖 Le point de l'assistante</b></div>
    <div style="padding:6px 14px 12px">${liste.map((a, i) => `
      <div style="display:flex;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--g2,#eee)">
        <span style="width:10px;height:10px;border-radius:50%;background:${couleur[a.niveau] || '#6b7280'};flex:0 0 10px"></span>
        <div style="flex:1"><b>${esc(a.titre)}</b><div class="text-muted" style="font-size:12.5px">${esc(a.detail)}</div></div>
        <button class="btn btn-outline btn-xs" onclick="assistantAlerte(${i})">Que faire ?</button>
      </div>`).join('')}</div></div>`;
}
function assistantAlerte(i) {
  const a = (window._assistantAlertes || [])[i];
  if (!a) return;
  ouvrirAssistante();
  const s = $('#as-saisie'); if (s) { s.value = a.question; assistantEnvoyer(); }
}
window.assistantPointAccueil = assistantPointAccueil; window.assistantAlerte = assistantAlerte;

async function assistantReglage() {
  let st;
  try { st = await apiFetch('/assistant/statut'); } catch (err) { toast(err.message, 'error'); return; }
  const desactiver = !st.desactivee_par_ecole;
  if (!confirm(desactiver ? "Désactiver l'assistante pour tout l'établissement ?" : "Réactiver l'assistante pour l'établissement ?")) return;
  try {
    await apiFetch('/settings', { method: 'PUT', body: { assistant_actif: desactiver ? '0' : '1' } });
    toast(desactiver ? 'Assistante désactivée' : 'Assistante réactivée', 'success');
    if (desactiver) fermerAssistante();
  } catch (err) { toast(err.message, 'error'); }
}
window.assistantReglage = assistantReglage;

async function assistantBilan() {
  if (!confirm("Envoyer maintenant le bilan de l'école par e-mail à l'administrateur et au directeur ?")) return;
  try { const r = await apiFetch('/assistant/bilan', { method: 'POST', body: {} }); toast(`Bilan envoyé à ${r.destinataires} personne(s)`, 'success'); }
  catch (err) { toast(err.message, 'error'); }
}
window.assistantBilan = assistantBilan;
