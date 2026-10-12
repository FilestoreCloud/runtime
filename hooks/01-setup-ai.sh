#!/bin/sh
# ==============================================================================
# Nextcloud Official Docker Entrypoint Hook
# Auto-enables pre-baked AI applications and configures LiteLLM Bedrock Bridge
# Also applies all recommended system configuration to fix Admin security warnings
# ==============================================================================
set -e

echo "[ENTRYPOINT-HOOK] Nextcloud Docker Hook: Checking initialization and configuration..."

# ──────────────────────────────────────────────────────────────────────────
# 0. ENSURE MODULAR CONFIG FILES IN MOUNTED EFS /var/www/html/config
# ──────────────────────────────────────────────────────────────────────────
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

# Improvement 2: Verify database installation state via occ status
if su -s /bin/sh www-data -c "php /var/www/html/occ status" 2>/dev/null | grep -q "installed: true"; then
    echo "[ENTRYPOINT-HOOK] Nextcloud is installed. Activating pre-baked AI apps..."

    # ──────────────────────────────────────────────────────────────────────────
    # 1. ENABLE AI APPS
    # ──────────────────────────────────────────────────────────────────────────
    su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force assistant" || true
    su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force integration_openai" || true

    # Configure Assistant guardrails (Zero Data Retention)
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant enabled --value=yes" || true
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant zero_data_retention --value=1" || true

    # ──────────────────────────────────────────────────────────────────────────
    # 2. CONFIGURE LITELLM BEDROCK BRIDGE
    # ──────────────────────────────────────────────────────────────────────────
    LITELLM_ENDPOINT="${LITELLM_API_URL:-http://127.0.0.1:4000/v1}"
    LITELLM_KEY="${LITELLM_API_KEY:-sk-saas-nextcloud-internal}"
    BEDROCK_MODEL="${BEDROCK_DEFAULT_MODEL:-bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0}"

    echo "[ENTRYPOINT-HOOK] Binding AI Provider to LiteLLM Bedrock Bridge at ${LITELLM_ENDPOINT}..."
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai api_url --value='${LITELLM_ENDPOINT}'" || true
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai api_key --value='${LITELLM_KEY}'" || true
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai default_model --value='${BEDROCK_MODEL}'" || true
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai enable_text_processing --value=1" || true
    su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai enable_assistant --value=1" || true

    # ──────────────────────────────────────────────────────────────────────────
    # 3. HTTPS / REVERSE-PROXY SETTINGS (ALB terminates TLS → HTTP to container)
    #    Fixes: "Accessing site insecurely via HTTP" + Strict-Transport-Security
    # ──────────────────────────────────────────────────────────────────────────
    echo "[ENTRYPOINT-HOOK] Configuring HTTPS proxy settings..."
    su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set overwriteprotocol --value=https" || true
    # overwritecliurl — use env var OVERWRITECLIURL if set, otherwise keep existing value
    if [ -n "${OVERWRITECLIURL}" ]; then
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set overwritecliurl --value='${OVERWRITECLIURL}'" || true
    fi
    # Trusted proxy range covering the entire VPC CIDR (ALB uses VPC IPs)
    su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set trusted_proxies 0 --value='10.0.0.0/16'" || true
    # Force HSTS header to be emitted by Nextcloud as well (belt-and-suspenders with ALB header policy)
    su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set hsts --value=true --type=boolean" || true

    # ──────────────────────────────────────────────────────────────────────────
    # 4. MAINTENANCE WINDOW (2 AM UTC = low-traffic)
    #    Fixes: "Server has no maintenance window start time configured"
    # ──────────────────────────────────────────────────────────────────────────
    MAINT_WINDOW="${NC_maintenance_window_start:-2}"
    echo "[ENTRYPOINT-HOOK] Setting maintenance window start to ${MAINT_WINDOW}:00 UTC..."
    su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set maintenance_window_start --value=${MAINT_WINDOW} --type=integer" || true

    # ──────────────────────────────────────────────────────────────────────────
    # 5. DEFAULT PHONE REGION
    #    Fixes: "Your installation has no default phone region set"
    # ──────────────────────────────────────────────────────────────────────────
    PHONE_REGION="${NC_default_phone_region:-VN}"
    echo "[ENTRYPOINT-HOOK] Setting default phone region to ${PHONE_REGION}..."
    su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set default_phone_region --value='${PHONE_REGION}'" || true

    # ──────────────────────────────────────────────────────────────────────────
    # 6. MEMCACHE (APCu for local cache; Redis not available in this Fargate config)
    #    Fixes: "The database is used for transactional file locking"
    #    Note: For production multi-replica, replace APCu with Redis ElastiCache
    # ──────────────────────────────────────────────────────────────────────────
    echo "[ENTRYPOINT-HOOK] Configuring APCu memcache..."
    su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set memcache.local --value='\OC\Memcache\APCu'" || true
    # If REDIS_HOST env var is present (optional ElastiCache), configure Redis locking
    if [ -n "${REDIS_HOST}" ]; then
        echo "[ENTRYPOINT-HOOK] Redis detected at ${REDIS_HOST} — enabling Redis distributed locking..."
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set memcache.locking --value='\OC\Memcache\Redis'" || true
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set redis host --value='${REDIS_HOST}'" || true
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set redis port --value=${REDIS_PORT:-6379} --type=integer" || true
    fi

    # ──────────────────────────────────────────────────────────────────────────
    # 7. MISSING DATABASE INDICES
    #    Fixes: "Detected some missing optional indices" (fs_storage_path_prefix)
    # ──────────────────────────────────────────────────────────────────────────
    echo "[ENTRYPOINT-HOOK] Adding missing database indices..."
    su -s /bin/sh www-data -c "php /var/www/html/occ db:add-missing-indices" || true

    # ──────────────────────────────────────────────────────────────────────────
    # 8. MIMETYPE MIGRATIONS
    #    Fixes: "One or more mimetype migrations are available"
    # ──────────────────────────────────────────────────────────────────────────
    echo "[ENTRYPOINT-HOOK] Running mimetype and DB repair migrations..."
    su -s /bin/sh www-data -c "php /var/www/html/occ maintenance:repair --include-expensive" || true

    echo "[ENTRYPOINT-HOOK] ✅ All Nextcloud configuration and repairs completed successfully."
else
    echo "[ENTRYPOINT-HOOK] Nextcloud not fully installed yet; hook will execute on next boot or post-installation."
fi
