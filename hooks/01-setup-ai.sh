#!/bin/sh
# ==============================================================================
# Nextcloud Official Docker Entrypoint Hook
# Auto-enables pre-baked AI applications and configures LiteLLM Bedrock Bridge
# Uses persistent flag in EFS to optimize boot time (sub-second cold start)
# ==============================================================================
set -e

echo "[ENTRYPOINT-HOOK] Nextcloud Docker Hook: Checking initialization and configuration..."

# ──────────────────────────────────────────────────────────────────────────
# 0. ENSURE DATA DIRECTORY & .NCDATA EXIST (Primary Object Storage / Ephemeral)
# ──────────────────────────────────────────────────────────────────────────
mkdir -p /var/www/html/data
if [ ! -f /var/www/html/data/.ncdata ]; then
    echo "# Nextcloud data directory" > /var/www/html/data/.ncdata
fi
chown -R www-data:www-data /var/www/html/data 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────────────
# 0. ENSURE MODULAR CONFIG FILES IN MOUNTED EFS /var/www/html/config
# ──────────────────────────────────────────────────────────────────────────
mkdir -p /var/www/html/config
if [ -d /usr/src/nextcloud/config ]; then
    for cfg in /usr/src/nextcloud/config/*.config.php; do
        if [ -f "$cfg" ]; then
            target="/var/www/html/config/$(basename "$cfg")"
            if [ ! -f "$target" ]; then
                echo "[ENTRYPOINT-HOOK] Seeding $(basename "$cfg") to EFS config directory..."
                cp "$cfg" "$target"
                chown www-data:www-data "$target" 2>/dev/null || true
            fi
        fi
    done
fi

# ──────────────────────────────────────────────────────────────────────────
# 0.1 AUTO-HEAL CONFIG.PHP IF DATABASE ALREADY INITIALIZED
# ──────────────────────────────────────────────────────────────────────────
if [ ! -f /var/www/html/config/config.php ] || ! grep -q "'installed' => true" /var/www/html/config/config.php 2>/dev/null; then
    # In Nextcloud, maintenance:install is strictly registered ONLY when NOT installed.
    # If maintenance:install is absent from occ, Nextcloud recognizes the database as already initialized.
    if ! su -s /bin/sh www-data -c "php /var/www/html/occ list" 2>/dev/null | grep -q "maintenance:install"; then
        echo "[ENTRYPOINT-HOOK] Detected existing database installation (maintenance:install is absent from occ)."
        echo "[ENTRYPOINT-HOOK] Generating /var/www/html/config/config.php to prevent installation retry loop..."
        mkdir -p /var/www/html/config
        INSTANCE_ID="oc$(head -c 16 /dev/urandom 2>/dev/null | md5sum | head -c 10 || echo "inst$(date +%s)")"
        SECRET="sec_$(head -c 32 /dev/urandom 2>/dev/null | sha256sum | head -c 30 || echo "sec$(date +%s)")"
        cat <<EOF > /var/www/html/config/config.php
<?php
\$CONFIG = array (
  'instanceid' => '${INSTANCE_ID}',
  'passwordsalt' => 'salt_${INSTANCE_ID}',
  'secret' => '${SECRET}',
  'trusted_domains' => array (
    0 => 'localhost',
    1 => '127.0.0.1',
    2 => '*',
  ),
  'datadirectory' => '/var/www/html/data',
  'dbtype' => 'pgsql',
  'version' => '30.0.17.2',
  'overwrite.cli.url' => 'http://localhost',
  'dbname' => '${POSTGRES_DB:-nextcloud}',
  'dbhost' => '${POSTGRES_HOST}',
  'dbport' => '',
  'dbtableprefix' => 'oc_',
  'dbuser' => '${POSTGRES_USER:-nextcloud}',
  'dbpassword' => '${POSTGRES_PASSWORD:-}',
  'installed' => true,
);
EOF
        chown -R www-data:www-data /var/www/html/config
        echo "[ENTRYPOINT-HOOK] config.php successfully generated and marked installed."
    fi
fi

# ──────────────────────────────────────────────────────────────────────────
# 1. OPTIMIZED INITIALIZATION VIA PERSISTENT EFS FLAG
# ──────────────────────────────────────────────────────────────────────────
INIT_FLAG="/var/www/html/config/.tenant_initialized"

if su -s /bin/sh www-data -c "php /var/www/html/occ status" 2>/dev/null | grep -q "installed: true"; then
    if [ ! -f "$INIT_FLAG" ] || [ "${FORCE_REINIT:-0}" = "1" ]; then
        echo "[ENTRYPOINT-HOOK] Initializing tenant configuration & activating pre-baked AI apps..."

        # Enable AI Apps
        su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force assistant" || true
        su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force integration_openai" || true

        # Configure Assistant guardrails (Zero Data Retention)
        su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant enabled --value=yes" || true
        su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant zero_data_retention --value=1" || true

        # Configure External AI Provider if explicitly configured via environment
        AI_ENDPOINT="${AI_API_URL:-${OPENAI_API_URL:-}}"
        if [ -n "${AI_ENDPOINT}" ]; then
            AI_KEY="${AI_API_KEY:-${OPENAI_API_KEY:-}}"
            echo "[ENTRYPOINT-HOOK] Binding AI Provider to ${AI_ENDPOINT}..."
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai api_url --value='${AI_ENDPOINT}'" || true
            if [ -n "${AI_KEY}" ]; then
                su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai api_key --value='${AI_KEY}'" || true
            fi
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai enable_text_processing --value=1" || true
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai enable_assistant --value=1" || true
        fi

        # Optional Redis Distributed Locking (if REDIS_HOST configured)
        if [ -n "${REDIS_HOST}" ]; then
            echo "[ENTRYPOINT-HOOK] Redis detected at ${REDIS_HOST} — configuring distributed locking..."
            su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set memcache.locking --value='\OC\Memcache\Redis'" || true
            su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set redis host --value='${REDIS_HOST}'" || true
            su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set redis port --value=${REDIS_PORT:-6379} --type=integer" || true
        fi

        # Missing database indices & migrations (one-time execution)
        echo "[ENTRYPOINT-HOOK] Adding missing database indices and initial repairs..."
        su -s /bin/sh www-data -c "php /var/www/html/occ db:add-missing-indices" || true
        su -s /bin/sh www-data -c "php /var/www/html/occ maintenance:repair --include-expensive" || true

        # Mark initialization as completed in persistent storage (EFS)
        touch "$INIT_FLAG"
        chown www-data:www-data "$INIT_FLAG" 2>/dev/null || true
        echo "[ENTRYPOINT-HOOK] ✅ First-time tenant setup completed and persisted to EFS."
    else
        echo "[ENTRYPOINT-HOOK] ⚡ Tenant already initialized in EFS. Fast-booting container (< 1s)."
    fi

    # Dynamic CLI URL update if specified at runtime
    if [ -n "${OVERWRITECLIURL}" ]; then
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set overwritecliurl --value='${OVERWRITECLIURL}'" || true
    fi
else
    echo "[ENTRYPOINT-HOOK] Nextcloud not fully installed yet; hook will execute on next boot or post-installation."
fi
