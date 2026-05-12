#!/usr/bin/env bash
# deploy.sh — Build Docker image and push to registry
#
# Usage:
#   ./scripts/deploy.sh                          # auto-detect best registry
#   ./scripts/deploy.sh ghcr.io/your-org latest  # explicit registry + tag
#   ./scripts/deploy.sh --check-only             # test Docker registries, no build
#
# The script auto-selects a working Docker base image if Docker Hub is unavailable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log_step() { echo -e "\n${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
log_ok()   { echo -e "${GREEN}  ✓${RESET} $*"; }
log_fail() { echo -e "${RED}  ✗${RESET} $*"; }
log_info() { echo -e "${YELLOW}  i${RESET} $*"; }

# ─── Args ─────────────────────────────────────────────────────────────────────
REGISTRY="${1:-ghcr.io/your-org}"
TAG="${2:-latest}"
IMAGE="$REGISTRY/universal-ai-mcp:$TAG"
TIMEOUT=5

# ─── Require Docker ───────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo -e "${RED}ERROR: Docker is not installed.${RESET}"
  echo "Install Docker: https://docs.docker.com/engine/install/"
  exit 1
fi

# ─── Check only mode ─────────────────────────────────────────────────────────
if [[ "${1:-}" == "--check-only" ]]; then
  bash scripts/check-mirrors.sh --docker-only
  exit 0
fi

# ─── Load mirror config ───────────────────────────────────────────────────────
MIRRORS_ENV="$PROJECT_DIR/.mirrors.env"
if [[ -f "$MIRRORS_ENV" ]]; then
  set -a; source "$MIRRORS_ENV"; set +a
  log_info "Loaded mirror config"
else
  log_info "No .mirrors.env — running mirror check first..."
  bash scripts/check-mirrors.sh --docker-only
  [[ -f "$MIRRORS_ENV" ]] && { set -a; source "$MIRRORS_ENV"; set +a; }
fi

# ─── Select base image ────────────────────────────────────────────────────────
log_step "Selecting Python base image..."

DOCKER_BASE_PYTHON="${DOCKER_BASE_PYTHON:-python:3.12-slim}"

# Python image candidates ordered by availability
PYTHON_IMAGE_CANDIDATES=(
  "$DOCKER_BASE_PYTHON"
  "python:3.12-slim"
  "registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim"
  "ccr.ccs.tencentyun.com/library/python:3.12-slim"
  "hub.c.163.com/library/python:3.12-slim"
)

SELECTED_BASE=""
for img in "${PYTHON_IMAGE_CANDIDATES[@]}"; do
  log_info "Testing: $img"
  if docker manifest inspect "$img" &>/dev/null 2>&1; then
    log_ok "Available: $img"
    SELECTED_BASE="$img"
    break
  else
    log_fail "Unavailable: $img"
  fi
done

if [[ -z "$SELECTED_BASE" ]]; then
  echo -e "${RED}ERROR: No Python base image is accessible.${RESET}"
  echo "Options:"
  echo "  1. Login to Docker Hub:  docker login"
  echo "  2. Login to Aliyun:      docker login registry.cn-hangzhou.aliyuncs.com"
  echo "  3. Set DOCKER_BASE_PYTHON env var to a locally available image"
  exit 1
fi

# ─── Select uv approach ───────────────────────────────────────────────────────
log_step "Selecting uv installation method..."

SELECTED_UV_INSTALLER="${UV_INSTALL_URL:-}"
UV_COPY_FROM=""

if docker manifest inspect "ghcr.io/astral-sh/uv:latest" &>/dev/null 2>&1; then
  log_ok "GHCR available — using COPY --from=ghcr.io/astral-sh/uv:latest"
  UV_COPY_FROM="ghcr.io/astral-sh/uv:latest"
elif [[ "$SELECTED_UV_INSTALLER" != "pip" && -n "$SELECTED_UV_INSTALLER" ]]; then
  log_ok "Will download uv via: $SELECTED_UV_INSTALLER"
else
  log_info "Will install uv via pip (pip fallback)"
  SELECTED_UV_INSTALLER="pip"
fi

# ─── Build ────────────────────────────────────────────────────────────────────
log_step "Building Docker image: $IMAGE"
log_info "Base image : $SELECTED_BASE"
log_info "uv method  : ${UV_COPY_FROM:-$SELECTED_UV_INSTALLER}"

docker build \
  --build-arg BASE_PYTHON_IMAGE="$SELECTED_BASE" \
  --build-arg UV_IMAGE="${UV_COPY_FROM:-}" \
  --build-arg UV_INSTALL_URL="${SELECTED_UV_INSTALLER:-https://astral.sh/uv/install.sh}" \
  -t "$IMAGE" \
  .

log_ok "Build complete: $IMAGE"

# ─── Push ─────────────────────────────────────────────────────────────────────
log_step "Pushing image to registry..."
if docker push "$IMAGE"; then
  log_ok "Pushed: $IMAGE"
else
  echo -e "${RED}Push failed. Make sure you're logged in:${RESET}"
  echo "  docker login ${REGISTRY%%/*}"
  exit 1
fi

echo ""
echo -e "${GREEN}${BOLD}Deploy complete: $IMAGE${RESET}"
echo ""
echo "  Cloud Run:"
echo "    gcloud run deploy universal-ai-mcp \\"
echo "      --image $IMAGE --port 8000 \\"
echo "      --set-env-vars MCP_TRANSPORT=http"
