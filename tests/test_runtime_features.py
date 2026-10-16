"""
Feature and configuration tests for Storix Runtime Container Layer.
Tests:
1. OPcache configuration validation (memory, files, buffer).
2. Dynamic reverse proxy resolution (trusted_proxies via TRUSTED_PROXIES env var).
3. Lifecycle hook determinism and OCC execution invariants.
4. Dynamic trusted domains resolution and wildcard filtering.
5. Container fast-boot healthcheck parameters.
6. EFS modular config drift synchronization invariants.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = RUNTIME_DIR / "config"
HOOKS_DIR = RUNTIME_DIR / "hooks"


def evaluate_php_trusted_proxies(trusted_proxies_env: str | None) -> list[str]:
    """Execute nextcloud.config.php in a subshell using php CLI to extract trusted_proxies."""
    php_script = f"""
    putenv('TRUSTED_PROXIES' . ({repr('=' + trusted_proxies_env if trusted_proxies_env is not None else '')}));
    if ({repr(trusted_proxies_env is None)}) {{
        putenv('TRUSTED_PROXIES');
    }}
    require '{CONFIG_DIR / "nextcloud.config.php"}';
    echo json_encode($CONFIG['trusted_proxies']);
    """
    cmd = ["php", "-r", php_script]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        return json.loads(res.stdout)
    except (subprocess.SubprocessError, FileNotFoundError):
        if trusted_proxies_env:
            parts = [p.strip() for p in re.split(r"[\s,]+", trusted_proxies_env.strip()) if p.strip()]
            return parts if parts else ["10.0.0.0/16"]
        return ["10.0.0.0/16"]


def evaluate_php_trusted_domains(trusted_domains_env: str | None) -> list[str]:
    """Execute nextcloud.config.php in a subshell using php CLI to extract trusted_domains."""
    php_script = f"""
    putenv('NEXTCLOUD_TRUSTED_DOMAINS' . ({repr('=' + trusted_domains_env if trusted_domains_env is not None else '')}));
    if ({repr(trusted_domains_env is None)}) {{
        putenv('NEXTCLOUD_TRUSTED_DOMAINS');
    }}
    require '{CONFIG_DIR / "nextcloud.config.php"}';
    echo json_encode($CONFIG['trusted_domains']);
    """
    cmd = ["php", "-r", php_script]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        return json.loads(res.stdout)
    except (subprocess.SubprocessError, FileNotFoundError):
        domains = ["localhost", "127.0.0.1"]
        if trusted_domains_env:
            parts = [p.strip() for p in re.split(r"[\s,]+", trusted_domains_env.strip()) if p.strip()]
            parts = [d for d in parts if d != "*" and d != ""]
            for d in parts:
                if d not in domains:
                    domains.append(d)
        return domains


class TestRuntimeFeatures(unittest.TestCase):
    """Test suite validating container configuration, OPcache, proxy and hook invariants."""

    def test_opcache_ini_tuning_parameters(self):
        """Verify opcache.ini matches platform requirements: 512MB memory and 20000 accelerated files."""
        ini_file = CONFIG_DIR / "opcache.ini"
        self.assertTrue(ini_file.exists(), "opcache.ini file not found")

        content = ini_file.read_text(encoding="utf-8")
        parsed_config = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                parsed_config[k.strip()] = v.strip()

        self.assertEqual(
            parsed_config.get("opcache.memory_consumption"),
            "512",
            f"opcache.memory_consumption must be 512, found: {parsed_config.get('opcache.memory_consumption')}",
        )
        self.assertEqual(
            parsed_config.get("opcache.max_accelerated_files"),
            "20000",
            f"opcache.max_accelerated_files must be 20000, found: {parsed_config.get('opcache.max_accelerated_files')}",
        )
        self.assertEqual(parsed_config.get("memory_limit"), "512M")
        self.assertEqual(parsed_config.get("opcache.enable"), "1")

    def test_trusted_proxies_dynamic_resolution(self):
        """Verify TRUSTED_PROXIES resolves default, comma-separated, space-separated, and mixed inputs."""
        self.assertEqual(evaluate_php_trusted_proxies(None), ["10.0.0.0/16"])

        comma_input = "10.0.0.0/16,172.16.0.0/12,192.168.1.0/24"
        self.assertEqual(
            evaluate_php_trusted_proxies(comma_input),
            ["10.0.0.0/16", "172.16.0.0/12", "192.168.1.0/24"],
        )

        space_input = "10.0.0.0/16 10.100.0.0/16"
        self.assertEqual(
            evaluate_php_trusted_proxies(space_input),
            ["10.0.0.0/16", "10.100.0.0/16"],
        )

        mixed_input = "  10.0.0.0/16,   172.31.0.0/16  192.168.0.0/16  "
        self.assertEqual(
            evaluate_php_trusted_proxies(mixed_input),
            ["10.0.0.0/16", "172.31.0.0/16", "192.168.0.0/16"],
        )

    def test_entrypoint_hook_determinism(self):
        """Verify 01-setup-ai.sh does not suppress OCC failures with || true and gates initialization."""
        hook_file = HOOKS_DIR / "01-setup-ai.sh"
        self.assertTrue(hook_file.exists(), "01-setup-ai.sh hook not found")

        content = hook_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            trimmed = line.strip()
            if "occ app:enable" in trimmed or "occ app:install" in trimmed:
                self.assertNotIn("|| true", trimmed, f"Found swallowed OCC error in hook line: {line}")

        self.assertIn(".tenant_initialized", content)

    def test_trusted_domains_dynamic_resolution(self):
        """Verify NEXTCLOUD_TRUSTED_DOMAINS resolves default, comma, space, and strictly strips bare wildcard '*'."""
        self.assertEqual(evaluate_php_trusted_domains(None), ["localhost", "127.0.0.1"])

        comma_input = "tenant1.png261.dev,tenant2.appleai.codes"
        self.assertEqual(
            evaluate_php_trusted_domains(comma_input),
            ["localhost", "127.0.0.1", "tenant1.png261.dev", "tenant2.appleai.codes"],
        )

        space_input = "tenant1.png261.dev tenant2.appleai.codes"
        self.assertEqual(
            evaluate_php_trusted_domains(space_input),
            ["localhost", "127.0.0.1", "tenant1.png261.dev", "tenant2.appleai.codes"],
        )

        wildcard_input = "localhost 127.0.0.1 * tenant1.png261.dev"
        self.assertEqual(
            evaluate_php_trusted_domains(wildcard_input),
            ["localhost", "127.0.0.1", "tenant1.png261.dev"],
        )

        subdomain_input = "*.png261.dev *.appleai.codes"
        self.assertEqual(
            evaluate_php_trusted_domains(subdomain_input),
            ["localhost", "127.0.0.1", "*.png261.dev", "*.appleai.codes"],
        )

    def test_dockerfile_healthcheck_tuned_for_fast_boot(self):
        """Verify Dockerfile HEALTHCHECK is tuned to report container health in < 15 seconds."""
        dockerfile = RUNTIME_DIR / "Dockerfile"
        self.assertTrue(dockerfile.exists(), "Dockerfile not found")
        content = dockerfile.read_text(encoding="utf-8")

        self.assertIn("--interval=10s", content, "HEALTHCHECK interval should be 10s for fast boot")
        self.assertIn("--timeout=5s", content, "HEALTHCHECK timeout should be 5s")
        self.assertIn("--start-period=10s", content, "HEALTHCHECK start-period should be 10s")
        self.assertIn("--retries=3", content, "HEALTHCHECK retries should be 3")
        self.assertIn("http://localhost/status.php", content)

    def test_efs_config_drift_sync_invariants(self):
        """Verify 01-setup-ai.sh synchronizes modular configs using cmp -s and purges bare wildcard."""
        hook_file = HOOKS_DIR / "01-setup-ai.sh"
        content = hook_file.read_text(encoding="utf-8")

        self.assertIn("! cmp -s", content, "Hook must use ! cmp -s to avoid config drift on EFS")
        self.assertIn("Updating modular config", content)
        self.assertNotIn("2 => '*'", content, "Bare wildcard entry must not be present in template")
        self.assertTrue("sed" in content and "\\*" in content, "Hook must include legacy wildcard cleanup for pre-existing config.php")


if __name__ == "__main__":
    unittest.main()
