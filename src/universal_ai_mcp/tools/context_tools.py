"""Context module MCP tools — token optimization via Blockify IdeaBlocks.

Registered tools:
  - context_add_content      : convert raw text/code to IdeaBlocks and add to session
  - context_get_xml          : return current session context as compact XML
  - context_token_usage      : report token budget consumption
  - context_compress_now     : force immediate compression
  - context_persist_blocks   : persist session IdeaBlocks to ChromaDB for cross-session retrieval
  - context_retrieve_blocks  : semantic search over indexed IdeaBlocks with optional tag filter
"""

from __future__ import annotations

import json
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.idea_block_entity import IdeaBlockCollection
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="context",
    display_name="Context Optimizer (Blockify)",
    description=(
        "Converts raw content to IdeaBlocks for 3x token efficiency. "
        "Tracks session token budget and triggers automatic compression "
        "when approaching the configured limit."
    ),
    scenarios=[
        ModuleScenario(
            name="ingest_codebase",
            description="Parse project files into IdeaBlocks before starting a task",
            scenario_type=ScenarioType.SYSTEM,
            required_tools=["context_add_content"],
        ),
        ModuleScenario(
            name="budget_check",
            description="Monitor token usage during long sessions",
            scenario_type=ScenarioType.USER,
            required_tools=["context_token_usage"],
        ),
        ModuleScenario(
            name="persist_for_next_session",
            description="Save distilled IdeaBlocks to vector store before ending a session",
            scenario_type=ScenarioType.USER,
            required_tools=["context_persist_blocks"],
        ),
    ],
    mcp_tools=[
        "context_add_content",
        "context_get_xml",
        "context_token_usage",
        "context_compress_now",
        "context_persist_blocks",
        "context_retrieve_blocks",
    ],
)


def register_context_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def context_add_content(
        content: str,
        session_id: str,
        source_ref: str | None = None,
    ) -> str:
        """Convert raw text or code into IdeaBlocks and add to session context.

        This significantly reduces token consumption for repeated context references.
        Returns compression statistics (source tokens vs. compressed tokens).
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.context.context_manager import ContextManager
        from universal_ai_mcp.modules.context.idea_block_builder import IdeaBlockBuilder
        from universal_ai_mcp.modules.context.idea_block_distiller import IdeaBlockDistiller
        from universal_ai_mcp.modules.context.semantic_compressor import SemanticCompressor
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        builder = IdeaBlockBuilder(router, settings.idea_block_merge_threshold)
        compressor = SemanticCompressor()
        distiller = IdeaBlockDistiller(router)
        ctx_mgr = ContextManager(settings, builder, compressor, distiller)

        session = mcp.state.session_store.get_or_create(UUID(session_id))
        collection = await ctx_mgr.add_content(session, content, source_ref)

        return json.dumps({
            "blocks_created": len(collection.blocks),
            "source_tokens": collection.source_token_count,
            "compressed_tokens": collection.compressed_token_count,
            "compression_ratio": f"{collection.compression_ratio:.2f}",
            "session_token_usage": session.context_token_usage,
        }, indent=2)

    @mcp.tool()
    async def context_get_xml(session_id: str, tags_filter: str | None = None) -> str:
        """Return the current session context as compact IdeaBlock XML.

        Use this instead of dumping raw code/docs into prompts.
        The XML format is processed more efficiently by LLMs.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.context.context_manager import ContextManager
        from universal_ai_mcp.modules.context.idea_block_builder import IdeaBlockBuilder
        from universal_ai_mcp.modules.context.semantic_compressor import SemanticCompressor
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        builder = IdeaBlockBuilder(router)
        compressor = SemanticCompressor()
        ctx_mgr = ContextManager(settings, builder, compressor)

        session = mcp.state.session_store.get_or_create(UUID(session_id))
        collection = ctx_mgr.get_context(session)

        if not collection:
            return "<KnowledgeContext blocks='0'/>"

        if tags_filter:
            tags = [t.strip() for t in tags_filter.split(",")]
            collection = collection.filter_by_tags(tags)

        return collection.to_xml_context()

    @mcp.tool()
    async def context_token_usage(session_id: str) -> str:
        """Report current token budget usage for the session."""
        from universal_ai_mcp.core.config import get_settings

        settings = get_settings()
        session = mcp.state.session_store.get(UUID(session_id))

        if not session:
            return json.dumps({"error": "Session not found"})

        used = session.context_token_usage
        budget = settings.context_max_tokens
        ratio = used / budget if budget > 0 else 0.0

        return json.dumps({
            "used_tokens": used,
            "budget_tokens": budget,
            "utilization": f"{ratio:.1%}",
            "status": "ok" if ratio < 0.7 else "warning" if ratio < 0.9 else "critical",
        }, indent=2)

    @mcp.tool()
    async def context_compress_now(session_id: str) -> str:
        """Force immediate context compression to free token budget."""
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.context.context_manager import ContextManager
        from universal_ai_mcp.modules.context.idea_block_builder import IdeaBlockBuilder
        from universal_ai_mcp.modules.context.semantic_compressor import SemanticCompressor
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        builder = IdeaBlockBuilder(router)
        compressor = SemanticCompressor()
        ctx_mgr = ContextManager(settings, builder, compressor)

        session = mcp.state.session_store.get_or_create(UUID(session_id))
        before = session.context_token_usage
        collection = ctx_mgr.get_context(session)

        if not collection:
            return json.dumps({"message": "No context to compress"})

        target = int(settings.context_max_tokens * settings.context_target_ratio * 0.5)
        compressed = await compressor.compress(collection, target)
        session.context_token_usage = compressed.total_tokens()

        return json.dumps({
            "before_tokens": before,
            "after_tokens": session.context_token_usage,
            "blocks_removed": len(collection.blocks) - len(compressed.blocks),
        }, indent=2)

    @mcp.tool()
    async def context_persist_blocks(
        session_id: str,
        project_path: str | None = None,
        scope: str = "project",
    ) -> str:
        """Persist the current session's IdeaBlocks to ChromaDB for cross-session retrieval.

        Call at the end of a session to preserve the distilled knowledge.
        On the next session, use memory_search to retrieve relevant blocks
        without re-ingesting the same content.

        Args:
            session_id   : current session with IdeaBlocks to persist.
            project_path : root path of the project (required when scope='project').
            scope        : 'project' (default) or 'global'.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.entities.memory_entity import MemoryScope
        from universal_ai_mcp.modules.context.block_memory_bridge import BlockMemoryBridge
        from universal_ai_mcp.modules.memory.embedding_provider import OllamaEmbeddingProvider
        from universal_ai_mcp.modules.memory.memory_indexer import MemoryIndexer
        from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore

        session = mcp.state.session_store.get(UUID(session_id))
        if not session:
            return json.dumps({"error": "Session not found"})

        collection = session.idea_block_collection
        if not collection or not collection.blocks:
            return json.dumps({"message": "No IdeaBlocks in session to persist"})

        settings = get_settings()
        mem_scope = MemoryScope.PROJECT if scope == "project" else MemoryScope.GLOBAL

        if mem_scope == MemoryScope.PROJECT and not project_path:
            return json.dumps({"error": "project_path is required when scope='project'"})

        store = MemoryVectorStore(settings.memory_data_dir)
        embedder = OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.embedding_model,
        )
        indexer = MemoryIndexer(store, embedder)
        bridge = BlockMemoryBridge(indexer)

        result = await bridge.persist(collection, mem_scope, project_path)

        return json.dumps({
            "persisted": result.status == "ok",
            "blocks": len(collection.blocks),
            "chunks_indexed": result.chunks_indexed,
            "chunks_skipped": result.chunks_skipped,
            "scope": scope,
            "source": result.source,
            "embedding_model": result.embedding_model,
            "error": result.error,
        }, indent=2)

    @mcp.tool()
    async def context_retrieve_blocks(
        query: str,
        limit: int = 10,
        filter_tags: str | None = None,
    ) -> str:
        """Search indexed IdeaBlocks by semantic similarity, optionally filtered by tags.

        Use at the start of a task to pull relevant knowledge from previous sessions
        before deciding what to build. Returns typed IdeaBlocks + ready-to-use XML
        context for direct injection into an LLM prompt.

        IdeaBlocks are indexed via context_persist_blocks (or the orchestrator pipeline
        CONTEXT_BUILD phase). Search is fail-open: returns empty list if Ollama is
        unavailable rather than erroring.

        Args:
            query:       Natural language question or task description to search for.
            limit:       Max blocks to return (default 10, max 50).
            filter_tags: Comma-separated tag list. Only blocks with at least one matching
                         tag are returned (e.g. "auth,security"). Post-filter after
                         vector search.

        Returns:
            JSON with: blocks (list), count, xml_context (for LLM injection), query.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.context.block_retriever import BlockRetriever
        from universal_ai_mcp.modules.memory.embedding_provider import OllamaEmbeddingProvider
        from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore

        settings = get_settings()
        store = MemoryVectorStore(settings.memory_data_dir)
        embedder = OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.embedding_model,
        )
        retriever = BlockRetriever(store, embedder)

        tags = [t.strip() for t in filter_tags.split(",")] if filter_tags else None
        effective_limit = min(max(1, limit), 50)
        blocks = await retriever.query(query, limit=effective_limit, filter_tags=tags)

        xml_context = IdeaBlockCollection(blocks=blocks).to_xml_context() if blocks else ""

        return json.dumps({
            "query": query,
            "count": len(blocks),
            "xml_context": xml_context,
            "blocks": [
                {
                    "id": str(b.id),
                    "name": b.name,
                    "critical_question": b.critical_question,
                    "trusted_answer": b.trusted_answer,
                    "tags": b.tags,
                    "entities": b.entities,
                    "keywords": b.keywords,
                    "source_ref": b.source_ref,
                    "token_count": b.token_count,
                }
                for b in blocks
            ],
        }, indent=2)
