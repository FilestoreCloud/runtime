# ==============================================================================
# FilestoreCloud Enterprise Golden Image
# ==============================================================================
# Base image: Official Nextcloud 30 (Apache & PHP 8.2+)
# Architecture: Multi-Stage Build with Pre-baked Apps & PHP OPcache Optimization
# Zero Runtime Downloads: Works seamlessly in air-gapped & Zero-NAT environments
# ==============================================================================

# ── Stage 1: Downloader ────────────────────────────────────────────────────────
FROM alpine:3.20 AS builder

# hadolint ignore=DL3018
RUN apk add --no-cache curl tar ca-certificates python3

ENV ASSISTANT_VERSION="v2.13.0"
ENV ASSISTANT_SHA256="59f0a5ee67468b787b0b506018282e18c4689da70301006ee6fbc7e75368fa05"
ENV OPENAI_INTEGRATION_VERSION="v3.10.2"
ENV OPENAI_INTEGRATION_SHA256="0567bbea950b2cf90e5547c6bece93750008048b6ea88356742610fd0379f2ab"
ENV FULLTEXTSEARCH_VERSION="30.0.2"
ENV FULLTEXTSEARCH_SHA256="b0cbeb2359c8d8ece7dfca81fc770a7c72ce18b21892a460db0b6ae4bffb3046"
ENV FILES_FULLTEXTSEARCH_VERSION="30.0.1"
ENV FILES_FULLTEXTSEARCH_SHA256="5f0974cc8ecd692751d953770b913a420b44fb6463ea5cf642556b471dd9d6ed"
ENV FULLTEXTSEARCH_ELASTICSEARCH_VERSION="30.0.1"
ENV FULLTEXTSEARCH_ELASTICSEARCH_SHA256="f366504f50e8a490ebc99fe9bee10943e785ec76fae22c88a92bda65cb8c8424"

WORKDIR /apps
# hadolint ignore=DL4006
RUN curl -fsSL -o assistant.tar.gz "https://github.com/nextcloud-releases/assistant/releases/download/${ASSISTANT_VERSION}/assistant-${ASSISTANT_VERSION}.tar.gz" \
    && echo "${ASSISTANT_SHA256}  assistant.tar.gz" | sha256sum -c - \
    && tar -xzf assistant.tar.gz && rm -f assistant.tar.gz \
    && curl -fsSL -o integration_openai.tar.gz "https://github.com/nextcloud-releases/integration_openai/releases/download/${OPENAI_INTEGRATION_VERSION}/integration_openai-${OPENAI_INTEGRATION_VERSION}.tar.gz" \
    && echo "${OPENAI_INTEGRATION_SHA256}  integration_openai.tar.gz" | sha256sum -c - \
    && tar -xzf integration_openai.tar.gz && rm -f integration_openai.tar.gz \
    && curl -fsSL -o fulltextsearch.tar.gz "https://github.com/nextcloud-releases/fulltextsearch/releases/download/${FULLTEXTSEARCH_VERSION}/fulltextsearch-${FULLTEXTSEARCH_VERSION}.tar.gz" \
    && echo "${FULLTEXTSEARCH_SHA256}  fulltextsearch.tar.gz" | sha256sum -c - \
    && tar -xzf fulltextsearch.tar.gz && rm -f fulltextsearch.tar.gz \
    && curl -fsSL -o files_fulltextsearch.tar.gz "https://github.com/nextcloud-releases/files_fulltextsearch/releases/download/${FILES_FULLTEXTSEARCH_VERSION}/files_fulltextsearch-${FILES_FULLTEXTSEARCH_VERSION}.tar.gz" \
    && echo "${FILES_FULLTEXTSEARCH_SHA256}  files_fulltextsearch.tar.gz" | sha256sum -c - \
    && tar -xzf files_fulltextsearch.tar.gz && rm -f files_fulltextsearch.tar.gz \
    && curl -fsSL -o fulltextsearch_elasticsearch.tar.gz "https://github.com/nextcloud-releases/fulltextsearch_elasticsearch/releases/download/${FULLTEXTSEARCH_ELASTICSEARCH_VERSION}/fulltextsearch_elasticsearch-${FULLTEXTSEARCH_ELASTICSEARCH_VERSION}.tar.gz" \
    && echo "${FULLTEXTSEARCH_ELASTICSEARCH_SHA256}  fulltextsearch_elasticsearch.tar.gz" | sha256sum -c - \
    && tar -xzf fulltextsearch_elasticsearch.tar.gz && rm -f fulltextsearch_elasticsearch.tar.gz \
    && sed -i 's/throw new ProductCheckException/return; \/\/ throw new ProductCheckException/g' /apps/fulltextsearch_elasticsearch/lib/Vendor/Elastic/Elasticsearch/Traits/ProductCheckTrait.php \
    && sed -i 's/protected function buildCompatibilityHeaders(array \$headers) : array/protected function buildCompatibilityHeaders(array \$headers) : array { return \$headers; } protected function _orig_buildCompatibilityHeaders(array \$headers) : array/g' /apps/fulltextsearch_elasticsearch/lib/Vendor/Elastic/Elasticsearch/Traits/EndpointTrait.php \
    && sed -i 's/max_analyzed_offset/max_analyzer_offset/g' /apps/fulltextsearch_elasticsearch/lib/Service/SearchMappingService.php \
    && python3 -c "p = '/apps/fulltextsearch_elasticsearch/lib/Service/IndexMappingService.php'; s = open(p).read(); s = s.replace(\"'mappings' => [\n\t\t\t\t'standard' => [\", \"'mappings' => [\"); s = s.replace(\"\t\t\t\t\t]\n\t\t\t\t]\n\t\t\t]\n\t\t];\", \"\t\t\t\t\t]\n\t\t\t]\n\t\t];\"); open(p, 'w').write(s)"

# ── Stage 2: Production Golden Image ───────────────────────────────────────────
FROM nextcloud:30.0.17-apache

LABEL maintainer="FilestoreCloud Engineering Team"
LABEL version="2.0.0"
LABEL description="FilestoreCloud Hardened Nextcloud 30 Golden Runtime Image"

# Copy pre-downloaded apps from builder
COPY --from=builder --chown=www-data:www-data /apps /var/www/html/custom_apps/
COPY --from=builder --chown=www-data:www-data /apps /usr/src/nextcloud/custom_apps/

# Copy OPcache & PHP optimizations
COPY config/opcache.ini /usr/local/etc/php/conf.d/opcache-recommended.ini
COPY config/storix-mpm.conf /etc/apache2/conf-available/storix-mpm.conf

# Copy Nextcloud modular configurations
COPY config/ai.config.php /usr/src/nextcloud/config/ai.config.php
COPY config/search.config.php /usr/src/nextcloud/config/search.config.php
COPY config/nextcloud.config.php /usr/src/nextcloud/config/nextcloud.config.php
# Copy Storix custom theme
COPY themes/storix /usr/src/nextcloud/themes/storix/
RUN mkdir -p /var/www/html/config /var/www/html/themes /usr/src/nextcloud/core/img /var/www/html/core/img /var/www/html/themes/storix/core/img/tenants /usr/src/nextcloud/themes/storix/core/img/tenants \
    && cp /usr/src/nextcloud/config/ai.config.php /var/www/html/config/ai.config.php \
    && cp /usr/src/nextcloud/config/search.config.php /var/www/html/config/search.config.php \
    && cp /usr/src/nextcloud/config/nextcloud.config.php /var/www/html/config/nextcloud.config.php \
    && cp -r /usr/src/nextcloud/themes/storix /var/www/html/themes/storix \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/logo-white.png /usr/src/nextcloud/core/img/logo-header.png 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/logo-wide.svg /usr/src/nextcloud/core/img/logo-header.svg 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/logo-white.png /usr/src/nextcloud/core/img/logo.png 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/logo-wide.svg /usr/src/nextcloud/core/img/logo.svg 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/favicon.ico /usr/src/nextcloud/core/img/favicon.ico 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/favicon.png /usr/src/nextcloud/core/img/favicon.png 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/favicon-touch.png /usr/src/nextcloud/core/img/favicon-touch.png 2>/dev/null || : \
    && cp -r /usr/src/nextcloud/themes/storix/core/img/background.png /usr/src/nextcloud/core/img/background.png 2>/dev/null || : \
    && cp -a /usr/src/nextcloud/. /var/www/html/ \
    && cp -p /usr/src/nextcloud/version.php /var/www/html/version.php \
    && rm -f /var/www/html/config/CAN_INSTALL /usr/src/nextcloud/config/CAN_INSTALL \
    && chown -R www-data:www-data /usr/src/nextcloud /var/www/html \
    && chmod -R 775 /var/www/html/themes /usr/src/nextcloud/themes

# Copy entrypoint hooks and wrapper
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh
COPY hooks/02-setup-opensearch.sh /docker-entrypoint-hooks.d/post-installation/02-setup-opensearch.sh
COPY hooks/02-setup-opensearch.sh /docker-entrypoint-hooks.d/before-starting/02-setup-opensearch.sh
COPY storix-entrypoint.sh /storix-entrypoint.sh

RUN chmod +x /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh \
    && chmod +x /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh \
    && chmod +x /docker-entrypoint-hooks.d/post-installation/02-setup-opensearch.sh \
    && chmod +x /docker-entrypoint-hooks.d/before-starting/02-setup-opensearch.sh \
    && chmod +x /storix-entrypoint.sh \
    && a2enconf storix-mpm \
    && chown -R www-data:www-data /docker-entrypoint-hooks.d

ENTRYPOINT ["/storix-entrypoint.sh"]
CMD ["apache2-foreground"]

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/status.php || exit 1
