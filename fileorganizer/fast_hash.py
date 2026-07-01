"""Fast fingerprint hashing with algorithm selection (NEXT-33).

Supports sha256 (builtin), blake3 (optional, ~10x faster), and xxhash
(optional, ~15x faster). Defaults to blake3 when installed, falls back
to sha256.

The DeDuper tiered-hash pattern (size -> partial -> full) is included
as `tiered_hash()` for I/O-efficient dedup scanning.
"""
import hashlib
import importlib.util
import os
from typing import Optional, Tuple

_HAS_BLAKE3 = importlib.util.find_spec("blake3") is not None
_HAS_XXHASH = importlib.util.find_spec("xxhash") is not None

ALGO_SHA256 = "sha256"
ALGO_BLAKE3 = "blake3"
ALGO_XXHASH = "xxhash"

_CHUNK_SIZE = 65536
_PARTIAL_SIZE = 65536


def default_algo() -> str:
    """Return the best available hash algorithm."""
    if _HAS_BLAKE3:
        return ALGO_BLAKE3
    return ALGO_SHA256


def hash_file(filepath: str, algo: Optional[str] = None,
              chunk_size: int = _CHUNK_SIZE) -> Optional[Tuple[str, str]]:
    """Hash a file with the specified algorithm.

    Returns (hex_digest, algo_name) or None on error.
    """
    if algo is None:
        algo = default_algo()

    try:
        if algo == ALGO_BLAKE3 and _HAS_BLAKE3:
            import blake3
            h = blake3.blake3()
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest(), ALGO_BLAKE3

        if algo == ALGO_XXHASH and _HAS_XXHASH:
            import xxhash
            h = xxhash.xxh128()
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest(), ALGO_XXHASH

        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest(), ALGO_SHA256

    except (PermissionError, OSError):
        return None


def partial_hash(filepath: str, size: int = _PARTIAL_SIZE,
                 algo: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Hash only the first `size` bytes of a file (fast pre-filter).

    Returns (hex_digest, algo_name) or None.
    """
    if algo is None:
        algo = default_algo()

    try:
        if algo == ALGO_BLAKE3 and _HAS_BLAKE3:
            import blake3
            h = blake3.blake3()
            with open(filepath, "rb") as f:
                data = f.read(size)
                h.update(data)
            return h.hexdigest(), ALGO_BLAKE3

        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            data = f.read(size)
            h.update(data)
        return h.hexdigest(), ALGO_SHA256

    except (PermissionError, OSError):
        return None


def tiered_hash(filepath: str, algo: Optional[str] = None) -> Optional[Tuple[str, str, str]]:
    """Three-tier hash: size -> partial (64KB head) -> full hash.

    Returns (size_key, partial_digest, full_digest) or None.
    Callers can compare tiers progressively to skip expensive full hashes.
    """
    try:
        file_size = os.path.getsize(filepath)
    except OSError:
        return None

    size_key = str(file_size)

    partial = partial_hash(filepath, algo=algo)
    if partial is None:
        return None

    full = hash_file(filepath, algo=algo)
    if full is None:
        return None

    return size_key, partial[0], full[0]


def available_algorithms() -> list:
    """Return list of available hash algorithm names."""
    algos = [ALGO_SHA256]
    if _HAS_BLAKE3:
        algos.append(ALGO_BLAKE3)
    if _HAS_XXHASH:
        algos.append(ALGO_XXHASH)
    return algos
