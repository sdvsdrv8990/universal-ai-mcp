"""IdeaBlock builder — converts raw text/code into structured semantic units.

Based on Blockify's three-stage pipeline:
  1. Ingest  — extract draft IdeaBlocks from raw content
  2. Distill — deduplicate via LSH hash comparison (stub: full LSH requires separate service)
  3. Retrieve — return optimized collection ordered by relevance

Token efficiency target: ~3x reduction vs. raw text injection.
"""

from __future__ import annotations

import hashlib
import json
import re

import structlog

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.context.content_chunker import ContentChunker
from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

INGEST_SYSTEM_PROMPT = """You are a knowledge extraction specialist using the Blockify method.

Convert the given content into a list of IdeaBlocks. Each IdeaBlock must:
1. Address exactly ONE critical question about the content.
2. Provide a trusted, self-contained answer.
3. Include relevant tags, named entities, and keywords.
4. Be as concise as possible while remaining complete.

Output ONLY valid JSON:
{
  "blocks": [
    {
      "name": "Short label",
      "critical_question": "What question does this answer?",
      "trusted_answer": "Self-contained answer.",
      "tags": ["tag1"],
      "entities": ["EntityName"],
      "keywords": ["keyword1"]
    }
  ]
}
"""


class IdeaBlockBuilder:
    """Converts raw content into an optimized IdeaBlockCollection."""

    def __init__(self, router: LLMRouter, merge_threshold: float = 0.85) -> None:
        self._router = router
        self._merge_threshold = merge_threshold

    async def build(
        self,
        content: str,
        source_ref: str | None = None,
    ) -> IdeaBlockCollection:
        source_tokens = self._estimate_tokens(content)

        raw_blocks = await self._ingest(content, source_ref)
        deduplicated = self._distill(raw_blocks)

        compressed_tokens = sum(b.token_count for b in deduplicated)
        ratio = min(1.0, compressed_tokens / source_tokens) if source_tokens > 0 else 1.0

        log.info(
            "idea_blocks_built",
            source_tokens=source_tokens,
            compressed_tokens=compressed_tokens,
            ratio=f"{ratio:.2f}",
            blocks=len(deduplicated),
        )

        return IdeaBlockCollection(
            blocks=deduplicated,
            source_token_count=source_tokens,
            compressed_token_count=compressed_tokens,
            compression_ratio=ratio,
        )

    async def _ingest(
        self, content: str, source_ref: str | None
    ) -> list[IdeaBlock]:
        from universal_ai_mcp.modules.llm.json_extractor import extract_json

        chunker = ContentChunker()
        chunks = chunker.chunk(content)

        all_blocks: list[IdeaBlock] = []
        for chunk in chunks:
            request = LLMRequest(
                model="auto",
                messages=[LLMMessage(role="user", content=f"Content to extract:\n\n{chunk}")],
                system_prompt=INGEST_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.1,
                response_format={
                    "type": "object",
                    "properties": {"blocks": {"type": "array"}},
                    "required": ["blocks"],
                },
            )
            response = await self._router.complete(request, tier="fast")

            try:
                data = extract_json(response.content)
                raw: list[dict] = data.get("blocks", [])
            except (json.JSONDecodeError, KeyError, AttributeError):
                log.warning("ingest_parse_failed", source=source_ref, preview=response.content[:200])
                continue

            for item in raw:
                answer = item.get("trusted_answer", "")
                block = IdeaBlock(
                    name=item.get("name", "unnamed"),
                    critical_question=item.get("critical_question", ""),
                    trusted_answer=answer,
                    tags=item.get("tags", []),
                    entities=item.get("entities", []),
                    keywords=item.get("keywords", []),
                    source_ref=source_ref,
                    token_count=self._estimate_tokens(answer),
                    embedding_hash=self._lsh_hash(answer),
                )
                all_blocks.append(block)

        return all_blocks

    def _distill(self, blocks: list[IdeaBlock]) -> list[IdeaBlock]:
        """Deduplicate blocks using LSH hash prefix comparison."""
        seen_hashes: dict[str, IdeaBlock] = {}
        unique: list[IdeaBlock] = []

        for block in blocks:
            h = block.embedding_hash or ""
            prefix = h[:8]  # compare first 8 hex chars (~32 bits)
            if prefix in seen_hashes:
                log.debug("block_deduplicated", name=block.name)
                continue
            seen_hashes[prefix] = block
            unique.append(block)

        return unique

    def _lsh_hash(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
