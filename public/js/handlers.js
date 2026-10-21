/* Gestionnaires d'événements sans « script en ligne » (CSP stricte : pas de 'unsafe-inline').
 *
 * Le code de l'interface produit du HTML contenant des attributs onclick="fonction('a', 1)".
 * Le navigateur n'exécute plus ces attributs (la politique de sécurité les bloque) : ce fichier les
 * lit et les exécute lui-même avec un petit interpréteur volontairement limité :
 *   - appels de fonctions DE L'APPLICATION (jamais de code natif arbitraire : pas d'eval, de fetch,
 *     de Function, de cookie, de stockage…) ;
 *   - quelques méthodes natives inoffensives (remove, select, preventDefault, window.open…) ;
 *   - littéraux, this / event, opérateurs simples, if/else, affectations de variables et de
 *     propriétés non dangereuses.
 * Tout le reste est refusé et journalisé dans la console. Aucun accès à eval ni à new Function.
 */
(function () {
  'use strict';

  /* ───────── 1. Analyse lexicale ───────── */
  const PONCT3 = ['===', '!=='];
  const PONCT2 = ['==', '!=', '<=', '>=', '&&', '||', '=>', '++', '--'];
  function lexer(src) {
    const t = []; let i = 0;
    while (i < src.length) {
      const c = src[i];
      if (/\s/.test(c)) { i++; continue; }
      if (/[0-9]/.test(c) || (c === '.' && /[0-9]/.test(src[i + 1] || ''))) {
        let j = i; while (j < src.length && /[0-9.]/.test(src[j])) j++;
        t.push({ k: 'num', v: parseFloat(src.slice(i, j)) }); i = j; continue;
      }
      if (c === '"' || c === "'" || c === '`') {
        let j = i + 1, s = '';
        while (j < src.length && src[j] !== c) {
          if (src[j] === '\\') {
            const n = src[j + 1];
            s += n === 'n' ? '\n' : n === 't' ? '\t' : n === 'u' ? String.fromCharCode(parseInt(src.substr(j + 2, 4), 16)) : n;
            j += n === 'u' ? 6 : 2;
          } else if (c === '`' && src[j] === '$' && src[j + 1] === '{') {
            throw new Error('gabarit non pris en charge');
          } else s += src[j++];
        }
        t.push({ k: 'str', v: s }); i = j + 1; continue;
      }
      if (/[A-Za-z_$]/.test(c)) {
        let j = i; while (j < src.length && /[\w$]/.test(src[j])) j++;
        t.push({ k: 'id', v: src.slice(i, j) }); i = j; continue;
      }
      const p3 = src.substr(i, 3), p2 = src.substr(i, 2);
      if (PONCT3.includes(p3)) { t.push({ k: 'p', v: p3 }); i += 3; continue; }
      if (PONCT2.includes(p2)) { t.push({ k: 'p', v: p2 }); i += 2; continue; }
      t.push({ k: 'p', v: c }); i++;
    }
    return t;
  }

  /* ───────── 2. Analyse syntaxique → arbre ───────── */
  function analyser(src) {
    const t = lexer(src); let i = 0;
    const peek = () => t[i], suit = () => t[i++];
    const est = v => t[i] && t[i].k === 'p' && t[i].v === v;
    const estId = v => t[i] && t[i].k === 'id' && t[i].v === v;
    const attend = v => { if (!est(v)) throw new Error('« ' + v + ' » attendu'); i++; };

    function programme(finSur) {
      const l = [];
      while (i < t.length && !(finSur && est(finSur))) {
        if (est(';')) { i++; continue; }
        l.push(instruction());
      }
      return { t: 'prog', l };
    }
    function instruction() {
      if (estId('if')) {
        i++; attend('('); const c = expr(); attend(')');
        const a = instruction(); let b = null;
        if (est(';')) i++;
        if (estId('else')) { i++; b = instruction(); }
        return { t: 'if', c, a, b };
      }
      if (est('{')) { i++; const p = programme('}'); attend('}'); return p; }
      if (estId('return')) {
        i++; return { t: 'ret', e: (i >= t.length || est(';') || est('}')) ? null : expr() };
      }
      return expr();
    }
    function expr() { return affectation(); }
    function affectation() {
      const g = ternaire();
      if (est('=')) {
        if (g.t !== 'id' && g.t !== 'mb') throw new Error('affectation invalide');
        i++; return { t: 'aff', cible: g, v: affectation() };
      }
      return g;
    }
    function ternaire() {
      const c = ou();
      if (est('?')) { i++; const a = affectation(); attend(':'); const b = affectation(); return { t: 'ter', c, a, b }; }
      return c;
    }
    function ou() { let g = et(); while (est('||')) { i++; g = { t: 'bin', o: '||', a: g, b: et() }; } return g; }
    function et() { let g = egal(); while (est('&&')) { i++; g = { t: 'bin', o: '&&', a: g, b: egal() }; } return g; }
    function egal() {
      let g = compar();
      while (est('===') || est('!==') || est('==') || est('!=')) { const o = suit().v; g = { t: 'bin', o, a: g, b: compar() }; }
      return g;
    }
    function compar() {
      let g = somme();
      while (est('<') || est('>') || est('<=') || est('>=')) { const o = suit().v; g = { t: 'bin', o, a: g, b: somme() }; }
      return g;
    }
    function somme() {
      let g = produit();
      while (est('+') || est('-')) { const o = suit().v; g = { t: 'bin', o, a: g, b: produit() }; }
      return g;
    }
    function produit() {
      let g = unaire();
      while (est('*') || est('/') || est('%')) { const o = suit().v; g = { t: 'bin', o, a: g, b: unaire() }; }
      return g;
    }
    function unaire() {
      if (est('!')) { i++; return { t: 'non', e: unaire() }; }
      if (est('-')) { i++; return { t: 'neg', e: unaire() }; }
      if (estId('typeof')) { i++; return { t: 'typeof', e: unaire() }; }
      return suffixe();
    }
    function args() {
      const a = []; attend('(');
      while (!est(')')) { a.push(expr()); if (est(',')) i++; else break; }
      attend(')'); return a;
    }
    function flechePossible() {
      // () => … ou (x, y) => …
      let j = i + 1; const noms = [];
      while (t[j] && t[j].k === 'id') { noms.push(t[j].v); j++; if (t[j] && t[j].v === ',') j++; else break; }
      if (t[j] && t[j].v === ')' && t[j + 1] && t[j + 1].v === '=>') return { noms, fin: j + 2 };
      return null;
    }
    function suffixe() {
      let g = primaire();
      for (;;) {
        if (est('.')) { i++; const n = suit(); if (!n || n.k !== 'id') throw new Error('nom attendu'); g = { t: 'mb', o: g, p: { t: 'lit', v: n.v } }; }
        else if (est('[')) { i++; const p = expr(); attend(']'); g = { t: 'mb', o: g, p }; }
        else if (est('(')) { g = { t: 'app', f: g, a: args() }; }
        else break;
      }
      return g;
    }
    function primaire() {
      const x = suit();
      if (!x) throw new Error('expression incomplète');
      if (x.k === 'num' || x.k === 'str') return { t: 'lit', v: x.v };
      if (x.k === 'id') {
        if (x.v === 'true') return { t: 'lit', v: true };
        if (x.v === 'false') return { t: 'lit', v: false };
        if (x.v === 'null') return { t: 'lit', v: null };
        if (x.v === 'undefined') return { t: 'lit', v: undefined };
        return { t: 'id', n: x.v };
      }
      if (x.v === '(') {
        i--; const f = flechePossible();
        if (f) { i = f.fin; return { t: 'fl', noms: f.noms, c: affectation() }; }
        i++; const e = expr(); attend(')'); return e;
      }
      if (x.v === '[') {
        const l = []; while (!est(']')) { l.push(expr()); if (est(',')) i++; else break; } attend(']');
        return { t: 'tab', l };
      }
      if (x.v === '{') {
        const o = [];
        while (!est('}')) {
          const k = suit(); if (!k || (k.k !== 'str' && k.k !== 'id' && k.k !== 'num')) throw new Error('clé attendue');
          attend(':'); o.push([String(k.v), expr()]); if (est(',')) i++; else break;
        }
        attend('}'); return { t: 'obj', o };
      }
      throw new Error('« ' + x.v + ' » inattendu');
    }
    const p = programme(null);
    if (i < t.length) throw new Error('fin inattendue');
    return p;
  }

  /* ───────── 3. Règles de sécurité ───────── */
  const NOMS_INTERDITS = new Set(['constructor', '__proto__', 'prototype', 'eval', 'Function', 'fetch', 'XMLHttpRequest',
    'WebSocket', 'importScripts', 'import', 'localStorage', 'sessionStorage', 'indexedDB', 'cookie', 'document.write',
    'write', 'writeln', 'innerHTML', 'outerHTML', 'srcdoc', 'setTimeout', 'setInterval', 'execScript', 'defineProperty',
    'assign', 'sendBeacon', 'postMessage', 'opener', 'top', 'parent', 'eval']);
  const METHODES_NATIVES = new Set(['remove', 'select', 'toggle', 'add', 'closest', 'querySelector', 'querySelectorAll',
    'getElementById', 'insertAdjacentHTML', 'stopPropagation', 'preventDefault', 'then', 'writeText', 'open', 'print',
    'focus', 'blur', 'click', 'scrollIntoView', 'stringify', 'trim', 'toLowerCase', 'toUpperCase', 'includes',
    'toString', 'toFixed', 'getAttribute', 'setAttribute', 'removeAttribute', 'contains', 'back', 'reload']);
  const GLOBALES_NATIVES = new Set(['encodeURIComponent', 'decodeURIComponent', 'String', 'Number', 'parseInt',
    'parseFloat', 'Boolean', 'confirm', 'alert', 'prompt']);
  const PROTOCOLES_OK = /^(https?:|mailto:|tel:|sms:|whatsapp:|\/)/i;

  function refuse(msg) { throw new Error('refusé : ' + msg); }
  function nomOk(n) { if (NOMS_INTERDITS.has(n) || (typeof n === 'string' && /^on[a-z]+$/i.test(n))) refuse(n); return n; }
  function natif(f) { return /\{\s*\[native code\]\s*\}/.test(Function.prototype.toString.call(f)); }

  /* ───────── 4. Exécution ───────── */
  class Retour { constructor(v) { this.v = v; } }

  function evaluer(n, ctx) {
    switch (n.t) {
      case 'prog': { let r; for (const s of n.l) { r = evaluer(s, ctx); } return r; }
      case 'if': return evaluer(n.c, ctx) ? evaluer(n.a, ctx) : (n.b ? evaluer(n.b, ctx) : undefined);
      case 'ret': throw new Retour(n.e ? evaluer(n.e, ctx) : undefined);
      case 'lit': return n.v;
      case 'id':
        if (n.n === 'this') return ctx.el;
        if (n.n === 'event') return ctx.ev;
        if (n.n === 'window' || n.n === 'globalThis') return window;
        if (n.n === 'document') return document;
        if (n.n === 'navigator') return navigator;
        if (n.n === 'history') return history;
        nomOk(n.n);
        if (ctx.locaux && n.n in ctx.locaux) return ctx.locaux[n.n];
        if (!(n.n in window)) throw new ReferenceError(n.n + ' n\'est pas défini');
        return window[n.n];
      case 'mb': {
        const o = evaluer(n.o, ctx); const p = evaluer(n.p, ctx); nomOk(p);
        if (o == null) throw new TypeError('propriété de ' + o);
        return o[p];
      }
      case 'non': return !evaluer(n.e, ctx);
      case 'neg': return -evaluer(n.e, ctx);
      case 'typeof': try { return typeof evaluer(n.e, ctx); } catch (e) { return 'undefined'; }
      case 'ter': return evaluer(n.c, ctx) ? evaluer(n.a, ctx) : evaluer(n.b, ctx);
      case 'tab': return n.l.map(x => evaluer(x, ctx));
      case 'obj': { const o = {}; for (const [k, v] of n.o) { nomOk(k); o[k] = evaluer(v, ctx); } return o; }
      case 'fl': return (...vals) => {
        const locaux = Object.assign({}, ctx.locaux); n.noms.forEach((nm, k) => { locaux[nm] = vals[k]; });
        return evaluer(n.c, Object.assign({}, ctx, { locaux }));
      };
      case 'bin': {
        if (n.o === '&&') { const a = evaluer(n.a, ctx); return a ? evaluer(n.b, ctx) : a; }
        if (n.o === '||') { const a = evaluer(n.a, ctx); return a ? a : evaluer(n.b, ctx); }
        const a = evaluer(n.a, ctx), b = evaluer(n.b, ctx);
        switch (n.o) {
          case '+': return a + b; case '-': return a - b; case '*': return a * b; case '/': return a / b; case '%': return a % b;
          case '===': return a === b; case '!==': return a !== b; case '==': return a == b; case '!=': return a != b; // eslint-disable-line eqeqeq
          case '<': return a < b; case '>': return a > b; case '<=': return a <= b; case '>=': return a >= b;
        }
        throw new Error('opérateur ' + n.o);
      }
      case 'aff': {
        const v = evaluer(n.v, ctx);
        if (n.cible.t === 'id') {
          const nom = nomOk(n.cible.n);
          if (ctx.locaux && nom in ctx.locaux) ctx.locaux[nom] = v;
          else if (nom in ctx.variables) ctx.variables[nom] = v;   // variables « let » déclarées par l'application
          else window[nom] = v;
          return v;
        }
        const o = evaluer(n.cible.o, ctx); const p = nomOk(evaluer(n.cible.p, ctx));
        if (o === window.location && p === 'href') {
          if (typeof v !== 'string' || !PROTOCOLES_OK.test(v)) refuse('adresse ' + v);
        } else if (o === window.location) refuse('location');
        o[p] = v; return v;
      }
      case 'app': {
        let f, recepteur;
        if (n.f.t === 'mb') {
          recepteur = evaluer(n.f.o, ctx); const nom = nomOk(evaluer(n.f.p, ctx));
          if (recepteur == null) throw new TypeError('appel sur ' + recepteur);
          f = recepteur[nom];
          if (typeof f !== 'function') throw new TypeError(nom + ' n\'est pas une fonction');
          if (natif(f) && !METHODES_NATIVES.has(nom)) refuse('méthode ' + nom);
          const a = n.a.map(x => evaluer(x, ctx));
          if (nom === 'open' && recepteur === window) { if (typeof a[0] !== 'string' || !PROTOCOLES_OK.test(a[0])) refuse('open ' + a[0]); }
          if (nom === 'insertAdjacentHTML' && typeof a[1] !== 'string') refuse('insertAdjacentHTML');
          return f.apply(recepteur, a);
        }
        if (n.f.t === 'id') {
          const nom = nomOk(n.f.n);
          f = (ctx.locaux && nom in ctx.locaux) ? ctx.locaux[nom] : window[nom];
          if (typeof f !== 'function') throw new TypeError(nom + ' n\'est pas une fonction');
          if (natif(f) && !GLOBALES_NATIVES.has(nom)) refuse('fonction ' + nom);
          return f.apply(window, n.a.map(x => evaluer(x, ctx)));
        }
        f = evaluer(n.f, ctx);
        if (typeof f !== 'function') throw new TypeError('appel invalide');
        return f.apply(undefined, n.a.map(x => evaluer(x, ctx)));
      }
    }
    throw new Error('nœud ' + n.t);
  }

  /* Variables « let/const » de premier niveau déclarées par l'application : inaccessibles via window.
     Les gestionnaires n'y écrivent qu'à travers des fonctions (voir emploi.js), donc aucun cas ici. */
  const VARIABLES = {};

  const cache = new Map();
  function executer(source, el, ev) {
    let arbre = cache.get(source);
    if (!arbre) { arbre = analyser(source); cache.set(source, arbre); }
    try {
      // Dans un attribut natif, event.currentTarget est l'élément qui porte le gestionnaire (ici l'écoute
      // est posée sur document) : on le restitue, sans toucher à l'événement réel.
      const evp = ev && new Proxy(ev, {
        get(cible, k) { if (k === 'currentTarget') return el; const v = cible[k]; return typeof v === 'function' ? v.bind(cible) : v; },
      });
      const r = evaluer(arbre, { el, ev: evp, variables: VARIABLES, locaux: null });
      if (r === false && ev) ev.preventDefault();
    } catch (e) {
      if (e instanceof Retour) { if (e.v === false && ev) ev.preventDefault(); return; }
      console.error('[gestionnaire] « ' + source + ' » :', e.message || e);
    }
  }

  /* ───────── 5. Écoute globale (délégation) ───────── */
  ['click', 'change', 'input', 'keydown', 'error'].forEach(nom => {
    const attr = 'on' + nom;
    // « error » ne remonte pas : on l'écoute en phase de capture ; les autres remontent comme un attribut natif.
    document.addEventListener(nom, ev => {
      const chemin = ev.composedPath ? ev.composedPath() : [ev.target];
      for (const el of chemin) {
        if (!(el instanceof Element) || !el.hasAttribute(attr)) { if (nom === 'error') return; continue; }
        executer(el.getAttribute(attr), el, ev);
        if (ev.cancelBubble || nom === 'error') return;
      }
    }, nom === 'error');
  });

  window.__executerGestionnaire = executer;   // pour les tests
  window.__analyserGestionnaire = analyser;
})();
