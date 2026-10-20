#!/usr/bin/env python3
"""
Relais de pointage MY-ECOLE — à installer sur un ordinateur de l'école.

Il récupère les passages enregistrés par l'appareil de pointage et les envoie au site
MY-ECOLE. Les doublons sont ignorés par le site : on peut le lancer aussi souvent que
l'on veut (toutes les 5 minutes, par exemple), sans risque.

Trois modes :
  1) Appareil ZKTeco sur le réseau de l'école (nécessite : pip install pyzk)
       python relais_pointage.py --site https://my-ecole.onrender.com --cle MA_CLE --appareil 192.168.1.201
  2) Fichier exporté de l'appareil (clé USB : .dat, .csv, .txt — « numéro ; date heure »)
       python relais_pointage.py --site https://my-ecole.onrender.com --cle MA_CLE --fichier export.dat
  3) Essai sans appareil : ajoutez --essai pour voir ce qui serait envoyé, sans rien envoyer.

La clé se crée dans MY-ECOLE : Pointage → Appareils → Ajouter un appareil.
Aucune empreinte ni aucun visage n'est lu ni envoyé : seulement « numéro + heure ».
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

LOT = 1000                       # passages par envoi
FICHIER_ETAT = 'relais_pointage_etat.json'


def lire_fichier(chemin):
    """Passages d'un fichier texte exporté. Accepte tabulation, point-virgule ou virgule,
    « numéro, date heure » ou « numéro, date, heure »."""
    passages = []
    with open(chemin, encoding='utf-8-sig', errors='replace') as f:
        for ligne in f:
            champs = [c.strip() for c in re.split(r'[\t;,]', ligne.strip()) if c.strip() != '']
            if len(champs) < 2 or not champs[0].replace(' ', '').isalnum():
                continue
            horodatage = champs[1]
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', horodatage) and len(champs) > 2 and re.match(r'\d{1,2}:\d{2}', champs[2]):
                horodatage = f"{horodatage} {champs[2]}"
            if re.match(r'\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}', horodatage):
                passages.append({'code': champs[0], 'horodatage': horodatage})
    return passages


def lire_appareil(adresse, port, delai):
    try:
        from zk import ZK
    except ImportError:
        sys.exit("Le module « pyzk » est nécessaire pour lire l'appareil : pip install pyzk")
    connexion = ZK(adresse, port=port, timeout=delai).connect()
    try:
        return [{'code': str(a.user_id), 'horodatage': a.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
                for a in connexion.get_attendance()]
    finally:
        connexion.disconnect()


def envoyer(site, cle, passages):
    requete = urllib.request.Request(
        site.rstrip('/') + '/api/pointage/passages', method='POST',
        headers={'Content-Type': 'application/json', 'X-Cle-Appareil': cle},
        data=json.dumps({'passages': passages}).encode('utf-8'))
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        return json.loads(reponse.read().decode('utf-8'))


def main():
    p = argparse.ArgumentParser(description="Envoie les passages de l'appareil de pointage vers MY-ECOLE")
    p.add_argument('--site', required=True, help="Adresse du site, ex : https://my-ecole.onrender.com")
    p.add_argument('--cle', default=os.environ.get('POINTAGE_CLE'), help="Clé de l'appareil (ou variable POINTAGE_CLE)")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--appareil', help="Adresse IP de l'appareil ZKTeco sur le réseau de l'école")
    source.add_argument('--fichier', help="Fichier exporté de l'appareil")
    p.add_argument('--port', type=int, default=4370)
    p.add_argument('--tout', action='store_true', help="Renvoyer aussi les anciens passages (sinon : depuis la dernière fois)")
    p.add_argument('--essai', action='store_true', help="Afficher sans envoyer")
    a = p.parse_args()
    if not a.cle and not a.essai:
        p.error("la clé de l'appareil est requise (--cle ou variable POINTAGE_CLE)")

    passages = lire_fichier(a.fichier) if a.fichier else lire_appareil(a.appareil, a.port, 10)
    print(f"{len(passages)} passage(s) lu(s).")

    etat = {}
    if os.path.exists(FICHIER_ETAT):
        try:
            etat = json.load(open(FICHIER_ETAT, encoding='utf-8'))
        except (OSError, ValueError):
            etat = {}
    if not a.tout and etat.get('dernier'):
        # Marge d'un jour : le site ignore les doublons, on ne risque donc rien à en renvoyer.
        depuis = (datetime.strptime(etat['dernier'], '%Y-%m-%d %H:%M:%S') - timedelta(days=1)).strftime('%Y-%m-%d')
        passages = [x for x in passages if x['horodatage'][:10] >= depuis]
        print(f"{len(passages)} passage(s) depuis le {depuis}.")

    if a.essai:
        for x in passages[:20]:
            print('  ', x['code'], x['horodatage'])
        print("(essai : rien n'a été envoyé)")
        return
    total = {'nouveaux': 0, 'doublons': 0, 'invalides': 0, 'inconnus': 0, 'retards_crees': 0}
    try:
        for i in range(0, len(passages), LOT):
            res = envoyer(a.site, a.cle, passages[i:i + LOT])
            for k in total:
                total[k] += res.get(k, 0)
    except urllib.error.HTTPError as e:
        sys.exit(f"Le site a refusé l'envoi (code {e.code}) — la clé est-elle correcte et l'appareil actif ?")
    except OSError as e:
        sys.exit(f"Site injoignable ({e}). Réessayez quand la connexion Internet est revenue.")
    print(f"Envoyé : {total['nouveaux']} nouveau(x), {total['doublons']} déjà connu(s), "
          f"{total['invalides']} invalide(s), {total['inconnus']} numéro(s) inconnu(s).")
    if passages:
        etat['dernier'] = max(x['horodatage'] for x in passages)[:19].replace('T', ' ')
        if len(etat['dernier']) == 16:
            etat['dernier'] += ':00'
        with open(FICHIER_ETAT, 'w', encoding='utf-8') as f:
            json.dump(etat, f)


if __name__ == '__main__':
    main()
