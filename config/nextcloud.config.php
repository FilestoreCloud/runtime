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
    // 'overwriteprotocol' => 'https' (Default production setting; supports dynamic OVERWRITEPROTOCOL override)
    'overwriteprotocol' => (getenv('OVERWRITEPROTOCOL') !== false && getenv('OVERWRITEPROTOCOL') !== '') ? getenv('OVERWRITEPROTOCOL') : 'https',
    'overwrite.cli.url' => (getenv('OVERWRITECLIURL') !== false && getenv('OVERWRITECLIURL') !== '') ? getenv('OVERWRITECLIURL') : 'http://localhost',

    // ── Default Theme & White-Label ─────────────────────────────────────────
    'theme'             => 'storix',

    // ── Trusted Domains ─────────────────────────────────────────────────────
    // Dynamic resolution from NEXTCLOUD_TRUSTED_DOMAINS environment variable
    // to prevent Host Header injection attacks (bare wildcard '*' is strictly forbidden).
    'trusted_domains'   => [
        ...(function () {
            $domains = ['localhost', '127.0.0.1'];
            $raw = getenv('NEXTCLOUD_TRUSTED_DOMAINS');
            if ($raw !== false && trim($raw) !== '') {
                $parsed = array_values(array_filter(array_map('trim', preg_split('/[\s,]+/', trim($raw)))));
                // Strictly exclude bare wildcard '*'
                $parsed = array_values(array_filter($parsed, function ($d) {
                    return $d !== '*' && $d !== '';
                }));
                if (!empty($parsed)) {
                    $domains = array_values(array_unique(array_merge($domains, $parsed)));
                }
            }
            return $domains;
        })(),
    ],
    'trusted_proxies'   => [
        ...(function () {
            $raw = getenv('TRUSTED_PROXIES');
            if ($raw !== false && trim($raw) !== '') {
                $proxies = array_values(array_filter(array_map('trim', preg_split('/[\s,]+/', trim($raw)))));
                if (!empty($proxies)) {
                    return $proxies;
                }
            }
            return ['10.0.0.0/16'];
        })(),
    ],
    'forwarded_for_headers' => ['HTTP_X_FORWARDED_FOR'],

    // ── Strict-Transport-Security ───────────────────────────────────────────
    // Belt-and-suspenders: ALB response header policy also injects HSTS.
    'hsts' => true,

    // ── Local Memcache (APCu) ───────────────────────────────────────────────
    // Eliminates DB-based transactional file locking for single-node deployments.
    // For multi-replica ECS tasks, replace with Redis (ElastiCache) — see hook.
    'memcache.local' => '\OC\Memcache\APCu',

    // ── Logging to stderr (Docker / CloudWatch) ──────────────────────────────
    'log_type' => 'errorlog',

    // ── Background Jobs / Maintenance Window ───────────────────────────────
    // 2 = 2:00 AM UTC. Resource-intensive cron jobs will only start in this window.
    'maintenance_window_start' => 2,

    // ── Default Phone Region ────────────────────────────────────────────────
    // ISO 3166-1 alpha-2. Set to VN (Vietnam); change as needed.
    'default_phone_region' => 'VN',

    // ── Pre-baked Apps Overwrite Allowlist ──────────────────────────────────
    'app_install_overwrite' => [
        'assistant',
        'integration_openai',
        'fulltextsearch',
        'files_fulltextsearch',
        'fulltextsearch_elasticsearch',
    ],

    // ── Multi-Directory Apps Configuration (Production Hardened) ────────────
    'appstoreenabled' => false,
    'apps_paths' => [
        [
            'path'     => '/var/www/html/apps',
            'url'      => '/apps',
            'writable' => false,
        ],
        [
            'path'     => '/var/www/html/custom_apps',
            'url'      => '/custom_apps',
            'writable' => true,
        ],
    ],
];

// ── S3 Primary ObjectStore (Vault) & Direct-to-S3 Transfer ───────────────────
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
            'upload_part_size' => 52428800, // 50MB Multipart chunking for optimal throughput
        ],
    ];
    if (getenv('TENANT_STORAGE_PREFIX') !== false && trim(getenv('TENANT_STORAGE_PREFIX')) !== '') {
        $CONFIG['objectstore']['arguments']['prefix'] = trim(getenv('TENANT_STORAGE_PREFIX'));
    }
    // Enable direct transfer mechanics to bypass PHP streaming bottlenecks
    $CONFIG['direct_transfer'] = true;
}

// ── Redis Distributed Cache & File Locking (ElastiCache) ───────────────────
$redisHost = getenv('REDIS_HOST') ?: getenv('REDIS_ENDPOINT');
if ($redisHost && trim($redisHost) !== '') {
    $CONFIG['memcache.distributed'] = '\OC\Memcache\Redis';
    $CONFIG['memcache.locking'] = '\OC\Memcache\Redis';
    $CONFIG['redis'] = [
        'host' => trim($redisHost),
        'port' => (int)(getenv('REDIS_PORT') ?: 6379),
        'timeout' => 1.5,
    ];
    if (getenv('REDIS_PASSWORD')) {
        $CONFIG['redis']['password'] = getenv('REDIS_PASSWORD');
    }
}

