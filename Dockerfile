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
RUN apk add --no-cache curl tar ca-certificates

ENV ASSISTANT_VERSION="v4.0.0"
ENV ASSISTANT_SHA256="0d7c72d3cd8a41cdb7a402d0822331d6cad23271a9a4ee6222c85f00b2dd6271"
ENV OPENAI_INTEGRATION_VERSION="v5.0.0"
ENV OPENAI_INTEGRATION_SHA256="c980b47d462d6f84a4161e13122277fa049b0650da14207d98066ee7d5ba5127"

WORKDIR /apps
# hadolint ignore=DL4006
RUN curl -fsSL -o assistant.tar.gz "https://github.com/nextcloud-releases/assistant/releases/download/${ASSISTANT_VERSION}/assistant-${ASSISTANT_VERSION}.tar.gz" \
    && echo "${ASSISTANT_SHA256}  assistant.tar.gz" | sha256sum -c - \
    && tar -xzf assistant.tar.gz && rm -f assistant.tar.gz \
    && curl -fsSL -o integration_openai.tar.gz "https://github.com/nextcloud-releases/integration_openai/releases/download/${OPENAI_INTEGRATION_VERSION}/integration_openai-${OPENAI_INTEGRATION_VERSION}.tar.gz" \
    && echo "${OPENAI_INTEGRATION_SHA256}  integration_openai.tar.gz" | sha256sum -c - \
    && tar -xzf integration_openai.tar.gz && rm -f integration_openai.tar.gz

# ── Stage 2: Production Golden Image ───────────────────────────────────────────
FROM nextcloud:35.0.1-apache

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
COPY config/nextcloud.config.php /usr/src/nextcloud/config/nextcloud.config.php
# Copy Storix custom theme
COPY themes/storix /usr/src/nextcloud/themes/storix/
RUN mkdir -p /var/www/html/config /var/www/html/themes /usr/src/nextcloud/core/img /var/www/html/core/img \
    && cp /usr/src/nextcloud/config/ai.config.php /var/www/html/config/ai.config.php \
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
    && rm -f /var/www/html/version.php \
    && chown -R www-data:www-data /usr/src/nextcloud /var/www/html

# Copy entrypoint hooks and wrapper
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh
COPY storix-entrypoint.sh /storix-entrypoint.sh

RUN chmod +x /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh \
    && chmod +x /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh \
    && chmod +x /storix-entrypoint.sh \
    && a2enconf storix-mpm \
    && chown -R www-data:www-data /docker-entrypoint-hooks.d

ENTRYPOINT ["/storix-entrypoint.sh"]
CMD ["apache2-foreground"]

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/status.php || exit 1
