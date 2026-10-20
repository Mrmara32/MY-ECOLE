"""Choix du parent à contacter pour un élève (relances de paiement, absences…)."""

COLONNES_CONTACT = (
    'e.mere_prenom, e.mere_nom, e.mere_telephone, '
    'e.pere_prenom, e.pere_nom, e.pere_telephone, '
    'e.tuteur_prenom, e.tuteur_nom, e.tuteur_telephone, '
    'e.contact_urgence_nom, e.contact_urgence_telephone'
)


def contact_a_prevenir(r):
    """Premier responsable ayant un numéro, dans l'ordre : mère, père, tuteur, contact
    d'urgence. `r` doit contenir les colonnes de COLONNES_CONTACT. Renvoie
    {'lien', 'nom', 'telephone'} ou None."""
    for prenom, nom, tel, lien in (
        (r['mere_prenom'], r['mere_nom'], r['mere_telephone'], 'Mère'),
        (r['pere_prenom'], r['pere_nom'], r['pere_telephone'], 'Père'),
        (r['tuteur_prenom'], r['tuteur_nom'], r['tuteur_telephone'], 'Tuteur'),
        (None, r['contact_urgence_nom'], r['contact_urgence_telephone'], 'Contact'),
    ):
        if (tel or '').strip():
            return {'lien': lien, 'nom': ' '.join(x for x in (prenom, nom) if x).strip(), 'telephone': tel.strip()}
    return None
