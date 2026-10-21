"""CSP stricte : aucun script en ligne n'est autorisé, donc aucun ne doit subsister dans les pages."""
import glob
import re

import securite_http


def test_csp_sans_unsafe_inline_pour_les_scripts():
    script_src = [d for d in securite_http.CSP.split(';') if d.strip().startswith('script-src')][0]
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src


def test_aucun_script_en_ligne_dans_les_pages():
    for f in glob.glob('public/*.html'):
        html = open(f, encoding='utf-8').read()
        assert not re.search(r'<script(?![^>]*\bsrc=)[^>]*>', html), f"script en ligne dans {f}"
        assert '/js/handlers.js' in html, f"gestionnaire manquant dans {f}"


def test_aucun_script_en_ligne_genere_par_le_javascript():
    for f in glob.glob('public/js/**/*.js', recursive=True):
        if 'vendor' in f:
            continue
        src = open(f, encoding='utf-8').read()
        assert not re.search(r'document\.write\([^)]*<script', src), f
        assert not re.search(r"<script>\w", src), f"script en ligne généré dans {f}"


def test_entete_csp_servi(client):
    r = client.get('/')
    assert "script-src 'self'" in r.headers['Content-Security-Policy']
    assert "'unsafe-inline'" not in r.headers['Content-Security-Policy'].split('style-src')[0]


def test_interpreteur_charge_et_precache(client):
    assert client.get('/js/handlers.js').status_code == 200
    assert "/js/handlers.js" in client.get('/sw.js').get_data(as_text=True)


def test_pages_publiques_chargent_la_couche_accessibilite():
    for f in glob.glob('public/*.html'):
        if f.endswith(('confidentialite.html', 'conditions.html')):
            continue
        assert 'js/a11y.js' in open(f, encoding='utf-8').read(), f
