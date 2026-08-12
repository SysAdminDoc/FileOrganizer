"""FileOrganizer — Archive inspection and extraction pipeline.

Supports: ZIP, RAR, 7z, TAR (including .gz/.bz2/.xz)

Workflow:
  1. inspect_archive()    — peek at contents, detect if it's a design archive
  2. extract_design_archive() — extract to temp/staging dir, return file list
  3. Caller classifies extracted files and moves them to organized destination

Design file extensions that trigger extraction:
  .aep .aepx .prproj .psd .psb .ai .indd .idml .mogrt .xd
  .wav .mp3 .aiff .flac .ogg .mid .ttf .otf .lut .cube
"""
import os, re, shutil, tempfile, zipfile, tarfile, logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from fileorganizer.safe_archive import UnsafeArchiveEntryError, safe_extract_path

log = logging.getLogger(__name__)

# ── Design file classification ─────────────────────────────────────────────────

DESIGN_EXTENSIONS = {
    # Project files
    '.aep', '.aepx',            # After Effects
    '.prproj',                  # Premiere Pro
    '.psd', '.psb',             # Photoshop
    '.ai',                      # Illustrator
    '.indd', '.idml',           # InDesign
    '.mogrt',                   # Motion Graphics Template
    '.xd',                      # Adobe XD
    '.fig',                     # Figma (exported)
    '.sketch',                  # Sketch
    # Audio
    '.wav', '.aiff', '.aif',
    '.mp3', '.flac', '.ogg',
    '.mid', '.midi',
    # Video  
    '.mp4', '.mov', '.mxf',
    '.r3d', '.avi', '.mkv',
    # Fonts
    '.ttf', '.otf', '.woff', '.woff2',
    # Color grading
    '.lut', '.cube', '.3dl', '.look',
    # 3D model / scene formats
    '.gltf', '.glb', '.drc', '.usd', '.usda', '.usdc', '.usdz',
    # Images (common in design packs)
    '.png', '.jpg', '.jpeg', '.tiff', '.tif',
    # Documents
    '.pdf',
}

# Extensions that are the "main" deliverable (not just assets)
CORE_DESIGN_EXTENSIONS = {
    '.aep', '.aepx', '.prproj', '.psd', '.psb',
    '.ai', '.indd', '.idml', '.mogrt',
}

# Extensions we never want to extract or keep
_JUNK_EXTENSIONS = {
    '.db', '.ds_store', '.thumbs', '.url', '.lnk',
    '.nfo', '.txt',  # readme files excluded from design asset detection
}

_ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar',
                       '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz',
                       '.zst', '.tar.zst'}


def _normalize_member_name(member_name: str) -> str:
    return str(member_name or '').replace('\\', '/')


def _member_output_name(member_name: str, top_folder: Optional[str], *,
                        flatten: bool, strip_top_folder: bool) -> str:
    normalized = _normalize_member_name(member_name)
    p = PurePosixPath(normalized)
    if flatten:
        return p.name
    if strip_top_folder and top_folder:
        top = _normalize_member_name(top_folder).strip('/')
        parts = p.parts
        if parts and parts[0] == top:
            return '/'.join(parts[1:])
    return normalized


def _safe_member_destination(dest_dir: str, member_name: str,
                             top_folder: Optional[str] = None, *,
                             flatten: bool = False,
                             strip_top_folder: bool = True,
                             validation_root: Optional[str] = None) -> str:
    """Validate archive member and return its safe output path."""
    normalized = _normalize_member_name(member_name)
    safe_extract_path(validation_root or dest_dir, normalized)
    output_name = _member_output_name(
        normalized,
        top_folder,
        flatten=flatten,
        strip_top_folder=strip_top_folder,
    )
    return safe_extract_path(dest_dir, output_name)


def is_archive(path: str) -> bool:
    p = Path(path)
    name_lower = p.name.lower()
    return (p.suffix.lower() in _ARCHIVE_EXTENSIONS
            or name_lower.endswith(('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst')))


def is_design_file(path: str) -> bool:
    return Path(path).suffix.lower() in DESIGN_EXTENSIONS


def is_core_design_file(path: str) -> bool:
    return Path(path).suffix.lower() in CORE_DESIGN_EXTENSIONS


# ── Extraction safety limits ─────────────────────────────────────────────────

@dataclass(frozen=True)
class ArchiveLimits:
    """Resource ceilings applied before and during archive extraction."""

    max_entries: Optional[int] = 100_000
    max_total_bytes: Optional[int] = 20 * 1024 * 1024 * 1024
    max_entry_bytes: Optional[int] = 4 * 1024 * 1024 * 1024
    max_compression_ratio: Optional[float] = 1_000.0
    min_free_bytes: Optional[int] = 256 * 1024 * 1024


DEFAULT_ARCHIVE_LIMITS = ArchiveLimits()


class ArchiveExtractionError(RuntimeError):
    """Structured failure raised when extraction cannot safely continue."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class ArchiveLimitError(ArchiveExtractionError):
    """Raised when an archive exceeds a configured extraction ceiling."""


class ArchiveExtractionCancelled(ArchiveExtractionError):
    """Raised when the caller cancels an extraction in progress."""

    def __init__(self):
        super().__init__('cancelled', 'archive extraction was cancelled')


_COPY_CHUNK_SIZE = 1024 * 1024


def _check_cancelled(cancel_cb: Optional[Callable[[], bool]]) -> None:
    if cancel_cb and cancel_cb():
        raise ArchiveExtractionCancelled()


def _top_level_folder(member_names: list[str]) -> Optional[str]:
    roots = set()
    for member_name in member_names:
        parts = PurePosixPath(_normalize_member_name(member_name)).parts
        if parts:
            roots.add(parts[0])
    return next(iter(roots)) if len(roots) == 1 else None


def _existing_disk_path(path: str) -> str:
    candidate = Path(os.path.abspath(path))
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return str(candidate)


def _preflight_archive_limits(
    archive_path: str,
    dest_dir: str,
    entries: list[tuple[str, Optional[int], Optional[int]]],
    limits: ArchiveLimits,
) -> None:
    """Reject oversized archives before opening any output file."""
    if limits.max_entries is not None and len(entries) > limits.max_entries:
        raise ArchiveLimitError(
            'entry_count',
            f"{len(entries)} entries exceeds the limit of {limits.max_entries}",
        )

    total_bytes = 0
    known_total = True
    for name, raw_size, compressed_size in entries:
        size = None if raw_size is None else int(raw_size)
        if size is None:
            known_total = False
            continue
        if size < 0:
            raise ArchiveLimitError('entry_size', f"negative size for {name!r}")
        if limits.max_entry_bytes is not None and size > limits.max_entry_bytes:
            raise ArchiveLimitError(
                'entry_size',
                f"{name!r} is {size} bytes; limit is {limits.max_entry_bytes}",
            )
        total_bytes += size
        if limits.max_total_bytes is not None and total_bytes > limits.max_total_bytes:
            raise ArchiveLimitError(
                'total_size',
                f"declared size exceeds the limit of {limits.max_total_bytes} bytes",
            )
        if limits.max_compression_ratio is not None and compressed_size is not None:
            compressed = int(compressed_size)
            if compressed < 0:
                raise ArchiveLimitError('compressed_size', f"negative size for {name!r}")
            ratio = float('inf') if size and not compressed else (
                size / compressed if compressed else 1.0
            )
            if ratio > limits.max_compression_ratio:
                raise ArchiveLimitError(
                    'compression_ratio',
                    f"{name!r} expands at {ratio:.1f}:1; limit is "
                    f"{limits.max_compression_ratio:.1f}:1",
                )

    archive_size = os.path.getsize(archive_path)
    if (known_total and total_bytes and archive_size
            and limits.max_compression_ratio is not None
            and total_bytes / archive_size > limits.max_compression_ratio):
        ratio = total_bytes / archive_size
        raise ArchiveLimitError(
            'compression_ratio',
            f"archive expands at {ratio:.1f}:1; limit is "
            f"{limits.max_compression_ratio:.1f}:1",
        )

    required_free = (total_bytes if known_total else 0) + (limits.min_free_bytes or 0)
    if limits.min_free_bytes is not None:
        free_bytes = shutil.disk_usage(_existing_disk_path(dest_dir)).free
        if free_bytes < required_free:
            raise ArchiveLimitError(
                'free_space',
                f"{free_bytes} bytes free; need at least {required_free}",
            )


def _copy_stream_bounded(
    source,
    target,
    *,
    name: str,
    limits: ArchiveLimits,
    total_written: int,
    cancel_cb: Optional[Callable[[], bool]],
) -> int:
    """Copy an archive member while enforcing actual byte ceilings."""
    entry_written = 0
    while True:
        _check_cancelled(cancel_cb)
        chunk = source.read(_COPY_CHUNK_SIZE)
        if not chunk:
            break
        entry_written += len(chunk)
        if (limits.max_entry_bytes is not None
                and entry_written > limits.max_entry_bytes):
            raise ArchiveLimitError(
                'entry_size',
                f"{name!r} exceeded {limits.max_entry_bytes} bytes while streaming",
            )
        if (limits.max_total_bytes is not None
                and total_written + entry_written > limits.max_total_bytes):
            raise ArchiveLimitError(
                'total_size',
                f"extraction exceeded {limits.max_total_bytes} bytes while streaming",
            )
        target.write(chunk)
    return entry_written


# ── Archive inspection ─────────────────────────────────────────────────────────

def inspect_archive(path: str, max_entries: int = 500) -> dict:
    """
    Peek inside an archive without extracting.

    Returns:
      {
        'format': 'zip' | 'rar' | '7z' | 'tar',
        'total_files': int,
        'design_files': [filename, ...],   # core design files found
        'asset_files': [filename, ...],    # other design assets
        'has_design_content': bool,
        'total_compressed_size': int,      # bytes (0 if unknown)
        'total_uncompressed_size': int,    # bytes (0 if unknown)
        'top_level_folder': str | None,    # if all files under one root folder
        'error': str | None,
      }
    """
    result = {
        'format': '',
        'total_files': 0,
        'design_files': [],
        'asset_files': [],
        'has_design_content': False,
        'total_compressed_size': 0,
        'total_uncompressed_size': 0,
        'top_level_folder': None,
        'error': None,
    }

    path = str(path)
    name_lower = Path(path).name.lower()

    try:
        if zipfile.is_zipfile(path):
            result['format'] = 'zip'
            with zipfile.ZipFile(path, 'r') as zf:
                infos = zf.infolist()[:max_entries]
                result['total_files'] = len(zf.infolist())
                roots = set()
                for info in infos:
                    parts = Path(info.filename).parts
                    if parts:
                        roots.add(parts[0])
                    result['total_uncompressed_size'] += info.file_size
                    result['total_compressed_size'] += info.compress_size
                    ext = Path(info.filename).suffix.lower()
                    if ext in CORE_DESIGN_EXTENSIONS:
                        result['design_files'].append(info.filename)
                    elif ext in DESIGN_EXTENSIONS:
                        result['asset_files'].append(info.filename)
                if len(roots) == 1:
                    result['top_level_folder'] = list(roots)[0]

        elif name_lower.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
            result['format'] = 'tar'
            with tarfile.open(path, 'r:*') as tf:
                members = tf.getmembers()[:max_entries]
                result['total_files'] = len(tf.getmembers())
                roots = set()
                for m in members:
                    parts = Path(m.name).parts
                    if parts:
                        roots.add(parts[0])
                    result['total_uncompressed_size'] += m.size
                    ext = Path(m.name).suffix.lower()
                    if ext in CORE_DESIGN_EXTENSIONS:
                        result['design_files'].append(m.name)
                    elif ext in DESIGN_EXTENSIONS:
                        result['asset_files'].append(m.name)
                if len(roots) == 1:
                    result['top_level_folder'] = list(roots)[0]

        elif name_lower.endswith('.7z'):
            result['format'] = '7z'
            try:
                import py7zr
                with py7zr.SevenZipFile(path, 'r') as sz:
                    names = sz.getnames()[:max_entries]
                    result['total_files'] = len(sz.getnames())
                    roots = set()
                    for n in names:
                        parts = Path(n).parts
                        if parts:
                            roots.add(parts[0])
                        ext = Path(n).suffix.lower()
                        if ext in CORE_DESIGN_EXTENSIONS:
                            result['design_files'].append(n)
                        elif ext in DESIGN_EXTENSIONS:
                            result['asset_files'].append(n)
                    if len(roots) == 1:
                        result['top_level_folder'] = list(roots)[0]
            except ImportError:
                result['error'] = '7z support requires py7zr (pip install py7zr)'
            except Exception as e:
                result['error'] = str(e)

        elif name_lower.endswith('.rar'):
            result['format'] = 'rar'
            try:
                import rarfile
                with rarfile.RarFile(path) as rf:
                    infos = rf.infolist()[:max_entries]
                    result['total_files'] = len(rf.infolist())
                    roots = set()
                    for info in infos:
                        parts = Path(info.filename).parts
                        if parts:
                            roots.add(parts[0])
                        result['total_uncompressed_size'] += info.file_size
                        ext = Path(info.filename).suffix.lower()
                        if ext in CORE_DESIGN_EXTENSIONS:
                            result['design_files'].append(info.filename)
                        elif ext in DESIGN_EXTENSIONS:
                            result['asset_files'].append(info.filename)
                    if len(roots) == 1:
                        result['top_level_folder'] = list(roots)[0]
            except ImportError:
                result['error'] = 'RAR support requires rarfile (pip install rarfile)'
            except Exception as e:
                result['error'] = str(e)

    except Exception as e:
        result['error'] = str(e)

    result['has_design_content'] = bool(result['design_files'] or result['asset_files'])
    return result


def is_design_archive(path: str) -> bool:
    """Quick check: does this archive contain design assets?"""
    if not is_archive(path):
        return False
    info = inspect_archive(path, max_entries=100)
    return info.get('has_design_content', False)


# ── Archive extraction ─────────────────────────────────────────────────────────

def extract_archive(path: str, dest_dir: str, *,
                    flatten: bool = False,
                    strip_top_folder: bool = True,
                    log_cb=None,
                    limits: Optional[ArchiveLimits] = None,
                    cancel_cb: Optional[Callable[[], bool]] = None) -> list:
    """
    Extract archive to dest_dir.

    Args:
      path:             Source archive path
      dest_dir:         Target directory (created if needed)
      flatten:          If True, all files go directly into dest_dir (no subfolders)
      strip_top_folder: If archive has one root folder, extract its contents directly
                        into dest_dir instead of creating dest_dir/<root>/<files>
      log_cb:           Optional callback(message: str) for progress logging
      limits:           Resource ceilings; defaults to DEFAULT_ARCHIVE_LIMITS
      cancel_cb:        Optional callback returning True to cancel extraction

    Returns:
      List of absolute paths of extracted files (files only, not dirs)
    """
    limits = limits or DEFAULT_ARCHIVE_LIMITS
    dest_was_absent = not os.path.lexists(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    extracted = []
    created_files = []
    name_lower = Path(path).name.lower()

    def _log(msg):
        if log_cb:
            log_cb(msg)
        else:
            log.debug(msg)

    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, 'r') as zf:
                members = zf.infolist()
                _preflight_archive_limits(
                    path,
                    dest_dir,
                    [(m.filename, m.file_size, m.compress_size) for m in members],
                    limits,
                )
                top = (_top_level_folder([m.filename for m in members])
                       if strip_top_folder else None)
                total_written = 0
                for member in members:
                    _check_cancelled(cancel_cb)
                    if member.is_dir():
                        continue
                    try:
                        dst = _safe_member_destination(
                            dest_dir, member.filename, top,
                            flatten=flatten,
                            strip_top_folder=strip_top_folder,
                        )
                    except UnsafeArchiveEntryError:
                        _log(f"  Skipped (path traversal): {member.filename}")
                        continue
                    if os.path.lexists(dst):
                        raise ArchiveExtractionError(
                            'destination_exists', f"output already exists: {dst}")
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    created_files.append(dst)
                    with zf.open(member) as src, open(dst, 'xb') as out:
                        total_written += _copy_stream_bounded(
                            src,
                            out,
                            name=member.filename,
                            limits=limits,
                            total_written=total_written,
                            cancel_cb=cancel_cb,
                        )
                    extracted.append(dst)
                    _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

        elif name_lower.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
            with tarfile.open(path, 'r:*') as tf:
                members = tf.getmembers()
                _preflight_archive_limits(
                    path,
                    dest_dir,
                    [(m.name, m.size, None) for m in members],
                    limits,
                )
                top = (_top_level_folder([m.name for m in members])
                       if strip_top_folder else None)
                total_written = 0
                for member in members:
                    _check_cancelled(cancel_cb)
                    if not member.isfile():
                        continue
                    try:
                        dst = _safe_member_destination(
                            dest_dir, member.name, top,
                            flatten=flatten,
                            strip_top_folder=strip_top_folder,
                        )
                    except UnsafeArchiveEntryError:
                        _log(f"  Skipped (path traversal): {member.name}")
                        continue
                    if os.path.lexists(dst):
                        raise ArchiveExtractionError(
                            'destination_exists', f"output already exists: {dst}")
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    f = tf.extractfile(member)
                    if f:
                        created_files.append(dst)
                        with f, open(dst, 'xb') as out:
                            total_written += _copy_stream_bounded(
                                f,
                                out,
                                name=member.name,
                                limits=limits,
                                total_written=total_written,
                                cancel_cb=cancel_cb,
                            )
                        extracted.append(dst)
                        _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

        elif name_lower.endswith('.7z'):
            import py7zr
            with py7zr.SevenZipFile(path, 'r') as sz:
                names = sz.getnames()
                metadata = {}
                try:
                    metadata = {
                        getattr(item, 'filename', ''): item
                        for item in sz.list()
                        if getattr(item, 'filename', '')
                    }
                except (AttributeError, OSError, RuntimeError):
                    metadata = {}
                entries = []
                for member_name in names:
                    item = metadata.get(member_name)
                    entries.append((
                        member_name,
                        getattr(item, 'uncompressed', None) if item else None,
                        getattr(item, 'compressed', None) if item else None,
                    ))
                _preflight_archive_limits(path, dest_dir, entries, limits)
                top = (_top_level_folder(names) if strip_top_folder else None)
                total_written = 0
                with tempfile.TemporaryDirectory() as tmp:
                    for member_name in names:
                        _check_cancelled(cancel_cb)
                        try:
                            src_file = _safe_member_destination(
                                tmp, member_name,
                                flatten=False,
                                strip_top_folder=False,
                                validation_root=tmp,
                            )
                            dst = _safe_member_destination(
                                dest_dir, member_name, top,
                                flatten=flatten,
                                strip_top_folder=strip_top_folder,
                            )
                        except UnsafeArchiveEntryError:
                            _log(f"  Skipped (path traversal): {member_name}")
                            continue
                        sz.extract(path=tmp, targets=[member_name])
                        _check_cancelled(cancel_cb)
                        if not os.path.isfile(src_file):
                            continue
                        actual_size = os.path.getsize(src_file)
                        if (limits.max_entry_bytes is not None
                                and actual_size > limits.max_entry_bytes):
                            raise ArchiveLimitError(
                                'entry_size',
                                f"{member_name!r} exceeded {limits.max_entry_bytes} bytes",
                            )
                        if (limits.max_total_bytes is not None
                                and total_written + actual_size > limits.max_total_bytes):
                            raise ArchiveLimitError(
                                'total_size',
                                f"extraction exceeded {limits.max_total_bytes} bytes",
                            )
                        if os.path.lexists(dst):
                            raise ArchiveExtractionError(
                                'destination_exists', f"output already exists: {dst}")
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        created_files.append(dst)
                        shutil.move(src_file, dst)
                        total_written += actual_size
                        extracted.append(dst)
                        _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

        elif name_lower.endswith('.rar'):
            import rarfile
            with rarfile.RarFile(path) as rf:
                members = rf.infolist()
                _preflight_archive_limits(
                    path,
                    dest_dir,
                    [(
                        m.filename,
                        getattr(m, 'file_size', None),
                        getattr(m, 'compress_size', None),
                    ) for m in members],
                    limits,
                )
                top = (_top_level_folder([m.filename for m in members])
                       if strip_top_folder else None)
                total_written = 0
                for member in members:
                    _check_cancelled(cancel_cb)
                    if member.is_dir():
                        continue
                    try:
                        dst = _safe_member_destination(
                            dest_dir, member.filename, top,
                            flatten=flatten,
                            strip_top_folder=strip_top_folder,
                        )
                    except UnsafeArchiveEntryError:
                        _log(f"  Skipped (path traversal): {member.filename}")
                        continue
                    if os.path.lexists(dst):
                        raise ArchiveExtractionError(
                            'destination_exists', f"output already exists: {dst}")
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    created_files.append(dst)
                    with rf.open(member) as src, open(dst, 'xb') as out:
                        total_written += _copy_stream_bounded(
                            src,
                            out,
                            name=member.filename,
                            limits=limits,
                            total_written=total_written,
                            cancel_cb=cancel_cb,
                        )
                    extracted.append(dst)
                    _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

    except ArchiveExtractionError as e:
        for created in reversed(created_files):
            try:
                os.remove(created)
            except OSError:
                pass
        if dest_was_absent:
            shutil.rmtree(dest_dir, ignore_errors=True)
        _log(f"  Extraction blocked [{e.code}]: {e.message}")
        raise
    except Exception as e:
        for created in reversed(created_files):
            try:
                os.remove(created)
            except OSError:
                pass
        if dest_was_absent:
            shutil.rmtree(dest_dir, ignore_errors=True)
        _log(f"  Extraction error: {e}")
        log.error("extract_archive failed on %s: %s", path, e)

    return extracted


def extract_to_temp(
    path: str,
    log_cb=None,
    *,
    limits: Optional[ArchiveLimits] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
) -> tuple:
    """
    Extract archive to a temporary directory.

    Returns: (temp_dir: str, file_list: list)
    Caller is responsible for cleanup: shutil.rmtree(temp_dir)
    """
    tmp = tempfile.mkdtemp(prefix='fo_extract_')
    try:
        files = extract_archive(
            path,
            tmp,
            log_cb=log_cb,
            limits=limits,
            cancel_cb=cancel_cb,
        )
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return tmp, files


# ── Design archive scanner ─────────────────────────────────────────────────────

def scan_archives_in_dir(root: str, recursive: bool = True) -> list:
    """
    Walk root directory and return list of dicts for all archives containing design content.

    Returns list of: {path, format, design_files, asset_files, total_uncompressed_size}
    """
    results = []
    walk = os.walk(root) if recursive else [(root, [], os.listdir(root))]
    for dirpath, dirnames, filenames in walk:
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            if is_archive(full):
                info = inspect_archive(full, max_entries=200)
                if info.get('has_design_content'):
                    results.append({
                        'path': full,
                        'format': info['format'],
                        'design_files': info['design_files'],
                        'asset_files': info['asset_files'],
                        'total_uncompressed_size': info['total_uncompressed_size'],
                    })
    return results


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_archive_display_name(path: str) -> str:
    """Suggest a display name for an archive based on its filename."""
    from fileorganizer.catalog import strip_marketplace_noise
    stem = Path(path).stem
    # Remove extension artifacts like ".tar" from ".tar.gz"
    stem = re.sub(r'\.tar$', '', stem)
    return strip_marketplace_noise(stem)


def archive_summary(path: str) -> str:
    """One-line summary of archive contents for UI display."""
    info = inspect_archive(path, max_entries=50)
    if info.get('error'):
        return f"Error: {info['error']}"
    n_design = len(info['design_files'])
    n_asset = len(info['asset_files'])
    fmt = info.get('format', '?').upper()
    size_mb = info.get('total_uncompressed_size', 0) / 1_048_576
    parts = [f"{fmt}"]
    if n_design:
        parts.append(f"{n_design} project file{'s' if n_design != 1 else ''}")
    if n_asset:
        parts.append(f"{n_asset} asset{'s' if n_asset != 1 else ''}")
    if size_mb:
        parts.append(f"{size_mb:.1f} MB uncompressed")
    return '  ·  '.join(parts) if parts else "Archive"
