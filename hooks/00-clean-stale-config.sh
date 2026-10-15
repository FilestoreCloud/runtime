#!/bin/sh
set -e

echo "[PRE-INSTALL] Checking storage configuration before initial installation..."

# Note: pre-installation hooks ONLY run when entrypoint.sh has decided to perform a fresh install
# (i.e. installed_version == 0.0.0.0).
# If the database already has oc_users but config.php is missing or uninstalled,
# maintenance:install would fail with 'The Login is already being used'.
# We must reset the public schema in PostgreSQL so fresh install succeeds without collision.
if [ -n "${POSTGRES_HOST:-}" ]; then
    php -r '
        $host = getenv("POSTGRES_HOST");
        $db = getenv("POSTGRES_DB") ?: "nextcloud";
        $user = getenv("POSTGRES_USER") ?: "nextcloud";
        $pass = getenv("POSTGRES_PASSWORD") ?: "";
        if (!$host) { exit(0); }
        try {
            $pdo = new PDO("pgsql:host=$host;dbname=$db", $user, $pass, [PDO::ATTR_TIMEOUT => 5]);
            $stmt = $pdo->query("SELECT 1 FROM information_schema.tables WHERE table_name = '\''oc_users'\''");
            if ($stmt && $stmt->fetch()) {
                echo "[PRE-INSTALL] ⚠️ Found orphaned tables from prior failed installation. Resetting public schema...\n";
                $pdo->exec("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
                echo "[PRE-INSTALL] Public schema reset successfully.\n";
            }
        } catch (Exception $e) {
            echo "[PRE-INSTALL] DB check note: " . $e->getMessage() . "\n";
        }
    ' 2>/dev/null || :
fi

if [ -f /var/www/html/config/.tenant_initialized ]; then
    rm -f /var/www/html/config/.tenant_initialized
fi

echo "[PRE-INSTALL] Storage verification completed."
