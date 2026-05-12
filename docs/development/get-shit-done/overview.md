# GSD — Source Pointer

> Полное содержимое слоёв вынесено в skills.

**Источник:** github.com/gsd-build/get-shit-done

## Что решает GSD

«Context rot» — деградация качества по мере заполнения контекстного окна. GSD удерживает качество через:

1. Запуск каждой задачи в свежем 200k-токеновом subagent-контексте
2. Хранение состояния в structured artifacts (не в context window)
3. Phase-gate workflow: Initialize → Discuss → Plan → Execute → Verify → Ship

## Skills (runtime слои)

| Skill | Layer | Status |
|-------|-------|--------|
| `uai-layer-gsd-phase-gates` | Approval gate, SessionPhase machine | implemented |
| `uai-layer-gsd-wave-execution` | Wave-based parallel execution | implemented |
| `uai-layer-gsd-state-persist` | `.planning/` artifacts | implemented |
| `uai-layer-gsd-verification` | Goal-backward work_verifier | implemented |

## Отличия от полного GSD

| Feature | GSD upstream | This project (v1.0) |
|---------|--------------|---------------------|
| Subagent isolation | Fresh 200k context per subagent | In-process via `SessionStore` |
| Platform support | 15+ платформ | Любой MCP client |
| Roadmap/Milestones | PROJECT.md, ROADMAP.md | `.planning/STATE.md` + `CONTEXT.md` |
| Model profiles | quality/balanced/budget | tier routing (heavy/balanced/fast) |

Subprocess-level isolation — см. `uai-layer-bp-subagent-patterns` (planned v2.0).
