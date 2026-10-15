#!/bin/sh
set -e

echo "[PRE-INSTALL] Checking storage configuration before initial installation..."

# Only purge config.php if the database is actually uninitialized.
# If database is already initialized (e.g. oc_users exists), we must preserve config.php!
if [ -f /var/www/html/config/config.php ] && [ -n "${POSTGRES_HOST:-}" ]; then
    DB_INITIALIZED=$(php -r '
        $host = getenv("POSTGRES_HOST");
        $db = getenv("POSTGRES_DB") ?: "nextcloud";
        $user = getenv("POSTGRES_USER") ?: "nextcloud";
        $pass = getenv("POSTGRES_PASSWORD") ?: "";
        if (!$host) { echo "0"; exit; }
        try {
            $pdo = new PDO("pgsql:host=$host;dbname=$db", $user, $pass, [PDO::ATTR_TIMEOUT => 5]);
            $stmt = $pdo->query("SELECT 1 FROM information_schema.tables WHERE table_name = '\''oc_users'\''");
            if ($stmt && $stmt->fetch()) {
                echo "1";
            } else {
                echo "0";
            }
        } catch (Exception $e) {
            echo "0";
        }
    ' 2>/dev/null || echo "0")

    if [ "$DB_INITIALIZED" = "0" ]; then
        echo "[PRE-INSTALL] ⚠️ Database is empty but stale config.php exists on persistent storage. Purging to allow fresh installation..."
        rm -f /var/www/html/config/config.php
        rm -f /var/www/html/config/.tenant_initialized
    else
        echo "[PRE-INSTALL] Database is already initialized. Preserving existing configuration."
    fi
fi

echo "[PRE-INSTALL] Storage verification completed."
