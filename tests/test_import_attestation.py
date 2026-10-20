"""Import d'élèves (CSV / Excel) et attestations de scolarité."""
import io

import pytest


def _csv(texte, nom='eleves.csv'):
    return {'fichier': (io.BytesIO(texte.encode('utf-8-sig')), nom)}


@pytest.fixture
def classe_import(client, entetes):
    client.post('/api/classes', json={'nom': 'CP-Imp', 'cycle': 'primaire'}, headers=entetes)
    return 'CP-Imp'


def _post(client, entetes, fichiers, simulation=False):
    data = dict(fichiers)
    if simulation:
        data['simulation'] = '1'
    return client.post('/api/import-eleves', data=data, headers=entetes, content_type='multipart/form-data')


def test_simulation_ne_cree_rien_puis_import_reel(client, entetes, classe_import):
    csv_ = ("Nom;Prénom;Date de naissance;Sexe;Classe;Téléphone père\n"
            f"Importé;Awa;14/03/2015;F;{classe_import};622111222\n"
            f"Importé;Moussa;02/11/2014;garçon;{classe_import};\n")
    r = _post(client, entetes, _csv(csv_), simulation=True)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['a_importer'] == 2 and r.get_json()['importes'] == 0
    avant = len(client.get('/api/eleves', headers=entetes).get_json())

    r = _post(client, entetes, _csv(csv_))
    assert r.get_json()['importes'] == 2
    eleves = [e for e in client.get('/api/eleves', headers=entetes).get_json() if e['nom'] == 'Importé']
    assert len(client.get('/api/eleves', headers=entetes).get_json()) == avant + 2
    awa = next(e for e in eleves if e['prenom'] == 'Awa')
    assert awa['date_naissance'] == '2015-03-14' and awa['sexe'] == 'F' and awa['pere_telephone'] == '622111222'
    assert awa['matricule'].startswith('M') and awa['statut'] == 'actif'

    # Réimporter le même fichier : tout est reconnu comme doublon, rien n'est recréé
    r = _post(client, entetes, _csv(csv_)).get_json()
    assert r['importes'] == 0 and len(r['doublons']) == 2


def test_lignes_en_erreur_signalees_et_ignorees(client, entetes, classe_import):
    csv_ = ("nom;prenom;naissance;sexe;classe\n"
            f"Bon;Un;01/01/2016;M;{classe_import}\n"
            "Mauvais;Date;pas-une-date;M;\n"
            "Mauvais;Sexe;01/01/2016;X;\n"
            "Mauvais;Classe;01/01/2016;M;ClasseInexistante\n"
            ";SansNom;01/01/2016;M;\n")
    r = _post(client, entetes, _csv(csv_)).get_json()
    assert r['importes'] == 1
    assert {p['ligne'] for p in r['erreurs']} == {3, 4, 5, 6}
    assert any('Classe inconnue' in e for p in r['erreurs'] for e in p['erreurs'])


def test_fichier_invalide_refuse(client, entetes):
    assert _post(client, entetes, {}).status_code == 400
    assert _post(client, entetes, _csv('Foo;Bar\n1;2\n')).status_code == 400            # pas de colonnes Nom/Prénom
    assert _post(client, entetes, _csv('x', 'liste.pdf')).status_code == 400
    assert _post(client, entetes, {'fichier': (io.BytesIO(b'pas un excel'), 'liste.xlsx')}).status_code == 400


def test_import_excel_xlsx(client, entetes, classe_import):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(['Nom', 'Prénoms', 'Date de naissance', 'Sexe', 'Niveau'])
    import datetime
    ws.append(['Excel', 'Fanta', datetime.date(2013, 5, 9), 'Féminin', classe_import])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    r = _post(client, entetes, {'fichier': (buf, 'eleves.xlsx')}).get_json()
    assert r['importes'] == 1
    e = next(x for x in client.get('/api/eleves', headers=entetes).get_json() if x['nom'] == 'Excel')
    assert e['date_naissance'] == '2013-05-09' and e['sexe'] == 'F' and e['classe'] == classe_import


def test_modele_telechargeable_et_reimportable(client, entetes):
    r = client.get('/api/import-eleves/modele', headers=entetes)
    assert r.status_code == 200 and b'Pr\xc3\xa9nom' in r.data


def test_import_refuse_sans_connexion(client):
    assert client.post('/api/import-eleves').status_code == 401


def test_attestation_numerotee_et_reservee_aux_eleves_actifs(client, entetes, creer_eleve):
    e1, e2 = creer_eleve(nom='Att1', prenom='A'), creer_eleve(nom='Att2', prenom='B')
    a1 = client.post(f"/api/eleves/{e1['id']}/attestation", headers=entetes)
    a2 = client.post(f"/api/eleves/{e2['id']}/attestation", headers=entetes)
    assert a1.status_code == 201 and a2.status_code == 201
    n1, n2 = a1.get_json()['numero'], a2.get_json()['numero']
    assert n1.startswith('ATT-') and n1 != n2 and int(n2.split('-')[-1]) == int(n1.split('-')[-1]) + 1
    client.put(f"/api/eleves/{e2['id']}", json={'statut': 'inactif'}, headers=entetes)
    assert client.post(f"/api/eleves/{e2['id']}/attestation", headers=entetes).status_code == 400
    assert client.post('/api/eleves/inexistant/attestation', headers=entetes).status_code == 404
