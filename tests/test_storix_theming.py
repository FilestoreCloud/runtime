#!/usr/bin/env python3
"""
Test Suite for Storix Nextcloud Runtime Custom Theme and Logo Branding.
Verifies:
1. Storix theme files (defaults.php, server.css, and core assets).
2. Image formats, dimensions, and readability (PIL verification).
3. Dockerfile asset synchronization and core image overlays.
4. storix-entrypoint.sh configuration and theme synchronization.
5. 01-setup-ai.sh theming:config execution (logo, logoheader, favicon, background, colors).
"""

import os
import re
import unittest
from PIL import Image

RUNTIME_DIR = os.environ.get("RUNTIME_REPO_ROOT")
REPO_ROOT = os.path.abspath(RUNTIME_DIR) if RUNTIME_DIR else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
THEMES_DIR = os.path.join(REPO_ROOT, "themes", "storix")
DEFAULTS_PHP = os.path.join(THEMES_DIR, "defaults.php")
SERVER_CSS = os.path.join(THEMES_DIR, "core", "css", "server.css")
IMG_DIR = os.path.join(THEMES_DIR, "core", "img")
DOCKERFILE = os.path.join(REPO_ROOT, "Dockerfile")
ENTRYPOINT_SH = os.path.join(REPO_ROOT, "storix-entrypoint.sh")
HOOK_SH = os.path.join(REPO_ROOT, "hooks", "01-setup-ai.sh")
NEXTCLOUD_CONFIG = os.path.join(REPO_ROOT, "config", "nextcloud.config.php")


class TestStorixThemeStructure(unittest.TestCase):
    """Verifies that the Storix theme folder and PHP class are properly configured."""

    def test_theme_directory_structure(self):
        """Ensures themes/storix directory has defaults.php, server.css, and core/img assets."""
        self.assertTrue(os.path.isdir(THEMES_DIR), f"Theme directory missing at {THEMES_DIR}")
        self.assertTrue(os.path.isfile(DEFAULTS_PHP), f"defaults.php missing at {DEFAULTS_PHP}")
        self.assertTrue(os.path.isfile(SERVER_CSS), f"server.css missing at {SERVER_CSS}")
        self.assertTrue(os.path.isdir(IMG_DIR), f"Image directory missing at {IMG_DIR}")

    def test_defaults_php_methods(self):
        """Verifies that defaults.php implements all required OC_Theme branding and theming methods."""
        with open(DEFAULTS_PHP, "r", encoding="utf-8") as f:
            content = f.read()

        # Class definition
        self.assertIn("class OC_Theme", content)

        # Branding methods
        self.assertIn("function getName()", content)
        self.assertIn("'Storix'", content)
        self.assertIn("function getTitle()", content)
        self.assertIn("function getSlogan()", content)
        self.assertIn("function getBaseUrl()", content)
        self.assertIn("https://storix.io", content)
        self.assertIn("function getEntity()", content)
        self.assertIn("function getProductName()", content)

        # Theming color & asset methods
        self.assertIn("function getColorPrimary()", content)
        self.assertIn("'#1652f0'", content)
        self.assertIn("function getDefaultColorPrimary()", content)
        self.assertIn("function getBackgroundColor()", content)
        self.assertIn("'#071736'", content)
        self.assertIn("function getLogo(", content)
        self.assertIn("function getLogoHeader(", content)
        self.assertIn("function getBackground()", content)

    def test_server_css_branding(self):
        """Verifies that server.css defines Storix CSS variables, header colors, and login gradients."""
        with open(SERVER_CSS, "r", encoding="utf-8") as f:
            content = f.read()

        # CSS variables
        self.assertIn("--color-primary: #1652f0;", content)
        self.assertIn("--color-header-background: #071736;", content)
        self.assertIn("--color-background-plain: #071736;", content)

        # Header bar
        self.assertIn("#header", content)
        self.assertIn("border-bottom: 2px solid #1652f0", content)

        # Login page background & card wrapper
        self.assertIn("#body-login", content)
        self.assertIn("#1652f0", content)
        self.assertIn("#071736", content)
        self.assertIn("#body-login .wrapper", content)
        self.assertIn("#body-login .logo", content)

        # Interactive controls
        self.assertIn(".primary", content)
        self.assertIn("button.primary", content)

    def test_nextcloud_config_theme_directive(self):
        """Verifies that nextcloud.config.php explicitly specifies 'theme' => 'storix'."""
        with open(NEXTCLOUD_CONFIG, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("'theme'             => 'storix'", content)


class TestStorixBrandAssets(unittest.TestCase):
    """Verifies that all required image and icon assets exist and are valid graphic files."""

    def test_core_image_files_exist(self):
        """Verifies presence of all core image assets in themes/storix/core/img."""
        expected_files = [
            "logo.png",
            "logo.svg",
            "logo-white.png",
            "logo-wide.png",
            "logo-wide.svg",
            "logo-header.png",
            "logo-header.svg",
            "favicon.ico",
            "favicon.png",
            "favicon-touch.png",
            "background.png",
            "storix-icon.png",
            "storix-logo.png",
            "storix-logo-white.png",
        ]
        for fname in expected_files:
            fpath = os.path.join(IMG_DIR, fname)
            self.assertTrue(os.path.isfile(fpath), f"Asset {fname} must exist in {IMG_DIR}")

    def test_image_dimensions_and_validity(self):
        """Ensures that image files can be loaded and have expected dimensions and formats."""
        # Check logo-white.png
        logo_white_path = os.path.join(IMG_DIR, "logo-white.png")
        with Image.open(logo_white_path) as img:
            self.assertEqual(img.format, "PNG")
            self.assertGreater(img.width, 200)
            self.assertGreater(img.height, 50)

        # Check logo-header.png
        logo_header_path = os.path.join(IMG_DIR, "logo-header.png")
        with Image.open(logo_header_path) as img:
            self.assertEqual(img.format, "PNG")
            self.assertGreater(img.width, 200)

        # Check square logo / icon (512x512)
        logo_sq_path = os.path.join(IMG_DIR, "logo.png")
        with Image.open(logo_sq_path) as img:
            self.assertEqual(img.format, "PNG")
            self.assertEqual(img.width, img.height)

        # Check favicon.ico
        favicon_ico_path = os.path.join(IMG_DIR, "favicon.ico")
        with Image.open(favicon_ico_path) as img:
            self.assertEqual(img.format, "ICO")

        # Check background.png
        bg_path = os.path.join(IMG_DIR, "background.png")
        with Image.open(bg_path) as img:
            self.assertEqual(img.format, "PNG")
            self.assertEqual(img.size, (1920, 1080))


class TestDockerfileThemeIntegration(unittest.TestCase):
    """Verifies Dockerfile instructions for theme deployment and core asset overlay."""

    def setUp(self):
        with open(DOCKERFILE, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_theme_copied_to_template_and_live(self):
        """Verifies Dockerfile copies themes/storix to template and live paths."""
        self.assertIn("COPY themes/storix /usr/src/nextcloud/themes/storix/", self.content)
        self.assertIn("cp -r /usr/src/nextcloud/themes/storix /var/www/html/themes/storix", self.content)

    def test_core_image_overlay_in_dockerfile(self):
        """Verifies Dockerfile overlays default Nextcloud core image assets with Storix branded assets."""
        self.assertIn("core/img/logo-header.png", self.content)
        self.assertIn("core/img/logo.png", self.content)
        self.assertIn("core/img/favicon.ico", self.content)
        self.assertIn("core/img/background.png", self.content)


class TestEntrypointScriptsTheming(unittest.TestCase):
    """Verifies entrypoint scripts synchronize themes and apply Nextcloud theming:config."""

    def test_storix_entrypoint_syncs_theme_and_config(self):
        """Verifies storix-entrypoint.sh synchronizes modular configs and Storix theme to live paths."""
        with open(ENTRYPOINT_SH, "r", encoding="utf-8") as f:
            content = f.read()

        # Modular config template syncing
        self.assertIn("Syncing modular config", content)
        self.assertIn("/usr/src/nextcloud/config/*.config.php", content)

        # Theme synchronization
        self.assertIn("/usr/src/nextcloud/themes/storix", content)
        self.assertIn("/var/www/html/themes/storix", content)

        # Core image asset synchronization
        self.assertIn("/var/www/html/core/img", content)
        self.assertIn("logo-header.png", content)

    def test_setup_ai_hook_theming_configuration(self):
        """Verifies 01-setup-ai.sh runs occ theming:config and sets theme in config.php."""
        with open(HOOK_SH, "r", encoding="utf-8") as f:
            content = f.read()

        # App enable
        self.assertIn("app:enable --force theming", content)

        # Configuration keys
        self.assertIn("theming:config name 'Storix'", content)
        self.assertIn("theming:config slogan 'Enterprise Cloud Storage Platform'", content)
        self.assertIn("theming:config url 'https://storix.io'", content)
        self.assertIn("theming:config color '#1652f0'", content)
        self.assertIn("theming:config primary_color '#1652f0'", content)
        self.assertIn("theming:config background_color '#071736'", content)

        # Logo and favicon configuration
        self.assertIn("theming:config logo", content)
        self.assertIn("theming:config logoheader", content)
        self.assertIn("theming:config favicon", content)
        self.assertIn("theming:config background", content)

        # System theme registration in config.php
        self.assertIn("config:system:set theme --value='storix'", content)

        # Cachebuster invalidation
        self.assertIn("config:app:set theming cachebuster", content)


if __name__ == "__main__":
    unittest.main()
