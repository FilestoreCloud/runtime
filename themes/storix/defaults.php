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
}
