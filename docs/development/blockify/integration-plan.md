# Blockify Integration Plan — Pointer

> Содержимое перенесено в skills + master-plan. Файл сохранён для git-history.

## v1.0 status

Все три слоя имеют свои skills с актуальными чеклистами:

- `uai-layer-blockify-ingest` (implemented)
- `uai-layer-blockify-distill` (implemented)
- `uai-layer-blockify-retrieve` (planned v2.0)

## v2.0 roadmap

См. [`../master-plan.md`](../master-plan.md) — единая roadmap для всех слоёв в контексте unified dev-system.

Краткая выжимка по Blockify v2.0:
- Full distillation sidecar (`blockify-distillation-service` Docker)
- Vector storage integration (Qdrant/Milvus/ChromaDB)
- Reference API: `POST /distill`, `GET /retrieve`

Подробности — в чеклистах соответствующих skills.
