#!/usr/bin/env python3
"""
Automated Test Suite for FilestoreCloud Runtime Container
Tests Dockerfile architecture, PHP configurations, OPcache settings, and entrypoint hooks.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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
        """Verifies assistant and integration_openai are pre-baked in builder and copied."""
        self.assertIn("ASSISTANT_VERSION=", self.dockerfile_content)
        self.assertIn("OPENAI_INTEGRATION_VERSION=", self.dockerfile_content)
        self.assertIn("COPY --from=builder --chown=www-data:www-data /apps /var/www/html/custom_apps/", self.dockerfile_content)
        self.assertIn("COPY --from=builder --chown=www-data:www-data /apps /usr/src/nextcloud/custom_apps/", self.dockerfile_content)

    def test_configuration_copies(self):
        """Verifies modular config files are copied to both template and live paths."""
        self.assertIn("COPY config/opcache.ini /usr/local/etc/php/conf.d/opcache-recommended.ini", self.dockerfile_content)
        self.assertIn("COPY config/ai.config.php /usr/src/nextcloud/config/ai.config.php", self.dockerfile_content)
        self.assertIn("COPY config/nextcloud.config.php /usr/src/nextcloud/config/nextcloud.config.php", self.dockerfile_content)

    def test_entrypoint_hooks_installed_in_all_lifecycles(self):
        """Verifies 01-setup-ai.sh is registered in all 3 Docker entrypoint hook directories."""
        hooks = [
            "/docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh",
            "/docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh",
            "/docker-entrypoint-hooks.d/pre-installation/01-setup-ai.sh",
        ]
        for hook in hooks:
            self.assertIn(f"COPY hooks/01-setup-ai.sh {hook}", self.dockerfile_content)
            self.assertIn(f"chmod +x {hook}", self.dockerfile_content)

    def test_labels_and_healthcheck(self):
        """Verifies container labels and HTTP healthcheck directive."""
        self.assertRegex(self.dockerfile_content, r'LABEL version="[\d\.]+"')
        self.assertIn('LABEL maintainer="FilestoreCloud Engineering Team"', self.dockerfile_content)
        self.assertIn("HEALTHCHECK", self.dockerfile_content)
        self.assertIn("http://localhost/status.php", self.dockerfile_content)


class TestPHPConfigurations(unittest.TestCase):
    """Verifies Nextcloud and AI PHP configuration files."""

    def test_nextcloud_config_hardening(self):
        """Verifies nextcloud.config.php has reverse proxy, HSTS, APCu, and S3 vault bindings."""
        self.assertTrue(os.path.isfile(NEXTCLOUD_CONFIG_PATH))
        with open(NEXTCLOUD_CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # ALB Reverse Proxy settings
        self.assertIn("'overwriteprotocol' => 'https'", content)
        self.assertIn("'trusted_proxies'", content)
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
        self.assertGreaterEqual(int(self.config.get("opcache.memory_consumption", "0")), 128)
        self.assertGreaterEqual(int(self.config.get("opcache.interned_strings_buffer", "0")), 8)
        self.assertGreaterEqual(int(self.config.get("opcache.max_accelerated_files", "0")), 10000)

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

    def test_hook_execution_simulation(self):
        """Simulates hook execution in a sandbox environment with mocked occ."""
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
# Shift past options until -c
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

            # Run a modified version of hook pointing to temp directory
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


if __name__ == "__main__":
    unittest.main()
