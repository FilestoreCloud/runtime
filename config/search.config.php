<?php
/**
 * Nextcloud OpenSearch & FullTextSearch Configuration
 *
 * Configures OpenSearch domain, tenant index namespaces,
 * and Apache Tika text extraction sidecar.
 */

$opensearchHost = getenv('OPENSEARCH_HOST') ?: getenv('ELASTICSEARCH_HOST');
$tikaHost = getenv('TIKA_HOST') ?: '127.0.0.1';
$tikaPort = (int)(getenv('TIKA_PORT') ?: 9998);
$tenantId = getenv('TENANT_ID') ?: 'default';

// Add search apps to overwrite allowlist
if (!isset($CONFIG['app_install_overwrite'])) {
    $CONFIG['app_install_overwrite'] = [];
}
$CONFIG['app_install_overwrite'] = array_values(array_unique(array_merge(
    $CONFIG['app_install_overwrite'],
    [
        'assistant',
        'integration_openai',
        'fulltextsearch',
        'files_fulltextsearch',
        'fulltextsearch_elasticsearch',
    ]
)));

// Configure OpenSearch cluster settings if host is provided
if ($opensearchHost && trim($opensearchHost) !== '') {
    $opensearchPort = (int)(getenv('OPENSEARCH_PORT') ?: 443);
    $opensearchProto = getenv('OPENSEARCH_PROTO') ?: 'https';
    $sanitizedTenant = preg_replace('/[^a-zA-Z0-9_-]/', '_', $tenantId);
    $opensearchIndex = 'tenant_' . $sanitizedTenant;

    $CONFIG['fulltextsearch'] = [
        'platform' => 'fulltextsearch_elasticsearch',
        'search_platform' => 'fulltextsearch_elasticsearch',
        'index' => $opensearchIndex,
        'elastic_host' => ["{$opensearchProto}://{$opensearchHost}:{$opensearchPort}"],
        'files_tika_host' => $tikaHost,
        'files_tika_port' => $tikaPort,
        'files_pdf' => '1',
        'files_office' => '1',
        'files_image' => '1',
    ];
}
