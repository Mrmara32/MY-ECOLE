/* Installation de MY-ECOLE sur l'écran d'accueil (Android, iPhone/iPad, ordinateur).
 *  - Android / Chrome / Edge : le navigateur propose l'installation → bouton « 📲 Installer ».
 *  - iPhone / iPad (Safari) : pas de bouton système → une aide indique « Partager → Sur l'écran d'accueil ».
 * Une fois installée, l'application s'ouvre en plein écran, comme une application native. */
(function () {
  'use strict';
  const dejaInstallee = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  let invite = null;

  function bouton() {
    let b = document.getElementById('btn-installer');
    if (b) return b;
    const zone = document.querySelector('.topbar-right');
    if (!zone) return null;
    b = document.createElement('button');
    b.id = 'btn-installer'; b.className = 'btn btn-outline btn-sm'; b.type = 'button';
    b.textContent = '📲 Installer'; b.title = "Installer l'application sur cet appareil"; b.style.display = 'none';
    zone.insertBefore(b, zone.firstChild);
    return b;
  }

  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault(); invite = e;
    if (dejaInstallee()) return;
    const b = bouton(); if (!b) return;
    b.style.display = '';
    b.onclick = async () => {
      if (!invite) return;
      invite.prompt();
      try { await invite.userChoice; } catch (x) {}
      invite = null; b.style.display = 'none';
    };
  });
  window.addEventListener('appinstalled', () => { const b = document.getElementById('btn-installer'); if (b) b.style.display = 'none'; });

  // iPhone / iPad : explication unique (Safari ne propose pas d'invite d'installation)
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  function aideIos() {
    if (!ios || dejaInstallee()) return;
    try { if (localStorage.getItem('gs_aide_ios')) return; } catch (e) { /* stockage indisponible : on affiche quand même */ }
    const bandeau = document.createElement('div');
    bandeau.setAttribute('role', 'status');
    bandeau.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;background:#1E3A8A;color:#fff;padding:12px 14px;border-radius:12px;font-size:14px;box-shadow:0 6px 24px rgba(0,0,0,.3)';
    bandeau.innerHTML = "📲 Pour installer MY-ECOLE : touchez <b>Partager</b> (carré avec une flèche) puis <b>Sur l'écran d'accueil</b>. " +
      '<button type="button" style="margin-left:8px;background:#fff;color:#1E3A8A;border:0;border-radius:8px;padding:4px 10px;font-weight:600">OK</button>';
    bandeau.querySelector('button').addEventListener('click', () => {
      try { localStorage.setItem('gs_aide_ios', '1'); } catch (e) {}
      bandeau.remove();
    });
    document.body.appendChild(bandeau);
  }
  window.addEventListener('load', () => setTimeout(aideIos, 4000));
})();
