/* ===================== PARAMÈTRES ÉCOLE ===================== */
async function pageSettings() {
  $('#content').innerHTML = loadingHtml;
  try {
    const s = await apiGetSettings();
    let carouselImages = [];
    try { carouselImages = JSON.parse(s.carousel_images || '[]'); } catch(_) { carouselImages = []; }
    let servicesVieScolaire = [];
    try { servicesVieScolaire = JSON.parse(s.services_vie_scolaire || '[]'); } catch(_) { servicesVieScolaire = []; }
    const CYCLES_DEFAUT = {
      maternelle: { titre:'Maternelle', icone:'🧸', accroche:'Éveil, langage et premiers repères, dans un cadre rassurant.', presentation:'', objectif:'', pedagogie:'', activites:'', equipements:'' },
      primaire:   { titre:'Primaire',   icone:'📘', accroche:'Lecture, écriture, calcul : les fondamentaux, bien ancrés.', presentation:'', objectif:'', pedagogie:'', activites:'', equipements:'' },
      college:    { titre:'Collège',    icone:'🔬', accroche:"Ouverture disciplinaire et méthode de travail affirmée.", presentation:'', objectif:'', pedagogie:'', activites:'', equipements:'' },
      lycee:      { titre:'Lycée',      icone:'🎓', accroche:"Préparation exigeante au baccalauréat et à l'après-bac.", presentation:'', objectif:'', pedagogie:'', activites:'', equipements:'' },
    };
    let cyclesDetail = CYCLES_DEFAUT;
    try { cyclesDetail = { ...CYCLES_DEFAUT, ...JSON.parse(s.cycles_detail || '{}') }; } catch(_) {}
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

          <!-- Site public (vitrine) -->
          <div class="form-section">
            <div class="form-section-title">🌐 Site public — Apparence</div>
            <div class="text-muted mb-3" style="font-size:12px">Ces réglages s'appliquent immédiatement sur le site public (/vitrine), modifiables à tout moment.</div>

            <div class="fg mb-3">
              <label>Fond du site (image d'arrière-plan de la page d'accueil)</label>
              <div class="flex items-center gap-3">
                ${s.ecole_fond_url ? `<img src="${esc(s.ecole_fond_url)}" style="width:140px;height:80px;object-fit:cover;border:1px solid #E5E7EB;border-radius:8px">` : '<div class="photo-placeholder" style="width:140px;height:80px">🖼️</div>'}
                <label class="btn btn-outline btn-sm" style="cursor:pointer">
                  🖼️ Changer le fond
                  <input type="file" id="fond-file" accept="image/*" style="display:none">
                </label>
                ${s.ecole_fond_url ? `<button type="button" class="btn btn-outline btn-sm" onclick="retirerFond()">↺ Revenir au fond par défaut</button>` : ''}
              </div>
              <div class="text-muted mt-1" style="font-size:11.5px">Sans image ici, le site affiche son apparence par défaut (fond blanc, touches bleu ciel et jaune pâle).</div>
            </div>

            <div class="fg">
              <label>Carrousel d'images (page d'accueil — 8 maximum)</label>
              <div class="flex flex-wrap gap-2 mb-2" id="carousel-list">
                ${(carouselImages||[]).map(url => `
                  <div style="position:relative">
                    <img src="${esc(url)}" style="width:90px;height:65px;object-fit:cover;border-radius:6px;border:1px solid #E5E7EB">
                    <button type="button" class="btn btn-danger btn-xs" style="position:absolute;top:-6px;right:-6px;border-radius:50%;padding:2px 6px" onclick="retirerImageCarousel('${esc(url)}')">✕</button>
                  </div>`).join('') || '<span class="text-muted" style="font-size:12px">Aucune image ajoutée</span>'}
              </div>
              <label class="btn btn-outline btn-sm" style="cursor:pointer">
                + Ajouter une image au carrousel
                <input type="file" id="carousel-file" accept="image/*" style="display:none">
              </label>
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-title">🎬 Vidéo de présentation (YouTube)</div>
            <div class="fg"><label>Lien YouTube</label>
              <input name="video_presentation_youtube" value="${esc(s.video_presentation_youtube||'')}" placeholder="https://www.youtube.com/watch?v=...">
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-title">✍️ Mot du Fondateur</div>
            <div class="fg"><label>Texte affiché sur le site public</label>
              <textarea name="mot_fondateur" rows="5" placeholder="Chers parents, chers élèves...">${esc(s.mot_fondateur||'')}</textarea>
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-title">📱 Réseaux sociaux</div>
            <div class="form-2">
              <div class="fg"><label>📘 Facebook</label><input name="reseau_facebook" value="${esc(s.reseau_facebook||'')}" placeholder="https://facebook.com/..."></div>
              <div class="fg"><label>📷 Instagram</label><input name="reseau_instagram" value="${esc(s.reseau_instagram||'')}" placeholder="https://instagram.com/..."></div>
            </div>
            <div class="form-2">
              <div class="fg"><label>▶️ YouTube</label><input name="reseau_youtube" value="${esc(s.reseau_youtube||'')}" placeholder="https://youtube.com/@..."></div>
              <div class="fg"><label>🎵 TikTok</label><input name="reseau_tiktok" value="${esc(s.reseau_tiktok||'')}" placeholder="https://tiktok.com/@..."></div>
            </div>
            <div class="fg"><label>💬 WhatsApp</label><input name="reseau_whatsapp" value="${esc(s.reseau_whatsapp||'')}" placeholder="https://wa.me/224..."></div>
          </div>

          <div class="form-section">
            <div class="form-section-title">🎓 Vie scolaire — « Au-delà des salles de classe »</div>
            <div class="text-muted mb-3" style="font-size:12px">Ces cartes s'affichent sur le site public. Sans modification ici, les 4 exemples par défaut (Cantine, Cours de révision, Activités parascolaires, Transport) restent affichés.</div>
            <div id="services-list" style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px">
              ${(servicesVieScolaire||[]).map((sv, i) => `
                <div class="flex items-center gap-3" style="border:1px solid #E5E7EB;border-radius:8px;padding:10px 12px">
                  <div style="font-size:22px">${esc(sv.icone||'⭐')}</div>
                  <div style="flex:1">
                    <div style="font-weight:600;font-size:13.5px">${esc(sv.titre||'')}</div>
                    <div class="text-muted" style="font-size:12px">${esc(sv.description||'')}</div>
                  </div>
                  <button type="button" class="btn btn-outline btn-xs" onclick="modalServiceVieScolaire(${i})">✏️</button>
                  <button type="button" class="btn btn-danger btn-xs" onclick="supprimerServiceVieScolaire(${i})">🗑</button>
                </div>`).join('') || '<span class="text-muted" style="font-size:12px">Aucun service personnalisé — les 4 exemples par défaut sont affichés.</span>'}
            </div>
            <button type="button" class="btn btn-outline btn-sm" onclick="modalServiceVieScolaire()">+ Ajouter un service</button>
          </div>

          <div class="form-section">
            <div class="form-section-title">🏫 Section « Notre établissement »</div>
            <div class="fg"><label>Titre affiché</label><input name="etablissement_titre" value="${esc(s.etablissement_titre||'Un repère éducatif à Sonfonia')}"></div>
            <div class="fg"><label>Texte de présentation</label><textarea name="etablissement_texte" rows="4" placeholder="Implanté à Yattaya...">${esc(s.etablissement_texte||'')}</textarea></div>
          </div>

          <div class="form-section">
            <div class="form-section-title">🎓 Nos cycles — contenu détaillé (affiché au clic sur chaque cycle)</div>
            <div class="text-muted mb-3" style="font-size:12px">Pour chaque cycle : une accroche courte (carte) et un détail complet (Objectif, Pédagogie, Activités, Équipements) affiché dans une fenêtre au clic. Vous pouvez en ajouter ou en retirer librement.</div>
            <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px">
              ${Object.entries(cyclesDetail).filter(([_, c]) => !c._supprime).map(([cle, c]) => `
                <div class="flex items-center gap-3" style="border:1px solid #E5E7EB;border-radius:8px;padding:10px 12px">
                  <div style="font-size:22px">${esc(c.icone||'🎓')}</div>
                  <div style="flex:1"><div style="font-weight:600;font-size:13.5px">${esc(c.titre||cle)}</div>
                    <div class="text-muted" style="font-size:12px">${esc(c.accroche||'')}</div></div>
                  <button type="button" class="btn btn-outline btn-xs" onclick="modalCycleDetail('${esc(cle)}')">✏️ Modifier</button>
                  <button type="button" class="btn btn-danger btn-xs" onclick="supprimerCycle('${esc(cle)}')">🗑</button>
                </div>`).join('')}
            </div>
            <button type="button" class="btn btn-outline btn-sm" onclick="modalCycleDetail()">+ Ajouter un cycle</button>
          </div>

          <div class="form-section">
            <div class="form-section-title">📍 Localisation (carte « Venez nous rencontrer »)</div>
            <div class="text-muted mb-3" style="font-size:12px">Astuce : ouvrez Google Maps, faites un clic droit sur l'emplacement exact de l'école, cliquez sur les coordonnées affichées pour les copier.</div>
            <div class="form-2">
              <div class="fg"><label>Latitude</label><input name="carte_latitude" value="${esc(s.carte_latitude||'')}" placeholder="9.6412"></div>
              <div class="fg"><label>Longitude</label><input name="carte_longitude" value="${esc(s.carte_longitude||'')}" placeholder="-13.6250"></div>
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

    $('#fond-file').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('fond', file);
      try {
        await apiUpload('/settings/fond', fd);
        toast('Fond du site mis à jour', 'success');
        pageSettings();
      } catch(err) { toast(err.message, 'error'); }
    });

    $('#carousel-file').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('image', file);
      try {
        await apiUpload('/settings/carousel', fd);
        toast('Image ajoutée au carrousel', 'success');
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

async function _getServicesVieScolaire() {
  const s = await apiGetSettings();
  try { return JSON.parse(s.services_vie_scolaire || '[]'); } catch(_) { return []; }
}
async function _saveServicesVieScolaire(liste) {
  await apiSaveSettings({ services_vie_scolaire: JSON.stringify(liste) });
}

async function modalServiceVieScolaire(index) {
  const liste = await _getServicesVieScolaire();
  const existant = (index !== undefined) ? liste[index] : { icone: '', titre: '', description: '' };
  openModal(index !== undefined ? 'Modifier ce service' : 'Ajouter un service', `
    <form id="f-service-vs" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>Icône (un émoji, ex : 🍽️ ⚽ 🚌 🎨)</label><input name="icone" value="${esc(existant.icone||'')}" placeholder="⭐" required></div>
      <div class="fg"><label>Titre*</label><input name="titre" value="${esc(existant.titre||'')}" required></div>
      <div class="fg"><label>Description*</label><textarea name="description" rows="3" required>${esc(existant.description||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });

  $('#f-service-vs').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const listeMaj = await _getServicesVieScolaire();
    if (index !== undefined) listeMaj[index] = fd; else listeMaj.push(fd);
    try {
      await _saveServicesVieScolaire(listeMaj);
      toast('Service enregistré', 'success');
      closeModal();
      pageSettings();
    } catch(err) { toast(err.message, 'error'); }
  };
}
window.modalServiceVieScolaire = modalServiceVieScolaire;

async function supprimerServiceVieScolaire(index) {
  if (!confirm('Supprimer ce service ?')) return;
  try {
    const liste = await _getServicesVieScolaire();
    liste.splice(index, 1);
    await _saveServicesVieScolaire(liste);
    toast('Service supprimé', 'success');
    pageSettings();
  } catch(err) { toast(err.message, 'error'); }
}
window.supprimerServiceVieScolaire = supprimerServiceVieScolaire;

async function modalCycleDetail(cle) {
  const s = await apiGetSettings();
  let cycles = {};
  try { cycles = JSON.parse(s.cycles_detail || '{}'); } catch(_) { cycles = {}; }
  const defauts = {
    maternelle:{titre:'Maternelle',icone:'🧸',accroche:'Éveil, langage et premiers repères, dans un cadre rassurant.'},
    primaire:{titre:'Primaire',icone:'📘',accroche:'Lecture, écriture, calcul : les fondamentaux, bien ancrés.'},
    college:{titre:'Collège',icone:'🔬',accroche:"Ouverture disciplinaire et méthode de travail affirmée."},
    lycee:{titre:'Lycée',icone:'🎓',accroche:"Préparation exigeante au baccalauréat et à l'après-bac."},
  };
  const estNouveau = cle === undefined;
  const c = estNouveau ? { titre:'', icone:'🎓', accroche:'' } : { ...(defauts[cle]||{titre:cle,icone:'🎓',accroche:''}), ...(cycles[cle]||{}) };

  openModal(estNouveau ? 'Ajouter un cycle' : `Modifier — ${c.titre}`, `
    <form id="f-cycle-detail" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Icône</label><input name="icone" value="${esc(c.icone||'')}"></div>
        <div class="fg"><label>Titre*</label><input name="titre" value="${esc(c.titre||'')}" required></div>
      </div>
      <div class="fg"><label>Accroche courte (affichée sur la carte)*</label><input name="accroche" value="${esc(c.accroche||'')}" required></div>
      <div class="fg"><label>Présentation</label><textarea name="presentation" rows="3" placeholder="Paragraphe d'introduction affiché en haut de la fenêtre de détail">${esc(c.presentation||'')}</textarea></div>
      <div class="fg"><label>🎯 Objectif</label><textarea name="objectif" rows="3">${esc(c.objectif||'')}</textarea></div>
      <div class="fg"><label>📚 Pédagogie</label><textarea name="pedagogie" rows="3">${esc(c.pedagogie||'')}</textarea></div>
      <div class="fg"><label>🎨 Activités</label><textarea name="activites" rows="3">${esc(c.activites||'')}</textarea></div>
      <div class="fg"><label>🏫 Équipements</label><textarea name="equipements" rows="3">${esc(c.equipements||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`);

  $('#f-cycle-detail').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    let cleFinale = cle;
    if (estNouveau) {
      let base = fd.titre.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'cycle';
      cleFinale = base;
      let i = 2;
      while (cycles[cleFinale]) { cleFinale = `${base}-${i}`; i++; }
    }
    cycles[cleFinale] = fd;
    try {
      await apiSaveSettings({ cycles_detail: JSON.stringify(cycles) });
      toast(estNouveau ? 'Cycle ajouté' : 'Cycle mis à jour', 'success');
      closeModal();
      pageSettings();
    } catch(err) { toast(err.message, 'error'); }
  };
}
window.modalCycleDetail = modalCycleDetail;

async function supprimerCycle(cle) {
  if (!confirm('Supprimer ce cycle ? Il ne sera plus affiché sur le site.')) return;
  try {
    const s = await apiGetSettings();
    let cycles = {};
    try { cycles = JSON.parse(s.cycles_detail || '{}'); } catch(_) { cycles = {}; }
    // On mémorise explicitement une suppression, y compris pour un cycle par défaut
    // (maternelle/primaire/collège/lycée), qui sinon réapparaîtrait automatiquement.
    cycles[cle] = { ...(cycles[cle]||{}), _supprime: true };
    await apiSaveSettings({ cycles_detail: JSON.stringify(cycles) });
    toast('Cycle supprimé', 'success');
    pageSettings();
  } catch(err) { toast(err.message, 'error'); }
}
window.supprimerCycle = supprimerCycle;

async function retirerFond() {
  if (!confirm("Revenir à l'apparence par défaut du site (fond blanc, bleu ciel, jaune pâle) ?")) return;
  try {
    await apiFetch('/settings/fond', { method: 'DELETE' });
    toast('Fond par défaut restauré', 'success');
    pageSettings();
  } catch(err) { toast(err.message, 'error'); }
}
window.retirerFond = retirerFond;

async function retirerImageCarousel(url) {
  if (!confirm('Retirer cette image du carrousel ?')) return;
  try {
    await apiFetch('/settings/carousel', { method: 'DELETE', body: { url } });
    toast('Image retirée', 'success');
    pageSettings();
  } catch(err) { toast(err.message, 'error'); }
}
window.retirerImageCarousel = retirerImageCarousel;
