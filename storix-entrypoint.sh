#!/bin/sh
set -e

# If REDIS_HOST is empty or unset, ensure official entrypoint does NOT configure Redis as session handler
if [ -z "${REDIS_HOST:-}" ]; then
    unset REDIS_HOST
    unset REDIS_PORT
    rm -f /usr/local/etc/php/conf.d/redis-session.ini 2>/dev/null || :
fi

# Ensure all application and configuration directories exist with correct permissions
mkdir -p /var/www/html/config /var/www/html/data /var/www/html/apps /var/www/html/custom_apps /var/www/html/themes
chown -R www-data:www-data /var/www/html/config /var/www/html/data /var/www/html/apps /var/www/html/custom_apps /var/www/html/themes 2>/dev/null || :
chmod -R 775 /var/www/html/config /var/www/html/apps /var/www/html/custom_apps 2>/dev/null || :

# In ECS Fargate, /var/www/html is ephemeral container filesystem while /var/www/html/config is mounted to persistent EFS.
# Sanitize and validate config.php on EFS if present:
if [ -f /var/www/html/config/config.php ]; then
    sed -i "/PGSQL_ATTR_SSL_MODE/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/pgsql_ssl/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/dbdriveroptions/d" /var/www/html/config/config.php 2>/dev/null || :
fi

# If config.php exists but does NOT contain 'installed' => true or fails php lint check: reset it.
if [ -f /var/www/html/config/config.php ]; then
    if ! grep -q "'installed' => true" /var/www/html/config/config.php || ! php -l /var/www/html/config/config.php >/dev/null 2>&1; then
        echo "[STORIX] Detected incomplete or broken config.php; resetting config.php..."
        rm -f /var/www/html/config/config.php
    fi
fi

# Fast Boot Optimization (< 2.5s cold start):
# - If config.php exists (Nextcloud already installed on EFS): restore version.php so official entrypoint skips re-install.
# - If config.php does not exist: ensure version.php is absent so official entrypoint performs clean automated install.
if [ -f /var/www/html/config/config.php ]; then
    cp -p /usr/src/nextcloud/version.php /var/www/html/version.php 2>/dev/null || :
else
    rm -f /var/www/html/version.php
fi

exec /entrypoint.sh "$@"
