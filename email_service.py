"""
Envoi d'e-mails (confirmations de compte, notifications) via SMTP.
Configuré par défaut pour Gmail, mais fonctionne avec n'importe quel service SMTP
standard en changeant les variables d'environnement EMAIL_HOST / EMAIL_PORT.

Configuration requise (variables d'environnement, à définir sur l'hébergeur —
jamais dans le code) :
  EMAIL_ADRESSE       : l'adresse d'envoi (ex: contact@monecole.com ou un Gmail)
  EMAIL_MOT_DE_PASSE  : le "mot de passe d'application" (PAS le mot de passe normal
                        du compte — voir https://myaccount.google.com/apppasswords
                        pour Gmail : nécessite la validation en 2 étapes activée)
  EMAIL_HOST          : optionnel, défaut smtp.gmail.com
  EMAIL_PORT          : optionnel, défaut 587
  URL_APPLICATION     : l'adresse publique de l'application (pour les liens dans les
                        e-mails, ex: https://my-ecole.onrender.com) — sans slash final

Si ces variables ne sont pas définies, l'envoi est silencieusement ignoré (avec un
message dans les logs) plutôt que de faire planter l'application — un e-mail non
envoyé ne doit jamais empêcher une inscription de fonctionner.
"""
import os
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _config_disponible():
    return bool(os.environ.get('EMAIL_ADRESSE') and os.environ.get('EMAIL_MOT_DE_PASSE'))


def generer_jeton():
    """Jeton aléatoire pour les liens de confirmation par e-mail (usage unique)."""
    return secrets.token_urlsafe(32)


def url_application():
    return os.environ.get('URL_APPLICATION', 'http://localhost:3000').rstrip('/')


def envoyer_email(destinataire, sujet, corps_html):
    """Envoie un e-mail. Ne lève jamais d'exception vers l'appelant — retourne
    True/False — pour ne jamais bloquer une inscription à cause d'un souci d'envoi."""
    if not _config_disponible():
        print(f"[email] Configuration absente (EMAIL_ADRESSE / EMAIL_MOT_DE_PASSE) — e-mail à {destinataire} non envoyé")
        return False
    try:
        adresse = os.environ['EMAIL_ADRESSE']
        mot_de_passe = os.environ['EMAIL_MOT_DE_PASSE']
        host = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
        port = int(os.environ.get('EMAIL_PORT', '587'))

        msg = MIMEMultipart('alternative')
        msg['Subject'] = sujet
        msg['From'] = adresse
        msg['To'] = destinataire
        msg.attach(MIMEText(corps_html, 'html', 'utf-8'))

        with smtplib.SMTP(host, port, timeout=15) as serveur:
            serveur.starttls()
            serveur.login(adresse, mot_de_passe)
            serveur.sendmail(adresse, destinataire, msg.as_string())
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


def envoyer_confirmation_ecole(email_destinataire, nom_ecole, jeton):
    url = f"{url_application()}/api/ecoles/confirmer/{jeton}"
    corps = _gabarit(
        "Bienvenue sur Gestion Scolaire !",
        f"""<p>Bonjour,</p>
        <p>Votre établissement <strong>{nom_ecole}</strong> vient d'être inscrit sur la plateforme.</p>
        <p>Pour activer votre compte et commencer à l'utiliser, veuillez confirmer votre adresse e-mail :</p>""",
        bouton_texte="Confirmer mon compte",
        bouton_url=url,
    )
    return envoyer_email(email_destinataire, f"Confirmez votre inscription — {nom_ecole}", corps)


def envoyer_confirmation_enseignant(email_destinataire, nom_enseignant, nom_ecole, jeton):
    url = f"{url_application()}/api/candidatures/confirmer/{jeton}"
    corps = _gabarit(
        "Votre candidature a été acceptée !",
        f"""<p>Bonjour {nom_enseignant},</p>
        <p>Votre candidature chez <strong>{nom_ecole}</strong> a été acceptée. Votre compte
        d'accès à l'application est prêt.</p>
        <p>Pour l'activer, veuillez confirmer votre adresse e-mail :</p>""",
        bouton_texte="Activer mon compte",
        bouton_url=url,
    )
    return envoyer_email(email_destinataire, f"Candidature acceptée — {nom_ecole}", corps)


def envoyer_confirmation_parent(email_destinataire, nom_parent, nom_ecole, jeton):
    url = f"{url_application()}/api/parent/confirmer/{jeton}"
    corps = _gabarit(
        "Activez votre espace parents",
        f"""<p>Bonjour {nom_parent},</p>
        <p>Votre compte pour suivre la scolarité de votre enfant à <strong>{nom_ecole}</strong> a été créé.</p>
        <p>Pour l'activer, veuillez confirmer votre adresse e-mail :</p>""",
        bouton_texte="Activer mon compte",
        bouton_url=url,
    )
    return envoyer_email(email_destinataire, f"Activez votre espace parents — {nom_ecole}", corps)
