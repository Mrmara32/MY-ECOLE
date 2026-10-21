function codeEcoleDepuisURL() {
  const m = window.location.pathname.match(/^\/ecole\/([^/]+)/);
  return m ? m[1] : null;
}
const CODE_ECOLE = codeEcoleDepuisURL();
if (CODE_ECOLE) {
  document.querySelectorAll('a[href="/vitrine.html"]').forEach(a => a.href = `/ecole/${CODE_ECOLE}/vitrine`);
}
document.getElementById('f-pre').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errBox = document.getElementById('msg-err');
  errBox.style.display = 'none';
  const fd = new FormData(e.target);
  const body = {};
  for (const [k, v] of fd.entries()) { if (v) body[k] = v; }

  if (!body.pere_telephone && !body.mere_telephone && !body.contact_urgence_telephone) {
    errBox.textContent = 'Veuillez indiquer au moins un numéro de téléphone (père, mère ou contact d\'urgence).';
    errBox.style.display = 'block';
    return;
  }

  if (CODE_ECOLE) body.code_ecole = CODE_ECOLE;

  try {
    const res = await fetch('/api/eleves/preinscription-publique', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erreur');
    document.getElementById('form-wrap').style.display = 'none';
    document.getElementById('matricule-affiche').textContent = 'MATRICULE : ' + data.matricule;
    document.getElementById('msg-ok').style.display = 'block';
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = 'block';
  }
});
