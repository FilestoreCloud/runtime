<?php
/**
 * Storix Custom Theme Defaults
 * Completely replaces all Nextcloud UI branding, titles, names, slogans, and footers with Storix.
 */

class OC_Theme {

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
        return 'Storix — Enterprise Cloud Storage';
    }

    /**
     * Short name used throughout the UI
     */
    public function getName(): string {
        return 'Storix';
    }

    /**
     * HTML formatted name
     */
    public function getHTMLName(): string {
        return 'Storix';
    }

    /**
     * Entity name for copyrights
     */
    public function getEntity(): string {
        return 'Storix Platform Inc.';
    }

    /**
     * Slogan displayed on login page and dialogs
     */
    public function getSlogan(): string {
        return 'Enterprise Cloud Storage Platform';
    }

    /**
     * Short footer
     */
    public function getShortFooter(): string {
        return '© ' . date('Y') . ' Storix Cloud Platform';
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
        return '#1652f0';
    }

    /**
     * Primary Brand Color for UI buttons and active accents
     */
    public function getColorPrimary(): string {
        return '#1652f0';
    }

    /**
     * Default primary color fallback
     */
    public function getDefaultColorPrimary(): string {
        return '#1652f0';
    }

    /**
     * Header & background base color (Deep Navy)
     */
    public function getBackgroundColor(): string {
        return '#071736';
    }

    /**
     * Path / URL to the main brand logo
     */
    public function getLogo(bool $useSvg = true): string {
        if ($useSvg && file_exists(__DIR__ . '/core/img/logo-wide.svg')) {
            return 'themes/storix/core/img/logo-wide.svg';
        }
        return 'themes/storix/core/img/logo-white.png';
    }

    /**
     * Path / URL to the header navigation logo
     */
    public function getLogoHeader(bool $useSvg = true): string {
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
        return 'Storix';
    }
}
