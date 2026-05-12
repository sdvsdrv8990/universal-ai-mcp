# IdeaBlock Spec — Pointer

> Содержимое перенесено в skills. Этот файл сохранён для git-history.

Полная спека IdeaBlock entity, ingestion flow, и LSH-deduplication алгоритма теперь в:

- **Entity + Ingest** → skill `uai-layer-blockify-ingest`
- **LSH dedup + Distill** → skill `uai-layer-blockify-distill`

Загрузи нужный skill через Skill tool.

## Quick reference

`IdeaBlock` (`src/universal_ai_mcp/entities/idea_block_entity.py`) поля:

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | auto-generated |
| `name` | str | short label |
| `critical_question` | str | the one question this answers |
| `trusted_answer` | str | self-contained answer |
| `tags`, `entities`, `keywords` | list[str] | retrieval metadata |
| `token_count` | int | `len(answer) // 4` ±20% |
| `embedding_hash` | str? | SHA-256 of normalized answer |

Изменения относительно source repo (TypeScript `blockify-skill-for-claude-code/`):
1. Pydantic вместо TypeScript interface
2. SHA-256 prefix вместо full LSH (sidecar service в v2.0)
3. Добавлено поле `token_count` для budget tracking
4. `to_xml()` сериализация совпадает с original XML schema
