# FilestoreCloud Runtime Image

Production-hardened enterprise container runtime with pre-baked AI assistant and Amazon Bedrock integration for AWS ECS Fargate.

---

## 1. Overview & Golden Image Baking Strategy

In a **Zero-NAT** cloud environment, containers cannot freely download external dependencies or apps from the internet at runtime without internet gateways or NAT. Downloading apps at container boot also significantly degrades container startup and scaling times.

To solve this, this repository implements a **Golden Image Baking** strategy:
* **Pre-Baked AI Apps:** The Dockerfile downloads and installs Nextcloud Assistant (`v4.0.0`) and OpenAI / Bedrock Integration (`v5.0.0`) into `/var/www/html/custom_apps/` and `/usr/src/nextcloud/custom_apps/` during image build time.
* **Production Hardened Config:** Pre-seeded configuration [`config/nextcloud.config.php`](config/nextcloud.config.php) configures reverse proxy headers for ALB, strict transport security (HSTS), APCu local memcache, and S3 Primary ObjectStore bindings.
* **Smart Entrypoint Hook:** The hook script [`hooks/01-setup-ai.sh`](hooks/01-setup-ai.sh) verifies `occ status` (`installed: true`) before activating apps and connecting them to the LiteLLM Bedrock Bridge sidecar (`http://127.0.0.1:4000/v1`).

---

## 2. Directory Structure

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
│       └── docker.yml          # Automated CI/CD build & push to Amazon ECR
└── .hadolint.yaml              # Dockerfile linting configuration
```

---

## 3. Automated CI/CD Image Build (GitHub Actions)

Container builds are automated via [`.github/workflows/docker.yml`](.github/workflows/docker.yml):
* **Triggers:** Push to `main`, git tags (`v*`), or on-demand via `workflow_dispatch`.
* **Builder:** Docker Buildx targeting `linux/amd64` (AWS Fargate compatible).
* **ECR Destination:** Amazon ECR repository `filestore-runtime` with automated vulnerability scanning on push.
* **Authentication:** AWS IAM OpenID Connect (OIDC) federation without static credentials.

---

## 4. Local Build & Test

To build and test the image locally:

```bash
docker build -t filestore-runtime:latest .

# Run locally with PostgreSQL container or mock database
docker run -d -p 8080:80 \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_DB=nextcloud \
  -e POSTGRES_USER=nextcloud \
  -e POSTGRES_PASSWORD=testpassword \
  filestore-runtime:latest
```
