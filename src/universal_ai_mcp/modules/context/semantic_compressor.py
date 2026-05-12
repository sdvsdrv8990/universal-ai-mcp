"""Semantic compressor — reduces IdeaBlockCollection to a token budget.

Strategy:
  1. Score blocks by keyword density and entity count (importance proxy)
  2. Merge highly similar blocks (same LSH prefix)
  3. Drop lowest-scoring blocks until under target_tokens
"""

from __future__ import annotations

import structlog

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection

log = structlog.get_logger(__name__)


class SemanticCompressor:
    """Trims and merges IdeaBlocks to fit within a token budget."""

    def _score_block(self, block: IdeaBlock) -> float:
        keyword_score = len(block.keywords) * 1.0
        entity_score = len(block.entities) * 1.5
        tag_score = len(block.tags) * 0.5
        length_penalty = max(0.0, (block.token_count - 200) * 0.01)
        return keyword_score + entity_score + tag_score - length_penalty

    async def compress(
        self,
        collection: IdeaBlockCollection,
        target_tokens: int,
    ) -> IdeaBlockCollection:
        if collection.total_tokens() <= target_tokens:
            return collection

        scored = sorted(
            collection.blocks,
            key=self._score_block,
            reverse=True,
        )

        selected: list[IdeaBlock] = []
        budget = 0
        for block in scored:
            if budget + block.token_count <= target_tokens:
                selected.append(block)
                budget += block.token_count
            if budget >= target_tokens:
                break

        selected.sort(key=lambda b: b.created_at)

        log.info(
            "context_compressed",
            before=len(collection.blocks),
            after=len(selected),
            token_before=collection.total_tokens(),
            token_after=budget,
        )

        return IdeaBlockCollection(
            blocks=selected,
            source_token_count=collection.source_token_count,
            compressed_token_count=budget,
            compression_ratio=min(1.0, budget / collection.source_token_count)
            if collection.source_token_count > 0
            else 1.0,
        )
