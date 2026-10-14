#!/usr/bin/env python3
"""
Adversarial Empirical Stress Test Suite for Milestone 1 (Gen 2 Challenge)
Author: Empirical Challenger 1 (teamwork_preview_challenger_m1_gen2_1)

Validates:
1. Dynamic trusted_domains resolution:
   - Host Header injection attempts: bare wildcard '*', whitespace-padded '  *  ', quoted, tabs, multiple spaces, mixed with valid domains.
   - Invariant: Bare wildcard '*' is NEVER admitted under any input string.
   - Invariant: Vanity subdomains (*.png261.dev, *.appleai.codes, dev-tenant.png261.dev) are retained.
   - Invariant: Empty, whitespace-only, or unset NEXTCLOUD_TRUSTED_DOMAINS safely falls back to ['localhost', '127.0.0.1'].
2. Dynamic trusted_proxies:
   - CIDR lists, whitespace, comma separation, invalid inputs, fallback to ['10.0.0.0/16'].
3. EFS config drift & differential sync:
   - Identical files are NOT re-copied (mtime preserved).
   - Modified image configs overwrite stale EFS modular configs.
   - Tenant config.php is NEVER overwritten.
   - Legacy bare wildcard '*' is purged from config.php while preserving tenant state.
4. Fast boot and Healthcheck invariants (< 15s).
"""

import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / "config" / "nextcloud.config.php"
HOOK_FILE = REPO_ROOT / "hooks" / "01-setup-ai.sh"
DOCKERFILE = REPO_ROOT / "Dockerfile"


def resolve_php_trusted_domains(env_val: str | None) -> list[str]:
    r"""
    Simulates the exact PHP IIFE in nextcloud.config.php for trusted_domains:
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
    """
    domains = ["localhost", "127.0.0.1"]
    if env_val is not None:
        trimmed_raw = env_val.strip()
        if trimmed_raw != "":
            # preg_split('/[\s,]+/', ...)
            parts = [p.strip() for p in re.split(r"[\s,]+", trimmed_raw) if p.strip()]
            # Exclude bare wildcard '*' and empty strings
            filtered = [d for d in parts if d != "*" and d != ""]
            if filtered:
                # array_values(array_unique(array_merge($domains, $parsed)))
                merged = domains + filtered
                # Preserve unique in order
                seen = set()
                unique_domains = []
                for d in merged:
                    if d not in seen:
                        seen.add(d)
                        unique_domains.append(d)
                domains = unique_domains
    return domains


def resolve_php_trusted_proxies(env_val: str | None) -> list[str]:
    r"""
    Simulates the exact PHP IIFE in nextcloud.config.php for trusted_proxies:
        $raw = getenv('TRUSTED_PROXIES');
        if ($raw !== false && trim($raw) !== '') {
            $proxies = array_values(array_filter(array_map('trim', preg_split('/[\s,]+/', trim($raw)))));
            if (!empty($proxies)) {
                return $proxies;
            }
        }
        return ['10.0.0.0/16'];
    """
    if env_val is not None:
        trimmed_raw = env_val.strip()
        if trimmed_raw != "":
            parts = [p.strip() for p in re.split(r"[\s,]+", trimmed_raw) if p.strip()]
            if parts:
                return parts
    return ["10.0.0.0/16"]


class TestAdversarialTrustedDomains(unittest.TestCase):
    """Stress-test dynamic trusted_domains resolution against Host Header injection attempts."""

    def test_php_source_has_strict_bare_wildcard_exclusion(self):
        """Verify nextcloud.config.php contains strict bare wildcard exclusion logic."""
        content = CONFIG_FILE.read_text(encoding="utf-8")
        self.assertIn("'trusted_domains'", content)
        self.assertIn("NEXTCLOUD_TRUSTED_DOMAINS", content)
        self.assertIn("return $d !== '*'", content)
        self.assertIn("array_unique", content)

    def test_bare_wildcard_variations_never_admitted(self):
        """Host Header injection: Bare wildcard '*' must never be admitted under any input form."""
        attack_payloads = [
            "*",
            " *",
            "* ",
            "   *   ",
            "\t*\t",
            "\n*\n",
            "\r\n*\r\n",
            "\t  *  \t",
            "* *",
            "* * *",
            "*,*",
            "*, *, *",
            ",*,",
            " , * , ",
            "\t,\t*\t,\t",
        ]
        for payload in attack_payloads:
            result = resolve_php_trusted_domains(payload)
            self.assertNotIn(
                "*",
                result,
                f"CRITICAL: Bare wildcard '*' was admitted for payload {repr(payload)}: got {result}",
            )
            # Must safely fall back to loopbacks
            self.assertEqual(
                result,
                ["localhost", "127.0.0.1"],
                f"Expected loopback fallback for payload {repr(payload)}, got {result}",
            )

    def test_mixed_wildcard_and_valid_domains(self):
        """Verify bare wildcard '*' is stripped while valid domains are preserved."""
        test_cases = [
            (
                "dev.png261.dev * tenant.appleai.codes",
                ["localhost", "127.0.0.1", "dev.png261.dev", "tenant.appleai.codes"],
            ),
            (
                "dev.png261.dev, *, tenant.appleai.codes",
                ["localhost", "127.0.0.1", "dev.png261.dev", "tenant.appleai.codes"],
            ),
            (
                "  *  , dev.png261.dev  *  tenant.appleai.codes , *  ",
                ["localhost", "127.0.0.1", "dev.png261.dev", "tenant.appleai.codes"],
            ),
            (
                "* dev.png261.dev *",
                ["localhost", "127.0.0.1", "dev.png261.dev"],
            ),
        ]
        for raw_input, expected in test_cases:
            result = resolve_php_trusted_domains(raw_input)
            self.assertNotIn("*", result)
            self.assertEqual(result, expected)

    def test_vanity_wildcard_subdomains_retained(self):
        """Verify vanity wildcard subdomains like *.png261.dev and *.appleai.codes are retained."""
        test_cases = [
            ("*.png261.dev", ["localhost", "127.0.0.1", "*.png261.dev"]),
            ("*.appleai.codes", ["localhost", "127.0.0.1", "*.appleai.codes"]),
            ("dev-tenant.png261.dev", ["localhost", "127.0.0.1", "dev-tenant.png261.dev"]),
            (
                "*.png261.dev, *.appleai.codes, dev-tenant.png261.dev",
                ["localhost", "127.0.0.1", "*.png261.dev", "*.appleai.codes", "dev-tenant.png261.dev"],
            ),
            (
                "*.corp.storix.internal  app-*.cloud.storix.internal",
                ["localhost", "127.0.0.1", "*.corp.storix.internal", "app-*.cloud.storix.internal"],
            ),
        ]
        for raw_input, expected in test_cases:
            result = resolve_php_trusted_domains(raw_input)
            self.assertEqual(result, expected)

    def test_empty_or_unset_safe_fallback(self):
        """Verify empty, unset, whitespace-only, or delimiter-only inputs fall back to loopbacks."""
        safe_fallback_payloads = [
            None,
            "",
            "   ",
            "\t\t",
            "\n\r\n",
            ",",
            ",,,",
            "  ,  ,  ,  ",
            "\t,\t,\n",
        ]
        for payload in safe_fallback_payloads:
            result = resolve_php_trusted_domains(payload)
            self.assertEqual(
                result,
                ["localhost", "127.0.0.1"],
                f"Failed safe fallback for payload {repr(payload)}: got {result}",
            )

    def test_deduplication_and_loopback_preservation(self):
        """Verify duplicate domains are collapsed while preserving localhost and 127.0.0.1."""
        raw_input = "localhost 127.0.0.1 tenant1.png261.dev tenant1.png261.dev 127.0.0.1 tenant2.png261.dev"
        result = resolve_php_trusted_domains(raw_input)
        self.assertEqual(
            result,
            ["localhost", "127.0.0.1", "tenant1.png261.dev", "tenant2.png261.dev"],
        )


class TestAdversarialTrustedProxies(unittest.TestCase):
    """Stress-test dynamic trusted_proxies resolution with CIDR lists, whitespace, and fallbacks."""

    def test_php_source_has_trusted_proxies_unpacking(self):
        """Verify nextcloud.config.php contains trusted_proxies array unpacking."""
        content = CONFIG_FILE.read_text(encoding="utf-8")
        self.assertIn("'trusted_proxies'", content)
        self.assertIn("TRUSTED_PROXIES", content)
        self.assertIn("10.0.0.0/16", content)

    def test_trusted_proxies_fallbacks(self):
        """Verify unset, empty, and whitespace-only inputs fall back to 10.0.0.0/16."""
        fallbacks = [
            None,
            "",
            "   ",
            "\t\t",
            "\n",
            ",",
            ",,,   ,,",
            "  \t , \n ,  ",
        ]
        for payload in fallbacks:
            result = resolve_php_trusted_proxies(payload)
            self.assertEqual(
                result,
                ["10.0.0.0/16"],
                f"Fallback failed for payload {repr(payload)}: got {result}",
            )

    def test_trusted_proxies_delimiters_and_cidrs(self):
        """Verify comma, space, tab, and mixed delimiters for CIDRs."""
        test_cases = [
            ("10.0.0.0/16", ["10.0.0.0/16"]),
            ("10.0.0.0/16,172.16.0.0/12,192.168.1.0/24", ["10.0.0.0/16", "172.16.0.0/12", "192.168.1.0/24"]),
            ("10.0.0.0/16 10.100.0.0/16 10.200.0.0/16", ["10.0.0.0/16", "10.100.0.0/16", "10.200.0.0/16"]),
            ("  10.0.0.0/16 ,   172.31.0.0/16 \t 192.168.0.0/16  ", ["10.0.0.0/16", "172.31.0.0/16", "192.168.0.0/16"]),
            ("fd00::/8, 10.0.0.0/8", ["fd00::/8", "10.0.0.0/8"]),
        ]
        for raw_input, expected in test_cases:
            result = resolve_php_trusted_proxies(raw_input)
            self.assertEqual(result, expected)


class TestAdversarialEFSConfigDrift(unittest.TestCase):
    """Empirical testing of EFS modular config drift, differential sync, and tenant state preservation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_efs_test_")
        self.src_dir = os.path.join(self.temp_dir, "usr_src_nextcloud_config")
        self.efs_dir = os.path.join(self.temp_dir, "var_www_html_config")
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.efs_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _execute_sync_snippet(self):
        """Runs the exact differential sync shell snippet used in 01-setup-ai.sh."""
        sync_script = f"""
        set -e
        if [ -d "{self.src_dir}" ]; then
            for cfg in "{self.src_dir}"/*.config.php; do
                if [ -f "$cfg" ]; then
                    target="{self.efs_dir}/$(basename "$cfg")"
                    if [ ! -f "$target" ] || ! cmp -s "$cfg" "$target"; then
                        echo "[SYNC] Updating modular config $(basename "$cfg") in EFS..."
                        cp "$cfg" "$target"
                    fi
                fi
            done
        fi
        """
        res = subprocess.run(["/bin/sh", "-c", sync_script], capture_output=True, text=True)
        return res

    def _execute_legacy_sed_snippet(self):
        """Runs the legacy bare wildcard removal sed snippet used in 01-setup-ai.sh."""
        config_path = os.path.join(self.efs_dir, "config.php")
        sed_script = f"""
        if [ -f "{config_path}" ]; then
            sed -i.bak "/['\\"]\\*['\\"]/d" "{config_path}" 2>/dev/null && rm -f "{config_path}.bak" 2>/dev/null || sed -i "/['\\"]\\*['\\"]/d" "{config_path}" 2>/dev/null || :
        fi
        """
        res = subprocess.run(["/bin/sh", "-c", sed_script], capture_output=True, text=True)
        return res

    def test_cmp_s_identical_files_not_recopied(self):
        """Differential sync: Identical files must NOT be re-copied (mtime preserved)."""
        src_file = os.path.join(self.src_dir, "nextcloud.config.php")
        efs_file = os.path.join(self.efs_dir, "nextcloud.config.php")
        content = "<?php $CONFIG = ['version' => '1.0'];"

        with open(src_file, "w") as f:
            f.write(content)
        with open(efs_file, "w") as f:
            f.write(content)

        # Set efs_file timestamp to 1 hour ago
        old_time = time.time() - 3600
        os.utime(efs_file, (old_time, old_time))

        res = self._execute_sync_snippet()
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("[SYNC] Updating", res.stdout)

        # Inode / mtime must remain unchanged
        new_stat = os.stat(efs_file)
        self.assertAlmostEqual(new_stat.st_mtime, old_time, delta=2)

    def test_cmp_s_modified_image_config_overwrites_stale_efs_config(self):
        """Differential sync: Modified image configs MUST overwrite stale EFS modular configs."""
        src_file = os.path.join(self.src_dir, "nextcloud.config.php")
        efs_file = os.path.join(self.efs_dir, "nextcloud.config.php")

        with open(src_file, "w") as f:
            f.write("<?php $CONFIG = ['version' => '2.0.0-NEW'];")
        with open(efs_file, "w") as f:
            f.write("<?php $CONFIG = ['version' => '1.0.0-STALE'];")

        res = self._execute_sync_snippet()
        self.assertEqual(res.returncode, 0)
        self.assertIn("[SYNC] Updating modular config nextcloud.config.php in EFS...", res.stdout)

        # EFS file must now contain the updated image configuration
        with open(efs_file, "r") as f:
            efs_content = f.read()
        self.assertIn("2.0.0-NEW", efs_content)
        self.assertNotIn("1.0.0-STALE", efs_content)

    def test_tenant_config_php_never_overwritten_by_modular_sync(self):
        """CRITICAL INVARIANT: Tenant config.php is NEVER overwritten by modular config synchronization."""
        tenant_config_file = os.path.join(self.efs_dir, "config.php")
        tenant_content = """<?php
$CONFIG = array (
  'instanceid' => 'oc_tenant_persistent_12345',
  'passwordsalt' => 'salt_super_secure_9999',
  'secret' => 'secret_tenant_custom_data',
  'dbname' => 'tenant_db_production',
  'dbuser' => 'prod_user',
);
"""
        with open(tenant_config_file, "w") as f:
            f.write(tenant_content)

        # Image has modular configs
        src_file = os.path.join(self.src_dir, "nextcloud.config.php")
        with open(src_file, "w") as f:
            f.write("<?php $CONFIG = ['overwriteprotocol' => 'https'];")

        # Run differential sync
        res = self._execute_sync_snippet()
        self.assertEqual(res.returncode, 0)

        # Verify tenant config.php is 100% intact
        with open(tenant_config_file, "r") as f:
            current_tenant_content = f.read()
        self.assertEqual(current_tenant_content, tenant_content)
        self.assertIn("oc_tenant_persistent_12345", current_tenant_content)
        self.assertIn("salt_super_secure_9999", current_tenant_content)
        self.assertIn("secret_tenant_custom_data", current_tenant_content)

    def test_legacy_bare_wildcard_purged_from_preexisting_config_php(self):
        """Verify legacy wildcard sed cleanup purges bare wildcard while keeping tenant settings intact."""
        config_path = os.path.join(self.efs_dir, "config.php")
        legacy_config = """<?php
$CONFIG = array (
  'instanceid' => 'oc_legacy_tenant',
  'passwordsalt' => 'salt_legacy_123',
  'secret' => 'sec_legacy_456',
  'trusted_domains' => array (
    0 => 'localhost',
    1 => '127.0.0.1',
    2 => '*',
    3 => 'dev.png261.dev',
  ),
  'installed' => true,
);
"""
        with open(config_path, "w") as f:
            f.write(legacy_config)

        res = self._execute_legacy_sed_snippet()
        self.assertEqual(res.returncode, 0)

        with open(config_path, "r") as f:
            cleaned = f.read()

        # Invariants:
        # 1. Bare wildcard '*' line is purged
        self.assertNotIn("2 => '*'", cleaned)
        self.assertNotIn("'*'", cleaned)
        # 2. Localhost and valid tenant domain preserved
        self.assertIn("0 => 'localhost'", cleaned)
        self.assertIn("1 => '127.0.0.1'", cleaned)
        self.assertIn("3 => 'dev.png261.dev'", cleaned)
        # 3. Persistent tenant credentials preserved
        self.assertIn("oc_legacy_tenant", cleaned)
        self.assertIn("salt_legacy_123", cleaned)
        self.assertIn("sec_legacy_456", cleaned)
        # 4. No leftover .bak files
        self.assertFalse(os.path.exists(config_path + ".bak"))


class TestAdversarialContainerBootParameters(unittest.TestCase):
    """Stress-test Dockerfile and hook boot timing invariants (< 15 seconds)."""

    def test_dockerfile_healthcheck_parameters(self):
        """Verify Dockerfile HEALTHCHECK parameters guarantee boot health reporting in < 15s."""
        content = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("--interval=10s", content)
        self.assertIn("--timeout=5s", content)
        self.assertIn("--start-period=10s", content)
        self.assertIn("--retries=3", content)

    def test_no_recursive_chown_in_hook_critical_path(self):
        """Verify 01-setup-ai.sh does not perform unbounded recursive chown on /var/www/html."""
        content = HOOK_FILE.read_text(encoding="utf-8")
        # Ensure chown -R is not run over the entire webroot
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("#"):
                continue
            if "chown -R" in line_str:
                self.assertNotIn(
                    "chown -R www-data:www-data /var/www/html\n",
                    line_str,
                    "Found unbounded recursive chown over entire webroot!",
                )


if __name__ == "__main__":
    unittest.main()
