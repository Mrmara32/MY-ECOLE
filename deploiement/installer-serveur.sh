#!/bin/bash
# ==========================================================================
# Script d'installation - Gestion Scolaire
# Groupe Scolaire Elhadji Mountaga Djély
# Développé par Actif System Groupe — Tél : 661-97-43-43
#
# À exécuter UNE SEULE FOIS sur un serveur Ubuntu 22.04 (ou plus récent),
# fraîchement créé, en tant que root (ou avec sudo).
#
# Utilisation :
#   1. Transférez d'abord le dossier gestion-scolaire-py sur le serveur,
#      à l'emplacement /opt/gestion-scolaire (voir le guide pour la commande scp)
#   2. Puis lancez :  sudo bash installer-serveur.sh
# ==========================================================================
set -e

DOMAINE="groupescolairemd.com"
APP_DIR="/opt/gestion-scolaire"

echo "================================================================"
echo "  GESTION SCOLAIRE — Installation sur le serveur"
echo "  Domaine configuré : $DOMAINE"
echo "================================================================"
echo ""

if [ ! -d "$APP_DIR" ]; then
    echo "[ERREUR] Le dossier $APP_DIR est introuvable."
    echo "Transférez d'abord les fichiers de l'application à cet emplacement"
    echo "(voir l'étape 'Transférer les fichiers' du guide) avant de relancer ce script."
    exit 1
fi

echo "→ Étape 1/8 : Mise à jour du système..."
apt update -y && apt upgrade -y

echo "→ Étape 2/8 : Installation de Python, nginx et outils nécessaires..."
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx ufw

echo "→ Étape 3/8 : Création de l'environnement Python de l'application..."
cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "→ Étape 4/8 : Préparation des dossiers de données..."
mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$APP_DIR/public/uploads"
chown -R www-data:www-data "$APP_DIR"

echo "→ Étape 5/8 : Installation du service (démarrage automatique + redémarrage en cas de coupure)..."
cp "$APP_DIR/deploiement/gestion-scolaire.service" /etc/systemd/system/gestion-scolaire.service
systemctl daemon-reload
systemctl enable gestion-scolaire
systemctl restart gestion-scolaire
sleep 3
systemctl status gestion-scolaire --no-pager || true

echo "→ Étape 6/8 : Configuration de nginx (redirection du domaine vers l'application)..."
cp "$APP_DIR/deploiement/nginx-gestion-scolaire.conf" /etc/nginx/sites-available/gestion-scolaire
ln -sf /etc/nginx/sites-available/gestion-scolaire /etc/nginx/sites-enabled/gestion-scolaire
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

echo "→ Étape 7/8 : Ouverture du pare-feu (web + SSH uniquement)..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "→ Étape 8/8 : Certificat de sécurité HTTPS (Let's Encrypt)..."
echo "   (Ceci ne fonctionnera que si $DOMAINE pointe déjà vers ce serveur — voir le guide)"
certbot --nginx -d "$DOMAINE" -d "www.$DOMAINE" --non-interactive --agree-tos -m "contact@$DOMAINE" --redirect || \
    echo "   [ATTENTION] HTTPS non configuré automatiquement. Vérifiez que le domaine pointe bien vers ce serveur, puis relancez : certbot --nginx -d $DOMAINE"

echo ""
echo "================================================================"
echo "  INSTALLATION TERMINÉE"
echo "  Votre application devrait être accessible à :"
echo "  https://$DOMAINE"
echo ""
echo "  Identifiant : admin"
echo "  Mot de passe : Admin@2025!  (à changer immédiatement)"
echo "================================================================"
