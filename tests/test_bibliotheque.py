"""Bibliothèque : catalogue, prêts, limites, retours, retards, droits."""
from datetime import date, timedelta

import pytest


@pytest.fixture
def livre(client, entetes):
    r = client.post('/api/bibliotheque/livres', json={'titre': 'Le Petit Prince', 'auteur': 'Saint-Exupéry', 'exemplaires': 2}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_catalogue_recherche_et_validation(client, entetes, livre):
    assert client.post('/api/bibliotheque/livres', json={'titre': ' '}, headers=entetes).status_code == 400
    assert client.post('/api/bibliotheque/livres', json={'titre': 'X', 'exemplaires': -1}, headers=entetes).status_code == 400
    r = client.get('/api/bibliotheque/livres?q=prince', headers=entetes).get_json()
    assert any(l['id'] == livre['id'] and l['disponibles'] == 2 for l in r)
    assert client.get('/api/bibliotheque/livres?q=zzzintrouvable', headers=entetes).get_json() == []


def test_pret_disponibilite_et_retour(client, entetes, creer_eleve, livre):
    e1, e2, e3 = (creer_eleve(nom=f'Lecteur{i}', prenom='Test') for i in range(3))
    p1 = client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': e1['id']}, headers=entetes)
    assert p1.status_code == 201
    assert p1.get_json()['date_retour_prevue'] == (date.today() + timedelta(days=14)).isoformat()
    assert client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': e1['id']}, headers=entetes).status_code == 409   # déjà ce livre
    assert client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': e2['id']}, headers=entetes).status_code == 201
    r = client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': e3['id']}, headers=entetes)
    assert r.status_code == 409 and 'exemplaire' in r.get_json()['error']                                                                       # plus d'exemplaire
    ligne = next(l for l in client.get('/api/bibliotheque/livres', headers=entetes).get_json() if l['id'] == livre['id'])
    assert ligne['disponibles'] == 0
    assert client.delete(f"/api/bibliotheque/livres/{livre['id']}", headers=entetes).status_code == 409                                         # prêts en cours
    assert client.put(f"/api/bibliotheque/livres/{livre['id']}", json={'exemplaires': 1}, headers=entetes).status_code == 400
    assert client.post(f"/api/bibliotheque/prets/{p1.get_json()['id']}/retour", headers=entetes).status_code == 200
    assert client.post(f"/api/bibliotheque/prets/{p1.get_json()['id']}/retour", headers=entetes).status_code == 409
    assert client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': e3['id']}, headers=entetes).status_code == 201


def test_limite_par_emprunteur_et_retard(client, entetes, creer_eleve):
    import database
    e = creer_eleve(nom='Gourmand', prenom='Livres')
    ids = []
    for i in range(4):
        l = client.post('/api/bibliotheque/livres', json={'titre': f'Tome {i}', 'exemplaires': 5}, headers=entetes).get_json()
        ids.append(l['id'])
    prets = []
    for lid in ids[:3]:
        r = client.post('/api/bibliotheque/prets', json={'livre_id': lid, 'emprunteur_id': e['id'], 'jours': 7}, headers=entetes)
        assert r.status_code == 201
        prets.append(r.get_json())
    assert 'déjà empruntés' in client.post('/api/bibliotheque/prets', json={'livre_id': ids[3], 'emprunteur_id': e['id']}, headers=entetes).get_json()['error']
    # un prêt dépasse la date de retour -> l'emprunteur est bloqué et le prêt apparaît « en retard »
    hier = (date.today() - timedelta(days=3)).isoformat()
    database.db.execute("UPDATE prets_livres SET date_retour_prevue=? WHERE id=?", (hier, prets[0]['id'])); database.db.commit()
    retards = client.get('/api/bibliotheque/prets?statut=retard', headers=entetes).get_json()
    assert [p['id'] for p in retards if p['emprunteur_id'] == e['id']] == [prets[0]['id']] and retards[0]['jours_retard'] >= 3
    client.post(f"/api/bibliotheque/prets/{prets[1]['id']}/retour", headers=entetes)
    assert 'retard' in client.post('/api/bibliotheque/prets', json={'livre_id': ids[3], 'emprunteur_id': e['id']}, headers=entetes).get_json()['error']
    s = client.get('/api/bibliotheque/stats', headers=entetes).get_json()
    assert s['en_retard'] >= 1 and s['prets_en_cours'] >= 2


def test_eleve_inconnu_et_droits(client, entetes, livre):
    assert client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': 'inconnu'}, headers=entetes).status_code == 404
    client.post('/api/users', json={'username': 'ens_biblio', 'password': 'Provisoire-1', 'full_name': 'Ens', 'role': 'enseignant'}, headers=entetes)
    t = client.post('/api/auth/login', json={'username': 'ens_biblio', 'password': 'Provisoire-1'}).get_json()['token']
    c = client.post('/api/auth/change-password', json={'oldPassword': 'Provisoire-1', 'newPassword': 'Solide-2026'}, headers={'Authorization': f'Bearer {t}'}).get_json()['token']
    h = {'Authorization': f'Bearer {c}'}
    assert client.get('/api/bibliotheque/livres', headers=h).status_code == 200                       # un enseignant consulte
    assert client.post('/api/bibliotheque/livres', json={'titre': 'Interdit'}, headers=h).status_code == 403   # mais ne gère pas
    assert client.post('/api/bibliotheque/prets', json={'livre_id': livre['id'], 'emprunteur_id': 'x'}, headers=h).status_code == 403
