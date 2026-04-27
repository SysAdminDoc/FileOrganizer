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
from pathlib import Path
from typing import Optional

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
                       '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz'}


def is_archive(path: str) -> bool:
    p = Path(path)
    name_lower = p.name.lower()
    return (p.suffix.lower() in _ARCHIVE_EXTENSIONS
            or name_lower.endswith(('.tar.gz', '.tar.bz2', '.tar.xz')))


def is_design_file(path: str) -> bool:
    return Path(path).suffix.lower() in DESIGN_EXTENSIONS


def is_core_design_file(path: str) -> bool:
    return Path(path).suffix.lower() in CORE_DESIGN_EXTENSIONS


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
                    log_cb=None) -> list:
    """
    Extract archive to dest_dir.

    Args:
      path:             Source archive path
      dest_dir:         Target directory (created if needed)
      flatten:          If True, all files go directly into dest_dir (no subfolders)
      strip_top_folder: If archive has one root folder, extract its contents directly
                        into dest_dir instead of creating dest_dir/<root>/<files>
      log_cb:           Optional callback(message: str) for progress logging

    Returns:
      List of absolute paths of extracted files (files only, not dirs)
    """
    os.makedirs(dest_dir, exist_ok=True)
    extracted = []
    name_lower = Path(path).name.lower()

    def _log(msg):
        if log_cb:
            log_cb(msg)
        else:
            log.debug(msg)

    def _dest_path(member_name: str, top_folder: Optional[str]) -> str:
        """Compute destination path for a member, applying strip/flatten rules."""
        p = Path(member_name)
        if flatten:
            return os.path.join(dest_dir, p.name)
        if strip_top_folder and top_folder:
            try:
                rel = p.relative_to(top_folder)
                return os.path.join(dest_dir, str(rel))
            except ValueError:
                pass
        return os.path.join(dest_dir, member_name)

    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, 'r') as zf:
                info = inspect_archive(path, max_entries=10)
                top = info.get('top_level_folder') if strip_top_folder else None
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    dst = _dest_path(member.filename, top)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    # Avoid path traversal
                    if not os.path.abspath(dst).startswith(os.path.abspath(dest_dir)):
                        _log(f"  Skipped (path traversal): {member.filename}")
                        continue
                    with zf.open(member) as src, open(dst, 'wb') as out:
                        shutil.copyfileobj(src, out)
                    extracted.append(dst)
                    _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

        elif name_lower.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
            with tarfile.open(path, 'r:*') as tf:
                info = inspect_archive(path, max_entries=10)
                top = info.get('top_level_folder') if strip_top_folder else None
                for member in tf.getmembers():
                    if member.isdir():
                        continue
                    dst = _dest_path(member.name, top)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if not os.path.abspath(dst).startswith(os.path.abspath(dest_dir)):
                        _log(f"  Skipped (path traversal): {member.name}")
                        continue
                    f = tf.extractfile(member)
                    if f:
                        with open(dst, 'wb') as out:
                            shutil.copyfileobj(f, out)
                        extracted.append(dst)
                        _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

        elif name_lower.endswith('.7z'):
            import py7zr
            with py7zr.SevenZipFile(path, 'r') as sz:
                info = inspect_archive(path, max_entries=10)
                top = info.get('top_level_folder') if strip_top_folder else None
                # py7zr extracts to a directory; we then move files
                with tempfile.TemporaryDirectory() as tmp:
                    sz.extractall(tmp)
                    for dirpath, _, filenames in os.walk(tmp):
                        for fname in filenames:
                            src_file = os.path.join(dirpath, fname)
                            rel = os.path.relpath(src_file, tmp)
                            dst = _dest_path(rel, top)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            if not os.path.abspath(dst).startswith(os.path.abspath(dest_dir)):
                                continue
                            shutil.move(src_file, dst)
                            extracted.append(dst)
                            _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

        elif name_lower.endswith('.rar'):
            import rarfile
            with rarfile.RarFile(path) as rf:
                info = inspect_archive(path, max_entries=10)
                top = info.get('top_level_folder') if strip_top_folder else None
                for member in rf.infolist():
                    if member.is_dir():
                        continue
                    dst = _dest_path(member.filename, top)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if not os.path.abspath(dst).startswith(os.path.abspath(dest_dir)):
                        _log(f"  Skipped (path traversal): {member.filename}")
                        continue
                    with rf.open(member) as src, open(dst, 'wb') as out:
                        shutil.copyfileobj(src, out)
                    extracted.append(dst)
                    _log(f"  Extracted: {os.path.relpath(dst, dest_dir)}")

    except Exception as e:
        _log(f"  Extraction error: {e}")
        log.error("extract_archive failed on %s: %s", path, e)

    return extracted


def extract_to_temp(path: str, log_cb=None) -> tuple:
    """
    Extract archive to a temporary directory.

    Returns: (temp_dir: str, file_list: list)
    Caller is responsible for cleanup: shutil.rmtree(temp_dir)
    """
    tmp = tempfile.mkdtemp(prefix='fo_extract_')
    files = extract_archive(path, tmp, log_cb=log_cb)
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
