# Master Plan — Unified Development System

**Status:** Draft / ADR  
**Date:** 2026-05-12  
**Goal:** Свести слои Blockify + GSD + Claude Best-Practice + Local-AI в один оркестратор разработки с двуглавой AI-моделью (heavy executor + local auditor + local janitor).

---

## 1. Карта слоёв (single source of truth)

Каждый слой имеет свой skill в `~/.claude/skills/uai-layer-<solution>-<concern>/`.
Skill содержит чеклист состояния — это и есть live-карта прогресса.

| # | Skill | Source | Layer concern | Layer status |
|---|-------|--------|---------------|--------------|
| 1 | `uai-layer-blockify-ingest` | Blockify | LLM extraction → IdeaBlock | implemented |
| 2 | `uai-layer-blockify-distill` | Blockify | LSH dedup + LLM merge | implemented |
| 3 | `uai-layer-blockify-retrieve` | Blockify | Vector store / retrieval | implemented |
| 4 | `uai-layer-gsd-phase-gates` | GSD | Approval-gated phases | implemented |
| 5 | `uai-layer-gsd-wave-execution` | GSD | asyncio.gather wave runner | implemented |
| 6 | `uai-layer-gsd-state-persist` | GSD | `.planning/` artifacts | implemented |
| 7 | `uai-layer-gsd-verification` | GSD | Goal-backward verifier | implemented |
| 8 | `uai-layer-bp-workflow` | Claude BP | Research→Plan→Execute→Review→Ship | implemented (design) |
| 9 | `uai-layer-bp-context-rules` | Claude BP | 200-line cap, lazy load | implemented (design) |
| 10 | `uai-layer-bp-subagent-patterns` | Claude BP | Agent isolation | deferred (v2.1) |

Naming convention: `uai-layer-*` = runtime слои внутри сервера; `uai-*` (без `layer-`) = meta/dev skills для разработчика.
Никаких пересечений по семантике — каждый слой имеет уникальный concern.

---

## 2. Архитектура целевой системы — Двуглавая AI

```
┌──────────────────────────────────────────────────────────────┐
│  dev_session  (top-level MCP tool, новый)                    │
│                                                               │
│  ┌────────────────┐    ┌──────────────────┐  ┌─────────────┐ │
│  │ HEAVY AI       │    │ LOCAL AUDITOR    │  │ LOCAL JANIT.│ │
│  │ Claude (driver)│◄──►│ Ollama (observer)│  │ Ollama      │ │
│  │                │    │ BLOCKING на high │  │ project-only│ │
│  │ executes phases│    │ severity         │  │ writes      │ │
│  └────────────────┘    └──────────────────┘  └─────────────┘ │
│         │                       ▲                    ▲       │
│         ▼                       │                    │       │
│  ┌──────────────────────────────────────────────┐    │       │
│  │ Phase Pipeline                               │    │       │
│  │  1. profile_select  (dynamic_config)         │    │       │
│  │  2. context_build   (layers 1+2: blockify)   │    │       │
│  │  3. plan_gate       (layer 4: gsd gates)     │    │       │
│  │  4. wave_execute    (layer 5: gsd waves)     │    │       │
│  │  5. state_persist   (layer 6: gsd state)     │    │       │
│  │  6. verify          (layer 7: gsd verifier)  │────┘       │
│  └──────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

### 2.1 Heavy AI (driver)
- Запускается из любого MCP-клиента (Claude Code, Cursor, Windsurf...)
- Вызывает `dev_session_run(task, opts)` — единая точка входа
- Получает structured результат: фазы, audit-отчёт, janitor-actions

### 2.2 Local Auditor (BLOCKING при severity=high)
- **Запуск:** после каждой фазы pipeline
- **Модель:** local Ollama, cheap (qwen3.5:9b или меньше)
- **Вход:** task, выбранный profile, список tool calls, file deltas
- **Выход:** `AuditReport { missed_actions[], questionable_choices[], severity }`
- **Поведение:**
  - `severity=low/med` → log + продолжить
  - `severity=high` → **остановить pipeline**, вернуть отчёт в Claude для исправления
- **Аргументы за blocking:** ловит пропуски (например, тесты не написаны после feature_build) до того как сессия дойдёт до verify-фазы и потратит больше токенов

### 2.3 Local Janitor (project-only)
- **Запуск:** после успешной verify-фазы
- **Модель:** local Ollama
- **Scope (жёсткие границы):**
  - ✅ Может писать: `docs/`, `CHANGELOG.md`, `.planning/STATE.md`, `.planning/CONTEXT.md`
  - ❌ Не может писать: `src/`, `~/.claude/*`, `~/`, любые user-level пути
- **Действия:**
  - Обновить `docs/project/*.md` если изменилась публичная API
  - Дописать запись в `CHANGELOG.md` (если есть)
  - Обновить `.planning/STATE.md` итоговым статусом сессии
- **Аргументы за project-only:** janitor под локальной моделью может ошибаться в нюансах; ограничение scope минимизирует blast radius

---

## 3. Roadmap фаз реализации

### Фаза A — Skills рефакторинг ✅ DONE (2026-05-12)
**Цель:** все 10 слоёв вынесены в отдельные `uai-layer-*` skills с чеклистами.

- [x] A1. 10 SKILL.md созданы с frontmatter `layer_status` + markdown-чеклист  
- [x] A2. Reference code перенесён из `docs/development/<solution>/*.md` в skills  
- [x] A3. `docs/development/<solution>/overview.md` → thin indexes (10-30 строк)  
- [x] A4. 26 cross-refs `[[uai-layer-...]]` валидны, concerns уникальны (нет дублей)

### Фаза B — Entities + Config для оркестратора ✅ DONE (2026-05-12)
- [x] B1. `entities/audit_report_entity.py` — `AuditSeverity`, `AuditReport` с `is_blocking`  
- [x] B2. `entities/janitor_action_entity.py` — `JanitorChangeType`, `JanitorAction` с `mark_applied()`  
- [x] B3. `entities/dev_session_entity.py` — `OrchestratorPhase`, `DevSession` с phase state machine  
- [x] B4. `config/orchestrator.yaml` — qwen3:8b, severity thresholds, janitor whitelist + per-session override  
- [x] Тесты: `tests/test_orchestrator_entities.py` — 11/11 passed  
- [x] Groundwork: `~/.claude/skills/uai-layer-orchestrator/SKILL.md` — C+D design, 6 clarifying Q's

### Фаза C — Modules + Tools для оркестратора ✅ DONE (2026-05-12)
- [x] C1. `modules/orchestrator/dev_session_runner.py` — phase state machine  
- [x] C2. `modules/orchestrator/local_auditor.py` — после-фазовый observer с blocking-логикой  
- [x] C3. `modules/orchestrator/local_janitor.py` — финализатор с whitelisted scope  
- [x] C4. `tools/orchestrator_tools.py` → `dev_session_run` MCP tool  
- [x] C5. `modules/orchestrator/orchestrator_config.py` — Pydantic config loader  

### Фаза D — Wiring + Tests ✅ DONE (2026-05-12)
- [x] D1. `core/registry.py` — регистрация модуля orchestrator  
- [x] D2. `config/modules.yaml` — orchestrator с deps [llm, context, planning, workflow]  
- [x] D3. Профиль `orchestrated` в `workflow_profiles.yaml`  
- [x] D4. `tests/test_orchestrator_modules.py` — 22 теста (auditor blocking, janitor scope, runner pipeline)  
- Total: **83/83 tests pass**, server builds OK

---

## 4. Почему это даёт максимальную эффективность

| Метрика | До | После | Δ |
|---|---|---|---|
| Платные tokens / сессия | ~80k | ~25k (heavy) + ~50k (local, $0) | **−70%** |
| Время выполнения | Sequential, manual | Auto-pipeline + parallel janitor | **−40%** |
| Пропущенные действия | Зависит от модели | Ловится auditor'ом | **+надёжность** |
| Свежесть документации | Часто отстаёт | Janitor обновляет каждую сессию | **always-fresh** |
| Стоимость API | $$ | $ (heavy на работу, local на присмотр и финализацию) | **−50% $$$** |

---

## 5. Решения, зафиксированные на этом этапе

| # | Решение | Альтернатива | Почему так |
|---|---------|--------------|------------|
| 1 | Гранулярность skills: 10 (по слоям) | 6 (по фазам), 3 (по решениям) | Максимум token-economy; чёткие границы concern |
| 2 | Auditor: **blocking** на severity=high | advisory-only, hybrid | Ловит пропуски рано, до verify-фазы. Без блокировки local-модель = шум |
| 3 | Janitor: **project-only** writes | full system access, read-only | Безопасность: local-модель может ошибаться, scope ограничивает blast radius |
| 4 | Префикс `uai-layer-*` | смешать с `uai-*` | Разделяет meta/dev skills и runtime layer skills, исключает путаницу |

---

## 6. Ссылки

- Layer skills: `~/.claude/skills/uai-layer-*/SKILL.md`
- Dev skills: `~/.claude/skills/uai-*/SKILL.md` (meta, не путать)
- Источники: `docs/development/<solution>/overview.md` (thin index'ы)
- Конфиг профилей: `config/workflow_profiles.yaml`
