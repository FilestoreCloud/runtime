<?php
/**
 * Storix Custom Multi-Tenant Theme Defaults
 * Dynamically customizes branding, titles, slogans, colors, and logos based on tenant identity.
 */

class OC_Theme {

    /**
     * Resolves tenant slug from container environment or Host header
     */
    private function getTenantSlug(): string {
        $tenant = getenv('TENANT_ID');
        if (!empty($tenant) && $tenant !== 'storix' && $tenant !== 'default') {
            return strtolower(trim($tenant));
        }

        $host = $_SERVER['HTTP_HOST'] ?? '';
        if (!empty($host)) {
            $hostParts = explode(':', $host);
            $cleanHost = $hostParts[0];
            $parts = explode('.', $cleanHost);
            $subdomain = $parts[0] ?? '';
            $reserved = ['admin', 'api', 'www', 'storix', 'localhost', 'dev-nextcloud', 'prod-nextcloud'];
            if (!empty($subdomain) && !in_array(strtolower($subdomain), $reserved, true)) {
                return strtolower(trim($subdomain));
            }
        }

        return 'storix';
    }

    /**
     * Formats the tenant display name
     */
    private function getTenantDisplayName(string $slug): string {
        if ($slug === 'storix') {
            return 'Storix';
        }
        if (strlen($slug) <= 4) {
            return strtoupper($slug);
        }
        return ucwords(str_replace(['-', '_'], ' ', $slug));
    }

    /**
     * Generates a deterministic palette for the tenant
     */
    private function getTenantPalette(string $slug): array {
        if ($slug === 'storix') {
            return [
                'primary' => '#1652f0',
                'secondary' => '#00c6ff',
                'darkBg' => '#071736',
                'accent' => '#3b82f6',
            ];
        }

        $palettes = [
            [
                'primary' => '#059669', // Emerald
                'secondary' => '#34d399',
                'darkBg' => '#062e24',
                'accent' => '#10b981',
            ],
            [
                'primary' => '#7c3aed', // Purple / Violet
                'secondary' => '#c084fc',
                'darkBg' => '#1a0e36',
                'accent' => '#8b5cf6',
            ],
            [
                'primary' => '#ea580c', // Coral / Orange
                'secondary' => '#fb923c',
                'darkBg' => '#2e1306',
                'accent' => '#f97316',
            ],
            [
                'primary' => '#0891b2', // Cyan / Teal
                'secondary' => '#38bdf8',
                'darkBg' => '#062836',
                'accent' => '#06b6d4',
            ],
            [
                'primary' => '#e11d48', // Rose / Crimson
                'secondary' => '#fb7185',
                'darkBg' => '#360814',
                'accent' => '#f43f5e',
            ],
            [
                'primary' => '#4f46e5', // Indigo
                'secondary' => '#818cf8',
                'darkBg' => '#0e1238',
                'accent' => '#6366f1',
            ],
            [
                'primary' => '#d97706', // Amber / Gold
                'secondary' => '#fbbf24',
                'darkBg' => '#2b1c05',
                'accent' => '#f59e0b',
            ],
            [
                'primary' => '#2563eb', // Royal Blue
                'secondary' => '#60a5fa',
                'darkBg' => '#0b193d',
                'accent' => '#3b82f6',
            ],
        ];

        $idx = abs(crc32($slug)) % count($palettes);
        return $palettes[$idx];
    }

    /**
     * Ensures an SVG logo exists on disk for this tenant, generating it if necessary.
     */
    private function ensureTenantLogo(string $slug, string $type): ?string {
        $slugClean = preg_replace('/[^a-zA-Z0-9_-]/', '', $slug);
        if (empty($slugClean) || $slugClean === 'storix') {
            return null;
        }

        $dir = __DIR__ . '/core/img/tenants';
        if (!is_dir($dir)) {
            @mkdir($dir, 0775, true);
        }

        $fileName = ($type === 'header') ? "logo-header-{$slugClean}.svg" : "logo-{$slugClean}.svg";
        $fullPath = $dir . '/' . $fileName;
        $relativePath = 'themes/storix/core/img/tenants/' . $fileName;

        if (file_exists($fullPath) && filesize($fullPath) > 50) {
            return $relativePath;
        }

        $palette = $this->getTenantPalette($slugClean);
        $displayName = $this->getTenantDisplayName($slugClean);
        $initial = strtoupper(substr($displayName, 0, 1));
        $primary = htmlspecialchars($palette['primary'], ENT_QUOTES, 'UTF-8');
        $secondary = htmlspecialchars($palette['secondary'], ENT_QUOTES, 'UTF-8');
        $safeName = htmlspecialchars($displayName, ENT_QUOTES, 'UTF-8');
        $safeInitial = htmlspecialchars($initial, ENT_QUOTES, 'UTF-8');

        if ($type === 'header') {
            $svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 50" width="260" height="50">' . "\n"
                . '  <defs>' . "\n"
                . '    <linearGradient id="gradH_' . $slugClean . '" x1="0%" y1="0%" x2="100%" y2="100%">' . "\n"
                . '      <stop offset="0%" stop-color="' . $primary . '"/>' . "\n"
                . '      <stop offset="100%" stop-color="' . $secondary . '"/>' . "\n"
                . '    </linearGradient>' . "\n"
                . '  </defs>' . "\n"
                . '  <rect x="5" y="5" width="40" height="40" rx="10" fill="url(#gradH_' . $slugClean . ')"/>' . "\n"
                . '  <text x="25" y="26" font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif" font-size="20" font-weight="800" fill="#ffffff" text-anchor="middle" dominant-baseline="central">' . $safeInitial . '</text>' . "\n"
                . '  <text x="56" y="26" font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif" font-size="18" font-weight="700" fill="#ffffff" dominant-baseline="central">' . $safeName . ' CLOUD</text>' . "\n"
                . '</svg>';
        } else {
            $svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 140" width="520" height="140">' . "\n"
                . '  <defs>' . "\n"
                . '    <linearGradient id="gradW_' . $slugClean . '" x1="0%" y1="0%" x2="100%" y2="100%">' . "\n"
                . '      <stop offset="0%" stop-color="' . $primary . '"/>' . "\n"
                . '      <stop offset="100%" stop-color="' . $secondary . '"/>' . "\n"
                . '    </linearGradient>' . "\n"
                . '    <filter id="shadow_' . $slugClean . '" x="-10%" y="-10%" width="130%" height="130%">' . "\n"
                . '      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="' . $primary . '" flood-opacity="0.35"/>' . "\n"
                . '    </filter>' . "\n"
                . '  </defs>' . "\n"
                . '  <rect x="15" y="15" width="110" height="110" rx="24" fill="url(#gradW_' . $slugClean . ')" filter="url(#shadow_' . $slugClean . ')"/>' . "\n"
                . '  <path d="M 45 80 C 38 80 32 74 32 67 C 32 60 37 55 43 54 C 45 44 54 37 65 37 C 75 37 84 44 86 54 C 92 55 97 60 97 67 C 97 74 91 80 84 80 Z" fill="none" stroke="#ffffff" stroke-width="3" stroke-opacity="0.25"/>' . "\n"
                . '  <text x="70" y="74" font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif" font-size="48" font-weight="900" fill="#ffffff" text-anchor="middle" dominant-baseline="central">' . $safeInitial . '</text>' . "\n"
                . '  <text x="145" y="62" font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif" font-size="34" font-weight="800" fill="#ffffff" letter-spacing="1px">' . $safeName . ' CLOUD</text>' . "\n"
                . '  <rect x="145" y="82" width="310" height="26" rx="13" fill="' . $primary . '" fill-opacity="0.25" stroke="' . $secondary . '" stroke-width="1" stroke-opacity="0.5"/>' . "\n"
                . '  <text x="160" y="99" font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif" font-size="11" font-weight="700" fill="#e2e8f0" letter-spacing="0.5px">DEDICATED CLOUD &#8226; POWERED BY STORIX</text>' . "\n"
                . '</svg>';
        }

        if (@file_put_contents($fullPath, $svg) !== false) {
            return $relativePath;
        }

        return null;
    }

    /**
     * Base URL for branding links
     */
    public function getBaseUrl(): string {
        return 'https://storix.io';
    }

    /**
     * Documentation URL
     */
    public function getDocBaseUrl(): string {
        return 'https://docs.storix.io';
    }

    /**
     * Title shown in browser titlebar / tabs
     */
    public function getTitle(): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            return 'Storix — Enterprise Cloud Storage';
        }
        $name = $this->getTenantDisplayName($slug);
        return $name . ' Cloud — Storix';
    }

    /**
     * Short name used throughout the UI
     */
    public function getName(): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            return 'Storix';
        }
        return $this->getTenantDisplayName($slug) . ' Cloud';
    }

    /**
     * HTML formatted name
     */
    public function getHTMLName(): string {
        return htmlspecialchars($this->getName(), ENT_QUOTES, 'UTF-8');
    }

    /**
     * Entity name for copyrights
     */
    public function getEntity(): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            return 'Storix Platform Inc.';
        }
        return $this->getTenantDisplayName($slug) . ' Workspace';
    }

    /**
     * Slogan displayed on login page and dialogs
     */
    public function getSlogan(): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            return 'Enterprise Cloud Storage Platform';
        }
        return 'Dedicated Enterprise Cloud Platform';
    }

    /**
     * Short footer
     */
    public function getShortFooter(): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            return '© ' . date('Y') . ' Storix Cloud Platform';
        }
        return '© ' . date('Y') . ' ' . $this->getTenantDisplayName($slug) . ' Cloud Platform';
    }

    /**
     * Long footer
     */
    public function getLongFooter(): string {
        return '© ' . date('Y') . ' <a href="' . $this->getBaseUrl() . '" target="_blank">' . $this->getEntity() . '</a> — ' . $this->getSlogan();
    }

    /**
     * Mail header / footer branding
     */
    public function getMailHeaderColor(): string {
        return $this->getColorPrimary();
    }

    /**
     * Primary Brand Color for UI buttons and active accents
     */
    public function getColorPrimary(): string {
        $slug = $this->getTenantSlug();
        $palette = $this->getTenantPalette($slug);
        return $palette['primary'];
    }

    /**
     * Default primary color fallback
     */
    public function getDefaultColorPrimary(): string {
        return '#1652f0';
    }

    /**
     * Header & background base color
     */
    public function getBackgroundColor(): string {
        $slug = $this->getTenantSlug();
        $palette = $this->getTenantPalette($slug);
        return $palette['darkBg'];
    }

    /**
     * Path / URL to the main brand logo
     */
    public function getLogo(bool $useSvg = true): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            if ($useSvg && file_exists(__DIR__ . '/core/img/logo-wide.svg')) {
                return 'themes/storix/core/img/logo-wide.svg';
            }
            return 'themes/storix/core/img/logo-white.png';
        }

        $tenantLogo = $this->ensureTenantLogo($slug, 'wide');
        if ($tenantLogo) {
            return $tenantLogo;
        }

        if ($useSvg && file_exists(__DIR__ . '/core/img/logo-wide.svg')) {
            return 'themes/storix/core/img/logo-wide.svg';
        }
        return 'themes/storix/core/img/logo-white.png';
    }

    /**
     * Path / URL to the header navigation logo
     */
    public function getLogoHeader(bool $useSvg = true): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            if ($useSvg && file_exists(__DIR__ . '/core/img/logo-header.svg')) {
                return 'themes/storix/core/img/logo-header.svg';
            }
            return 'themes/storix/core/img/logo-header.png';
        }

        $tenantHeader = $this->ensureTenantLogo($slug, 'header');
        if ($tenantHeader) {
            return $tenantHeader;
        }

        if ($useSvg && file_exists(__DIR__ . '/core/img/logo-header.svg')) {
            return 'themes/storix/core/img/logo-header.svg';
        }
        return 'themes/storix/core/img/logo-header.png';
    }

    /**
     * Path / URL to the branded background image
     */
    public function getBackground(): string {
        return 'themes/storix/core/img/background.png';
    }

    /**
     * Product name returned in status.php and API endpoints
     */
    public function getProductName(): string {
        $slug = $this->getTenantSlug();
        if ($slug === 'storix') {
            return 'Storix';
        }
        return $this->getTenantDisplayName($slug) . ' Cloud';
    }
}
