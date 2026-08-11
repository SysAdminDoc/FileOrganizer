"""Optional OpenCLIP ViT-L/14 embeddings backed by sqlite-vec.

The module keeps heavyweight ML imports lazy. A normal FileOrganizer install
therefore retains its existing startup cost and deterministic behavior; users
who opt into the visual index install the CLIP stack and provide model weights
when the index runner is invoked.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


MODEL_NAME = "ViT-L-14"
PRETRAINED_NAME = "datacomp_xl_s13b_b90k"
EMBEDDING_DIMENSION = 768
MAX_BATCH_SIZE = 64
MAX_RESULTS = 100
IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff",
    ".avif", ".jxl", ".heic", ".heif",
})
_TABLE_NAME = "clip_embeddings"


class ClipIndexUnavailable(RuntimeError):
    """Raised when an optional model, extension, or index cannot be loaded."""


@dataclass(frozen=True)
class EncodedImage:
    path: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class EncodingFailure:
    path: str
    reason: str


def normalize_embedding(
    values: Sequence[float],
    *,
    dimension: int = EMBEDDING_DIMENSION,
) -> tuple[float, ...]:
    """Return a finite unit vector with the configured CLIP dimension."""
    if len(values) != dimension:
        raise ValueError(f"embedding must have {dimension} values")
    converted = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in converted):
        raise ValueError("embedding contains a non-finite value")
    norm = math.sqrt(sum(value * value for value in converted))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("embedding must have a non-zero magnitude")
    return tuple(value / norm for value in converted)


def cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    """Compute cosine similarity without assuming either input is normalized."""
    if len(first) != len(second) or not first:
        raise ValueError("embeddings must have the same non-zero dimension")
    first_norm = math.sqrt(sum(float(value) ** 2 for value in first))
    second_norm = math.sqrt(sum(float(value) ** 2 for value in second))
    if first_norm <= 0 or second_norm <= 0:
        raise ValueError("embeddings must have a non-zero magnitude")
    return sum(float(a) * float(b) for a, b in zip(first, second)) / (
        first_norm * second_norm
    )


def iter_image_paths(root: str | os.PathLike[str]) -> Iterable[str]:
    """Yield supported image paths in deterministic order without following links."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise FileNotFoundError(f"image root is not an existing folder: {root}")
    for directory, dirnames, filenames in os.walk(root_path, followlinks=False):
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".") and name != "__pycache__"
        )
        for filename in sorted(filenames):
            if Path(filename).suffix.casefold() in IMAGE_EXTENSIONS:
                yield os.path.abspath(os.path.join(directory, filename))


def _path_key(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(os.fspath(path))))


def _path_metadata(path: str) -> tuple[int, int]:
    info = os.stat(path, follow_symlinks=False)
    return int(info.st_size), int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1e9)))


class ClipIndex:
    """A local sqlite-vec index with path/identity metadata beside each vector."""

    def __init__(self, database: str | os.PathLike[str], *, dimension: int = EMBEDDING_DIMENSION):
        if not 1 <= int(dimension) <= 4096:
            raise ValueError("embedding dimension is outside the supported range")
        self.database = Path(database)
        self.dimension = int(dimension)
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> "ClipIndex":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise ClipIndexUnavailable("the CLIP index is not open")
        return self._connection

    def open(self) -> None:
        if self._connection is not None:
            return
        try:
            import sqlite_vec
        except ImportError as exc:
            raise ClipIndexUnavailable(
                "sqlite-vec is not installed; install sqlite-vec to use the visual index"
            ) from exc
        try:
            self.database.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.database))
            connection.enable_load_extension(True)
            try:
                sqlite_vec.load(connection)
            finally:
                connection.enable_load_extension(False)
            connection.execute(
                f"""CREATE VIRTUAL TABLE IF NOT EXISTS {_TABLE_NAME} USING vec0(
                    embedding float[{self.dimension}],
                    +path TEXT,
                    +size INTEGER,
                    +mtime_ns INTEGER,
                    +vector_json TEXT
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS clip_files (
                    path_key TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    embedding_rowid INTEGER NOT NULL UNIQUE,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS clip_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS clip_files_path_index ON clip_files(path)"
            )
            connection.commit()
            self._connection = connection
        except ClipIndexUnavailable:
            raise
        except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
            if "connection" in locals():
                connection.close()
            raise ClipIndexUnavailable(f"could not open sqlite-vec index: {exc}") from exc

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def clear(self) -> None:
        self.connection.execute(f"DELETE FROM {_TABLE_NAME}")
        self.connection.execute("DELETE FROM clip_files")
        self.connection.execute("DELETE FROM clip_meta")
        self.connection.commit()

    def ensure_model(self, model_id: str) -> None:
        """Bind the database to one model/weight pair to prevent mixed spaces."""
        if not model_id or len(model_id) > 128:
            raise ValueError("model_id must be a bounded nonempty string")
        row = self.connection.execute(
            "SELECT value FROM clip_meta WHERE key = 'model_id'"
        ).fetchone()
        if row is not None and str(row[0]) != model_id:
            raise ClipIndexUnavailable(
                "the index was created with different CLIP weights; use --rebuild"
            )
        if row is None:
            self.connection.execute(
                "INSERT INTO clip_meta(key, value) VALUES ('model_id', ?)",
                (model_id,),
            )
            self.connection.commit()

    def upsert(self, path: str | os.PathLike[str], embedding: Sequence[float]) -> None:
        path_text = os.path.abspath(os.path.normpath(os.fspath(path)))
        size, mtime_ns = _path_metadata(path_text)
        normalized = normalize_embedding(embedding, dimension=self.dimension)
        key = _path_key(path_text)
        connection = self.connection
        previous = connection.execute(
            "SELECT embedding_rowid FROM clip_files WHERE path_key = ?", (key,)
        ).fetchone()
        if previous is not None:
            connection.execute(
                f"DELETE FROM {_TABLE_NAME} WHERE rowid = ?", (int(previous[0]),)
            )
            connection.execute("DELETE FROM clip_files WHERE path_key = ?", (key,))
        cursor = connection.execute(
            f"""INSERT INTO {_TABLE_NAME}
               (embedding, path, size, mtime_ns, vector_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                json.dumps(normalized, separators=(",", ":")),
                path_text,
                size,
                mtime_ns,
                json.dumps(normalized, separators=(",", ":")),
            ),
        )
        rowid = int(cursor.lastrowid)
        connection.execute(
            """INSERT INTO clip_files(path_key, path, embedding_rowid, size, mtime_ns)
               VALUES (?, ?, ?, ?, ?)""",
            (key, path_text, rowid, size, mtime_ns),
        )
        connection.commit()

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM clip_files").fetchone()
        return int(row[0]) if row else 0

    def remove_missing_under(self, root: str | os.PathLike[str], live_paths: set[str]) -> int:
        root_key = _path_key(root).rstrip("\\/") + os.sep
        stale = [
            (str(row[0]), int(row[1]))
            for row in self.connection.execute(
                "SELECT path, embedding_rowid FROM clip_files"
            ).fetchall()
            if _path_key(str(row[0])).startswith(root_key)
            and _path_key(str(row[0])) not in live_paths
        ]
        for path, rowid in stale:
            self.connection.execute(f"DELETE FROM {_TABLE_NAME} WHERE rowid = ?", (rowid,))
            self.connection.execute(
                "DELETE FROM clip_files WHERE path_key = ?", (_path_key(path),)
            )
        if stale:
            self.connection.commit()
        return len(stale)

    def search(
        self,
        embedding: Sequence[float],
        *,
        limit: int = 10,
        minimum_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        normalized = normalize_embedding(embedding, dimension=self.dimension)
        limit = max(1, min(int(limit), MAX_RESULTS))
        threshold = max(-1.0, min(1.0, float(minimum_similarity)))
        fetch_limit = min(MAX_RESULTS * 10, max(limit, limit * 5))
        rows = self.connection.execute(
            f"""SELECT rowid, path, size, mtime_ns, vector_json
                FROM {_TABLE_NAME}
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?""",
            (json.dumps(normalized, separators=(",", ":")), fetch_limit),
        ).fetchall()
        matches: list[dict[str, Any]] = []
        for rowid, path, size, mtime_ns, vector_json in rows:
            try:
                candidate = normalize_embedding(
                    json.loads(str(vector_json)),
                    dimension=self.dimension,
                )
                similarity = cosine_similarity(normalized, candidate)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if similarity >= threshold:
                matches.append({
                    "rowid": int(rowid),
                    "path": str(path),
                    "size": int(size),
                    "mtime_ns": int(mtime_ns),
                    "similarity": similarity,
                })
        matches.sort(key=lambda item: (-float(item["similarity"]), str(item["path"])))
        return matches[:limit]


class ClipEmbedder:
    """Lazy OpenCLIP image encoder with explicit device and batch bounds."""

    def __init__(
        self,
        *,
        model_name: str = MODEL_NAME,
        pretrained: str = PRETRAINED_NAME,
        device: str = "auto",
        batch_size: int = 16,
    ):
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        if not 1 <= int(batch_size) <= MAX_BATCH_SIZE:
            raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
        self.model_name = model_name
        self.pretrained = pretrained
        self.requested_device = device
        self.batch_size = int(batch_size)
        self._torch: Any = None
        self._model: Any = None
        self._preprocess: Any = None
        self.device = ""

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise ClipIndexUnavailable(
                "open_clip_torch and torch are required for the visual index"
            ) from exc
        if self.requested_device == "cuda":
            if not torch.cuda.is_available():
                raise ClipIndexUnavailable("CUDA was requested but is not available")
            self.device = "cuda"
        else:
            self.device = "cuda" if self.requested_device == "auto" and torch.cuda.is_available() else "cpu"
        try:
            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained or None,
                device=self.device,
            )
            self._model.eval()
        except Exception as exc:
            raise ClipIndexUnavailable(
                f"could not load {self.model_name}/{self.pretrained}: {exc}"
            ) from exc
        self._torch = torch

    def encode_paths(
        self,
        paths: Iterable[str],
    ) -> tuple[list[EncodedImage], list[EncodingFailure]]:
        self.load()
        try:
            from PIL import Image
        except ImportError as exc:
            raise ClipIndexUnavailable("Pillow is required to preprocess CLIP images") from exc

        encoded: list[EncodedImage] = []
        failures: list[EncodingFailure] = []
        pending: list[str] = []
        tensors: list[Any] = []

        def flush() -> None:
            if not tensors:
                return
            try:
                batch = self._torch.stack(tensors).to(self.device)
                with self._torch.inference_mode():
                    features = self._model.encode_image(batch, normalize=True)
                values = features.detach().float().cpu().tolist()
                for path_text, vector in zip(pending, values):
                    encoded.append(EncodedImage(
                        path_text,
                        normalize_embedding(vector),
                    ))
            except Exception as exc:
                for path_text in pending:
                    failures.append(EncodingFailure(path_text, str(exc)))
            finally:
                pending.clear()
                tensors.clear()

        for path in paths:
            path_text = os.path.abspath(os.path.normpath(path))
            try:
                with Image.open(path_text) as image:
                    tensors.append(self._preprocess(image.convert("RGB")))
                pending.append(path_text)
            except Exception as exc:
                failures.append(EncodingFailure(path_text, f"{type(exc).__name__}: {exc}"))
            if len(tensors) >= self.batch_size:
                flush()
        flush()
        return encoded, failures


def stable_model_id(model_name: str, pretrained: str) -> str:
    """Return a short deterministic model identifier for index metadata."""
    payload = f"{model_name}\0{pretrained}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
