"""Block memory bridge — persists IdeaBlocks to ChromaDB for cross-session retrieval.

Bridges two modules that must stay decoupled:
  context/   — builds IdeaBlocks in memory (fast, per-session)
  memory/    — persists MemoryEntries in ChromaDB (durable, cross-session)

Each IdeaBlock is indexed as a QA pair:
  content = "Q: <critical_question>\\n\\nA: <trusted_answer>"

This format maximises vector search accuracy: the critical_question is the
natural search query, and the trusted_answer is the relevant fact to retrieve.

Source key convention:
  GLOBAL scope  → "idea_blocks:global"
  PROJECT scope → "idea_blocks:<project_path>"
"""

from __future__ import annotations

import structlog

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.entities.memory_entity import IndexResult, MemoryScope
from universal_ai_mcp.modules.memory.memory_indexer import MemoryIndexer

log = structlog.get_logger(__name__)


def _block_to_text(block: IdeaBlock) -> str:
    """Format a single IdeaBlock as a QA pair for vector indexing."""
    return f"Q: {block.critical_question}\n\nA: {block.trusted_answer}"


class BlockMemoryBridge:
    """Writes IdeaBlocks into the MemoryIndexer so they survive session boundaries.

    After a session ends, the persisted blocks can be retrieved via
    MemoryRetriever.search() using the critical_question as the query.
    """

    def __init__(self, indexer: MemoryIndexer) -> None:
        self._indexer = indexer

    async def persist(
        self,
        collection: IdeaBlockCollection,
        scope: MemoryScope,
        project_path: str | None = None,
    ) -> IndexResult:
        """Index all IdeaBlocks in the collection into ChromaDB.

        Idempotent: blocks whose content_hash already exists are skipped.
        Returns an IndexResult summarising what was indexed vs. skipped.
        """
        if not collection.blocks:
            return IndexResult(
                source=_source_key(scope, project_path),
                scope=scope,
                chunks_indexed=0,
                embedding_model="",
            )

        source_key = _source_key(scope, project_path)

        # Join all blocks as QA pairs separated by a clear delimiter.
        # MemoryIndexer will rechunk this text with its own 512-token chunker,
        # so the bridge does NOT need to manage chunk size.
        full_text = "\n\n---\n\n".join(_block_to_text(b) for b in collection.blocks)

        result = await self._indexer.index_text(
            text=full_text,
            source=source_key,
            scope=scope,
            project_path=project_path,
            library_name=None,
        )

        log.info(
            "blocks_persisted_to_memory",
            blocks=len(collection.blocks),
            chunks_indexed=result.chunks_indexed,
            chunks_skipped=result.chunks_skipped,
            scope=scope.value,
            source=source_key,
        )
        return result

    async def persist_single(
        self,
        block: IdeaBlock,
        scope: MemoryScope,
        project_path: str | None = None,
    ) -> IndexResult:
        """Persist a single IdeaBlock. Useful for incremental updates."""
        source_key = _source_key(scope, project_path)
        return await self._indexer.index_text(
            text=_block_to_text(block),
            source=source_key,
            scope=scope,
            project_path=project_path,
        )


def _source_key(scope: MemoryScope, project_path: str | None) -> str:
    if scope == MemoryScope.PROJECT and project_path:
        return f"idea_blocks:{project_path}"
    return "idea_blocks:global"
