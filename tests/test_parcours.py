"""
Parcours essentiels de MY-ECOLE : s'ils cassent, l'école ne peut plus travailler.
"""
from concurrent.futures import ThreadPoolExecutor


def test_sante(client):
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.get_json()['ok'] is True


def test_connexion_refusee_avec_mauvais_mot_de_passe(client):
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'mauvais-mot-de-passe'})
    assert r.status_code == 401


def test_acces_refuse_sans_connexion(client):
    assert client.get('/api/eleves').status_code == 401


def test_inscription_eleve_avec_matricule(creer_eleve):
    eleve = creer_eleve()
    assert eleve['matricule'].startswith('M')
    assert eleve['statut'] == 'actif'


def test_paiement_puis_versement_partiel_et_recu(client, entetes, creer_eleve, creer_paiement):
    eleve = creer_eleve(nom='Camara', prenom='Mamadou')
    paiement = creer_paiement(eleve['id'], montant_du=1500000)

    r = client.post(f"/api/paiements/{paiement['id']}/verser",
                    json={'montant': 500000, 'moyen_paiement': 'Espèces'}, headers=entetes)
    assert r.status_code == 200, r.get_json()
    p = r.get_json()['paiement']
    assert p['montant_paye'] == 500000
    assert p['statut'] == 'partiel'

    # Le versement doit apparaître en comptabilité avec un numéro de reçu séquentiel
    r = client.get('/api/transactions', headers=entetes)
    assert r.status_code == 200
    recettes = [t for t in r.get_json() if t.get('eleve_id') == eleve['id']]
    assert recettes and recettes[0]['reference'].startswith('REC-')


def test_inscriptions_simultanees_sans_doublon_de_matricule(app, jeton_admin):
    """Plusieurs secrétaires qui inscrivent des élèves au même moment ne doivent
    jamais obtenir d'erreur ni deux fois le même matricule."""
    entetes = {'Authorization': f'Bearer {jeton_admin}'}

    def inscrire(i):
        with app.test_client() as c:
            r = c.post('/api/eleves', json={'nom': f'Simultane{i}', 'prenom': 'Test'}, headers=entetes)
            return r.status_code, (r.get_json() or {}).get('matricule')

    with ThreadPoolExecutor(max_workers=8) as executeur:
        resultats = list(executeur.map(inscrire, range(40)))

    codes = [code for code, _ in resultats]
    matricules = [m for _, m in resultats]
    assert codes == [201] * 40, codes
    assert len(set(matricules)) == 40


def test_versements_simultanes_sans_perte(client, app, jeton_admin, creer_eleve, creer_paiement):
    """Deux caisses qui encaissent en même temps sur des paiements différents : aucun
    versement ne doit être perdu, et les numéros de reçu doivent rester uniques."""
    entetes = {'Authorization': f'Bearer {jeton_admin}'}
    paiements = [creer_paiement(creer_eleve(nom=f'Caisse{i}', prenom='Test')['id'], montant_du=300000)
                 for i in range(12)]

    def verser(p):
        with app.test_client() as c:
            r = c.post(f"/api/paiements/{p['id']}/verser", json={'montant': 100000}, headers=entetes)
            return r.status_code

    with ThreadPoolExecutor(max_workers=6) as executeur:
        codes = list(executeur.map(verser, paiements))
    assert codes == [200] * 12, codes

    r = client.get('/api/transactions', headers=entetes)
    ids_eleves = {p['eleve_id'] for p in paiements}
    recettes = [t for t in r.get_json() if t.get('eleve_id') in ids_eleves]
    assert len(recettes) == 12
    references = [t['reference'] for t in recettes]
    assert len(set(references)) == 12
