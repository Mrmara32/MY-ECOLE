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
