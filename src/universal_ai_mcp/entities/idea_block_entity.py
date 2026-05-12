"""IdeaBlock entity — Blockify-inspired semantic knowledge unit.

Based on: github.com/iternal-technologies-partners/blockify-agentic-data-optimization
Each IdeaBlock addresses a single critical question with a trusted answer,
enabling 40x dataset compression and 3x token efficiency vs. naive chunking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class IdeaBlock(BaseModel):
    """Single semantic knowledge unit addressing one critical question."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(description="Short human-readable label for this block")
    critical_question: str = Field(description="The question this block answers")
    trusted_answer: str = Field(description="Authoritative answer to the critical question")
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list, description="Named entities referenced")
    keywords: list[str] = Field(default_factory=list)
    source_ref: str | None = Field(default=None, description="Origin file or URL")
    token_count: int = Field(default=0, description="Estimated token cost of this block")
    embedding_hash: str | None = Field(default=None, description="LSH hash for deduplication")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_xml(self) -> str:
        """Serialize to Blockify XML format for LLM consumption."""
        tags_str = ", ".join(self.tags)
        entities_str = ", ".join(self.entities)
        keywords_str = ", ".join(self.keywords)
        return (
            f"<IdeaBlock id='{self.id}'>\n"
            f"  <Name>{self.name}</Name>\n"
            f"  <CriticalQuestion>{self.critical_question}</CriticalQuestion>\n"
            f"  <TrustedAnswer>{self.trusted_answer}</TrustedAnswer>\n"
            f"  <Tags>{tags_str}</Tags>\n"
            f"  <Entities>{entities_str}</Entities>\n"
            f"  <Keywords>{keywords_str}</Keywords>\n"
            f"</IdeaBlock>"
        )


class IdeaBlockCollection(BaseModel):
    """Ordered collection of IdeaBlocks representing an optimized context."""

    blocks: list[IdeaBlock] = Field(default_factory=list)
    source_token_count: int = Field(default=0, description="Tokens before compression")
    compressed_token_count: int = Field(default=0, description="Tokens after compression")
    compression_ratio: Annotated[float, Field(ge=0.0, le=1.0)] = Field(default=1.0)

    def total_tokens(self) -> int:
        return sum(b.token_count for b in self.blocks)

    def to_xml_context(self) -> str:
        """Render all blocks as a compact XML context string."""
        blocks_xml = "\n\n".join(b.to_xml() for b in self.blocks)
        return f"<KnowledgeContext blocks='{len(self.blocks)}'>\n{blocks_xml}\n</KnowledgeContext>"

    def filter_by_tags(self, tags: list[str]) -> "IdeaBlockCollection":
        filtered = [b for b in self.blocks if any(t in b.tags for t in tags)]
        return IdeaBlockCollection(blocks=filtered)
