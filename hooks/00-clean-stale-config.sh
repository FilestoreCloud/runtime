#!/bin/sh
set -e

echo "[PRE-INSTALL] Checking for stale configuration before fresh installation..."
if [ -f /var/www/html/config/config.php ]; then
    echo "[PRE-INSTALL] Found stale config.php on persistent storage. Purging to ensure clean maintenance:install..."
    rm -f /var/www/html/config/config.php
fi

if [ -f /var/www/html/config/.tenant_initialized ]; then
    rm -f /var/www/html/config/.tenant_initialized
fi

echo "[PRE-INSTALL] Storage sanitized for initial installation."
