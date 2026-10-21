const $ = id => document.getElementById(id);
const m = location.pathname.match(/^\/ecole\/([^/]+)/);
const ECOLE = m ? m[1] : (new URLSearchParams(location.search).get('ecole') || '');
let CONFIG = {};
const fmt = n => Number(n).toLocaleString('fr-FR').replace(/ /g, ' ') + ' GNF';
const erreur = t => { $('err').textContent = t; $('err').style.display = t ? 'block' : 'none'; };
async function api(chemin, corps) {
  const r = await fetch('/api/orange-money/public/' + chemin + (corps ? '' : '?ecole=' + encodeURIComponent(ECOLE)), corps ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ecole: ECOLE, ...corps }) } : undefined);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || 'Erreur');
  return d;
}
const identite = () => ({ nom: $('nom').value.trim(), prenom: $('prenom').value.trim(), matricule: $('matricule').value.trim() });
api('config').then(c => {
  CONFIG = c; if (c.ecole_nom) { $('ecole-nom').textContent = c.ecole_nom; document.title = 'Payer la scolarité — ' + c.ecole_nom; }
}).catch(() => {});
$('f1').addEventListener('submit', async e => {
  e.preventDefault(); erreur('');
  try {
    const d = await api('verifier', identite());
    if (d.reste <= 0) return erreur("Aucun solde à régler pour cet élève : merci !");
    $('el').textContent = d.eleve.prenom + ' ' + d.eleve.nom; $('cl').textContent = d.eleve.classe || ''; $('reste').textContent = fmt(d.reste);
    $('montant').value = d.reste; $('montant').max = d.reste;
    if (CONFIG.mode === 'qr') {
      $('bloc-qr').classList.remove('hide'); $('btn2').textContent = "J'ai payé : enregistrer mon paiement";
      if (CONFIG.qr_url) { $('qr-img').src = CONFIG.qr_url; $('qr-img').classList.remove('hide'); }
      $('qr-nom').textContent = CONFIG.nom || ''; $('qr-code').textContent = CONFIG.code ? 'Code marchand : ' + CONFIG.code : '';
      $('instr').textContent = CONFIG.instructions || '';
    } else { $('btn2').textContent = 'Payer avec Orange Money'; }
    $('f1').classList.add('hide'); $('f2').classList.remove('hide');
  } catch (x) { erreur(x.message); }
});
$('retour').onclick = () => { $('f2').classList.add('hide'); $('f1').classList.remove('hide'); erreur(''); };
$('f2').addEventListener('submit', async e => {
  e.preventDefault(); erreur(''); $('btn2').disabled = true;
  try {
    const d = await api('payer', { ...identite(), montant: $('montant').value, transaction_id: $('trans').value, telephone: $('tel').value });
    if (d.mode === 'api') { location.href = d.payment_url; return; }
    $('f2').classList.add('hide'); $('fin').classList.remove('hide');
  } catch (x) { erreur(x.message); }
  $('btn2').disabled = false;
});
