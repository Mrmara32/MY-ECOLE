"""
Envoi automatique des sauvegardes HORS du serveur, chiffrées.

Pourquoi : le disque de Render peut être perdu (panne, suppression du service, erreur).
Une copie rangée ailleurs est la seule vraie protection.

Fonctionne avec tout stockage compatible S3 : Backblaze B2 (10 Go gratuits), Cloudflare R2
(10 Go gratuits), Wasabi, Amazon S3… Aucune bibliothèque en plus : la signature AWS V4
est faite ici avec la bibliothèque standard.

Réglages (variables d'environnement Render) — tout est obligatoire :
  GS_S3_ENDPOINT   ex. https://s3.us-west-004.backblazeb2.com
  GS_S3_REGION     ex. us-west-004   (« auto » pour Cloudflare R2)
  GS_S3_BUCKET     nom du seau
  GS_S3_KEY_ID     identifiant de la clé d'accès
  GS_S3_SECRET     clé secrète
  GS_BACKUP_CLE    mot de passe de chiffrement (à NOTER AILLEURS : sans lui, la copie est illisible)

Les copies contiennent les données des élèves : elles sont chiffrées (Fernet/AES) AVANT
l'envoi, le stockage ne voit jamais que du contenu illisible. L'envoi est refusé tant que
GS_BACKUP_CLE n'est pas défini. Pour relire une copie : outils_sauvegarde/dechiffrer.py.
La durée de conservation à distance se règle dans le stockage (règle de cycle de vie).
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from cryptography.fernet import Fernet

import sauvegarde

VARIABLES = ('GS_S3_ENDPOINT', 'GS_S3_REGION', 'GS_S3_BUCKET', 'GS_S3_KEY_ID', 'GS_S3_SECRET', 'GS_BACKUP_CLE')
SEL = b'my-ecole-sauvegarde-v1'
DELAI_S = 120


def _val(nom):
    return (os.environ.get(nom) or '').strip()


def configuration_manquante():
    return [v for v in VARIABLES if not _val(v)]


def configure():
    return not configuration_manquante()


def cle_fernet(phrase):
    brut = hashlib.pbkdf2_hmac('sha256', phrase.encode(), SEL, 200_000, dklen=32)
    return base64.urlsafe_b64encode(brut)


def chiffrer(donnees, phrase):
    return Fernet(cle_fernet(phrase)).encrypt(donnees)


def dechiffrer(donnees, phrase):
    return Fernet(cle_fernet(phrase)).decrypt(donnees)


def _hmac(cle, msg):
    return hmac.new(cle, msg.encode(), hashlib.sha256).digest()


def requete_signee(methode, endpoint, region, bucket, objet, corps, key_id, secret, maintenant=None):
    """Renvoie (url, en-têtes) d'une requête S3 signée AWS V4 (adressage par chemin)."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    amz_date = maintenant.strftime('%Y%m%dT%H%M%SZ')
    jour = maintenant.strftime('%Y%m%d')
    hote = urllib.parse.urlparse(endpoint).netloc
    chemin = '/' + urllib.parse.quote(f"{bucket}/{objet}", safe='/-_.~')
    hash_corps = hashlib.sha256(corps).hexdigest()
    entetes = {'host': hote, 'x-amz-content-sha256': hash_corps, 'x-amz-date': amz_date}
    noms = ';'.join(sorted(entetes))
    canon_entetes = ''.join(f"{k}:{entetes[k]}\n" for k in sorted(entetes))
    canonique = '\n'.join([methode, chemin, '', canon_entetes, noms, hash_corps])
    portee = f"{jour}/{region}/s3/aws4_request"
    a_signer = '\n'.join(['AWS4-HMAC-SHA256', amz_date, portee, hashlib.sha256(canonique.encode()).hexdigest()])
    k = _hmac(('AWS4' + secret).encode(), jour)
    for part in (region, 's3', 'aws4_request'):
        k = _hmac(k, part)
    signature = hmac.new(k, a_signer.encode(), hashlib.sha256).hexdigest()
    entetes['Authorization'] = (f"AWS4-HMAC-SHA256 Credential={key_id}/{portee}, "
                                f"SignedHeaders={noms}, Signature={signature}")
    entetes.pop('host')
    return endpoint.rstrip('/') + chemin, entetes


def _etat_chemin():
    return os.path.join(sauvegarde.preparer_dossier(), 'envoi-externe.json')


def lire_etat():
    try:
        with open(_etat_chemin(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _ecrire_etat(**champs):
    etat = {**lire_etat(), **champs}
    with open(_etat_chemin(), 'w', encoding='utf-8') as f:
        json.dump(etat, f)


def televerser(nom_objet, contenu_zip):
    """Chiffre puis envoie. Lève une exception explicite en cas d'échec."""
    manquantes = configuration_manquante()
    if manquantes:
        raise RuntimeError('Réglages manquants : ' + ', '.join(manquantes))
    corps = chiffrer(contenu_zip, _val('GS_BACKUP_CLE'))
    url, entetes = requete_signee('PUT', _val('GS_S3_ENDPOINT'), _val('GS_S3_REGION'), _val('GS_S3_BUCKET'),
                                  nom_objet, corps, _val('GS_S3_KEY_ID'), _val('GS_S3_SECRET'))
    req = urllib.request.Request(url, data=corps, method='PUT', headers=entetes)
    try:
        with urllib.request.urlopen(req, timeout=DELAI_S) as r:
            if r.status not in (200, 201, 204):
                raise RuntimeError(f"Réponse inattendue du stockage : {r.status}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Le stockage a refusé l'envoi (HTTP {e.code}) : {e.read()[:200].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Stockage injoignable : {e.reason}")
    return len(corps)


def envoyer_si_besoin():
    """Envoie la copie du jour si elle n'est pas encore partie. Sans effet si non configuré.
    Appelé toutes les heures : un échec est donc réessayé automatiquement."""
    if not configure():
        return None
    nom = f"ecole-{dt.datetime.now():%Y-%m-%d}.zip"
    if lire_etat().get('dernier_envoi_nom') == nom:
        return None
    chemin = sauvegarde.chemin_sauvegarde(nom)
    if not chemin:
        return None
    try:
        with open(chemin, 'rb') as f:
            taille = televerser(nom + '.enc', f.read())
        _ecrire_etat(dernier_envoi_nom=nom, dernier_envoi=dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
                     taille=taille, derniere_erreur=None)
        return nom
    except Exception as e:
        _ecrire_etat(derniere_erreur=str(e), derniere_erreur_le=dt.datetime.now().strftime('%Y-%m-%d %H:%M'))
        raise


def envoyer_maintenant():
    """Copie fraîche envoyée tout de suite (test depuis l'écran Paramètres)."""
    nom = f"ecole-{dt.datetime.now():%Y-%m-%d-%H%M}-manuel.zip.enc"
    try:
        taille = televerser(nom, sauvegarde.archive_en_memoire().getvalue())
    except Exception as e:
        _ecrire_etat(derniere_erreur=str(e), derniere_erreur_le=dt.datetime.now().strftime('%Y-%m-%d %H:%M'))
        raise
    _ecrire_etat(dernier_envoi_nom=nom, dernier_envoi=dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
                 taille=taille, derniere_erreur=None)
    return nom


def statut():
    return {'configure': configure(), 'manquantes': configuration_manquante(), **lire_etat()}
