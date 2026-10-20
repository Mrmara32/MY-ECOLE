"""
Outil RÉSERVÉ À L'ÉDITEUR : fabrique les clés de licence de l'exécutable MY-ECOLE.

Il n'est jamais inclus dans l'exécutable (MY-ECOLE.spec ne l'importe pas) et ne contient
aucun secret : il a besoin de la CLÉ PRIVÉE de l'éditeur, un fichier .pem gardé HORS du
projet (jamais dans le dépôt Git, jamais envoyé à une école). Quiconque possède ce
fichier peut fabriquer des licences : le garder comme un mot de passe, avec une copie
de sauvegarde (clé USB, coffre-fort de mots de passe).

Emplacement de la clé privée, par ordre de priorité :
  1. l'option --cle-privee CHEMIN
  2. la variable d'environnement MY_ECOLE_CLE_PRIVEE
  3. %USERPROFILE%\\MY-ECOLE-editeur\\cle_privee_licences_my_ecole.pem
     (~/MY-ECOLE-editeur/... sous Linux/macOS)

Exemples (à lancer depuis le dossier du projet MY-ECOLE) :
  python outils_editeur/generer_licence.py --ecole "École Djely"
  python outils_editeur/generer_licence.py --ecole "École Djely" --expiration 2027-12-31
  python outils_editeur/generer_licence.py --creer-cles     (nouvelle paire de clés)

Nécessite le paquet cryptography (déjà dans requirements.txt).
"""
import argparse
import base64
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Doit rester identique à licence.CONTEXTE_SIGNATURE (vérifié à chaque génération, voir plus bas).
CONTEXTE_SIGNATURE = "MY-ECOLE-LICENCE-V2"
CHEMIN_PAR_DEFAUT = Path.home() / "MY-ECOLE-editeur" / "cle_privee_licences_my_ecole.pem"


def chemin_cle_privee(option):
    return Path(option or os.environ.get("MY_ECOLE_CLE_PRIVEE") or CHEMIN_PAR_DEFAUT)


def identifiant_ecole(nom):
    sans_accents = unicodedata.normalize("NFD", nom).encode("ascii", "ignore").decode("ascii")
    identifiant = re.sub(r"[^A-Za-z0-9]", "", sans_accents).upper()[:12]
    if not identifiant:
        raise SystemExit("Nom d'école invalide : il doit contenir au moins une lettre ou un chiffre.")
    return identifiant


def code_expiration(expiration):
    if not expiration:
        return "PERPETUEL"
    try:
        date_fin = datetime.strptime(expiration, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("Date d'expiration invalide : format attendu AAAA-MM-JJ (ex : 2027-12-31).")
    if date_fin < date.today():
        raise SystemExit(f"La date d'expiration {expiration} est déjà passée.")
    return date_fin.strftime("%Y%m%d")


def charger_cle_privee(chemin):
    if not chemin.exists():
        raise SystemExit(
            f"Clé privée introuvable : {chemin}\n"
            "Placez-y le fichier cle_privee_licences_my_ecole.pem, ou indiquez son emplacement "
            "avec --cle-privee."
        )
    cle = serialization.load_pem_private_key(chemin.read_bytes(), password=None)
    if not isinstance(cle, Ed25519PrivateKey):
        raise SystemExit("Ce fichier n'est pas une clé privée Ed25519 MY-ECOLE.")
    return cle


def generer(nom_ecole, expiration, chemin):
    identifiant = identifiant_ecole(nom_ecole)
    exp = code_expiration(expiration)
    texte = f"{CONTEXTE_SIGNATURE}|{identifiant}|{exp}".encode("ascii")
    signature = charger_cle_privee(chemin).sign(texte)
    cle_licence = f"{identifiant}-{exp}-{base64.b32encode(signature).decode().rstrip('=')}"

    # Contrôle : la licence doit être acceptée par l'application de CE dossier. Si ce n'est
    # pas le cas, la clé privée utilisée ne correspond pas à la clé publique de licence.py.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        import licence
    except ImportError:
        print("(contrôle ignoré : lancez l'outil depuis le dossier du projet pour vérifier la clé)",
              file=sys.stderr)
    else:
        if not licence.signature_valide(identifiant, exp, cle_licence.split("-")[2]):
            raise SystemExit(
                "ERREUR : l'application refuserait cette licence. La clé privée utilisée ne "
                "correspond pas à CLE_PUBLIQUE_LICENCES dans licence.py."
            )
    return cle_licence


def creer_cles(chemin):
    if chemin.exists():
        raise SystemExit(f"{chemin} existe déjà : déplacez-le d'abord (il ne sera jamais écrasé).")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cle = Ed25519PrivateKey.generate()
    chemin.write_bytes(cle.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    try:
        os.chmod(chemin, 0o600)
    except OSError:
        pass
    publique = cle.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print(f"Clé privée créée : {chemin}  (à garder secrète et à sauvegarder)")
    print("Remplacez CLE_PUBLIQUE_LICENCES dans licence.py par :")
    print(base64.b64encode(publique).decode())
    print("puis reconstruisez l'exécutable. Les licences de l'ancienne clé ne seront plus acceptées.")


def main():
    parser = argparse.ArgumentParser(description="Clés de licence MY-ECOLE (réservé à l'éditeur).")
    parser.add_argument("--ecole", help="Nom de l'école (12 lettres/chiffres retenus, sans accents)")
    parser.add_argument("--expiration", help="Date de fin AAAA-MM-JJ (sans cette option : licence perpétuelle)")
    parser.add_argument("--cle-privee", help="Chemin du fichier .pem de la clé privée")
    parser.add_argument("--creer-cles", action="store_true", help="Créer une nouvelle paire de clés")
    args = parser.parse_args()

    chemin = chemin_cle_privee(args.cle_privee)
    if args.creer_cles:
        creer_cles(chemin)
    elif args.ecole:
        print(generer(args.ecole, args.expiration, chemin))
    else:
        parser.error("indiquez --ecole NOM (ou --creer-cles)")


if __name__ == "__main__":
    main()
