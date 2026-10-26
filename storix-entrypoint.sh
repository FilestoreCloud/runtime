#!/bin/sh
set -e

# If REDIS_HOST is empty or unset, ensure official entrypoint does NOT configure Redis as session handler
if [ -z "${REDIS_HOST:-}" ]; then
    unset REDIS_HOST
    unset REDIS_PORT
    rm -f /usr/local/etc/php/conf.d/redis-session.ini 2>/dev/null || :
fi

# Ensure all application and configuration directories exist with correct permissions
mkdir -p /var/www/html/config /var/www/html/data /var/www/html/apps /var/www/html/custom_apps /var/www/html/themes /var/www/html/core/img
chown -R www-data:www-data /var/www/html/config /var/www/html/data /var/www/html/apps /var/www/html/custom_apps /var/www/html/themes /var/www/html/core/img 2>/dev/null || :
chmod -R 775 /var/www/html/config /var/www/html/apps /var/www/html/custom_apps 2>/dev/null || :

# Sync modular config templates (nextcloud.config.php with theme=>storix) into mounted EFS config
if [ -d /usr/src/nextcloud/config ]; then
    for cfg in /usr/src/nextcloud/config/*.config.php; do
        if [ -f "$cfg" ]; then
            target="/var/www/html/config/$(basename "$cfg")"
            if [ ! -f "$target" ] || ! cmp -s "$cfg" "$target" 2>/dev/null; then
                echo "[STORIX] Syncing modular config $(basename "$cfg") to EFS /var/www/html/config..."
                cp -p "$cfg" "$target" 2>/dev/null || cp "$cfg" "$target"
                chown www-data:www-data "$target" 2>/dev/null || :
            fi
        fi
    done
fi

# Ensure Storix custom theme is always populated and up-to-date in /var/www/html/themes
if [ -d /usr/src/nextcloud/themes/storix ]; then
    mkdir -p /var/www/html/themes/storix
    cp -r /usr/src/nextcloud/themes/storix/. /var/www/html/themes/storix/ 2>/dev/null || :
    chown -R www-data:www-data /var/www/html/themes/storix 2>/dev/null || :
fi

# Ensure Storix core image assets are present in /var/www/html/core/img
if [ -d /usr/src/nextcloud/themes/storix/core/img ]; then
    mkdir -p /var/www/html/core/img
    cp -r /usr/src/nextcloud/themes/storix/core/img/logo-white.png /var/www/html/core/img/logo-header.png 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/logo-wide.svg /var/www/html/core/img/logo-header.svg 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/logo-white.png /var/www/html/core/img/logo.png 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/logo-wide.svg /var/www/html/core/img/logo.svg 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/favicon.ico /var/www/html/core/img/favicon.ico 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/favicon.png /var/www/html/core/img/favicon.png 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/favicon-touch.png /var/www/html/core/img/favicon-touch.png 2>/dev/null || :
    cp -r /usr/src/nextcloud/themes/storix/core/img/background.png /var/www/html/core/img/background.png 2>/dev/null || :
    chown -R www-data:www-data /var/www/html/core/img 2>/dev/null || :
fi

# In ECS Fargate, /var/www/html is ephemeral container filesystem while /var/www/html/config is mounted to persistent EFS.
# Sanitize, validate and synchronize config.php on EFS if present:
if [ -f /var/www/html/config/config.php ]; then
    sed -i "/PGSQL_ATTR_SSL_MODE/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/pgsql_ssl/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/dbdriveroptions/d" /var/www/html/config/config.php 2>/dev/null || :

    # Synchronize POSTGRES_PASSWORD into config.php if present in environment
    if [ -n "${POSTGRES_PASSWORD:-}" ]; then
        php -r '
            $pass = getenv("POSTGRES_PASSWORD");
            $file = "/var/www/html/config/config.php";
            if (file_exists($file) && !empty($pass)) {
                $c = file_get_contents($file);
                $pattern = "/(\047dbpassword\047\s*=>\s*\047)[^\047]*(\047)/";
                if (preg_match($pattern, $c)) {
                    $escaped = addcslashes($pass, "\047\\");
                    $updated = preg_replace($pattern, "${1}{$escaped}${2}", $c);
                    if ($updated && $updated !== $c) {
                        file_put_contents($file, $updated);
                        echo "[STORIX] Synchronized dbpassword in config.php from POSTGRES_PASSWORD.\n";
                    }
                }
            }
        ' 2>/dev/null || :
    fi
fi

# If config.php exists but does NOT contain 'installed' => true or fails php lint check: reset it.
if [ -f /var/www/html/config/config.php ]; then
    if ! grep -q "'installed' => true" /var/www/html/config/config.php || ! php -l /var/www/html/config/config.php >/dev/null 2>&1; then
        echo "[STORIX] Detected incomplete or broken config.php; resetting config.php..."
        rm -f /var/www/html/config/config.php
    fi
fi

# Self-healing: If config.php exists on persistent storage but PostgreSQL was recreated (tables missing):
# Reset config.php so official entrypoint performs clean automated install into the new database.
if [ -f /var/www/html/config/config.php ] && [ -n "${POSTGRES_HOST:-}" ]; then
    DB_OK=$(php -r '
        $host = getenv("POSTGRES_HOST");
        $db = getenv("POSTGRES_DB") ?: "nextcloud";
        $user = getenv("POSTGRES_USER") ?: "nextcloud";
        $pass = getenv("POSTGRES_PASSWORD") ?: "";
        $sslmode = getenv("PGSSLMODE") ?: "prefer";
        try {
            $pdo = new PDO("pgsql:host=$host;dbname=$db;sslmode=$sslmode", $user, $pass, [PDO::ATTR_TIMEOUT => 5]);
            $stmt = $pdo->query("SELECT 1 FROM information_schema.tables WHERE table_name = '\''oc_appconfig'\''");
            if ($stmt && $stmt->fetch()) {
                echo "1";
            } else {
                echo "0";
            }
        } catch (Exception $e) {
            echo "1";
        }
    ' 2>/dev/null || echo "1")

    if [ "$DB_OK" = "0" ]; then
        echo "[STORIX] PostgreSQL table oc_appconfig missing despite existing config.php (database was recreated). Resetting config.php to allow clean automated install..."
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
