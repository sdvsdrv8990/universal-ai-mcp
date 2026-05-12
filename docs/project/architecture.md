# Architecture

## System Overview

Universal AI MCP Server is a Python-based MCP server exposing a suite of AI-powered tools
to any connected AI client (Claude Code, Cursor, Windsurf, etc.).

It enforces a **Plan → Approve → Execute → Verify** loop before any work is done,
prevents context bloat via Blockify IdeaBlocks, and adapts all output to the detected
project's conventions.

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  AI Client (Claude Code / Cursor / Windsurf / custom agent)     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ MCP / HTTP-SSE / stdio
┌───────────────────────────▼─────────────────────────────────────┐
│  Transport Layer          core/server.py                        │
│  BearerAuth middleware + Starlette + FastMCP                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│  Tool Registry            core/registry.py                      │
│  All tools registered here; nothing registers implicitly        │
└───┬───────┬───────┬──────────┬────────────┬────────────────────┘
    │       │       │          │            │
    ▼       ▼       ▼          ▼            ▼
planning  context  llm   project_det   solutions   workflow
module    module  module   module       module      module
```

## Module Responsibilities

| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| `core` | Server, registry, session store, config, logging | `server.py`, `registry.py`, `session_store.py` |
| `entities` | Domain models — each declared once | `*_entity.py` |
| `types` | Enums and literal types | `*_types.py` |
| `modules/planning` | Planning gate: questions → tool selection → plan | `planner.py`, `question_engine.py`, `tool_selector.py` |
| `modules/context` | Blockify IdeaBlock compression | `idea_block_builder.py`, `context_manager.py`, `semantic_compressor.py` |
| `modules/llm` | Provider abstraction + routing | `router.py`, `provider_registry.py`, `providers/` |
| `modules/project_detection` | Stack detection + convention adaptation | `stack_detector.py`, `convention_adapter.py`, `stack_advisor.py` |
| `modules/solutions` | GitHub search + dep optimization + integration planner | `github_finder.py`, `dependency_optimizer.py`, `integration_planner.py` |
| `modules/workflow` | Execution + state persistence | `task_executor.py`, `work_verifier.py`, `state_manager.py` |
| `tools` | MCP tool registrations — one file per module | `planning_tools.py`, `context_tools.py`, etc. |

## Planning Gate (Critical Path)

Every AI-initiated task MUST follow this sequence:

```
task_analyze()           → returns complexity + questions
  │
  ▼ (user answers questions)
task_plan_build()        → returns ExecutionPlan (not yet approved)
  │
  ▼ (user reviews plan)
task_plan_approve()      → sets plan.approved = True
  │
  ▼
workflow_execute_plan()  → runs steps in parallel waves
  │
  ▼
workflow_verify_work()   → checks objective achieved, finds gaps
```

No step can be skipped. `workflow_execute_plan` raises RuntimeError if plan is not approved.

## Context Optimization (Blockify)

```
Raw content (100k tokens)
        │
        ▼
IdeaBlockBuilder.build()
  │  - LLM extracts 1 IdeaBlock per critical question
  │  - LSH hash deduplication
        ▼
IdeaBlockCollection (≈2.5-5k tokens)
  - Each block: name, question, answer, tags, entities, keywords
  - XML-serialized for efficient LLM consumption
```

## Session Lifecycle

```
Connection established
  → SessionStore.create()
  → project_detect() — stores ProjectContext in session
  → AgentSession.state = INITIALIZING → IDLE

Per task:
  IDLE → QUESTIONING → PLANNING → AWAITING_APPROVAL → EXECUTING → VERIFYING → IDLE
```

## LLM Routing Logic

```
Request tier | Default provider | Model
-------------|-----------------|------
heavy        | Anthropic       | claude-opus-4-7
balanced     | Anthropic       | claude-sonnet-4-6
fast         | Anthropic       | claude-haiku-4-5-20251001

Fallback chain: Anthropic → OpenRouter → Ollama (by priority)
```

## File Naming Conventions

All files follow Python snake_case. Entities end in `_entity.py`. Types end in `_types.py`.
Tools end in `_tools.py`. Each module directory has `__init__.py` exporting its public API.

## State Persistence (.planning/ directory)

```
.planning/
├── STATE.md          — current phase, active plan ID, token usage
├── CONTEXT.md        — decisions and findings across sessions
└── PLANS/
    └── <uuid>.json   — one file per ExecutionPlan
```
