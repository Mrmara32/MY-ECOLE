/* ===================== ACTUALITÉS & RÉSEAUX SOCIAUX ===================== */
let _actuSettings = {};
async function pageActualites() {
  $('#content').innerHTML = loadingHtml;
  try {
    const [articles, settings] = await Promise.all([apiGetArticlesAdmin(), apiGetSettings()]);
    _actuSettings = settings;

    const reseaux = [
      { cle:'reseau_facebook', label:'Facebook', icon:'📘' },
      { cle:'reseau_instagram', label:'Instagram', icon:'📷' },
      { cle:'reseau_youtube', label:'YouTube', icon:'▶️' },
      { cle:'reseau_tiktok', label:'TikTok', icon:'🎵' },
      { cle:'reseau_whatsapp', label:'WhatsApp', icon:'💬' },
    ].filter(r => settings[r.cle]);

    $('#content').innerHTML = `
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">📰 Articles & Événements (${articles.length})</span>
        <button class="btn btn-primary btn-sm" onclick="modalArticle()">+ Publier un article</button>
      </div>
      <div class="card-body">
        <div id="articles-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">🔗 Réseaux sociaux de l'école</span>
        <button class="btn btn-outline btn-sm" onclick="modalReseauxSociaux()">✏️ Modifier les liens</button>
      </div>
      <div class="card-body">
        ${reseaux.length ? `<div class="flex gap-3 flex-wrap">
          ${reseaux.map(r => `<a href="${esc(settings[r.cle])}" target="_blank" rel="noopener" class="btn btn-outline">${r.icon} ${r.label}</a>`).join('')}
        </div>` : emptyHtml('🔗','Aucun réseau social configuré','Cliquez sur "Modifier les liens" pour en ajouter')}
      </div>
    </div>`;

    const grid = $('#articles-grid');
    grid.innerHTML = articles.length ? articles.map(a => {
      const photo = a.media.find(m => m.type === 'photo');
      return `<div class="card" style="overflow:hidden">
        ${photo ? `<img src="${esc(photo.url)}" style="width:100%;height:150px;object-fit:cover" onerror="this.style.display='none'">` : ''}
        <div class="card-body">
          <div class="flex justify-between items-center mb-2">
            <span class="badge ${a.type==='evenement'?'bdg-primary':'bdg-gray'}">${a.type==='evenement'?'📅 Événement':'📰 Article'}</span>
            <span class="badge ${a.publie?'bdg-ok':'bdg-gray'}">${a.publie?'Publié':'Brouillon'}</span>
          </div>
          <div class="fw-600 mb-2">${esc(a.titre)}</div>
          <div class="text-muted" style="font-size:12px;margin-bottom:8px">${esc(a.auteur_nom||'')} · ${fmtDate(a.date_publication)}</div>
          <div style="font-size:13px;margin-bottom:10px">${esc((a.contenu||'').substring(0,120))}${(a.contenu||'').length>120?'…':''}</div>
          ${a.media.length ? `<div class="text-muted mb-2" style="font-size:11px">📎 ${a.media.length} média(s)</div>` : ''}
          <div class="td-actions">
            <button class="btn btn-outline btn-xs" onclick="modalArticle('${escJs(a.id)}')">✏️ Gérer</button>
            <button class="btn btn-danger btn-xs" onclick="delArticle('${escJs(a.id)}')">🗑</button>
          </div>
        </div>
      </div>`;
    }).join('') : emptyHtml('📰','Aucun article publié pour le moment');
  } catch(e) { $('#content').innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}

async function modalArticle(id = null) {
  let data = { titre:'', contenu:'', type:'article', publie:true, media:[] };
  if (id) data = await apiGetArticle(id);

  openModal(id ? 'Gérer l\'article' : 'Publier un nouvel article', `
    <form id="f-article" style="display:flex;flex-direction:column;gap:14px">
      <div class="form-2">
        <div class="fg"><label>Type</label><select name="type">
          <option value="article" ${data.type==='article'?'selected':''}>📰 Article</option>
          <option value="evenement" ${data.type==='evenement'?'selected':''}>📅 Événement</option>
        </select></div>
        <div class="fg"><label>Statut</label><select name="publie">
          <option value="1" ${data.publie?'selected':''}>Publié</option>
          <option value="0" ${!data.publie?'selected':''}>Brouillon</option>
        </select></div>
      </div>
      <div class="fg"><label>Titre*</label><input name="titre" value="${esc(data.titre||'')}" required></div>
      <div class="fg"><label>Contenu</label><textarea name="contenu" rows="5">${esc(data.contenu||'')}</textarea></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">${id?'Enregistrer':'Publier'}</button>
      </div>
    </form>
    ${id ? `
    <div class="sep"></div>
    <div class="form-section-title">Photos & vidéos</div>
    <div id="media-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:10px;margin-bottom:14px">
      ${data.media.map(m => `<div style="position:relative">
        ${m.type==='photo'
          ? `<img src="${esc(m.url)}" style="width:100%;height:80px;object-fit:cover;border-radius:6px">`
          : `<video src="${esc(m.url)}" style="width:100%;height:80px;object-fit:cover;border-radius:6px" controls></video>`}
        <button class="btn btn-danger btn-xs" style="position:absolute;top:2px;right:2px" onclick="delMedia('${escJs(m.id)}','${escJs(id)}')">✕</button>
      </div>`).join('')}
    </div>
    <label class="btn btn-outline btn-sm" style="cursor:pointer">
      📎 Ajouter une photo ou vidéo
      <input type="file" id="media-file" accept="image/*,video/*" style="display:none">
    </label>
    ` : `<div class="text-muted mt-3" style="font-size:12px">💡 Enregistrez d'abord l'article pour pouvoir y ajouter des photos et vidéos.</div>`}
  `, { wide: true });

  if (id) {
    $('#media-file').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('fichier', file);
      try { await apiUploadArticleMedia(id, fd); toast('Média ajouté','success'); modalArticle(id); }
      catch(err) { toast(err.message,'error'); }
    });
  }

  $('#f-article').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.publie = fd.publie === '1';
    try {
      if (id) { await apiUpdateArticle(id, fd); toast('Article mis à jour','success'); }
      else { const created = await apiCreateArticle(fd); toast('Article publié','success'); closeModal(); modalArticle(created.id); pageActualites(); return; }
      closeModal(); pageActualites();
    } catch(err) { toast(err.message,'error'); }
  };
}

async function delMedia(mediaId, articleId) {
  if (!confirmDel('Supprimer ce média ?')) return;
  try { await apiDeleteArticleMedia(mediaId); toast('Média supprimé','success'); modalArticle(articleId); }
  catch(e) { toast(e.message,'error'); }
}

async function delArticle(id) {
  if (!confirmDel('Supprimer cet article et tous ses médias ?')) return;
  try { await apiDeleteArticle(id); toast('Supprimé','success'); pageActualites(); }
  catch(e) { toast(e.message,'error'); }
}

function modalReseauxSociaux() {
  const settings = _actuSettings;
  openModal('Liens des réseaux sociaux', `
    <form id="f-reseaux" style="display:flex;flex-direction:column;gap:14px">
      <div class="fg"><label>📘 Facebook</label><input name="reseau_facebook" value="${esc(settings.reseau_facebook||'')}" placeholder="https://facebook.com/votre-ecole"></div>
      <div class="fg"><label>📷 Instagram</label><input name="reseau_instagram" value="${esc(settings.reseau_instagram||'')}" placeholder="https://instagram.com/votre-ecole"></div>
      <div class="fg"><label>▶️ YouTube</label><input name="reseau_youtube" value="${esc(settings.reseau_youtube||'')}" placeholder="https://youtube.com/@votre-ecole"></div>
      <div class="fg"><label>🎵 TikTok</label><input name="reseau_tiktok" value="${esc(settings.reseau_tiktok||'')}" placeholder="https://tiktok.com/@votre-ecole"></div>
      <div class="fg"><label>💬 WhatsApp</label><input name="reseau_whatsapp" value="${esc(settings.reseau_whatsapp||'')}" placeholder="https://wa.me/224XXXXXXXXX"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>`, { narrow: true });
  $('#f-reseaux').onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    try { await apiSaveSettings(fd); toast('Liens mis à jour','success'); closeModal(); pageActualites(); }
    catch(err) { toast(err.message,'error'); }
  };
}
window.modalArticle = modalArticle;
window.delArticle = delArticle;
window.delMedia = delMedia;
window.modalReseauxSociaux = modalReseauxSociaux;
