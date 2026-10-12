# ==============================================================================
# Nextcloud Enterprise AI Golden Image
# ==============================================================================
# Base image: Official Nextcloud 30 (Apache & PHP 8.2+)
# Architecture: Pre-baked AI apps into /var/www/html/custom_apps/ & /usr/src/nextcloud/custom_apps/
# Zero Runtime Downloads: Works seamlessly in air-gapped & Zero-NAT environments
# ==============================================================================
FROM nextcloud:30.0.17-apache

LABEL maintainer="Nextcloud SaaS Engineering Team"
LABEL version="1.2.0"
LABEL description="Nextcloud Enterprise AI Golden Image with Pre-baked Assistant & Bedrock/OpenAI Apps"

# 1. Install utilities required for image building
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tar \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Pre-bake AI Apps into /var/www/html/custom_apps (Zero runtime network calls)
ENV ASSISTANT_VERSION="v4.0.0"
ENV OPENAI_INTEGRATION_VERSION="v5.0.0"

# hadolint ignore=DL3003
RUN mkdir -p /var/www/html/custom_apps && cd /var/www/html/custom_apps \
    && echo "Pre-baking Nextcloud Assistant ${ASSISTANT_VERSION}..." \
    && curl -fsSL -o assistant.tar.gz "https://github.com/nextcloud-releases/assistant/releases/download/${ASSISTANT_VERSION}/assistant-${ASSISTANT_VERSION}.tar.gz" \
    && tar -xzf assistant.tar.gz && rm -f assistant.tar.gz \
    && echo "Pre-baking OpenAI / Bedrock Integration ${OPENAI_INTEGRATION_VERSION}..." \
    && curl -fsSL -o integration_openai.tar.gz "https://github.com/nextcloud-releases/integration_openai/releases/download/${OPENAI_INTEGRATION_VERSION}/integration_openai-${OPENAI_INTEGRATION_VERSION}.tar.gz" \
    && tar -xzf integration_openai.tar.gz && rm -f integration_openai.tar.gz \
    # Improvement 1: Sync to /usr/src/nextcloud/custom_apps so entrypoint rsync preserves apps across boots
    && mkdir -p /usr/src/nextcloud/custom_apps \
    && cp -r /var/www/html/custom_apps/* /usr/src/nextcloud/custom_apps/ \
    && chown -R www-data:www-data /var/www/html/custom_apps /usr/src/nextcloud/custom_apps

# 3. Pre-seed modular configuration files (prevents version-check warnings & applies hardening)
COPY config/ai.config.php /usr/src/nextcloud/config/ai.config.php
COPY config/nextcloud.config.php /usr/src/nextcloud/config/nextcloud.config.php
RUN mkdir -p /var/www/html/config \
    && cp /usr/src/nextcloud/config/ai.config.php /var/www/html/config/ai.config.php \
    && cp /usr/src/nextcloud/config/nextcloud.config.php /var/www/html/config/nextcloud.config.php \
    && chown -R www-data:www-data /usr/src/nextcloud/config /var/www/html/config

# 4. Inject native Docker Entrypoint Hooks to auto-enable AI apps on container startup
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh
COPY hooks/01-setup-ai.sh /docker-entrypoint-hooks.d/pre-installation/01-setup-ai.sh

RUN chmod +x /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh \
    && chmod +x /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh \
    && chmod +x /docker-entrypoint-hooks.d/pre-installation/01-setup-ai.sh \
    && chown -R www-data:www-data /docker-entrypoint-hooks.d

# Health check inherits from official Nextcloud Apache container
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost/status.php || exit 1
