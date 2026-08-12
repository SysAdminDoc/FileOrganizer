"""FileOrganizer — Duplicate detection: perceptual hash, BK-tree, progressive dedup,
audio fingerprinting, and similar-content detection.

Inspired by Czkawka, Duplicate Cleaner Pro, dupeGuru, and pHash."""
import json
import os, hashlib, math, subprocess, struct, sqlite3
from pathlib import Path
from collections import Counter, defaultdict

from fileorganizer.bootstrap import HAS_PILLOW, HAS_CV2
try:
    from PIL import Image as _PILImage
except ImportError:
    pass
try:
    import cv2 as _cv2
except ImportError:
    pass

from fileorganizer.cache import hash_file
from fileorganizer.dedup_checkpoint import (
    DEFAULT_CHECKPOINT_PATH, DedupCheckpointStore, checkpoint_key,
)


# ── Audio fingerprint support (optional: chromaprint/fpcalc) ─────────────────
_HAS_FPCALC = None  # lazy-detected

def _find_fpcalc() -> str:
    """Find the fpcalc binary (Chromaprint CLI). Returns path or empty string."""
    global _HAS_FPCALC
    if _HAS_FPCALC is not None:
        return _HAS_FPCALC

    # Try common locations
    import shutil
    fpcalc = shutil.which('fpcalc')
    if fpcalc:
        _HAS_FPCALC = fpcalc
        return fpcalc

    # Windows: check common install paths
    import sys
    if sys.platform == 'win32':
        for candidate in [
            os.path.expandvars(r'%LOCALAPPDATA%\fpcalc\fpcalc.exe'),
            os.path.expandvars(r'%PROGRAMFILES%\Chromaprint\fpcalc.exe'),
            os.path.join(os.path.dirname(sys.executable), 'fpcalc.exe'),
        ]:
            if os.path.isfile(candidate):
                _HAS_FPCALC = candidate
                return candidate

    _HAS_FPCALC = ''
    return ''


def _audio_fingerprint(filepath: str, duration: int = 120) -> tuple:
    """Compute audio fingerprint using Chromaprint/fpcalc.
    Returns (duration_secs, fingerprint_list) or (0, []) on failure."""
    fpcalc = _find_fpcalc()
    if not fpcalc:
        return (0, [])
    try:
        result = subprocess.run(
            [fpcalc, '-raw', '-length', str(duration), filepath],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode != 0:
            return (0, [])

        dur = 0
        fp_data = []
        for line in result.stdout.strip().split('\n'):
            if line.startswith('DURATION='):
                dur = int(line.split('=', 1)[1])
            elif line.startswith('FINGERPRINT='):
                fp_data = [int(x) for x in line.split('=', 1)[1].split(',') if x.strip()]
        return (dur, fp_data)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, OSError):
        return (0, [])


def _fingerprint_similarity(fp1: list, fp2: list) -> float:
    """Compare two Chromaprint fingerprints. Returns similarity 0.0-1.0.
    Uses popcount of XOR to compute bit-level similarity (like Hamming distance)."""
    if not fp1 or not fp2:
        return 0.0
    # Compare overlapping portion
    length = min(len(fp1), len(fp2))
    if length == 0:
        return 0.0

    total_bits = length * 32
    diff_bits = 0
    for i in range(length):
        xor = fp1[i] ^ fp2[i]
        # Popcount
        diff_bits += bin(xor & 0xFFFFFFFF).count('1')

    return 1.0 - (diff_bits / total_bits)


AUDIO_EXTS = {'.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac', '.wma',
              '.opus', '.ape', '.aiff', '.aif'}

# ── Perceptual Hash Deduplication ────────────────────────────────────────────

def _flattened_image_data(img):
    """Return pixel data with Pillow 12.1+ API when available."""
    flattened = getattr(img, "get_flattened_data", None)
    if callable(flattened):
        return list(flattened())
    return list(img.getdata())


def _compute_phash(filepath: str, hash_size: int = 8) -> str:
    """Compute perceptual hash of an image using average hash algorithm.
    Pure Python implementation using PIL - no heavy ML dependencies.
    Returns hex string of the hash, or empty string on failure."""
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            if img.mode == 'P' and 'transparency' in img.info:
                img = img.convert('RGBA')
            img = img.convert('L').resize((hash_size + 1, hash_size), Image.LANCZOS)
            pixels = _flattened_image_data(img)
        # Difference hash (dHash): compare adjacent pixels
        bits = []
        for row in range(hash_size):
            for col in range(hash_size):
                bits.append(pixels[row * (hash_size + 1) + col] < pixels[row * (hash_size + 1) + col + 1])
        return ''.join('1' if b else '0' for b in bits)
    except Exception:
        return ''

def _hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two binary hash strings."""
    if len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def _complete_linkage_clusters(
    paths: list[str], phashes: dict[str, str], threshold: int,
    neighbor_sets: dict[str, set[str]] | None = None,
) -> list[list[str]]:
    """Group perceptual neighbors without allowing chain over-merging.

    A new item joins a cluster only when it is within the threshold of every
    existing member. This is the complete-linkage invariant: a cluster never
    contains a pair that exceeds the configured Hamming distance.
    """
    if threshold < 0:
        raise ValueError('perceptual hash threshold must be non-negative')

    clusters: list[list[str]] = []
    if neighbor_sets is None:
        neighbor_sets = {
            path: {
                neighbor for neighbor in paths
                if _hamming_distance(phashes[path], phashes[neighbor]) <= threshold
            }
            for path in paths
        }
    for path in sorted(paths):
        compatible = [
            cluster for cluster in clusters
            if all(member in neighbor_sets[path] for member in cluster)
        ]
        if not compatible:
            clusters.append([path])
            continue

        # Choose the tightest compatible cluster; size then lexical order make
        # results deterministic when several clusters are equally suitable.
        target = min(
            compatible,
            key=lambda cluster: (
                max(_hamming_distance(phashes[path], phashes[member]) for member in cluster),
                -len(cluster),
                tuple(cluster),
            ),
        )
        target.append(path)
    return [cluster for cluster in clusters if len(cluster) > 1]

class _BKTree:
    """BK-tree for efficient nearest-neighbor search under Hamming distance.
    Reduces O(n²) all-pairs comparison to ~O(n log n) for sparse matches."""

    def __init__(self, distance_fn):
        self._dist = distance_fn
        self._root = None  # (item, {distance: child_node})

    def insert(self, item):
        if self._root is None:
            self._root = (item, {})
            return
        node = self._root
        while True:
            d = self._dist(item, node[0])
            if d in node[1]:
                node = node[1][d]
            else:
                node[1][d] = (item, {})
                return

    def query(self, item, threshold):
        """Return all items within `threshold` distance of `item`."""
        if self._root is None:
            return []
        results = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            d = self._dist(item, node[0])
            if d <= threshold:
                results.append((node[0], d))
            for edge_d, child in node[1].items():
                if d - threshold <= edge_d <= d + threshold:
                    stack.append(child)
        return results


IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.avif', '.jxl'}
_PHASH_IMAGE_EXTS = IMAGE_EXTS | {'.heic', '.heif'}


class ProgressiveDuplicateDetector:
    """Multi-stage duplicate detection pipeline for files.

    Stage 1: Group by file size (zero I/O — eliminates ~80-95% of candidates)
    Stage 2: Hash first 64KB of each file (prefix hash)
    Stage 3: Hash last 64KB of each file (suffix hash)
    Stage 4: Full SHA-256 content hash for final confirmation
    Stage 5 (optional): Perceptual hash for image near-duplicates

    Results:
        dup_map:  {filepath: DupInfo} where DupInfo has group_id, is_original, detail
    """

    PARTIAL_SIZE = 65536   # 64KB prefix/suffix
    PHASH_THRESHOLD = 4    # Hamming distance ≤4 = near-duplicate

    class DupInfo:
        __slots__ = ('group_id', 'is_original', 'detail', 'is_perceptual')
        def __init__(self, group_id=0, is_original=True, detail='', is_perceptual=False):
            self.group_id = group_id
            self.is_original = is_original
            self.detail = detail
            self.is_perceptual = is_perceptual

    AUDIO_SIM_THRESHOLD = 0.85  # 85% fingerprint similarity = duplicate audio

    def __init__(self, enable_perceptual=True, enable_audio=True, phash_threshold=4,
                 checkpoint_path=DEFAULT_CHECKPOINT_PATH, checkpoint_every=25,
                 cancel_cb=None):
        self.enable_perceptual = enable_perceptual and HAS_PILLOW
        self.enable_audio = enable_audio
        self.phash_threshold = phash_threshold
        self.checkpoint_path = checkpoint_path
        self.checkpoint_every = max(1, min(int(checkpoint_every), 1000))
        self.cancel_cb = cancel_cb
        self.dup_map = {}        # filepath → DupInfo
        self._group_counter = 0
        self._checkpoint = None
        self._run_key = ''

    def _check_cancelled(self):
        return bool(self.cancel_cb and self.cancel_cb())

    def _flush_hashes(self, stage: str, pending: dict[str, str]) -> None:
        if self._checkpoint and pending:
            self._checkpoint.put_many(self._run_key, stage, pending)
            pending.clear()

    def _finish_checkpoint(self, complete: bool) -> None:
        if not self._checkpoint:
            return
        if complete and self._run_key:
            self._checkpoint.clear(self._run_key)
        self._checkpoint.close()
        self._checkpoint = None

    def _hash_stage(self, stage: str, paths: list[str], hash_fn,
                    progress_cb=None, progress_total: int | None = None) -> dict[str, str]:
        """Hash paths while reusing saved stage values and checkpointing batches."""
        result = {}
        pending = {}
        total = progress_total or len(paths)
        for index, path in enumerate(paths, start=1):
            if self._check_cancelled():
                self._cancelled_seen = True
                break
            cached = self._checkpoint.get(self._run_key, stage, path) if self._checkpoint else None
            value = cached if cached is not None else hash_fn(path)
            if value:
                result[path] = value
                if cached is None:
                    pending[path] = value
            if progress_cb:
                progress_cb(index, total)
            if len(pending) >= self.checkpoint_every:
                self._flush_hashes(stage, pending)
        self._flush_hashes(stage, pending)
        return result

    def _next_group(self) -> int:
        self._group_counter += 1
        return self._group_counter

    def detect(self, file_entries: list, log_cb=None, progress_cb=None) -> dict:
        """Run the full progressive pipeline on a list of (Path, size) tuples.

        Args:
            file_entries: list of (filepath_str, file_size) for files only (no folders)
            log_cb:       optional logging callback
            progress_cb:  optional (current, total) progress callback

        Returns:
            dict mapping filepath → DupInfo for ALL duplicates found.
            Files not in the dict are unique.
        """
        self.dup_map.clear()
        self._group_counter = 0
        self._cancelled_seen = False

        if len(file_entries) < 2:
            return self.dup_map

        normalized_entries = []
        for entry in file_entries:
            path = str(entry[0])
            size = int(entry[1]) if len(entry) > 1 else 0
            if len(entry) > 2:
                mtime_ns = int(entry[2])
            else:
                try:
                    mtime_ns = os.stat(path).st_mtime_ns
                except OSError:
                    mtime_ns = 0
            normalized_entries.append((path, size, mtime_ns))
        file_entries = normalized_entries
        if self.checkpoint_path:
            try:
                self._checkpoint = DedupCheckpointStore(self.checkpoint_path)
                self._checkpoint.open()
                self._checkpoint.prune()
                self._run_key = checkpoint_key(file_entries)
            except (OSError, sqlite3.Error):
                self._checkpoint = None
                self._run_key = ''

        # ── Stage 1: Group by size ───────────────────────────────────────────
        if log_cb:
            log_cb(f"  [DEDUP] Stage 1: Grouping {len(file_entries)} files by size…")
        size_groups = {}
        for entry in file_entries:
            fpath, fsize = entry[0], entry[1]
            if fsize > 0:
                size_groups.setdefault(fsize, []).append(fpath)

        # Eliminate unique sizes
        candidates = {sz: paths for sz, paths in size_groups.items() if len(paths) > 1}
        n_candidates = sum(len(p) for p in candidates.values())
        n_eliminated = len(file_entries) - n_candidates
        if log_cb:
            log_cb(f"  [DEDUP] Stage 1: {n_eliminated} unique sizes eliminated, "
                   f"{n_candidates} candidates in {len(candidates)} size groups")
        if not candidates:
            self._run_perceptual(file_entries, log_cb)
            self._run_audio_fingerprint(file_entries, log_cb)
            self._finish_checkpoint(complete=not self._cancelled_seen)
            return self.dup_map
        # ── Stage 2: Prefix hash (first 64KB) ───────────────────────────────
        if log_cb:
            log_cb(f"  [DEDUP] Stage 2: Prefix hash ({n_candidates} files)…")
        prefix_groups = {}
        size_by_path = {
            fpath: sz for sz, paths in candidates.items() for fpath in paths
        }
        candidate_paths = list(size_by_path)
        prefix_hashes = self._hash_stage(
            'prefix',
            candidate_paths,
            lambda path: self._hash_partial(
                path, offset=0, size=min(self.PARTIAL_SIZE, size_by_path[path])
            ),
            progress_cb=progress_cb,
            progress_total=n_candidates,
        )
        if self._cancelled_seen:
            if log_cb:
                log_cb("  [DEDUP] Checkpoint saved; scan cancelled during prefix hashing")
            self._finish_checkpoint(complete=False)
            return self.dup_map
        for sz, paths in candidates.items():
            bucket = {}
            for fpath in paths:
                h = prefix_hashes.get(fpath)
                if h:
                    bucket.setdefault(h, []).append(fpath)
            for h, group_paths in bucket.items():
                if len(group_paths) > 1:
                    prefix_groups[(sz, h)] = group_paths

        n_prefix = sum(len(p) for p in prefix_groups.values())
        if log_cb:
            log_cb(f"  [DEDUP] Stage 2: {n_prefix} files share prefix hashes")
        if not prefix_groups:
            self._run_perceptual(file_entries, log_cb)
            self._run_audio_fingerprint(file_entries, log_cb)
            self._finish_checkpoint(complete=not self._cancelled_seen)
            return self.dup_map

        # ── Stage 3: Suffix hash (last 64KB) ────────────────────────────────
        if log_cb:
            log_cb(f"  [DEDUP] Stage 3: Suffix hash ({n_prefix} files)…")
        suffix_groups = {}
        suffix_paths = []
        for (sz, ph), paths in prefix_groups.items():
            if sz <= self.PARTIAL_SIZE:
                # File is small enough that prefix covered entire file — already confirmed
                suffix_groups[(sz, ph, 'full')] = paths
                continue
            suffix_paths.extend(paths)

        suffix_hashes = self._hash_stage(
            'suffix',
            suffix_paths,
            lambda path: self._hash_partial(
                path,
                offset=max(0, size_by_path[path] - self.PARTIAL_SIZE),
                size=self.PARTIAL_SIZE,
            ),
            progress_cb=progress_cb,
            progress_total=len(suffix_paths),
        )
        if self._cancelled_seen:
            if log_cb:
                log_cb("  [DEDUP] Checkpoint saved; scan cancelled during suffix hashing")
            self._finish_checkpoint(complete=False)
            return self.dup_map
        for (sz, ph), paths in prefix_groups.items():
            if sz <= self.PARTIAL_SIZE:
                continue
            bucket = {}
            for fpath in paths:
                h = suffix_hashes.get(fpath)
                if h:
                    bucket.setdefault(h, []).append(fpath)
            for sh, group_paths in bucket.items():
                if len(group_paths) > 1:
                    suffix_groups[(sz, ph, sh)] = group_paths

        n_suffix = sum(len(p) for p in suffix_groups.values())
        if log_cb:
            log_cb(f"  [DEDUP] Stage 3: {n_suffix} files share prefix+suffix hashes")
        if not suffix_groups:
            self._run_perceptual(file_entries, log_cb)
            self._run_audio_fingerprint(file_entries, log_cb)
            self._finish_checkpoint(complete=not self._cancelled_seen)
            return self.dup_map

        # ── Stage 4: Full content hash ───────────────────────────────────────
        if log_cb:
            log_cb(f"  [DEDUP] Stage 4: Full SHA-256 ({n_suffix} files)…")
        full_groups = {}
        full_hash_paths = []
        for key, paths in suffix_groups.items():
            sz = key[0]
            if sz <= self.PARTIAL_SIZE:
                # Prefix hash already covered entire file — no need to re-hash
                full_groups[key] = paths
                continue
            full_hash_paths.extend(paths)

        full_hashes = self._hash_stage(
            'full',
            full_hash_paths,
            self._hash_full,
            progress_cb=progress_cb,
            progress_total=len(full_hash_paths),
        )
        if self._cancelled_seen:
            if log_cb:
                log_cb("  [DEDUP] Checkpoint saved; scan cancelled during full hashing")
            self._finish_checkpoint(complete=False)
            return self.dup_map
        for key, paths in suffix_groups.items():
            if key[0] <= self.PARTIAL_SIZE:
                continue
            bucket = {}
            for fpath in paths:
                h = full_hashes.get(fpath)
                if h:
                    bucket.setdefault(h, []).append(fpath)
            for fh, group_paths in bucket.items():
                if len(group_paths) > 1:
                    full_groups.setdefault(fh, []).extend(group_paths)

        # ── Assign groups ────────────────────────────────────────────────────
        total_dup_files = 0
        for fh, paths in full_groups.items():
            gid = self._next_group()
            # First file is the "original" (keep), rest are duplicates
            # Sort by mtime descending — newest is "original"
            try:
                paths_sorted = sorted(paths, key=lambda p: os.path.getmtime(p), reverse=True)
            except OSError:
                paths_sorted = paths
            for i, fpath in enumerate(paths_sorted):
                is_orig = (i == 0)
                detail = (f"Group {gid}: original (newest)" if is_orig
                          else f"Group {gid}: duplicate of {os.path.basename(paths_sorted[0])}")
                self.dup_map[fpath] = self.DupInfo(
                    group_id=gid, is_original=is_orig, detail=detail)
                if not is_orig:
                    total_dup_files += 1

        if log_cb:
            n_groups = len(full_groups)
            log_cb(f"  [DEDUP] Stage 4: {n_groups} duplicate groups, "
                   f"{total_dup_files} duplicate files")

        # ── Stage 5: Perceptual image hashing ────────────────────────────────
        self._run_perceptual(file_entries, log_cb)

        if self._cancelled_seen:
            if log_cb:
                log_cb("  [DEDUP] Checkpoint saved; scan cancelled during perceptual hashing")
            self._finish_checkpoint(complete=False)
            return self.dup_map

        # ── Stage 6: Audio fingerprinting (Chromaprint) ──────────────────────
        self._run_audio_fingerprint(file_entries, log_cb)

        if self._cancelled_seen:
            if log_cb:
                log_cb("  [DEDUP] Checkpoint saved; scan cancelled during audio fingerprinting")
            self._finish_checkpoint(complete=False)
            return self.dup_map

        self._finish_checkpoint(complete=True)
        return self.dup_map

    def _run_perceptual(self, file_entries: list, log_cb=None):
        """Stage 5: Find near-duplicate images via perceptual hashing."""
        if not self.enable_perceptual or self._cancelled_seen:
            return
        if self._check_cancelled():
            self._cancelled_seen = True
            return
        # Collect image files not already flagged as exact duplicates
        images = [entry[0] for entry in file_entries
                  if os.path.splitext(entry[0])[1].lower() in _PHASH_IMAGE_EXTS
                  and entry[0] not in self.dup_map]
        if len(images) < 2:
            return
        if log_cb:
            log_cb(f"  [DEDUP] Stage 5: Perceptual hashing {len(images)} images…")

        # Compute dHash for each image
        phashes = self._hash_stage('phash', images, _compute_phash)

        if self._cancelled_seen or len(phashes) < 2:
            return

        # BK-tree for efficient nearest-neighbor search — O(n log n) vs O(n²)
        paths = list(phashes.keys())
        tree = _BKTree(lambda a, b: _hamming_distance(phashes[a], phashes[b]))
        for p in paths:
            tree.insert(p)

        # Prime the BK-tree query for each image so the complete-linkage
        # builder only considers threshold-neighbor candidates. The builder
        # still checks every member before joining a cluster.
        neighbor_sets = {
            path: {
                neighbor for neighbor, _distance in tree.query(
                    path, self.phash_threshold
                )
            }
            for path in paths
        }
        perceptual_groups = _complete_linkage_clusters(
            paths,
            phashes,
            self.phash_threshold,
            neighbor_sets=neighbor_sets,
        )

        # Assign perceptual duplicate groups
        n_perceptual = 0
        for group in perceptual_groups:
            gid = self._next_group()
            # Keep the largest file as original
            try:
                group_sorted = sorted(group, key=lambda p: os.path.getsize(p), reverse=True)
            except OSError:
                group_sorted = group
            for i, fpath in enumerate(group_sorted):
                is_orig = (i == 0)
                detail = (f"Group {gid} (visual): original (largest)" if is_orig
                          else f"Group {gid} (visual): near-duplicate of "
                               f"{os.path.basename(group_sorted[0])}")
                self.dup_map[fpath] = self.DupInfo(
                    group_id=gid, is_original=is_orig, detail=detail,
                    is_perceptual=True)
                if not is_orig:
                    n_perceptual += 1

        if log_cb and n_perceptual > 0:
            log_cb(f"  [DEDUP] Stage 5: {n_perceptual} near-duplicate images found")

    def _run_audio_fingerprint(self, file_entries: list, log_cb=None):
        """Stage 6: Find similar audio files via Chromaprint acoustic fingerprinting."""
        if not self.enable_audio or self._cancelled_seen:
            return
        if self._check_cancelled():
            self._cancelled_seen = True
            return
        if not _find_fpcalc():
            if log_cb:
                log_cb("  [DEDUP] Stage 6: Skipped (fpcalc not found — install Chromaprint)")
            return

        # Collect audio files not already flagged as exact duplicates
        audio_files = [entry[0] for entry in file_entries
                       if os.path.splitext(entry[0])[1].lower() in AUDIO_EXTS
                       and entry[0] not in self.dup_map]
        if len(audio_files) < 2:
            return
        if log_cb:
            log_cb(f"  [DEDUP] Stage 6: Audio fingerprinting {len(audio_files)} files…")

        # Compute fingerprints
        encoded = self._hash_stage(
            'audio',
            audio_files,
            lambda path: json.dumps(_audio_fingerprint(path), separators=(',', ':')),
        )
        if self._cancelled_seen:
            return
        fingerprints = {}
        for fpath, raw in encoded.items():
            try:
                dur, fp = json.loads(raw)
                dur = int(dur)
                fp = [int(value) for value in fp]
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if fp and dur > 5:  # skip very short clips
                fingerprints[fpath] = (dur, fp)

        if len(fingerprints) < 2:
            return

        # Compare all pairs (audio collections are typically smaller than image sets)
        paths = list(fingerprints.keys())
        assigned = set()
        n_audio_dups = 0

        # Group by similar duration first to reduce comparisons
        dur_buckets = defaultdict(list)
        for fpath, (dur, fp) in fingerprints.items():
            bucket = dur // 10  # 10-second buckets
            dur_buckets[bucket].append(fpath)
            # Also add to adjacent buckets for edge cases
            dur_buckets[bucket - 1].append(fpath)
            dur_buckets[bucket + 1].append(fpath)

        compared = set()
        for bucket_paths in dur_buckets.values():
            for i in range(len(bucket_paths)):
                for j in range(i + 1, len(bucket_paths)):
                    p1, p2 = bucket_paths[i], bucket_paths[j]
                    pair_key = (min(p1, p2), max(p1, p2))
                    if pair_key in compared or p1 in assigned or p2 in assigned:
                        continue
                    compared.add(pair_key)

                    sim = _fingerprint_similarity(
                        fingerprints[p1][1], fingerprints[p2][1])
                    if sim >= self.AUDIO_SIM_THRESHOLD:
                        gid = self._next_group()
                        # Keep larger file as original
                        try:
                            sz1, sz2 = os.path.getsize(p1), os.path.getsize(p2)
                        except OSError:
                            sz1, sz2 = 0, 0
                        orig, dup = (p1, p2) if sz1 >= sz2 else (p2, p1)

                        self.dup_map[orig] = self.DupInfo(
                            group_id=gid, is_original=True,
                            detail=f"Group {gid} (audio): original (largest)",
                            is_perceptual=True)
                        self.dup_map[dup] = self.DupInfo(
                            group_id=gid, is_original=False,
                            detail=f"Group {gid} (audio {sim:.0%} match): "
                                   f"similar to {os.path.basename(orig)}",
                            is_perceptual=True)
                        assigned.update({p1, p2})
                        n_audio_dups += 1

        if log_cb and n_audio_dups > 0:
            log_cb(f"  [DEDUP] Stage 6: {n_audio_dups} similar audio pairs found")

    @staticmethod
    def _hash_partial(filepath: str, offset: int, size: int) -> str:
        """Hash a portion of a file. Returns hex digest or None."""
        try:
            h = hashlib.sha256()
            with open(filepath, 'rb') as f:
                f.seek(offset)
                remaining = size
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    h.update(chunk)
                    remaining -= len(chunk)
            return h.hexdigest()
        except (PermissionError, OSError):
            return None

    @staticmethod
    def _hash_full(filepath: str) -> str:
        """Full SHA-256 hash of a file. Returns hex digest or None."""
        try:
            h = hashlib.sha256()
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except (PermissionError, OSError):
            return None


# ══════════════════════════════════════════════════════════════════════════════
# CONFLICT RESOLUTION ENGINE
# Detects destination path collisions and resolves them via configurable strategy.
# ══════════════════════════════════════════════════════════════════════════════

class ConflictResolver:
    """Detects and resolves destination path conflicts among FileItems."""

    STRATEGIES = ('auto_suffix', 'keep_newest', 'keep_largest', 'skip')

    @staticmethod
    def detect(items) -> dict:
        """Return {dest_path: [list of FileItems]} for paths with >1 item."""
        by_dest = {}
        for it in items:
            if not it.selected or it.status != "Pending":
                continue
            dp = it.full_dst.lower() if it.full_dst else ''
            if dp:
                by_dest.setdefault(dp, []).append(it)
        return {k: v for k, v in by_dest.items() if len(v) > 1}

    @staticmethod
    def resolve(conflicts: dict, strategy: str, items: list) -> int:
        """Resolve conflicts. Returns count of adjustments made."""
        count = 0
        for dest_path, dupes in conflicts.items():
            if strategy == 'auto_suffix':
                # Keep first, suffix the rest
                for i, it in enumerate(dupes[1:], start=1):
                    stem, ext = os.path.splitext(it.full_dst)
                    it.full_dst = f"{stem}_{i:03d}{ext}"
                    it.display_name = os.path.basename(it.full_dst)
                    count += 1
            elif strategy == 'keep_newest':
                # Sort by mtime descending, deselect all but newest
                ranked = sorted(dupes, key=lambda x: os.path.getmtime(x.full_src)
                                if os.path.exists(x.full_src) else 0, reverse=True)
                for it in ranked[1:]:
                    it.selected = False
                    it.detail = "Conflict: kept newest"
                    count += 1
            elif strategy == 'keep_largest':
                ranked = sorted(dupes, key=lambda x: x.size, reverse=True)
                for it in ranked[1:]:
                    it.selected = False
                    it.detail = "Conflict: kept largest"
                    count += 1
            elif strategy == 'skip':
                for it in dupes[1:]:
                    it.selected = False
                    it.detail = "Conflict: skipped"
                    count += 1
        return count


