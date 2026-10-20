"""
Import d'élèves depuis un fichier Excel (.xlsx) ou CSV : reprise d'une école qui tient
encore ses listes sur papier ou dans un tableur.

Le fichier doit avoir une ligne de titres ; l'ordre des colonnes est libre et les titres
sont reconnus avec ou sans accents, majuscules ou variantes courantes (« Prénom »,
« prenoms », « Date de naissance », « Tél. père »…). Seules « nom » et « prénom » sont
obligatoires.
"""
import unicodedata

from releve_bancaire import _lignes_csv, _lignes_excel, lire_date

MAX_LIGNES = 3000

# titre normalisé -> champ de la table eleves
SYNONYMES = {
    'matricule': 'matricule', 'nom': 'nom', 'nom de famille': 'nom',
    'prenom': 'prenom', 'prenoms': 'prenom',
    'date de naissance': 'date_naissance', 'naissance': 'date_naissance', 'ne le': 'date_naissance',
    'date naissance': 'date_naissance', 'lieu de naissance': 'lieu_naissance', 'lieu naissance': 'lieu_naissance',
    'sexe': 'sexe', 'genre': 'sexe', 'nationalite': 'nationalite', 'classe': 'classe', 'niveau': 'classe',
    'adresse': 'adresse', 'quartier': 'adresse',
    'pere': 'pere_nom', 'nom du pere': 'pere_nom', 'nom pere': 'pere_nom',
    'telephone pere': 'pere_telephone', 'tel pere': 'pere_telephone', 'tel. pere': 'pere_telephone',
    'telephone du pere': 'pere_telephone', 'profession pere': 'pere_profession',
    'mere': 'mere_nom', 'nom de la mere': 'mere_nom', 'nom mere': 'mere_nom',
    'telephone mere': 'mere_telephone', 'tel mere': 'mere_telephone', 'tel. mere': 'mere_telephone',
    'telephone de la mere': 'mere_telephone', 'profession mere': 'mere_profession',
    'tuteur': 'tuteur_nom', 'nom du tuteur': 'tuteur_nom', 'telephone tuteur': 'tuteur_telephone',
    'tel tuteur': 'tuteur_telephone', 'tel. tuteur': 'tuteur_telephone',
    'contact urgence': 'contact_urgence_nom', 'telephone urgence': 'contact_urgence_telephone',
}

MODELE_TITRES = ['Matricule', 'Nom', 'Prénom', 'Date de naissance', 'Lieu de naissance', 'Sexe', 'Classe',
                 'Père', 'Téléphone père', 'Mère', 'Téléphone mère', 'Tuteur', 'Téléphone tuteur', 'Adresse']
MODELE_EXEMPLE = ['', 'Diallo', 'Aïssatou', '14/03/2015', 'Conakry', 'F', 'CP1',
                  'Mamadou Diallo', '622000000', 'Fatoumata Camara', '628000000', '', '', 'Yattaya']


def normaliser(texte):
    t = unicodedata.normalize('NFD', str(texte or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(t.replace('_', ' ').replace('-', ' ').split())


def lire_sexe(valeur):
    v = normaliser(valeur)
    if v in ('m', 'masculin', 'garcon', 'g', 'homme', 'h'):
        return 'M'
    if v in ('f', 'feminin', 'fille', 'femme'):
        return 'F'
    return None


def lire_fichier(contenu, extension):
    """-> (liste de dicts {champ: valeur}, erreur). Le numéro de ligne du fichier est ajouté sous '_ligne'."""
    if extension == '.csv':
        brutes = _lignes_csv(contenu)
    elif extension == '.xlsx':
        brutes = _lignes_excel(contenu)
    else:
        return None, "Format non pris en charge : utilisez un fichier .xlsx (Excel) ou .csv"
    numerotees = [(i, l) for i, l in enumerate(brutes, start=1) if l and any(c is not None and str(c).strip() for c in l)]
    if not numerotees:
        return None, "Le fichier est vide"
    _, titres = numerotees[0]
    colonnes = {}
    for idx, t in enumerate(titres):
        champ = SYNONYMES.get(normaliser(t))
        if champ and champ not in colonnes.values():
            colonnes[idx] = champ
    if 'nom' not in colonnes.values() or 'prenom' not in colonnes.values():
        return None, "Titres de colonnes introuvables : la première ligne doit contenir au moins « Nom » et « Prénom »"
    if len(numerotees) - 1 > MAX_LIGNES:
        return None, f"Trop de lignes (maximum {MAX_LIGNES} par import) : découpez le fichier"
    lignes = []
    for numero, l in numerotees[1:]:
        d = {'_ligne': numero}
        for idx, champ in colonnes.items():
            v = l[idx] if idx < len(l) else None
            if v is not None and str(v).strip():
                d[champ] = v if champ == 'date_naissance' else str(v).strip()
        lignes.append(d)
    return lignes, None


def valider_ligne(d, classes_connues):
    """-> (valeurs prêtes pour l'insertion, liste d'erreurs)."""
    erreurs, v = [], {}
    for champ, val in d.items():
        if champ != '_ligne':
            v[champ] = val
    if not v.get('nom') or not v.get('prenom'):
        erreurs.append('Nom et prénom obligatoires')
    if 'date_naissance' in v:
        iso = lire_date(v['date_naissance'])
        if iso is None:
            erreurs.append(f"Date de naissance illisible (« {v['date_naissance']} ») — attendu JJ/MM/AAAA")
        else:
            v['date_naissance'] = iso
    if 'sexe' in v:
        s = lire_sexe(v['sexe'])
        if s is None:
            erreurs.append(f"Sexe non reconnu (« {v['sexe']} ») — attendu M ou F")
        else:
            v['sexe'] = s
    if v.get('classe') and v['classe'] not in classes_connues:
        erreurs.append(f"Classe inconnue : « {v['classe']} » (à créer d'abord dans Classes)")
    return v, erreurs
