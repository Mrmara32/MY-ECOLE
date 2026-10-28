"""Réception d'une commande -> dépense comptabilisée automatiquement (une seule fois)."""


def _transactions(client, entetes, reference):
    r = client.get('/api/transactions', headers=entetes)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    lignes = data if isinstance(data, list) else data.get('items') or data.get('transactions') or []
    return [t for t in lignes if t.get('reference') == reference]


def test_reception_comptabilise_automatiquement(client, entetes):
    r = client.post('/api/commandes', json={
        'numero': 'BC-AUTO-1',
        'lignes': [{'designation': 'Craie', 'quantite': 10, 'prix_unitaire': 5000}],
    }, headers=entetes)
    assert r.status_code == 201, r.get_json()
    cid = r.get_json()['id']
    assert _transactions(client, entetes, 'CMD-BC-AUTO-1') == []          # pas encore reçue : rien en compta
    assert client.post(f'/api/commandes/{cid}/receptionner', headers=entetes).status_code == 200
    ecritures = _transactions(client, entetes, 'CMD-BC-AUTO-1')
    assert len(ecritures) == 1
    assert ecritures[0]['type'] == 'sortie' and ecritures[0]['montant'] == 50000 and ecritures[0]['journal'] == 'achats'
    # Réception en double refusée : pas de seconde écriture
    assert client.post(f'/api/commandes/{cid}/receptionner', headers=entetes).status_code == 409
    assert len(_transactions(client, entetes, 'CMD-BC-AUTO-1')) == 1


def test_commande_creee_directement_recue_est_comptabilisee(client, entetes):
    r = client.post('/api/commandes', json={
        'numero': 'BC-AUTO-2', 'statut': 'recue',
        'lignes': [{'designation': 'Cahiers', 'quantite': 2, 'prix_unitaire': 1000}],
    }, headers=entetes)
    assert r.status_code == 201, r.get_json()
    assert len(_transactions(client, entetes, 'CMD-BC-AUTO-2')) == 1


def test_suppression_ponctuelle_des_doublons(client, entetes):
    from database import db, gen_id, _supprimer_depenses_en_double, REFERENCES_DEPENSES_DOUBLONS
    ecole = db.execute("SELECT id FROM ecoles LIMIT 1").fetchone()['id']
    for ref in (REFERENCES_DEPENSES_DOUBLONS[0], 'CMD-autre-commande'):
        db.execute("INSERT INTO transactions (id,ecole_id,type,date_op,montant,reference,journal) VALUES (?,?,?,?,?,?,?)",
                   (gen_id('t'), ecole, 'sortie', '2026-10-27', 1000, ref, 'achats'))
    db.commit()
    _supprimer_depenses_en_double()
    db.commit()
    assert not db.execute("SELECT 1 FROM transactions WHERE reference=?", (REFERENCES_DEPENSES_DOUBLONS[0],)).fetchone()
    assert db.execute("SELECT 1 FROM transactions WHERE reference='CMD-autre-commande'").fetchone()


def _achat_a_regler(client, entetes, numero, prix=1000, quantite=10):
    r = client.post('/api/commandes', json={'numero': numero, 'statut': 'recue',
        'lignes': [{'designation': 'Craie', 'quantite': quantite, 'prix_unitaire': prix}]}, headers=entetes)
    assert r.status_code == 201, r.get_json()
    return _transactions(client, entetes, f'CMD-{numero}')[0]


def test_reglement_fournisseur_partiel_puis_total(client, entetes):
    t = _achat_a_regler(client, entetes, 'BC-REG-1')            # 10 000
    assert t['a_regler'] == 1
    dettes = client.get('/api/dettes-fournisseurs', headers=entetes).get_json()
    assert any(d['id'] == t['id'] and d['solde'] == 10000 for d in dettes['dettes'])
    r = client.post(f"/api/transactions/{t['id']}/regler", json={'montant': 4000, 'moyen_paiement': 'Espèces'}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['solde'] == 6000 and not r.get_json()['soldee']
    # dépassement refusé
    assert client.post(f"/api/transactions/{t['id']}/regler", json={'montant': 7000}, headers=entetes).status_code == 400
    r = client.post(f"/api/transactions/{t['id']}/regler", json={'moyen_paiement': 'Virement bancaire'}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['soldee']
    assert client.post(f"/api/transactions/{t['id']}/regler", json={'montant': 1}, headers=entetes).status_code == 409
    maj = _transactions(client, entetes, 'CMD-BC-REG-1')[0]
    assert maj['moyen_paiement'] == 'Virement bancaire' and maj['montant_regle'] == 10000
    assert len(client.get(f"/api/transactions/{t['id']}/reglements", headers=entetes).get_json()) == 2
    # une seule dépense : le règlement ne double pas la comptabilité
    assert len(_transactions(client, entetes, 'CMD-BC-REG-1')) == 1
    dettes = client.get('/api/dettes-fournisseurs', headers=entetes).get_json()
    assert all(d['id'] != t['id'] for d in dettes['dettes'])


def test_regler_depense_ordinaire_refuse(client, entetes):
    r = client.post('/api/transactions', json={'type': 'sortie', 'montant': 500, 'categorie': 'Divers',
        'moyen_paiement': 'Espèces', 'date_op': '2026-10-01', 'journal': 'diverses'}, headers=entetes)
    assert r.status_code in (200, 201), r.get_json()
    tid = r.get_json().get('id')
    assert client.post(f'/api/transactions/{tid}/regler', json={'montant': 100}, headers=entetes).status_code == 400


def test_badge_eleve_securise_et_verification_publique(client, entetes):
    r = client.post('/api/eleves', json={'nom': 'Mara', 'prenom': 'Test', 'classe': '7ème', 'date_naissance': '2012-01-01', 'annee_scolaire': '2099-2100'}, headers=entetes)
    assert r.status_code in (200, 201), r.get_json()
    eid = r.get_json()['id']
    b = client.get(f'/api/eleves/{eid}/badge-securise', headers=entetes).get_json()
    assert b['signature'] and '<svg' in b['qr_svg'] and b['expire'].endswith('-07-31')
    chemin = b['url'].split('://', 1)[1].split('/', 1)[1]
    ok = client.get('/api/' + chemin).get_json()           # public : sans authentification
    assert ok['valide'] is True and ok['nom'] == 'Mara'
    faux = client.get('/api/' + chemin[:-3] + 'abc').get_json()
    assert faux['valide'] is False
    page = client.get('/' + chemin)
    assert page.status_code == 200 and 'Badge authentique' in page.get_data(as_text=True)
    # ancien format d'adresse (badges déjà imprimés) toujours accepté
    ancien = f"api/verifier-badge/1/{eid}/2099-2100/{b['signature']}"
    assert client.get('/' + ancien).get_json()['valide'] is True


def test_verification_badge_par_matricule_et_code(client, entetes):
    r = client.post('/api/eleves', json={'nom': 'Diallo', 'prenom': 'Aicha', 'classe': '7ème', 'annee_scolaire': '2099-2100'}, headers=entetes)
    eid = r.get_json()['id']
    mat = client.get(f'/api/eleves/{eid}', headers=entetes).get_json()['matricule']
    b = client.get(f'/api/eleves/{eid}/badge-securise', headers=entetes).get_json()
    ok = client.get(f"/api/verifier-badge-code?matricule={mat}&code={b['code_controle']}").get_json()
    assert ok['valide'] is True and ok['nom'] == 'Diallo'
    faux = client.get(f"/api/verifier-badge-code?matricule={mat}&code=0000-0000-0000").get_json()
    assert faux['valide'] is False
    # le matricule est facultatif ; le QR (adresse courte) fonctionne aussi
    assert client.get(f"/api/verifier-badge-code?code={b['code_controle']}").get_json()['valide'] is True
    court = b['url'].split('://', 1)[1].split('/', 1)[1]            # v/<ecole>/<code>
    assert client.get('/api/' + court).get_json()['valide'] is True
    assert 'Badge authentique' in client.get('/' + court).get_data(as_text=True)
    assert client.get('/api/verifier-badge-code?matricule=&code=').status_code == 400
