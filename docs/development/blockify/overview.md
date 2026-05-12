# Blockify — Source Pointer

> Полное содержимое слоёв вынесено в skills. Здесь — только ссылки и метаданные.

**Источник:** github.com/iternal-technologies-partners/blockify-agentic-data-optimization

## Skills (runtime слои)

| Skill | Layer | Status |
|-------|-------|--------|
| [`uai-layer-blockify-ingest`](../../../../home/admin/.claude/skills/uai-layer-blockify-ingest/SKILL.md) | LLM extraction → IdeaBlock | implemented |
| [`uai-layer-blockify-distill`](../../../../home/admin/.claude/skills/uai-layer-blockify-distill/SKILL.md) | LSH dedup + LLM merge | implemented |
| [`uai-layer-blockify-retrieve`](../../../../home/admin/.claude/skills/uai-layer-blockify-retrieve/SKILL.md) | Vector storage | planned (v2.0) |

## Метрики (из source repo)

| Метрика | Улучшение |
|---------|-----------|
| Aggregate enterprise performance | 78× |
| Vector search accuracy | 2.29× |
| Dataset size reduction | 40× (до ~2.5% от исходного) |
| Token efficiency | 3.09× |

## Что в этой директории

- `overview.md` — этот файл (pointer)
- `idea-blocks-spec.md` — pointer на ingest/distill skills для деталей IdeaBlock entity
- `integration-plan.md` — pointer на skills + master-plan для v2.0 roadmap
