"""
Envoi d'e-mails (confirmations de compte, notifications) via SMTP.

Configuré pour Gmail par défaut. Reste compatible avec n'importe quel autre
service SMTP standard (Brevo, Mailgun, SendGrid…) en changeant EMAIL_HOST /
EMAIL_PORT — utile si la délivrabilité de Gmail personnel pose problème
(certains fournisseurs de messagerie filtrent silencieusement les envois
automatiques venant d'un compte Gmail personnel, sans même passer par les
indésirables).

Configuration requise (variables d'environnement, à définir sur l'hébergeur —
jamais dans le code) :
  EMAIL_ADRESSE        : l'adresse d'envoi (ex: contact@monecole.com ou un Gmail).
                         Pour Gmail, nécessite un "mot de passe d'application"
                         (voir https://myaccount.google.com/apppasswords —
                         requiert la validation en 2 étapes activée).
  EMAIL_MOT_DE_PASSE   : le mot de passe d'application (PAS le mot de passe
                         normal du compte).
  EMAIL_EXPEDITEUR     : optionnel — adresse affichée comme expéditeur si elle
                         diffère de EMAIL_ADRESSE (utile avec certains services
                         comme Brevo qui séparent identifiant de connexion et
                         expéditeur validé). À défaut, EMAIL_ADRESSE est utilisée.
  EMAIL_EXPEDITEUR_NOM : optionnel — nom affiché avant l'adresse (ex: "MY-ECOLE").
  EMAIL_HOST           : optionnel, défaut smtp.gmail.com
  EMAIL_PORT           : optionnel, défaut 587
  URL_APPLICATION      : l'adresse publique de l'application (pour les liens dans
                         les e-mails, ex: https://my-ecole.onrender.com) — sans
                         slash final

Si ces variables ne sont pas définies, l'envoi est silencieusement ignoré (avec un
message dans les logs) plutôt que de faire planter l'application — un e-mail non
envoyé ne doit jamais empêcher une inscription de fonctionner.
"""
import os
import base64
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import formataddr
from email import encoders


def _config_disponible():
    return bool(os.environ.get('EMAIL_ADRESSE') and os.environ.get('EMAIL_MOT_DE_PASSE'))


def generer_jeton():
    """Jeton aléatoire pour les liens de confirmation par e-mail (usage unique)."""
    return secrets.token_urlsafe(32)


def url_application():
    return os.environ.get('URL_APPLICATION', 'http://localhost:3000').rstrip('/')


def envoyer_email(destinataire, sujet, corps_html, piece_jointe=None):
    """Envoie un e-mail. Ne lève jamais d'exception vers l'appelant — retourne
    True/False — pour ne jamais bloquer une inscription à cause d'un souci d'envoi.

    piece_jointe (optionnel) : dict {'nom_fichier': str, 'contenu_base64': str,
    'type_mime': str (ex: 'application/pdf')} — pour joindre un document (relevé,
    reçu…) généré côté client et transmis encodé en base64."""
    if not _config_disponible():
        print(f"[email] Configuration absente (EMAIL_ADRESSE / EMAIL_MOT_DE_PASSE) — e-mail à {destinataire} non envoyé")
        return False
    try:
        adresse = os.environ['EMAIL_ADRESSE']
        mot_de_passe = os.environ['EMAIL_MOT_DE_PASSE']
        expediteur_email = os.environ.get('EMAIL_EXPEDITEUR') or adresse
        expediteur_nom = os.environ.get('EMAIL_EXPEDITEUR_NOM')
        host = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
        port = int(os.environ.get('EMAIL_PORT', '587'))

        msg = MIMEMultipart('mixed' if piece_jointe else 'alternative')
        msg['Subject'] = sujet
        msg['From'] = formataddr((expediteur_nom, expediteur_email)) if expediteur_nom else expediteur_email
        msg['To'] = destinataire

        if piece_jointe:
            # Avec pièce jointe : le corps HTML doit être imbriqué dans un sous-message
            # 'alternative' séparé de la pièce jointe (structure MIME 'mixed' standard).
            corps = MIMEMultipart('alternative')
            corps.attach(MIMEText(corps_html, 'html', 'utf-8'))
            msg.attach(corps)
            donnees = base64.b64decode(piece_jointe['contenu_base64'])
            piece = MIMEBase(*piece_jointe.get('type_mime', 'application/pdf').split('/', 1))
            piece.set_payload(donnees)
            encoders.encode_base64(piece)
            piece.add_header('Content-Disposition', 'attachment', filename=piece_jointe['nom_fichier'])
            msg.attach(piece)
        else:
            # Sans pièce jointe : attacher directement le HTML au message 'alternative'
            # de premier niveau — pas besoin (et pas souhaitable) d'imbrication ici,
            # certains clients mail affichent mal un 'alternative' imbriqué sans raison.
            msg.attach(MIMEText(corps_html, 'html', 'utf-8'))

        with smtplib.SMTP(host, port, timeout=15) as serveur:
            serveur.starttls()
            serveur.login(adresse, mot_de_passe)
            serveur.sendmail(expediteur_email, destinataire, msg.as_string())
        return True
    except Exception as e:
        print(f"[email] Échec d'envoi à {destinataire} : {e}")
        return False


def _gabarit(titre, contenu_html, bouton_texte=None, bouton_url=None):
    bouton = ""
    if bouton_texte and bouton_url:
        bouton = f"""
        <div style="text-align:center;margin:28px 0">
          <a href="{bouton_url}" style="background:#F0703F;color:#fff;padding:14px 32px;
             border-radius:999px;text-decoration:none;font-weight:700;font-family:sans-serif;
             display:inline-block">{bouton_texte}</a>
        </div>"""
    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:520px;margin:0 auto;
                background:#F4F7F5;padding:32px 16px">
      <div style="background:#fff;border-radius:16px;padding:32px;border:1px solid #E1E8E4">
        <div style="text-align:center;font-size:40px;margin-bottom:8px">🎓</div>
        <h1 style="color:#0E332C;font-size:20px;text-align:center;margin:0 0 20px">{titre}</h1>
        <div style="color:#374151;font-size:14.5px;line-height:1.6">{contenu_html}</div>
        {bouton}
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:11.5px;margin-top:18px">
        Gestion Scolaire — Actif System Groupe
      </p>
    </div>"""


def _encart_code(code_ecole):
    if not code_ecole or code_ecole == 'ecole-1':
        return ""
    return f"""
        <div style="background:#F4F7F5;border:1px solid #E1E8E4;border-radius:10px;
                    padding:14px 18px;margin:16px 0;text-align:center">
          <div style="font-size:11.5px;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">
            Votre code établissement
          </div>
          <div style="font-size:19px;font-weight:800;color:#0E332C;letter-spacing:.03em">{code_ecole}</div>
          <div style="font-size:11.5px;color:#6B7280;margin-top:4px">
            Il vous sera demandé à chaque connexion — conservez-le précieusement.
          </div>
        </div>"""


def envoyer_confirmation_ecole(email_destinataire, nom_ecole, code_ecole, jeton, admin_username=None, admin_password=None):
    url = f"{url_application()}/api/ecoles/confirmer/{jeton}"
    identifiants_html = ""
    if admin_username and admin_password:
        identifiants_html = f"""
        <div style="background:#F3F4F6;border-radius:8px;padding:16px;margin:16px 0">
          <p style="margin:0 0 8px 0;font-weight:700;color:#111827">Vos identifiants de connexion</p>
          <p style="margin:4px 0"><strong>Identifiant :</strong> {admin_username}</p>
          <p style="margin:4px 0"><strong>Mot de passe :</strong> {admin_password}</p>
          <p style="margin:8px 0 0 0;font-size:12px;color:#6B7280">Conservez-les précieusement et changez le mot de passe après votre première connexion.</p>
        </div>"""
    corps = _gabarit(
        "Bienvenue sur Gestion Scolaire !",
        f"""<p>Bonjour,</p>
        <p>Votre établissement <strong>{nom_ecole}</strong> vient d'être inscrit sur la plateforme.</p>
        {_encart_code(code_ecole)}
        {identifiants_html}
        <p>Pour activer votre compte et commencer à l'utiliser, veuillez confirmer votre adresse e-mail :</p>""",
        bouton_texte="Confirmer mon compte",
        bouton_url=url,
    )
    return envoyer_email(email_destinataire, f"Confirmez votre inscription — {nom_ecole}", corps)


def envoyer_confirmation_enseignant(email_destinataire, nom_enseignant, nom_ecole, code_ecole, jeton):
    url = f"{url_application()}/api/candidatures/confirmer/{jeton}"
    corps = _gabarit(
        "Votre candidature a été acceptée !",
        f"""<p>Bonjour {nom_enseignant},</p>
        <p>Votre candidature chez <strong>{nom_ecole}</strong> a été acceptée. Votre compte
        d'accès à l'application est prêt.</p>
        {_encart_code(code_ecole)}
        <p>Pour l'activer, veuillez confirmer votre adresse e-mail :</p>""",
        bouton_texte="Activer mon compte",
        bouton_url=url,
    )
    return envoyer_email(email_destinataire, f"Candidature acceptée — {nom_ecole}", corps)


def envoyer_confirmation_parent(email_destinataire, nom_parent, nom_ecole, code_ecole, jeton):
    url = f"{url_application()}/api/parent/confirmer/{jeton}"
    corps = _gabarit(
        "Activez votre espace parents",
        f"""<p>Bonjour {nom_parent},</p>
        <p>Votre compte pour suivre la scolarité de votre enfant à <strong>{nom_ecole}</strong> a été créé.</p>
        {_encart_code(code_ecole)}
        <p>Pour l'activer, veuillez confirmer votre adresse e-mail :</p>""",
        bouton_texte="Activer mon compte",
        bouton_url=url,
    )
    return envoyer_email(email_destinataire, f"Activez votre espace parents — {nom_ecole}", corps)
