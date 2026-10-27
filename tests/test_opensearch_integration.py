"""Unit tests for Storix OpenSearch and FullTextSearch Integration."""

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

RUNTIME_ROOT = Path(__file__).parent.parent


class TestOpenSearchIntegration(unittest.TestCase):
    """Verifies OpenSearch modular configs, Docker hooks, and app allowlists."""

    def test_search_config_php_structure(self):
        """Ensure search.config.php exists and has proper variables and structure."""
        config_path = RUNTIME_ROOT / "config" / "search.config.php"
        self.assertTrue(config_path.exists(), "search.config.php must exist")

        content = config_path.read_text(encoding="utf-8")
        self.assertIn("OPENSEARCH_HOST", content)
        self.assertIn("TIKA_HOST", content)
        self.assertIn("fulltextsearch", content)
        self.assertIn("files_fulltextsearch", content)
        self.assertIn("fulltextsearch_elasticsearch", content)
        self.assertIn("tenant_", content)

        # If php CLI is present, also lint it
        if shutil.which("php"):
            res = subprocess.run(
                ["php", "-l", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"PHP lint failed: {res.stderr}")

    def test_search_config_index_generation_logic(self):
        """Simulate index sanitization logic for multi-tenant isolation."""
        def generate_index_name(tenant_id: str) -> str:
            sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", tenant_id)
            return f"tenant_{sanitized}"

        self.assertEqual(generate_index_name("acme-corp"), "tenant_acme-corp")
        self.assertEqual(generate_index_name("marvel.studios"), "tenant_marvel_studios")
        self.assertEqual(generate_index_name("org@123"), "tenant_org_123")

    def test_dockerfile_contains_fulltextsearch_apps(self):
        """Verify Dockerfile downloads and verifies all 3 FullTextSearch apps."""
        dockerfile = (RUNTIME_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ENV FULLTEXTSEARCH_VERSION=", dockerfile)
        self.assertIn("ENV FILES_FULLTEXTSEARCH_VERSION=", dockerfile)
        self.assertIn("ENV FULLTEXTSEARCH_ELASTICSEARCH_VERSION=", dockerfile)

        self.assertIn("fulltextsearch.tar.gz", dockerfile)
        self.assertIn("files_fulltextsearch.tar.gz", dockerfile)
        self.assertIn("fulltextsearch_elasticsearch.tar.gz", dockerfile)

        # Check hook and config copy
        self.assertIn("02-setup-opensearch.sh", dockerfile)
        self.assertIn("search.config.php", dockerfile)

    def test_nextcloud_config_app_allowlist(self):
        """Verify nextcloud.config.php allows fulltextsearch apps."""
        config_path = RUNTIME_ROOT / "config" / "nextcloud.config.php"
        content = config_path.read_text(encoding="utf-8")

        self.assertIn("'fulltextsearch'", content)
        self.assertIn("'files_fulltextsearch'", content)
        self.assertIn("'fulltextsearch_elasticsearch'", content)

    def test_opensearch_hook_syntax(self):
        """Verify 02-setup-opensearch.sh shell syntax and idempotency logic."""
        hook_path = RUNTIME_ROOT / "hooks" / "02-setup-opensearch.sh"
        self.assertTrue(hook_path.exists())

        res = subprocess.run(
            ["sh", "-n", str(hook_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Shell check failed: {res.stderr}")

        content = hook_path.read_text(encoding="utf-8")
        self.assertIn(".opensearch_configured", content)
        self.assertIn("fulltextsearch:configure", content)
        self.assertIn("fulltextsearch_elasticsearch:configure", content)
        self.assertIn("files_fulltextsearch:configure", content)


if __name__ == "__main__":
    unittest.main()
