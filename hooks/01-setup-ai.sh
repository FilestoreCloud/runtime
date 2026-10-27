#!/bin/sh
# ==============================================================================
# Nextcloud Official Docker Entrypoint Hook
# Auto-enables pre-baked AI applications and configures LiteLLM Bedrock Bridge
# Uses persistent flag in EFS to optimize boot time (sub-second cold start)
# ==============================================================================
set -e

INIT_FLAG="/var/www/html/config/.tenant_initialized"

# Error trap handler for deterministic failure logging and gating
CURRENT_STEP="Startup pre-flight"
cleanup_on_exit() {
    exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        echo "[ENTRYPOINT-HOOK] ❌ ERROR: Initialization step '${CURRENT_STEP}' failed with exit code ${exit_code}!" >&2
        echo "[ENTRYPOINT-HOOK] ❌ Halting execution. Tenant initialization aborted; .tenant_initialized was not created." >&2
        rm -f "${INIT_FLAG}" 2>/dev/null
    fi
}
trap cleanup_on_exit EXIT

# If REDIS_HOST is empty or unset, ensure Redis session handler and locking are omitted
if [ -z "${REDIS_HOST:-}" ]; then
    unset REDIS_HOST
    unset REDIS_PORT
    rm -f /usr/local/etc/php/conf.d/redis-session.ini 2>/dev/null || :
fi

echo "[ENTRYPOINT-HOOK] Nextcloud Docker Hook: Checking initialization and configuration..."

# ──────────────────────────────────────────────────────────────────────────
# 0. ENSURE DATA DIRECTORY & .NCDATA EXIST (Primary Object Storage / Ephemeral)
# ──────────────────────────────────────────────────────────────────────────
CURRENT_STEP="Ensuring data and app directories"
mkdir -p /var/www/html/data /var/www/html/apps /var/www/html/custom_apps 2>/dev/null || :
if [ ! -f /var/www/html/data/.ncdata ]; then
    echo "# Nextcloud data directory" > /var/www/html/data/.ncdata 2>/dev/null || :
fi
chown -R www-data:www-data /var/www/html/data /var/www/html/apps /var/www/html/custom_apps 2>/dev/null || :

# ──────────────────────────────────────────────────────────────────────────
# 0. ENSURE MODULAR CONFIG FILES IN MOUNTED EFS /var/www/html/config
# ──────────────────────────────────────────────────────────────────────────
CURRENT_STEP="Seeding modular configs"
mkdir -p /var/www/html/config

# Remove legacy bare wildcard '*' from existing config.php in EFS if present
if [ -f /var/www/html/config/config.php ]; then
    sed -i.bak "/['\"]\*['\"]/d" /var/www/html/config/config.php 2>/dev/null && rm -f /var/www/html/config/config.php.bak 2>/dev/null || sed -i "/['\"]\*['\"]/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/PGSQL_ATTR_SSL_MODE/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/pgsql_ssl/d" /var/www/html/config/config.php 2>/dev/null || :
    sed -i "/dbdriveroptions/d" /var/www/html/config/config.php 2>/dev/null || :
fi

if [ -d /usr/src/nextcloud/config ]; then
    for cfg in /usr/src/nextcloud/config/*.config.php; do
        if [ -f "$cfg" ]; then
            target="/var/www/html/config/$(basename "$cfg")"
            if [ ! -f "$target" ] || ! cmp -s "$cfg" "$target"; then
                echo "[ENTRYPOINT-HOOK] Updating modular config $(basename "$cfg") in EFS..."
                cp "$cfg" "$target"
                chown www-data:www-data "$target" 2>/dev/null || :
            fi
        fi
    done
fi

# ──────────────────────────────────────────────────────────────────────────
# 0.05 SEED STORIX THEME IN MOUNTED EFS /var/www/html/themes
# ──────────────────────────────────────────────────────────────────────────
if [ -d /usr/src/nextcloud/themes/storix ] && [ ! -d /var/www/html/themes/storix ]; then
    echo "[ENTRYPOINT-HOOK] Seeding Storix theme into EFS /var/www/html/themes..."
    mkdir -p /var/www/html/themes
    cp -r /usr/src/nextcloud/themes/storix /var/www/html/themes/
    chown -R www-data:www-data /var/www/html/themes/storix 2>/dev/null || :
fi

# ──────────────────────────────────────────────────────────────────────────
# 0.1 AUTO-PROVISION CONFIG.PHP IF DATABASE ALREADY INITIALIZED
# ──────────────────────────────────────────────────────────────────────────
CURRENT_STEP="Auto-provisioning config.php check"
if [ ! -f /var/www/html/config/config.php ] && [ -n "${POSTGRES_HOST:-}" ]; then
    DB_INITIALIZED=$(php -r '
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
            echo "0";
        }
    ' 2>/dev/null || echo "0")

    if [ "$DB_INITIALIZED" = "1" ]; then
        echo "[ENTRYPOINT-HOOK] Database already initialized. Restoring /var/www/html/config/config.php with PostgreSQL bindings..."
        mkdir -p /var/www/html/config
        INSTANCE_ID="oc$(head -c 16 /dev/urandom 2>/dev/null | md5sum | head -c 10 || echo "inst$(date +%s)")"
        SECRET="sec_$(head -c 32 /dev/urandom 2>/dev/null | sha256sum | head -c 30 || echo "sec$(date +%s)")"
        cat <<EOF > /var/www/html/config/config.php
<?php
\$rawDomains = '${NEXTCLOUD_TRUSTED_DOMAINS:-}';
\$trusted = array('localhost', '127.0.0.1');
if (!empty(\$rawDomains)) {
    foreach (preg_split('/[\s,]+/', \$rawDomains) as \$d) {
        \$d = trim(\$d);
        if (\$d !== '' && \$d !== '*' && !in_array(\$d, \$trusted, true)) {
            \$trusted[] = \$d;
        }
    }
}
\$CONFIG = array (
  'instanceid' => '${INSTANCE_ID}',
  'passwordsalt' => 'salt_${INSTANCE_ID}',
  'secret' => '${SECRET}',
  'trusted_domains' => \$trusted,
  'datadirectory' => '/var/www/html/data',
  'dbtype' => 'pgsql',
  'version' => '30.0.17.2',
  'overwrite.cli.url' => (getenv('OVERWRITECLIURL') ?: 'http://localhost'),
  'overwriteprotocol' => (getenv('OVERWRITEPROTOCOL') ?: 'https'),
  'dbname' => '${POSTGRES_DB:-nextcloud}',
  'dbhost' => '${POSTGRES_HOST}',
  'dbport' => '5432',
  'dbtableprefix' => 'oc_',
  'dbuser' => '${POSTGRES_USER:-nextcloud}',
  'dbpassword' => '${POSTGRES_PASSWORD:-}',
  'appstoreenabled' => false,
  'apps_paths' => array (
    0 => array (
      'path' => '/var/www/html/apps',
      'url' => '/apps',
      'writable' => false,
    ),
    1 => array (
      'path' => '/var/www/html/custom_apps',
      'url' => '/custom_apps',
      'writable' => true,
    ),
  ),
  'installed' => true,
);
EOF
        chown -R www-data:www-data /var/www/html/config
        echo "[ENTRYPOINT-HOOK] config.php successfully restored with installed=true."
    else
        echo "[ENTRYPOINT-HOOK] Database not yet initialized. Skipping config.php generation to allow official Nextcloud maintenance:install to run."
    fi
fi

# ──────────────────────────────────────────────────────────────────────────
# 1. OPTIMIZED INITIALIZATION VIA PERSISTENT EFS FLAG
# ──────────────────────────────────────────────────────────────────────────
CURRENT_STEP="Checking Nextcloud installation status"
if su -s /bin/sh www-data -c "php /var/www/html/occ status" 2>/dev/null | grep -q "installed: true"; then
    if [ ! -f "$INIT_FLAG" ] || [ "${FORCE_REINIT:-0}" = "1" ]; then
        echo "[ENTRYPOINT-HOOK] Initializing tenant configuration & activating pre-baked AI apps..."

        # Enable AI Apps
        CURRENT_STEP="Enabling assistant app"
        su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force assistant"

        CURRENT_STEP="Enabling integration_openai app"
        su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force integration_openai"

        # Configure Assistant guardrails (Zero Data Retention)
        CURRENT_STEP="Configuring assistant guardrails"
        su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant enabled --value=yes"
        su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant zero_data_retention --value=1"

        # Configure External AI Provider if explicitly configured via environment
        AI_ENDPOINT="${AI_API_URL:-${OPENAI_API_URL:-}}"
        if [ -n "${AI_ENDPOINT}" ]; then
            AI_KEY="${AI_API_KEY:-${OPENAI_API_KEY:-}}"
            echo "[ENTRYPOINT-HOOK] Binding AI Provider to ${AI_ENDPOINT}..."
            CURRENT_STEP="Binding AI provider endpoint"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai url --value='${AI_ENDPOINT}'"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai api_url --value='${AI_ENDPOINT}'"
            if [ -n "${AI_KEY}" ]; then
                CURRENT_STEP="Setting AI provider key"
                su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai api_key --value='${AI_KEY}'"
            fi
            AI_MODEL="${AI_MODEL_NAME:-${OPENAI_MODEL:-}}"
            if [ -n "${AI_MODEL}" ]; then
                su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai default_completion_model_id --value='${AI_MODEL}'" 2>/dev/null || :
                su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai model --value='${AI_MODEL}'" 2>/dev/null || :
                su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai chat_model --value='${AI_MODEL}'" 2>/dev/null || :
                su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai text_generation_model --value='${AI_MODEL}'" 2>/dev/null || :
            fi
            CURRENT_STEP="Enabling AI text processing and assistant features"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai enable_text_processing --value=1"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai enable_assistant --value=1"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai llm_provider_enabled --value=1" 2>/dev/null || :
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai chat_endpoint_enabled --value=1" 2>/dev/null || :
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set integration_openai translation_provider_enabled --value=1" 2>/dev/null || :
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant assistant_enabled --value=1" 2>/dev/null || :
            su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set assistant free_prompt_picker_enabled --value=1" 2>/dev/null || :
        fi

        # Optional Redis Distributed Locking (if REDIS_HOST configured)
        if [ -n "${REDIS_HOST}" ]; then
            echo "[ENTRYPOINT-HOOK] Redis detected at ${REDIS_HOST} — configuring distributed locking..."
            CURRENT_STEP="Configuring Redis distributed locking"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set memcache.locking --value='\OC\Memcache\Redis'"
            CURRENT_STEP="Configuring Redis host"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set redis host --value='${REDIS_HOST}'"
            CURRENT_STEP="Configuring Redis port"
            su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set redis port --value=${REDIS_PORT:-6379} --type=integer"
        fi

        # Missing database indices & migrations (one-time execution)
        echo "[ENTRYPOINT-HOOK] Adding missing database indices and initial repairs..."
        CURRENT_STEP="Adding missing database indices"
        su -s /bin/sh www-data -c "php /var/www/html/occ db:add-missing-indices"

        CURRENT_STEP="Running maintenance repair"
        su -s /bin/sh www-data -c "php /var/www/html/occ maintenance:repair --include-expensive"

        # Configure Storix Theming & Corporate Branding
        CURRENT_STEP="Configuring Storix branding and theme"
        echo "[ENTRYPOINT-HOOK] Applying default Storix branding and theme..."
        
        # 1. Ensure theming app is enabled
        su -s /bin/sh www-data -c "php /var/www/html/occ app:enable --force theming" 2>/dev/null || :
        
        # 2. Configure theming text and color metadata
        su -s /bin/sh www-data -c "php /var/www/html/occ theming:config name 'Storix'" 2>/dev/null || su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set theming name --value='Storix'"
        su -s /bin/sh www-data -c "php /var/www/html/occ theming:config slogan 'Enterprise Cloud Storage Platform'" 2>/dev/null || su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set theming slogan --value='Enterprise Cloud Storage Platform'"
        su -s /bin/sh www-data -c "php /var/www/html/occ theming:config url 'https://storix.io'" 2>/dev/null || su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set theming url --value='https://storix.io'"
        su -s /bin/sh www-data -c "php /var/www/html/occ theming:config color '#1652f0'" 2>/dev/null || su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set theming color --value='#1652f0'"
        su -s /bin/sh www-data -c "php /var/www/html/occ theming:config primary_color '#1652f0'" 2>/dev/null || :
        su -s /bin/sh www-data -c "php /var/www/html/occ theming:config background_color '#071736'" 2>/dev/null || :

        # 3. Apply Storix Logos, Header Logo, Favicon, and Background via occ theming:config
        THEME_IMG_DIR="/var/www/html/themes/storix/core/img"
        if [ -d "$THEME_IMG_DIR" ]; then
            if [ -f "$THEME_IMG_DIR/logo-white.png" ]; then
                su -s /bin/sh www-data -c "php /var/www/html/occ theming:config logo $THEME_IMG_DIR/logo-white.png" 2>/dev/null || :
                su -s /bin/sh www-data -c "php /var/www/html/occ theming:config logoheader $THEME_IMG_DIR/logo-white.png" 2>/dev/null || :
            elif [ -f "$THEME_IMG_DIR/logo.png" ]; then
                su -s /bin/sh www-data -c "php /var/www/html/occ theming:config logo $THEME_IMG_DIR/logo.png" 2>/dev/null || :
            fi

            if [ -f "$THEME_IMG_DIR/favicon.ico" ]; then
                su -s /bin/sh www-data -c "php /var/www/html/occ theming:config favicon $THEME_IMG_DIR/favicon.ico" 2>/dev/null || :
            fi

            if [ -f "$THEME_IMG_DIR/background.png" ]; then
                su -s /bin/sh www-data -c "php /var/www/html/occ theming:config background $THEME_IMG_DIR/background.png" 2>/dev/null || :
            fi
        fi

        # 4. Set system theme to storix in config.php
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set theme --value='storix'" 2>/dev/null || :

        # 5. Invalidate theme cachebuster so clients immediately receive new branding
        CACHEBUSTER=$(date +%s)
        su -s /bin/sh www-data -c "php /var/www/html/occ config:app:set theming cachebuster --value='${CACHEBUSTER}'" 2>/dev/null || :

        # Configure background jobs mode to cron (EventBridge dedicated runner)
        echo "[ENTRYPOINT-HOOK] Setting background jobs mode to cron runner..."
        su -s /bin/sh www-data -c "php /var/www/html/occ background:cron" 2>/dev/null || :

        # Mark initialization as completed in persistent storage (EFS)
        CURRENT_STEP="Marking tenant initialization complete"
        touch "$INIT_FLAG"
        chown www-data:www-data "$INIT_FLAG" 2>/dev/null || :
        echo "[ENTRYPOINT-HOOK] ✅ First-time tenant setup completed and persisted to EFS."
    else
        echo "[ENTRYPOINT-HOOK] ⚡ Tenant already initialized in EFS. Fast-booting container (< 1s)."
    fi

    # Dynamic CLI URL update if specified at runtime
    if [ -n "${OVERWRITECLIURL}" ]; then
        CURRENT_STEP="Setting overwritecliurl"
        su -s /bin/sh www-data -c "php /var/www/html/occ config:system:set overwritecliurl --value='${OVERWRITECLIURL}'"
    fi
else
    echo "[ENTRYPOINT-HOOK] Nextcloud not fully installed yet; hook will execute on next boot or post-installation."
fi

CURRENT_STEP="Completed successfully"
