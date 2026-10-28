"""
Assistante IA de MY-ECOLE : aide à l'utilisation de l'application et réponses pédagogiques
(sciences, mathématiques, langues, histoire-géographie… Guinée, Afrique, monde).

Respect des données : la conversation passe par le serveur (la clé d'API n'est jamais exposée au navigateur) ;
AUCUNE donnée de la base (élèves, notes, paiements) n'est envoyée au modèle — seulement ce que l'utilisateur écrit.
Le contenu des échanges n'est pas conservé ; seul le nombre de messages est compté (quota et traçabilité).
"""
import json
import os
import urllib.request
import urllib.error
from datetime import date

from flask import Blueprint, request, jsonify, g

from database import db, log_action
from auth import require_auth

bp = Blueprint('assistant_routes', __name__, url_prefix='/api/assistant')

URL_API = 'https://api.anthropic.com/v1/messages'
MESSAGES_MAX = 20
LONGUEUR_MAX = 4000
QUOTA_JOUR_DEFAUT = 300          # messages par établissement et par jour (ASSISTANT_MAX_JOUR)
PAR_MINUTE = 12                  # messages par utilisateur et par minute

GUIDE_APPLICATION = """
MY-ECOLE est une application de gestion scolaire (web, Windows, Mac, Android). Rubriques (modules) du tableau de bord :
- Scolarité : élèves (fiche, photo, badge sécurisé avec QR vérifiable), classes, salles, emploi du temps, séances de cours, notes et bulletins,
  devoirs, absences, pointage, discipline, examens, bibliothèque (prêts/retours), réinscriptions, élève du mois, import d'élèves (Excel).
- Finances : paiements de scolarité (reçus), cantine, comptabilité (entrées/sorties, justificatifs, règlement des fournisseurs, dettes fournisseurs,
  relevé bancaire), fournisseurs, logistique (stock, commandes, maintenance, transport), budgets.
- Ressources humaines : personnel, paie (bulletins, primes, avances), candidatures (recrutement).
- Communication : annonces, messages, actualités du site, WhatsApp/SMS.
- Administration : utilisateurs et droits par rôle, journal d'audit (traçabilité, intégrité SHA-256), paramètres de l'établissement, sauvegardes,
  vitrine publique (site de l'école, vérification de badge, préinscription en ligne).
Sécurité : double authentification (TOTP) obligatoire pour admin, directeur et comptable ; mot de passe de 12 caractères pour ces rôles ;
déconnexion après 30 minutes d'inactivité ; un motif écrit est demandé pour supprimer une donnée financière ; les comptes ayant agi ne peuvent
pas être supprimés (seulement désactivés). Les boutons « ← Retour » et « 🏠 Accueil » sont en haut de chaque page.
Rôles : admin, directeur, directeur d'études, comptable, secrétaire, enseignant, chargé de communication, parent.
"""


def _prompt_systeme(role, page):
    return (
        "Tu es l'Assistante MY-ECOLE, une assistante IA complète intégrée à l'application de gestion scolaire MY-ECOLE. "
        "Tu as deux missions.\n"
        "1) AIDE À L'APPLICATION : expliquer pas à pas comment accomplir une tâche dans MY-ECOLE (inscrire un élève, enregistrer un paiement, "
        "saisir des notes, éditer un bulletin, gérer les droits…). Appuie-toi sur le guide ci-dessous ; si tu n'es pas sûre qu'une fonction existe, "
        "dis-le au lieu d'inventer.\n"
        "2) ÉDUCATION ET CONNAISSANCES : répondre à toute question de sciences (mathématiques, physique, chimie, SVT), langues (français, anglais, arabe, "
        "langues nationales de Guinée), histoire, géographie, éducation civique, philosophie, informatique, économie, etc., sur la Guinée, l'Afrique et le monde. "
        "Aide les enseignants (préparation de cours, fiches pédagogiques, exercices et corrigés, évaluations, barèmes, approche par compétences, programmes "
        "de Guinée : primaire, collège, lycée, examens nationaux CEPE, BEPC, Baccalauréat), les élèves et les parents (explications, méthodes de travail, révisions).\n"
        "Règles : réponds en français (ou dans la langue de l'utilisateur), de façon claire, structurée et adaptée au niveau ; montre les étapes des calculs ; "
        "pour les élèves, explique plutôt que de donner seulement le résultat. Sois honnête : si tu n'es pas certaine d'un fait précis (date, chiffre, loi, "
        "programme officiel), dis-le et invite à vérifier la source officielle ; tu n'as pas accès à Internet ni aux données de l'école, donc tu ne connais "
        "pas les actualités récentes ni les informations sur des élèves précis. Ne demande pas et ne retiens pas de données personnelles (noms d'élèves, "
        "notes individuelles, numéros) : conseille de les anonymiser. Refuse poliment tout contenu dangereux, haineux ou sexuel, et reste respectueuse. "
        "Pour les questions médicales, juridiques ou financières, donne une information générale et recommande un professionnel.\n"
        f"Rôle de l'utilisateur dans l'application : {role}. Page actuellement ouverte : {page or 'inconnue'}.\n"
        f"GUIDE DE L'APPLICATION :{GUIDE_APPLICATION}"
    )


def _cle_api():
    return os.environ.get('ANTHROPIC_API_KEY', '').strip()


def _quota_jour():
    try:
        return int(os.environ.get('ASSISTANT_MAX_JOUR', QUOTA_JOUR_DEFAUT))
    except ValueError:
        return QUOTA_JOUR_DEFAUT


def _compter_usage(ecole_id):
    """Incrémente le compteur du jour ; renvoie False si le quota de l'établissement est atteint."""
    jour = date.today().isoformat()
    ligne = db.execute("SELECT nb FROM assistant_usage WHERE ecole_id=? AND jour=?", (ecole_id, jour)).fetchone()
    if ligne and ligne['nb'] >= _quota_jour():
        return False
    db.execute("INSERT INTO assistant_usage (ecole_id, jour, nb) VALUES (?,?,1) "
               "ON CONFLICT(ecole_id, jour) DO UPDATE SET nb = nb + 1", (ecole_id, jour))
    db.commit()
    return True


def _appeler_modele(systeme, messages):
    """Appel à l'API Messages d'Anthropic. Isolé pour pouvoir être simulé dans les tests."""
    corps = json.dumps({
        'model': os.environ.get('ASSISTANT_MODEL', 'claude-sonnet-5-5'),
        'max_tokens': 1800,
        'system': systeme,
        'messages': messages,
    }).encode()
    req = urllib.request.Request(URL_API, data=corps, headers={
        'content-type': 'application/json', 'x-api-key': _cle_api(), 'anthropic-version': '2023-06-01'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    return ''.join(b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text').strip()


@bp.route('/statut', methods=['GET'])
@require_auth
def statut():
    return jsonify({'actif': bool(_cle_api()), 'quota_jour': _quota_jour()})


@bp.route('/discuter', methods=['POST'])
@require_auth
def discuter():
    if not _cle_api():
        return jsonify({'error': "L'assistante n'est pas encore activée sur ce serveur (clé ANTHROPIC_API_KEY à renseigner par l'administrateur).",
                        'code': 'ASSISTANT_NON_CONFIGURE'}), 503
    import securite
    attente = securite.debit_assistant(g.user['id'], PAR_MINUTE)
    if attente:
        return jsonify({'error': f"Un instant : trop de messages. Réessayez dans {attente} s."}), 429
    body = request.get_json(silent=True) or {}
    brut = body.get('messages')
    if not isinstance(brut, list) or not brut:
        return jsonify({'error': 'Message vide'}), 400
    messages = []
    for m in brut[-MESSAGES_MAX:]:
        role = 'assistant' if m.get('role') == 'assistant' else 'user'
        texte = str(m.get('content') or '').strip()[:LONGUEUR_MAX]
        if texte:
            messages.append({'role': role, 'content': texte})
    while messages and messages[0]['role'] != 'user':
        messages.pop(0)
    if not messages or messages[-1]['role'] != 'user':
        return jsonify({'error': 'Message vide'}), 400
    if not _compter_usage(g.user['ecole_id']):
        return jsonify({'error': "Le quota quotidien de l'assistante est atteint pour votre établissement. Réessayez demain."}), 429
    try:
        reponse = _appeler_modele(_prompt_systeme(g.user.get('role'), str(body.get('page') or '')[:60]), messages)
    except urllib.error.HTTPError as e:
        print(f"[assistant] erreur API {e.code}")
        return jsonify({'error': "L'assistante est momentanément indisponible. Réessayez dans un instant."}), 502
    except Exception as e:
        print(f"[assistant] erreur: {type(e).__name__}")
        return jsonify({'error': "L'assistante est momentanément indisponible. Réessayez dans un instant."}), 502
    log_action(g.user, 'question_assistante', 'assistant', None, {'longueur': len(messages[-1]['content'])})
    return jsonify({'reponse': reponse or "Je n'ai pas pu formuler de réponse. Pouvez-vous reformuler ?"})
