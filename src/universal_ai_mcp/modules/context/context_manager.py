"""Context manager — tracks token usage and triggers compression when approaching limits.

Keeps context utilization below the configured target ratio by converting
raw content to IdeaBlocks before it enters the active context window.
"""

from __future__ import annotations

import structlog

from universal_ai_mcp.core.config import ServerSettings
from universal_ai_mcp.entities.idea_block_entity import IdeaBlockCollection
from universal_ai_mcp.entities.session_entity import AgentSession
from universal_ai_mcp.modules.context.idea_block_builder import IdeaBlockBuilder
from universal_ai_mcp.modules.context.idea_block_distiller import IdeaBlockDistiller
from universal_ai_mcp.modules.context.semantic_compressor import SemanticCompressor

log = structlog.get_logger(__name__)


class ContextManager:
    """Monitors token budget per session and compresses context on demand."""

    def __init__(
        self,
        settings: ServerSettings,
        builder: IdeaBlockBuilder,
        compressor: SemanticCompressor,
        distiller: IdeaBlockDistiller | None = None,
    ) -> None:
        self._settings = settings
        self._builder = builder
        self._compressor = compressor
        self._distiller = distiller

    async def add_content(
        self,
        session: AgentSession,
        content: str,
        source_ref: str | None = None,
    ) -> IdeaBlockCollection:
        """Convert raw content to IdeaBlocks and add to session context."""
        collection = await self._builder.build(content, source_ref)

        # Run LLM-based distillation if distiller is configured
        if self._distiller and len(collection.blocks) > 1:
            collection = await self._distiller.distill(collection)

        existing = session.idea_block_collection
        if existing:
            merged_blocks = existing.blocks + collection.blocks
            collection = IdeaBlockCollection(
                blocks=merged_blocks,
                source_token_count=existing.source_token_count + collection.source_token_count,
                compressed_token_count=existing.compressed_token_count
                + collection.compressed_token_count,
            )

        session.context_token_usage = collection.total_tokens()

        if self._should_compress(session):
            log.info("context_compression_triggered", session=str(session.id))
            collection = await self._compressor.compress(
                collection,
                target_tokens=self._target_token_budget(),
            )
            session.context_token_usage = collection.total_tokens()

        session.idea_block_collection = collection
        return collection

    def get_context(self, session: AgentSession) -> IdeaBlockCollection | None:
        return session.idea_block_collection

    def get_context_xml(self, session: AgentSession) -> str:
        collection = self.get_context(session)
        if not collection:
            return "<KnowledgeContext blocks='0'/>"
        return collection.to_xml_context()

    def token_usage(self, session: AgentSession) -> int:
        return session.context_token_usage

    def _should_compress(self, session: AgentSession) -> bool:
        budget = self._settings.context_max_tokens
        target = self._settings.context_target_ratio
        return session.context_token_usage > budget * target

    def _target_token_budget(self) -> int:
        return int(
            self._settings.context_max_tokens * self._settings.context_target_ratio * 0.8
        )
