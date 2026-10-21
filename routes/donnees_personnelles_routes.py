"""
Droits des personnes sur leurs données (RGPD / lois nationales de protection des données) :
  * droit d'accès et de portabilité : export complet des données d'un élève (JSON) ;
  * droit à l'effacement : anonymisation irréversible d'un ancien élève (les chiffres comptables et
    statistiques sont conservés, l'identité et les coordonnées sont effacées).
Réservé à la direction ; chaque opération est tracée au journal d'audit.
"""
import json
from datetime import datetime

from flask import Blueprint, request, jsonify, g, Response

from database import db, rows_to_list, log_action
from auth import require_auth, require_role

bp = Blueprint('donnees_personnelles_routes', __name__, url_prefix='/api/eleves')

# Tables rattachées à un élève (nom -> colonne de liaison)
TABLES_ELEVE = ('notes', 'absences', 'discipline', 'paiements', 'versements', 'reinscriptions', 'decisions_annuelles',
                'appreciations_bulletin', 'cantine_abonnements', 'transport_eleves', 'examen_candidats', 'eleve_du_mois')
CHAMPS_IDENTITE_A_EFFACER = (
    'photo_url', 'date_naissance', 'lieu_naissance', 'adresse', 'telephone', 'email', 'email_parent',
    'pere_nom', 'pere_prenom', 'pere_profession', 'pere_telephone', 'pere_email',
    'mere_nom', 'mere_prenom', 'mere_profession', 'mere_telephone', 'mere_email',
    'tuteur_nom', 'tuteur_prenom', 'tuteur_relation', 'tuteur_telephone', 'tuteur_email',
    'contact_urgence_nom', 'contact_urgence_telephone', 'groupe_sanguin', 'allergies', 'maladies_chroniques',
    'medicaments', 'handicap', 'medecin_nom', 'medecin_telephone', 'assurance_nom', 'assurance_numero', 'vaccins',
)


def _eleve(eleve_id):
    return db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchone()


def _colonnes(table):
    return {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def anonymiser_eleve(ecole, e):
    """Efface l'identité d'un élève (irréversible) ; les chiffres comptables et statistiques restent."""
    eleve_id = e['id']
    sets = ["nom='ANONYME'", "prenom=?"] + [f"{c}=NULL" for c in CHAMPS_IDENTITE_A_EFFACER if c in e.keys()]
    db.execute(f"UPDATE eleves SET {', '.join(sets)} WHERE id=? AND ecole_id=?", (e['matricule'], eleve_id, ecole))
    db.execute("UPDATE examen_candidats SET nom='ANONYME', prenom=?, date_naissance=NULL, telephone=NULL WHERE eleve_id=? AND ecole_id=?",
               (e['matricule'], eleve_id, ecole))
    db.execute("UPDATE prets_livres SET emprunteur_nom=? WHERE emprunteur_id=? AND ecole_id=?", (f"Ancien élève {e['matricule']}", eleve_id, ecole))
    db.execute("UPDATE discipline SET description=NULL WHERE eleve_id=? AND ecole_id=?", (eleve_id, ecole))
    db.execute("DELETE FROM parents_eleves WHERE eleve_id=?", (eleve_id,))
    db.commit()


@bp.route('/<eleve_id>/donnees', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def exporter_donnees(eleve_id):
    e = _eleve(eleve_id)
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    paquet = {'exporte_le': datetime.utcnow().isoformat() + 'Z', 'eleve': dict(e), 'donnees': {}}
    for t in TABLES_ELEVE:
        if 'eleve_id' in _colonnes(t):
            paquet['donnees'][t] = rows_to_list(db.execute(f"SELECT * FROM {t} WHERE eleve_id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchall()) \
                if 'ecole_id' in _colonnes(t) else rows_to_list(db.execute(f"SELECT * FROM {t} WHERE eleve_id=?", (eleve_id,)).fetchall())
    paquet['donnees']['prets_livres'] = rows_to_list(db.execute(
        "SELECT * FROM prets_livres WHERE emprunteur_id=? AND ecole_id=?", (eleve_id, g.user['ecole_id'])).fetchall())
    log_action(g.user, 'export_donnees', 'eleve', eleve_id, {'motif': 'droit d\'accès'})
    nom = f"donnees_{e['matricule'] or eleve_id}.json"
    return Response(json.dumps(paquet, ensure_ascii=False, indent=2, default=str), mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="{nom}"'})


@bp.route('/<eleve_id>/anonymiser', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def anonymiser(eleve_id):
    """Irréversible. Réservé aux élèves qui ne sont plus inscrits ; il faut retaper le matricule pour confirmer."""
    e = _eleve(eleve_id)
    if not e:
        return jsonify({'error': 'Élève introuvable'}), 404
    if e['statut'] == 'actif':
        return jsonify({'error': "Un élève actuellement inscrit ne peut pas être anonymisé : changez d'abord son statut"}), 409
    if (request.get_json(silent=True) or {}).get('confirmation') != e['matricule']:
        return jsonify({'error': "Confirmation incorrecte : saisissez le matricule de l'élève"}), 400
    anonymiser_eleve(g.user['ecole_id'], e)
    log_action(g.user, 'anonymisation', 'eleve', eleve_id, {'matricule': e['matricule']})
    return jsonify({'success': True})


# ── Durées de conservation ────────────────────────────────────────────────────
@bp.route('/retention', methods=['GET'])
@require_auth
@require_role('admin', 'directeur')
def rapport_conservation():
    """Politique de conservation de l'école et dossiers d'anciens élèves ayant dépassé la durée prévue."""
    import retention
    ecole = g.user['ecole_id']
    pol = retention.politique(ecole)
    cands = retention.candidats_anonymisation(ecole, pol['eleves_annees'])
    return jsonify({'politique': pol, 'a_anonymiser': len(cands),
                    'dossiers': [{'id': c['id'], 'matricule': c['matricule'], 'nom': c['nom'], 'prenom': c['prenom'],
                                  'statut': c['statut'], 'derniere_activite': c['derniere_activite']} for c in cands[:200]]})


@bp.route('/retention', methods=['PUT'])
@require_auth
@require_role('admin', 'directeur')
def modifier_politique_conservation():
    import retention
    body = request.get_json(silent=True) or {}
    try:
        retention.enregistrer_politique(g.user['ecole_id'], body.get('eleves_annees'), body.get('journal_mois'))
    except ValueError as err:
        return jsonify({'error': str(err)}), 400
    log_action(g.user, 'politique_conservation', 'ecole', str(g.user['ecole_id']), body)
    return jsonify(retention.politique(g.user['ecole_id']))


@bp.route('/retention/anonymiser', methods=['POST'])
@require_auth
@require_role('admin', 'directeur')
def anonymiser_echus():
    """Anonymise d'un coup tous les anciens élèves ayant dépassé la durée de conservation (irréversible)."""
    import retention
    if (request.get_json(silent=True) or {}).get('confirmation') != 'ANONYMISER':
        return jsonify({'error': 'Confirmation incorrecte : saisissez ANONYMISER'}), 400
    ecole = g.user['ecole_id']
    n = 0
    for c in retention.candidats_anonymisation(ecole, retention.politique(ecole)['eleves_annees']):
        e = db.execute("SELECT * FROM eleves WHERE id=? AND ecole_id=?", (c['id'], ecole)).fetchone()
        if e:
            anonymiser_eleve(ecole, e)
            n += 1
    log_action(g.user, 'anonymisation_en_lot', 'ecole', str(ecole), {'dossiers': n})
    return jsonify({'success': True, 'anonymises': n})
