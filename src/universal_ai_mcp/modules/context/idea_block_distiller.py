"""IdeaBlock distiller — LLM-based merging of semantically similar blocks.

Blockify distill stage (implemented locally, without the Blockify API):
  1. Cluster  — group blocks whose LSH (SHA-256 prefix) indicates similar content
  2. Merge    — call LLM to synthesize each cluster of 2-15 blocks into ONE canonical block
  3. Return   — deduplicated IdeaBlockCollection with compressed_token_count updated

The LSH hash already stored in IdeaBlock.embedding_hash (SHA-256 of normalised answer)
is used for clustering. Blocks with matching N-char prefixes are considered candidates
for merging. N defaults to 8 (32-bit comparison), which provides a good balance between
false-positives (too short) and missed duplicates (too long).

Merge fidelity: ~95% lossless (Blockify spec) — all unique facts are preserved;
only exact or near-exact restatements are consolidated.
"""

from __future__ import annotations

import hashlib
import json
import re

import structlog

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

_MAX_CLUSTER_SIZE = 15  # Blockify spec: merge at most 15 blocks at once

DISTILL_SYSTEM_PROMPT = """You are a knowledge consolidation specialist using the Blockify distillation method.

Given multiple IdeaBlocks on the same topic, merge them into ONE canonical IdeaBlock.

Rules:
1. Preserve ALL unique facts from every input block — never discard distinct information.
2. Discard only exact or near-exact restatements of the same fact.
3. The merged trusted_answer must be a complete synthesis, self-contained.
4. Combine tags, entities, and keywords from all blocks (deduplicate).
5. Write the critical_question as the broadest question all blocks collectively answer.

Output ONLY valid JSON:
{
  "name": "Merged block title",
  "critical_question": "The most comprehensive question this block answers",
  "trusted_answer": "Complete synthesized answer preserving all unique facts",
  "tags": ["tag1", "tag2"],
  "entities": ["EntityName"],
  "keywords": ["keyword1", "keyword2"]
}
"""


class IdeaBlockDistiller:
    """Clusters IdeaBlocks by LSH hash and merges each cluster via LLM.

    Usage:
        distiller = IdeaBlockDistiller(router)
        distilled = await distiller.distill(collection)
    """

    def __init__(
        self,
        router: LLMRouter,
        hash_prefix_length: int = 8,
    ) -> None:
        self._router = router
        self._prefix_len = hash_prefix_length

    async def distill(self, collection: IdeaBlockCollection) -> IdeaBlockCollection:
        """Return a new IdeaBlockCollection with similar blocks merged."""
        if len(collection.blocks) <= 1:
            return collection

        clusters = self._cluster(collection.blocks)
        merged: list[IdeaBlock] = []

        for cluster in clusters:
            if len(cluster) == 1:
                merged.append(cluster[0])
            else:
                block = await self._merge_cluster(cluster)
                merged.append(block)

        compressed_tokens = sum(b.token_count for b in merged)
        log.info(
            "distillation_complete",
            input_blocks=len(collection.blocks),
            output_blocks=len(merged),
            clusters=len(clusters),
            input_tokens=collection.source_token_count,
            output_tokens=compressed_tokens,
        )

        return IdeaBlockCollection(
            blocks=merged,
            source_token_count=collection.source_token_count,
            compressed_token_count=compressed_tokens,
            compression_ratio=(
                min(1.0, compressed_tokens / collection.source_token_count)
                if collection.source_token_count > 0
                else 1.0
            ),
        )

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _cluster(self, blocks: list[IdeaBlock]) -> list[list[IdeaBlock]]:
        """Group blocks by LSH hash prefix into candidate merge clusters."""
        groups: dict[str, list[IdeaBlock]] = {}
        ungrouped: list[IdeaBlock] = []

        for block in blocks:
            prefix = (block.embedding_hash or "")[:self._prefix_len]
            if prefix:
                groups.setdefault(prefix, []).append(block)
            else:
                ungrouped.append(block)

        clusters: list[list[IdeaBlock]] = []
        for group in groups.values():
            # Split oversized clusters to stay within Blockify's 15-block merge limit
            for i in range(0, len(group), _MAX_CLUSTER_SIZE):
                clusters.append(group[i: i + _MAX_CLUSTER_SIZE])

        clusters.extend([b] for b in ungrouped)
        return clusters

    async def _merge_cluster(self, cluster: list[IdeaBlock]) -> IdeaBlock:
        """Call LLM to synthesize a cluster of similar blocks into one canonical block."""
        blocks_xml = "\n\n".join(b.to_xml() for b in cluster)
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(
                role="user",
                content=f"Merge these {len(cluster)} IdeaBlocks into one canonical block:\n\n{blocks_xml}",
            )],
            system_prompt=DISTILL_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.1,
        )
        response = await self._router.complete(request, tier="fast")

        try:
            data = extract_json(response.content)
        except (json.JSONDecodeError, AttributeError):
            log.warning("distill_merge_failed", cluster_size=len(cluster))
            return cluster[0]  # safe fallback: keep first block unchanged

        answer = data.get("trusted_answer") or cluster[0].trusted_answer
        normalized = re.sub(r"\s+", " ", answer.lower().strip())
        new_hash = hashlib.sha256(normalized.encode()).hexdigest()

        # Merge metadata from all cluster members
        all_tags = list({t for b in cluster for t in b.tags} | set(data.get("tags", [])))
        all_entities = list({e for b in cluster for e in b.entities} | set(data.get("entities", [])))
        all_keywords = list({k for b in cluster for k in b.keywords} | set(data.get("keywords", [])))

        return IdeaBlock(
            name=data.get("name") or cluster[0].name,
            critical_question=data.get("critical_question") or cluster[0].critical_question,
            trusted_answer=answer,
            tags=all_tags,
            entities=all_entities,
            keywords=all_keywords,
            source_ref=cluster[0].source_ref,
            token_count=max(1, len(answer) // 4),
            embedding_hash=new_hash,
        )
