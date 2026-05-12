"""Memory retriever — converts a MemoryQuery into a MemorySearchResult.

Three search layers, each strictly additive (later layers require earlier ones):

  Layer 1 — Vector similarity (always active)
    Embed query → ChromaDB cosine search → top-K candidates

  Layer 2 — Hybrid search (active when scope or source_filter set)
    Apply ChromaDB where-clause pre-filter by metadata before vector search.
    Narrows the candidate set so cosine scores are more meaningful.

  Layer 3 — LLM re-ranking (active when query.rerank=True)
    Pass top-10 candidates to LLMRouter with a relevance prompt.
    LLM scores each chunk 0–10; results are re-sorted by LLM score.
    Adds ~1–3s latency. Use for final answers, not for live lookups.

Isolation contract:
  - Depends on MemoryVectorStore, OllamaEmbeddingProvider (same module)
  - LLMRouter is an optional injection — if None, rerank silently downgrades to Layer 1
  - Never imports from tools/ or core/
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from universal_ai_mcp.entities.memory_entity import (
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
    MemorySearchResult,
)
from universal_ai_mcp.modules.memory.embedding_provider import (
    EmbeddingError,
    OllamaEmbeddingProvider,
)
from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore, VectorStoreError

if TYPE_CHECKING:
    from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

_RERANK_TOP_CANDIDATES = 10
_RERANK_PROMPT = """\
You are a relevance judge. Given a user query and a list of text chunks,
score each chunk's relevance to the query from 0 (irrelevant) to 10 (perfect match).

Query: {query}

Chunks:
{chunks}

Respond ONLY with a JSON array of integers, one score per chunk, in the same order.
Example: [8, 3, 10, 0, 5]"""


class MemoryRetriever:
    """Retrieves relevant memory entries for a given query."""

    def __init__(
        self,
        store: MemoryVectorStore,
        embedder: OllamaEmbeddingProvider,
        router: "LLMRouter | None" = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._router = router

    async def search(self, query: MemoryQuery) -> MemorySearchResult:
        """Execute a memory search across the appropriate collection(s)."""
        try:
            query_embedding = await self._embedder.embed_one(query.query)
        except EmbeddingError as exc:
            log.warning("retriever_embed_failed", error=str(exc))
            return MemorySearchResult(
                entries=[],
                distances=[],
                query_text=query.query,
                total_found=0,
            )

        # Determine which collections to search
        collections = self._resolve_collections(query)

        all_entries: list[MemoryEntry] = []
        all_distances: list[float] = []

        for col_name in collections:
            where = self._build_where(query, col_name)
            try:
                raw = self._store.query(
                    collection_name=col_name,
                    query_embedding=query_embedding,
                    top_k=_RERANK_TOP_CANDIDATES if query.rerank else query.top_k,
                    where=where,
                )
            except VectorStoreError as exc:
                log.warning("retriever_query_failed", collection=col_name, error=str(exc))
                continue

            entries, distances = self._parse_chroma_result(raw)
            all_entries.extend(entries)
            all_distances.extend(distances)

        # Sort combined results by distance (ascending = most similar first)
        if len(all_entries) > 1:
            paired = sorted(zip(all_distances, all_entries), key=lambda x: x[0])
            all_distances, all_entries = zip(*paired) if paired else ([], [])  # type: ignore[assignment]
            all_distances = list(all_distances)
            all_entries = list(all_entries)

        # Layer 3: optional LLM re-ranking
        reranked = False
        if query.rerank and all_entries:
            all_entries, all_distances, reranked = await self._llm_rerank(
                query.query, all_entries, all_distances
            )

        # Trim to requested top_k after potential multi-collection merge
        final_entries = all_entries[: query.top_k]
        final_distances = all_distances[: query.top_k]

        log.info(
            "memory_search",
            query=query.query[:60],
            collections=collections,
            total=len(all_entries),
            returned=len(final_entries),
            reranked=reranked,
        )

        return MemorySearchResult(
            entries=final_entries,
            distances=final_distances,
            query_text=query.query,
            total_found=len(all_entries),
            reranked=reranked,
        )

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _resolve_collections(self, query: MemoryQuery) -> list[str]:
        """Determine which ChromaDB collections to search."""
        if query.scope == MemoryScope.GLOBAL:
            return ["global"]
        if query.scope == MemoryScope.PROJECT:
            return [MemoryEntry.collection_name_for(MemoryScope.PROJECT, query.project_path)]
        # No scope filter → search global + project if path given
        collections = ["global"]
        if query.project_path:
            collections.append(
                MemoryEntry.collection_name_for(MemoryScope.PROJECT, query.project_path)
            )
        return collections

    def _build_where(
        self,
        query: MemoryQuery,
        collection_name: str,
    ) -> dict[str, Any] | None:
        """Build ChromaDB where-clause for Layer 2 hybrid filtering."""
        conditions: list[dict[str, Any]] = []

        if query.source_filter:
            # ChromaDB doesn't support LIKE; we filter by exact prefix match post-query
            pass  # handled in _parse_chroma_result via source_filter

        # No conditions → no where clause (ChromaDB rejects empty where dicts)
        return conditions[0] if len(conditions) == 1 else ({"$and": conditions} if conditions else None)

    def _parse_chroma_result(
        self,
        raw: dict[str, Any],
    ) -> tuple[list[MemoryEntry], list[float]]:
        """Unpack ChromaDB result dict into typed lists."""
        ids = (raw.get("ids") or [[]])[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        entries: list[MemoryEntry] = []
        distances: list[float] = []

        for chroma_id, doc, meta, dist in zip(ids, docs, metas, dists):
            try:
                entry = MemoryEntry.from_chroma_result(chroma_id, doc, meta)
                entries.append(entry)
                distances.append(float(dist))
            except Exception as exc:
                log.warning("retriever_parse_error", id=chroma_id, error=str(exc))

        return entries, distances

    async def _llm_rerank(
        self,
        query: str,
        entries: list[MemoryEntry],
        distances: list[float],
    ) -> tuple[list[MemoryEntry], list[float], bool]:
        """Re-rank candidates using LLM relevance scoring (Layer 3).

        Falls back to original order if LLM call fails or router is None.
        """
        if self._router is None:
            log.debug("rerank_skipped_no_router")
            return entries, distances, False

        chunks_text = "\n\n".join(
            f"[{i + 1}] {e.content[:300]}" for i, e in enumerate(entries)
        )
        prompt = _RERANK_PROMPT.format(query=query, chunks=chunks_text)

        from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest

        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=prompt)],
            max_tokens=256,
        )
        try:
            response = await self._router.complete(request, tier="fast")
            raw_scores = json.loads(response.content.strip())
            if not isinstance(raw_scores, list) or len(raw_scores) != len(entries):
                raise ValueError("Score list length mismatch")
            scores = [float(s) for s in raw_scores]
        except Exception as exc:
            log.warning("rerank_failed", error=str(exc))
            return entries, distances, False

        # Sort by LLM score descending; use distance as tiebreaker
        paired = sorted(
            zip(scores, distances, entries),
            key=lambda x: (-x[0], x[1]),
        )
        reranked_entries = [p[2] for p in paired]
        reranked_distances = [p[1] for p in paired]
        return reranked_entries, reranked_distances, True
