#!/bin/sh
set -e

# If REDIS_HOST is empty or unset, ensure official entrypoint does NOT configure Redis as session handler
if [ -z "${REDIS_HOST:-}" ]; then
    unset REDIS_HOST
    unset REDIS_PORT
    rm -f /usr/local/etc/php/conf.d/redis-session.ini 2>/dev/null || :
fi

# In ECS Fargate, /var/www/html is ephemeral container filesystem while /var/www/html/config is mounted to persistent EFS.
# If config.php exists but does NOT contain 'installed' => true, it is an incomplete/failed installation: reset it.
if [ -f /var/www/html/config/config.php ] && ! grep -q "'installed' => true" /var/www/html/config/config.php; then
    echo "[STORIX] Detected incomplete or broken config.php without installed=true; resetting config.php..."
    rm -f /var/www/html/config/config.php
fi

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

mkdir -p /var/www/html/data /var/www/html/apps /var/www/html/custom_apps /var/www/html/themes
chown -R www-data:www-data /var/www/html/data /var/www/html/apps /var/www/html/custom_apps /var/www/html/themes 2>/dev/null || :
chmod -R 775 /var/www/html/apps /var/www/html/custom_apps 2>/dev/null || :

exec /entrypoint.sh "$@"
