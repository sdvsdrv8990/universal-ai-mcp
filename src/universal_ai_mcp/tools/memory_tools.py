"""Memory module MCP tools — search and index the knowledge base.

Registered tools:
  memory_search        : semantic search across global + project memory
  memory_store         : index arbitrary text content manually
  memory_index_github  : fetch a GitHub repo README and index it
  memory_index_docs    : index documentation content (e.g. fetched from Context7)
  memory_list_sources  : list indexed sources with entry counts
  memory_delete_source : remove all entries from a specific source

Context7 workflow (two-step):
  1. Claude calls Context7 MCP tool to fetch library docs
  2. Claude passes the result to memory_index_docs() to store in vector DB
  This keeps universal-ai-mcp decoupled from Context7's transport.

All tools return JSON strings and never raise — errors appear in the JSON.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="memory",
    display_name="Memory Store",
    description=(
        "Local vector database with global (library docs) and project-specific memory. "
        "Search via semantic similarity; index from GitHub, Context7, or manual text."
    ),
    scenarios=[
        ModuleScenario(
            name="semantic_search",
            description="Search the knowledge base for relevant context before answering",
            scenario_type=ScenarioType.USER,
            required_tools=["memory_search"],
        ),
        ModuleScenario(
            name="index_library_docs",
            description="Fetch documentation from Context7 or GitHub and store it",
            scenario_type=ScenarioType.USER,
            required_tools=["memory_index_docs", "memory_index_github"],
        ),
        ModuleScenario(
            name="manage_sources",
            description="Inspect or clean up indexed knowledge sources",
            scenario_type=ScenarioType.USER,
            required_tools=["memory_list_sources", "memory_delete_source"],
        ),
    ],
    mcp_tools=[
        "memory_search",
        "memory_store",
        "memory_index_github",
        "memory_index_docs",
        "memory_list_sources",
        "memory_delete_source",
    ],
)


def _make_components() -> tuple[object, object, object]:
    """Construct store, embedder, indexer from current settings.

    Called lazily inside each tool to avoid import-time side effects.
    Returns (store, embedder, indexer).
    """
    from universal_ai_mcp.core.config import get_settings
    from universal_ai_mcp.modules.memory.embedding_provider import OllamaEmbeddingProvider
    from universal_ai_mcp.modules.memory.memory_indexer import MemoryIndexer
    from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore
    from universal_ai_mcp.modules.solutions.github_finder import GitHubFinder

    settings = get_settings()
    store = MemoryVectorStore(data_dir=settings.memory_data_dir)
    embedder = OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.memory_embedding_model,
    )
    github_token = settings.github_token.get_secret_value() if settings.github_token else None
    finder = GitHubFinder(
        github_token=github_token,
        max_results=settings.github_search_max_results,
    )
    indexer = MemoryIndexer(store=store, embedder=embedder, github_finder=finder)
    return store, embedder, indexer


def register_memory_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def memory_search(
        query: str,
        scope: str = "both",
        project_path: str | None = None,
        top_k: int = 5,
        rerank: bool = False,
    ) -> str:
        """Search the vector memory for relevant context.

        Args:
            query: Natural language question or keyword query.
            scope: "global" (library docs), "project" (project context), or "both".
            project_path: Absolute project root path — required when scope includes project.
            top_k: Number of results to return (1–50).
            rerank: Run an LLM re-ranking pass on the top candidates (slower, more accurate).
        """
        from universal_ai_mcp.entities.memory_entity import MemoryQuery, MemoryScope
        from universal_ai_mcp.modules.memory.memory_retriever import MemoryRetriever

        store, embedder, _ = _make_components()

        scope_map = {
            "global": MemoryScope.GLOBAL,
            "project": MemoryScope.PROJECT,
            "both": None,
        }
        parsed_scope = scope_map.get(scope)
        if parsed_scope is None and scope not in ("both",):
            return json.dumps({"error": f"Unknown scope: {scope!r}. Use global, project, or both."})

        router = None
        if rerank:
            from universal_ai_mcp.core.config import get_settings
            from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
            from universal_ai_mcp.modules.llm.router import LLMRouter
            settings = get_settings()
            router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)

        retriever = MemoryRetriever(store=store, embedder=embedder, router=router)  # type: ignore[arg-type]
        mem_query = MemoryQuery(
            query=query,
            scope=parsed_scope,
            project_path=project_path,
            top_k=min(max(1, top_k), 50),
            rerank=rerank,
        )
        result = await retriever.search(mem_query)

        return json.dumps({
            "query": result.query_text,
            "total_found": result.total_found,
            "reranked": result.reranked,
            "results": [
                {
                    "content": e.content,
                    "source": e.source,
                    "scope": e.scope.value,
                    "library_name": e.library_name,
                    "distance": round(d, 4),
                    "relevance_score": round(1.0 - d, 4),
                }
                for e, d in zip(result.entries, result.distances)
            ],
        }, indent=2)

    @mcp.tool()
    async def memory_store(
        content: str,
        source: str,
        scope: str = "project",
        project_path: str | None = None,
        library_name: str | None = None,
    ) -> str:
        """Index arbitrary text content into memory.

        Use this to store any text — code snippets, notes, decision records.
        For Context7 docs, use memory_index_docs instead (adds library metadata).

        Args:
            content: Text content to index (will be chunked automatically).
            source: Descriptive identifier — URL, file path, or "manual".
            scope: "global" or "project".
            project_path: Required when scope="project".
            library_name: Optional label for GLOBAL scope docs.
        """
        from universal_ai_mcp.entities.memory_entity import MemoryScope

        _, _, indexer = _make_components()

        try:
            scope_enum = MemoryScope(scope)
        except ValueError:
            return json.dumps({"error": f"Unknown scope: {scope!r}. Use global or project."})

        result = await indexer.index_text(  # type: ignore[attr-defined]
            text=content,
            source=source,
            scope=scope_enum,
            project_path=project_path,
            library_name=library_name,
        )
        return json.dumps({
            "source": result.source,
            "scope": result.scope.value,
            "chunks_indexed": result.chunks_indexed,
            "chunks_skipped": result.chunks_skipped,
            "embedding_model": result.embedding_model,
            "status": result.status,
            "error": result.error,
        }, indent=2)

    @mcp.tool()
    async def memory_index_github(
        repo_full_name: str,
        scope: str = "global",
        project_path: str | None = None,
    ) -> str:
        """Fetch a GitHub repository's README and index it in memory.

        The source key is "github:<repo_full_name>" — re-running this tool
        is safe; unchanged content is deduplicated by content hash.

        Args:
            repo_full_name: GitHub repository name, e.g. "owner/repo".
            scope: "global" (shared docs) or "project" (project-specific).
            project_path: Required when scope="project".
        """
        from universal_ai_mcp.entities.memory_entity import MemoryScope

        _, _, indexer = _make_components()

        try:
            scope_enum = MemoryScope(scope)
        except ValueError:
            return json.dumps({"error": f"Unknown scope: {scope!r}."})

        result = await indexer.index_github_repo(  # type: ignore[attr-defined]
            repo_full_name=repo_full_name,
            scope=scope_enum,
            project_path=project_path,
        )
        return json.dumps({
            "source": result.source,
            "scope": result.scope.value,
            "chunks_indexed": result.chunks_indexed,
            "chunks_skipped": result.chunks_skipped,
            "embedding_model": result.embedding_model,
            "status": result.status,
            "error": result.error,
        }, indent=2)

    @mcp.tool()
    async def memory_index_docs(
        content: str,
        library_name: str,
        scope: str = "global",
        project_path: str | None = None,
        version: str | None = None,
    ) -> str:
        """Index documentation content fetched from Context7 or another source.

        Context7 workflow:
          1. Call Context7's resolve-library-id tool to get the library ID
          2. Call Context7's get-library-docs tool to fetch documentation text
          3. Pass the result here as `content`

        Args:
            content: Documentation text to index.
            library_name: Library identifier, e.g. "chromadb", "fastmcp".
            scope: "global" (recommended for library docs) or "project".
            project_path: Required when scope="project".
            version: Optional library version tag stored in metadata source key.
        """
        from universal_ai_mcp.entities.memory_entity import MemoryScope

        _, _, indexer = _make_components()

        try:
            scope_enum = MemoryScope(scope)
        except ValueError:
            return json.dumps({"error": f"Unknown scope: {scope!r}."})

        ver_suffix = f"@{version}" if version else ""
        source = f"docs:{library_name}{ver_suffix}"

        result = await indexer.index_text(  # type: ignore[attr-defined]
            text=content,
            source=source,
            scope=scope_enum,
            project_path=project_path,
            library_name=library_name,
        )
        return json.dumps({
            "library": library_name,
            "version": version,
            "source": result.source,
            "scope": result.scope.value,
            "chunks_indexed": result.chunks_indexed,
            "chunks_skipped": result.chunks_skipped,
            "embedding_model": result.embedding_model,
            "status": result.status,
            "error": result.error,
        }, indent=2)

    @mcp.tool()
    async def memory_list_sources(
        scope: str = "both",
        project_path: str | None = None,
    ) -> str:
        """List all indexed sources with their entry counts.

        Args:
            scope: "global", "project", or "both".
            project_path: Required when scope includes project.
        """
        from universal_ai_mcp.entities.memory_entity import MemoryEntry, MemoryScope

        store, _, _ = _make_components()

        results: list[dict[str, object]] = []

        def _collect(col_name: str, scope_label: str) -> None:
            sources = store.list_sources(col_name)  # type: ignore[attr-defined]
            for s in sources:
                results.append({**s, "scope": scope_label, "collection": col_name})

        if scope in ("global", "both"):
            _collect("global", "global")

        if scope in ("project", "both") and project_path:
            col = MemoryEntry.collection_name_for(MemoryScope.PROJECT, project_path)
            _collect(col, "project")

        all_collections = store.list_collections()  # type: ignore[attr-defined]
        return json.dumps({
            "sources": results,
            "total_collections": len(all_collections),
            "collections": all_collections,
        }, indent=2)

    @mcp.tool()
    async def memory_delete_source(
        source: str,
        scope: str,
        project_path: str | None = None,
    ) -> str:
        """Delete all memory entries for a specific source.

        Args:
            source: Exact source key (e.g. "github:owner/repo", "docs:fastmcp").
            scope: "global" or "project".
            project_path: Required when scope="project".
        """
        from universal_ai_mcp.entities.memory_entity import MemoryEntry, MemoryScope

        store, _, _ = _make_components()

        try:
            scope_enum = MemoryScope(scope)
        except ValueError:
            return json.dumps({"error": f"Unknown scope: {scope!r}."})

        col = MemoryEntry.collection_name_for(scope_enum, project_path)
        deleted = store.delete_by_source(col, source)  # type: ignore[attr-defined]
        return json.dumps({
            "source": source,
            "scope": scope,
            "deleted": deleted,
        }, indent=2)
