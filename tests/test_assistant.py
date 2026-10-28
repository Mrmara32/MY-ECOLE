"""Assistante IA : clé requise, aucune donnée de la base envoyée au modèle, quota, limites."""
import pytest

import routes.assistant_routes as ar


def _msg(texte):
    return {'messages': [{'role': 'user', 'content': texte}], 'page': 'dashboard'}


def test_assistante_non_configuree(client, entetes, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert client.get('/api/assistant/statut', headers=entetes).get_json()['actif'] is False
    r = client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes)
    assert r.status_code == 503 and r.get_json()['code'] == 'ASSISTANT_NON_CONFIGURE'


def test_assistante_exige_une_connexion(client):
    assert client.post('/api/assistant/discuter', json=_msg('Bonjour')).status_code == 401


def test_assistante_repond_et_ne_transmet_que_la_question(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    vus = {}

    def faux(systeme, messages):
        vus['systeme'], vus['messages'] = systeme, messages
        return "Le théorème de Pythagore : a² + b² = c²."
    monkeypatch.setattr(ar, '_appeler_modele', faux)
    r = client.post('/api/assistant/discuter', json=_msg('Explique Pythagore'), headers=entetes)
    assert r.status_code == 200 and 'Pythagore' in r.get_json()['reponse']
    assert vus['messages'] == [{'role': 'user', 'content': 'Explique Pythagore'}]
    assert 'Rôle de l\'utilisateur dans l\'application : admin' in vus['systeme']
    assert 'MY-ECOLE' in vus['systeme'] and 'Guinée' in vus['systeme']


def test_assistante_nettoie_la_conversation(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    recus = {}
    monkeypatch.setattr(ar, '_appeler_modele', lambda s, m: recus.setdefault('m', m) and 'ok')
    corps = {'messages': [{'role': 'assistant', 'content': 'intro'}, {'role': 'user', 'content': 'x' * 9000}]}
    assert client.post('/api/assistant/discuter', json=corps, headers=entetes).status_code == 200
    assert recus['m'][0]['role'] == 'user' and len(recus['m'][0]['content']) == ar.LONGUEUR_MAX


def test_quota_quotidien_de_l_etablissement(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '1')
    from database import db
    db.execute("DELETE FROM assistant_usage"); db.commit()
    monkeypatch.setattr(ar, '_appeler_modele', lambda s, m: 'ok')
    import securite
    securite._debit.clear()
    assert client.post('/api/assistant/discuter', json=_msg('un'), headers=entetes).status_code == 200
    r = client.post('/api/assistant/discuter', json=_msg('deux'), headers=entetes)
    assert r.status_code == 429 and 'quota' in r.get_json()['error']


def test_panne_du_fournisseur_renvoie_502(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '500')
    import securite
    securite._debit.clear()

    def panne(s, m):
        raise OSError('réseau')
    monkeypatch.setattr(ar, '_appeler_modele', panne)
    assert client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes).status_code == 502
