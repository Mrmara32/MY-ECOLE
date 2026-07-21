/* ===================== PARAMÈTRES ÉCOLE ===================== */
async function pageSettings() {
  $('#content').innerHTML = loadingHtml;
  try {
    const s = await apiGetSettings();
    $('#content').innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">🏫 Paramètres de l'établissement</span></div>
      <div class="card-body">
        <form id="f-settings" style="display:flex;flex-direction:column;gap:18px">
          <!-- Logo -->
          <div class="form-section">
            <div class="form-section-title">Logo de l'école</div>
            <div class="flex items-center gap-3 mb-3">
              ${s.ecole_logo ? `<img src="${esc(s.ecole_logo)}" style="width:80px;height:80px;object-fit:contain;border:1px solid #E5E7EB;border-radius:8px">` : '<div class="photo-placeholder" style="width:80px;height:80px">🏫</div>'}
              <div>
                <label class="btn btn-outline btn-sm" style="cursor:pointer">
                  📷 Changer le logo
                  <input type="file" id="logo-file" accept="image/*" style="display:none">
                </label>
                <div class="text-muted mt-2" style="font-size:12px">PNG, JPG recommandé · Max 5 Mo</div>
              </div>
            </div>
          </div>
          <!-- Cachet et signature -->
          <div class="form-section">
            <div class="form-section-title">Cachet et signature du directeur</div>
            <div class="text-muted mb-3" style="font-size:12px">Utilisés automatiquement sur la carte scolaire, les badges, les cartes d'accès et les documents imprimés.</div>
            <div class="form-2">
              <div class="flex items-center gap-3">
                ${s.ecole_cachet ? `<img src="${esc(s.ecole_cachet)}" style="width:70px;height:70px;object-fit:contain;border:1px solid #E5E7EB;border-radius:8px;background:#fff">` : '<div class="photo-placeholder" style="width:70px;height:70px">🔖</div>'}
                <div>
                  <label class="btn btn-outline btn-sm" style="cursor:pointer">
                    🔖 Changer le cachet
                    <input type="file" id="cachet-file" accept="image/*" style="display:none">
                  </label>
                  <div class="text-muted mt-1" style="font-size:11px">Idéalement un PNG à fond transparent</div>
                </div>
              </div>
              <div class="flex items-center gap-3">
                ${s.signature_directeur ? `<img src="${esc(s.signature_directeur)}" style="width:110px;height:60px;object-fit:contain;border:1px solid #E5E7EB;border-radius:8px;background:#fff">` : '<div class="photo-placeholder" style="width:110px;height:60px">✍️</div>'}
                <div>
                  <label class="btn btn-outline btn-sm" style="cursor:pointer">
                    ✍️ Changer la signature
                    <input type="file" id="signature-file" accept="image/*" style="display:none">
                  </label>
                  <div class="text-muted mt-1" style="font-size:11px">Idéalement un PNG à fond transparent</div>
                </div>
              </div>
            </div>
          </div>
          <div class="form-section">
            <div class="form-section-title">Informations générales</div>
            <div class="form-2">
              <div class="fg"><label>Nom de l'établissement*</label>
                <input name="ecole_nom" value="${esc(s.ecole_nom||'')}" required placeholder="Groupe Scolaire ABC">
              </div>
              <div class="fg"><label>Année scolaire courante</label>
                <input name="annee_scolaire" value="${esc(s.annee_scolaire||anneeCourante())}" placeholder="2024-2025">
              </div>
            </div>
            <div class="fg mt-3"><label>Adresse complète</label>
              <textarea name="ecole_adresse" rows="2" placeholder="Quartier, Commune, Ville">${esc(s.ecole_adresse||'')}</textarea>
            </div>
            <div class="form-2 mt-3">
              <div class="fg"><label>Téléphone</label>
                <input name="ecole_telephone" value="${esc(s.ecole_telephone||'')}" placeholder="+224 6XX XXX XXX">
              </div>
              <div class="fg"><label>Email</label>
                <input type="email" name="ecole_email" value="${esc(s.ecole_email||'')}" placeholder="contact@ecole.com">
              </div>
            </div>
          </div>
          <div>
            <button type="submit" class="btn btn-primary">💾 Enregistrer</button>
          </div>
        </form>
      </div>
    </div>

    ${currentUser.role === 'admin' ? `
    <div class="card mt-4">
      <div class="card-header"><span class="card-title">🔒 Seuils d'approbation comptable</span></div>
      <div class="card-body">
        <div class="alert alert-info">Ces seuils déterminent qui doit approuver une dépense avant qu'elle soit comptabilisée :
        en dessous du 1er seuil, la dépense est automatique ; entre les deux seuils, le <strong>directeur</strong> doit l'approuver ;
        au-dessus du 2ème seuil, seul <strong>vous (administrateur/fondateur)</strong> pouvez l'approuver.</div>
        <form id="f-seuils" class="form-2">
          <div class="fg"><label>Seuil d'approbation du directeur (GNF)</label>
            <input type="number" name="seuil_approbation_directeur" value="${s.seuil_approbation_directeur||30000}" min="0" step="1">
          </div>
          <div class="fg"><label>Seuil d'approbation de l'administrateur (GNF)</label>
            <input type="number" name="seuil_approbation_admin" value="${s.seuil_approbation_admin||100000}" min="0" step="1">
          </div>
          <div style="grid-column:1/-1">
            <button type="submit" class="btn btn-primary">💾 Enregistrer les seuils</button>
          </div>
        </form>
      </div>
    </div>` : ''}`;

    // Upload logo
    $('#logo-file').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('logo', file);
      try {
        const r = await apiUpload('/settings/logo', fd);
        toast('Logo mis à jour', 'success');
        // Mettre à jour l'aperçu et la sidebar
        applyBranding({ ecole_logo: r.logo_url });
        pageSettings();
      } catch(err) { toast(err.message, 'error'); }
    });

    $('#cachet-file').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('cachet', file);
      try {
        await apiUpload('/settings/cachet', fd);
        toast('Cachet mis à jour', 'success');
        pageSettings();
      } catch(err) { toast(err.message, 'error'); }
    });

    $('#signature-file').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('signature', file);
      try {
        await apiUpload('/settings/signature-directeur', fd);
        toast('Signature mise à jour', 'success');
        pageSettings();
      } catch(err) { toast(err.message, 'error'); }
    });

    $('#f-settings').onsubmit = async e => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(e.target));
      try {
        const updated = await apiSaveSettings(data);
        applyBranding(updated);
        toast('Paramètres enregistrés', 'success');
      } catch(err) { toast(err.message, 'error'); }
    };

    if ($('#f-seuils')) {
      $('#f-seuils').onsubmit = async e => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        try { await apiUpdateSeuils(data); toast('Seuils mis à jour', 'success'); }
        catch(err) { toast(err.message, 'error'); }
      };
    }
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

function applyBranding(s) {
  if (s.ecole_nom) {
    document.title = s.ecole_nom + ' — Gestion';
    $('#sb-ecole-nom') && ($('#sb-ecole-nom').textContent = s.ecole_nom);
    $('#login-ecole-nom') && ($('#login-ecole-nom').textContent = s.ecole_nom);
  }
  if (s.annee_scolaire) {
    $('#sb-annee') && ($('#sb-annee').textContent = s.annee_scolaire);
  }
  if (s.ecole_logo) {
    const sbLogo = $('#sb-logo');
    if (sbLogo) { sbLogo.src = s.ecole_logo; sbLogo.style.display = ''; }
    const sbIcon = $('#sb-logo-icon');
    if (sbIcon) sbIcon.style.display = 'none';
    const lLogo = $('#login-logo');
    if (lLogo) { lLogo.src = s.ecole_logo; lLogo.style.display = ''; }
    const lIcon = $('#login-logo-default');
    if (lIcon) lIcon.style.display = 'none';
  }
}
window.applyBranding = applyBranding;
