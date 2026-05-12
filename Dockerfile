# ─────────────────────────────────────────────────────────────────────────────
# Universal AI MCP Server — Dockerfile
#
# Build with auto-detected mirror (via deploy.sh):
#   ./scripts/deploy.sh
#
# Build with explicit base image (manual):
#   docker build --build-arg BASE_PYTHON_IMAGE=python:3.12-slim .
#   docker build --build-arg BASE_PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim .
#
# Build arguments:
#   BASE_PYTHON_IMAGE  — Python base image (default: python:3.12-slim)
#   UV_IMAGE           — uv COPY source (ghcr.io/astral-sh/uv:latest or empty)
#   UV_INSTALL_URL     — uv installer URL (used when UV_IMAGE is empty)
# ─────────────────────────────────────────────────────────────────────────────

ARG BASE_PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest

# ─── Stage 1: get uv binary ───────────────────────────────────────────────────
# This stage is used only when UV_IMAGE is set (GHCR accessible).
# If UV_IMAGE is empty, deploy.sh installs uv via pip in stage 2.
FROM ${UV_IMAGE} AS uv-source

# ─── Stage 2: application ────────────────────────────────────────────────────
FROM ${BASE_PYTHON_IMAGE}

ARG UV_INSTALL_URL=https://astral.sh/uv/install.sh

WORKDIR /app

# Copy uv from stage 1 (works only when UV_IMAGE was set)
COPY --from=uv-source /uv /usr/local/bin/uv 2>/dev/null || true

# Fallback: install uv via pip if the COPY above produced nothing
# (happens when uv-source stage was skipped due to UV_IMAGE="")
RUN if ! command -v uv &>/dev/null; then \
      echo "==> uv not found from stage 1, installing via pip..." && \
      pip install --no-cache-dir uv; \
    fi && \
    uv --version

# Copy dependency manifests first (enables layer caching)
COPY pyproject.toml uv.lock* ./
COPY config/ ./config/

# Install production dependencies only (no dev extras)
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ ./src/

# Non-root user — no root privileges needed at runtime
RUN useradd --create-home --shell /bin/bash --uid 1001 mcpuser && \
    chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8000

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV LOG_FORMAT=json

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uv", "run", "universal-ai-mcp"]
