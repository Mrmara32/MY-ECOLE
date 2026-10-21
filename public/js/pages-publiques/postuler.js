function codeEcoleDepuisURL() {
  const m = window.location.pathname.match(/^\/ecole\/([^/]+)/);
  return m ? m[1] : null;
}
const CODE_ECOLE = codeEcoleDepuisURL();
if (CODE_ECOLE) {
  document.querySelectorAll('a[href="/vitrine.html"]').forEach(a => a.href = `/ecole/${CODE_ECOLE}/vitrine`);
}
const MATIERES = ['Mathématiques','Français','Anglais','Histoire-Géographie','SVT','Physique-Chimie','EPS','Arts Plastiques','Musique','Éducation Civique','Philosophie','Espagnol','Informatique','Arabe'];
document.getElementById('matieres-grid').innerHTML = MATIERES.map(m =>
  `<label><input type="checkbox" name="matiere" value="${m}"> ${m}</label>`
).join('');

document.getElementById('f-cand').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errBox = document.getElementById('msg-err');
  errBox.style.display = 'none';
  const fd = new FormData(e.target);
  const matieres = Array.from(document.querySelectorAll('input[name=matiere]:checked')).map(el => el.value);
  const cyclesChoisis = Array.from(document.querySelectorAll('input[name=cycle_check]:checked')).map(el => el.value);
  if (matieres.length === 0) {
    errBox.textContent = 'Veuillez cocher au moins une matière.';
    errBox.style.display = 'block';
    return;
  }
  if (cyclesChoisis.length === 0) {
    errBox.textContent = 'Veuillez cocher au moins un cycle.';
    errBox.style.display = 'block';
    return;
  }
  const body = {
    prenom: fd.get('prenom'), nom: fd.get('nom'), telephone: fd.get('telephone'),
    email: fd.get('email'), cycle: cyclesChoisis.join(', '), disponibilites: fd.get('disponibilites'),
    message: fd.get('message'), matieres,
    username_souhaite: fd.get('username_souhaite'), password: fd.get('password'),
  };
  if (CODE_ECOLE) body.code_ecole = CODE_ECOLE;
  try {
    const res = await fetch('/api/candidatures', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Erreur'); }
    document.getElementById('form-wrap').style.display = 'none';
    document.getElementById('msg-ok').style.display = 'block';
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = 'block';
  }
});
