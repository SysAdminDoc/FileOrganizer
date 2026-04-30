"""Local embeddings classifier — pre-AI stage for classify_design.py.

Routes well-named items to canonical categories via cosine similarity against
embedded category anchors, before any DeepSeek/OpenAI call is made.  When the
top-1 anchor scores >= MIN_TOP1 AND the margin over top-2 is >= MIN_MARGIN,
the classifier returns the canonical category at confidence 90.  Otherwise it
returns None and the caller falls through to the next stage (AI).

Backend chain (in order of preference, each optional):
    1. fastembed       — ONNX runtime, small footprint (BAAI/bge-small-en-v1.5)
    2. model2vec       — distilled static embeddings (8-30 MB, very fast CPU)
    3. sentence_transformers — full PyTorch (all-MiniLM-L6-v2)
    4. none            — returns None for every classify() call

Pattern adapted from Bookmark-Organizer-Pro `services/embeddings.py` [S55].

Anchor cache:
    %APPDATA%/FileOrganizer/category_embeddings.db
    Keyed by (backend, model, category_hash) so a backend swap rebuilds anchors
    automatically on first call.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import sqlite3
import threading
from typing import Optional

from fileorganizer.config import _APP_DATA_DIR


# ── Tunables (also overridable via embeddings_settings.json) ─────────────────
MIN_TOP1   = 0.65   # cosine similarity floor for the winning category
MIN_MARGIN = 0.15   # required margin over the runner-up
HIT_CONF   = 90     # confidence assigned to embedding-decided items

DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_M2V_MODEL       = "minishlab/potion-base-8M"
DEFAULT_ST_MODEL        = "sentence-transformers/all-MiniLM-L6-v2"

_ANCHOR_DB = os.path.join(_APP_DATA_DIR, 'category_embeddings.db')


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _cosine(a, b) -> float:
    """Cosine similarity.  Accepts numpy arrays or plain Python sequences;
    routes to numpy ops when available, falls back to pure Python otherwise.
    Returns 0.0 when either input is empty, mismatched, or zero-norm.
    """
    # Length check works for both lists and numpy arrays.
    if len(a) == 0 or len(b) == 0 or len(a) != len(b):
        return 0.0
    # numpy path: detect via attribute, never use truthy on the array itself.
    if hasattr(a, 'dot') and hasattr(b, 'dot'):
        na = float((a * a).sum()) ** 0.5
        nb = float((b * b).sum()) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(a.dot(b)) / (na * nb)
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Anchor cache (SQLite) ────────────────────────────────────────────────────

def _init_anchor_db() -> sqlite3.Connection:
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    con = sqlite3.connect(_ANCHOR_DB, timeout=30.0)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS anchors (
            backend  TEXT NOT NULL,
            model    TEXT NOT NULL,
            category TEXT NOT NULL,
            vector   TEXT NOT NULL,
            PRIMARY KEY (backend, model, category)
        )
    """)
    con.commit()
    return con


def _load_cached_anchors(backend: str, model: str) -> dict[str, list[float]]:
    con = _init_anchor_db()
    rows = con.execute(
        "SELECT category, vector FROM anchors WHERE backend=? AND model=?",
        (backend, model)
    ).fetchall()
    con.close()
    out = {}
    for cat, vec_json in rows:
        try:
            out[cat] = json.loads(vec_json)
        except Exception:
            continue
    return out


def _persist_anchors(backend: str, model: str,
                     anchors: dict[str, list[float]]) -> None:
    con = _init_anchor_db()
    rows = [(backend, model, cat, json.dumps(vec, separators=(',', ':')))
            for cat, vec in anchors.items()]
    con.executemany(
        """INSERT OR REPLACE INTO anchors (backend, model, category, vector)
           VALUES (?, ?, ?, ?)""", rows)
    con.commit()
    con.close()


# ── Embedding service ────────────────────────────────────────────────────────

class EmbeddingsClassifier:
    """Lazy-loaded embeddings classifier.  Thread-safe singleton in practice
    since a single process only ever needs one backend.
    """

    _instance_lock = threading.Lock()
    _instance: 'EmbeddingsClassifier | None' = None

    def __init__(self) -> None:
        self._backend: str = ""
        self._model_name: str = ""
        self._dim: int = 0
        self._embedder = None
        self._anchors: dict[str, list[float]] = {}
        self._load_lock = threading.Lock()
        self._initialized = False

    @classmethod
    def instance(cls) -> 'EmbeddingsClassifier':
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── backend selection ───────────────────────────────────────────────────

    def _ensure_backend(self) -> None:
        if self._initialized:
            return
        with self._load_lock:
            if self._initialized:
                return
            for loader in (self._load_fastembed, self._load_model2vec,
                           self._load_sentence_transformers):
                try:
                    if loader():
                        self._initialized = True
                        return
                except Exception:
                    continue
            self._backend = "none"
            self._initialized = True

    def _load_fastembed(self) -> bool:
        fe = _try_import("fastembed")
        if fe is None or not hasattr(fe, "TextEmbedding"):
            return False
        self._embedder = fe.TextEmbedding(model_name=DEFAULT_FASTEMBED_MODEL)
        sample = list(self._embedder.embed(["probe"]))[0]
        self._dim = len(sample)
        self._backend = "fastembed"
        self._model_name = DEFAULT_FASTEMBED_MODEL
        return True

    def _load_model2vec(self) -> bool:
        m2v = _try_import("model2vec")
        if m2v is None or not hasattr(m2v, "StaticModel"):
            return False
        self._embedder = m2v.StaticModel.from_pretrained(DEFAULT_M2V_MODEL)
        sample = self._embedder.encode(["probe"])
        self._dim = int(sample.shape[1])
        self._backend = "model2vec"
        self._model_name = DEFAULT_M2V_MODEL
        return True

    def _load_sentence_transformers(self) -> bool:
        st = _try_import("sentence_transformers")
        if st is None or not hasattr(st, "SentenceTransformer"):
            return False
        self._embedder = st.SentenceTransformer(DEFAULT_ST_MODEL)
        self._dim = int(self._embedder.get_sentence_embedding_dimension())
        self._backend = "sentence_transformers"
        self._model_name = DEFAULT_ST_MODEL
        return True

    @property
    def available(self) -> bool:
        self._ensure_backend()
        return self._backend not in ("", "none")

    @property
    def backend(self) -> str:
        self._ensure_backend()
        return self._backend or "none"

    # ── embedding ────────────────────────────────────────────────────────────

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self.available or not texts:
            return [[] for _ in texts]
        if self._backend == "fastembed":
            return [list(map(float, v))
                    for v in self._embedder.embed(list(texts))]
        if self._backend == "model2vec":
            arr = self._embedder.encode(list(texts))
            return [list(map(float, row)) for row in arr]
        if self._backend == "sentence_transformers":
            arr = self._embedder.encode(list(texts), show_progress_bar=False)
            return [list(map(float, row)) for row in arr]
        return [[] for _ in texts]

    # ── anchors ──────────────────────────────────────────────────────────────

    def _load_anchors(self, categories: list[str]) -> None:
        """Embed every category once and persist.  On second run we read from
        SQLite, so the only cost is the cosine pass at classify-time.
        """
        if self._anchors:
            return
        self._ensure_backend()
        if not self.available:
            return
        cached = _load_cached_anchors(self._backend, self._model_name)
        missing = [c for c in categories if c not in cached]
        if missing:
            vecs = self._embed(missing)
            for cat, vec in zip(missing, vecs):
                if vec:
                    cached[cat] = vec
            _persist_anchors(self._backend, self._model_name,
                             {c: cached[c] for c in missing if c in cached})
        # Only retain anchors that match the current taxonomy (categories list).
        self._anchors = {c: cached[c] for c in categories if c in cached}

    def warm(self, categories: list[str]) -> None:
        """Public hook so callers can pre-load anchors at startup."""
        self._load_anchors(categories)

    # ── classification ───────────────────────────────────────────────────────

    @staticmethod
    def _build_text(name: str, ext_set: list[str] | None,
                    marketplace: str | None) -> str:
        parts = [name or ""]
        if ext_set:
            parts.append("file types: " + " ".join(sorted(set(ext_set))))
        if marketplace:
            parts.append(f"marketplace: {marketplace}")
        return " | ".join(p for p in parts if p)

    def classify(self, name: str,
                 categories: list[str],
                 ext_set: list[str] | None = None,
                 marketplace: str | None = None) -> Optional[dict]:
        """Return {'category', 'confidence', 'top1', 'margin'} or None.

        None means "I don't know — caller should fall through to AI."
        """
        if not categories:
            return None
        self._ensure_backend()
        if not self.available:
            return None
        self._load_anchors(categories)
        if not self._anchors:
            return None

        text = self._build_text(name, ext_set, marketplace)
        vec = self._embed([text])[0]
        if not vec:
            return None

        # Score every anchor.  384 cats × 384 dims is fast enough in pure
        # Python; if numpy is present we get a free speed-up via _cosine().
        np = _try_import("numpy")
        if np is not None:
            qv = np.asarray(vec, dtype="float32")
            best_cat, best, runner = "", -1.0, -1.0
            for cat, anchor in self._anchors.items():
                av = np.asarray(anchor, dtype="float32")
                s = _cosine(qv, av)
                if s > best:
                    runner = best
                    best = s
                    best_cat = cat
                elif s > runner:
                    runner = s
        else:
            best_cat, best, runner = "", -1.0, -1.0
            for cat, anchor in self._anchors.items():
                s = _cosine(vec, anchor)
                if s > best:
                    runner = best
                    best = s
                    best_cat = cat
                elif s > runner:
                    runner = s

        margin = best - max(runner, 0.0)
        if best < MIN_TOP1 or margin < MIN_MARGIN:
            return None
        return {
            'category':   best_cat,
            'confidence': HIT_CONF,
            'top1':       round(best, 4),
            'margin':     round(margin, 4),
            'cleaned_name': name,
            '_classifier': 'embeddings',
        }


def classify_one(name: str, categories: list[str],
                 ext_set: list[str] | None = None,
                 marketplace: str | None = None) -> Optional[dict]:
    """Convenience wrapper around the singleton."""
    return EmbeddingsClassifier.instance().classify(
        name, categories, ext_set=ext_set, marketplace=marketplace,
    )


def stable_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
