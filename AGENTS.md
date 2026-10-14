# AGENTS.md

> Universal AI Agent Instructions & Operating Guidelines for FilestoreCloud Runtime Container.
> Stewarded under the open [AGENTS.md](https://agents.md) standard (Linux Foundation / AAIF).

---

## 1. Project Overview & Architecture

Production-hardened Golden Container Image providing the Nextcloud 30 enterprise application runtime and Amazon Bedrock AI proxy sidecar integration for AWS ECS Fargate.

### Key Architecture Boundaries

- **Zero-NAT Baking Strategy:** Container images pre-bake all AI applications (Nextcloud Assistant `v4.0.0` and OpenAI / Bedrock integration `v5.0.0`) during image build. No runtime downloads or internet access required at boot.
- **Pre-seeded Configuration:** `config/nextcloud.config.php` enforces reverse proxy headers for ALB, strict transport security (HSTS), APCu memcache, and S3 Vault primary storage bindings.
- **Initialization Hooks:** Native Docker entrypoint hooks in `hooks/01-setup-ai.sh` auto-enable AI apps and bridge them to the LiteLLM Bedrock Bridge sidecar (`http://127.0.0.1:4000/v1`).
- **Multi-Repo Federation:**
  - `FilestoreCloud/runtime` (This repo): Dockerfile, Apache configs, entrypoint hooks.
  - `FilestoreCloud/infra`: CloudFormation IaC deploying ECS task definitions with image tags.
  - `FilestoreCloud/console`: Super Admin web portal.

### Directory Layout

```
.
├── Dockerfile                  # Multi-layer Dockerfile extending nextcloud:30.0.17-apache
├── config/
│   ├── nextcloud.config.php    # Hardened system config (ALB proxy, APCu, HSTS, S3 Vault)
│   └── ai.config.php           # AI apps overwrite allowlist
├── hooks/
│   └── 01-setup-ai.sh          # Container initialization hook for AI apps & LiteLLM linking
├── .github/
│   └── workflows/
│       ├── docker.yml          # Automated CI/CD build & push to Amazon ECR
│       └── branch-guard.yml    # Enforces PR into main only originates from dev
├── .devsecops/                 # AWS Labs DevSecOps configurations (Ferret Scan)
├── .githook/                   # Git hooks (Conventional Commits, branch protection)
├── .pre-commit-config.yaml     # DevSecOps linters (Hadolint, Shellcheck, Ferret Scan)
└── .hadolint.yaml              # Dockerfile linting configuration
```

---

## 2. Essential Commands

### Testing & Verification

```bash
# Run automated test suite (linting, configuration validation, hook simulation)
./tests/run_tests.sh

# Lint Dockerfile
hadolint Dockerfile --config .hadolint.yaml

# Run complete AWS Labs DevSecOps pre-commit checks
pre-commit run --all-files

# Build container image locally
docker build -t filestore-runtime:latest .
```

### Local Container Run

```bash
docker run -d -p 8080:80 \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_DB=nextcloud \
  -e POSTGRES_USER=nextcloud \
  -e POSTGRES_PASSWORD=testpassword \
  filestore-runtime:latest
```

---

## 3. Branching Strategy & Boundaries ("Never" Rules)

1. **NEVER Commit Directly to `main`:**
   - `main` is strictly protected. The pre-commit and pre-push hooks will reject direct commits or pushes.
   - Always commit to `dev` or feature branches (`feat/...`, `fix/...`). Merging to `main` is only allowed via Pull Request from `dev`.
2. **MANDATORY Conventional Commits:**
   - Validated by `.githook/commit-msg`.
   - Allowed prefixes: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`, `chore:`.
3. **NEVER Hardcode Secrets or Credentials:**
   - Validated by AWS Labs Ferret Scan and pre-commit checks.
4. **Never Use Unpinned `:latest` Image in Production Deployments:**
   - Production ECS Task Definitions must always point to an immutable SemVer release tag (`vX.Y.Z`) or commit SHA tag.

---

## 4. Definition of Done (Verification Checklist)

Before concluding any implementation or opening a PR:

1. [ ] **Pre-commit:** `pre-commit run --all-files` passes cleanly with zero errors.
2. [ ] **Tests:** `./tests/run_tests.sh` passes cleanly with all tests green.
3. [ ] **Dockerfile:** `hadolint Dockerfile --config .hadolint.yaml` passes cleanly.
4. [ ] **Build:** Local `docker build` succeeds without warnings.
5. [ ] **Git:** Staged changes committed to `dev` with Conventional Commit message.
