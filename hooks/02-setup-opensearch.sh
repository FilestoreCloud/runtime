#!/bin/sh
# ==============================================================================
# Storix Hook: Auto-configure Nextcloud FullTextSearch & OpenSearch Backend
# ==============================================================================
set -e

OPENSEARCH_FLAG="/var/www/html/config/.opensearch_configured"

if [ -f "${OPENSEARCH_FLAG}" ]; then
    echo "[OPENSEARCH-HOOK] ⚡ FullTextSearch already initialized for this tenant. Skipping."
    exit 0
fi

# Only configure if OPENSEARCH_HOST or ELASTICSEARCH_HOST is defined
SEARCH_HOST="${OPENSEARCH_HOST:-${ELASTICSEARCH_HOST:-}}"
if [ -z "${SEARCH_HOST}" ]; then
    echo "[OPENSEARCH-HOOK] ℹ️ OPENSEARCH_HOST not provided. Skipping OpenSearch configuration."
    exit 0
fi

TENANT_ID="${TENANT_ID:-default}"
TIKA_HOST="${TIKA_HOST:-127.0.0.1}"
TIKA_PORT="${TIKA_PORT:-9998}"
OPENSEARCH_PORT="${OPENSEARCH_PORT:-443}"
OPENSEARCH_PROTO="${OPENSEARCH_PROTO:-https}"

echo "[OPENSEARCH-HOOK] 🔍 Configuring Nextcloud FullTextSearch for tenant '${TENANT_ID}'..."

# Verify Nextcloud is installed before invoking occ
if [ -f /var/www/html/config/config.php ] && grep -q "'installed' => true" /var/www/html/config/config.php; then
    run_occ() {
        if [ "$(id -u)" = "0" ]; then
            runuser -u www-data -- php /var/www/html/occ "$@" 2>/dev/null || :
        else
            php /var/www/html/occ "$@" 2>/dev/null || :
        fi
    }

    echo "[OPENSEARCH-HOOK] 📦 Enabling FullTextSearch suite..."
    run_occ app:enable fulltextsearch || :
    run_occ app:enable files_fulltextsearch || :
    run_occ app:enable fulltextsearch_elasticsearch || :

    SANITIZED_TENANT=$(echo "${TENANT_ID}" | tr -cd 'a-zA-Z0-9_-')
    INDEX_NAME="tenant_${SANITIZED_TENANT}"

    echo "[OPENSEARCH-HOOK] ⚙️ Setting OpenSearch platform and index '${INDEX_NAME}'..."
    run_occ fulltextsearch:configure "{\"search_platform\":\"fulltextsearch_elasticsearch\"}" || :
    run_occ fulltextsearch_elasticsearch:configure "{\"elastic_host\":\"${OPENSEARCH_PROTO}://${SEARCH_HOST}:${OPENSEARCH_PORT}\",\"elastic_index\":\"${INDEX_NAME}\"}" || :
    run_occ config:app:set fulltextsearch search_platform --value="OCA\\FullTextSearch_Elasticsearch\\Platform\\ElasticSearchPlatform" || :
    run_occ config:app:set fulltextsearch app_navigation --value="1" || :
    run_occ config:app:set fulltextsearch enabled --value="yes" || :
    run_occ config:app:set fulltextsearch_elasticsearch enabled --value="yes" || :
    run_occ config:app:set fulltextsearch_elasticsearch elastic_host --value="${OPENSEARCH_PROTO}://${SEARCH_HOST}:${OPENSEARCH_PORT}" || :
    run_occ config:app:set fulltextsearch_elasticsearch elastic_index --value="${INDEX_NAME}" || :
    run_occ config:app:set fulltextsearch_elasticsearch analyzer_tokenizer --value="standard" || :

    echo "[OPENSEARCH-HOOK] 📄 Setting files fulltextsearch options..."
    run_occ config:app:set files_fulltextsearch enabled --value="yes" || :
    run_occ files_fulltextsearch:configure "{\"files_local\":\"1\",\"files_pdf\":\"1\",\"files_office\":\"1\",\"files_image\":\"1\"}" || :

    # Touch initialization flag
    touch "${OPENSEARCH_FLAG}" 2>/dev/null || :
    echo "[OPENSEARCH-HOOK] ✅ FullTextSearch successfully configured for tenant '${TENANT_ID}'."
else
    echo "[OPENSEARCH-HOOK] ℹ️ Nextcloud not yet installed. Configuration deferred to next start."
fi
