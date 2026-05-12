# Development Documentation — Index

Эта директория — **thin index** на runtime-слои сервера. Полное содержимое каждого слоя живёт в соответствующем skill в `~/.claude/skills/uai-layer-*/SKILL.md`.

## Что где

| Файл | Назначение |
|------|------------|
| [`master-plan.md`](master-plan.md) | Архитектура единой dev-системы (двуглавая AI: heavy + auditor + janitor) |
| [`scenario-testing-skill-upgrade-plan.md`](scenario-testing-skill-upgrade-plan.md) | Temporary working plan for scenario-aware tests and anti-hardcode skill upgrades |
| [`blockify/`](blockify/) | Source pointer: Blockify (IdeaBlocks compression pipeline) |
| [`get-shit-done/`](get-shit-done/) | Source pointer: GSD (phase gates + state + verification) |
| [`claude-best-practice/`](claude-best-practice/) | Source pointer: Claude Code best practices |
| [`hot-test-bugs.md`](hot-test-bugs.md) | Live bug log from hot-tests |
| [`structured-output-research.md`](structured-output-research.md) | JSON parsing research (decision: Option C) |

## Карта слоёв → skills

Запускай нужный skill через `Skill` tool. Skill = собственная папка `~/.claude/skills/uai-layer-<name>/`.

### Blockify (context optimization)

- `uai-layer-blockify-ingest` — LLM extraction → IdeaBlock (implemented)
- `uai-layer-blockify-distill` — LSH dedup + LLM merge (implemented)
- `uai-layer-blockify-retrieve` — Vector storage + retrieval (planned v2.0)

### GSD (workflow + state)

- `uai-layer-gsd-phase-gates` — Approval-gated phases (implemented)
- `uai-layer-gsd-wave-execution` — asyncio.gather wave runner (implemented)
- `uai-layer-gsd-state-persist` — `.planning/` artifacts (implemented)
- `uai-layer-gsd-verification` — Goal-backward verifier (implemented)

### Claude Best-Practice (design + context rules)

- `uai-layer-bp-workflow` — Research→Plan→Execute→Review→Ship (implemented)
- `uai-layer-bp-context-rules` — Auto-compress + tag injection (implemented)
- `uai-layer-bp-subagent-patterns` — Subprocess isolation (planned v2.0)

## Naming convention

- `uai-*` (без `layer-`) — meta/dev skills для разработчика этого сервера (мандаторные при работе с кодом)
- `uai-layer-*` — runtime слои внутри сервера (для понимания внутреннего устройства)

Никаких смысловых пересечений между двумя группами.
