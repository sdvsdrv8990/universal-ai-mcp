# universal-ai-mcp — Project Instructions for AI

## CRITICAL: These Skills Are NOT Part of the Server

The `uai-*` skills exist to help AI develop this server correctly.
They are Claude Code skills installed at `~/.claude/skills/uai-*/`.
Never ship skill files as part of the server. Never import or reference them in server code.

---

## Mandatory Skill Loading

**At the start of every session working on this project, load:**
1. `/uai-dev-guide` — always first, contains architecture rules and directory map
2. Select one task-specific skill from the table below

**Task → Skill mapping:**

| What you're doing | Load this skill |
|---|---|
| Any code change (mandatory gate) | `/uai-planning-gate` |
| Creating a new module | `/uai-module-builder` |
| Adding/editing workflow profiles | `/uai-profile-designer` |
| Integrating a new LLM provider | `/uai-provider-integrator` |
| Designing context/token management | `/uai-context-optimizer` |
| Code review or naming questions | `/uai-code-standards` |

**The AI must not write code without loading `uai-dev-guide` and running `uai-planning-gate`.**

---

## Project Quick Facts

- **Runtime:** Python 3.14, FastMCP, Pydantic v2, structlog, uv
- **Package:** `universal_ai_mcp` in `src/`
- **Config:** YAML files in `config/` — modules.yaml, workflow_profiles.yaml, providers.yaml
- **Entities:** One entity per file in `entities/`, all exported from `entities/__init__.py`
- **Modules:** Logic in `modules/<name>/`, tools registered in `tools/<name>_tools.py`
- **Entry point:** `core/server.py` → `main()` → HTTP (uvicorn) or stdio

## Running

```bash
uv sync                        # install dependencies
uv run pytest tests/ -v        # run tests
uv run python -m universal_ai_mcp.core.server  # start server
```

## Non-Negotiable Rules (see uai-dev-guide for full list)

1. No code before an approved plan (uai-planning-gate)
2. Entities declared exactly once in `entities/<name>_entity.py`
3. No `utils.py`, `helpers.py`, `misc.py` — every file has a purpose name
4. All LLM calls go through `LLMRouter.complete()`, never direct to providers
5. MCP tools always return `str` (JSON) and never raise — handle errors gracefully
6. Feature flags in `workflow_profiles.yaml`, not hardcoded in Python
