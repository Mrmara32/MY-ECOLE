"""
Assistante IA de MY-ECOLE : aide à l'utilisation de l'application et réponses pédagogiques
(sciences, mathématiques, langues, histoire-géographie… Guinée, Afrique, monde).

Respect des données : la conversation passe par le serveur (la clé d'API n'est jamais exposée au navigateur).
L'assistante peut consulter des STATISTIQUES AGRÉGÉES de l'établissement (assistant_donnees.py) selon le rôle de l'utilisateur ;
jamais de noms d'élèves, de notes individuelles ni de coordonnées. Le contenu des échanges n'est pas conservé ;
seuls le nombre de messages et les outils consultés sont tracés (quota et audit).
"""
import json
import os
import urllib.request
import urllib.error

import assistant_donnees
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
        "3) PILOTAGE DE L'ÉCOLE : tu es impliquée dans la vie de l'établissement. Pour toute question sur les effectifs, les élèves à jour de leurs paiements, "
        "les résultats, l'assiduité, les recettes/dépenses ou la vie scolaire, CONSULTE d'abord les outils de données (chiffres réels, agrégés, sans noms) au lieu de "
        "répondre de mémoire, puis analyse : points forts, points d'alerte, causes probables, puis RECOMMANDATIONS CONCRÈTES et priorisées (qui fait quoi, délai, "
        "indicateur de suivi) — pour la direction : organisation, recouvrement, soutien scolaire, gestion des absences, budget ; pour les enseignants : remédiation, "
        "évaluations, différenciation, travail avec les parents. Ne devine jamais un chiffre : s'il n'est pas dans les outils, dis-le. Les chiffres viennent de la base "
        "de l'école : cite-les tels quels, signale les données manquantes (ex. paiements non enregistrés) et ne t'en sers que pour l'utilisateur connecté. "
        "Si un outil n'est pas disponible pour ce rôle, explique que l'information est réservée à la direction.\n"
        f"Rôle de l'utilisateur dans l'application : {role}. Page actuellement ouverte : {page or 'inconnue'}.\n"
        f"GUIDE DE L'APPLICATION :{GUIDE_APPLICATION}"
    )


def _cle_api():
    return os.environ.get('ANTHROPIC_API_KEY', '').strip()


def _assistant_actif(ecole_id):
    """L'administrateur peut désactiver l'assistante pour son établissement (paramètre assistant_actif = 0)."""
    r = db.execute("SELECT valeur FROM settings WHERE ecole_id=? AND cle='assistant_actif'", (ecole_id,)).fetchone()
    return not (r and str(r['valeur']) == '0')


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


def _appeler_api(charge):
    """Un appel à l'API Messages d'Anthropic. Isolé pour pouvoir être simulé dans les tests."""
    req = urllib.request.Request(URL_API, data=json.dumps(charge).encode(), headers={
        'content-type': 'application/json', 'x-api-key': _cle_api(), 'anthropic-version': '2023-06-01'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def _appeler_modele(systeme, messages, user):
    """Boucle d'outils : le modèle peut consulter les statistiques autorisées pour le rôle (5 tours au plus)."""
    outils = assistant_donnees.outils_pour(user.get('role'))
    messages = list(messages)
    consultes = []
    for _ in range(6):
        charge = {'model': os.environ.get('ASSISTANT_MODEL', 'claude-sonnet-5-5'), 'max_tokens': 2200,
                  'system': systeme, 'messages': messages}
        if outils:
            charge['tools'] = outils
        rep = _appeler_api(charge)
        blocs = rep.get('content', [])
        appels = [b for b in blocs if b.get('type') == 'tool_use']
        if rep.get('stop_reason') != 'tool_use' or not appels:
            texte = ''.join(b.get('text', '') for b in blocs if b.get('type') == 'text').strip()
            return texte, consultes
        messages.append({'role': 'assistant', 'content': blocs})
        resultats = []
        for a in appels:
            consultes.append(a['name'])
            donnees = assistant_donnees.executer(a['name'], user, a.get('input') or {})
            resultats.append({'type': 'tool_result', 'tool_use_id': a['id'], 'content': json.dumps(donnees, ensure_ascii=False)})
        messages.append({'role': 'user', 'content': resultats})
    return "J'ai consulté beaucoup de données sans réussir à conclure ; pouvez-vous préciser votre question ?", consultes


@bp.route('/statut', methods=['GET'])
@require_auth
def statut():
    return jsonify({'actif': bool(_cle_api()) and _assistant_actif(g.user['ecole_id']),
                    'desactivee_par_ecole': not _assistant_actif(g.user['ecole_id']), 'quota_jour': _quota_jour(),
                    'donnees': [o['name'] for o in assistant_donnees.outils_pour(g.user.get('role'))]})


@bp.route('/alertes', methods=['GET'])
@require_auth
def alertes():
    """Le point de l'assistante sur le tableau de bord : calculé par règles, sans clé d'API ni appel externe."""
    try:
        if not _assistant_actif(g.user['ecole_id']):
            return jsonify({'alertes': []})
        return jsonify({'alertes': assistant_donnees.alertes(g.user)})
    except Exception as e:
        print(f"[assistant] alertes: {type(e).__name__}: {e}")
        return jsonify({'alertes': []})


@bp.route('/discuter', methods=['POST'])
@require_auth
def discuter():
    if not _assistant_actif(g.user['ecole_id']):
        return jsonify({'error': "L'assistante est désactivée par l'administration de votre établissement.",
                        'code': 'ASSISTANT_DESACTIVE'}), 403
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
        reponse, consultes = _appeler_modele(_prompt_systeme(g.user.get('role'), str(body.get('page') or '')[:60]), messages, g.user)
    except urllib.error.HTTPError as e:
        print(f"[assistant] erreur API {e.code}")
        return jsonify({'error': "L'assistante est momentanément indisponible. Réessayez dans un instant."}), 502
    except Exception as e:
        print(f"[assistant] erreur: {type(e).__name__}")
        return jsonify({'error': "L'assistante est momentanément indisponible. Réessayez dans un instant."}), 502
    log_action(g.user, 'question_assistante', 'assistant', None, {'longueur': len(messages[-1]['content']), 'donnees_consultees': sorted(set(consultes))})
    return jsonify({'reponse': reponse or "Je n'ai pas pu formuler de réponse. Pouvez-vous reformuler ?"})
