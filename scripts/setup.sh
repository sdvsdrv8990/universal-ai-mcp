#!/usr/bin/env bash
# setup.sh — Local development setup (no Docker, no root required)
#
# What it does:
#   1. Check mirror reachability → write .mirrors.env
#   2. Install uv (user-space, ~/.cargo/bin or ~/.local/bin)
#   3. Sync Python dependencies into .venv/
#   4. Create .env from .env.example (if not exists)
#
# Requirements: bash, curl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ─── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'
log_step() { echo -e "\n${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
log_ok()   { echo -e "${GREEN}  ✓${RESET} $*"; }
log_info() { echo -e "${YELLOW}  i${RESET} $*"; }

# ─── Step 1: Mirror check ─────────────────────────────────────────────────────
log_step "Checking mirror reachability..."
if [[ -f "scripts/check-mirrors.sh" ]]; then
  bash scripts/check-mirrors.sh --pypi-only
else
  log_info "check-mirrors.sh not found — using default PyPI"
fi

# Load mirror env if exists
MIRRORS_ENV="$PROJECT_DIR/.mirrors.env"
if [[ -f "$MIRRORS_ENV" ]]; then
  # shellcheck source=/dev/null
  set -a; source "$MIRRORS_ENV"; set +a
  log_ok "Loaded mirror config: UV_INDEX_URL=${UV_INDEX_URL:-not set}"
fi

# ─── Step 2: Install uv ──────────────────────────────────────────────────────
log_step "Checking uv..."
if command -v uv &>/dev/null; then
  log_ok "uv already installed: $(uv --version)"
else
  UV_INSTALL_URL="${UV_INSTALL_URL:-https://astral.sh/uv/install.sh}"

  if [[ "$UV_INSTALL_URL" == "pip" ]]; then
    log_info "Installing uv via pip (mirror fallback)..."
    python3 -m pip install --user uv "${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL}"
  else
    log_info "Installing uv from: $UV_INSTALL_URL"
    curl -LsSf "$UV_INSTALL_URL" | sh
  fi

  # Add to PATH for this session
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

  if command -v uv &>/dev/null; then
    log_ok "uv installed: $(uv --version)"
  else
    echo "ERROR: uv installation failed. Install manually: pip install --user uv" >&2
    exit 1
  fi
fi

# ─── Step 3: Sync dependencies ───────────────────────────────────────────────
log_step "Syncing Python dependencies into .venv/ ..."
log_info "Index URL: ${UV_INDEX_URL:-https://pypi.org/simple (default)}"

UV_SYNC_ARGS=(sync --all-extras)

# Pass custom index URL to uv if set
if [[ -n "${UV_INDEX_URL:-}" ]]; then
  UV_SYNC_ARGS+=(--index-url "$UV_INDEX_URL")
fi

uv "${UV_SYNC_ARGS[@]}"
log_ok "Dependencies installed into .venv/"

# ─── Step 4: Create .env ─────────────────────────────────────────────────────
log_step "Setting up environment configuration..."
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  log_ok "Created .env from template"
  echo ""
  echo "  Next: fill in your API keys in .env"
else
  log_ok ".env already exists"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Setup complete!${RESET}"
echo ""
echo "  Next steps:"
echo "    1. Edit .env — add ANTHROPIC_API_KEY and/or OPENROUTER_API_KEY"
echo "    2. Set MCP_AUTH_SECRET to a strong random string:"
echo "         openssl rand -hex 32"
echo "    3. Start the server:"
echo "         uv run universal-ai-mcp"
echo ""
echo "  Other commands:"
echo "    uv run pytest tests/unit/       # run unit tests"
echo "    ./scripts/check-mirrors.sh      # refresh mirror selection"
echo "    ./scripts/check-mirrors.sh --show  # show current mirrors"
