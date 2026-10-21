"""Durées de conservation : rapport, anonymisation en lot, purge du journal."""
import retention
from database import db


def _h(jeton):
    return {'Authorization': 'Bearer ' + jeton}


def test_politique_par_defaut_et_validation(client, jeton_admin):
    r = client.get('/api/eleves/retention', headers=_h(jeton_admin)).get_json()
    assert r['politique'] == {'eleves_annees': 10, 'journal_mois': 36}
    assert client.put('/api/eleves/retention', headers=_h(jeton_admin), json={'journal_mois': 3}).status_code == 400
    ok = client.put('/api/eleves/retention', headers=_h(jeton_admin), json={'eleves_annees': 7, 'journal_mois': 24})
    assert ok.get_json() == {'eleves_annees': 7, 'journal_mois': 24}
    client.put('/api/eleves/retention', headers=_h(jeton_admin), json={'eleves_annees': 10, 'journal_mois': 36})


def test_anonymisation_en_lot(client, jeton_admin, creer_eleve):
    ancien = creer_eleve(nom='Ancien', prenom='Eleve')
    actif = creer_eleve(nom='Actif', prenom='Eleve')
    db.execute("UPDATE eleves SET statut='transfere', created_at='2005-01-01' WHERE id=?", (ancien['id'],))
    db.execute("UPDATE eleves SET created_at='2005-01-01' WHERE id=?", (actif['id'],))  # actif : jamais concerné
    db.commit()
    r = client.get('/api/eleves/retention', headers=_h(jeton_admin)).get_json()
    ids = [d['id'] for d in r['dossiers']]
    assert ancien['id'] in ids and actif['id'] not in ids
    assert client.post('/api/eleves/retention/anonymiser', headers=_h(jeton_admin), json={'confirmation': 'non'}).status_code == 400
    ok = client.post('/api/eleves/retention/anonymiser', headers=_h(jeton_admin), json={'confirmation': 'ANONYMISER'}).get_json()
    assert ok['anonymises'] >= 1
    e = db.execute("SELECT nom FROM eleves WHERE id=?", (ancien['id'],)).fetchone()
    assert e['nom'] == 'ANONYME'
    assert db.execute("SELECT nom FROM eleves WHERE id=?", (actif['id'],)).fetchone()['nom'] == 'Actif'


def test_purge_du_journal_et_des_jetons(client, jeton_admin):
    db.execute("INSERT INTO journal_audit (id,ecole_id,action,entite,created_at) VALUES ('vieux-1',1,'x','y','2001-01-01')")
    db.execute("INSERT OR IGNORE INTO jetons_revoques (jti, expire_le) VALUES ('perime', 1)")
    db.commit()
    retention.purger()
    assert not db.execute("SELECT 1 FROM journal_audit WHERE id='vieux-1'").fetchone()
    assert not db.execute("SELECT 1 FROM jetons_revoques WHERE jti='perime'").fetchone()
