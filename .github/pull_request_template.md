## 📌 Description / Context
<!-- Provide a clear summary of changes made to the Storix Runtime container or configurations. -->


## 🔗 Related Issues / Tickets
- Fixes #

---

## 📋 Type of Change
- [ ] 🐛 **Bug Fix** (Fix for PHP runtime, Apache MPM, hook failure, or container error)
- [ ] ✨ **New Feature** (New Nextcloud app pre-bundling, AI integration, theming enhancement)
- [ ] 💥 **Breaking Change** (Incompatible config change, base image upgrade, or entrypoint behavior change)
- [ ] 🛡️ **Security Hardening** (CVE mitigation, file permission hardening, Trivy scan fix)
- [ ] ⚡ **Performance Optimization** (OPcache tuning, Apache MPM worker configuration, SOCI indexing)
- [ ] 🔧 **Refactoring / Tooling** (Shell script cleanup, test suite modernization)
- [ ] 📖 **Documentation** (README, architecture scorecard, setup instructions)

---

## 📦 Runtime Components Affected
- [ ] `Dockerfile` (Multi-stage build, base image, layer caching)
- [ ] `config/opcache.ini` (PHP OPcache parameters)
- [ ] `config/storix-mpm.conf` (Apache Event/Prefork MPM worker tuning)
- [ ] `config/nextcloud.config.php` (Core Nextcloud settings, object store, memcache)
- [ ] `config/ai.config.php` (AI Assistant & LLM backend configuration)
- [ ] `hooks/` (Pre-install, post-install, or before-starting entrypoint hooks)
- [ ] `themes/storix/` (Custom theme, CSS styling, assets & branding)
- [ ] `storix-entrypoint.sh` (Container lifecycle orchestration wrapper)

---

## 🧪 Testing & Verification
- [ ] **Hadolint**: `hadolint Dockerfile` passed with zero errors
- [ ] **ShellCheck**: All shell scripts (`hooks/*.sh`, `storix-entrypoint.sh`) validated
- [ ] **Automated Test Suite**: `./tests/run_tests.sh` executed and passed 100%
- [ ] **Trivy Vulnerability Scan**: Zero High/Critical security vulnerabilities detected
- [ ] **Local Container Build**: Tested running locally via `docker build -t storix-runtime:test .`

---

## 🛡️ DevSecOps Checklist
- [ ] **No Secrets**: No API keys, admin passwords, or private tokens committed
- [ ] **Zero-NAT / Air-Gapped Safe**: Container downloads all apps at build time, zero runtime curl
- [ ] **File Permissions**: Files owned by `www-data:www-data` and executable scripts have `+x`
- [ ] **Conventional Commits**: Commit messages follow standard commit guidelines
