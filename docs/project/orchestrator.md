# Orchestrator Module

The orchestrator runs a development task through a 7-phase dual-AI pipeline.
A heavy driver (Claude) executes the work; a local auditor (Ollama/qwen3:8b)
reviews after every phase and can block the pipeline on critical issues.
A local janitor tidies docs and planning artifacts at the end.

## Tool: `dev_session_run`

```
dev_session_run(
  task:          str,             # what to build/fix
  project_path:  str,             # absolute path to project root
  file_deltas:   list[str] | None # optional: ["src/foo.py: +15/-3", ...]
  janitor_scope: list[str] | None # optional: extra paths janitor may write
  xml_context:   str              # optional: compressed context for auditor
)
```

### Pipeline phases

| # | Phase | What happens |
|---|-------|-------------|
| 1 | `profile_select` | Pick the best workflow profile for the task |
| 2 | `context_build` | Build compressed semantic context |
| 3 | `plan_gate` | Verify an approved plan exists |
| 4 | `wave_execute` | Execute plan steps in waves |
| 5 | `state_persist` | Save state to `.planning/` |
| 6 | `verify` | Verify work against acceptance criteria |
| 7 | `finalize` | Janitor updates docs/state (blocking) |

After **every** phase the auditor runs. If it returns `severity=high` the
pipeline halts immediately and returns a `blocked` response.

### Response format

```json
{
  "status": "completed" | "blocked" | "error",
  "session_id": "uuid",
  "phases_completed": ["profile_select", "context_build", ...],
  "audit_summary": [
    {"phase": "plan_gate", "severity": "low", "issues": 0}
  ],
  "janitor_actions_applied": [
    {"path": "docs/api.md", "type": "update", "description": "..."}
  ]
}
```

`status=blocked` additionally includes `blocked_at_phase` and `audit_report`
with the full list of `missed_actions` and `questionable_choices`.

## Janitor scope

The janitor may only write to paths in `config/orchestrator.yaml → janitor.scope_whitelist`:

```yaml
scope_whitelist:
  - "docs/"
  - "CHANGELOG.md"
  - ".planning/STATE.md"
  - ".planning/CONTEXT.md"
```

Pass `janitor_scope=["reports/"]` to grant extra paths for one session only.

## Auditor availability

If Ollama is down and `auditor.required: false` (default), the auditor silently
returns `severity=low` and the pipeline continues. Set `required: true` in
`config/orchestrator.yaml` for production environments.

A fallback to Anthropic Haiku is configured by default and is tried before
the `required` check triggers.
