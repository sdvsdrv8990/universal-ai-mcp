"""MCP server entry point — HTTP/SSE transport with Bearer auth.

Startup sequence:
  1. Load settings from environment
  2. Initialize session store and tool registry
  3. Register all module tools
  4. Start HTTP server (uvicorn) or stdio depending on MCP_TRANSPORT
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import structlog
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from universal_ai_mcp.core.config import get_settings
from universal_ai_mcp.core.dynamic_config import get_dynamic_config
from universal_ai_mcp.core.logging import configure_logging
from universal_ai_mcp.core.registry import ToolRegistry, register_all_modules
from universal_ai_mcp.core.session_store import SessionStore

log = structlog.get_logger(__name__)


class BearerAuthMiddleware:
    """Reject requests missing a valid Bearer token — pure ASGI, SSE-safe.

    BaseHTTPMiddleware is incompatible with SSE (streaming) responses and causes
    an AssertionError on client disconnect. This pure ASGI implementation avoids
    that by never buffering the response body.
    """

    def __init__(self, app: ASGIApp, secret: str) -> None:
        self._app = app
        self._secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in ("/health", "/"):
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if not auth.startswith("Bearer ") or auth[7:] != self._secret:
            response = JSONResponse({"error": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)


def _make_mcp(settings: object) -> tuple[FastMCP, ToolRegistry, SessionStore]:
    """Create FastMCP instance with shared state attached via __dict__."""
    from universal_ai_mcp.core.config import ServerSettings
    assert isinstance(settings, ServerSettings)

    registry = ToolRegistry()
    session_store = SessionStore()
    dynamic_config = get_dynamic_config()

    mcp = FastMCP(name=settings.mcp_server_name)
    mcp.__dict__["state"] = SimpleNamespace(
        registry=registry,
        session_store=session_store,
        settings=settings,
        dynamic_config=dynamic_config,
    )

    register_all_modules(mcp, registry)
    return mcp, registry, session_store


def build_app() -> Starlette:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    mcp, registry, _ = _make_mcp(settings)
    dynamic_config = get_dynamic_config()

    async def health(_: Request) -> JSONResponse:
        active_state = dynamic_config.get_active_state()
        return JSONResponse({
            "status": "ok",
            "server": settings.mcp_server_name,
            "version": settings.mcp_server_version,
            "modules_total": len(registry.list_modules()),
            "modules_active": len(registry.list_active_modules()),
            "tools_total": len(registry.list_tool_names()),
            "tools_active": len(registry.list_active_tool_names()),
            "active_profile": active_state.profile.name if active_state else None,
            "workflow_profiles": len(dynamic_config.list_profiles()),
        })

    sse_app = mcp.sse_app()

    routes = [
        Route("/health", health),
        Mount("/", app=sse_app),
    ]
    starlette_app = Starlette(routes=routes)
    return BearerAuthMiddleware(starlette_app, secret=settings.mcp_auth_secret.get_secret_value())  # type: ignore[return-value]


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    if settings.mcp_transport == "stdio":
        mcp, _, _ = _make_mcp(settings)
        asyncio.run(mcp.run_stdio_async())
    else:
        app = build_app()
        uvicorn.run(
            app,
            host=settings.mcp_host,
            port=settings.mcp_port,
            log_config=None,
        )


if __name__ == "__main__":
    main()
