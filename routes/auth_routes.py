from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from auth import (login as do_login, require_auth, emettre_jeton, revoquer_sessions, revoquer_jeton,
                  creer_session, renouveler_session, mfa_requise, revoquer_session_appareil)
import securite
import coffre
import double_authentification as da
from database import log_action

bp = Blueprint('auth_routes', __name__, url_prefix='/api/auth')


def _journaliser_securite(action, username, code_ecole):
    """Trace les échecs de connexion (détection d'attaques) sans jamais enregistrer de mot de passe."""
    from database import ecole_id_depuis_code
    try:
        ecole = ecole_id_depuis_code(code_ecole) if code_ecole else 1
        log_action({'id': None, 'name': str(username)[:80], 'ecole_id': ecole}, action, 'securite', None,
                   {'ip': securite.adresse_client()})
    except Exception:
        pass


def _alerter_verrouillage(username, code_ecole):
    """E-mail d'alerte au titulaire du compte et aux administrateurs de l'école (en arrière-plan)."""
    import threading
    from database import ecole_id_depuis_code
    import email_service
    try:
        ecole = ecole_id_depuis_code(code_ecole) if code_ecole else 1
        titulaire = db.execute("SELECT full_name, email FROM users WHERE ecole_id=? AND username=?", (ecole, username)).fetchone()
        admins = db.execute("SELECT email FROM users WHERE ecole_id=? AND role='admin' AND active=1 AND email IS NOT NULL AND email<>''",
                            (ecole,)).fetchall()
        destinataires = {a['email'] for a in admins}
        if titulaire and titulaire['email']:
            destinataires.add(titulaire['email'])
        ip = securite.adresse_client()
    except Exception:
        return
    if not destinataires:
        return
    corps = (f"<p>Plusieurs tentatives de connexion échouées ont été détectées sur le compte <b>{__import__('html').escape(str(username))}</b> "
             f"(adresse {__import__('html').escape(ip)}).</p><p>Par sécurité, le compte est <b>temporairement verrouillé</b> (quelques minutes). "
             "Si ce n'était pas vous, changez votre mot de passe dès que possible et prévenez votre administrateur.</p>")
    def envoyer():
        for d in destinataires:
            email_service.envoyer_email(d, "Alerte sécurité : compte temporairement verrouillé", corps)
    threading.Thread(target=envoyer, daemon=True).start()


@bp.route('/login', methods=['POST'])
def login_route():
    body = request.get_json(silent=True) or {}
    username, password = body.get('username'), body.get('password')
    code_ecole = body.get('code_ecole')
    if not username or not password:
        return jsonify({'error': 'Identifiant et mot de passe requis'}), 400
    cles = securite.cles_connexion(code_ecole or '1', username)
    attente = securite.secondes_restantes(cles)
    if attente:
        minutes = (attente + 59) // 60
        r = jsonify({'error': f"Trop de tentatives de connexion. Réessayez dans {minutes} minute{'s' if minutes > 1 else ''}."})
        r.status_code = 429
        r.headers['Retry-After'] = str(attente)
        return r
    result = do_login(username, password, code_ecole)
    if result == 'ecole_non_confirmee':
        return jsonify({'error': "Cette école n'a pas encore confirmé son adresse e-mail — vérifiez la boîte de réception (et les indésirables) pour le lien reçu à l'inscription."}), 403
    if result == 'compte_non_confirme':
        return jsonify({'error': "Ce compte n'est pas encore activé — vérifiez votre boîte de réception (et vos indésirables) pour le lien d'activation."}), 403
    if result == 'compte_desactive':
        return jsonify({'error': "Ce compte a été désactivé — contactez votre administration."}), 403
    if not result:
        _journaliser_securite('echec_connexion', username, code_ecole)
        if securite.enregistrer_echec(cles):
            _journaliser_securite('compte_verrouille', username, code_ecole)
            _alerter_verrouillage(username, code_ecole)
        return jsonify({'error': 'Identifiant, mot de passe ou établissement incorrect'}), 401
    # Double authentification : mot de passe correct, mais le compte exige aussi un code.
    u = db.execute("SELECT id, totp_secret, totp_actif, totp_dernier_pas, codes_secours FROM users WHERE id=?",
                   (result['user']['id'],)).fetchone()
    if u and u['totp_actif']:
        code = (body.get('code_2fa') or '').strip()
        if not code:
            return jsonify({'requires_2fa': True}), 200
        pas = da.verifier(coffre.dechiffrer(u['totp_secret']), code, u['totp_dernier_pas'])
        if pas:
            db.execute("UPDATE users SET totp_dernier_pas=? WHERE id=?", (pas, u['id']))
            db.commit()
        else:
            reste = da.consommer_code_secours(u['codes_secours'], code)
            if reste is None:
                _journaliser_securite('echec_2fa', username, code_ecole)
                if securite.enregistrer_echec(cles):
                    _journaliser_securite('compte_verrouille', username, code_ecole)
                    _alerter_verrouillage(username, code_ecole)
                return jsonify({'error': 'Code de vérification incorrect', 'requires_2fa': True}), 401
            db.execute("UPDATE users SET codes_secours=? WHERE id=?", (reste, u['id']))
            db.commit()
            result['user']['codes_secours_restants'] = len(__import__('json').loads(reste))
    securite.effacer_echecs(cles[0])
    urow = db.execute("SELECT * FROM users WHERE id=?", (result['user']['id'],)).fetchone()
    ua = request.headers.get('User-Agent', '')
    from auth import _appareil
    nouvel_appareil = not db.execute("SELECT 1 FROM sessions_appareils WHERE user_id=? AND appareil=?",
                                     (urow['id'], _appareil(ua))).fetchone()
    result['token'], result['refresh_token'] = creer_session(urow, securite.adresse_client(), ua)
    result['user']['double_auth_requise'] = bool(mfa_requise(urow))
    db.commit()
    if nouvel_appareil:
        log_action({'id': urow['id'], 'name': urow['full_name'], 'ecole_id': urow['ecole_id']},
                   'connexion_nouvel_appareil', 'securite', None, {'ip': securite.adresse_client(), 'appareil': _appareil(ua)})
    log_action({'id': result['user']['id'], 'name': result['user']['full_name'], 'ecole_id': result['user']['ecole_id']},
               'connexion', 'securite', None, {'ip': securite.adresse_client()})
    return jsonify(result)


# ── Gestion de la double authentification par l'utilisateur lui-même ──

@bp.route('/2fa', methods=['GET'])
@require_auth
def statut_2fa():
    u = db.execute("SELECT totp_actif, codes_secours FROM users WHERE id=?", (g.user['id'],)).fetchone()
    restants = len(__import__('json').loads(u['codes_secours'] or '[]')) if u and u['totp_actif'] else 0
    return jsonify({'actif': bool(u and u['totp_actif']), 'codes_secours_restants': restants})


@bp.route('/2fa/preparer', methods=['POST'])
@require_auth
def preparer_2fa():
    """Génère un secret (pas encore actif) à scanner dans l'application d'authentification."""
    u = db.execute("SELECT username, totp_actif FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if u['totp_actif']:
        return jsonify({'error': 'La double authentification est déjà active'}), 400
    secret = da.nouveau_secret()
    db.execute("UPDATE users SET totp_secret=?, totp_dernier_pas=0 WHERE id=?", (coffre.chiffrer(secret), g.user['id']))
    db.commit()
    return jsonify({'secret': secret, 'uri': da.uri_otpauth(secret, u['username'])})


@bp.route('/2fa/activer', methods=['POST'])
@require_auth
def activer_2fa():
    body = request.get_json(silent=True) or {}
    u = db.execute("SELECT totp_secret, totp_actif FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if u['totp_actif'] or not u['totp_secret']:
        return jsonify({'error': 'Préparez d\'abord la double authentification'}), 400
    pas = da.verifier(coffre.dechiffrer(u['totp_secret']), body.get('code'))
    if not pas:
        return jsonify({'error': 'Code incorrect : vérifiez l\'heure de votre téléphone et réessayez'}), 400
    codes, empreintes = da.generer_codes_secours()
    db.execute("UPDATE users SET totp_actif=1, totp_dernier_pas=?, codes_secours=? WHERE id=?",
               (pas, empreintes, g.user['id']))
    db.commit()
    log_action(g.user, 'activation_2fa', 'utilisateur', str(g.user['id']), {})
    u2 = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],)).fetchone()
    return jsonify({'success': True, 'codes_secours': codes, 'token': emettre_jeton(u2, g.user.get('sid'))})


@bp.route('/2fa/desactiver', methods=['POST'])
@require_auth
def desactiver_2fa():
    body = request.get_json(silent=True) or {}
    u = db.execute("SELECT password_hash, totp_secret, totp_actif, totp_dernier_pas FROM users WHERE id=?",
                   (g.user['id'],)).fetchone()
    if not u['totp_actif']:
        return jsonify({'success': True})
    if not check_password_hash(u['password_hash'], body.get('password') or ''):
        return jsonify({'error': 'Mot de passe incorrect'}), 401
    if not da.verifier(coffre.dechiffrer(u['totp_secret']), body.get('code'), u['totp_dernier_pas']):
        return jsonify({'error': 'Code de vérification incorrect'}), 401
    db.execute("UPDATE users SET totp_actif=0, totp_secret=NULL, codes_secours=NULL, totp_dernier_pas=0 WHERE id=?",
               (g.user['id'],))
    db.commit()
    log_action(g.user, 'desactivation_2fa', 'utilisateur', str(g.user['id']), {})
    return jsonify({'success': True})


@bp.route('/me', methods=['GET'])
@require_auth
def me():
    u = db.execute(
        "SELECT id,ecole_id,username,full_name,role,email,telephone,civilite FROM users WHERE id=?", (g.user['id'],)
    ).fetchone()
    if not u:
        return jsonify({'error': 'Introuvable'}), 404
    d = dict(u)
    d['doit_changer_mot_de_passe'] = bool(g.user.get('mdp_provisoire'))
    return jsonify(d)


@bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    body = request.get_json(silent=True) or {}
    old_password, new_password = body.get('oldPassword'), body.get('newPassword')
    if not old_password or not new_password:
        return jsonify({'error': 'Champs requis'}), 400
    erreur = securite.erreur_mot_de_passe(new_password, g.user.get('username'), g.user.get('role'))
    if erreur:
        return jsonify({'error': erreur}), 400
    u = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],)).fetchone()
    if not check_password_hash(u['password_hash'], old_password):
        return jsonify({'error': 'Ancien mot de passe incorrect'}), 401
    if old_password == new_password:
        return jsonify({'error': "Le nouveau mot de passe doit être différent de l'ancien"}), 400
    db.execute("UPDATE users SET password_hash=?, doit_changer_mdp=0 WHERE id=?",
               (generate_password_hash(new_password), g.user['id']))
    revoquer_sessions(g.user['id'])  # les autres appareils/jetons volés sont déconnectés
    db.commit()
    u = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],)).fetchone()
    # Nouveau jeton sans la mention « mot de passe provisoire » : l'utilisateur peut continuer sans se reconnecter.
    acces, renouv = creer_session(u, securite.adresse_client(), request.headers.get('User-Agent', ''))
    db.commit()
    return jsonify({'success': True, 'token': acces, 'refresh_token': renouv})



@bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    """Déconnexion réelle : le jeton est révoqué côté serveur (pas seulement oublié par le navigateur)."""
    revoquer_jeton(g.user)
    if g.user.get('sid'):
        revoquer_session_appareil(g.user['sid'])
    db.commit()
    log_action(g.user, 'deconnexion', 'session', str(g.user['id']), {})
    reponse = jsonify({'success': True})
    reponse.delete_cookie('gs_media', path='/uploads')
    return reponse


@bp.route('/logout-all', methods=['POST'])
@require_auth
def logout_all():
    """Déconnecte tous les appareils de l'utilisateur (téléphone perdu, session oubliée…)."""
    revoquer_sessions(g.user['id'])
    db.commit()
    log_action(g.user, 'deconnexion_tous_appareils', 'session', str(g.user['id']), {})
    reponse = jsonify({'success': True})
    reponse.delete_cookie('gs_media', path='/uploads')
    return reponse


@bp.route('/refresh', methods=['POST'])
def renouveler():
    """Renouvelle l'accès (1 h) avec le jeton de renouvellement (7 jours, à usage unique)."""
    if securite.debit_depasse('connexion', 'refresh:' + securite.adresse_client()):
        return jsonify({'error': 'Trop de requêtes'}), 429
    body = request.get_json(silent=True) or {}
    res, erreur = renouveler_session(body.get('refresh_token'), securite.adresse_client())
    if erreur:
        return jsonify({'error': erreur}), 401
    db.commit()
    return jsonify({'token': res['token'], 'refresh_token': res['refresh_token']})


@bp.route('/sessions', methods=['GET'])
@require_auth
def mes_appareils():
    """Appareils actuellement connectés au compte (contrôle des appareils de connexion)."""
    now = int(__import__('time').time())
    lignes = db.execute("SELECT id, ip, appareil, cree_le, derniere_activite FROM sessions_appareils "
                        "WHERE user_id=? AND revoquee=0 AND expire_le>? ORDER BY derniere_activite DESC",
                        (g.user['id'], now)).fetchall()
    return jsonify([dict(l, courante=(l['id'] == g.user.get('sid'))) for l in lignes])


@bp.route('/sessions/<sid>', methods=['DELETE'])
@require_auth
def deconnecter_appareil(sid):
    s = db.execute("SELECT id FROM sessions_appareils WHERE id=? AND user_id=?", (sid, g.user['id'])).fetchone()
    if not s:
        return jsonify({'error': 'Appareil introuvable'}), 404
    revoquer_session_appareil(sid)
    db.commit()
    log_action(g.user, 'deconnexion_appareil', 'session', sid, {})
    return jsonify({'success': True})
