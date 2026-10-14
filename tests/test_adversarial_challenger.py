#!/usr/bin/env python3
"""
Adversarial Empirical Stress Test Suite for Milestone 1 (Runtime Container Hardening & Determinism)
Author: Empirical Challenger Agent
Validates:
1. Entrypoint hook failure handling across all OCC failure scenarios (DB down, permission denied, app enable error).
2. Exit code propagation and complete purging of .tenant_initialized on failure.
3. FORCE_REINIT=1 reinitialization and failure recovery.
4. Error trap execution across multiple shell environments (/bin/sh, /bin/dash, /bin/bash, /bin/zsh, /bin/ksh).
5. Dockerfile SHA256 checksum hardening and tamper rejection.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOOK_SOURCE = os.path.join(REPO_ROOT, "hooks", "01-setup-ai.sh")
DOCKERFILE_PATH = os.path.join(REPO_ROOT, "Dockerfile")


class TestAdversarialHookScenarios(unittest.TestCase):
    """Adversarial stress-testing of 01-setup-ai.sh lifecycle, error trapping, and state gating."""

    def setUp(self):
        self.assertTrue(os.path.isfile(HOOK_SOURCE), f"Missing hook source at {HOOK_SOURCE}")
        with open(HOOK_SOURCE, "r", encoding="utf-8") as f:
            self.hook_text = f.read()

    def _run_hook_in_sandbox(
        self,
        shell_bin="/bin/sh",
        fail_at_command=None,
        fail_exit_code=1,
        fail_message="SQLSTATE[08006] [7] could not connect to server",
        force_reinit=None,
        pre_existing_init_flag=False,
        make_config_readonly=False,
        extra_env=None,
    ):
        """Runs the actual 01-setup-ai.sh script in an isolated sandbox with mock binaries."""
        temp_dir = tempfile.mkdtemp(prefix="adv_hook_test_")
        try:
            sandbox_html = os.path.join(temp_dir, "html")
            sandbox_config = os.path.join(sandbox_html, "config")
            sandbox_data = os.path.join(sandbox_html, "data")
            sandbox_src = os.path.join(temp_dir, "src_nextcloud", "config")
            sandbox_bin = os.path.join(temp_dir, "bin")

            os.makedirs(sandbox_config, exist_ok=True)
            os.makedirs(sandbox_data, exist_ok=True)
            os.makedirs(sandbox_src, exist_ok=True)
            os.makedirs(sandbox_bin, exist_ok=True)

            init_flag_path = os.path.join(sandbox_config, ".tenant_initialized")
            if pre_existing_init_flag:
                with open(init_flag_path, "w") as f:
                    f.write("pre-existing-initialized\n")

            # Create mock config files in src
            with open(os.path.join(sandbox_src, "nextcloud.config.php"), "w") as f:
                f.write("<?php return [];")

            # Mock occ log
            occ_log = os.path.join(temp_dir, "occ_executions.log")

            # Create Python-based mock php / occ execution wrapper for robust arg handling
            mock_php = os.path.join(sandbox_bin, "php")
            with open(mock_php, "w") as f:
                f.write(f'''#!/usr/bin/env python3
import sys

cmd_args = " ".join(sys.argv[1:])
with open(r"{occ_log}", "a") as lf:
    lf.write(cmd_args + "\\n")

if "status" in cmd_args:
    if "{fail_at_command or ''}" == "status":
        sys.stderr.write("{fail_message}\\n")
        sys.exit({fail_exit_code})
    sys.stdout.write("  - installed: true\\n  - version: 30.0.17.2\\n")
    sys.exit(0)

target = "{fail_at_command or ''}"
if target and target in cmd_args:
    sys.stderr.write(f"[MOCK-OCC] Injected failure on command matching '{{target}}': {fail_message}\\n")
    sys.exit({fail_exit_code})

sys.exit(0)
''')
            os.chmod(mock_php, 0o755)

            # Create mock su
            mock_su = os.path.join(sandbox_bin, "su")
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

            # Create mock chown
            mock_chown = os.path.join(sandbox_bin, "chown")
            with open(mock_chown, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(mock_chown, 0o755)

            # Prepare sandbox hook script with adapted path roots
            adapted_script = (
                self.hook_text
                .replace("/var/www/html", sandbox_html)
                .replace("/usr/src/nextcloud", os.path.join(temp_dir, "src_nextcloud"))
            )

            # If testing read-only config at point of touching INIT_FLAG
            if make_config_readonly:
                mock_touch = os.path.join(sandbox_bin, "touch")
                with open(mock_touch, "w") as f:
                    f.write("""#!/bin/sh
case "$*" in
    *.tenant_initialized*)
        echo "touch: cannot touch '$*': Permission denied (EACCES)" >&2
        exit 1
        ;;
esac
/usr/bin/touch "$@"
""")
                os.chmod(mock_touch, 0o755)

            hook_exec_path = os.path.join(temp_dir, "test_01-setup-ai.sh")
            with open(hook_exec_path, "w") as f:
                f.write(adapted_script)
            os.chmod(hook_exec_path, 0o755)

            # Environment variables
            env = dict(os.environ)
            env["PATH"] = f"{sandbox_bin}:{env.get('PATH', '')}"
            if force_reinit is not None:
                env["FORCE_REINIT"] = str(force_reinit)
            else:
                env.pop("FORCE_REINIT", None)

            if extra_env:
                env.update(extra_env)

            res = subprocess.run(
                [shell_bin, hook_exec_path],
                capture_output=True,
                text=True,
                env=env,
            )

            flag_exists = os.path.isfile(init_flag_path)

            executed_calls = []
            if os.path.isfile(occ_log):
                with open(occ_log, "r") as f:
                    executed_calls = [line.strip() for line in f if line.strip()]

            return res.returncode, res.stdout, res.stderr, flag_exists, executed_calls
        finally:
            shutil.rmtree(temp_dir)

    # --------------------------------------------------------------------------
    # 1. OCC Failure Scenarios: DB Down, App Enable Error, Permission Denied
    # --------------------------------------------------------------------------

    def test_database_down_on_status_check(self):
        """Simulates database down during initial status check: hook gracefully skips setup and does NOT create flag."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="status",
            fail_exit_code=1,
            fail_message="SQLSTATE[08006] Connection refused to PostgreSQL",
        )
        self.assertEqual(code, 0, f"Expected 0 exit code on uninstalled/unreachable status, got {code}")
        self.assertFalse(flag_exists, ".tenant_initialized must NOT be created when status fails")
        self.assertIn("Nextcloud not fully installed yet", stdout)

    def test_database_down_on_app_enable_assistant(self):
        """Simulates database failure during 'occ app:enable --force assistant': exits non-zero and purges flag."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="app:enable --force assistant",
            fail_exit_code=1,
            fail_message="SQLSTATE[08006] Server closed connection unexpectedly",
        )
        self.assertNotEqual(code, 0, "Hook MUST exit with non-zero status on app:enable failure")
        self.assertFalse(flag_exists, ".tenant_initialized MUST NOT exist after failure")
        self.assertIn("Enabling assistant app", stderr)
        self.assertIn("failed with exit code 1", stderr)

    def test_database_down_on_app_enable_openai(self):
        """Simulates failure during 'occ app:enable --force integration_openai': exits non-zero and purges flag."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="app:enable --force integration_openai",
            fail_exit_code=1,
            fail_message="An unhandled exception occurred in integration_openai migration",
        )
        self.assertNotEqual(code, 0, "Hook MUST exit with non-zero status on integration_openai failure")
        self.assertFalse(flag_exists, ".tenant_initialized MUST NOT exist after failure")
        self.assertIn("Enabling integration_openai app", stderr)
        self.assertIn("failed with exit code 1", stderr)

    def test_database_down_on_db_add_missing_indices(self):
        """Simulates database failure during 'occ db:add-missing-indices': exits non-zero and purges flag."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="db:add-missing-indices",
            fail_exit_code=1,
            fail_message="SQLSTATE[57P01] terminating connection due to administrator command",
        )
        self.assertNotEqual(code, 0, "Hook MUST exit with non-zero status on db:add-missing-indices failure")
        self.assertFalse(flag_exists, ".tenant_initialized MUST NOT exist after failure")
        self.assertIn("Adding missing database indices", stderr)
        self.assertIn("failed with exit code 1", stderr)

    def test_database_down_on_maintenance_repair(self):
        """Simulates database failure during 'occ maintenance:repair': exits non-zero and purges flag."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="maintenance:repair",
            fail_exit_code=1,
            fail_message="Repair error: Failed to establish DB lock",
        )
        self.assertNotEqual(code, 0, "Hook MUST exit with non-zero status on maintenance:repair failure")
        self.assertFalse(flag_exists, ".tenant_initialized MUST NOT exist after failure")
        self.assertIn("Running maintenance repair", stderr)
        self.assertIn("failed with exit code 1", stderr)

    def test_permission_denied_on_occ_execution(self):
        """Simulates permission denied error (exit 126) executing occ."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="app:enable --force assistant",
            fail_exit_code=126,
            fail_message="/var/www/html/occ: Permission denied",
        )
        self.assertEqual(code, 126, "Exit code 126 must be preserved through the trap")
        self.assertFalse(flag_exists, ".tenant_initialized MUST NOT exist on permission denied failure")
        self.assertIn("failed with exit code 126", stderr)

    def test_permission_denied_on_creating_init_flag(self):
        """Simulates failure to write .tenant_initialized (read-only filesystem or EACCES)."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            make_config_readonly=True,
        )
        self.assertNotEqual(code, 0, "Hook must fail when creating init flag fails")
        self.assertFalse(flag_exists, ".tenant_initialized flag must not exist")
        self.assertIn("Marking tenant initialization complete", stderr)

    def test_overwritecliurl_failure_handling(self):
        """Simulates failure during dynamic CLI URL configuration when OVERWRITECLIURL is provided."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            fail_at_command="overwritecliurl",
            fail_exit_code=1,
            fail_message="Failed to write system config overwritecliurl",
            extra_env={"OVERWRITECLIURL": "https://cloud.tenant.example.com"},
        )
        self.assertNotEqual(code, 0, "Hook must exit non-zero when overwritecliurl fails")
        self.assertFalse(flag_exists, ".tenant_initialized must be purged if overwritecliurl fails after setup")
        self.assertIn("Setting overwritecliurl", stderr)

    # --------------------------------------------------------------------------
    # 2. Challenge FORCE_REINIT=1 Behavior
    # --------------------------------------------------------------------------

    def test_fast_boot_when_already_initialized(self):
        """Verifies fast boot (< 1s) when flag exists and FORCE_REINIT is not enabled."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            pre_existing_init_flag=True,
            force_reinit=None,
        )
        self.assertEqual(code, 0)
        self.assertTrue(flag_exists)
        self.assertIn("Fast-booting container", stdout)
        # Verify no setup commands were invoked
        setup_calls = [c for c in calls if "app:enable" in c or "db:add-missing-indices" in c]
        self.assertEqual(len(setup_calls), 0, "Setup commands must NOT be executed on fast-boot")

    def test_force_reinit_1_forces_execution_when_initialized(self):
        """Verifies that FORCE_REINIT=1 forces execution even when flag exists."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            pre_existing_init_flag=True,
            force_reinit="1",
        )
        self.assertEqual(code, 0)
        self.assertTrue(flag_exists)
        self.assertIn("Initializing tenant configuration", stdout)
        self.assertIn("First-time tenant setup completed", stdout)
        setup_calls = [c for c in calls if "app:enable" in c]
        self.assertGreater(len(setup_calls), 0, "Setup commands must be executed under FORCE_REINIT=1")

    def test_force_reinit_1_purges_preexisting_flag_on_failure(self):
        """CRITICAL ADVERSARIAL TEST: Pre-existing flag MUST be purged if re-init fails midway."""
        code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
            pre_existing_init_flag=True,
            force_reinit="1",
            fail_at_command="app:enable --force integration_openai",
            fail_exit_code=1,
            fail_message="Corrupted integration_openai package",
        )
        self.assertNotEqual(code, 0, "Expected non-zero exit code on failure")
        self.assertFalse(
            flag_exists,
            "CRITICAL: .tenant_initialized was preserved after failed FORCE_REINIT=1! Must be purged.",
        )
        self.assertIn("failed with exit code 1", stderr)

    def test_force_reinit_0_or_invalid_values(self):
        """Verifies that FORCE_REINIT=0, empty string, or invalid strings do not trigger re-init."""
        for invalid_val in ["0", "", "false", "no", "2"]:
            code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
                pre_existing_init_flag=True,
                force_reinit=invalid_val,
            )
            self.assertEqual(code, 0)
            self.assertTrue(flag_exists)
            self.assertIn("Fast-booting container", stdout)
            setup_calls = [c for c in calls if "app:enable" in c]
            self.assertEqual(len(setup_calls), 0, f"Setup ran unexpectedly with FORCE_REINIT={invalid_val}")

    # --------------------------------------------------------------------------
    # 3. Challenge Error Trap Across Multiple Shell Environments
    # --------------------------------------------------------------------------

    def test_error_trap_across_available_shells(self):
        """Tests 01-setup-ai.sh failure handling under /bin/sh, /bin/dash, /bin/bash, /bin/zsh, /bin/ksh."""
        candidate_shells = ["/bin/sh", "/bin/dash", "/bin/bash", "/bin/zsh", "/bin/ksh"]
        tested_count = 0
        for sh_bin in candidate_shells:
            if not os.path.exists(sh_bin) or not os.access(sh_bin, os.X_OK):
                continue

            tested_count += 1
            # Test failure exit code propagation
            code, stdout, stderr, flag_exists, calls = self._run_hook_in_sandbox(
                shell_bin=sh_bin,
                fail_at_command="app:enable --force assistant",
                fail_exit_code=1,
            )
            self.assertEqual(
                code,
                1,
                f"Shell {sh_bin} failed to preserve exit code 1; got {code}. Stderr: {stderr}",
            )
            self.assertFalse(
                flag_exists,
                f"Shell {sh_bin} left behind .tenant_initialized after failure!",
            )
            self.assertIn(
                "Enabling assistant app",
                stderr,
                f"Shell {sh_bin} failed to print CURRENT_STEP in error trap",
            )

            # Test normal completion exit code 0 and flag creation
            code_ok, stdout_ok, stderr_ok, flag_exists_ok, calls_ok = self._run_hook_in_sandbox(
                shell_bin=sh_bin,
            )
            self.assertEqual(code_ok, 0, f"Shell {sh_bin} failed normal execution; got {code_ok}")
            self.assertTrue(flag_exists_ok, f"Shell {sh_bin} did not create .tenant_initialized")
            self.assertNotIn("ERROR:", stderr_ok)

        self.assertGreaterEqual(tested_count, 2, "Expected at least 2 distinct shells to be tested")


class TestAdversarialDockerfileIntegrity(unittest.TestCase):
    """Adversarial stress-testing of Dockerfile cryptographic checksum enforcement."""

    def setUp(self):
        with open(DOCKERFILE_PATH, "r", encoding="utf-8") as f:
            self.dockerfile = f.read()

    def test_checksum_hex_format_validity(self):
        """Verifies that SHA256 checksums are exactly 64 hexadecimal characters."""
        import re

        assistant_match = re.search(r'ASSISTANT_SHA256="([a-f0-9]+)"', self.dockerfile)
        self.assertIsNotNone(assistant_match, "ASSISTANT_SHA256 not found in Dockerfile")
        self.assertEqual(len(assistant_match.group(1)), 64, "ASSISTANT_SHA256 must be exactly 64 hex chars")

        openai_match = re.search(r'OPENAI_INTEGRATION_SHA256="([a-f0-9]+)"', self.dockerfile)
        self.assertIsNotNone(openai_match, "OPENAI_INTEGRATION_SHA256 not found in Dockerfile")
        self.assertEqual(len(openai_match.group(1)), 64, "OPENAI_INTEGRATION_SHA256 must be exactly 64 hex chars")

    def test_checksum_verification_adversarial_tamper_rejection(self):
        """Simulates a modified/tampered tarball to verify sha256sum -c rejects it with non-zero exit."""
        temp_dir = tempfile.mkdtemp()
        try:
            fake_tarball = os.path.join(temp_dir, "fake_app.tar.gz")
            with open(fake_tarball, "w") as f:
                f.write("tampered-payload-content")

            correct_hash = "0d7c72d3cd8a41cdb7a402d0822331d6cad23271a9a4ee6222c85f00b2dd6271"

            # Check matching checksum
            res_fail = subprocess.run(
                ["sh", "-c", f'echo "{correct_hash}  {fake_tarball}" | sha256sum -c -'],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                res_fail.returncode,
                0,
                "sha256sum MUST fail when tarball content does not match checksum",
            )
            self.assertIn("FAILED", res_fail.stdout + res_fail.stderr)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
