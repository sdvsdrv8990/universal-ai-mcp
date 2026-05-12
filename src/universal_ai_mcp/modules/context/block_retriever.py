"""Block retriever — semantic search over individually indexed IdeaBlocks.

Completes the Blockify three-stage pipeline: Ingest → Distill → Retrieve.

Design vs BlockMemoryBridge:
  BlockMemoryBridge  — joins all blocks into one text string, rechunks for
                        cross-session storage. Tags and block boundaries lost.
  BlockRetriever     — upserts each block as a single ChromaDB entry with all
                        metadata preserved. Enables typed retrieval + tag filtering.

Use both: bridge for durable cross-session text, retriever for typed lookup.

Tag filtering note: ChromaDB does not support native list-value filtering in
metadata. Tags are stored as JSON strings and filtered in Python after vector
search. To keep enough candidates, the query fetches limit*3 when filter_tags
is set before applying the Python filter.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import structlog

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.modules.memory.embedding_provider import (
    EmbeddingError,
    OllamaEmbeddingProvider,
)
from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore, VectorStoreError

log = structlog.get_logger(__name__)

_COLLECTION = "idea_blocks"
# Oversample factor when tag post-filtering to ensure enough candidates survive
_TAG_OVERSAMPLE = 3


class BlockRetriever:
    """Index and query IdeaBlocks via vector similarity with optional tag filtering."""

    def __init__(
        self,
        store: MemoryVectorStore,
        embedder: OllamaEmbeddingProvider,
    ) -> None:
        self._store = store
        self._embedder = embedder

    async def index(self, collection: IdeaBlockCollection) -> int:
        """Upsert every block individually, preserving all metadata.

        Idempotent: block.id is the ChromaDB entry ID so re-indexing
        the same block updates it in place without creating duplicates.

        Returns the count of blocks written (0 if embedder unavailable — fail-open).
        """
        if not collection.blocks:
            return 0

        texts = [_to_search_text(b) for b in collection.blocks]
        try:
            embeddings = await self._embedder.embed(texts)
        except EmbeddingError as exc:
            log.warning("block_index_embed_failed", error=str(exc), blocks=len(texts))
            return 0

        self._store.upsert(
            collection_name=_COLLECTION,
            ids=[str(b.id) for b in collection.blocks],
            documents=texts,
            embeddings=embeddings,
            metadatas=[_to_metadata(b) for b in collection.blocks],
        )
        log.info("blocks_indexed", count=len(collection.blocks), collection=_COLLECTION)
        return len(collection.blocks)

    async def query(
        self,
        query: str,
        limit: int = 10,
        filter_tags: list[str] | None = None,
    ) -> list[IdeaBlock]:
        """Semantic search over indexed IdeaBlocks.

        filter_tags: Python post-filter — only blocks whose tags intersect with
        filter_tags are returned. Fetches limit*3 candidates first to ensure
        enough survive the filter.

        Returns [] on any infrastructure failure (fail-open, never raises).
        """
        try:
            query_embedding = await self._embedder.embed_one(query)
        except EmbeddingError as exc:
            log.warning("block_query_embed_failed", error=str(exc))
            return []

        fetch_k = limit * _TAG_OVERSAMPLE if filter_tags else limit

        try:
            raw = self._store.query(
                collection_name=_COLLECTION,
                query_embedding=query_embedding,
                top_k=fetch_k,
            )
        except VectorStoreError as exc:
            log.warning("block_query_store_failed", error=str(exc))
            return []

        blocks = _from_chroma_result(raw)

        if filter_tags:
            tag_set = set(filter_tags)
            blocks = [b for b in blocks if tag_set.intersection(b.tags)]

        result = blocks[:limit]
        log.info(
            "blocks_retrieved",
            query=query[:60],
            filter_tags=filter_tags,
            candidates=len(blocks),
            returned=len(result),
        )
        return result


# ──────────────────────────────────────────────────────────────────────────────
# Serialization helpers (module-private)
# ──────────────────────────────────────────────────────────────────────────────

def _to_search_text(block: IdeaBlock) -> str:
    """Text that gets embedded — same QA format as BlockMemoryBridge."""
    return f"Q: {block.critical_question}\n\nA: {block.trusted_answer}"


def _to_metadata(block: IdeaBlock) -> dict[str, str | int | float]:
    """Flatten IdeaBlock to ChromaDB-compatible flat metadata (str/int/float only)."""
    return {
        "name": block.name,
        "critical_question": block.critical_question,
        "trusted_answer": block.trusted_answer,
        "tags": json.dumps(block.tags),
        "entities": json.dumps(block.entities),
        "keywords": json.dumps(block.keywords),
        "source_ref": block.source_ref or "",
        "token_count": block.token_count,
        "embedding_hash": block.embedding_hash or "",
        "created_at": block.created_at.isoformat(),
    }


def _from_chroma_result(raw: dict) -> list[IdeaBlock]:
    """Reconstruct typed IdeaBlocks from a ChromaDB query result dict."""
    ids = (raw.get("ids") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    blocks: list[IdeaBlock] = []
    for block_id, meta in zip(ids, metas):
        try:
            blocks.append(
                IdeaBlock(
                    id=UUID(block_id),
                    name=str(meta["name"]),
                    critical_question=str(meta["critical_question"]),
                    trusted_answer=str(meta["trusted_answer"]),
                    tags=json.loads(str(meta.get("tags", "[]"))),
                    entities=json.loads(str(meta.get("entities", "[]"))),
                    keywords=json.loads(str(meta.get("keywords", "[]"))),
                    source_ref=str(meta["source_ref"]) or None,
                    token_count=int(meta.get("token_count", 0)),
                    embedding_hash=str(meta.get("embedding_hash")) or None,
                    created_at=datetime.fromisoformat(str(meta["created_at"])),
                )
            )
        except Exception as exc:
            log.warning("block_parse_error", block_id=block_id, error=str(exc))
    return blocks
