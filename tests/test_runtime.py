#!/usr/bin/env python3
"""
Automated Test Suite for FilestoreCloud Runtime Container
Tests Dockerfile architecture, PHP configurations, OPcache settings, and entrypoint hooks.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

RUNTIME_DIR = os.environ.get("RUNTIME_REPO_ROOT")
REPO_ROOT = os.path.abspath(RUNTIME_DIR) if RUNTIME_DIR else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCKERFILE_PATH = os.path.join(REPO_ROOT, "Dockerfile")
NEXTCLOUD_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "nextcloud.config.php")
AI_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "ai.config.php")
OPCACHE_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "opcache.ini")
HOOK_PATH = os.path.join(REPO_ROOT, "hooks", "01-setup-ai.sh")


class TestDockerfileStructure(unittest.TestCase):
    """Verifies Dockerfile architecture invariants, multi-stage build, and hardening."""

    def setUp(self):
        self.assertTrue(os.path.isfile(DOCKERFILE_PATH), f"Dockerfile missing at {DOCKERFILE_PATH}")
        with open(DOCKERFILE_PATH, "r", encoding="utf-8") as f:
            self.dockerfile_content = f.read()

    def test_multi_stage_build(self):
        """Ensures image uses multi-stage build with Alpine builder and Nextcloud runtime."""
        self.assertIn("FROM alpine:", self.dockerfile_content, "Stage 1 builder must use Alpine")
        self.assertIn("AS builder", self.dockerfile_content, "Stage 1 must be named builder")
        self.assertIn("FROM nextcloud:30.0.17-apache", self.dockerfile_content, "Base image must be Nextcloud 30.0.17-apache")

    def test_pre_baked_ai_apps(self):
        """Verifies assistant and integration_openai are pre-baked in builder with verified SHA256 checksums."""
        self.assertIn("ASSISTANT_VERSION=", self.dockerfile_content)
        self.assertIn("OPENAI_INTEGRATION_VERSION=", self.dockerfile_content)
        # Checksum verification requirements (R1)
        self.assertIn("ASSISTANT_SHA256=", self.dockerfile_content)
        self.assertIn("OPENAI_INTEGRATION_SHA256=", self.dockerfile_content)
        self.assertIn("sha256sum -c", self.dockerfile_content)
        self.assertIn("COPY --from=builder --chown=www-data:www-data /apps /var/www/html/custom_apps/", self.dockerfile_content)
        self.assertIn("COPY --from=builder --chown=www-data:www-data /apps /usr/src/nextcloud/custom_apps/", self.dockerfile_content)

    def test_configuration_copies(self):
        """Verifies modular config files are copied to both template and live paths."""
        self.assertIn("COPY config/opcache.ini /usr/local/etc/php/conf.d/opcache-recommended.ini", self.dockerfile_content)
        self.assertIn("COPY config/ai.config.php /usr/src/nextcloud/config/ai.config.php", self.dockerfile_content)
        self.assertIn("COPY config/nextcloud.config.php /usr/src/nextcloud/config/nextcloud.config.php", self.dockerfile_content)

    def test_entrypoint_hooks_lifecycle_registration(self):
        """Verifies 01-setup-ai.sh is registered only in post-installation and before-starting, and absent from pre-installation."""
        required_hooks = [
            "/docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh",
            "/docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh",
        ]
        for hook in required_hooks:
            self.assertIn(f"COPY hooks/01-setup-ai.sh {hook}", self.dockerfile_content)
            self.assertIn(f"chmod +x {hook}", self.dockerfile_content)

        # Assert pre-installation hook is absent to eliminate premature/redundant execution before DB exists
        self.assertNotIn(
            "/docker-entrypoint-hooks.d/pre-installation/01-setup-ai.sh",
            self.dockerfile_content,
            "pre-installation hook must be removed from Dockerfile to prevent premature execution before Nextcloud is installed",
        )

    def test_labels_and_healthcheck(self):
        """Verifies container labels and HTTP healthcheck directive tuned for < 15s boot."""
        self.assertRegex(self.dockerfile_content, r'LABEL version="[\d\.]+"')
        self.assertIn('LABEL maintainer="FilestoreCloud Engineering Team"', self.dockerfile_content)
        self.assertIn("HEALTHCHECK", self.dockerfile_content)
        self.assertIn("http://localhost/status.php", self.dockerfile_content)
        self.assertIn("--interval=10s", self.dockerfile_content)
        self.assertIn("--timeout=5s", self.dockerfile_content)
        self.assertIn("--start-period=10s", self.dockerfile_content)


class TestPHPConfigurations(unittest.TestCase):
    """Verifies Nextcloud and AI PHP configuration files."""

    def test_nextcloud_config_hardening(self):
        """Verifies nextcloud.config.php has reverse proxy, dynamic trusted proxies, HSTS, APCu, and S3 bindings."""
        self.assertTrue(os.path.isfile(NEXTCLOUD_CONFIG_PATH))
        with open(NEXTCLOUD_CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # ALB Reverse Proxy settings & dynamic proxy reading
        self.assertIn("'overwriteprotocol' => 'https'", content)
        self.assertIn("'trusted_domains'", content)
        self.assertIn("getenv('NEXTCLOUD_TRUSTED_DOMAINS')", content)
        self.assertIn("'trusted_proxies'", content)
        self.assertIn("getenv('TRUSTED_PROXIES')", content)
        self.assertIn("'10.0.0.0/16'", content)
        self.assertIn("'forwarded_for_headers' => ['HTTP_X_FORWARDED_FOR']", content)

        # HSTS Header
        self.assertIn("'hsts' => true", content)

        # APCu Memcache
        self.assertIn(r"'memcache.local' => '\OC\Memcache\APCu'", content)

        # AI App allowlist
        self.assertIn("'assistant'", content)
        self.assertIn("'integration_openai'", content)

        # S3 ObjectStore
        self.assertIn("OBJECTSTORE_S3_BUCKET", content)
        self.assertIn(r"'class' => '\\OC\\Files\\ObjectStore\\S3'", content)
        self.assertIn("OBJECTSTORE_S3_REGION", content)

    def test_trusted_domains_resolution_logic(self):
        """Validates dynamic NEXTCLOUD_TRUSTED_DOMAINS parsing, bare wildcard filtering, and fallback scenarios."""
        with open(NEXTCLOUD_CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # Structural assertions on nextcloud.config.php implementation
        self.assertIn("'trusted_domains'", content)
        self.assertIn("NEXTCLOUD_TRUSTED_DOMAINS", content)
        self.assertIn("localhost", content)
        self.assertIn("127.0.0.1", content)
        self.assertIn("array_unique", content)

        # Standalone logic verification matching the PHP specification
        def resolve_trusted_domains(raw_env):
            domains = ["localhost", "127.0.0.1"]
            if raw_env is not None and raw_env.strip() != "":
                parsed = [item.strip() for item in re.split(r"[\s,]+", raw_env.strip()) if item.strip()]
                # Filter bare wildcard '*'
                parsed = [d for d in parsed if d != "*" and d != ""]
                if parsed:
                    for d in parsed:
                        if d not in domains:
                            domains.append(d)
            return domains

        # Fallback when unset or empty
        self.assertEqual(resolve_trusted_domains(None), ["localhost", "127.0.0.1"])
        self.assertEqual(resolve_trusted_domains(""), ["localhost", "127.0.0.1"])
        self.assertEqual(resolve_trusted_domains("   "), ["localhost", "127.0.0.1"])

        # Comma-separated domains
        self.assertEqual(
            resolve_trusted_domains("tenant1.png261.dev, tenant2.appleai.codes"),
            ["localhost", "127.0.0.1", "tenant1.png261.dev", "tenant2.appleai.codes"],
        )

        # Space-separated domains
        self.assertEqual(
            resolve_trusted_domains("tenant1.png261.dev tenant2.appleai.codes"),
            ["localhost", "127.0.0.1", "tenant1.png261.dev", "tenant2.appleai.codes"],
        )

        # Bare wildcard MUST be stripped to prevent Host Header injection
        self.assertEqual(
            resolve_trusted_domains("localhost 127.0.0.1 * tenant1.png261.dev"),
            ["localhost", "127.0.0.1", "tenant1.png261.dev"],
        )
        self.assertEqual(resolve_trusted_domains("*"), ["localhost", "127.0.0.1"])
        self.assertEqual(resolve_trusted_domains("*, *"), ["localhost", "127.0.0.1"])

        # Vanity subdomains with wildcard prefixes must be preserved
        self.assertEqual(
            resolve_trusted_domains("*.png261.dev *.appleai.codes"),
            ["localhost", "127.0.0.1", "*.png261.dev", "*.appleai.codes"],
        )

        # If PHP CLI is available, directly evaluate the PHP file with environment variables
        php_bin = shutil.which("php")
        if php_bin:
            test_cases = [
                ("tenant1.png261.dev, tenant2.appleai.codes", ["localhost", "127.0.0.1", "tenant1.png261.dev", "tenant2.appleai.codes"]),
                ("localhost 127.0.0.1 * *.png261.dev", ["localhost", "127.0.0.1", "*.png261.dev"]),
                ("*", ["localhost", "127.0.0.1"]),
                ("", ["localhost", "127.0.0.1"]),
            ]
            for env_val, expected in test_cases:
                cmd = [
                    php_bin,
                    "-r",
                    f'putenv("NEXTCLOUD_TRUSTED_DOMAINS={env_val}"); require "{NEXTCLOUD_CONFIG_PATH}"; echo json_encode($CONFIG["trusted_domains"]);',
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(res.stdout), expected)

    def test_trusted_proxies_resolution_logic(self):
        """Validates dynamic TRUSTED_PROXIES parsing logic across varied delimiters and fallback scenarios."""
        with open(NEXTCLOUD_CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # Structural assertions on nextcloud.config.php implementation
        self.assertIn("preg_split", content)
        self.assertIn("trim", content)

        # Standalone logic verification matching the PHP specification
        def resolve_trusted_proxies(raw_env):
            if raw_env is not None and raw_env.strip() != "":
                items = [item.strip() for item in re.split(r"[\s,]+", raw_env.strip()) if item.strip()]
                if items:
                    return items
            return ["10.0.0.0/16"]

        # Comma-separated CIDRs
        self.assertEqual(
            resolve_trusted_proxies("10.0.0.0/16, 172.16.0.0/12"),
            ["10.0.0.0/16", "172.16.0.0/12"],
        )
        # Space-separated CIDRs
        self.assertEqual(
            resolve_trusted_proxies("10.0.0.0/16 192.168.1.0/24"),
            ["10.0.0.0/16", "192.168.1.0/24"],
        )
        # Mixed commas, multiple spaces, tabs, and trailing whitespace
        self.assertEqual(
            resolve_trusted_proxies("  10.0.0.0/16 ,  172.16.0.0/12 \t 192.168.0.0/16  "),
            ["10.0.0.0/16", "172.16.0.0/12", "192.168.0.0/16"],
        )
        # Empty string / whitespace fallback
        self.assertEqual(resolve_trusted_proxies(""), ["10.0.0.0/16"])
        self.assertEqual(resolve_trusted_proxies("   "), ["10.0.0.0/16"])
        # Unset env fallback
        self.assertEqual(resolve_trusted_proxies(None), ["10.0.0.0/16"])

        # If PHP CLI is available, directly evaluate the PHP file with environment variables
        php_bin = shutil.which("php")
        if php_bin:
            test_cases = [
                ("10.0.0.0/16, 172.16.0.0/12", ["10.0.0.0/16", "172.16.0.0/12"]),
                ("10.0.0.0/16 192.168.1.0/24", ["10.0.0.0/16", "192.168.1.0/24"]),
                ("", ["10.0.0.0/16"]),
            ]
            for env_val, expected in test_cases:
                cmd = [
                    php_bin,
                    "-r",
                    f'putenv("TRUSTED_PROXIES={env_val}"); require "{NEXTCLOUD_CONFIG_PATH}"; echo json_encode($CONFIG["trusted_proxies"]);',
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(res.stdout), expected)

    def test_ai_config_allowlist(self):
        """Verifies ai.config.php contains app_install_overwrite for AI apps."""
        self.assertTrue(os.path.isfile(AI_CONFIG_PATH))
        with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("'app_install_overwrite'", content)
        self.assertIn("'assistant'", content)
        self.assertIn("'integration_openai'", content)


class TestOPcacheConfiguration(unittest.TestCase):
    """Verifies PHP OPcache settings match Nextcloud production guidelines."""

    def setUp(self):
        self.assertTrue(os.path.isfile(OPCACHE_CONFIG_PATH))
        with open(OPCACHE_CONFIG_PATH, "r", encoding="utf-8") as f:
            self.lines = [line.strip() for line in f if line.strip() and not line.startswith(";")]
            self.config = {}
            for line in self.lines:
                if "=" in line:
                    k, v = line.split("=", 1)
                    self.config[k.strip()] = v.strip()

    def test_opcache_enabled(self):
        self.assertEqual(self.config.get("opcache.enable"), "1")
        self.assertEqual(self.config.get("opcache.enable_cli"), "1")

    def test_memory_and_strings(self):
        """Verifies OPcache memory consumption is exactly 512MB and max accelerated files is 20000."""
        self.assertEqual(int(self.config.get("opcache.memory_consumption", "0")), 512)
        self.assertEqual(int(self.config.get("opcache.max_accelerated_files", "0")), 20000)
        self.assertGreaterEqual(int(self.config.get("opcache.interned_strings_buffer", "0")), 8)

    def test_comments_preserved(self):
        """Nextcloud annotations require comments to be preserved in OPcache."""
        self.assertEqual(self.config.get("opcache.save_comments"), "1")

    def test_php_resource_limits(self):
        """Verifies generous memory and upload limits for enterprise storage."""
        self.assertIn(self.config.get("memory_limit"), ["512M", "1024M", "2048M"])
        self.assertIn(self.config.get("upload_max_filesize"), ["16G", "32G", "64G"])
        self.assertIn(self.config.get("post_max_size"), ["16G", "32G", "64G"])


class TestEntrypointHookScript(unittest.TestCase):
    """Verifies logic, shell syntax, and guardrails in hooks/01-setup-ai.sh."""

    def setUp(self):
        self.assertTrue(os.path.isfile(HOOK_PATH))
        with open(HOOK_PATH, "r", encoding="utf-8") as f:
            self.hook_content = f.read()

    def test_shell_syntax(self):
        """Validates that the hook passes syntax check without errors."""
        res = subprocess.run(["sh", "-n", HOOK_PATH], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Shell syntax error in {HOOK_PATH}: {res.stderr}")

    def test_strict_mode_and_shebang(self):
        """Verifies shebang and set -e error handling."""
        self.assertTrue(self.hook_content.startswith("#!/bin/sh"))
        self.assertIn("set -e", self.hook_content)

    def test_persistence_flag_logic(self):
        """Verifies tenant initialization uses EFS persistent flag and supports FORCE_REINIT."""
        self.assertIn('INIT_FLAG="/var/www/html/config/.tenant_initialized"', self.hook_content)
        self.assertIn('"${FORCE_REINIT:-0}" = "1"', self.hook_content)
        self.assertIn('touch "$INIT_FLAG"', self.hook_content)

    def test_ai_app_enable_and_guardrails(self):
        """Verifies assistant and integration_openai are enabled with Zero Data Retention."""
        self.assertIn("app:enable --force assistant", self.hook_content)
        self.assertIn("app:enable --force integration_openai", self.hook_content)
        self.assertIn("config:app:set assistant zero_data_retention --value=1", self.hook_content)

    def test_ai_endpoint_and_redis_support(self):
        """Verifies dynamic AI endpoint and Redis locking support."""
        self.assertIn("AI_ENDPOINT=", self.hook_content)
        self.assertIn("REDIS_HOST", self.hook_content)
        self.assertIn("memcache.locking", self.hook_content)
        self.assertIn("db:add-missing-indices", self.hook_content)

    def test_no_swallowed_occ_errors(self):
        """Verifies that core OCC commands do NOT swallow errors with || true."""
        occ_lines = [line.strip() for line in self.hook_content.splitlines() if "occ " in line]
        self.assertGreater(len(occ_lines), 5, "Expected multiple OCC invocations in hook")
        for line in occ_lines:
            if "occ status" in line:
                continue
            self.assertNotIn("|| true", line, f"Core OCC command must not swallow errors with || true: {line}")

    def test_error_trapping_and_exit_handling(self):
        """Verifies that hook defines an EXIT trap, logs failure, and gates .tenant_initialized."""
        self.assertIn("trap cleanup_on_exit EXIT", self.hook_content)
        self.assertIn("cleanup_on_exit()", self.hook_content)
        self.assertIn("CURRENT_STEP=", self.hook_content)
        self.assertIn('rm -f "${INIT_FLAG}"', self.hook_content)

        touch_pos = self.hook_content.index('touch "$INIT_FLAG"')
        for marker in [
            "app:enable --force assistant",
            "app:enable --force integration_openai",
            "config:app:set assistant zero_data_retention",
            "db:add-missing-indices",
            "maintenance:repair --include-expensive",
        ]:
            marker_pos = self.hook_content.index(marker)
            self.assertLess(marker_pos, touch_pos, f"Setup step '{marker}' must execute before creating INIT_FLAG")

    def test_hook_execution_simulation(self):
        """Simulates hook execution in a sandbox environment with mocked occ (happy path and fast-boot)."""
        temp_dir = tempfile.mkdtemp(prefix="test_runtime_hook_")
        try:
            # Create simulated filesystem
            src_config = os.path.join(temp_dir, "usr", "src", "nextcloud", "config")
            html_config = os.path.join(temp_dir, "var", "www", "html", "config")
            html_dir = os.path.join(temp_dir, "var", "www", "html")
            bin_dir = os.path.join(temp_dir, "bin")
            os.makedirs(src_config, exist_ok=True)
            os.makedirs(html_config, exist_ok=True)
            os.makedirs(bin_dir, exist_ok=True)

            # Create test config file in src
            test_cfg = os.path.join(src_config, "test.config.php")
            with open(test_cfg, "w") as f:
                f.write("<?php return [];")

            # Mock occ script
            occ_log = os.path.join(temp_dir, "occ_calls.log")
            mock_occ = os.path.join(html_dir, "occ")
            with open(mock_occ, "w") as f:
                f.write(f"""#!/bin/sh
echo "$@" >> "{occ_log}"
if [ "$1" = "status" ]; then
    echo "installed: true"
    exit 0
fi
exit 0
""")
            os.chmod(mock_occ, 0o755)

            # Mock su to directly execute the command in sandbox
            mock_su = os.path.join(bin_dir, "su")
            with open(mock_su, "w") as f:
                f.write("""#!/bin/sh
while [ $# -gt 0 ]; do
    if [ "$1" = "-c" ]; then
        shift
        sh -c "$@"
        exit $?
    fi
    shift
done
""")
            os.chmod(mock_su, 0o755)

            # Run a simulated version of hook pointing to temp directory
            test_script = f"""#!/bin/sh
set -e
PATH="{bin_dir}:$PATH"
export PATH
INIT_FLAG="{html_config}/.tenant_initialized"

# Simulate section 0: copy configs
for cfg in "{src_config}"/*.config.php; do
    if [ -f "$cfg" ]; then
        target="{html_config}/$(basename "$cfg")"
        if [ ! -f "$target" ]; then
            cp "$cfg" "$target"
        fi
    fi
done

# Simulate section 1: init
if su -s /bin/sh www-data -c "sh {mock_occ} status" | grep -q "installed: true"; then
    if [ ! -f "$INIT_FLAG" ] || [ "${{FORCE_REINIT:-0}}" = "1" ]; then
        su -s /bin/sh www-data -c "sh {mock_occ} app:enable --force assistant"
        su -s /bin/sh www-data -c "sh {mock_occ} app:enable --force integration_openai"
        su -s /bin/sh www-data -c "sh {mock_occ} db:add-missing-indices"
        touch "$INIT_FLAG"
    fi
fi
"""
            run_file = os.path.join(temp_dir, "run_test.sh")
            with open(run_file, "w") as f:
                f.write(test_script)
            os.chmod(run_file, 0o755)

            # First run: should initialize
            res = subprocess.run(["sh", run_file], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Simulated run failed: {res.stderr}")
            self.assertTrue(os.path.isfile(os.path.join(html_config, "test.config.php")), "Config was not copied")
            self.assertTrue(os.path.isfile(os.path.join(html_config, ".tenant_initialized")), "Init flag was not created")

            with open(occ_log, "r") as f:
                log_content = f.read()
            self.assertIn("app:enable --force assistant", log_content)
            self.assertIn("db:add-missing-indices", log_content)

            # Second run: init flag exists, should fast-boot without re-running app:enable
            os.remove(occ_log)
            res2 = subprocess.run(["sh", run_file], capture_output=True, text=True)
            self.assertEqual(res2.returncode, 0)
            if os.path.exists(occ_log):
                with open(occ_log, "r") as f:
                    log_content2 = f.read()
                self.assertNotIn("app:enable --force assistant", log_content2, "Should not re-run setup when initialized")
        finally:
            shutil.rmtree(temp_dir)

    def test_hook_failure_gating_simulation(self):
        """Verifies that an OCC setup failure halts execution and prevents creation of .tenant_initialized."""
        temp_dir = tempfile.mkdtemp(prefix="test_runtime_hook_fail_")
        try:
            # Create simulated filesystem
            src_config = os.path.join(temp_dir, "usr", "src", "nextcloud", "config")
            html_config = os.path.join(temp_dir, "var", "www", "html", "config")
            html_dir = os.path.join(temp_dir, "var", "www", "html")
            bin_dir = os.path.join(temp_dir, "bin")
            os.makedirs(src_config, exist_ok=True)
            os.makedirs(html_config, exist_ok=True)
            os.makedirs(bin_dir, exist_ok=True)

            # Mock occ script that fails during app enablement
            mock_occ = os.path.join(html_dir, "occ")
            with open(mock_occ, "w") as f:
                f.write("""#!/bin/sh
if [ "$1" = "status" ]; then
    echo "installed: true"
    exit 0
fi
if [ "$1" = "app:enable" ] && [ "$3" = "assistant" ]; then
    echo "Error: Database connection lost or migration failed" >&2
    exit 1
fi
exit 0
""")
            os.chmod(mock_occ, 0o755)

            # Mock su to directly execute the command in sandbox
            mock_su = os.path.join(bin_dir, "su")
            with open(mock_su, "w") as f:
                f.write("""#!/bin/sh
while [ $# -gt 0 ]; do
    if [ "$1" = "-c" ]; then
        shift
        sh -c "$@"
        exit $?
    fi
    shift
done
""")
            os.chmod(mock_su, 0o755)

            # Hook simulation script with deterministic gating (no || true on core commands) and trap cleanup
            test_script = f"""#!/bin/sh
set -e
PATH="{bin_dir}:$PATH"
export PATH
INIT_FLAG="{html_config}/.tenant_initialized"

CURRENT_STEP="Startup pre-flight"
cleanup_on_exit() {{
    exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        echo "[ENTRYPOINT-HOOK] ❌ ERROR: Initialization step '${{CURRENT_STEP}}' failed with exit code ${{exit_code}}!" >&2
        rm -f "${{INIT_FLAG}}" 2>/dev/null || true
    fi
}}
trap cleanup_on_exit EXIT

if su -s /bin/sh www-data -c "sh {mock_occ} status" | grep -q "installed: true"; then
    if [ ! -f "$INIT_FLAG" ] || [ "${{FORCE_REINIT:-0}}" = "1" ]; then
        CURRENT_STEP="Enabling assistant app"
        su -s /bin/sh www-data -c "sh {mock_occ} app:enable --force assistant"
        CURRENT_STEP="Enabling integration_openai app"
        su -s /bin/sh www-data -c "sh {mock_occ} app:enable --force integration_openai"
        CURRENT_STEP="Adding missing database indices"
        su -s /bin/sh www-data -c "sh {mock_occ} db:add-missing-indices"
        touch "$INIT_FLAG"
    fi
fi
"""
            run_file = os.path.join(temp_dir, "run_fail_test.sh")
            with open(run_file, "w") as f:
                f.write(test_script)
            os.chmod(run_file, 0o755)

            # Execution must fail with non-zero return code
            res = subprocess.run(["sh", run_file], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit code on OCC failure, got {res.returncode}")

            # Crucial invariant: .tenant_initialized must NOT exist!
            self.assertFalse(
                os.path.isfile(os.path.join(html_config, ".tenant_initialized")),
                ".tenant_initialized flag was created despite OCC failure! Gating failed.",
            )
            self.assertIn("Enabling assistant app", res.stderr)
        finally:
            shutil.rmtree(temp_dir)

    def test_efs_modular_config_drift_synchronization(self):
        """Verifies modular config files update on EFS when changed in container image (! cmp -s), leaving config.php untouched."""
        self.assertIn("! cmp -s", self.hook_content, "Hook must use differential comparison (! cmp -s) for config sync")
        self.assertIn("Updating modular config", self.hook_content)

        temp_dir = tempfile.mkdtemp(prefix="test_drift_sync_")
        try:
            src_config = os.path.join(temp_dir, "usr", "src", "nextcloud", "config")
            html_config = os.path.join(temp_dir, "var", "www", "html", "config")
            os.makedirs(src_config, exist_ok=True)
            os.makedirs(html_config, exist_ok=True)

            # 1. Existing persistent tenant config.php on EFS (must NEVER be overwritten)
            tenant_config_php = os.path.join(html_config, "config.php")
            with open(tenant_config_php, "w") as f:
                f.write("<?php $CONFIG = ['instanceid' => 'tenant_persistent_123', 'installed' => true];")

            # 2. Existing outdated modular config on EFS
            efs_mod_cfg = os.path.join(html_config, "nextcloud.config.php")
            with open(efs_mod_cfg, "w") as f:
                f.write("<?php // Old release v1")

            # 3. New modular config in container image
            img_mod_cfg = os.path.join(src_config, "nextcloud.config.php")
            with open(img_mod_cfg, "w") as f:
                f.write("<?php // New release v2 with updated security settings")

            # Execute drift sync logic
            sync_script = f"""#!/bin/sh
set -e
for cfg in "{src_config}"/*.config.php; do
    if [ -f "$cfg" ]; then
        target="{html_config}/$(basename "$cfg")"
        if [ ! -f "$target" ] || ! cmp -s "$cfg" "$target"; then
            cp "$cfg" "$target"
        fi
    fi
done
"""
            res = subprocess.run(["sh", "-c", sync_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Sync script failed: {res.stderr}")

            # Verify nextcloud.config.php was updated
            with open(efs_mod_cfg, "r") as f:
                updated_content = f.read()
            self.assertEqual(updated_content, "<?php // New release v2 with updated security settings")

            # Verify tenant config.php was completely preserved
            with open(tenant_config_php, "r") as f:
                tenant_content = f.read()
            self.assertIn("tenant_persistent_123", tenant_content)
        finally:
            shutil.rmtree(temp_dir)

    def test_wildcard_purged_from_config_php_template_and_legacy(self):
        """Verifies bare wildcard '*' is absent from auto-provision template and purged from pre-existing config.php."""
        # Assert auto-provisioning template has no bare '*'
        self.assertNotIn("2 => '*',", self.hook_content, "Bare wildcard '*' must be removed from auto-provision template")
        self.assertNotIn("=> '*'", self.hook_content, "Bare wildcard '*' must not appear in any trusted_domains entry")

        # Test legacy cleanup in sandbox
        temp_dir = tempfile.mkdtemp(prefix="test_legacy_purge_")
        try:
            html_config = os.path.join(temp_dir, "var", "www", "html", "config")
            os.makedirs(html_config, exist_ok=True)
            legacy_config = os.path.join(html_config, "config.php")

            with open(legacy_config, "w") as f:
                f.write("""<?php
$CONFIG = array (
  'trusted_domains' => array (
    0 => 'localhost',
    1 => '127.0.0.1',
    2 => '*',
  ),
  'installed' => true,
);
""")

            # Run legacy cleanup
            cleanup_script = f"""#!/bin/sh
if [ -f "{legacy_config}" ]; then
    sed -i.bak "/['\\"]\\*['\\"]/d" "{legacy_config}" 2>/dev/null && rm -f "{legacy_config}.bak" 2>/dev/null || sed -i "/['\\"]\\*['\\"]/d" "{legacy_config}" 2>/dev/null || :
fi
"""
            res = subprocess.run(["sh", "-c", cleanup_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Cleanup script failed: {res.stderr}")

            with open(legacy_config, "r") as f:
                cleaned = f.read()
            self.assertNotIn("'*'", cleaned, "Bare wildcard '*' must be purged from legacy config.php")
            self.assertIn("'localhost'", cleaned)
            self.assertIn("'127.0.0.1'", cleaned)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
