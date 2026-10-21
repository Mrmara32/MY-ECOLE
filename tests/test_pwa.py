"""Installation sur Android / iPhone : manifeste, icônes, balises."""
import json


def test_manifeste_valide(client):
    r = client.get('/manifest.webmanifest')
    assert r.status_code == 200 and 'manifest+json' in r.mimetype
    m = json.loads(r.get_data(as_text=True))
    assert m['display'] == 'standalone' and m['start_url'] == '/'
    tailles = {(i['sizes'], i.get('purpose', 'any')) for i in m['icons']}
    assert ('192x192', 'any') in tailles and ('512x512', 'any') in tailles and ('512x512', 'maskable') in tailles
    for i in m['icons']:
        assert client.get(i['src']).status_code == 200


def test_page_d_accueil_reference_le_manifeste_et_les_icones_apple(client):
    html = client.get('/').get_data(as_text=True)
    assert 'rel="manifest"' in html and 'apple-touch-icon' in html and 'theme-color' in html
    assert client.get('/icons/apple-touch-icon.png').status_code == 200
    assert client.get('/js/pwa.js').status_code == 200
