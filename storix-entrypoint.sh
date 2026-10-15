#!/bin/sh
set -e

# In ECS Fargate, /var/www/html is ephemeral container filesystem while /var/www/html/config is mounted to persistent EFS.
# If Nextcloud has already been installed on EFS config, ensure version.php exists in /var/www/html so that official
# docker-entrypoint.sh recognizes the existing installation and skips maintenance:install retry.
if [ -f /var/www/html/config/config.php ] && [ ! -f /var/www/html/version.php ]; then
    cp /usr/src/nextcloud/version.php /var/www/html/version.php 2>/dev/null || :
fi

exec /entrypoint.sh "$@"
