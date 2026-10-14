#!/usr/bin/env bash
# ==============================================================================
# FilestoreCloud Runtime Automated Test Runner
# Executes Hadolint Dockerfile checks, shell script syntax checks,
# and Python architecture & configuration validation tests.
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
echo -e "\n${BLUE}[1/3] Running Dockerfile Linting (Hadolint)...${NC}"
if command -v hadolint >/dev/null 2>&1; then
    hadolint Dockerfile --config .hadolint.yaml
    echo -e "${GREEN}✓ Dockerfile passed Hadolint inspection.${NC}"
else
    echo -e "${YELLOW}ℹ hadolint not found on PATH; skipping local lint.${NC}"
fi

# 2. Shell Script Syntax Check
echo -e "\n${BLUE}[2/3] Checking Shell Script Syntax...${NC}"
for sh_file in hooks/*.sh; do
    if [ -f "$sh_file" ]; then
        sh -n "$sh_file"
        echo -e "${GREEN}✓ Syntax valid: ${sh_file}${NC}"
    fi
done

# 3. Python Test Suite (Architecture Invariants & Hook Simulation)
echo -e "\n${BLUE}[3/3] Running Python Runtime Test Suite...${NC}"
python3 -m unittest discover -s tests -v

# 4. Optional Docker Image Verification
if [[ "${1:-}" == "--docker" ]]; then
    echo -e "\n${BLUE}[Optional] Running Container Build Verification...${NC}"
    docker build -t filestore-runtime:test .
    echo -e "${GREEN}✓ Container built successfully: filestore-runtime:test${NC}"
fi

echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}🎉 All Runtime automated tests passed successfully!        ${NC}"
echo -e "${GREEN}============================================================${NC}"
