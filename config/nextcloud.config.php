<?php
/**
 * Nextcloud System Configuration — Production Hardening
 *
 * This file is auto-merged by Nextcloud core ($CONFIG array).
 * Place in /var/www/html/config/ (or /usr/src/nextcloud/config/ for image pre-seeding).
 *
 * Fixes addressed:
 *   - HTTP/HTTPS proxy settings (ALB terminates TLS)
 *   - Strict-Transport-Security (HSTS)
 *   - APCu local memcache (reduces DB locking load)
 *   - Maintenance window (2 AM UTC)
 *   - Default phone region (Vietnam = VN)
 */
$CONFIG = [

    // ── HTTPS / Reverse-Proxy ───────────────────────────────────────────────
    // The ALB terminates TLS and forwards HTTP to the Fargate container.
    // These tell Nextcloud to treat incoming requests as HTTPS.
    'overwriteprotocol' => 'https',
    'trusted_proxies'   => ['10.0.0.0/16'],   // VPC CIDR — adjust if needed
    'forwarded_for_headers' => ['HTTP_X_FORWARDED_FOR'],

    // ── Strict-Transport-Security ───────────────────────────────────────────
    // Belt-and-suspenders: ALB response header policy also injects HSTS.
    'hsts' => true,

    // ── Local Memcache (APCu) ───────────────────────────────────────────────
    // Eliminates DB-based transactional file locking for single-node deployments.
    // For multi-replica ECS tasks, replace with Redis (ElastiCache) — see hook.
    'memcache.local' => '\OC\Memcache\APCu',

    // ── Background Jobs / Maintenance Window ───────────────────────────────
    // 2 = 2:00 AM UTC. Resource-intensive cron jobs will only start in this window.
    'maintenance_window_start' => 2,

    // ── Default Phone Region ────────────────────────────────────────────────
    // ISO 3166-1 alpha-2. Set to VN (Vietnam); change as needed.
    'default_phone_region' => 'VN',

    // ── AI App Overwrite Allowlist ──────────────────────────────────────────
    'app_install_overwrite' => [
        'assistant',
        'integration_openai',
    ],

];

// ── S3 Primary ObjectStore (Vault) ───────────────────────────────────────────
$s3Bucket = getenv('OBJECTSTORE_S3_BUCKET');
if ($s3Bucket) {
    $CONFIG['objectstore'] = [
        'class' => '\\OC\\Files\\ObjectStore\\S3',
        'arguments' => [
            'bucket' => $s3Bucket,
            'autocreate' => (getenv('OBJECTSTORE_S3_AUTOCREATE') === 'true'),
            'region' => getenv('OBJECTSTORE_S3_REGION') ?: (getenv('AWS_REGION') ?: 'ap-southeast-1'),
            'use_ssl' => (getenv('OBJECTSTORE_S3_SSL') !== 'false'),
            'use_path_style' => (getenv('OBJECTSTORE_S3_USEPATH_STYLE') === 'true'),
        ],
    ];
}
