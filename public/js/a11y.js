/* ===================== ACCESSIBILITÉ (WCAG 2.1 AA) =====================
   Améliorations transversales appliquées à toute l'interface, y compris aux écrans générés dynamiquement :
   lien d'évitement, repères de page, fenêtres modales annoncées et fermables au clavier (Échap), messages
   annoncés par les lecteurs d'écran, libellés explicites sur les boutons-icônes, champs reliés à leur étiquette. */
(function () {
  'use strict';
  let seq = 0;

  function reperes() {
    const content = document.getElementById('content');
    if (content) { content.setAttribute('role', 'main'); content.setAttribute('tabindex', '-1'); content.setAttribute('aria-live', 'off'); }
    const sb = document.querySelector('.sidebar, #sidebar');
    if (sb && !sb.getAttribute('aria-label')) sb.setAttribute('aria-label', 'Navigation principale');
    const top = document.querySelector('.topbar');
    if (top) top.setAttribute('role', 'banner');
    const toasts = document.getElementById('toasts');
    if (toasts) { toasts.setAttribute('role', 'status'); toasts.setAttribute('aria-live', 'polite'); toasts.setAttribute('aria-atomic', 'true'); }
    if (!document.getElementById('skip-link')) {
      const a = document.createElement('a');
      a.id = 'skip-link'; a.href = '#content'; a.className = 'skip-link'; a.textContent = 'Aller au contenu principal';
      a.addEventListener('click', e => { e.preventDefault(); const c = document.getElementById('content'); if (c) c.focus(); });
      document.body.insertBefore(a, document.body.firstChild);
    }
  }

  function enrichir(racine) {
    // Boutons / liens sans texte lisible : on reprend leur infobulle (title)
    racine.querySelectorAll('button, a, [role=button]').forEach(el => {
      if (el.hasAttribute('aria-label')) return;
      const texte = (el.textContent || '').replace(/[\s​]/g, '');
      const alpha = /[A-Za-zÀ-ÿ0-9]/.test(texte);
      if (!alpha && el.title) el.setAttribute('aria-label', el.title);
    });
    // Champs de formulaire reliés à leur étiquette (.fg > label + champ)
    racine.querySelectorAll('.fg').forEach(fg => {
      const label = fg.querySelector('label');
      const champ = fg.querySelector('input:not([type=hidden]), select, textarea');
      if (!label || !champ || label.htmlFor || champ.getAttribute('aria-label') || champ.getAttribute('aria-labelledby')) return;
      if (!champ.id) champ.id = 'f-auto-' + (++seq);
      label.htmlFor = champ.id;
      if (champ.required) champ.setAttribute('aria-required', 'true');
    });
    // Tableaux : en-têtes de colonnes
    racine.querySelectorAll('th:not([scope])').forEach(th => th.setAttribute('scope', 'col'));
    // Images décoratives ou sans description
    racine.querySelectorAll('img:not([alt])').forEach(img => img.setAttribute('alt', ''));
    // Messages d'erreur annoncés
    racine.querySelectorAll('.alert-danger, .alert-error').forEach(el => { if (!el.hasAttribute('role')) el.setAttribute('role', 'alert'); });
  }

  function modales() {
    document.querySelectorAll('#modal-bg').forEach(bg => {
      const box = bg.querySelector('#modal-box, .modal-box-el');
      if (box && bg.style.display !== 'none') {
        box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true');
        const titre = bg.querySelector('#modal-title');
        if (titre) { if (!titre.id) titre.id = 'modal-title'; box.setAttribute('aria-labelledby', titre.id); }
        if (!box.contains(document.activeElement)) {
          const premier = box.querySelector('input:not([type=hidden]):not([disabled]), select, textarea, button.btn-primary');
          if (premier) premier.focus({ preventScroll: true });
        }
      }
    });
  }

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const bg = document.getElementById('modal-bg');
    if (bg && bg.style.display !== 'none' && typeof window.closeModal === 'function') {
      e.preventDefault();
      window.closeModal({ currentTarget: bg });
    }
  });

  let planifie = false;
  const observateur = new MutationObserver(() => {
    if (planifie) return;
    planifie = true;
    requestAnimationFrame(() => { planifie = false; reperes(); enrichir(document); modales(); });
  });
  function demarrer() {
    reperes(); enrichir(document);
    observateur.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style'] });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer); else demarrer();

  // Langue du document et sens de lecture suivent la langue choisie
  window.addEventListener('storage', () => {});
  const langue = () => { try { return localStorage.getItem('gs_lang') || localStorage.getItem('lang') || document.documentElement.lang || 'fr'; } catch (_) { return 'fr'; } };
  const l = langue(); document.documentElement.lang = l; document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr';
})();
