"""Assistante IA : clé requise, aucune donnée de la base envoyée au modèle, quota, limites."""
import pytest

import routes.assistant_routes as ar


def _msg(texte):
    return {'messages': [{'role': 'user', 'content': texte}], 'page': 'dashboard'}


def test_assistante_non_configuree(client, entetes, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('KIMI_API_KEY', raising=False)
    assert client.get('/api/assistant/statut', headers=entetes).get_json()['actif'] is False
    r = client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes)
    assert r.status_code == 503 and r.get_json()['code'] == 'ASSISTANT_NON_CONFIGURE'


def test_assistante_exige_une_connexion(client):
    assert client.post('/api/assistant/discuter', json=_msg('Bonjour')).status_code == 401


def test_assistante_repond_et_ne_transmet_que_la_question(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    vus = {}

    def faux(systeme, messages, user):
        vus['systeme'], vus['messages'] = systeme, messages
        return "Le théorème de Pythagore : a² + b² = c².", []
    monkeypatch.setattr(ar, '_appeler_modele', faux)
    r = client.post('/api/assistant/discuter', json=_msg('Explique Pythagore'), headers=entetes)
    assert r.status_code == 200 and 'Pythagore' in r.get_json()['reponse']
    assert vus['messages'] == [{'role': 'user', 'content': 'Explique Pythagore'}]
    assert 'Rôle de l\'utilisateur dans l\'application : admin' in vus['systeme']
    assert 'MY-ECOLE' in vus['systeme'] and 'Guinée' in vus['systeme']


def test_assistante_nettoie_la_conversation(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    recus = {}
    monkeypatch.setattr(ar, '_appeler_modele', lambda s, m, u: (recus.setdefault('m', m) and 'ok', []))
    corps = {'messages': [{'role': 'assistant', 'content': 'intro'}, {'role': 'user', 'content': 'x' * 9000}]}
    assert client.post('/api/assistant/discuter', json=corps, headers=entetes).status_code == 200
    assert recus['m'][0]['role'] == 'user' and len(recus['m'][0]['content']) == ar.LONGUEUR_MAX


def test_quota_quotidien_de_l_etablissement(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '1')
    from database import db
    db.execute("DELETE FROM assistant_usage"); db.commit()
    monkeypatch.setattr(ar, '_appeler_modele', lambda s, m, u: ('ok', []))
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

    def panne(s, m, u):
        raise OSError('réseau')
    monkeypatch.setattr(ar, '_appeler_modele', panne)
    assert client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes).status_code == 502


# ───────── Données de l'école (statistiques agrégées par rôle) ─────────
def _peupler():
    from database import db
    eid = 1
    db.execute("DELETE FROM notes WHERE ecole_id=1"); db.execute("DELETE FROM paiements WHERE ecole_id=1")
    db.execute("DELETE FROM eleves WHERE ecole_id=1 AND classe LIKE 'ZZ-%'")
    for i in range(5):
        db.execute("INSERT INTO eleves (ecole_id,id,nom,prenom,sexe,classe,statut) VALUES (?,?,?,?,?,?,'actif')",
                   (eid, f'zz{i}', f'Secret{i}', 'Prenom', 'F' if i % 2 else 'M', 'ZZ-6e'))
        if i < 3:   # 3 élèves à jour, 2 avec impayé
            db.execute("INSERT INTO paiements (ecole_id,id,eleve_id,montant_du,montant_paye,statut) VALUES (?,?,?,?,?,'paye')",
                       (eid, f'zp{i}', f'zz{i}', 100, 100))
        else:
            db.execute("INSERT INTO paiements (ecole_id,id,eleve_id,montant_du,montant_paye,statut) VALUES (?,?,?,?,?,'a_payer')",
                       (eid, f'zp{i}', f'zz{i}', 100, 0))
        db.execute("INSERT INTO notes (ecole_id,id,eleve_id,matiere,trimestre,note,note_max) VALUES (?,?,?,?,1,?,20)",
                   (eid, f'zn{i}', f'zz{i}', 'Maths', 6 if i < 3 else 14))
    db.commit()


def test_outils_donnees_agreges_sans_noms(client, entetes):
    import assistant_donnees as ad
    _peupler()
    admin = {'id': 1, 'ecole_id': 1, 'role': 'admin'}
    eff = ad.executer('effectifs', admin, {})
    zz = next(c for c in eff['par_classe'] if c['classe'] == 'ZZ-6e')
    assert zz['total'] == 5 and zz['filles'] == 2 and zz['garcons'] == 3
    pay = ad.executer('paiements', admin, {})
    zz = next(c for c in pay['par_classe'] if c['classe'] == 'ZZ-6e')
    assert zz['a_jour'] == 3 and zz['avec_impayes'] == 2 and zz['taux_recouvrement_pct'] == 60.0
    res = ad.executer('resultats', admin, {'classe': 'ZZ-6e'})
    assert res['matieres_les_plus_faibles'][0]['moyenne_sur_20'] == 9.2
    import json
    assert 'Secret' not in json.dumps([eff, pay, res], ensure_ascii=False)     # jamais de noms d'élèves


def test_outils_reserves_selon_le_role(client):
    import assistant_donnees as ad
    assert ad.executer('finances', {'id': 5, 'ecole_id': 1, 'role': 'enseignant'}, {})['erreur']
    assert ad.executer('paiements', {'id': 5, 'ecole_id': 1, 'role': 'enseignant'}, {})['erreur']
    assert ad.executer('effectifs', {'id': 5, 'ecole_id': 1, 'role': 'parent'}, {})['erreur']
    assert [o['name'] for o in ad.outils_pour('parent')] == []
    assert 'resultats' in [o['name'] for o in ad.outils_pour('enseignant')]
    assert set(o['name'] for o in ad.outils_pour('comptable')) == {'effectifs', 'paiements', 'finances'}


def test_petits_groupes_masques(client):
    import assistant_donnees as ad
    from database import db
    _peupler()
    db.execute("DELETE FROM notes WHERE eleve_id IN ('zz3','zz4','zz2','zz1')"); db.commit()   # il ne reste qu'une note
    res = ad.executer('resultats', {'id': 1, 'ecole_id': 1, 'role': 'admin'}, {'classe': 'ZZ-6e'})
    assert res['matieres_les_plus_faibles'] == []


def test_boucle_d_outils_du_modele(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '500')
    import securite
    securite._debit.clear()
    _peupler()
    etapes = []

    def api(charge):
        etapes.append(charge)
        if len(etapes) == 1:
            assert any(o['name'] == 'paiements' for o in charge['tools'])
            return {'stop_reason': 'tool_use', 'content': [{'type': 'tool_use', 'id': 't1', 'name': 'paiements', 'input': {}}]}
        retour = charge['messages'][-1]['content'][0]
        assert retour['type'] == 'tool_result' and 'a_jour' in retour['content']
        return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Taux de recouvrement à améliorer.'}]}
    monkeypatch.setattr(ar, '_appeler_api', api)
    r = client.post('/api/assistant/discuter', json=_msg('Combien sont à jour ?'), headers=entetes)
    assert r.status_code == 200 and 'recouvrement' in r.get_json()['reponse'] and len(etapes) == 2
    from database import db
    ligne = db.execute("SELECT details FROM journal_audit WHERE action='question_assistante' ORDER BY rang DESC LIMIT 1").fetchone()
    assert 'paiements' in ligne['details']


def test_point_de_l_assistante_sans_cle_ni_appel_externe(client, entetes, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('KIMI_API_KEY', raising=False)
    _peupler()
    r = client.get('/api/assistant/alertes', headers=entetes)
    assert r.status_code == 200
    textes = ' '.join(a['titre'] for a in r.get_json()['alertes'])
    assert 'à jour' in textes and 'ZZ-6e' in textes          # 60 % de recouvrement, moyenne 9,2/20
    assert 'Secret' not in textes
    assert client.get('/api/assistant/alertes').status_code == 401


def test_point_de_l_assistante_vide_pour_un_parent(client):
    import assistant_donnees as ad
    assert ad.alertes({'id': 9, 'ecole_id': 1, 'role': 'parent'}) == []


def test_l_administrateur_peut_desactiver_l_assistante(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setattr(ar, '_appeler_modele', lambda s, m, u: ('ok', []))
    import securite
    securite._debit.clear()
    assert client.put('/api/settings', json={'assistant_actif': '0'}, headers=entetes).status_code == 200
    try:
        r = client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes)
        assert r.status_code == 403 and r.get_json()['code'] == 'ASSISTANT_DESACTIVE'
        assert client.get('/api/assistant/alertes', headers=entetes).get_json()['alertes'] == []
        assert client.get('/api/assistant/statut', headers=entetes).get_json()['desactivee_par_ecole'] is True
    finally:
        client.put('/api/settings', json={'assistant_actif': '1'}, headers=entetes)
    assert client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes).status_code == 200


def test_reponse_en_direct(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '500')
    import securite
    securite._debit.clear()
    _peupler()
    appels = []

    def flux(charge):
        appels.append(charge)
        if len(appels) == 1:
            yield {'type': 'content_block_start', 'content_block': {'type': 'tool_use', 'id': 't1', 'name': 'paiements'}}
            yield {'type': 'content_block_delta', 'delta': {'type': 'input_json_delta', 'partial_json': '{}'}}
            yield {'type': 'content_block_stop'}
            yield {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use'}}
        else:
            yield {'type': 'content_block_start', 'content_block': {'type': 'text'}}
            yield {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'Taux '}}
            yield {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'bon.'}}
            yield {'type': 'content_block_stop'}
            yield {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}}
    monkeypatch.setattr(ar, '_appeler_api_flux', flux)
    r = client.post('/api/assistant/discuter-flux', json=_msg('Combien sont à jour ?'), headers=entetes)
    corps = r.get_data(as_text=True)
    assert r.status_code == 200 and r.mimetype == 'text/event-stream'
    assert '"outil"' in corps and 'Taux ' in corps and 'bon.' in corps and '"fin"' in corps and len(appels) == 2


def test_flux_panne_du_fournisseur(client, entetes, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'cle-de-test')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '500')
    import securite
    securite._debit.clear()

    def panne(charge):
        raise OSError('réseau')
        yield
    monkeypatch.setattr(ar, '_appeler_api_flux', panne)
    r = client.post('/api/assistant/discuter-flux', json=_msg('Bonjour'), headers=entetes)
    assert '"erreur"' in r.get_data(as_text=True)


def test_kimi_traduction_du_format():
    import kimi_adaptateur as k
    charge = {'system': 'Sys', 'max_tokens': 100,
              'tools': [{'name': 'paiements', 'description': 'd', 'input_schema': {'type': 'object', 'properties': {}}}],
              'messages': [{'role': 'user', 'content': 'Salut'},
                           {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 't1', 'name': 'paiements', 'input': {}}]},
                           {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 't1', 'content': '{"a_jour": 3}'}]}]}
    o = k.vers_openai(charge)
    assert o['messages'][0] == {'role': 'system', 'content': 'Sys'}
    assert o['messages'][2]['tool_calls'][0]['function']['name'] == 'paiements'
    assert o['messages'][3] == {'role': 'tool', 'tool_call_id': 't1', 'content': '{"a_jour": 3}'}
    assert o['tools'][0]['function']['name'] == 'paiements' and o['model'] == 'kimi-k3'


class _Flux:
    def __init__(self, lignes): self.lignes = [l.encode() for l in lignes]
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(self.lignes)
    def read(self): return b''.join(self.lignes)


def test_kimi_flux_texte_et_outils(monkeypatch):
    import json as j, kimi_adaptateur as k
    monkeypatch.setenv('KIMI_API_KEY', 'cle')
    morceaux = [
        {'choices': [{'delta': {'content': 'Bon'}}]},
        {'choices': [{'delta': {'content': 'jour'}}]},
        {'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'c1', 'function': {'name': 'paiements', 'arguments': '{"cl'}}]}}]},
        {'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': 'asse":"6e"}'}}]}, 'finish_reason': 'tool_calls'}]},
    ]
    lignes = ['data: ' + j.dumps(m) + '\n' for m in morceaux] + ['data: [DONE]\n']
    monkeypatch.setattr(k.urllib.request, 'urlopen', lambda req, timeout=0: _Flux(lignes))
    evs = list(k.flux({'messages': [{'role': 'user', 'content': 'x'}]}))
    texte = ''.join(e['delta']['text'] for e in evs if e.get('delta', {}).get('type') == 'text_delta')
    args = ''.join(e['delta']['partial_json'] for e in evs if e.get('delta', {}).get('type') == 'input_json_delta')
    assert texte == 'Bonjour' and j.loads(args) == {'classe': '6e'}
    assert evs[-1] == {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use'}}


def test_kimi_prioritaire_et_reponse_simple(client, entetes, monkeypatch):
    import json as j, kimi_adaptateur as k, securite
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('KIMI_API_KEY', 'cle')
    monkeypatch.setenv('ASSISTANT_MAX_JOUR', '500')
    securite._debit.clear()
    rep = j.dumps({'choices': [{'message': {'content': 'Réponse de Kimi'}, 'finish_reason': 'stop'}]})
    monkeypatch.setattr(k.urllib.request, 'urlopen', lambda req, timeout=0: _Flux([rep]))
    r = client.post('/api/assistant/discuter', json=_msg('Bonjour'), headers=entetes)
    assert r.status_code == 200 and r.get_json()['reponse'] == 'Réponse de Kimi'
