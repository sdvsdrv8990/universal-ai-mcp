"""Memory module entities — types shared across all memory layers.

Data flow overview:
  [text source]
      → MemoryIndexer chunks it → List[MemoryEntry] with embeddings
      → MemoryVectorStore persists entries in ChromaDB
      → MemoryRetriever accepts MemoryQuery → returns MemorySearchResult

Scope rules:
  GLOBAL  — library docs, GitHub READMEs; shared across all projects
  PROJECT — IdeaBlocks, plans, code facts; isolated per project_path

Each layer only depends on these types, never on each other's internals.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class MemoryScope(str, Enum):
    GLOBAL = "global"
    PROJECT = "project"


class MemoryEntry(BaseModel):
    """Single indexed chunk of text in the vector store.

    id is a string UUID — ChromaDB requires str, not UUID objects.
    content_hash enables deduplication and TTL checks without re-reading content.
    chunk_index preserves reading order within a multi-chunk source.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str = Field(description="Text chunk (≤512 tokens)")
    source: str = Field(description="URL, file path, 'manual', or 'github:<full_name>'")
    scope: MemoryScope
    project_path: str | None = Field(
        default=None,
        description="Absolute path of the project root; required for PROJECT scope",
    )
    library_name: str | None = Field(
        default=None,
        description="Library or tool name; optional for GLOBAL scope",
    )
    embedding_model: str = Field(description="Ollama model used to produce the embedding")
    content_hash: str = Field(
        description="SHA-256 of content; used for dedup and staleness detection"
    )
    chunk_index: int = Field(default=0, description="Position within the source document")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "MemoryEntry":
        if self.scope == MemoryScope.PROJECT and self.project_path is None:
            raise ValueError("project_path is required for PROJECT scope")
        return self

    @classmethod
    def collection_name_for(
        cls,
        scope: MemoryScope,
        project_path: str | None = None,
    ) -> str:
        """Return the ChromaDB collection name for a given scope."""
        if scope == MemoryScope.GLOBAL:
            return "global"
        if project_path is None:
            raise ValueError("project_path required for PROJECT scope collection name")
        path_hash = hashlib.sha256(project_path.encode()).hexdigest()[:16]
        return f"project_{path_hash}"

    def to_chroma_metadata(self) -> dict[str, str | int | float]:
        """Flatten to ChromaDB-compatible metadata (str/int/float values only)."""
        return {
            "source": self.source,
            "scope": self.scope.value,
            "project_path": self.project_path or "",
            "library_name": self.library_name or "",
            "embedding_model": self.embedding_model,
            "content_hash": self.content_hash,
            "chunk_index": self.chunk_index,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_chroma_result(
        cls,
        chroma_id: str,
        document: str,
        metadata: dict[str, str | int | float],
    ) -> "MemoryEntry":
        """Reconstruct a MemoryEntry from a ChromaDB query result row."""
        return cls(
            id=chroma_id,
            content=document,
            source=str(metadata["source"]),
            scope=MemoryScope(metadata["scope"]),
            project_path=str(metadata["project_path"]) or None,
            library_name=str(metadata["library_name"]) or None,
            embedding_model=str(metadata["embedding_model"]),
            content_hash=str(metadata["content_hash"]),
            chunk_index=int(metadata["chunk_index"]),
            created_at=datetime.fromisoformat(str(metadata["created_at"])),
            updated_at=datetime.fromisoformat(str(metadata["updated_at"])),
        )


class MemoryQuery(BaseModel):
    """Parameters for a memory search operation."""

    query: str = Field(description="Natural language question or keyword query")
    scope: MemoryScope | None = Field(
        default=None,
        description="Limit to a specific scope; None searches both GLOBAL and PROJECT",
    )
    project_path: str | None = Field(
        default=None,
        description="Required when scope=PROJECT to target the correct collection",
    )
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = Field(
        default=False,
        description="Run an LLM re-ranking pass on the top candidates",
    )
    source_filter: str | None = Field(
        default=None,
        description="Restrict results to a specific source prefix",
    )


class MemorySearchResult(BaseModel):
    """Output of a MemoryRetriever.search() call."""

    entries: list[MemoryEntry] = Field(default_factory=list)
    distances: list[float] = Field(
        default_factory=list,
        description="Cosine distances; lower = more similar",
    )
    query_text: str
    total_found: int = Field(default=0)
    reranked: bool = Field(default=False)

    def as_context_text(self) -> str:
        """Format results for direct insertion into an LLM prompt."""
        if not self.entries:
            return "[Memory: no relevant results found]"
        parts = [f"[Memory search: '{self.query_text}' — {self.total_found} results]\n"]
        for i, (entry, dist) in enumerate(zip(self.entries, self.distances), 1):
            score = round(1.0 - dist, 3)
            header = f"[{i}] source={entry.source} score={score}"
            if entry.library_name:
                header += f" lib={entry.library_name}"
            parts.append(f"{header}\n{entry.content}")
        return "\n\n".join(parts)


class IndexResult(BaseModel):
    """Summary returned after an indexing operation."""

    source: str
    scope: MemoryScope
    chunks_indexed: int
    chunks_skipped: int = Field(
        default=0,
        description="Chunks skipped because content_hash matched existing entry",
    )
    embedding_model: str
    status: Literal["ok", "error"] = "ok"
    error: str | None = None
