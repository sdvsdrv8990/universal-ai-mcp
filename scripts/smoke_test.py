"""Smoke test — calls every registered tool and reports pass/fail/skip."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

SERVER_URL = "http://localhost:8000/sse"
TOKEN = "change-me-in-production"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@dataclass
class Result:
    tool: str
    status: str          # PASS | FAIL | SKIP
    note: str = ""
    response: Any = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Smoke calls — minimal valid inputs per tool
# ---------------------------------------------------------------------------

SMOKE_CALLS: dict[str, dict] = {
    # ── planning ─────────────────────────────────────────────────────────
    "task_analyze": {
        "task_description": "add a health-check endpoint to the FastAPI app"
    },
    "task_plan_build": {
        "task_description": "add a health-check endpoint",
        "complexity": "simple",
        "answers": "no extra context",
        "session_id": "00000000-0000-0000-0000-000000000001",
    },
    "task_plan_approve": {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "plan_id": "00000000-0000-0000-0000-000000000002",
    },
    "task_plan_status": {
        "session_id": "00000000-0000-0000-0000-000000000001",
    },

    # ── context ───────────────────────────────────────────────────────────
    "context_add_content": {
        "content": "We are building a REST API in Python with FastAPI.",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "source_ref": "smoke-test",
    },
    "context_get_xml": {
        "session_id": "00000000-0000-0000-0000-000000000001",
    },
    "context_token_usage": {
        "session_id": "00000000-0000-0000-0000-000000000001",
    },
    "context_compress_now": {
        "session_id": "00000000-0000-0000-0000-000000000001",
    },
    "context_persist_blocks": {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "project_path": "/tmp/smoke-test-project",
    },

    # ── llm ───────────────────────────────────────────────────────────────
    "llm_list_providers": {},
    "llm_list_models": {},
    "llm_complete": {
        "prompt": "Reply with only the word: PONG",
        "max_tokens": 16,
    },

    # ── project_detection ─────────────────────────────────────────────────
    "project_detect": {
        "project_path": "/home/admin/projects/universal-ai-mcp",
    },
    "project_map_codebase": {
        "project_path": "/home/admin/projects/universal-ai-mcp",
    },
    "project_recommend_stack": {
        "project_description": "Python REST API server with async workers and PostgreSQL",
    },
    "project_adapt_name": {
        "name": "UserService",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "kind": "file",
    },

    # ── solutions ─────────────────────────────────────────────────────────
    "solutions_find": {
        "requirement": "vector database for Python embeddings",
        "language": "python",
    },
    "solutions_optimize_deps": {
        "library_name": "chromadb",
        "features_used": "embedding storage, similarity search",
        "dependency_tree": "chromadb==0.4.0",
    },
    "solutions_plan_integration": {
        "solution_name": "chromadb",
        "target_feature": "semantic search for code blocks",
        "session_id": "00000000-0000-0000-0000-000000000001",
    },

    # ── workflow ──────────────────────────────────────────────────────────
    "workflow_execute_plan": {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "project_path": "/tmp/smoke-test-project",
    },
    "workflow_verify_work": {
        "session_id": "00000000-0000-0000-0000-000000000001",
    },
    "workflow_save_state": {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "project_path": "/tmp/smoke-test-project",
    },
    "workflow_load_state": {
        "plan_id": "smoke-test-plan",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "project_path": "/tmp/smoke-test-project",
    },
    "workflow_append_context": {
        "key": "smoke_test",
        "value": "Smoke test ran successfully",
        "project_path": "/tmp/smoke-test-project",
    },
    "workflow_read_context": {
        "project_path": "/tmp/smoke-test-project",
    },

    # ── config ────────────────────────────────────────────────────────────
    "config_list_profiles": {},
    "config_get_active_profile": {},
    "config_analyze_task": {
        "task_description": "add a new REST API endpoint",
    },
    "config_activate_profile": {
        "profile_name": "feature_build",
    },
    "config_reload_profiles": {},
    "config_toggle_module": {
        "module_name": "solutions",
        "enabled": True,
    },

    # ── memory ────────────────────────────────────────────────────────────
    "memory_list_sources": {},
    "memory_store": {
        "content": "FastMCP is a Python framework for building MCP servers.",
        "source": "smoke-test",
        "scope": "project",
        "project_path": "/tmp/smoke-test-project",
    },
    "memory_search": {
        "query": "MCP server Python",
        "top_k": 3,
    },
    "memory_index_docs": {
        "content": "FastMCP documentation: use @mcp.tool() to register tools.",
        "library_name": "fastmcp",
        "scope": "global",
    },
    "memory_index_github": {
        "repo_full_name": "modelcontextprotocol/python-sdk",
        "scope": "global",
    },
    "memory_delete_source": {
        "source": "smoke-test-nonexistent",
        "scope": "project",
        "project_path": "/tmp/smoke-test-project",
    },

    # ── orchestrator ──────────────────────────────────────────────────────
    "dev_session_run": {
        "task": "smoke test — verify orchestrator pipeline runs without errors",
        "project_path": "/tmp/smoke-test-project",
    },
}


async def call_tool(session: ClientSession, tool: str, args: dict) -> Result:
    try:
        result = await session.call_tool(tool, args)
        if result.isError:
            # Tool returned error content — still "responded", classify as FAIL
            content = result.content[0].text if result.content else "(no content)"
            try:
                parsed = json.loads(content)
                error_msg = parsed.get("error", content[:120])
            except Exception:
                error_msg = content[:120]
            return Result(tool=tool, status="FAIL", note=f"tool error: {error_msg}", response=content)

        content = result.content[0].text if result.content else ""
        try:
            parsed = json.loads(content)
            note = _summarize(parsed)
        except Exception:
            note = content[:80]
        return Result(tool=tool, status="PASS", note=note, response=content)

    except Exception as exc:
        return Result(tool=tool, status="FAIL", note=str(exc)[:120])


def _summarize(data: Any) -> str:
    if isinstance(data, dict):
        keys = list(data.keys())[:4]
        return f"keys={keys}"
    if isinstance(data, list):
        return f"list[{len(data)}]"
    return str(data)[:80]


async def run_smoke_test() -> None:
    import os
    os.makedirs("/tmp/smoke-test-project/.planning", exist_ok=True)

    print("=" * 72)
    print("universal-ai-mcp  SMOKE TEST")
    print("=" * 72)

    # Check server is alive
    async with httpx.AsyncClient() as http:
        r = await http.get("http://localhost:8000/health")
        health = r.json()
    print(f"\n/health → {health}\n")

    results: list[Result] = []

    async with sse_client(SERVER_URL, headers=HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover all tools from server
            tools_response = await session.list_tools()
            server_tools = {t.name for t in tools_response.tools}
            print(f"Server registered tools: {len(server_tools)}")
            print()

            for tool_name in sorted(server_tools):
                args = SMOKE_CALLS.get(tool_name)
                if args is None:
                    results.append(Result(tool=tool_name, status="SKIP", note="no smoke args defined"))
                    continue
                r = await call_tool(session, tool_name, args)
                results.append(r)

    # Report
    passed = [r for r in results if r.status == "PASS"]
    failed = [r for r in results if r.status == "FAIL"]
    skipped = [r for r in results if r.status == "SKIP"]

    col_w = max(len(r.tool) for r in results) + 2

    print(f"{'TOOL':<{col_w}}  {'STATUS':<6}  NOTE")
    print("-" * 72)
    for r in sorted(results, key=lambda x: (x.status, x.tool)):
        icon = "✓" if r.status == "PASS" else ("✗" if r.status == "FAIL" else "·")
        print(f"{icon} {r.tool:<{col_w}} {r.status:<6}  {r.note}")

    print()
    print(f"RESULTS:  {len(passed)} PASS  |  {len(failed)} FAIL  |  {len(skipped)} SKIP  |  {len(results)} total")

    if failed:
        print("\nFAILED TOOLS:")
        for r in failed:
            print(f"  {r.tool}: {r.note}")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
