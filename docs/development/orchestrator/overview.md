# Orchestrator Layer — Developer Overview

## Architecture

```
dev_session_run (MCP tool)
        │
        ▼
DevSessionRunner.run()
        │
        ├─► for each phase in PHASE_ORDER:
        │       │
        │       ├─ _describe_phase()        ← builds phase context string
        │       │
        │       └─ LocalAuditor.audit_phase()
        │               │
        │               ├─ router.complete(provider="ollama")
        │               ├─ [fallback: router.complete(provider="anthropic")]
        │               └─ parse → AuditReport
        │                       │
        │                       └─ is_blocking? → HALT pipeline
        │
        └─► LocalJanitor.finalize()   ← runs AFTER all phases pass (sync)
                │
                ├─ router.complete(provider="ollama")
                ├─ parse proposed actions
                ├─ filter via is_path_allowed()
                └─ apply → list[JanitorAction]
```

## Key files

| File | Role |
|------|------|
| `modules/orchestrator/orchestrator_config.py` | Pydantic models + YAML loader for `config/orchestrator.yaml` |
| `modules/orchestrator/local_auditor.py` | `LocalAuditor` — LLM reviewer, returns `AuditReport` |
| `modules/orchestrator/local_janitor.py` | `LocalJanitor` — doc finalizer, returns `list[JanitorAction]` |
| `modules/orchestrator/dev_session_runner.py` | `DevSessionRunner` — phase state machine |
| `tools/orchestrator_tools.py` | MCP tool registration (`dev_session_run`) |
| `config/orchestrator.yaml` | Auditor/janitor/pipeline configuration |
| `entities/audit_report_entity.py` | `AuditReport` + `AuditSeverity` (Phase B) |
| `entities/janitor_action_entity.py` | `JanitorAction` + `JanitorChangeType` (Phase B) |
| `entities/dev_session_entity.py` | `DevSession` + `OrchestratorPhase` (Phase B) |

## Phase state machine

`DevSession.current_phase` starts at `PROFILE_SELECT`. The runner advances it
at the END of each iteration (after auditing), never before. The invariant:

```
session.current_phase == PHASE_ORDER[i]  during iteration i
```

`advance_phase(PHASE_ORDER[i+1])` is called after a successful audit.
`session.complete()` seals the last phase.

## Auditor error handling

Three layers, tried in order:
1. `router.complete(preferred_provider="ollama")` — primary (qwen3:8b)
2. `router.complete(preferred_provider="anthropic")` — fallback (haiku)
3. If both fail:
   - `auditor.required=False` → return synthetic `severity=low` report (FAIL OPEN)
   - `auditor.required=True` → raise `AuditorUnavailableError` → runner returns `status=error`

## Janitor path security

`is_path_allowed(path, session)` checks:
1. Path starts with any entry in `config.janitor.scope_whitelist`
2. OR path starts with any entry in `session.janitor_scope_override`
   (only when `allow_per_session_override=true`)

Actions failing the check are logged as `janitor_path_rejected` and skipped.
`JanitorAction.applied` is only set to `True` after a successful `_apply_action()`.

## DevSession storage

`DevSession` objects are stored in a module-level dict `_dev_sessions` in
`tools/orchestrator_tools.py` (in-memory, per-process lifetime). This is
sufficient for v2.0. Migration to `SessionStore` or disk persistence (via
`StateManager`) is planned for v2.1.

## Design decisions

| Decision | Choice | Reason |
|---|---|---|
| Auditor input | XML context + file_deltas | Auditor sees both intent (XML) and facts (deltas) |
| Janitor mode | Sync/blocking | Deterministic result; async can be added via feature flag later |
| Error handling | Configurable (`auditor.required`) | Dev=FAIL OPEN, prod=FAIL CLOSED without code changes |
| Session storage | Module-level dict | Zero deps for v2.0; StateManager integration in v2.1 |
| Return type | Single JSON | Simple for v2.0; streaming possible in v2.1 |
