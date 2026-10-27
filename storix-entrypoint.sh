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
if [ ! -f /var/www/html/data/.ncdata ]; then
    echo "# Nextcloud data directory" > /var/www/html/data/.ncdata 2>/dev/null || :
fi
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
    mkdir -p /var/www/html/themes/storix/core/img/tenants
    cp -r /usr/src/nextcloud/themes/storix/. /var/www/html/themes/storix/ 2>/dev/null || :
    chown -R www-data:www-data /var/www/html/themes 2>/dev/null || :
    chmod -R 775 /var/www/html/themes 2>/dev/null || :
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

# Ensure version.php is ALWAYS present from /usr/src/nextcloud so occ never fails
if [ -f /usr/src/nextcloud/version.php ]; then
    cp -p /usr/src/nextcloud/version.php /var/www/html/version.php 2>/dev/null || :
    chown www-data:www-data /var/www/html/version.php 2>/dev/null || :
fi

# CRITICAL SECURITY RULE: Permanently block web-based manual installer ("Create an admin account")
# Nextcloud displays the installation wizard if CAN_INSTALL exists. Deleting it prevents the wizard from ever rendering.
rm -f /var/www/html/config/CAN_INSTALL /usr/src/nextcloud/config/CAN_INSTALL 2>/dev/null || :

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
            $user = getenv("POSTGRES_USER") ?: "nextcloud";
            $host = getenv("POSTGRES_HOST");
            $ssl = getenv("PGSSLMODE") ?: "prefer";
            $file = "/var/www/html/config/config.php";
            if (file_exists($file) && !empty($pass)) {
                $c = file_get_contents($file);
                // Align password in PostgreSQL for any dedicated oc_* database user
                if (preg_match("/\047dbuser\047\s*=>\s*\047([^\047]+)\047/", $c, $um)) {
                    $curr_user = $um[1];
                    if ($curr_user !== $user && !empty($host)) {
                        try {
                            $pdo = new PDO("pgsql:host=$host;dbname=postgres;sslmode=$ssl", $user, $pass, [PDO::ATTR_TIMEOUT => 5]);
                            $q = $pdo->quote($pass);
                            $pdo->exec("ALTER USER \"$curr_user\" WITH PASSWORD $q");
                            echo "[STORIX] Aligned PostgreSQL user $curr_user password.\n";
                        } catch (Exception $e) {}
                    }
                }
                $pattern = "/(\047dbpassword\047\s*=>\s*\047)[^\047]*(\047)/";
                if (preg_match($pattern, $c)) {
                    $escaped = addcslashes($pass, "\047\\");
                    $updated = preg_replace_callback($pattern, function($m) use ($escaped) {
                        return $m[1] . $escaped . $m[2];
                    }, $c);
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
# Reset config.php so headless installer performs clean automated install into the new database.
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

# Automated Headless Installation (Zero Web Setup Wizard):
# If config.php is missing or lacks 'installed' => true, perform non-interactive CLI installation before Apache starts.
if [ ! -f /var/www/html/config/config.php ] || ! grep -q "'installed' => true" /var/www/html/config/config.php; then
    echo "[STORIX] Nextcloud is not installed. Performing headless automated CLI installation..."
    rm -f /var/www/html/config/CAN_INSTALL 2>/dev/null || :

    if [ -n "${POSTGRES_HOST:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ] && [ -n "${NEXTCLOUD_ADMIN_PASSWORD:-}" ]; then
        ADMIN_USER="${NEXTCLOUD_ADMIN_USER:-admin}"
        DB_NAME="${POSTGRES_DB:-nextcloud}"
        DB_USER="${POSTGRES_USER:-nextcloud}"

        # Ensure target database exists in PostgreSQL
        php -r '
            $h = getenv("POSTGRES_HOST");
            $u = getenv("POSTGRES_USER") ?: "nextcloud";
            $p = getenv("POSTGRES_PASSWORD");
            $db = getenv("POSTGRES_DB") ?: "nextcloud";
            $ssl = getenv("PGSSLMODE") ?: "prefer";
            try {
                $pdo = new PDO("pgsql:host=$h;dbname=postgres;sslmode=$ssl", $u, $p, [PDO::ATTR_TIMEOUT => 10]);
                $stmt = $pdo->prepare("SELECT 1 FROM pg_database WHERE datname = ?");
                $stmt->execute([$db]);
                if (!$stmt->fetch()) {
                    $safe_db = preg_replace("/[^a-zA-Z0-9_]/", "", $db);
                    $pdo->exec("CREATE DATABASE \"$safe_db\"");
                    echo "[STORIX] Created database $safe_db\n";
                }
            } catch (Exception $e) {
                echo "[STORIX] DB Check Notice: " . $e->getMessage() . "\n";
            }
        ' 2>/dev/null || :

        # Ensure database schema is clean if we are performing a fresh installation
        php -r '
            $h = getenv("POSTGRES_HOST");
            $u = getenv("POSTGRES_USER") ?: "nextcloud";
            $p = getenv("POSTGRES_PASSWORD");
            $db = getenv("POSTGRES_DB") ?: "nextcloud";
            $ssl = getenv("PGSSLMODE") ?: "prefer";
            try {
                $pdo = new PDO("pgsql:host=$h;dbname=$db;sslmode=$ssl", $u, $p, [PDO::ATTR_TIMEOUT => 10]);
                $stmt = $pdo->query("SELECT 1 FROM information_schema.tables WHERE table_name = '\''oc_appconfig'\''");
                if ($stmt && $stmt->fetch()) {
                    $pdo->exec("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO \"$u\"; GRANT ALL ON SCHEMA public TO public;");
                    echo "[STORIX] Dropped existing tables for clean occ install.\n";
                }
            } catch (Exception $e) {}
        ' 2>/dev/null || :

        echo "[STORIX] Running occ maintenance:install..."
        runuser -u www-data -- php /var/www/html/occ maintenance:install \
            --database pgsql \
            --database-host "$POSTGRES_HOST" \
            --database-name "$DB_NAME" \
            --database-user "$DB_USER" \
            --database-pass "$POSTGRES_PASSWORD" \
            --admin-user "$ADMIN_USER" \
            --admin-pass "$NEXTCLOUD_ADMIN_PASSWORD" \
            --data-dir "/var/www/html/data" 2>&1 || {
                echo "[STORIX] Notice: occ maintenance:install returned non-zero code. Verifying status..."
            }

        # Configure trusted domains
        runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 0 --value="localhost" 2>/dev/null || :
        runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 1 --value="127.0.0.1" 2>/dev/null || :
        
        idx=2
        if [ -n "${NEXTCLOUD_TRUSTED_DOMAINS:-}" ]; then
            for dom in ${NEXTCLOUD_TRUSTED_DOMAINS}; do
                runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains $idx --value="$dom" 2>/dev/null || :
                idx=$((idx + 1))
            done
        fi
        runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains $idx --value="*.png261.dev" 2>/dev/null || :
        idx=$((idx + 1))
        runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains $idx --value="png261.dev" 2>/dev/null || :

        if [ -n "${OVERWRITEPROTOCOL:-}" ]; then
            runuser -u www-data -- php /var/www/html/occ config:system:set overwriteprotocol --value="$OVERWRITEPROTOCOL" 2>/dev/null || :
        fi
        if [ -n "${OVERWRITECLIURL:-}" ]; then
            runuser -u www-data -- php /var/www/html/occ config:system:set overwrite.cli.url --value="$OVERWRITECLIURL" 2>/dev/null || :
        fi
        if [ -n "${OVERWRITEHOST:-}" ]; then
            runuser -u www-data -- php /var/www/html/occ config:system:set overwritehost --value="$OVERWRITEHOST" 2>/dev/null || :
        fi

        # Permanently block web-based manual installer
        rm -f /var/www/html/config/CAN_INSTALL /usr/src/nextcloud/config/CAN_INSTALL 2>/dev/null || :
        echo "[STORIX] Automated headless installation completed successfully."
    fi
fi

# Ensure admin password is authenticated and up to date if supplied
if [ -n "${NEXTCLOUD_ADMIN_PASSWORD:-}" ] && [ -f /var/www/html/config/config.php ] && grep -q "'installed' => true" /var/www/html/config/config.php; then
    ADMIN_USER="${NEXTCLOUD_ADMIN_USER:-admin}"
    OC_PASS="$NEXTCLOUD_ADMIN_PASSWORD" runuser -u www-data -- php /var/www/html/occ user:resetpassword --password-from-env "$ADMIN_USER" 2>/dev/null || :
fi

# Ensure .htaccess rewrite rules are active for clean URLs (preventing 404 on /login or /apps/files/)
if [ -f /var/www/html/config/config.php ] && grep -q "'installed' => true" /var/www/html/config/config.php; then
    runuser -u www-data -- php /var/www/html/occ maintenance:update:htaccess 2>/dev/null || :
fi

# Trigger Storix AI & OpenSearch hooks directly with root privileges
if [ -x /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh ]; then
    /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh || :
fi
if [ -x /docker-entrypoint-hooks.d/before-starting/02-setup-opensearch.sh ]; then
    /docker-entrypoint-hooks.d/before-starting/02-setup-opensearch.sh || :
fi

# Ensure CAN_INSTALL is permanently gone before handing off to entrypoint
rm -f /var/www/html/config/CAN_INSTALL /usr/src/nextcloud/config/CAN_INSTALL 2>/dev/null || :

exec /entrypoint.sh "$@"
