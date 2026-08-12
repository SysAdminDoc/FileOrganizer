"""FileOrganizer — Background worker threads for scanning, applying, and LLM tasks."""
import os, re, json, shutil, tempfile, time, math, hashlib, base64, sys, subprocess
import hmac
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from urllib.parse import unquote, urlsplit

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRunnable, QThreadPool, QMutex, QMutexLocker, QObject
from PyQt6.QtGui import QImage

from fileorganizer.config import _APP_DATA_DIR, CONF_HIGH, CONF_MEDIUM, is_protected
from fileorganizer.path_safety import (
    source_signature, validate_move, validate_path, validate_source_signature,
)
from fileorganizer.bootstrap import (
    HAS_PILLOW, HAS_RAPIDFUZZ, HAS_PSD_TOOLS,
    HAS_CV2, HAS_FACE_RECOGNITION,
)
from fileorganizer.cache import (
    cache_lookup, cache_store, cache_clear, check_corrections, _preload_corrections,
    _close_cache_conn, _init_cache_db, save_correction, save_undo_log,
    append_csv_log, hash_file, create_backup_snapshot
)
from fileorganizer.categories import (
    get_all_categories, get_all_category_names, is_generic_aep, _score_aep,
    _CategoryIndex,
)
from fileorganizer.naming import (
    _normalize, _beautify_name, _smart_name, _ASSET_FOLDER_NAMES,
    _is_id_only_folder, _extract_name_hints,
)
from fileorganizer.classifier import (
    categorize_folder, classify_by_extensions, tiered_classify
)
from fileorganizer.metadata import (
    extract_folder_metadata, MetadataExtractor, ArchivePeeker, _extract_file_content,
)
from fileorganizer.ollama import (
    ollama_classify_folder, ollama_classify_batch, load_ollama_settings, save_ollama_settings,
    ollama_test_connection, ModelRouter, _ollama_generate,
    _llm_cache_get, _llm_cache_set,
    _EVIDENCE_CONFIDENCE_THRESHOLD, _escalate_classification,
    _find_ollama_binary, _is_ollama_server_running, _ollama_has_model,
    _ollama_pull_model_streaming, _ollama_list_models_detailed, _ollama_delete_model,
    _find_vision_model, _prepare_image_base64, _is_vision_model
)
from fileorganizer import photos as _photo_module
from fileorganizer.photos import (
    load_photo_settings, _detect_faces_full, _detect_faces_count_only,
    _reverse_geocode, _compute_blur_score, FaceDB, _convert_image_to_jpg,
    _PHOTO_SCENES,
)
from fileorganizer.adaptive_corrector import AdaptiveCorrector
_cv2 = getattr(_photo_module, '_cv2', None)
_face_recognition = getattr(_photo_module, '_face_recognition', None)
from fileorganizer.duplicates import (
    ProgressiveDuplicateDetector, ConflictResolver, _PHASH_IMAGE_EXTS,
)
from fileorganizer.files import (
    _load_pc_categories, _build_ext_map, _classify_pc_item, _classify_pc_folder,
    _ScanCache, _JUNK_PATTERNS, _JUNK_SUFFIXES, _extract_filename_date,
    _detect_mime_category,
)
from fileorganizer.engine import RuleEngine, RenameTemplateEngine
from fileorganizer.plugins import PluginManager
from fileorganizer.models import RenameItem, CategorizeItem, FileItem
from fileorganizer.xmp_sidecar import write_classification_sidecar
from fileorganizer.audit_log import audit_event, configure_audit, new_trace_id
from fileorganizer.metrics import ensure_metrics_exporter, record_files_moved


def _worker_audit_start(
    operation: str,
    message: str,
    *,
    source_path: object = "",
    count: int | None = None,
    mode: str = "gui_worker",
) -> str:
    """Start a GUI worker trace without allowing telemetry to affect work."""
    trace_id = new_trace_id()
    configure_audit(console=False)
    ensure_metrics_exporter()
    details: dict[str, object] = {"mode": mode, "status": "running"}
    if count is not None:
        details["count"] = count
    audit_event(
        operation,
        message,
        trace_id=trace_id,
        source_path=source_path,
        **details,
    )
    return trace_id


def _worker_audit_finish(
    operation: str,
    message: str,
    trace_id: str,
    *,
    source_path: object = "",
    status: str = "complete",
    **details: object,
) -> None:
    if operation == "move":
        record_files_moved(details.get("moved", 0))
    audit_event(
        operation,
        message,
        trace_id=trace_id,
        source_path=source_path,
        status=status,
        **details,
    )

# ── Safe merge (standalone for use in workers) ─────────────────────────────────
def _collision_destination(path):
    """Return the first available sibling path that preserves ``path``."""
    base, ext = os.path.splitext(path)
    number = 2
    candidate = f"{base} ({number}){ext}"
    while os.path.lexists(candidate):
        number += 1
        candidate = f"{base} ({number}){ext}"
    return candidate


def safe_merge_move(src, dst, log_cb=None, check_hashes=False, manifest=None):
    """Move a directory into an existing destination without deleting files.

    Differing destination files are preserved by suffixing the incoming file.
    When ``check_hashes`` is enabled, identical files are deduplicated by
    removing only the source copy.  ``manifest`` receives enough per-file and
    per-directory information for a guarded, selective undo.
    """
    validate_path(src)
    validate_path(dst, require_exists=False)
    if manifest is None:
        manifest = []
    elif not isinstance(manifest, list):
        raise TypeError("merge manifest must be a list")

    merged = 0
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [name for name in dirnames
                       if not os.path.islink(os.path.join(dirpath, name))]
        manifest.append({'action': 'directory', 'src': dirpath})
        rel = os.path.relpath(dirpath, src)
        dest_dir = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(dest_dir, exist_ok=True)
        for fname in filenames:
            src_file = os.path.join(dirpath, fname)
            requested_dst = os.path.join(dest_dir, fname)
            validate_path(src_file, root=src)
            validate_path(requested_dst, root=dst, require_exists=False)
            actual_dst = requested_dst
            if os.path.lexists(requested_dst):
                if check_hashes:
                    src_hash = hash_file(src_file)
                    dst_hash = hash_file(requested_dst)
                    if src_hash and dst_hash and src_hash == dst_hash:
                        destination_signature = source_signature(requested_dst)
                        manifest.append({
                            'action': 'deduplicated',
                            'src': src_file,
                            'dst': requested_dst,
                            'destination_signature': destination_signature,
                        })
                        if log_cb:
                            log_cb(f"    Skipped (identical): {os.path.relpath(src_file, src)}")
                        skipped += 1
                        os.remove(src_file)
                        continue
                actual_dst = _collision_destination(requested_dst)
                merged += 1
                if log_cb:
                    log_cb(
                        f"    Collision preserved: {os.path.relpath(src_file, src)}"
                        f" -> {os.path.basename(actual_dst)}"
                    )
            if log_cb:
                log_cb(f"    Moving: {os.path.relpath(src_file, src)}")
            shutil.move(src_file, actual_dst)
            manifest.append({
                'action': 'move',
                'src': src_file,
                'dst': actual_dst,
                'destination_signature': source_signature(actual_dst),
            })
    for dirpath, dirnames, filenames in os.walk(src, topdown=False):
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
    return merged, skipped


def restore_merge_manifest(manifest, source_root, dest_root, log_cb=None):
    """Undo a merge one guarded entry at a time.

    The manifest is mutated to retain only entries that could not be restored,
    allowing a later undo attempt to retry only the unresolved work. Existing
    destination files are never overwritten or removed.
    """
    if not isinstance(manifest, list) or not source_root or not dest_root:
        raise ValueError("merge undo requires a manifest and path boundaries")

    restored = 0
    errors = 0
    remaining = []
    for entry in reversed(manifest):
        try:
            if not isinstance(entry, dict):
                raise ValueError("merge manifest entry is not an object")
            action = entry.get('action')
            original = entry.get('src', '')
            if action == 'directory':
                validate_path(original, root=source_root, require_exists=False)
                os.makedirs(original, exist_ok=True)
                restored += 1
                continue

            current = entry.get('dst', '')
            if not original or not current:
                raise ValueError("merge manifest entry has no source/destination")
            validate_source_signature(current, entry.get('destination_signature', {}))
            validate_move(
                current,
                original,
                source_root=dest_root,
                dest_root=source_root,
            )
            os.makedirs(os.path.dirname(original), exist_ok=True)
            if action == 'move':
                shutil.move(current, original)
            elif action == 'deduplicated':
                shutil.copy2(current, original)
            else:
                raise ValueError(f"unknown merge manifest action: {action!r}")
            restored += 1
            if log_cb:
                log_cb(f"  Restored merged file: {os.path.basename(original)}")
        except Exception as exc:
            errors += 1
            remaining.append(entry)
            if log_cb:
                log_cb(f"  Merge undo error: {exc}")
    manifest[:] = list(reversed(remaining))
    return restored, errors



# ── Helpers ────────────────────────────────────────────────────────────────────
def format_size(b):
    if b >= 1_073_741_824: return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576: return f"{b/1_048_576:.1f} MB"
    if b >= 1024: return f"{b/1024:.1f} KB"
    return f"{b} B"



# ── File Operation Actions ────────────────────────────────────────────────────
# Inspired by DropIt (21 actions), File Juggler, and Czkawka.
# Each returns (success: bool, detail: str).

def action_copy(src: str, dst: str, *, overwrite: bool = False) -> tuple:
    """Copy file or folder to destination. Creates parent dirs as needed."""
    try:
        validate_move(src, dst, allow_existing_dest=overwrite)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            if os.path.exists(dst) and not overwrite:
                return (False, f"Destination exists: {dst}")
            shutil.copytree(src, dst, dirs_exist_ok=overwrite)
        else:
            if os.path.exists(dst) and not overwrite:
                return (False, f"Destination exists: {dst}")
            shutil.copy2(src, dst)
        return (True, f"Copied to {dst}")
    except Exception as e:
        return (False, str(e))


def action_delete(path: str, *, use_trash: bool = True) -> tuple:
    """Delete file or folder. Uses send2trash if available and requested."""
    try:
        validate_path(path)
        if use_trash:
            try:
                from send2trash import send2trash
                send2trash(path)
                return (True, "Sent to trash")
            except ImportError:
                pass  # fall through to permanent delete
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return (True, "Permanently deleted")
    except Exception as e:
        return (False, str(e))


def action_hardlink(src: str, dst: str) -> tuple:
    """Replace duplicate with a hard link to the original (same filesystem only).
    Saves disk space while keeping the file accessible at both paths."""
    try:
        validate_move(src, dst, allow_existing_dest=True)
        if os.path.isdir(src):
            return (False, "Cannot hardlink directories")
        # Verify same filesystem
        if os.stat(src).st_dev != os.stat(os.path.dirname(dst)).st_dev:
            return (False, "Source and destination on different filesystems")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # Remove dst first, then link
        if os.path.exists(dst):
            os.remove(dst)
        os.link(src, dst)
        return (True, f"Hardlinked to {src}")
    except Exception as e:
        return (False, str(e))


def action_symlink(src: str, dst: str) -> tuple:
    """Create a symbolic link at dst pointing to src."""
    try:
        validate_path(src)
        validate_move(src, dst, allow_existing_dest=True)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)
        os.symlink(src, dst, target_is_directory=os.path.isdir(src))
        return (True, f"Symlinked to {src}")
    except Exception as e:
        return (False, str(e))


def action_compress(paths: list, archive_path: str, *,
                    format: str = 'zip') -> tuple:
    """Compress one or more files/folders into an archive.
    Supported formats: zip, tar.gz, tar.bz2, tar.xz."""
    import zipfile, tarfile
    try:
        for path in paths:
            validate_path(path)
            validate_move(path, archive_path, allow_existing_dest=True)
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)
        if format == 'zip':
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for p in paths:
                    if os.path.isdir(p):
                        for dirpath, dirnames, filenames in os.walk(p):
                            for fname in filenames:
                                fpath = os.path.join(dirpath, fname)
                                arcname = os.path.relpath(fpath, os.path.dirname(p))
                                zf.write(fpath, arcname)
                    else:
                        zf.write(p, os.path.basename(p))
        elif format.startswith('tar'):
            mode_map = {'tar.gz': 'w:gz', 'tar.bz2': 'w:bz2', 'tar.xz': 'w:xz'}
            mode = mode_map.get(format, 'w:gz')
            with tarfile.open(archive_path, mode) as tf:
                for p in paths:
                    tf.add(p, arcname=os.path.basename(p))
        else:
            return (False, f"Unsupported format: {format}")

        total_size = os.path.getsize(archive_path)
        return (True, f"Archived ({format_size(total_size)})")
    except Exception as e:
        return (False, str(e))


# All supported actions for the rule engine
FILE_ACTIONS = {
    'move': 'Move to destination',
    'copy': 'Copy to destination',
    'delete': 'Delete (trash)',
    'delete_permanent': 'Delete permanently',
    'hardlink': 'Replace with hard link',
    'symlink': 'Replace with symbolic link',
    'compress': 'Compress to archive',
}


# ── Workers ────────────────────────────────────────────────────────────────────
def _collect_scan_folders(root: Path, scan_depth: int = 0) -> list:
    """Collect folders to process at the specified depth.
    depth=0: immediate children (default, original behavior)
    depth=1: grandchildren (subfolders within each top-level folder)
    depth=2+: deeper nesting levels
    Protected paths are automatically excluded."""
    try:
        top_dirs = sorted([f for f in root.iterdir()
                           if f.is_dir() and not is_protected(str(f))])
    except PermissionError:
        return []

    if scan_depth <= 0:
        return top_dirs

    # Recurse into deeper levels
    folders = []
    for top_dir in top_dirs:
        try:
            subs = _collect_scan_folders(top_dir, scan_depth - 1)
            folders.extend(subs)
        except (PermissionError, OSError):
            continue
    return folders


class ScanAepWorker(QThread):
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, root_dir, scan_depth=0):
        super().__init__()
        self.root_dir = root_dir
        self.scan_depth = scan_depth
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        trace_id = _worker_audit_start(
            "classify",
            "AEP folder scan started",
            source_path=self.root_dir,
            mode="aep_scan",
        )
        root = Path(self.root_dir)
        folders = _collect_scan_folders(root, self.scan_depth)
        if not folders:
            _worker_audit_finish(
                "classify", "AEP folder scan found no folders", trace_id,
                source_path=self.root_dir, status="empty",
            )
            self.log.emit("ERROR: No folders found or permission denied")
            self.finished.emit(); return

        if self.scan_depth > 0:
            self.log.emit(f"  Deep scan (depth {self.scan_depth}): processing {len(folders)} subfolders")

        total = len(folders)
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)
            self.log.emit(f"Scanning: {folder.name}")
            aep_files = []
            try:
                for aep in folder.rglob("*.aep"):
                    try:
                        aep_files.append(aep)
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                pass

            # Score each AEP and pick the best candidate for naming
            best_aep = None
            best_score = -999
            best_size = 0
            for aep in aep_files:
                aep_score, aep_size = _score_aep(aep, folder, folder.name)
                if aep_score > best_score or (aep_score == best_score and aep_size > best_size):
                    best_aep = aep
                    best_score = aep_score
                    best_size = aep_size

            self.result_ready.emit({
                'folder_name': folder.name,
                'folder_path': str(folder),
                'largest_aep': best_aep.name if best_aep else None,
                'aep_rel_path': str(best_aep.relative_to(folder)) if best_aep else None,
                'aep_size': best_size,
            })
        _worker_audit_finish(
            "classify", "AEP folder scan finished", trace_id,
            source_path=self.root_dir, count=total,
            status="cancelled" if self._cancelled else "complete",
        )
        self.finished.emit()


class ScanCategoryWorker(QThread):
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    phase = pyqtSignal(str, str)  # (phase_label, method_label)

    # Extensions that indicate real project content
    PROJECT_EXTS = {
        '.aep', '.aet', '.prproj', '.psd', '.ai', '.indd', '.idml',
        '.mogrt', '.ffx', '.atn', '.abr', '.jsx', '.jsxbin',
        '.c4d', '.blend', '.obj', '.fbx', '.stl',
        '.cube', '.3dl', '.lut', '.lrtemplate', '.xmp',
        '.ttf', '.otf', '.woff', '.woff2',
        '.mp4', '.mov', '.avi', '.wmv', '.mkv',
        '.mp3', '.wav', '.flac', '.aif', '.ogg',
        '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif', '.svg', '.eps', '.pdf',
        '.pptx', '.docx', '.xlsx',
    }

    def __init__(self, root_dir, dest_dir, scan_depth=0, use_cache=True):
        super().__init__()
        self.root_dir = root_dir
        self.dest_dir = dest_dir
        self.scan_depth = scan_depth
        self.use_cache = use_cache
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _collect_candidate_names(self, folder: Path, max_depth=4):
        """Walk into a folder to find all candidate names for categorization.
        Returns list of (name, depth, has_project_files) sorted by quality."""
        candidates = []
        # Always include the top-level folder itself
        top_has_files = any(
            f.suffix.lower() in self.PROJECT_EXTS
            for f in folder.iterdir() if f.is_file()
        ) if folder.is_dir() else False
        candidates.append((folder.name, 0, top_has_files))

        # Walk deeper
        try:
            self._walk_candidates(folder, folder, 1, max_depth, candidates)
        except (PermissionError, OSError):
            pass
        return candidates

    def _walk_candidates(self, base, current, depth, max_depth, candidates):
        """Recursively collect subfolder names as categorization candidates."""
        if depth > max_depth:
            return
        try:
            subdirs = [d for d in current.iterdir() if d.is_dir()]
        except (PermissionError, OSError):
            return

        for sub in subdirs:
            # Check if this subfolder has project files
            has_files = False
            try:
                has_files = any(
                    f.suffix.lower() in self.PROJECT_EXTS
                    for f in sub.iterdir() if f.is_file()
                )
            except (PermissionError, OSError):
                pass

            # Skip generic/junk folder names (asset folders, not project names)
            sub_lower = sub.name.lower().strip()
            # Strip parentheses for matching: "(Footage)" → "footage"
            sub_stripped = re.sub(r'^[\(\[\{]|[\)\]\}]$', '', sub_lower).strip()
            if sub_lower not in _ASSET_FOLDER_NAMES and sub_stripped not in _ASSET_FOLDER_NAMES:
                candidates.append((sub.name, depth, has_files))

            # If this is a single-subfolder wrapper, always go deeper
            # Also go deeper if no project files found yet at this level
            self._walk_candidates(base, sub, depth + 1, max_depth, candidates)

    def _best_categorization(self, folder: Path):
        """Find the best category using the tiered classification pipeline.
        Tries extension mapping and metadata on the actual folder, then
        keyword/fuzzy matching on all candidate subfolder names.
        Returns (category, confidence, cleaned_name, source_name, depth, method, detail, topic)."""

        # First: try tiered classification on the top-level folder itself
        # This runs extension mapping + metadata extraction on the actual folder contents
        top_result = tiered_classify(folder.name, str(folder))

        if top_result['category'] and top_result['confidence'] >= 70:
            return (top_result['category'], top_result['confidence'],
                    top_result['cleaned_name'], folder.name, 0,
                    top_result['method'], top_result['detail'],
                    top_result.get('topic'))

        # Cache the top-level result to avoid re-running I/O for depth-0
        best = None  # (cat, conf, cleaned, source_name, depth, method, detail, topic)

        # If top_result had any match (even low confidence), include it as a candidate
        if top_result['category']:
            best = (top_result['category'], top_result['confidence'],
                    top_result['cleaned_name'], folder.name, 0,
                    top_result['method'], top_result['detail'],
                    top_result.get('topic'))

        # Second: collect candidate subfolder names and try keyword matching on each
        candidates = self._collect_candidate_names(folder)

        for name, depth, has_files in candidates:
            if depth == 0:
                continue  # Already handled by top_result above

            # For deeper candidates, just use keyword + fuzzy matching (no redundant I/O)
            result = tiered_classify(name, None)

            if not result['category']:
                continue

            # Score bonus for having project files nearby
            effective_score = result['confidence']
            if has_files:
                effective_score += 5
            # Slight penalty for deeper folders (prefer top-level matches)
            effective_score -= depth * 2

            if best is None or effective_score > best[1]:
                best = (result['category'], result['confidence'],
                        result['cleaned_name'], name, depth,
                        result['method'], result['detail'],
                        result.get('topic'))

        if best:
            return best
        return (None, 0, folder.name, folder.name, 0, '', '', None)

    def run(self):
        trace_id = _worker_audit_start(
            "classify",
            "Category scan started",
            source_path=self.root_dir,
            mode="category_scan",
        )
        root = Path(self.root_dir)
        folders = _collect_scan_folders(root, self.scan_depth)
        if not folders:
            _worker_audit_finish(
                "classify", "Category scan found no folders", trace_id,
                source_path=self.root_dir, status="empty",
            )
            self.log.emit("ERROR: No folders found or permission denied")
            self.finished.emit(); return

        # ── Pre-load caches for scan performance ──
        _preload_corrections()
        adaptive_corrector = AdaptiveCorrector()
        _CategoryIndex.get()  # Build keyword index once

        # ── Check Ollama availability for escalation ──
        _ollama_available = _is_ollama_server_running()
        if _ollama_available:
            self.log.emit("  Escalation: Ollama available -- low-confidence items will auto-escalate")

        # Log engine capabilities
        caps = ["keyword"]
        if HAS_RAPIDFUZZ: caps.append("fuzzy")
        if HAS_PSD_TOOLS: caps.append("psd-metadata")
        caps.extend(["extension-map", "prproj-metadata", "content-analysis"])
        self.log.emit(f"  Engine: tiered v5.3 [{', '.join(caps)}, context-inference, cache, corrections, smart-naming]")
        if self.scan_depth > 0:
            self.log.emit(f"  Deep scan (depth {self.scan_depth}): processing {len(folders)} subfolders")

        total = len(folders)
        self.phase.emit("Categorizing", f"Classifying {total:,} folders with rule engine…")
        t0 = time.time(); cached_hits = 0; correction_hits = 0
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)

            # Check corrections first (learned from user overrides)
            adaptive_match = adaptive_corrector.apply_correction(str(folder))
            corr_cat = (
                adaptive_match[0] if adaptive_match
                else check_corrections(folder.name)
            )
            if corr_cat:
                correction_hits += 1
                self.log.emit(f"  {folder.name}")
                self.log.emit(f"    -->  {corr_cat}  (100%) [learned]")
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': corr_cat, 'confidence': 100,
                    'cleaned_name': folder.name, 'source_depth': 0,
                    'method': 'learned',
                    'detail': (
                        'From exact folder fingerprint correction'
                        if adaptive_match else 'From user correction history'
                    ),
                    'topic': None,
                })
                continue

            # Check cache
            if self.use_cache:
                cached = cache_lookup(folder.name, str(folder))
                if cached and cached.get('category'):
                    cached_hits += 1
                    self.log.emit(f"  {folder.name}")
                    self.log.emit(f"    -->  {cached['category']}  ({cached['confidence']:.0f}%) [cached]")
                    self.result_ready.emit({
                        'folder_name': folder.name, 'folder_path': str(folder),
                        'category': cached['category'], 'confidence': cached['confidence'],
                        'cleaned_name': cached.get('cleaned_name', folder.name), 'source_depth': 0,
                        'method': f"cached:{cached.get('method', '')}", 'detail': cached.get('detail', ''),
                        'topic': cached.get('topic'),
                    })
                    continue

            cat, conf, cleaned, source_name, depth, method, detail, topic = self._best_categorization(folder)

            # ── Escalation: auto-upgrade low-confidence items via evidence + LLM ──
            if _ollama_available and (conf or 0) < _EVIDENCE_CONFIDENCE_THRESHOLD and (conf or 0) > 0:
                esc_result = _escalate_classification(
                    folder.name, str(folder),
                    {'category': cat, 'confidence': conf, 'cleaned_name': cleaned,
                     'method': method, 'detail': detail, 'topic': topic},
                    url=load_ollama_settings()['url'], log_cb=self.log.emit)
                if esc_result.get('confidence', 0) > (conf or 0):
                    cat, conf = esc_result['category'], esc_result['confidence']
                    cleaned = esc_result.get('cleaned_name', cleaned)
                    method = esc_result.get('method', method)
                    detail = esc_result.get('detail', detail)

            # ── Smart ID-only enrichment ──────────────────────────────────────
            # If the folder name is just an ID and classification still failed or
            # is low-confidence, scan inside for project files to get a real name.
            if _is_id_only_folder(folder.name):
                hints = _extract_name_hints(str(folder))
                if hints:
                    best_hint_name, hint_source, _ = hints[0]
                    # Re-classify using the project file name
                    hint_result = tiered_classify(best_hint_name, str(folder))
                    if hint_result['category'] and hint_result['confidence'] >= (conf or 0):
                        if conf is None or hint_result['confidence'] > conf:
                            self.log.emit(f"  {folder.name}  [ID-only → scanned inside → \"{best_hint_name}\" from {hint_source}]")
                            cat = hint_result['category']
                            conf = hint_result['confidence']
                            cleaned = hint_result['cleaned_name'] or _beautify_name(best_hint_name)
                            method = f"id_enriched:{hint_result['method']}"
                            detail = f"Name from {hint_source}: {best_hint_name}"

            # Log what happened
            if depth > 0:
                self.log.emit(f"  {folder.name}")
                self.log.emit(f"    Found via subfolder: \"{source_name}\" (depth {depth})")
            elif cleaned != folder.name:
                self.log.emit(f"  {folder.name}  (detected: \"{cleaned}\")")
            else:
                self.log.emit(f"  {folder.name}")

            if cat:
                method_tag = f" [{method}]" if method else ""
                topic_tag = f" (topic: {topic})" if topic else ""
                self.log.emit(f"    -->  {cat}{topic_tag}  ({conf:.0f}%){method_tag}")
            else:
                self.log.emit(f"    -->  [no match]")

            result_dict = {
                'folder_name': folder.name,
                'folder_path': str(folder),
                'category': cat,
                'confidence': conf,
                'cleaned_name': cleaned if depth == 0 else f"{cleaned} (via: {source_name})",
                'source_depth': depth,
                'method': method,
                'detail': detail,
                'topic': topic,
            }
            self.result_ready.emit(result_dict)
            # Store in cache for future runs
            if cat and self.use_cache:
                cache_store(folder.name, str(folder), result_dict)

        elapsed = time.time() - t0
        if cached_hits: self.log.emit(f"  Cache hits: {cached_hits}")
        if correction_hits: self.log.emit(f"  Learned corrections applied: {correction_hits}")
        if elapsed > 1: self.log.emit(f"  Scan time: {elapsed:.1f}s ({elapsed/max(total,1)*1000:.0f}ms/folder)")
        _close_cache_conn()  # Release persistent DB connection
        _worker_audit_finish(
            "classify", "Category scan finished", trace_id,
            source_path=self.root_dir, count=total,
            status="cancelled" if self._cancelled else "complete",
        )
        self.finished.emit()



# ── LLM Classification Worker ─────────────────────────────────────────────────
class ScanLLMWorker(QThread):
    """Scans folders using Ollama LLM for classification and renaming.
    Processes every folder through the LLM for maximum accuracy."""
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    phase = pyqtSignal(str, str)  # (phase_label, method_label)

    def __init__(self, root_dir, dest_dir, scan_depth=0, use_cache=True):
        super().__init__()
        self.root_dir = root_dir
        self.dest_dir = dest_dir
        self.scan_depth = scan_depth
        self.use_cache = use_cache
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        trace_id = _worker_audit_start(
            "classify",
            "LLM category scan started",
            source_path=self.root_dir,
            mode="llm_scan",
        )
        root = Path(self.root_dir)
        settings = load_ollama_settings()
        folders = _collect_scan_folders(root, self.scan_depth)
        if not folders:
            _worker_audit_finish(
                "classify", "LLM category scan found no folders", trace_id,
                source_path=self.root_dir, status="empty",
            )
            self.log.emit("ERROR: No folders found or permission denied")
            self.finished.emit(); return

        # ── Pre-load caches for scan performance ──
        _preload_corrections()
        adaptive_corrector = AdaptiveCorrector()
        _CategoryIndex.get()

        # Verify Ollama connection first
        ok, msg, _ = ollama_test_connection(settings['url'], settings['model'])
        if not ok:
            self.log.emit(f"ERROR: {msg}")
            self.log.emit("Falling back to rule-based classification...")
            # Fall back to rule-based scanning
            self._fallback_scan(folders)
            _worker_audit_finish(
                "classify", "LLM category scan finished with rule fallback", trace_id,
                source_path=self.root_dir, status="fallback", count=len(folders),
            )
            return

        self.log.emit(f"  Engine: LLM via Ollama [{settings['model']}]")
        self.log.emit(f"  Processing {len(folders)} folders through LLM (batch mode)...")
        total = len(folders)
        self.phase.emit("Cache Sweep", f"Checking cache & corrections for {total:,} folders…")
        if self.scan_depth > 0:
            self.log.emit(f"  Deep scan (depth {self.scan_depth}): scanning subfolders")

        llm_ok = 0; llm_fail = 0
        BATCH_SIZE = 8  # folders per Ollama request

        t0 = time.time(); cached_hits = 0; correction_hits = 0; name_cache_hits = 0

        # Separate folders needing LLM from those already handled
        pending = []
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)

            # Check corrections first
            adaptive_match = adaptive_corrector.apply_correction(str(folder))
            corr_cat = (
                adaptive_match[0] if adaptive_match
                else check_corrections(folder.name)
            )
            if corr_cat:
                correction_hits += 1
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': corr_cat, 'confidence': 100,
                    'cleaned_name': folder.name, 'source_depth': 0,
                    'method': 'learned',
                    'detail': (
                        'From exact folder fingerprint correction'
                        if adaptive_match else 'From correction history'
                    ),
                    'topic': None, 'llm_name': None,
                })
                continue

            # Check fingerprint cache (SQLite)
            if self.use_cache:
                cached = cache_lookup(folder.name, str(folder))
                if cached and cached.get('category'):
                    cached_hits += 1
                    self.result_ready.emit({
                        'folder_name': folder.name, 'folder_path': str(folder),
                        'category': cached['category'], 'confidence': cached['confidence'],
                        'cleaned_name': cached.get('cleaned_name', folder.name), 'source_depth': 0,
                        'method': f"cached:{cached.get('method', '')}", 'detail': cached.get('detail', ''),
                        'topic': cached.get('topic'), 'llm_name': cached.get('cleaned_name'),
                        'alternatives': cached.get('alternatives', []),
                    })
                    continue

            # Check LLM name cache (in-memory, folder name key)
            name_cached = _llm_cache_get(folder.name)
            if name_cached and name_cached.get('category'):
                name_cache_hits += 1
                clean_name = name_cached.get('name', folder.name)
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': name_cached['category'],
                    'confidence': name_cached['confidence'],
                    'cleaned_name': clean_name, 'source_depth': 0,
                    'method': 'llm_name_cache', 'detail': name_cached.get('detail', ''),
                    'topic': None, 'llm_name': clean_name,
                    'alternatives': name_cached.get('alternatives', []),
                })
                continue

            pending.append(folder)

        # Process pending folders in batches
        def _emit_llm_result(folder, llm_result):
            nonlocal llm_ok, llm_fail
            if llm_result.get('category'):
                llm_ok += 1
                clean_name = llm_result.get('name', folder.name)
                _llm_cache_set(folder.name, llm_result)
                self.log.emit(f"  {folder.name}")
                if clean_name != folder.name:
                    self.log.emit(f"    LLM renamed: \"{clean_name}\"")
                self.log.emit(f"    -->  {llm_result['category']}  ({llm_result['confidence']}%) [llm]")
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': llm_result['category'], 'confidence': llm_result['confidence'],
                    'cleaned_name': clean_name, 'source_depth': 0,
                    'method': llm_result.get('method', 'llm'),
                    'detail': llm_result.get('detail', ''),
                    'topic': None, 'llm_name': clean_name,
                    'alternatives': llm_result.get('alternatives', []),
                })
            else:
                llm_fail += 1
                self.log.emit(f"  {folder.name}")
                self.log.emit(f"    LLM failed ({llm_result.get('detail', 'unknown')}), using rule-based...")
                rule_result = tiered_classify(folder.name, str(folder))
                cat = rule_result['category']
                if cat:
                    self.log.emit(f"    -->  {cat}  ({rule_result['confidence']:.0f}%) [{rule_result['method']}] (fallback)")
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': cat, 'confidence': rule_result['confidence'],
                    'cleaned_name': rule_result['cleaned_name'], 'source_depth': 0,
                    'method': rule_result['method'] or 'none',
                    'detail': rule_result['detail'], 'topic': rule_result.get('topic'),
                    'llm_name': None,
                })

        # ── Phase 2: LLM classify pending folders ────────────────────────────
        # Reset the progress bar for this new phase so it doesn't sit stuck at 100%
        pending_total = len(pending)
        if pending_total > 0:
            self.progress.emit(0, pending_total)  # reset bar to 0
        self.phase.emit("AI Classify", f"Classifying {pending_total:,} folders via Ollama [{settings['model']}]…")
        self.log.emit(f"  Classifying {pending_total} folders via LLM…")

        BATCH_SIZE = settings.get('batch_size', 3)  # per-model default from catalog
        consecutive_llm_failures = 0
        MAX_CONSECUTIVE_FAILURES = 5  # switch to rule-based after this many in a row

        for batch_start in range(0, len(pending), BATCH_SIZE):
            if self._cancelled:
                break

            # If LLM keeps failing, stop wasting time and use rule-based for the rest
            if consecutive_llm_failures >= MAX_CONSECUTIVE_FAILURES:
                self.log.emit(f"  {consecutive_llm_failures} consecutive LLM failures — switching to rule-based for remaining folders")
                remaining = pending[batch_start:]
                for folder in remaining:
                    if self._cancelled:
                        break
                    rule_result = tiered_classify(folder.name, str(folder))
                    cat = rule_result['category']
                    self.result_ready.emit({
                        'folder_name': folder.name, 'folder_path': str(folder),
                        'category': cat, 'confidence': rule_result['confidence'],
                        'cleaned_name': rule_result['cleaned_name'], 'source_depth': 0,
                        'method': rule_result['method'] or 'none',
                        'detail': rule_result['detail'], 'topic': rule_result.get('topic'),
                        'llm_name': None,
                    })
                    llm_fail += 1
                self.progress.emit(pending_total, pending_total)
                break

            batch = pending[batch_start:batch_start + BATCH_SIZE]
            # Emit progress: how many folders done so far in this LLM phase
            llm_done = batch_start + len(batch)
            self.progress.emit(llm_done, pending_total)

            if len(batch) == 1:
                # Single folder — use single classify (better prompt quality)
                folder = batch[0]
                llm_result = ollama_classify_folder(
                    folder.name, str(folder),
                    url=settings['url'], model=settings['model'],
                    log_cb=self.log.emit)
                _emit_llm_result(folder, llm_result)
                if llm_result.get('category'):
                    consecutive_llm_failures = 0
                else:
                    consecutive_llm_failures += 1
            else:
                # Multi-folder batch
                batch_input = []
                for folder in batch:
                    context_lines = [f"Folder name: \"{folder.name}\""]
                    if folder.is_dir():
                        try:
                            files = [e.name for e in os.scandir(str(folder)) if e.is_file()][:20]
                            if files:
                                context_lines.append(f"Files: {', '.join(files)}")
                        except (PermissionError, OSError):
                            pass
                    batch_input.append({
                        'folder_name': folder.name,
                        'folder_path': str(folder),
                        'context': '\n'.join(context_lines),
                    })

                batch_results = ollama_classify_batch(
                    batch_input, url=settings['url'], model=settings['model'])

                # If the whole batch failed (all empty_response), retry each folder individually
                all_failed = all(not r.get('category') for r in batch_results)
                if all_failed:
                    consecutive_llm_failures += 1
                    self.log.emit(f"  Batch failed — retrying {len(batch)} folders individually...")
                    for folder in batch:
                        if self._cancelled:
                            break
                        llm_result = ollama_classify_folder(
                            folder.name, str(folder),
                            url=settings['url'], model=settings['model'],
                            log_cb=self.log.emit)
                        _emit_llm_result(folder, llm_result)
                        if llm_result.get('category'):
                            consecutive_llm_failures = 0
                        else:
                            consecutive_llm_failures += 1
                else:
                    consecutive_llm_failures = 0
                    for folder, llm_result in zip(batch, batch_results):
                        if self._cancelled:
                            break
                        _emit_llm_result(folder, llm_result)

        elapsed = time.time() - t0
        self.log.emit(f"\n  LLM results: {llm_ok} classified, {llm_fail} fell back to rules")
        if cached_hits: self.log.emit(f"  Fingerprint cache hits: {cached_hits}")
        if name_cache_hits: self.log.emit(f"  Name cache hits: {name_cache_hits}")
        if correction_hits: self.log.emit(f"  Learned corrections: {correction_hits}")
        if elapsed > 1: self.log.emit(f"  Scan time: {elapsed:.1f}s")
        _close_cache_conn()
        _worker_audit_finish(
            "classify", "LLM category scan finished", trace_id,
            source_path=self.root_dir, count=total,
            status="cancelled" if self._cancelled else "complete",
        )
        self.finished.emit()

    def _fallback_scan(self, folders):
        """Full rule-based fallback if Ollama is unreachable."""
        total = len(folders)
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)
            top_result = tiered_classify(folder.name, str(folder))
            cat = top_result['category']
            if cat:
                self.log.emit(f"  {folder.name}  -->  {cat}  ({top_result['confidence']:.0f}%)")
            self.result_ready.emit({
                'folder_name': folder.name,
                'folder_path': str(folder),
                'category': cat,
                'confidence': top_result['confidence'],
                'cleaned_name': top_result['cleaned_name'],
                'source_depth': 0,
                'method': top_result['method'],
                'detail': top_result['detail'],
                'topic': top_result.get('topic'),
                'llm_name': None,
            })
        _close_cache_conn()
        self.finished.emit()



# ── Ollama Auto-Setup Worker ──────────────────────────────────────────────────
class OllamaSetupWorker(QThread):
    """Background worker that checks a user-installed Ollama setup.

    Installation and model downloads are intentionally explicit actions in the
    settings/model-manager UI. Startup may start an already installed local
    server, but it never downloads or executes an installer or model.
    """
    log = pyqtSignal(str)
    status = pyqtSignal(str)  # short status for UI label
    finished = pyqtSignal(bool)  # True = ready, False = setup failed

    def __init__(self, model: str = None, url: str = None):
        super().__init__()
        s = load_ollama_settings()
        self.model = model or s['model']
        self.url = url or s['url']

    def run(self):
        import time
        try:
            self._setup()
        except Exception as e:
            self.log.emit(f"  Ollama setup error: {e}")
            self.status.emit("LLM: setup failed")
            self.finished.emit(False)

    def _setup(self):
        import time

        # ── Step 1: Check if Ollama binary exists ──
        binary = _find_ollama_binary()
        if binary:
            self.log.emit(f"  Ollama found: {binary}")
        else:
            self.log.emit(
                "  Ollama not found. Install it from https://ollama.com, "
                "then restart FileOrganizer."
            )
            self.status.emit("LLM: install Ollama manually")
            self.finished.emit(False)
            return

        # ── Step 2: Ensure Ollama server is running ──
        if _is_ollama_server_running(self.url):
            self.log.emit("  Ollama server is running")
        else:
            self.log.emit("  Starting Ollama server...")
            self.status.emit("LLM: starting server...")
            self._start_server(binary)
            # Wait for server to come up (up to 15 seconds)
            for i in range(30):
                time.sleep(0.5)
                if _is_ollama_server_running(self.url):
                    break
            if _is_ollama_server_running(self.url):
                self.log.emit("  Ollama server started")
            else:
                self.log.emit("  WARNING: Ollama server did not start within 15s")
                self.log.emit("  You may need to start it manually: ollama serve")
                self.status.emit("LLM: server not responding")
                self.finished.emit(False)
                return

        # ── Step 3: Check if model is pulled ──
        if _ollama_has_model(self.model, self.url):
            self.log.emit(f"  Model ready: {self.model}")
            self.status.emit(f"LLM: {self.model}")
            self.finished.emit(True)
            return

        # ── Step 4: Tell the user how to acquire a missing model ──
        self.log.emit(
            f"  Model '{self.model}' is not installed. Open Settings > "
            "Ollama LLM and choose Pull Model or Model Manager."
        )
        self.status.emit(f"LLM: pull {self.model} in Settings")
        self.finished.emit(False)

    def _start_server(self, binary: str):
        """Start Ollama server in background."""
        try:
            if sys.platform == 'win32':
                # On Windows, 'ollama serve' or just launching ollama starts the server
                subprocess.Popen(
                    [binary, 'serve'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
            else:
                subprocess.Popen(
                    [binary, 'serve'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
        except Exception as e:
            self.log.emit(f"  Failed to start server: {e}")

# ── Apply Workers ──────────────────────────────────────────────────────────────
class ApplyAepWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    item_done = pyqtSignal(int, str)
    finished = pyqtSignal(int, int, list)  # ok, err, undo_ops

    def __init__(self, work_items, check_hashes=False, dry_run=False):
        super().__init__()
        self.work_items = work_items
        self.check_hashes = check_hashes
        self.dry_run = dry_run
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def run(self):
        ok = err = 0; undo_ops = []
        total = len(self.work_items)
        trace_id = _worker_audit_start(
            "move", "AEP apply started", mode="aep_apply", count=total,
        )
        ts = datetime.now().isoformat()
        for idx, (ri, it) in enumerate(self.work_items):
            if self._cancelled:
                self.log.emit(f"  Apply cancelled at {idx}/{total}"); break
            self.progress.emit(idx + 1, total)
            if is_protected(it.full_current_path):
                self.log.emit(f"  \u26D4 Skipped (protected): {it.current_name}")
                self.item_done.emit(ri, "Protected"); continue
            label = "[DRY RUN] " if self.dry_run else ""
            self.log.emit(f"  {label}[{idx+1}/{total}] {it.current_name}  ->  {it.new_name}")
            merge_manifest = []
            try:
                if not self.dry_run:
                    validate_move(
                        it.full_current_path,
                        it.full_new_path,
                        source_root=os.path.dirname(it.full_current_path),
                        dest_root=os.path.dirname(it.full_current_path),
                        allow_existing_dest=os.path.exists(it.full_new_path),
                    )
                    d = it.full_new_path
                    if os.path.exists(d):
                        merged, skipped = safe_merge_move(
                            it.full_current_path, d,
                            log_cb=self.log.emit, check_hashes=self.check_hashes,
                            manifest=merge_manifest,
                        )
                        self.log.emit(
                            f"  Merged ({merged} collisions preserved, "
                            f"{skipped} identical skipped)"
                        )
                    else:
                        os.rename(it.full_current_path, d)
                ok += 1
                undo_op = {'type': 'rename', 'src': it.full_new_path, 'dst': it.full_current_path,
                    'timestamp': ts, 'category': '', 'confidence': '', 'status': 'Done',
                    'source_root': os.path.dirname(it.full_current_path),
                    'dest_root': os.path.dirname(it.full_current_path)}
                if merge_manifest:
                    undo_op['merge_manifest'] = merge_manifest
                undo_ops.append(undo_op)
                self.log.emit(f"  \u2705 Done")
                self.item_done.emit(ri, "Done")
            except Exception as e:
                err += 1
                self.log.emit(f"  \u274C Error: {e}")
                # Attempt atomic rollback
                if not self.dry_run and merge_manifest:
                    restore_merge_manifest(
                        merge_manifest,
                        os.path.dirname(it.full_current_path),
                        os.path.dirname(it.full_new_path),
                        log_cb=self.log.emit,
                    )
                elif not self.dry_run and os.path.exists(it.full_new_path) and not os.path.exists(it.full_current_path):
                    try:
                        os.rename(it.full_new_path, it.full_current_path)
                        self.log.emit(f"  Rolled back to original location")
                    except Exception:
                        pass
                self.item_done.emit(ri, "Error")
        _worker_audit_finish(
            "move", "AEP apply finished", trace_id,
            status="cancelled" if self._cancelled else "complete",
            moved=ok, errors=err,
        )
        self.finished.emit(ok, err, undo_ops)


class ApplyCatWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    item_done = pyqtSignal(int, str)
    finished = pyqtSignal(int, int, list)  # ok, err, undo_ops

    def __init__(self, work_items, check_hashes=False, dry_run=False):
        super().__init__()
        self.work_items = work_items
        self.check_hashes = check_hashes
        self.dry_run = dry_run
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def run(self):
        from fileorganizer.move_journal import plan_run, mark_done, clear_run
        import uuid

        ok = err = 0; undo_ops = []
        total = len(self.work_items)
        trace_id = _worker_audit_start(
            "move", "Category apply started", mode="category_apply", count=total,
        )
        ts = datetime.now().isoformat()

        # Phase 1: write plan to journal before touching disk
        run_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        if not self.dry_run:
            plan_run(run_id, self.work_items)

        # Phase 2: execute
        for idx, (ri, it) in enumerate(self.work_items):
            if self._cancelled:
                self.log.emit(f"  Apply cancelled at {idx}/{total}"); break
            self.progress.emit(idx + 1, total)
            if is_protected(it.full_source_path):
                self.log.emit(f"  \u26D4 Skipped (protected): {it.folder_name}")
                self.item_done.emit(ri, "Protected")
                if not self.dry_run:
                    mark_done(run_id, ri, 'skipped')
                continue
            label = "[DRY RUN] " if self.dry_run else ""
            self.log.emit(f"  {label}[{idx+1}/{total}] {it.folder_name}  ->  {it.category}/")
            merge_manifest = []
            try:
                if not self.dry_run:
                    d = it.full_dest_path
                    validate_move(
                        it.full_source_path,
                        d,
                        source_root=getattr(it, 'source_root', '') or os.path.dirname(it.full_source_path),
                        dest_root=getattr(it, 'dest_root', ''),
                        allow_existing_dest=os.path.exists(d),
                    )
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    if os.path.exists(d):
                        merged, skipped = safe_merge_move(
                            it.full_source_path, d,
                            log_cb=self.log.emit, check_hashes=self.check_hashes,
                            manifest=merge_manifest,
                        )
                        self.log.emit(
                            f"  Merged ({merged} collisions preserved, "
                            f"{skipped} identical skipped)"
                        )
                    else:
                        shutil.move(it.full_source_path, d)
                ok += 1
                destination_signature = {}
                if not self.dry_run and os.path.lexists(it.full_dest_path):
                    try:
                        destination_signature = source_signature(it.full_dest_path)
                    except OSError:
                        destination_signature = {}
                undo_op = {'type': 'move', 'src': it.full_dest_path, 'dst': it.full_source_path,
                    'timestamp': ts, 'category': it.category, 'confidence': f'{it.confidence:.0f}',
                    'status': 'Done',
                    'source_root': getattr(it, 'source_root', '') or os.path.dirname(it.full_source_path),
                    'dest_root': getattr(it, 'dest_root', ''),
                    'destination_signature': destination_signature}
                if merge_manifest:
                    undo_op['merge_manifest'] = merge_manifest
                undo_ops.append(undo_op)
                self.log.emit(f"  \u2705 Done")
                self.item_done.emit(ri, "Done")
                if not self.dry_run:
                    mark_done(
                        run_id,
                        ri,
                        'done',
                        destination_signature=destination_signature,
                        merge_manifest=merge_manifest,
                    )
                    cache_store(it.folder_name, it.full_source_path,
                        {'category': it.category, 'confidence': it.confidence,
                         'cleaned_name': it.cleaned_name, 'method': it.method,
                         'detail': it.detail, 'topic': it.topic})
            except Exception as e:
                err += 1
                self.log.emit(f"  \u274C Error: {e}")
                if not self.dry_run:
                    mark_done(run_id, ri, 'error')
                    if merge_manifest:
                        restore_merge_manifest(
                            merge_manifest,
                            getattr(it, 'source_root', '') or os.path.dirname(it.full_source_path),
                            getattr(it, 'dest_root', ''),
                            log_cb=self.log.emit,
                        )
                    elif os.path.exists(it.full_dest_path) and not os.path.exists(it.full_source_path):
                        try:
                            shutil.move(it.full_dest_path, it.full_source_path)
                            self.log.emit(f"  Rolled back to original location")
                        except Exception:
                            pass
                self.item_done.emit(ri, "Error")

        # Remove incomplete rows on clean exit while retaining completed rows
        # for the history visualizer and guarded undo.
        if not self.dry_run:
            clear_run(run_id)

        # Notify Windows Explorer/Search of moved files
        if not self.dry_run and undo_ops:
            try:
                from fileorganizer.shell_notify import notify_shell_moves
                moves = [(op['dst'], op['src']) for op in undo_ops if op.get('status') == 'Done']
                notify_shell_moves(moves)
            except Exception:
                pass

        _worker_audit_finish(
            "move", "Category apply finished", trace_id,
            status="cancelled" if self._cancelled else "complete",
            moved=ok, errors=err,
        )
        self.finished.emit(ok, err, undo_ops)


class ResumeApplyWorker(QThread):
    """
    Execute pending moves from the two-phase commit journal after a crash.
    Does not sync back to GUI table rows (the table is fresh/empty after restart).
    """
    log      = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(int, int)   # ok, err

    def __init__(self, run_id: str, pending_moves: list, check_hashes: bool = False):
        super().__init__()
        self._run_id       = run_id
        self._moves        = pending_moves   # list of dicts from get_pending_moves()
        self._check_hashes = check_hashes
        self._cancelled    = False

    def cancel(self): self._cancelled = True

    def run(self):
        from fileorganizer.move_journal import mark_done, clear_run
        ok = err = 0
        total = len(self._moves)
        trace_id = _worker_audit_start(
            "move", "Resume apply started", source_path=self._run_id,
            mode="resume_apply", count=total,
        )
        for idx, mv in enumerate(self._moves):
            if self._cancelled:
                self.log.emit(f"  Resume cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)
            src  = mv['src']
            dst  = mv['dst']
            name = mv['folder_name']
            source_root = mv.get('source_root', '')
            dest_root = mv.get('dest_root', '')
            merge_manifest = []
            self.log.emit(f"  [{idx+1}/{total}] Resume: {name}  ->  {mv['category']}/")
            try:
                if not os.path.exists(src):
                    # Already moved in a prior attempt that didn't update DB
                    if os.path.exists(dst):
                        validate_move(
                            src,
                            dst,
                            source_root=source_root,
                            dest_root=dest_root,
                            allow_existing_dest=True,
                            require_source=False,
                        )
                        mark_done(
                            self._run_id,
                            mv['ri'],
                            'done',
                            destination_signature=source_signature(dst),
                            merge_manifest=merge_manifest,
                        )
                        ok += 1
                        self.log.emit(f"  Already at destination — marked done")
                        continue
                    else:
                        raise FileNotFoundError(f"Source gone and dest missing: {src}")
                validate_source_signature(src, mv.get('source_signature', {}))
                validate_move(
                    src,
                    dst,
                    source_root=source_root,
                    dest_root=dest_root,
                    allow_existing_dest=os.path.exists(dst),
                )
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    merged, skipped = safe_merge_move(
                        src, dst,
                        log_cb=self.log.emit, check_hashes=self._check_hashes,
                        manifest=merge_manifest,
                    )
                    self.log.emit(
                        f"  Merged ({merged} collisions preserved, "
                        f"{skipped} identical skipped)"
                    )
                else:
                    shutil.move(src, dst)
                mark_done(
                    self._run_id,
                    mv['ri'],
                    'done',
                    destination_signature=source_signature(dst),
                    merge_manifest=merge_manifest,
                )
                ok += 1
                self.log.emit(f"  \u2705 Done")
            except Exception as e:
                err += 1
                mark_done(self._run_id, mv['ri'], 'error')
                self.log.emit(f"  \u274C Error: {e}")
                if merge_manifest:
                    restore_merge_manifest(
                        merge_manifest, source_root, dest_root, log_cb=self.log.emit
                    )

        if not self._cancelled:
            clear_run(self._run_id)
        _worker_audit_finish(
            "move", "Resume apply finished", trace_id,
            source_path=self._run_id,
            status="cancelled" if self._cancelled else "complete",
            moved=ok, errors=err,
        )
        self.finished.emit(ok, err)




# ── Model Manager Workers ─────────────────────────────────────────────────────
class ModelListWorker(QThread):
    """Fetch installed models from Ollama in the background."""
    finished = pyqtSignal(list)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        self.finished.emit(_ollama_list_models_detailed(self.url))


class ModelPullWorker(QThread):
    """Download a model with streaming progress updates."""
    progress = pyqtSignal(int, int, str)  # completed, total, status
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)  # success, model_name

    def __init__(self, model: str, url: str):
        super().__init__()
        self.model = model
        self.url = url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        ok = _ollama_pull_model_streaming(
            self.model, self.url,
            progress_cb=lambda c, t, s: self.progress.emit(c, t, s),
            log_cb=lambda msg: self.log.emit(msg)
        )
        self.finished.emit(ok, self.model)


class ModelDeleteWorker(QThread):
    """Delete a model from Ollama in the background."""
    finished = pyqtSignal(bool, str)  # success, model_name

    def __init__(self, model: str, url: str):
        super().__init__()
        self.model = model
        self.url = url

    def run(self):
        self.finished.emit(_ollama_delete_model(self.model, self.url), self.model)


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM CATEGORIES DIALOG
# ══════════════════════════════════════════════════════════════════════════════

# ── PC File Scanner Worker ────────────────────────────────────────────────────
class ScanFilesWorker(QThread):
    """Scans a directory for files and folders, classifies each entry."""
    result_ready = pyqtSignal(dict)
    finished     = pyqtSignal()
    log          = pyqtSignal(str)
    progress     = pyqtSignal(int, int)
    phase        = pyqtSignal(str, str)

    def __init__(self, src_dir, dst_dir, categories, scan_depth=0,
                 check_hashes=False, include_folders=True, include_files=True,
                 ext_filter=None):
        super().__init__()
        self.src_dir        = src_dir
        self.dst_dir        = dst_dir
        self.categories     = categories
        self.scan_depth     = scan_depth
        self.check_hashes   = check_hashes
        self.include_folders = include_folders
        self.include_files  = include_files
        self.ext_filter     = ext_filter   # set of allowed extensions (e.g. _FILTER_IMAGE_EXTS) or None
        self._cancelled     = False

    def cancel(self): self._cancelled = True

    def run(self):
        trace_id = _worker_audit_start(
            "classify",
            "File scan started",
            source_path=self.src_dir,
            mode="file_scan",
        )
        self.phase.emit("Scanning", "Collecting files and folders…")
        src = Path(self.src_dir)
        ext_map = _build_ext_map(self.categories)
        items = self._collect(src)
        if not items:
            _worker_audit_finish(
                "classify", "File scan found no items", trace_id,
                source_path=self.src_dir, status="empty",
            )
            self.log.emit("No files/folders found.")
            self.finished.emit(); return

        total = len(items)
        self.log.emit(f"  Found {total} items to classify")

        # ── Open scan cache for incremental rescans ──────────────────────────
        cache = _ScanCache()
        cache.open()
        cache.prune(max_age_days=30)
        cache_hits = 0

        # ── Progressive duplicate detection (runs before classification) ─────
        dup_map = {}
        if self.check_hashes:
            self.phase.emit("Dedup", "Running progressive duplicate detection…")
            file_entries = []
            for item_path, is_folder in items:
                if not is_folder:
                    try:
                        fsize = item_path.stat().st_size
                        if fsize > 0:
                            file_entries.append((str(item_path), fsize))
                    except OSError:
                        pass
            if len(file_entries) >= 2:
                detector = ProgressiveDuplicateDetector(
                    enable_perceptual=True, phash_threshold=4)
                dup_map = detector.detect(
                    file_entries, log_cb=self.log.emit,
                    progress_cb=lambda c, t: self.progress.emit(c, t))
                self.log.emit(f"  [DEDUP] Complete: {len(dup_map)} files in duplicate groups")

        # ── Classify and emit results ────────────────────────────────────────
        self.phase.emit("Classifying", f"Classifying {total:,} items…")

        # ── Load HEIC/WEBP conversion settings once ─────────────────────────
        _conv_settings = load_ollama_settings()
        _convert_heic = _conv_settings.get('convert_heic_to_jpg', True)
        _convert_webp = _conv_settings.get('convert_webp_to_jpg', True)

        for idx, (item_path, is_folder) in enumerate(items):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}"); break
            self.progress.emit(idx + 1, total)

            name  = item_path.name

            # ── Auto-convert HEIC/WEBP -> JPG if enabled ────────────────────
            if not is_folder:
                ext_lower = os.path.splitext(name)[1].lower()
                if (ext_lower in ('.heic', '.heif') and _convert_heic) or \
                   (ext_lower == '.webp' and _convert_webp):
                    converted = _convert_image_to_jpg(str(item_path), log_cb=self.log.emit)
                    if converted:
                        item_path = Path(converted)
                        name = item_path.name

            fsize = 0
            fmtime = 0.0
            try:
                st = item_path.stat()
                fsize  = st.st_size if not is_folder else 0
                fmtime = st.st_mtime if not is_folder else 0.0
            except OSError:
                pass

            # Look up duplicate info from progressive pipeline
            is_dup = False
            dup_group = 0
            dup_detail = ''
            dup_is_original = False
            fpath_str = str(item_path)
            if fpath_str in dup_map:
                dinfo = dup_map[fpath_str]
                dup_group = dinfo.group_id
                dup_detail = dinfo.detail
                dup_is_original = dinfo.is_original
                is_dup = not dinfo.is_original   # mark non-originals as duplicates
                if is_dup:
                    self.log.emit(f"  [DUP] {name}  —  {dup_detail}")

            # ── Try scan cache first ─────────────────────────────────────────
            cached = None
            if not is_folder and fsize > 0:
                cached = cache.lookup(fpath_str, fmtime, fsize)

            if cached:
                cat      = cached['category']
                conf     = cached['confidence']
                method   = cached['method']
                item_meta = cached.get('metadata', {})
                cache_hits += 1
            else:
                # Classify with multi-signal engine
                cat, conf, method = _classify_pc_item(
                    fpath_str, ext_map, is_folder, self.categories)

                # Extract metadata for files (skip folders)
                item_meta = {}
                if not is_folder:
                    item_meta = MetadataExtractor.extract(fpath_str, log_cb=self.log.emit)

                    # Enrich metadata with filename-extracted dates if EXIF is missing
                    if 'date_taken' not in item_meta and 'creation_date' not in item_meta:
                        fname_dates = _extract_filename_date(name)
                        if fname_dates:
                            item_meta.update(fname_dates)
                            item_meta['_date_source'] = 'filename'

                    if item_meta and len(item_meta) > 1:
                        summary = MetadataExtractor.format_summary(item_meta)
                        if summary:
                            self.log.emit(f"    [META] {summary}")

                # Archive peek — inspect archive contents for smarter classification
                if not is_folder:
                    ext_lower = os.path.splitext(name)[1].lower()
                    if ext_lower in {'.zip', '.rar', '.7z', '.tar.gz', '.tar.bz2', '.tgz'}:
                        try:
                            peek = ArchivePeeker.peek(fpath_str)
                            if peek:
                                item_meta['archive_contents'] = peek
                                arc_cat, arc_conf = ArchivePeeker.classify_contents(peek)
                                if arc_conf > conf:
                                    cat, conf, method = arc_cat, arc_conf, 'archive_peek'
                                    self.log.emit(f"    [ARCHIVE] Reclassified via contents → {cat} ({conf}%)")
                        except Exception:
                            pass

                # Rule Engine — evaluate user-defined rules
                if not is_folder:
                    try:
                        rules = RuleEngine.load_rules()
                        if rules:
                            # Build a minimal FileItem-like dict for rule evaluation
                            _rule_item = type('_RI', (), {
                                'name': name, 'full_src': fpath_str,
                                'size': fsize, 'metadata': item_meta,
                                'category': cat, 'confidence': conf,
                            })()
                            rule_result = RuleEngine.evaluate(_rule_item, rules)
                            if rule_result:
                                r_cat, r_rename, r_conf = rule_result
                                if r_conf > conf:
                                    cat, conf, method = r_cat, r_conf, 'rule'
                                    self.log.emit(f"    [RULE] Matched → {cat} ({conf}%)")
                    except Exception:
                        pass

                # Plugin classifiers
                if not is_folder:
                    try:
                        plug_result = PluginManager.run_classifiers(fpath_str, item_meta)
                        if plug_result:
                            p_cat, p_conf = plug_result
                            if p_conf > conf:
                                cat, conf, method = p_cat, p_conf, 'plugin'
                                self.log.emit(f"    [PLUGIN] Classified → {cat} ({conf}%)")
                    except Exception:
                        pass

                # Store in cache for next scan
                if not is_folder and fsize > 0:
                    cache.store(fpath_str, fmtime, fsize, cat, conf, method, item_meta)

            detail = f"{'Folder' if is_folder else 'File'}: {os.path.splitext(name)[1] or '(no ext)'}"
            self.log.emit(f"  {name}  →  {cat}  ({conf}%) [{method}]")

            self.result_ready.emit({
                'name':       name,
                'full_src':   fpath_str,
                'category':   cat,
                'confidence': conf,
                'method':     method,
                'detail':     detail,
                'size':       fsize,
                'is_folder':  is_folder,
                'is_duplicate': is_dup,
                'dup_group':  dup_group,
                'dup_detail': dup_detail,
                'dup_is_original': dup_is_original,
                'metadata':   item_meta,
            })

        # Flush cache and close
        cache.commit()
        if cache_hits > 0:
            self.log.emit(f"  [CACHE] {cache_hits} items loaded from scan cache (unchanged files)")
        cache.close()

        _worker_audit_finish(
            "classify", "File scan finished", trace_id,
            source_path=self.src_dir, count=total,
            status="cancelled" if self._cancelled else "complete",
        )
        self.finished.emit()

    def _collect(self, src: Path) -> list:
        """Collect (path, is_folder) tuples at the configured depth.
        Filters out OS metadata, temp files, lock files, and hidden items.
        When ext_filter is set, only files with matching extensions are included.
        """
        result = []
        _ef = self.ext_filter   # None or set of allowed extensions
        try:
            if self.scan_depth == 0:
                for entry in src.iterdir():
                    if entry.name.startswith('.') or entry.name.startswith('$'):
                        continue
                    if _JUNK_PATTERNS.match(entry.name):
                        continue
                    ext_low = os.path.splitext(entry.name)[1].lower()
                    if ext_low in _JUNK_SUFFIXES:
                        continue
                    if entry.is_dir() and self.include_folders and not _ef:
                        result.append((entry, True))
                    elif entry.is_file() and self.include_files:
                        if _ef and ext_low not in _ef:
                            continue
                        result.append((entry, False))
            else:
                def _walk_err(e):
                    self.log.emit(f"  SKIP: {e}")
                for root, dirs, files in os.walk(str(src), onerror=_walk_err):
                    rel = os.path.relpath(root, str(src))
                    depth = 0 if rel == '.' else rel.count(os.sep) + 1
                    dirs[:] = [d for d in dirs
                               if not d.startswith('.') and not d.startswith('$')
                               and not _JUNK_PATTERNS.match(d)]
                    if depth > self.scan_depth:
                        dirs.clear(); continue
                    if self.include_files:
                        for f in files:
                            if f.startswith('.') or _JUNK_PATTERNS.match(f):
                                continue
                            f_ext = os.path.splitext(f)[1].lower()
                            if f_ext in _JUNK_SUFFIXES:
                                continue
                            if _ef and f_ext not in _ef:
                                continue
                            result.append((Path(root) / f, False))
                    if self.include_folders and depth < self.scan_depth and not _ef:
                        for d in dirs:
                            result.append((Path(root) / d, True))
        except (PermissionError, OSError) as e:
            self.log.emit(f"  ERROR: {e}")
        return result


# ── PC File Apply Worker ──────────────────────────────────────────────────────
class ApplyFilesWorker(QThread):
    log       = pyqtSignal(str)
    progress  = pyqtSignal(int, int)
    item_done = pyqtSignal(int, str)   # (list_index, status)
    finished  = pyqtSignal(int, int, list)  # ok, err, undo_ops

    def __init__(self, work_items, check_hashes=False, dry_run=False):
        super().__init__()
        self.work_items  = work_items   # list of (list_idx, FileItem)
        self.check_hashes = check_hashes
        self.dry_run     = dry_run
        self._cancelled  = False
        self._xmp_unavailable_logged = False

    def cancel(self): self._cancelled = True

    def run(self):
        ok = err = 0; undo_ops = []
        total = len(self.work_items)
        trace_id = _worker_audit_start(
            "move", "File apply started", mode="file_apply", count=total,
        )
        ts = datetime.now().isoformat()
        for seq, (li, it) in enumerate(self.work_items):
            if self._cancelled:
                self.log.emit(f"  Apply cancelled at {seq}/{total}"); break
            self.progress.emit(seq + 1, total)
            if is_protected(it.full_src):
                self.log.emit(f"  \u26D4 Skipped (protected): {it.name}")
                self.item_done.emit(li, "Protected"); continue
            label = "[DRY RUN] " if self.dry_run else ""
            rename_info = f"  (→ {it.display_name})" if it.display_name != it.name else ""
            self.log.emit(f"  {label}[{seq+1}/{total}] {it.name}{rename_info}  →  {it.category}/")
            merge_manifest = []
            try:
                if not self.dry_run:
                    dst = it.full_dst
                    source_root = getattr(it, 'source_root', '') or os.path.dirname(it.full_src)
                    dest_root = getattr(it, 'dest_root', '')
                    validate_move(
                        it.full_src,
                        dst,
                        source_root=source_root,
                        dest_root=dest_root,
                        allow_existing_dest=os.path.exists(dst),
                    )
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.exists(dst):
                        if it.is_folder:
                            merged, skipped = safe_merge_move(
                                it.full_src, dst,
                                log_cb=self.log.emit, check_hashes=self.check_hashes,
                                manifest=merge_manifest,
                            )
                            self.log.emit(
                                f"    Merged ({merged} collisions preserved, "
                                f"{skipped} skipped)"
                            )
                        else:
                            # File collision — keep both by suffixing
                            base, ext2 = os.path.splitext(dst)
                            n = 2
                            while os.path.exists(dst):
                                dst = f"{base} ({n}){ext2}"; n += 1
                            validate_move(
                                it.full_src,
                                dst,
                                source_root=source_root,
                                dest_root=dest_root,
                            )
                            shutil.move(it.full_src, dst)
                    else:
                        shutil.move(it.full_src, dst)
                ok += 1
                undo_op = {'type': 'move', 'src': dst if not self.dry_run else it.full_dst, 'dst': it.full_src,
                    'timestamp': ts, 'category': it.category,
                    'confidence': str(it.confidence), 'status': 'Done',
                    'source_root': getattr(it, 'source_root', '') or os.path.dirname(it.full_src),
                    'dest_root': getattr(it, 'dest_root', '')}
                if merge_manifest:
                    undo_op['merge_manifest'] = merge_manifest
                undo_ops.append(undo_op)
                self.log.emit(f"    ✅ Done")
                self.item_done.emit(li, "Done")
                # Plugin post-move hooks
                try:
                    PluginManager.run_post_move(it.full_src, dst if not self.dry_run else it.full_dst, it.category)
                except Exception:
                    pass
                if not self.dry_run and not it.is_folder:
                    try:
                        sidecar = write_classification_sidecar(
                            dst,
                            category=it.category,
                            confidence=it.confidence,
                            method=it.method,
                            detail=it.detail,
                            metadata=it.metadata,
                        )
                        if sidecar.status == "written":
                            self.log.emit(f"    [XMP] Wrote {os.path.basename(sidecar.sidecar_path)}")
                        elif sidecar.status == "failed":
                            self.log.emit(f"    [XMP] Skipped: {sidecar.detail}")
                        elif sidecar.status == "unavailable" and not self._xmp_unavailable_logged:
                            self.log.emit(f"    [XMP] Sidecars unavailable: {sidecar.detail}")
                            self._xmp_unavailable_logged = True
                    except Exception as exc:
                        # Sidecar provenance is optional and must never turn a
                        # completed filesystem move into a failed move.
                        self.log.emit(f"    [XMP] Skipped: {exc}")
            except Exception as e:
                err += 1
                self.log.emit(f"    ❌ Error: {e}")
                if not self.dry_run and merge_manifest:
                    restore_merge_manifest(
                        merge_manifest,
                        getattr(it, 'source_root', '') or os.path.dirname(it.full_src),
                        getattr(it, 'dest_root', ''),
                        log_cb=self.log.emit,
                    )
                self.item_done.emit(li, "Error")
        _worker_audit_finish(
            "move", "File apply finished", trace_id,
            status=(
                "cancelled" if self._cancelled
                else ("dry_run" if self.dry_run else "complete")
            ),
            moved=ok, errors=err,
        )
        self.finished.emit(ok, err, undo_ops)


# ── Parallel Vision Runnable ──────────────────────────────────────────────────

class _VisionSignals(QObject):
    """Signals for VisionRunnable (QRunnable can't emit signals directly)."""
    result_ready = pyqtSignal(int, dict)  # (index, result_dict)
    log = pyqtSignal(str)


class VisionRunnable(QRunnable):
    """Runs vision + face detection + blur analysis for a single image in parallel."""

    def __init__(self, index: int, filepath: str, ollama_url: str, vision_model: str,
                 face_db=None, face_mutex: QMutex = None, photo_settings: dict = None):
        super().__init__()
        self.index = index
        self.filepath = filepath
        self.ollama_url = ollama_url
        self.vision_model = vision_model
        self.face_db = face_db
        self.face_mutex = face_mutex
        self.photo_settings = photo_settings or {}
        self.signals = _VisionSignals()
        self.setAutoDelete(True)

    def run(self):
        result = {}
        fname = os.path.basename(self.filepath)
        try:
            import urllib.request
            # ── Vision description via Ollama ────────────────────────────────
            if self.vision_model and self.ollama_url:
                try:
                    with open(self.filepath, 'rb') as f:
                        img_b64 = base64.b64encode(f.read()).decode('ascii')
                    prompt = ("Describe this image concisely. "
                              "If there is text, include it verbatim under 'detected_text'. "
                              "Suggest a descriptive filename under 'suggested_name'.")
                    payload = json.dumps({
                        "model": self.vision_model,
                        "prompt": prompt,
                        "images": [img_b64],
                        "stream": False
                    }).encode()
                    req = urllib.request.Request(
                        f"{self.ollama_url}/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        data = json.loads(resp.read())
                    response_text = data.get('response', '')
                    result['vision_description'] = response_text[:500]
                    # Try to parse JSON from response
                    try:
                        parsed = json.loads(response_text)
                        if isinstance(parsed, dict):
                            result['vision_ocr'] = parsed.get('detected_text', '')
                            result['vision_name'] = parsed.get('suggested_name', '')
                    except (json.JSONDecodeError, TypeError):
                        pass
                    self.signals.log.emit(f"    [VISION] {fname}: done")
                except Exception as e:
                    self.signals.log.emit(f"    [VISION] {fname}: {e}")

            # ── Blur detection ───────────────────────────────────────────────
            if HAS_CV2 and self.photo_settings.get('blur_detection', False):
                try:
                    img = _cv2.imread(self.filepath, _cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        lap_var = _cv2.Laplacian(img, _cv2.CV_64F).var()
                        result['blur_score'] = lap_var
                except Exception:
                    pass

            # ── Face detection ───────────────────────────────────────────────
            if HAS_FACE_RECOGNITION and self.photo_settings.get('face_recognition', False):
                try:
                    image = _face_recognition.load_image_file(self.filepath)
                    locations = _face_recognition.face_locations(image)
                    result['face_count'] = len(locations)
                    if locations and self.face_db is not None:
                        encodings = _face_recognition.face_encodings(image, locations)
                        persons = []
                        if self.face_mutex:
                            self.face_mutex.lock()
                        try:
                            for enc in encodings:
                                name = self.face_db.identify(enc)
                                persons.append(name)
                        finally:
                            if self.face_mutex:
                                self.face_mutex.unlock()
                        result['persons'] = persons
                        result['primary_person'] = persons[0] if persons else ''
                    self.signals.log.emit(f"    [FACE] {fname}: {len(locations)} face(s)")
                except Exception as e:
                    self.signals.log.emit(f"    [FACE] {fname}: {e}")

        except Exception as e:
            self.signals.log.emit(f"    [VISION_RUNNABLE] {fname}: {e}")

        self.signals.result_ready.emit(self.index, result)


# ── PC LLM Scanner Worker ─────────────────────────────────────────────────────
class ScanFilesLLMWorker(QThread):
    """LLM-powered classification for all files/folders."""
    result_ready = pyqtSignal(dict)
    finished     = pyqtSignal()
    log          = pyqtSignal(str)
    progress     = pyqtSignal(int, int)
    phase        = pyqtSignal(str, str)

    def __init__(self, src_dir, dst_dir, categories, scan_depth=0,
                 check_hashes=False, include_folders=True, include_files=True,
                 ext_filter=None):
        super().__init__()
        self.src_dir        = src_dir
        self.dst_dir        = dst_dir
        self.categories     = categories
        self.scan_depth     = scan_depth
        self.check_hashes   = check_hashes
        self.include_folders = include_folders
        self.include_files  = include_files
        self.ext_filter     = ext_filter
        self._cancelled     = False
        self._fallback_worker = None

    def _fallback_rule_based(self):
        """Run rule-based classification as fallback."""
        fallback = ScanFilesWorker(
            self.src_dir, self.dst_dir, self.categories,
            self.scan_depth, self.check_hashes,
            self.include_folders, self.include_files,
            ext_filter=self.ext_filter)
        # Forward cancel state so the user can stop the fallback scan too
        fallback._cancelled = self._cancelled
        self._fallback_worker = fallback  # keep ref for cancel forwarding
        fallback.result_ready.connect(self.result_ready)
        fallback.log.connect(self.log)
        fallback.progress.connect(self.progress)
        fallback.phase.connect(self.phase)
        fallback.run(); self.finished.emit()

    def cancel(self):
        self._cancelled = True
        if hasattr(self, '_fallback_worker') and self._fallback_worker:
            self._fallback_worker._cancelled = True

    def _ensure_ollama_ready(self, settings) -> bool:
        """Ensure Ollama server is running and model is pulled.
        Returns True if ready, False if unrecoverable."""
        url = settings['url']
        model = settings['model']

        # ── Step 1: Check if server is running, start if not ──
        if not _is_ollama_server_running(url):
            self.log.emit("  Ollama server not running — attempting to start...")
            self.phase.emit("LLM Setup", "Starting Ollama server...")
            binary = _find_ollama_binary()
            if not binary:
                self.log.emit("  Ollama not installed. Install from https://ollama.com")
                return False
            # Start server in background
            try:
                if sys.platform == 'win32':
                    subprocess.Popen([binary, 'serve'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=0x00000008)  # DETACHED_PROCESS
                else:
                    subprocess.Popen([binary, 'serve'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
            except Exception as e:
                self.log.emit(f"  Failed to start Ollama: {e}")
                return False
            # Wait up to 15s for server
            for _ in range(30):
                time.sleep(0.5)
                if self._cancelled:
                    return False
                if _is_ollama_server_running(url):
                    break
            if not _is_ollama_server_running(url):
                self.log.emit("  Ollama server did not start within 15s")
                return False
            self.log.emit("  Ollama server started")

        # ── Step 2: Check if model is pulled ──
        if not _ollama_has_model(model, url):
            self.log.emit(
                f"  Model '{model}' is not installed. Open Settings > Ollama LLM "
                "and choose Pull Model or Model Manager."
            )
            self.phase.emit("LLM Setup", f"Pull {model} in Settings")
            return False

        return True

    def run(self):
        trace_id = _worker_audit_start(
            "classify",
            "LLM file scan started",
            source_path=self.src_dir,
            mode="file_llm_scan",
        )
        settings = load_ollama_settings()

        # Check the user-installed Ollama server and selected model.
        self.phase.emit("LLM Setup", "Checking Ollama...")
        if not self._ensure_ollama_ready(settings):
            self.log.emit("  LLM unavailable — falling back to rule-based classification")
            self._fallback_rule_based(); return

        # Final connectivity check
        ok, msg, _ = ollama_test_connection(settings['url'], settings['model'])
        if not ok:
            self.log.emit(f"  LLM connection failed ({msg}) — falling back to rule-based")
            self._fallback_rule_based(); return

        self.phase.emit("Scanning", "Collecting items…")
        src = Path(self.src_dir)
        rule_worker = ScanFilesWorker(
            self.src_dir, self.dst_dir, self.categories,
            self.scan_depth, self.check_hashes,
            self.include_folders, self.include_files,
            ext_filter=self.ext_filter)
        items = rule_worker._collect(src)
        if not items:
            _worker_audit_finish(
                "classify", "LLM file scan found no items", trace_id,
                source_path=self.src_dir, status="empty",
            )
            self.log.emit("No items found."); self.finished.emit(); return

        cat_names = [c['name'] for c in self.categories]
        ext_map   = _build_ext_map(self.categories)
        total     = len(items)
        self.log.emit(f"  LLM classifying {total} items via [{settings['model']}]")

        # ── Open scan cache for incremental rescans ──────────────────────────
        cache = _ScanCache()
        cache.open()
        cache.prune(max_age_days=30)
        cache_hits = 0

        # ── Progressive duplicate detection (runs before classification) ─────
        dup_map = {}
        if self.check_hashes:
            self.phase.emit("Dedup", "Running progressive duplicate detection…")
            file_entries = []
            for item_path, is_folder in items:
                if not is_folder:
                    try:
                        fsize = item_path.stat().st_size
                        if fsize > 0:
                            file_entries.append((str(item_path), fsize))
                    except OSError:
                        pass
            if len(file_entries) >= 2:
                detector = ProgressiveDuplicateDetector(
                    enable_perceptual=True, phash_threshold=4)
                dup_map = detector.detect(
                    file_entries, log_cb=self.log.emit,
                    progress_cb=lambda c, t: self.progress.emit(c, t))

        self.phase.emit("AI Classify", f"LLM classifying {total:,} items…")

        # ── Vision detection ─────────────────────────────────────────────────
        _v_enabled = settings.get('vision_enabled', True)
        _v_pil = HAS_PILLOW
        vision_max_bytes = settings.get('vision_max_file_mb', 20) * 1024 * 1024
        vision_max_px = settings.get('vision_max_pixels', 1024)
        _content_enabled = settings.get('content_extraction', True)
        _content_max = settings.get('content_max_chars', 800)
        vision_model = settings['model']  # may differ from text model

        # Check if scan has any images worth sending to vision
        has_images = any(
            not is_folder and os.path.splitext(str(p))[1].lower() in _PHASH_IMAGE_EXTS
            for p, is_folder in items
        )

        if _v_enabled and _v_pil and has_images:
            if _is_vision_model(settings['model']):
                # Selected model is already vision-capable
                vision_model = settings['model']
                self.log.emit(f"  Vision: using selected model [{vision_model}]")
            else:
                # Selected model is text-only — use an already-installed vision model.
                self.log.emit(
                    f"  Selected model [{settings['model']}] is text-only — "
                    "checking installed vision models..."
                )
                vision_model = _find_vision_model(settings['url'], auto_upgrade=False)
                if vision_model:
                    self.log.emit(f"  Vision: found [{vision_model}]")
                else:
                    self.log.emit(
                        "  Vision: no installed vision model; use Settings > Ollama LLM "
                        "to download one explicitly, then rescan"
                    )

        use_vision = bool(_v_enabled and _v_pil and has_images and vision_model and _is_vision_model(vision_model))
        self.log.emit(f"  Vision active: {use_vision}" + (f" [{vision_model}]" if use_vision else ""))

        system_vision = (
            f"You are a file organizer with vision. Classify this image into "
            f"exactly ONE category: {', '.join(cat_names)}.\n"
            "Respond ONLY with valid JSON:\n"
            "{\"category\": \"<name>\", \"confidence\": <0-100>, \"reason\": \"<brief>\", "
            "\"description\": \"<what you see in 1-2 sentences>\", "
            "\"suggested_name\": \"<descriptive_filename>\", "
            "\"detected_text\": \"<visible text or empty>\"}\n"
            "IMPORTANT: suggested_name MUST describe the visual content of the image. "
            "Use lowercase_with_underscores, max 60 chars. Examples: "
            "dog_wearing_bandana_on_chair, sunset_over_mountain_lake, error_dialog_task_failed. "
            "NEVER copy or reuse the original filename."
        )

        # Enhanced vision prompt for photo organization (scene tagging)
        _photo_s = load_photo_settings()
        if _photo_s.get('enabled') and _photo_s.get('scene_tagging_enabled'):
            system_vision = (
                f"You are a photo organizer with vision. Classify this image into "
                f"exactly ONE category: {', '.join(cat_names)}.\n"
                f"Also identify the photo scene type from: {', '.join(_PHOTO_SCENES)}.\n"
                "Respond ONLY with valid JSON:\n"
                "{\"category\": \"<name>\", \"confidence\": <0-100>, \"reason\": \"<brief>\", "
                "\"description\": \"<what you see in 2-3 sentences>\", "
                "\"suggested_name\": \"<descriptive_filename>\", "
                "\"detected_text\": \"<visible text or empty>\", "
                "\"photo_type\": \"<scene from list above>\"}\n"
                "IMPORTANT: suggested_name MUST describe the visual content of the image. "
                "Use lowercase_with_underscores, max 60 chars. "
                "NEVER copy or reuse the original filename."
            )

        BATCH_SIZE = 5
        system_batch = (
            f"You are a file organizer. Classify each item into exactly ONE of these categories: "
            f"{', '.join(cat_names)}.\n"
            "Respond ONLY with a valid JSON array of objects, one per item in order: "
            "[{\"category\": \"<name>\", \"confidence\": <0-100>, \"reason\": \"<brief>\", "
            "\"suggested_name\": \"<short_descriptive_filename_no_ext>\"}, ...]\n"
            "For suggested_name: use lowercase_with_underscores, max 60 chars, descriptive of the "
            "actual content. If no content preview is provided, clean up the original filename.\n"
            "No other text."
        )
        system_single = (
            f"You are a file organizer. Classify the given item into exactly ONE of these categories: "
            f"{', '.join(cat_names)}.\n"
            "Respond ONLY with valid JSON: "
            "{\"category\": \"<name>\", \"confidence\": <0-100>, \"reason\": \"<brief>\", "
            "\"suggested_name\": \"<short_descriptive_filename_no_ext>\"}\n"
            "For suggested_name: use lowercase_with_underscores, max 60 chars, descriptive of the "
            "actual content. If no content preview is provided, clean up the original filename.\n"
            "No other text."
        )

        def _prep_item(item_path, is_folder, name):
            """Build context lines for one item (sanitize for LLM injection)."""
            ext = os.path.splitext(name)[1].lower()
            safe_name = re.sub(r'[{}\[\]<>]', '', name)[:200]
            ctx_lines = [f"Item: \"{safe_name}\"",
                         f"Type: {'folder' if is_folder else 'file'}",
                         f"Extension: {ext or 'none'}"]
            if is_folder:
                try:
                    children = [re.sub(r'[{}\[\]<>]', '', e.name)[:80]
                                for e in os.scandir(str(item_path))][:10]
                    if children: ctx_lines.append(f"Contains: {', '.join(children)}")
                except (PermissionError, OSError): pass
            elif _content_enabled:
                snippet = _extract_file_content(str(item_path), max_chars=_content_max)
                if snippet:
                    ctx_lines.append(f"Content preview:\n{snippet}")
            return '\n'.join(ctx_lines)

        def _parse_llm(raw):
            """Clean LLM response and parse JSON. Handles prose-wrapped and
            markdown-fenced responses from models that don't return bare JSON."""
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
            raw = re.sub(r'<think>.*$', '', raw, flags=re.DOTALL)
            raw = raw.strip()
            # Try extracting JSON from markdown code fences (```json ... ```)
            fence_m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', raw)
            if fence_m:
                raw = fence_m.group(1).strip()
            elif raw.startswith('```'):
                raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
            # Try extracting a JSON object or array from prose text
            if not raw.startswith(('{', '[')):
                obj_m = re.search(r'(\{[\s\S]*\})', raw)
                arr_m = re.search(r'(\[[\s\S]*\])', raw)
                if obj_m:
                    raw = obj_m.group(1)
                elif arr_m:
                    raw = arr_m.group(1)
            return json.loads(raw)

        def _build_item_data(item_path, is_folder):
            """Prepare per-item data dict with dup info."""
            name = item_path.name
            fsize = 0
            fmtime = 0.0
            try:
                st = item_path.stat()
                fsize = st.st_size if not is_folder else 0
                fmtime = st.st_mtime if not is_folder else 0.0
            except OSError: pass
            fpath_str = str(item_path)
            is_dup = False; dup_group = 0; dup_detail = ''; dup_is_original = False
            if fpath_str in dup_map:
                dinfo = dup_map[fpath_str]
                dup_group = dinfo.group_id; dup_detail = dinfo.detail
                dup_is_original = dinfo.is_original; is_dup = not dinfo.is_original
            return {
                'item_path': item_path, 'is_folder': is_folder, 'name': name,
                'fsize': fsize, 'fmtime': fmtime, 'is_dup': is_dup,
                'dup_group': dup_group, 'dup_detail': dup_detail,
                'dup_is_original': dup_is_original,
            }

        def _emit_cached(bd, cached):
            """Emit a result from cache without re-running AI or metadata."""
            item_meta = cached.get('metadata', {})
            detail = item_meta.pop('_cached_detail', '')
            v_desc = item_meta.pop('_cached_vision_desc', '')
            v_ocr = item_meta.pop('_cached_vision_ocr', '')
            v_sname = item_meta.pop('_cached_vision_sname', '')
            c_sname = item_meta.pop('_cached_content_sname', '')
            result = {
                'name': bd['name'], 'full_src': str(bd['item_path']),
                'category': cached['category'], 'confidence': cached['confidence'],
                'method': cached['method'], 'detail': detail, 'size': bd['fsize'],
                'is_folder': bd['is_folder'], 'is_duplicate': bd['is_dup'],
                'dup_group': bd['dup_group'], 'dup_detail': bd['dup_detail'],
                'dup_is_original': bd['dup_is_original'], 'metadata': item_meta,
            }
            if v_desc or v_sname:
                result['vision_description'] = v_desc
                result['vision_ocr'] = v_ocr
                result['vision_suggested_name'] = v_sname
            elif c_sname:
                result['vision_suggested_name'] = c_sname
            self.log.emit(f"  {bd['name']}  →  {cached['category']}  ({cached['confidence']}%) [{cached['method']}]")
            self.result_ready.emit(result)

        def _extract_and_emit(bd, cat, conf, method, reason, vision_data=None, content_data=None):
            """Extract metadata and emit result for one item."""
            self.log.emit(f"  {bd['name']}  →  {cat}  ({conf}%) [{method}]")

            item_meta = {}
            if not bd['is_folder']:
                item_meta = MetadataExtractor.extract(str(bd['item_path']), log_cb=self.log.emit)
                if 'date_taken' not in item_meta and 'creation_date' not in item_meta:
                    fname_dates = _extract_filename_date(bd['name'])
                    if fname_dates:
                        item_meta.update(fname_dates)
                        item_meta['_date_source'] = 'filename'
                if item_meta and len(item_meta) > 1:
                    summary = MetadataExtractor.format_summary(item_meta)
                    if summary:
                        self.log.emit(f"    [META] {summary}")

            # ── Photo organization metadata ──────────────────────────────────
            _photo_s_ext = load_photo_settings()
            if _photo_s_ext.get('enabled') and not bd['is_folder']:
                _img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif',
                             '.tiff', '.tif', '.bmp', '.raw', '.cr2', '.cr3', '.crw', '.nef', '.nrw',
                             '.arw', '.dng', '.orf', '.rw2', '.raf', '.pef', '.rwl', '.x3f', '.3fr',
                             '.dcr', '.kdc', '.mrw', '.iiq', '.fff', '.mef', '.mos', '.cap'}
                if Path(bd['name']).suffix.lower() in _img_exts:
                    # Reverse geocoding from EXIF GPS
                    if _photo_s_ext.get('geocoding_enabled'):
                        lat = item_meta.get('gps_lat')
                        lon = item_meta.get('gps_lon')
                        if lat is not None and lon is not None:
                            geo = _reverse_geocode(round(lat, 4), round(lon, 4))
                            item_meta['_photo_city'] = geo.get('city', '')
                            item_meta['_photo_country'] = geo.get('country', '')
                            if geo.get('city'):
                                self.log.emit(f"    [GEO] {geo['city']}, {geo.get('country', '')}")

                    # Blur detection
                    if _photo_s_ext.get('blur_detection_enabled'):
                        blur = _compute_blur_score(str(bd['item_path']))
                        item_meta['_photo_blur'] = blur
                        item_meta['_photo_blur_threshold'] = _photo_s_ext.get('blur_threshold', 100.0)
                        if blur >= 0:
                            label = 'blurry' if blur < _photo_s_ext['blur_threshold'] else 'sharp'
                            self.log.emit(f"    [BLUR] {blur:.1f} ({label})")

                    # Face recognition
                    if _photo_s_ext.get('face_recognition_enabled'):
                        if HAS_FACE_RECOGNITION:
                            if not hasattr(_extract_and_emit, '_face_db'):
                                _extract_and_emit._face_db = FaceDB()
                            fr = _detect_faces_full(str(bd['item_path']), _extract_and_emit._face_db)
                            if fr.get('face_count', 0) > 0:
                                item_meta['_photo_face_count'] = fr['face_count']
                                item_meta['_photo_face_primary'] = fr['primary_person']
                                item_meta['_photo_face_persons'] = fr['persons']
                                names = ', '.join(fr['persons'][:5])
                                self.log.emit(f"    [FACE] {fr['face_count']} face(s): {names}")
                            else:
                                item_meta['_photo_face_count'] = 0
                        elif HAS_CV2:
                            fc = _detect_faces_count_only(str(bd['item_path']))
                            if fc > 0:
                                item_meta['_photo_face_count'] = fc
                                self.log.emit(f"    [FACE] {fc} face(s) detected (count only)")
                            elif fc == 0:
                                item_meta['_photo_face_count'] = 0

            # Inject vision data into metadata for rename template tokens
            if vision_data:
                item_meta['_vision_name'] = vision_data.get('suggested_name', '')
                item_meta['_vision_ocr'] = vision_data.get('detected_text', '')
                if item_meta['_vision_name']:
                    self.log.emit(f"    [RENAME] {bd['name']} -> {item_meta['_vision_name']}")

                # Extract photo scene from vision response
                if _photo_s_ext.get('enabled') and _photo_s_ext.get('scene_tagging_enabled'):
                    scene = vision_data.get('photo_type', '')
                    if scene and scene.lower() in [s.lower() for s in _PHOTO_SCENES]:
                        item_meta['_photo_scene'] = scene.lower()

            # Inject content-derived name (reuses vision_name pipeline)
            if content_data and not vision_data:
                sug = content_data.get('suggested_name', '')
                if sug and len(sug) >= 3:
                    item_meta['_vision_name'] = sug
                    self.log.emit(f"    [CONTENT] {bd['name']} -> {sug}")

            result = {
                'name': bd['name'], 'full_src': str(bd['item_path']),
                'category': cat, 'confidence': conf, 'method': method,
                'detail': reason, 'size': bd['fsize'],
                'is_folder': bd['is_folder'], 'is_duplicate': bd['is_dup'],
                'dup_group': bd['dup_group'], 'dup_detail': bd['dup_detail'],
                'dup_is_original': bd['dup_is_original'],
                'metadata': item_meta,
            }
            if vision_data:
                result['vision_description'] = vision_data.get('description', '')
                result['vision_ocr'] = vision_data.get('detected_text', '')
                result['vision_suggested_name'] = vision_data.get('suggested_name', '')
            if content_data and not vision_data:
                result['vision_suggested_name'] = content_data.get('suggested_name', '')

            # ── Store in cache for next scan ─────────────────────────────────
            if not bd['is_folder'] and bd['fsize'] > 0 and bd.get('fmtime', 0) > 0:
                cache_meta = dict(item_meta)
                cache_meta['_cached_detail'] = reason or ''
                if vision_data:
                    cache_meta['_cached_vision_desc'] = vision_data.get('description', '')
                    cache_meta['_cached_vision_ocr'] = vision_data.get('detected_text', '')
                    cache_meta['_cached_vision_sname'] = vision_data.get('suggested_name', '')
                if content_data and not vision_data:
                    cache_meta['_cached_content_sname'] = content_data.get('suggested_name', '')
                cache.store(str(bd['item_path']), bd['fmtime'], bd['fsize'],
                            cat, conf, method, cache_meta)

            self.result_ready.emit(result)

        def _is_vision_eligible(item_path, is_folder, fsize):
            """Check if an item is an image eligible for vision classification."""
            if not use_vision or is_folder:
                return False
            ext = os.path.splitext(str(item_path))[1].lower()
            if ext not in _PHASH_IMAGE_EXTS:
                return False
            if fsize > vision_max_bytes:
                return False
            return True

        def _vision_fuzzy_match_category(raw_text, cat_names_list):
            """Try to find a category name mentioned in free-text vision output."""
            lower = raw_text.lower()
            # Exact substring match (case-insensitive)
            for cn in cat_names_list:
                if cn.lower() in lower:
                    return cn
            # Try partial word matches for multi-word categories
            for cn in cat_names_list:
                words = cn.lower().split()
                if len(words) > 1 and all(w in lower for w in words):
                    return cn
            return ''

        def _is_poisoned_name(s):
            """Reject names that look like JSON key leakage or LLM garbage."""
            sl = s.lower().replace('-', '_').replace(' ', '_')
            _poison = ('category', 'confidence', 'reason', 'suggested_name',
                       'detected_text', 'description', 'the_image_is',
                       'this_image', 'image_is', 'no_ext', 'json', 'null',
                       'according_to', 'here_is', 'classified', 'classification',
                       'given_input', 'provided_image', 'based_on', 'as_follows',
                       'the_file_is', 'output_is', 'result_is', 'response_is')
            return any(p in sl for p in _poison)

        def _vision_name_from_description(desc, max_len=50):
            """Derive a short snake_case filename from a vision description."""
            if not desc:
                return ''
            # Reject if the description looks like raw JSON
            stripped = desc.strip()
            if stripped.startswith('{') or stripped.startswith('['):
                return ''
            # Take first sentence
            first = re.split(r'[.!?\n]', desc)[0].strip()
            # Strip filler prefixes iteratively (handles "The image is a photo of...")
            changed = True
            while changed:
                changed = False
                for filler in ['according to the given input ', 'according to ',
                               'here is the classification ', 'here is the ',
                               'based on the image ', 'based on ',
                               'the classified information ', 'classified as ',
                               'the image is of ', 'the image is a ', 'the image is an ',
                               'the image is ', 'the image shows ', 'the image features ',
                               'the image depicts ', 'the image contains ',
                               'this image is a ', 'this image is an ', 'this image is ',
                               'this image shows ', 'this is a ', 'this is an ', 'this is ',
                               'it shows ', 'it is a ', 'it is an ', 'it is ',
                               'a photo of ', 'a photograph of ', 'a picture of ',
                               'an image of ', 'a screenshot of ', 'a close-up of ',
                               'a meme featuring ', 'a meme with ', 'a meme that ',
                               'a meme of ', 'a meme about ', 'a meme ',
                               'featuring ', 'showing ', 'depicting ']:
                    if first.lower().startswith(filler):
                        first = first[len(filler):]
                        changed = True
                        break
            # Strip leading articles
            for art in ['a ', 'an ', 'the ']:
                if first.lower().startswith(art):
                    first = first[len(art):]
            # Clean to snake_case
            slug = re.sub(r'[^a-zA-Z0-9\s]', '', first).strip()
            slug = re.sub(r'\s+', '_', slug).lower()
            # Truncate to max_len at word boundary
            if len(slug) > max_len:
                slug = slug[:max_len].rsplit('_', 1)[0]
            # Remove trailing noise words left by truncation
            _noise_tail = re.compile(r'(_with|_and|_in|_on|_at|_a|_an|_the|_that|_which|_where|_from|_for|_to|_of|_by)$')
            while _noise_tail.search(slug):
                slug = _noise_tail.sub('', slug)
            # Final poison check
            if _is_poisoned_name(slug):
                return ''
            return slug if len(slug) >= 3 else ''

        def _classify_vision(bd):
            """Classify a single image using vision model. Returns (cat, conf, reason, vision_data) or None."""
            name = bd['name']
            fpath = str(bd['item_path'])
            self.log.emit(f"    [VISION] Processing: {name}")
            b64 = _prepare_image_base64(fpath, max_pixels=vision_max_px)
            if not b64:
                self.log.emit(f"    [VISION] Failed to encode image: {name}")
                return None
            prompt = "Classify this image based on what you see. For suggested_name, describe the visual content — do NOT reuse the original filename."
            try:
                raw = _ollama_generate(prompt, system=system_vision,
                                       url=settings['url'], model=vision_model,
                                       images=[b64], log_cb=self.log.emit)
                # Try JSON parse first
                try:
                    parsed = _parse_llm(raw)
                except (json.JSONDecodeError, ValueError):
                    parsed = None

                if parsed and isinstance(parsed, dict):
                    cat = parsed.get('category', '')
                    conf = int(parsed.get('confidence', 70))
                    reason = parsed.get('reason', '')
                    if cat not in cat_names:
                        self.log.emit(f"    [VISION] Unknown category '{cat}' — text fallback")
                        return None
                    raw_sug = parsed.get('suggested_name', '')
                    if _is_poisoned_name(raw_sug):
                        raw_sug = _vision_name_from_description(parsed.get('description', ''))
                    vision_data = {
                        'description': parsed.get('description', ''),
                        'suggested_name': raw_sug,
                        'detected_text': parsed.get('detected_text', ''),
                    }
                    desc_preview = (parsed.get('description', '') or '')[:80]
                    self.log.emit(f"    [VISION] {name} -> {cat} ({conf}%) | {desc_preview}")
                    return (cat, conf, reason, vision_data)

                # ── Fallback: vision model returned free text instead of JSON ──
                # Extract what we can from the natural language response
                raw_clean = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                # Strip common LLM preamble to isolate actual descriptive content
                _preamble_re = re.compile(
                    r'^(?:according to[^.]*[.:]|here is[^.]*[.:]|based on[^.]*[.:]|'
                    r'the (?:classified|classification)[^.]*[.:])\s*',
                    re.IGNORECASE)
                desc_clean = _preamble_re.sub('', raw_clean).strip()
                # Try to find a "Reason:" or "Description:" line for actual content
                reason_m = re.search(r'(?:reason|description|depicts?|shows?)\s*[:]\s*(.+)', desc_clean, re.IGNORECASE)
                description = reason_m.group(1).strip()[:300] if reason_m else desc_clean[:300]
                # Try to match a category from the full text
                matched_cat = _vision_fuzzy_match_category(raw_clean, cat_names)
                if matched_cat:
                    sug_name = _vision_name_from_description(description)
                    vision_data = {
                        'description': description,
                        'suggested_name': sug_name,
                        'detected_text': '',
                    }
                    self.log.emit(f"    [VISION] {name} -> {matched_cat} (60%) [text-extract] | {description[:80]}")
                    return (matched_cat, 60, 'vision_text_extract', vision_data)

                # No category match but still capture the description for metadata
                self.log.emit(f"    [VISION] {name} -> no JSON, no category match | {description[:80]}")
                # Return None for classification but the description is lost --
                # try a re-classify with a text-only model using the description
                if description:
                    sug_name = _vision_name_from_description(description)
                    vision_data = {
                        'description': description,
                        'suggested_name': sug_name,
                        'detected_text': '',
                    }
                    # Use text model to classify based on vision description
                    try:
                        reclassify_prompt = (
                            f"An image was described as: \"{description[:500]}\"\n"
                            f"The filename is: \"{re.sub('[{}[\\]<>]', '', name)[:200]}\"\n"
                            f"Classify into exactly ONE category: {', '.join(cat_names)}\n"
                            "Respond ONLY with JSON: {\"category\": \"<name>\", \"confidence\": <0-100>, "
                            "\"reason\": \"<brief>\", \"suggested_name\": \"<short_descriptive_name_no_ext>\"}"
                        )
                        text_model = ModelRouter.get_model('text_classify', url=settings['url'],
                                                           log_cb=self.log.emit, auto_pull=False)
                        if text_model:
                            raw2 = _ollama_generate(reclassify_prompt,
                                                    url=settings['url'], model=text_model)
                            p2 = _parse_llm(raw2)
                            cat2 = p2.get('category', '')
                            if cat2 in cat_names:
                                conf2 = int(p2.get('confidence', 65))
                                # Upgrade suggested_name if the text model provided a clean one
                                txt_sug = p2.get('suggested_name', '')
                                if txt_sug and len(txt_sug) >= 3:
                                    txt_sug_clean = re.sub(r'[^a-zA-Z0-9_\- ]', '', txt_sug)[:60].strip()
                                    if txt_sug_clean and not _is_poisoned_name(txt_sug_clean):
                                        vision_data['suggested_name'] = txt_sug_clean
                                self.log.emit(f"    [VISION->TEXT] {name} -> {cat2} ({conf2}%) | reclassified via {text_model}")
                                return (cat2, conf2, 'vision_reclassify', vision_data)
                    except Exception:
                        pass
                return None
            except Exception as e:
                self.log.emit(f"    [VISION] Error for {name}: {e}")
                return None

        idx = 0
        consecutive_llm_failures = 0
        MAX_CONSECUTIVE_FAILURES = 5
        llm_disabled = False
        while idx < total:
            if self._cancelled:
                self.log.emit(f"  Cancelled at {idx}/{total}"); break

            # Collect batch
            batch = []
            while len(batch) < BATCH_SIZE and idx < total:
                batch.append(items[idx])
                idx += 1
            self.progress.emit(idx, total)

            # If LLM keeps failing, fall back to rule-based for text items
            if consecutive_llm_failures >= MAX_CONSECUTIVE_FAILURES and not llm_disabled:
                llm_disabled = True
                self.log.emit(f"  {consecutive_llm_failures} consecutive LLM failures -- using rule-based for remaining items")

            # Separate vision-eligible images from text items
            text_batch_data = []
            for item_path, is_folder in batch:
                bd = _build_item_data(item_path, is_folder)

                # ── Cache check — skip AI if file unchanged since last scan ──
                if not bd['is_folder'] and bd['fsize'] > 0:
                    cached = cache.lookup(str(bd['item_path']), bd['fmtime'], bd['fsize'])
                    if cached:
                        cache_hits += 1
                        _emit_cached(bd, cached)
                        continue

                if _is_vision_eligible(item_path, is_folder, bd['fsize']):
                    # Try vision classification
                    result = _classify_vision(bd)
                    if result:
                        cat, conf, reason, vision_data = result
                        _extract_and_emit(bd, cat, conf, 'vision', reason, vision_data)
                        continue  # skip text batch for this item

                # Not vision-eligible or vision failed -- add to text batch
                text_batch_data.append(bd)

            # Process remaining text items via text LLM
            if not text_batch_data:
                continue

            # Skip LLM if it has been failing repeatedly
            if llm_disabled:
                for bd in text_batch_data:
                    ext = os.path.splitext(bd['name'])[1].lower()
                    cat, conf, method = _classify_pc_item(str(bd['item_path']), ext_map,
                                                           bd['is_folder'], self.categories)
                    _extract_and_emit(bd, cat, conf, method or 'rule_fallback', 'LLM disabled after repeated failures')
                continue

            if len(text_batch_data) == 1:
                prompt = _prep_item(text_batch_data[0]['item_path'], text_batch_data[0]['is_folder'], text_batch_data[0]['name'])
                system = system_single
            else:
                sections = []
                for i, bd in enumerate(text_batch_data):
                    sections.append(f"[{i+1}] {_prep_item(bd['item_path'], bd['is_folder'], bd['name'])}")
                prompt = '\n---\n'.join(sections)
                system = system_batch

            classifications = [None] * len(text_batch_data)
            try:
                raw = _ollama_generate(prompt, system=system,
                                       url=settings['url'], model=settings['model'])
                parsed = _parse_llm(raw)
                if len(text_batch_data) == 1:
                    classifications[0] = parsed
                elif isinstance(parsed, list):
                    for i in range(min(len(parsed), len(text_batch_data))):
                        classifications[i] = parsed[i]
                else:
                    classifications[0] = parsed
                # Check if we got any valid results
                if any(c and c.get('category') for c in classifications):
                    consecutive_llm_failures = 0
                else:
                    consecutive_llm_failures += 1
            except Exception:
                consecutive_llm_failures += 1

            for i, bd in enumerate(text_batch_data):
                cat = conf = reason = method = None
                content_data = None
                ext = os.path.splitext(bd['name'])[1].lower()
                if classifications[i]:
                    try:
                        cat = classifications[i].get('category', '')
                        conf = int(classifications[i].get('confidence', 70))
                        reason = classifications[i].get('reason', '')
                        # Extract suggested_name from LLM response
                        raw_sug = classifications[i].get('suggested_name', '')
                        if raw_sug and isinstance(raw_sug, str):
                            cleaned = re.sub(r'[^a-zA-Z0-9_\- ]', '', raw_sug)[:60].strip()
                            if cleaned and len(cleaned) >= 3 and not _is_poisoned_name(cleaned):
                                content_data = {'suggested_name': cleaned}
                        if cat not in cat_names:
                            cat, conf, _ = _classify_pc_item(str(bd['item_path']), ext_map,
                                                              bd['is_folder'], self.categories)
                            reason = 'LLM returned unknown category — rule fallback'
                        method = 'llm'
                    except (ValueError, TypeError, AttributeError):
                        cat = None
                if cat is None:
                    cat, conf, method = _classify_pc_item(str(bd['item_path']), ext_map,
                                                           bd['is_folder'], self.categories)
                    reason = reason or 'rule_fallback'
                    method = 'rule_fallback'
                # ── Escalate low-confidence folders via evidence gathering ──
                if conf and conf < _EVIDENCE_CONFIDENCE_THRESHOLD and bd['is_folder']:
                    esc_result = _escalate_classification(
                        bd['name'], str(bd['item_path']),
                        {'category': cat, 'confidence': conf, 'method': method, 'detail': reason},
                        url=settings['url'], log_cb=self.log.emit, category_list=cat_names)
                    if esc_result.get('confidence', 0) > conf:
                        cat, conf = esc_result['category'], esc_result['confidence']
                        method = esc_result.get('method', method)
                        reason = esc_result.get('detail', reason)
                _extract_and_emit(bd, cat, conf, method, reason, content_data=content_data)

        # ── Flush cache and close ────────────────────────────────────────────
        cache.commit()
        if cache_hits > 0:
            self.log.emit(f"  [CACHE] {cache_hits}/{total} items loaded from scan cache (unchanged files)")
        cache.close()
        if hasattr(_extract_and_emit, '_face_db'):
            try:
                _extract_and_emit._face_db.save()
                fc = _extract_and_emit._face_db.face_count()
                self.log.emit(f"  [FACE] Database saved ({fc} known face(s))")
            except Exception:
                pass
            del _extract_and_emit._face_db
        _worker_audit_finish(
            "classify", "LLM file scan finished", trace_id,
            source_path=self.src_dir, count=total,
            status="cancelled" if self._cancelled else "complete",
        )
        self.finished.emit()


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATE BUILDER WIDGET — Visual token palette for rename templates
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# CATALOG LOOKUP WORKER — DeepSeek marketplace identification
# ══════════════════════════════════════════════════════════════════════════════

class CatalogLookupWorker(QThread):
    """Batch catalog lookup via the AI provider system (DeepSeek preferred).

    Takes a list of FileItem-like objects, runs them through the catalog
    lookup pipeline, and emits updated results with display_name + category.
    """
    result_ready  = pyqtSignal(dict)   # {index, display_name, category, marketplace, confidence}
    finished      = pyqtSignal()
    log           = pyqtSignal(str)
    progress      = pyqtSignal(int, int)

    def __init__(self, items: list, batch_size: int = 20):
        super().__init__()
        self.items = items
        self.batch_size = batch_size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from fileorganizer.providers import get_router
            from fileorganizer.catalog import lookup_batch
        except ImportError as e:
            self.log.emit(f"ERROR: Could not load catalog module: {e}")
            self.finished.emit()
            return

        router = get_router()
        provider = router.get_provider_for('catalog')

        if provider:
            self.log.emit(f"  Catalog lookup: {len(self.items)} items via {provider.name} ...")
        else:
            self.log.emit("  No AI provider available — using heuristic catalog lookup")

        total = len(self.items)

        def _progress(done, tot):
            self.progress.emit(done, tot)

        # Run batch lookup
        pairs = []
        for item in self.items:
            name = getattr(item, 'folder_name', None) or getattr(item, 'name', str(item))
            path = getattr(item, 'full_source_path', None) or getattr(item, 'full_src', '')
            pairs.append((name, path))

        results = lookup_batch(
            pairs,
            provider=provider,
            batch_size=self.batch_size,
            progress_cb=_progress,
        )

        for i, res in enumerate(results):
            if self._cancelled:
                self.log.emit(f"  Catalog lookup cancelled at {i}/{total}")
                break
            self.result_ready.emit({
                'index': i,
                'display_name': res.get('display_name', ''),
                'category':     res.get('category', ''),
                'marketplace':  res.get('marketplace', 'Unknown'),
                'asset_type':   res.get('asset_type', 'Other'),
                'confidence':   res.get('confidence', 0),
                'source':       res.get('source', 'heuristic'),
            })

        source_counts = {}
        for r in results:
            s = r.get('source', 'heuristic')
            source_counts[s] = source_counts.get(s, 0) + 1

        parts = [f"{v} {k}" for k, v in source_counts.items()]
        self.log.emit(f"  Catalog done: {total} items ({', '.join(parts)})")
        self.finished.emit()


# ══════════════════════════════════════════════════════════════════════════════
# ARCHIVE EXTRACTION WORKER — Extract design archives before organizing
# ══════════════════════════════════════════════════════════════════════════════

class ArchiveExtractionWorker(QThread):
    """Scan a directory for design archives and extract them.

    After extraction, the caller should re-scan the extraction destination
    to classify the newly extracted files.
    """
    result_ready = pyqtSignal(dict)   # {archive_path, dest_dir, extracted_files}
    finished     = pyqtSignal()
    log          = pyqtSignal(str)
    progress     = pyqtSignal(int, int)

    def __init__(self, source_dir: str, extract_dest: str = '',
                 delete_after: bool = False, recursive: bool = True,
                 limits=None):
        super().__init__()
        self.source_dir   = source_dir
        self.extract_dest = extract_dest  # Empty = extract beside archive
        self.delete_after = delete_after
        self.recursive    = recursive
        self.limits       = limits
        self._cancelled   = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from fileorganizer.archive_extractor import (
                ArchiveExtractionCancelled, ArchiveExtractionError,
                scan_archives_in_dir, extract_archive, get_archive_display_name,
            )
        except ImportError as e:
            self.log.emit(f"ERROR: archive_extractor not available: {e}")
            self.finished.emit()
            return

        self.log.emit(f"  Scanning for design archives in: {self.source_dir}")
        archives = scan_archives_in_dir(self.source_dir, recursive=self.recursive)

        if not archives:
            self.log.emit("  No design archives found.")
            self.finished.emit()
            return

        self.log.emit(f"  Found {len(archives)} design archive(s)")
        total = len(archives)

        for i, arc in enumerate(archives):
            if self._cancelled:
                self.log.emit(f"  Extraction cancelled at {i}/{total}")
                break

            self.progress.emit(i + 1, total)
            arch_path = arc['path']
            display   = get_archive_display_name(arch_path)
            self.log.emit(f"  Extracting [{i+1}/{total}]: {display}")

            # Destination: use explicit dest or create folder beside archive.
            # Extract into a sibling staging directory and promote it only after
            # all quota and cancellation checks have passed.
            staging_parent = self.extract_dest or os.path.dirname(arch_path)
            os.makedirs(staging_parent, exist_ok=True)
            dest = os.path.join(staging_parent, display)

            if os.path.lexists(dest):
                error = ArchiveExtractionError(
                    'destination_exists', f"output already exists: {dest}")
                self.log.emit(f"    Extraction blocked [{error.code}]: {error.message}")
                self.result_ready.emit({
                    'archive_path': arch_path,
                    'dest_dir': dest,
                    'extracted_files': [],
                    'display_name': display,
                    'status': 'blocked',
                    'error_code': error.code,
                    'error': error.message,
                })
                continue

            staging = tempfile.mkdtemp(prefix='.fo_extract_', dir=staging_parent)

            def _log_cb(msg):
                self.log.emit(msg)

            try:
                extracted = extract_archive(
                    arch_path,
                    staging,
                    log_cb=_log_cb,
                    limits=self.limits,
                    cancel_cb=lambda: self._cancelled,
                )
                if self._cancelled:
                    raise ArchiveExtractionCancelled()
                relative_files = [
                    os.path.relpath(path, staging) for path in extracted
                ]
                os.replace(staging, dest)
                staging = ''
                extracted = [os.path.join(dest, rel) for rel in relative_files]
            except ArchiveExtractionCancelled as e:
                shutil.rmtree(staging, ignore_errors=True)
                self.log.emit(f"    Extraction cancelled: {e.message}")
                self.result_ready.emit({
                    'archive_path': arch_path,
                    'dest_dir': dest,
                    'extracted_files': [],
                    'display_name': display,
                    'status': 'cancelled',
                    'error_code': e.code,
                    'error': e.message,
                })
                break
            except ArchiveExtractionError as e:
                shutil.rmtree(staging, ignore_errors=True)
                self.log.emit(f"    Extraction blocked [{e.code}]: {e.message}")
                self.result_ready.emit({
                    'archive_path': arch_path,
                    'dest_dir': dest,
                    'extracted_files': [],
                    'display_name': display,
                    'status': 'blocked',
                    'error_code': e.code,
                    'error': e.message,
                })
                continue
            except Exception as e:
                shutil.rmtree(staging, ignore_errors=True)
                self.log.emit(f"    Extraction failed: {e}")
                self.result_ready.emit({
                    'archive_path': arch_path,
                    'dest_dir': dest,
                    'extracted_files': [],
                    'display_name': display,
                    'status': 'failed',
                    'error_code': 'extraction_failed',
                    'error': str(e),
                })
                continue

            self.log.emit(f"    {len(extracted)} file(s) extracted to: {dest}")

            if self.delete_after and extracted and os.path.isfile(arch_path):
                try:
                    os.remove(arch_path)
                    self.log.emit(f"    Removed archive: {os.path.basename(arch_path)}")
                except OSError as e:
                    self.log.emit(f"    Could not remove archive: {e}")

            self.result_ready.emit({
                'archive_path':   arch_path,
                'dest_dir':       dest,
                'extracted_files': extracted,
                'display_name':   display,
                'status':          'extracted',
                'error_code':       '',
                'error':            '',
            })

        self.log.emit("  Archive extraction complete.")
        self.finished.emit()


# ═══ COMMUNITY CATALOG SYNC ══════════════════════════════════════════════════

_CATALOG_SYNC_FILE  = os.path.join(_APP_DATA_DIR, 'catalog_sync.json')
_CATALOG_GITHUB_API = 'https://api.github.com/repos/SysAdminDoc/FileOrganizer/releases/latest'
_CATALOG_ASSET_NAME = 'asset_fingerprints.json'
_CATALOG_METADATA_MAX_BYTES = 2 * 1024 * 1024
_CATALOG_ASSET_MAX_BYTES = 64 * 1024 * 1024
_CATALOG_READ_CHUNK_BYTES = 64 * 1024
_CATALOG_MAX_ASSETS = 250_000
_CATALOG_MAX_FILES = 5_000_000
_CATALOG_MAX_TEXT_CHARS = 4096
_CATALOG_SYNC_STATE_MAX_BYTES = 64 * 1024
_CATALOG_DOWNLOAD_PREFIX = '/SysAdminDoc/FileOrganizer/releases/download/'
_CATALOG_REDIRECT_HOSTS = frozenset({
    'github.com',
    'objects.githubusercontent.com',
    'release-assets.githubusercontent.com',
})
_CATALOG_JSON_TYPES = frozenset({'application/json'})
_CATALOG_ASSET_TYPES = frozenset({
    'application/json',
    'application/octet-stream',
    'text/json',
    'text/plain',
})


class CatalogSyncError(ValueError):
    """Controlled catalog download or schema failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CatalogSyncCancelled(CatalogSyncError):
    def __init__(self) -> None:
        super().__init__('cancelled', 'catalog synchronization was cancelled')


def load_catalog_sync_state() -> dict:
    """Load bounded, non-sensitive catalog diagnostics for settings/status UI."""
    try:
        if os.path.getsize(_CATALOG_SYNC_FILE) > _CATALOG_SYNC_STATE_MAX_BYTES:
            return {}
        state = json.loads(Path(_CATALOG_SYNC_FILE).read_text(encoding='utf-8'))
        return state if isinstance(state, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _write_catalog_sync_state(state: dict) -> None:
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    directory = os.path.dirname(_CATALOG_SYNC_FILE) or '.'
    handle, temporary_path = tempfile.mkstemp(
        prefix='.catalog_sync_', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if os.path.getsize(temporary_path) > _CATALOG_SYNC_STATE_MAX_BYTES:
            raise CatalogSyncError('state_too_large', 'catalog sync state exceeded its limit')
        os.replace(temporary_path, _CATALOG_SYNC_FILE)
        temporary_path = ''
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def _record_catalog_sync_status(status: str, message: str) -> bool:
    try:
        state = load_catalog_sync_state()
        state.update({
            'schema_version': 1,
            'last_attempt_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'last_status': str(status)[:64],
            'last_message': str(message)[:1024],
        })
        _write_catalog_sync_state(state)
        return True
    except (OSError, CatalogSyncError, TypeError, ValueError):
        return False


def _validate_catalog_download_url(url: str, expected_tag: str = '') -> str:
    """Accept only this repository's named GitHub release asset URL."""
    if not isinstance(url, str) or not url:
        raise CatalogSyncError('invalid_url', 'catalog asset URL is missing')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com':
        raise CatalogSyncError(
            'invalid_url', 'catalog asset URL must use the approved GitHub release host')
    if parsed.query or parsed.fragment:
        raise CatalogSyncError('invalid_url', 'catalog asset URL cannot contain a query or fragment')

    path = unquote(parsed.path)
    if not path.startswith(_CATALOG_DOWNLOAD_PREFIX):
        raise CatalogSyncError('invalid_url', 'catalog asset URL has an unapproved release path')
    relative = path[len(_CATALOG_DOWNLOAD_PREFIX):]
    tag, separator, filename = relative.partition('/')
    if not tag or separator != '/' or filename != _CATALOG_ASSET_NAME:
        raise CatalogSyncError('invalid_url', 'catalog asset URL does not name the approved asset')
    if expected_tag and tag != expected_tag:
        raise CatalogSyncError('invalid_url', 'catalog asset URL does not match the release tag')
    return url


def _validate_catalog_digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', value):
        raise CatalogSyncError(
            'missing_digest', 'catalog release asset has no valid SHA-256 digest')
    return value.split(':', 1)[1].lower()


def _select_catalog_release_asset(release: dict) -> tuple[str, str]:
    matches = [
        asset for asset in release.get('assets', [])
        if asset.get('name') == _CATALOG_ASSET_NAME
    ]
    if not matches:
        raise CatalogSyncError('missing_asset', 'catalog release has no fingerprint asset')
    if len(matches) != 1:
        raise CatalogSyncError('ambiguous_asset', 'catalog release has duplicate fingerprint assets')

    asset = matches[0]
    size = asset.get('size')
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or size > _CATALOG_ASSET_MAX_BYTES
    ):
        raise CatalogSyncError('invalid_asset_size', 'catalog release asset has an invalid size')
    tag = release.get('tag_name', '')
    url = _validate_catalog_download_url(asset.get('browser_download_url', ''), tag)
    return url, _validate_catalog_digest(asset.get('digest', ''))


def _verify_catalog_digest(raw: bytes, expected_digest: str) -> str:
    actual_digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise CatalogSyncError('digest_mismatch', 'catalog asset SHA-256 digest mismatch')
    return actual_digest


def _validate_catalog_metadata_response_url(response) -> None:
    get_url = getattr(response, 'geturl', None)
    final_url = get_url() if callable(get_url) else _CATALOG_GITHUB_API
    parsed = urlsplit(final_url) if isinstance(final_url, str) else None
    expected = urlsplit(_CATALOG_GITHUB_API)
    if (
        parsed is None
        or parsed.scheme != 'https'
        or parsed.hostname != expected.hostname
        or parsed.path != expected.path
        or parsed.query
        or parsed.fragment
    ):
        raise CatalogSyncError(
            'invalid_redirect', 'catalog release metadata left the approved GitHub API URL')


def _validate_catalog_response_url(response, requested_url: str) -> None:
    """Fail closed if an HTTP redirect leaves GitHub's release asset hosts."""
    get_url = getattr(response, 'geturl', None)
    final_url = get_url() if callable(get_url) else requested_url
    if not isinstance(final_url, str):
        raise CatalogSyncError('invalid_redirect', 'catalog download returned an invalid URL')
    parsed = urlsplit(final_url)
    if parsed.scheme != 'https' or parsed.hostname not in _CATALOG_REDIRECT_HOSTS:
        raise CatalogSyncError('invalid_redirect', 'catalog download redirected to an unapproved host')


def _response_media_type(response) -> str:
    raw = response.headers.get('Content-Type', '')
    return raw.split(';', 1)[0].strip().lower()


def _read_bounded_http_body(
    response,
    *,
    max_bytes: int,
    media_types: frozenset[str],
    cancel_cb=None,
) -> bytes:
    """Read an HTTP body without retaining more than ``max_bytes`` bytes."""
    media_type = _response_media_type(response)
    if media_type not in media_types:
        raise CatalogSyncError(
            'invalid_content_type',
            f"catalog response has unsupported content type {media_type or '(missing)'}",
        )

    content_length = response.headers.get('Content-Length')
    if content_length not in (None, ''):
        try:
            declared_length = int(content_length)
        except (TypeError, ValueError) as exc:
            raise CatalogSyncError(
                'invalid_content_length', 'catalog response has an invalid Content-Length') from exc
        if declared_length < 0 or declared_length > max_bytes:
            raise CatalogSyncError(
                'response_too_large', f'catalog response exceeds the {max_bytes}-byte limit')

    body = bytearray()
    while len(body) < max_bytes:
        if cancel_cb is not None and cancel_cb():
            raise CatalogSyncCancelled()
        remaining = max_bytes - len(body)
        chunk = response.read(min(_CATALOG_READ_CHUNK_BYTES, remaining))
        if not chunk:
            return bytes(body)
        if not isinstance(chunk, bytes):
            raise CatalogSyncError('invalid_response', 'catalog response returned non-byte data')
        if len(chunk) > remaining:
            raise CatalogSyncError(
                'response_too_large', f'catalog response exceeds the {max_bytes}-byte limit')
        body.extend(chunk)

    if cancel_cb is not None and cancel_cb():
        raise CatalogSyncCancelled()
    if response.read(1):
        raise CatalogSyncError(
            'response_too_large', f'catalog response exceeds the {max_bytes}-byte limit')
    return bytes(body)


def _decode_catalog_json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CatalogSyncError('invalid_json', f'malformed {label}: {exc}') from exc
    if not isinstance(value, dict):
        raise CatalogSyncError('invalid_schema', f'{label} must be a JSON object')
    return value


def _validate_release_metadata(release: dict) -> None:
    assets = release.get('assets')
    if not isinstance(assets, list) or len(assets) > 10_000:
        raise CatalogSyncError('invalid_schema', 'release metadata has an invalid assets list')
    if any(not isinstance(asset, dict) for asset in assets):
        raise CatalogSyncError('invalid_schema', 'release metadata contains an invalid asset')
    for field in ('published_at', 'tag_name'):
        value = release.get(field, '')
        if not isinstance(value, str) or len(value) > 512:
            raise CatalogSyncError('invalid_schema', f'release metadata field {field} is invalid')


def _validate_catalog_payload(payload: dict) -> None:
    schema_version = payload.get('schema_version')
    if schema_version != 2:
        raise CatalogSyncError(
            'unsupported_schema', f'unsupported catalog schema version: {schema_version!r}')
    assets = payload.get('assets')
    if not isinstance(assets, list) or len(assets) > _CATALOG_MAX_ASSETS:
        raise CatalogSyncError('invalid_schema', 'catalog payload has an invalid assets list')
    asset_count = payload.get('asset_count', len(assets))
    if (
        not isinstance(asset_count, int)
        or isinstance(asset_count, bool)
        or asset_count != len(assets)
    ):
        raise CatalogSyncError('invalid_schema', 'catalog payload asset count does not match')

    total_files = 0
    for asset in assets:
        if not isinstance(asset, dict):
            raise CatalogSyncError('invalid_schema', 'catalog payload contains an invalid asset')
        fingerprint = asset.get('folder_fingerprint')
        if not isinstance(fingerprint, str) or not re.fullmatch(
            r'[0-9a-fA-F]{64}', fingerprint
        ):
            raise CatalogSyncError('invalid_schema', 'catalog asset has an invalid fingerprint')
        for field in ('clean_name', 'category', 'marketplace', 'disk_name', 'preview_image'):
            value = asset.get(field, '')
            if not isinstance(value, str) or len(value) > _CATALOG_MAX_TEXT_CHARS or '\x00' in value:
                raise CatalogSyncError(
                    'invalid_schema', f'catalog asset field {field} is invalid')
        confidence = asset.get('confidence', 0)
        if not isinstance(confidence, int) or isinstance(confidence, bool) or not 0 <= confidence <= 100:
            raise CatalogSyncError('invalid_schema', 'catalog asset confidence is invalid')
        for field in ('file_count', 'total_bytes'):
            value = asset.get(field, 0)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2**63 - 1:
                raise CatalogSyncError(
                    'invalid_schema', f'catalog asset field {field} is invalid')
        files = asset.get('files', [])
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise CatalogSyncError('invalid_schema', 'catalog asset has an invalid files list')
        total_files += len(files)
        if total_files > _CATALOG_MAX_FILES:
            raise CatalogSyncError('invalid_schema', 'catalog payload has too many file records')
        for file_record in files:
            relative_path = file_record.get('p')
            digest = file_record.get('h')
            size = file_record.get('s')
            key_file = file_record.get('k')
            if (
                not isinstance(relative_path, str)
                or not relative_path
                or len(relative_path) > _CATALOG_MAX_TEXT_CHARS
                or '\x00' in relative_path
            ):
                raise CatalogSyncError('invalid_schema', 'catalog file path is invalid')
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
                raise CatalogSyncError('invalid_schema', 'catalog file digest is invalid')
            if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= 2**63 - 1:
                raise CatalogSyncError('invalid_schema', 'catalog file size is invalid')
            if key_file not in (0, 1, False, True):
                raise CatalogSyncError('invalid_schema', 'catalog project-file flag is invalid')


class MarketplaceUpdateWorker(QThread):
    """Bounded, throttled marketplace update check for completed folder scans."""

    log = pyqtSignal(str)
    finished = pyqtSignal(object)  # {checked, skipped, updates, error?}

    def __init__(self, folder_names, *, force: bool = False, parent=None):
        super().__init__(parent)
        self._folder_names = list(folder_names or [])
        self._force = force

    def run(self):
        try:
            from marketplace_enrich import check_for_updates

            summary = check_for_updates(self._folder_names, force=self._force)
            self.log.emit(
                f"Marketplace update check: {summary.get('checked', 0)} checked, "
                f"{len(summary.get('updates', []))} update(s) found"
            )
            self.finished.emit(summary)
        except Exception as exc:
            self.log.emit(f"Marketplace update check skipped: {type(exc).__name__}")
            self.finished.emit({
                'checked': 0,
                'skipped': 0,
                'updates': [],
                'error': str(exc),
            })


class CrossLibraryScanWorker(QThread):
    """Hash independent library roots without blocking the Qt event loop."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # list[CrossLibraryDuplicateGroup] or error dict

    def __init__(self, roots, *, depth: int = 1, parent=None):
        super().__init__(parent)
        self._roots = list(roots or [])
        self._depth = depth
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from fileorganizer.cross_library_dedup import (
                CrossLibraryScanCancelled,
                scan_cross_library,
            )

            groups = scan_cross_library(
                self._roots,
                depth=self._depth,
                progress_cb=self.progress.emit,
                cancel_cb=lambda: self._cancelled,
            )
            self.finished.emit(groups)
        except CrossLibraryScanCancelled:
            self.progress.emit("Cross-library scan cancelled")
            self.finished.emit([])
        except Exception as exc:
            self.progress.emit(f"Cross-library scan failed: {type(exc).__name__}")
            self.finished.emit({'error': str(exc)})


class VersionDedupScanWorker(QThread):
    """Hash library folders and discover differing same-ID versions."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # {marketplace_id: candidates} or error dict

    def __init__(self, roots, *, depth: int = 1, parent=None):
        super().__init__(parent)
        self._roots = list(roots or [])
        self._depth = depth
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from fileorganizer.version_dedup import scan_version_groups

            groups = scan_version_groups(
                self._roots,
                depth=self._depth,
                progress_cb=self.progress.emit,
                cancel_cb=lambda: self._cancelled,
            )
            self.finished.emit(groups)
        except Exception as exc:
            self.progress.emit(f"Version scan failed: {type(exc).__name__}")
            self.finished.emit({'error': str(exc)})


class CatalogSyncWorker(QThread):
    """
    Background worker that checks GitHub Releases for a newer community
    asset_fingerprints.json and imports it into the local asset_fingerprints.db.

    Runs silently on startup; only logs on meaningful events (update found,
    error, or up-to-date confirmation).
    """

    log      = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # (success, summary_message)

    def __init__(self, *, enabled: bool = True) -> None:
        super().__init__()
        self._enabled = enabled
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self):
        import socket
        import urllib.error
        import urllib.request

        try:
            if not self._enabled:
                message = "Catalog sync disabled; using the local catalog"
                _record_catalog_sync_status('disabled', message)
                self.finished.emit(True, message)
                return

            # ── Load last-sync state ─────────────────────────────────────────
            state = load_catalog_sync_state()
            last_published = state.get('last_published_at', '')
            last_etag      = state.get('last_etag', '')
            last_modified  = state.get('last_modified', '')
            last_published = last_published if isinstance(last_published, str) else ''
            last_etag = last_etag if isinstance(last_etag, str) else ''
            last_modified = last_modified if isinstance(last_modified, str) else ''

            # ── Fetch latest release metadata (unauthenticated, 60 req/hr) ──
            # Use conditional headers so GitHub returns 304 Not Modified when
            # the release hasn't changed — that costs zero against the
            # rate-limit bucket and skips JSON parsing entirely.
            headers = {'Accept': 'application/vnd.github+json',
                       'User-Agent': 'FileOrganizer-CatalogSync/1.0'}
            if last_etag:
                headers['If-None-Match'] = last_etag
            elif last_modified:
                headers['If-Modified-Since'] = last_modified
            req = urllib.request.Request(_CATALOG_GITHUB_API, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    _validate_catalog_metadata_response_url(resp)
                    response_etag = resp.headers.get('ETag', '')
                    response_modified = resp.headers.get('Last-Modified', '')
                    response_etag = (
                        response_etag[:512] if isinstance(response_etag, str) else '')
                    response_modified = (
                        response_modified[:512]
                        if isinstance(response_modified, str) else '')
                    release_raw = _read_bounded_http_body(
                        resp,
                        max_bytes=_CATALOG_METADATA_MAX_BYTES,
                        media_types=_CATALOG_JSON_TYPES,
                        cancel_cb=lambda: self._cancelled,
                    )
                    release = _decode_catalog_json(release_raw, 'release metadata')
                    _validate_release_metadata(release)
            except urllib.error.HTTPError as exc:
                # 304 Not Modified — the release hasn't changed since last sync.
                if exc.code == 304:
                    message = "Catalog up-to-date (304 Not Modified)"
                    _record_catalog_sync_status('up_to_date', message)
                    self.finished.emit(True, message)
                    return
                message = f"Catalog sync skipped (HTTP {exc.code}: {exc.reason})"
                _record_catalog_sync_status('http_unavailable', message)
                self.finished.emit(True, message)
                return
            except urllib.error.URLError as exc:
                message = f"Catalog sync skipped (offline: {exc.reason}); using local catalog"
                _record_catalog_sync_status('offline', message)
                self.finished.emit(True, message)
                return
            except socket.timeout:
                message = "Catalog sync skipped (release metadata timeout); using local catalog"
                _record_catalog_sync_status('offline', message)
                self.finished.emit(True, message)
                return
            published_at = release.get('published_at', '')
            tag          = release.get('tag_name', '')

            if published_at and published_at <= last_published:
                # Refresh ETag/Last-Modified so we don't keep re-fetching.
                self._persist_sync_state(
                    last_published or published_at, tag,
                    response_etag, response_modified, 0, 0,
                    status='up_to_date',
                )
                self.finished.emit(True, f"Catalog up-to-date ({tag})")
                return

            # ── Find the fingerprint JSON asset ──────────────────────────────
            download_url, expected_digest = _select_catalog_release_asset(release)

            # ── Download ─────────────────────────────────────────────────────
            self.log.emit(f"Catalog: downloading {_CATALOG_ASSET_NAME} from {tag}…")
            dl_req = urllib.request.Request(
                download_url,
                headers={
                    'Accept': 'application/json, application/octet-stream',
                    'User-Agent': 'FileOrganizer-CatalogSync/1.0',
                }
            )
            try:
                with urllib.request.urlopen(dl_req, timeout=30) as resp:
                    _validate_catalog_response_url(resp, download_url)
                    raw = _read_bounded_http_body(
                        resp,
                        max_bytes=_CATALOG_ASSET_MAX_BYTES,
                        media_types=_CATALOG_ASSET_TYPES,
                        cancel_cb=lambda: self._cancelled,
                    )
            except (urllib.error.URLError, socket.timeout) as exc:
                reason = getattr(exc, 'reason', exc)
                message = f"Catalog sync skipped (download failed: {reason}); using local catalog"
                _record_catalog_sync_status('offline', message)
                self.finished.emit(True, message)
                return

            content_sha256 = _verify_catalog_digest(raw, expected_digest)
            json_data = _decode_catalog_json(raw, 'asset payload')
            _validate_catalog_payload(json_data)

            # ── Import via asset_db module ────────────────────────────────────
            new_assets, skipped = self._import_catalog(json_data)

            # ── Persist sync state ───────────────────────────────────────────
            self._persist_sync_state(
                published_at, tag, response_etag, response_modified,
                new_assets, skipped, content_sha256=content_sha256,
            )

            msg = (f"Catalog updated from {tag}: "
                   f"+{new_assets} new assets, {skipped} already known")
            self.log.emit(f"Catalog: {msg}")
            self.finished.emit(True, msg)

        except CatalogSyncCancelled:
            message = "Catalog sync skipped (cancelled); using local catalog"
            _record_catalog_sync_status('cancelled', message)
            self.finished.emit(True, message)
        except CatalogSyncError as exc:
            message = f"Catalog sync blocked [{exc.code}]: {exc}"
            _record_catalog_sync_status('blocked', message)
            self.finished.emit(False, message)
        except Exception as exc:
            message = f"Catalog sync error: {exc}"
            _record_catalog_sync_status('error', message)
            self.finished.emit(False, message)

    @staticmethod
    def _import_catalog(json_data: dict) -> tuple[int, int]:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'asset_fingerprints.db')
        db_mod_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'asset_db.py')
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location('asset_db', db_mod_path)
        if spec is None or spec.loader is None:
            raise CatalogSyncError('import_unavailable', 'asset database importer is unavailable')
        asset_db_mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(asset_db_mod)
        return asset_db_mod.import_community_json_atomic(json_data, db_path)

    @staticmethod
    def _persist_sync_state(published_at: str, tag: str,
                            etag: str, last_modified: str,
                            new_assets: int, skipped: int,
                            *, content_sha256: str = '',
                            status: str = 'updated') -> None:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        state = load_catalog_sync_state()
        state.update({
            'schema_version':     1,
            'last_published_at': published_at,
            'last_tag':          tag,
            'last_etag':         etag,
            'last_modified':     last_modified,
            'last_attempt_at':   now,
            'last_success_at':   now,
            'last_status':       status,
            'last_message':      '',
            'new_assets':        new_assets,
            'skipped':           skipped,
        })
        if content_sha256:
            state['content_sha256'] = content_sha256
        _write_catalog_sync_state(state)

