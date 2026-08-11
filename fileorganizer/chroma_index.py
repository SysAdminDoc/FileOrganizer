"""Optional persistent Chroma adapter for local CLIP cross-modal search."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from fileorganizer.clip_index import (
    EMBEDDING_DIMENSION,
    normalize_embedding,
)


MAX_RESULTS = 100
_COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")


class ChromaIndexUnavailable(RuntimeError):
    """Raised when the optional Chroma backend is not usable."""


@dataclass(frozen=True)
class ChromaRecord:
    record_id: str
    path: str
    embedding: tuple[float, ...]
    document: str
    metadata: dict[str, str | int | float | bool]


def record_id(path: str | os.PathLike[str]) -> str:
    """Return a stable, privacy-preserving Chroma ID for a local path."""
    normalized = os.path.normcase(os.path.abspath(os.path.normpath(os.fspath(path))))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def document_for_path(path: str | os.PathLike[str]) -> str:
    """Build a bounded text document for CLIP's cross-modal text search."""
    name = Path(path).stem.replace("_", " ").replace("-", " ")
    return " ".join(name.split())[:512] or "untitled image"


class ChromaIndex:
    """Thin version-tolerant wrapper around Chroma's PersistentClient API."""

    def __init__(
        self,
        database: str | os.PathLike[str],
        *,
        collection: str = "fileorganizer_clip",
        dimension: int = EMBEDDING_DIMENSION,
    ):
        if not _COLLECTION_RE.fullmatch(collection):
            raise ValueError("collection must be a lowercase 3–63 character Chroma name")
        if not 1 <= int(dimension) <= 4096:
            raise ValueError("embedding dimension is outside the supported range")
        self.database = Path(database)
        self.collection_name = collection
        self.dimension = int(dimension)
        self._collection: Any = None

    def __enter__(self) -> "ChromaIndex":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @property
    def collection(self) -> Any:
        if self._collection is None:
            raise ChromaIndexUnavailable("the Chroma index is not open")
        return self._collection

    def open(self) -> None:
        if self._collection is not None:
            return
        try:
            import chromadb
        except ImportError as exc:
            raise ChromaIndexUnavailable(
                "chromadb is not installed; install chromadb to use cross-modal search"
            ) from exc
        try:
            self.database.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.database))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine", "fileorganizer:dimension": self.dimension},
            )
        except Exception as exc:
            raise ChromaIndexUnavailable(f"could not open Chroma index: {exc}") from exc

    def close(self) -> None:
        self._collection = None

    def count(self) -> int:
        return int(self.collection.count())

    def upsert(self, records: Iterable[ChromaRecord]) -> int:
        batch = list(records)
        if not batch:
            return 0
        for record in batch:
            if len(record.embedding) != self.dimension:
                raise ValueError(f"embedding must have {self.dimension} values")
            normalize_embedding(record.embedding, dimension=self.dimension)
        self.collection.upsert(
            ids=[record.record_id for record in batch],
            embeddings=[list(record.embedding) for record in batch],
            documents=[record.document[:512] for record in batch],
            metadatas=[{
                key: value for key, value in {
                    **record.metadata,
                    "path": record.path,
                }.items()
                if value is not None
            } for record in batch],
        )
        return len(batch)

    def query(
        self,
        embedding: Sequence[float],
        *,
        limit: int = 10,
        minimum_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        normalized = normalize_embedding(embedding, dimension=self.dimension)
        limit = max(1, min(int(limit), MAX_RESULTS))
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[list(normalized)],
            n_results=min(limit, self.count()),
            include=["metadatas", "documents", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        threshold = max(-1.0, min(1.0, float(minimum_similarity)))
        matches: list[dict[str, Any]] = []
        for index, identifier in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            distance = float(distances[index]) if index < len(distances) else 1.0
            similarity = max(-1.0, min(1.0, 1.0 - distance))
            if similarity < threshold:
                continue
            matches.append({
                "id": str(identifier),
                "path": str(metadata.get("path", "")),
                "document": str(documents[index]) if index < len(documents) else "",
                "similarity": similarity,
                "distance": distance,
                "metadata": metadata,
            })
        matches.sort(key=lambda item: (-float(item["similarity"]), str(item["path"])))
        return matches[:limit]

    def remove_missing_under(
        self,
        root: str | os.PathLike[str],
        live_paths: set[str],
    ) -> int:
        root_key = os.path.normcase(os.path.abspath(os.path.normpath(os.fspath(root))))
        prefix = root_key.rstrip("\\/") + os.sep
        payload = self.collection.get(include=["metadatas"])
        ids = payload.get("ids", [])
        metadatas = payload.get("metadatas", []) or []
        stale = []
        for index, identifier in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            path = str(metadata.get("path", "")) if isinstance(metadata, dict) else ""
            key = os.path.normcase(os.path.abspath(os.path.normpath(path)))
            if key.startswith(prefix) and key not in live_paths:
                stale.append(str(identifier))
        if stale:
            self.collection.delete(ids=stale)
        return len(stale)
