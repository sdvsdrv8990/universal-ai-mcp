"""Vector store — ChromaDB PersistentClient wrapper.

Isolation contract:
  - Only this file imports chromadb; all other modules are shielded from it
  - Accepts pre-computed embeddings (list[float]) — does NOT call Ollama
  - Returns raw dicts from ChromaDB so callers can reconstruct their own types
  - All ChromaDB operations are synchronous (ChromaDB has no async API)

Collection naming (from MemoryEntry.collection_name_for):
  "global"           → library docs, GitHub READMEs
  "project_{hash}"   → per-project IdeaBlocks and context

This file is the only place to change if we replace ChromaDB with another DB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ChromaDB import is deferred to _get_client() so the module loads even
# when chromadb is not installed — tools handle the ImportError gracefully.


class VectorStoreError(RuntimeError):
    """Raised when a ChromaDB operation fails."""


class MemoryVectorStore:
    """Thin wrapper around a ChromaDB PersistentClient.

    A single instance manages all collections (global + all projects).
    Constructed once at module init and held in module state.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir).expanduser().resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._client: Any = None  # chromadb.PersistentClient, typed as Any to avoid import

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import chromadb  # type: ignore[import]
                self._client = chromadb.PersistentClient(path=str(self._data_dir))
                log.info("chroma_client_init", data_dir=str(self._data_dir))
            except ImportError as exc:
                raise VectorStoreError(
                    "chromadb is not installed. Run: uv add chromadb"
                ) from exc
        return self._client

    def _collection(self, name: str) -> Any:
        """Get or create a named collection (chromadb.Collection)."""
        client = self._get_client()
        return client.get_or_create_collection(
            name=name,
            # cosine distance: 0 = identical, 2 = opposite
            metadata={"hnsw:space": "cosine"},
        )

    # ──────────────────────────────────────────────────────────────
    # Write operations
    # ──────────────────────────────────────────────────────────────

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str | int | float]],
    ) -> int:
        """Upsert entries. Returns the number of entries written."""
        if not ids:
            return 0
        try:
            col = self._collection(collection_name)
            col.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            log.debug("chroma_upsert", collection=collection_name, count=len(ids))
            return len(ids)
        except Exception as exc:
            raise VectorStoreError(f"upsert failed in '{collection_name}': {exc}") from exc

    def delete_by_source(self, collection_name: str, source: str) -> int:
        """Delete all entries whose metadata.source matches the given value.

        Returns the number of deleted entries.
        """
        try:
            col = self._collection(collection_name)
            result = col.get(where={"source": source})
            ids = result.get("ids", [])
            if ids:
                col.delete(ids=ids)
                log.info("chroma_delete", collection=collection_name, source=source, count=len(ids))
            return len(ids)
        except Exception as exc:
            raise VectorStoreError(
                f"delete_by_source failed in '{collection_name}': {exc}"
            ) from exc

    # ──────────────────────────────────────────────────────────────
    # Read operations
    # ──────────────────────────────────────────────────────────────

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a vector similarity query.

        Returns ChromaDB's raw result dict with keys:
          ids, documents, metadatas, distances (all lists-of-lists)
        """
        try:
            col = self._collection(collection_name)
            count = col.count()
            if count == 0:
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
            effective_k = min(top_k, count)
            kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": effective_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            return col.query(**kwargs)
        except Exception as exc:
            raise VectorStoreError(f"query failed in '{collection_name}': {exc}") from exc

    def get_by_source_hash(
        self,
        collection_name: str,
        source: str,
    ) -> list[dict[str, Any]]:
        """Fetch all entries for a source; used for content_hash dedup check."""
        try:
            col = self._collection(collection_name)
            result = col.get(
                where={"source": source},
                include=["metadatas"],
            )
            ids = result.get("ids", [])
            metas = result.get("metadatas", [])
            return [{"id": i, **m} for i, m in zip(ids, metas)]
        except Exception as exc:
            raise VectorStoreError(
                f"get_by_source_hash failed in '{collection_name}': {exc}"
            ) from exc

    def list_sources(self, collection_name: str) -> list[dict[str, Any]]:
        """Return unique sources with their entry count.

        Output: list of {"source": str, "count": int, "library_name": str}
        """
        try:
            col = self._collection(collection_name)
            if col.count() == 0:
                return []
            result = col.get(include=["metadatas"])
            metas = result.get("metadatas", []) or []
            seen: dict[str, dict[str, Any]] = {}
            for meta in metas:
                src = str(meta.get("source", ""))
                if src not in seen:
                    seen[src] = {
                        "source": src,
                        "count": 0,
                        "library_name": meta.get("library_name", ""),
                    }
                seen[src]["count"] += 1
            return list(seen.values())
        except Exception as exc:
            raise VectorStoreError(f"list_sources failed in '{collection_name}': {exc}") from exc

    def collection_count(self, collection_name: str) -> int:
        """Return the number of entries in a collection (0 if not yet created)."""
        try:
            col = self._collection(collection_name)
            return col.count()
        except Exception:
            return 0

    def list_collections(self) -> list[str]:
        """Return names of all existing collections."""
        try:
            client = self._get_client()
            return [c.name for c in client.list_collections()]
        except Exception:
            return []
