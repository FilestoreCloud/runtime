#!/bin/sh
set -e

# In ECS Fargate, /var/www/html is ephemeral container filesystem while /var/www/html/config is mounted to persistent EFS.
# If Nextcloud has already been installed on EFS config (config.php exists):
# 1. We must copy all Nextcloud source files from /usr/src/nextcloud into ephemeral /var/www/html so that
#    Nextcloud core, apps, status.php, and index.php are available.
# 2. We ensure /var/www/html/version.php exists so that official docker-entrypoint.sh recognizes the existing
#    installation and skips `maintenance:install`.
if [ -f /var/www/html/config/config.php ]; then
    if [ ! -f /var/www/html/index.php ]; then
        echo "[STORIX] Populating ephemeral /var/www/html from /usr/src/nextcloud..."
        rsync -a --exclude='/config' /usr/src/nextcloud/ /var/www/html/
    fi
    cp /usr/src/nextcloud/version.php /var/www/html/version.php 2>/dev/null || :
fi

mkdir -p /var/www/html/data
chown www-data:www-data /var/www/html/data 2>/dev/null || :

exec /entrypoint.sh "$@"
