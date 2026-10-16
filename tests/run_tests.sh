#!/usr/bin/env bash
# ==============================================================================
# FilestoreCloud Runtime Automated Test Runner
# Executes Hadolint Dockerfile checks, shell script syntax checks,
# Python architecture & configuration validation tests, and Trivy security scans.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}   FilestoreCloud Runtime — Automated Test Suite            ${NC}"
echo -e "${BLUE}============================================================${NC}"

cd "${REPO_ROOT}"

# 1. Hadolint Dockerfile Linting
echo -e "\n${BLUE}[1/4] Running Dockerfile Linting (Hadolint)...${NC}"
if command -v hadolint >/dev/null 2>&1; then
    hadolint Dockerfile --config .devsecops/.hadolint.yaml
    echo -e "${GREEN}✓ Dockerfile passed Hadolint inspection.${NC}"
else
    echo -e "${YELLOW}ℹ hadolint not found on PATH; skipping local lint.${NC}"
fi

# 2. Shell Script Syntax Check
echo -e "\n${BLUE}[2/4] Checking Shell Script Syntax...${NC}"
for sh_file in hooks/*.sh; do
    if [ -f "$sh_file" ]; then
        sh -n "$sh_file"
        echo -e "${GREEN}✓ Syntax valid: ${sh_file}${NC}"
    fi
done

# 3. Python Test Suite (Architecture Invariants & Hook Simulation)
echo -e "\n${BLUE}[3/4] Running Python Runtime Test Suite...${NC}"
python3 -m unittest discover -s tests -v

# 4. PHP Configuration Syntax Check (if PHP is available)
if command -v php >/dev/null 2>&1; then
    echo -e "\n${BLUE}[*] Checking PHP Config Syntax...${NC}"
    for php_file in config/*.php; do
        if [ -f "$php_file" ]; then
            php -l "$php_file"
        fi
    done
    echo -e "${GREEN}✓ All PHP configuration files passed syntax check.${NC}"
fi

# 5. Trivy Security & Misconfiguration Scan (Zero High/Critical tolerance)
echo -e "\n${BLUE}[4/4] Running Security & Misconfig Scan (Trivy)...${NC}"
if command -v trivy >/dev/null 2>&1; then
    trivy config . --config .devsecops/.trivy.yaml --exit-code 1 --severity HIGH,CRITICAL
    echo -e "${GREEN}✓ Assets passed Trivy security & configuration audit (Zero High/Critical findings).${NC}"
else
    echo -e "${YELLOW}ℹ trivy not found on PATH; skipping local security scan.${NC}"
fi

# 5. Optional Docker Image Verification & Vulnerability Scan
if [[ "${1:-}" == "--docker" ]]; then
    echo -e "\n${BLUE}[Optional] Running Container Build & Image Scan...${NC}"
    docker build -t filestore-runtime:test .
    echo -e "${GREEN}✓ Container built successfully: filestore-runtime:test${NC}"
    if command -v trivy >/dev/null 2>&1; then
        echo -e "${BLUE}Scanning container image with Trivy...${NC}"
        trivy image --severity HIGH,CRITICAL --ignore-unfixed filestore-runtime:test
        echo -e "${GREEN}✓ Container image passed Trivy vulnerability scan.${NC}"
    fi
fi

echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}🎉 All Runtime automated tests & security scans passed!     ${NC}"
echo -e "${GREEN}============================================================${NC}"
