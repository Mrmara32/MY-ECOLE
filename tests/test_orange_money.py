"""Paiement Orange Money (Web Payment) — serveur Orange factice."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import orange_money_service as om

etat = {'statut': 'INITIATED', 'appels': []}


class FauxOrange(BaseHTTPRequestHandler):
    def do_POST(self):
        corps = self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200); self.end_headers()
        if self.path.endswith('/oauth/v3/token'):
            self.wfile.write(b'{"access_token":"T","expires_in":3600}')
        elif self.path.endswith('/webpayment'):
            etat['appels'].append(('webpayment', json.loads(corps)))
            self.wfile.write(b'{"payment_url":"https://pay.example/abc","pay_token":"PT1","notif_token":"NT1"}')
        elif self.path.endswith('/transactionstatus'):
            etat['appels'].append(('status', json.loads(corps)))
            self.wfile.write(json.dumps({'status': etat['statut']}).encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_om(monkeypatch):
    etat.update(statut='INITIATED', appels=[])
    om._jeton.update(valeur=None, expire=0)
    srv = HTTPServer(('127.0.0.1', 0), FauxOrange)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for k, v in {'OM_API_URL': f'http://127.0.0.1:{srv.server_port}', 'OM_AUTH': 'Basic x',
                 'OM_MERCHANT_KEY': 'MK', 'URL_APPLICATION': 'https://ecole.example'}.items():
        monkeypatch.setenv(k, v)
    yield
    srv.shutdown()


def _dossier(client, entetes, creer_eleve, creer_paiement):
    e = creer_eleve(nom='Barry', prenom='Mamadou', classe='CE2')
    p1 = creer_paiement(e['id'], 300000, 'Tranche 1')
    p2 = creer_paiement(e['id'], 200000, 'Tranche 2')
    return e, p1, p2


def _reste(client, entetes, eleve_id):
    return client.get(f'/api/paiements/solde/{eleve_id}', headers=entetes).get_json()['reste']


def test_non_configure_et_reglages(monkeypatch, client, entetes):
    monkeypatch.delenv('OM_AUTH', raising=False)
    assert client.get('/api/orange-money/statut', headers=entetes).get_json()['actif'] is False
    assert client.post('/api/orange-money/lien', json={'eleve_id': 'x'}, headers=entetes).status_code == 503


def test_parcours_complet_paiement_reussi(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 400000}, headers=entetes)
    assert r.status_code == 200, r.get_json()
    rid = r.get_json()['id']
    assert r.get_json()['payment_url'] == 'https://pay.example/abc'
    envoi = etat['appels'][0][1]
    assert envoi['amount'] == 400000 and envoi['merchant_key'] == 'MK' and envoi['currency'] == 'OUV'
    assert envoi['notif_url'].startswith('https://ecole.example/api/orange-money/notification?ref=')
    assert _reste(client, entetes, e['id']) == 500000  # rien n'est encaissé avant confirmation

    # fausse notification : refusée
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'status': 'SUCCESS', 'notif_token': 'FAUX'}).status_code == 403
    assert _reste(client, entetes, e['id']) == 500000
    # vraie notification mais Orange dit encore « en cours » : rien
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'}).status_code == 200
    assert _reste(client, entetes, e['id']) == 500000
    # Orange confirme
    etat['statut'] = 'SUCCESS'
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'}).status_code == 200
    assert _reste(client, entetes, e['id']) == 100000
    # notification répétée / retour du parent : pas de double encaissement
    client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'})
    page = client.get(f'/api/orange-money/retour?ref={rid}')
    assert 'Paiement confirmé' in page.get_data(as_text=True)
    assert _reste(client, entetes, e['id']) == 100000
    liste = client.get('/api/orange-money/paiements', headers=entetes).get_json()
    mien = next(x for x in liste if x['id'] == rid)  # (plusieurs paiements peuvent partager la même seconde)
    assert mien['statut'] == 'reussi' and mien['numero_recu'].startswith('REC-')


def test_paiement_echoue_et_montants_invalides(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, *_ = _dossier(client, entetes, creer_eleve, creer_paiement)
    assert client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 999999999}, headers=entetes).status_code == 400
    assert client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 10}, headers=entetes).status_code == 400
    rid = client.post('/api/orange-money/lien', json={'eleve_id': e['id']}, headers=entetes).get_json()['id']
    etat['statut'] = 'FAILED'
    assert client.post(f'/api/orange-money/verifier/{rid}', headers=entetes).get_json()['statut'] == 'echoue'
    assert _reste(client, entetes, e['id']) == 500000
    etat['statut'] = 'SUCCESS'  # un échec déjà constaté ne se transforme pas en encaissement
    assert client.post(f'/api/orange-money/verifier/{rid}', headers=entetes).get_json()['statut'] == 'echoue'
    assert _reste(client, entetes, e['id']) == 500000


def test_solde_regle_entre_temps_va_en_verification(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    rid = client.post('/api/orange-money/lien', json={'eleve_id': e['id'], 'montant': 100000}, headers=entetes).get_json()['id']
    for p, m in ((p1, 300000), (p2, 200000)):
        assert client.post(f"/api/paiements/{p['id']}/verser", json={'montant': m}, headers=entetes).status_code == 200
    etat['statut'] = 'SUCCESS'
    assert client.post(f'/api/orange-money/verifier/{rid}', headers=entetes).get_json()['statut'] == 'a_verifier'


# ───────────── paiement marchand par QR ─────────────
def test_declaration_validation_et_doublon(client, entetes, creer_eleve, creer_paiement):
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 400000, 'transaction_id': 'MP261020.2345.A12345'}, headers=entetes)
    assert r.status_code == 201 and r.get_json()['statut'] == 'a_valider'
    assert _reste(client, entetes, e['id']) == 500000  # pas encore encaissé
    # même numéro de transaction : refusé, même écrit autrement
    assert client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 400000, 'transaction_id': 'mp261020.2345.a12345'}, headers=entetes).status_code == 409
    did = r.get_json()['id']
    assert len(client.get('/api/orange-money/declarations?statut=a_valider', headers=entetes).get_json()) == 1
    v = client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes)
    assert v.status_code == 200 and v.get_json()['numero_recu'].startswith('REC-')
    assert _reste(client, entetes, e['id']) == 100000
    assert client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes).status_code == 409  # une seule fois
    assert _reste(client, entetes, e['id']) == 100000


def test_encaissement_direct_rejet_et_controles(client, entetes, creer_eleve, creer_paiement):
    e, *_ = _dossier(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 500000, 'transaction_id': 'TX-DIRECT-001', 'valider': True}, headers=entetes)
    assert r.status_code == 201 and r.get_json()['statut'] == 'valide' and _reste(client, entetes, e['id']) == 0
    assert client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 5000, 'transaction_id': 'ab'}, headers=entetes).status_code == 400
    e2, *_ = _dossier(client, entetes, creer_eleve, creer_paiement)
    did = client.post('/api/orange-money/declarations', json={'eleve_id': e2['id'], 'montant': 5000, 'transaction_id': 'TX-REJET-002'}, headers=entetes).get_json()['id']
    assert client.post(f'/api/orange-money/declarations/{did}/rejeter', json={'motif': 'x'}, headers=entetes).status_code == 400
    assert client.post(f'/api/orange-money/declarations/{did}/rejeter', json={'motif': 'Transaction introuvable chez Orange'}, headers=entetes).status_code == 200
    assert client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes).status_code == 409
    assert _reste(client, entetes, e2['id']) == 500000
    assert client.post('/api/orange-money/declarations', json={}).status_code == 401


def test_config_marchand(client, entetes):
    r = client.put('/api/orange-money/config', json={'nom': 'GS El Hadji Mountaga Djely', 'code': '123456', 'instructions': 'Scannez le QR'}, headers=entetes)
    assert r.status_code == 200 and r.get_json()['code'] == '123456'
    assert client.get('/api/orange-money/config', headers=entetes).get_json()['nom'].startswith('GS El Hadji')


# ───────────── page publique « Payer la scolarité » ─────────────
def _eleve_matricule(client, entetes, creer_eleve, creer_paiement):
    e = creer_eleve(nom='Diané', prenom='Aïssatou', classe='CE1')
    creer_paiement(e['id'], 600000, 'Tranche 1')
    return e, client.get(f"/api/eleves/{e['id']}", headers=entetes).get_json()['matricule']


def test_public_verification_identite_sans_accents(client, entetes, creer_eleve, creer_paiement):
    e, mat = _eleve_matricule(client, entetes, creer_eleve, creer_paiement)
    r = client.post('/api/orange-money/public/verifier', json={'nom': 'DIANE', 'prenom': 'aissatou', 'matricule': mat.lower()})
    assert r.status_code == 200 and r.get_json()['reste'] == 600000 and r.get_json()['eleve']['classe'] == 'CE1'
    for faux in ({'nom': 'Diané', 'prenom': 'Aïssatou', 'matricule': 'XXX'}, {'nom': 'Autre', 'prenom': 'Aïssatou', 'matricule': mat},
                 {'nom': '', 'prenom': '', 'matricule': mat}):
        assert client.post('/api/orange-money/public/verifier', json=faux).status_code == 404


def test_public_paiement_qr_attend_validation_puis_comptabilise(client, entetes, creer_eleve, creer_paiement):
    e, mat = _eleve_matricule(client, entetes, creer_eleve, creer_paiement)
    ident = {'nom': 'Diané', 'prenom': 'Aïssatou', 'matricule': mat}
    assert client.post('/api/orange-money/public/payer', json={**ident, 'montant': 200000}).status_code == 400  # n° transaction requis
    assert client.post('/api/orange-money/public/payer', json={**ident, 'montant': 900000, 'transaction_id': 'MP.PUB.0001'}).status_code == 400  # > solde
    r = client.post('/api/orange-money/public/payer', json={**ident, 'montant': 200000, 'transaction_id': 'MP.PUB.0001', 'telephone': '622000000'})
    assert r.status_code == 200 and r.get_json()['mode'] == 'qr'
    assert _reste(client, entetes, e['id']) == 600000  # rien n'est comptabilisé sans validation
    assert client.post('/api/orange-money/public/payer', json={**ident, 'montant': 200000, 'transaction_id': 'mp.pub.0001'}).status_code == 409
    liste = client.get('/api/orange-money/declarations?statut=a_valider', headers=entetes).get_json()
    assert liste[0]['montant'] == 200000 and liste[0]['nom'] == 'Diané'
    assert client.post(f"/api/orange-money/declarations/{liste[0]['id']}/valider", headers=entetes).status_code == 200
    assert _reste(client, entetes, e['id']) == 400000


def test_public_paiement_api_redirige_vers_orange(client, entetes, creer_eleve, creer_paiement, faux_om):
    e, mat = _eleve_matricule(client, entetes, creer_eleve, creer_paiement)
    assert client.get('/api/orange-money/public/config').get_json()['mode'] == 'api'
    r = client.post('/api/orange-money/public/payer', json={'nom': 'Diané', 'prenom': 'Aïssatou', 'matricule': mat, 'montant': 600000})
    assert r.status_code == 200 and r.get_json()['payment_url'] == 'https://pay.example/abc'
    rid = next(x['id'] for x in client.get('/api/orange-money/paiements', headers=entetes).get_json() if x['statut'] == 'en_attente')
    etat['statut'] = 'SUCCESS'  # Orange confirme : tout est automatique, sans aucune intervention
    assert client.post(f'/api/orange-money/notification?ref={rid}', json={'notif_token': 'NT1'}).status_code == 200
    assert _reste(client, entetes, e['id']) == 0


def test_public_page_servie_et_blocage_des_devinettes(client):
    assert client.get('/payer').status_code == 200 and client.get('/ecole/ecole-1/payer').status_code == 200
    for _ in range(45):
        r = client.post('/api/orange-money/public/verifier', json={'nom': 'a', 'prenom': 'b', 'matricule': 'ZZZ999'})
    assert r.status_code == 429
    from database import db
    db.execute("DELETE FROM echecs_connexion WHERE cle LIKE 'ip:payer:%'")  # ne pas bloquer les tests suivants
    db.commit()


def test_sms_de_confirmation_au_payeur_apres_validation(client, entetes, creer_eleve, creer_paiement, monkeypatch):
    import sms_service
    envoyes = []
    monkeypatch.setenv('ORANGE_SMS_AUTH', 'Basic x'); monkeypatch.setenv('ORANGE_SMS_SENDER', '224622000000')
    monkeypatch.setattr(sms_service, 'envoyer_sms', lambda tel, msg: envoyes.append((tel, msg)) or 'ok')
    e, mat = _eleve_matricule(client, entetes, creer_eleve, creer_paiement)
    client.post('/api/orange-money/public/payer', json={'nom': 'Diané', 'prenom': 'Aïssatou', 'matricule': mat, 'montant': 100000,
                                                       'transaction_id': 'TX-SMS-0001', 'telephone': '622 11 22 33'})
    assert envoyes == []  # rien tant que ce n'est pas validé
    did = client.get('/api/orange-money/declarations?statut=a_valider', headers=entetes).get_json()[0]['id']
    client.post(f'/api/orange-money/declarations/{did}/valider', headers=entetes)
    assert len(envoyes) == 1 and envoyes[0][0] == '622 11 22 33' and 'REC-' in envoyes[0][1] and '100 000 GNF' in envoyes[0][1]


def test_qr_de_l_ecole_visible_sans_connexion(client, entetes):
    import io
    import segno
    buf = io.BytesIO(); segno.make('TEST').save(buf, kind='png', scale=4)
    r = client.post('/api/orange-money/qr', data={'qr': (io.BytesIO(buf.getvalue()), 'qr.png')}, headers=entetes, content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    url = client.get('/api/orange-money/public/config').get_json()['qr_url']
    assert url and client.get(url).status_code == 200  # la page publique doit pouvoir l'afficher


def test_rapprochement_avec_le_releve_orange(client, entetes, creer_eleve, creer_paiement):
    import io
    e, mat = _eleve_matricule(client, entetes, creer_eleve, creer_paiement)
    ident = {'nom': 'Diané', 'prenom': 'Aïssatou', 'matricule': mat}
    for tx, m in (('RAPP-OK-0001', 100000), ('RAPP-MONTANT-02', 150000), ('RAPP-ABSENT-03', 50000)):
        assert client.post('/api/orange-money/public/payer', json={**ident, 'montant': m, 'transaction_id': tx}).status_code == 200
    csv = ("Date;Référence;Détail;Montant;Solde\n"
           "21/10/2026;RAPP-OK-0001;Paiement marchand;100 000;900 000\n"
           "21/10/2026;RAPP-MONTANT-02;Paiement marchand;120 000;1 020 000\n").encode('utf-8')

    def envoyer(appliquer):
        return client.post('/api/orange-money/declarations/rapprocher', headers=entetes, content_type='multipart/form-data',
                           data={'fichier': (io.BytesIO(csv), 'releve.csv'), 'appliquer': '1' if appliquer else '0'})
    apercu = envoyer(False).get_json()
    etats = {x['transaction_id']: x['etat'] for x in apercu['resultat']}
    assert etats['RAPP-OK-0001'] == 'confirme' and etats['RAPP-MONTANT-02'] == 'montant_different' and etats['RAPP-ABSENT-03'] == 'introuvable'
    assert _reste(client, entetes, e['id']) == 600000  # l'aperçu ne modifie rien
    r = envoyer(True).get_json()
    assert r['valides'] == 1 and _reste(client, entetes, e['id']) == 500000  # seul le paiement confirmé est encaissé
    restants = {x['transaction_id'] for x in client.get('/api/orange-money/declarations?statut=a_valider', headers=entetes).get_json()}
    assert {'RAPP-MONTANT-02', 'RAPP-ABSENT-03'} <= restants
    assert client.post('/api/orange-money/declarations/rapprocher', headers=entetes, data={}).status_code == 400


def test_export_mensuel(client, entetes, creer_eleve, creer_paiement):
    from datetime import datetime
    e, p1, p2 = _dossier(client, entetes, creer_eleve, creer_paiement)
    d = client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 400000, 'transaction_id': 'MP.EXPORT.1'}, headers=entetes).get_json()
    client.post('/api/orange-money/declarations', json={'eleve_id': e['id'], 'montant': 1000, 'transaction_id': 'MP.EXPORT.2'}, headers=entetes)  # reste à valider
    mois = datetime.utcnow().strftime('%Y-%m')
    avant = client.get(f'/api/orange-money/export?format=json&mois={mois}', headers=entetes).get_json()
    client.post(f"/api/orange-money/declarations/{d['id']}/valider", headers=entetes)
    apres = client.get(f'/api/orange-money/export?format=json&mois={mois}', headers=entetes).get_json()
    assert apres['nombre'] == avant['nombre'] + 1 and apres['total'] == avant['total'] + 400000
    csv_ = client.get(f'/api/orange-money/export?mois={mois}', headers=entetes)
    texte = csv_.data.decode('utf-8-sig')
    assert csv_.mimetype == 'text/csv' and 'MP.EXPORT.1' in texte and 'MP.EXPORT.2' not in texte
    assert texte.splitlines()[-1].startswith('TOTAL;')
    assert client.get('/api/orange-money/export?mois=2026-13', headers=entetes).status_code == 400
    assert client.get('/api/orange-money/export?mois=2020-01&format=json', headers=entetes).get_json()['nombre'] == 0
