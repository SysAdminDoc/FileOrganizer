"""Optional IPTC AI provenance written to XMP sidecar files.

ExifTool is deliberately treated as an optional capability.  Classification
and move operations must remain successful when either PyExifTool or the
ExifTool executable is absent, too old, or unable to write a particular
sidecar.  The writer never edits the source asset: it creates or updates the
same-basename ``.xmp`` companion instead.
"""
from __future__ import annotations

import getpass
import importlib
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from fileorganizer.path_safety import PathSafetyError, validate_path


MIN_EXIFTOOL_VERSION = (12, 15)
PYEXIFTOOL_VERSION = "0.5.6"
SYSTEM_USED = "FileOrganizer v8.x"
SIDECAR_SUFFIX = ".xmp"

AI_SYSTEM_TAG = "Iptc4xmpExt:AISystemUsed"
AI_PROMPT_TAG = "Iptc4xmpExt:AIPromptInformation"
AI_WRITER_TAG = "Iptc4xmpExt:AIPromptWriterName"
SUBJECT_TAG = "XMP-dc:Subject"
RATING_TAG = "XMP-xmp:Rating"
CATEGORY_TAG = "photoshop:Category"

_STATUS_WRITTEN = "written"
_STATUS_UNAVAILABLE = "unavailable"
_STATUS_SKIPPED = "skipped"
_STATUS_FAILED = "failed"
_MAX_TEXT = 4000
_MAX_SUBJECTS = 40
_VERSION_RE = re.compile(r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?(?!\d)")


@dataclass(frozen=True)
class XmpSidecarResult:
    """Outcome of one optional sidecar attempt."""

    status: str
    sidecar_path: str
    detail: str = ""
    tags: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == _STATUS_WRITTEN


def sidecar_path(asset_path: str | os.PathLike[str]) -> Path:
    """Return the conventional same-basename XMP sidecar path."""
    asset = Path(os.path.abspath(os.fspath(asset_path)))
    return asset.with_suffix(SIDECAR_SUFFIX)


def parse_exiftool_version(value: str) -> tuple[int, ...] | None:
    """Parse the numeric version emitted by ``exiftool -ver``."""
    match = _VERSION_RE.search(str(value or ""))
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _version_at_least(version: tuple[int, ...] | None, minimum: tuple[int, ...]) -> bool:
    if version is None:
        return False
    width = max(len(version), len(minimum))
    return tuple(version) + (0,) * (width - len(version)) >= tuple(minimum) + (0,) * (width - len(minimum))


def _resolve_exiftool(executable: str | os.PathLike[str] | None = None) -> str | None:
    if executable:
        supplied = os.fspath(executable)
        if os.path.isfile(supplied):
            return os.path.abspath(supplied)
        resolved = shutil.which(supplied)
        if resolved:
            return resolved
    for candidate in ("exiftool.exe", "exiftool"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def find_exiftool() -> str | None:
    """Find ExifTool on PATH without guessing at private install locations."""
    return _resolve_exiftool()


def _load_exiftool_module() -> Any | None:
    try:
        return importlib.import_module("exiftool")
    except (ImportError, ModuleNotFoundError):
        return None


def _run_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 3,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def _query_exiftool_version(path: str) -> tuple[str, tuple[int, ...] | None, str]:
    try:
        completed = subprocess.run([path, "-ver"], **_run_kwargs())
    except (OSError, subprocess.SubprocessError) as exc:
        return "", None, f"could not query ExifTool: {exc}"
    raw = (completed.stdout or completed.stderr or "").strip()
    version = raw.splitlines()[0].strip() if raw else ""
    parsed = parse_exiftool_version(version)
    if completed.returncode != 0:
        return version, parsed, f"ExifTool version query exited {completed.returncode}"
    if parsed is None:
        return version, None, "ExifTool returned an unparseable version"
    return version, parsed, ""


def probe_exiftool(
    executable: str | os.PathLike[str] | None = None,
    *,
    exiftool_module: Any | None = None,
) -> dict[str, Any]:
    """Return a deterministic local health record for the sidecar writer."""
    path = _resolve_exiftool(executable)
    if not path:
        return {
            "available": False,
            "path": "",
            "version": "",
            "reason": "ExifTool >=12.15 was not found on PATH.",
        }

    version, parsed, query_error = _query_exiftool_version(path)
    if query_error:
        return {
            "available": False,
            "path": path,
            "version": version,
            "reason": query_error,
        }
    if not _version_at_least(parsed, MIN_EXIFTOOL_VERSION):
        return {
            "available": False,
            "path": path,
            "version": version,
            "reason": f"ExifTool {version or 'unknown'} is older than the required 12.15.",
        }

    module = exiftool_module if exiftool_module is not None else _load_exiftool_module()
    if module is None:
        return {
            "available": False,
            "path": path,
            "version": version,
            "reason": f"PyExifTool {PYEXIFTOOL_VERSION} is not installed.",
        }
    if not callable(getattr(module, "ExifTool", None)):
        return {
            "available": False,
            "path": path,
            "version": version,
            "reason": "PyExifTool does not expose ExifTool.",
        }
    return {
        "available": True,
        "path": path,
        "version": version,
        "reason": "ExifTool and PyExifTool are available.",
    }


def _clean_text(value: Any, *, limit: int = _MAX_TEXT) -> str:
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"[\r\n\t]+", " ", text).strip()
    return text[:limit]


def _normalise_subjects(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = _clean_text(value, limit=256)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= _MAX_SUBJECTS:
            break
    return result


def confidence_rating(confidence: Any) -> int:
    """Map a 0–100 confidence value to the XMP 1–5 star range."""
    try:
        value = float(confidence)
    except (TypeError, ValueError, OverflowError):
        value = 0.0
    if not math.isfinite(value):
        value = 0.0
    value = max(0.0, min(100.0, value))
    return max(1, min(5, int(math.ceil(value / 20.0))))


def build_xmp_tags(
    *,
    category: str,
    confidence: Any,
    prompt_information: str,
    prompt_writer_name: str | None = None,
    subjects: Iterable[Any] | None = None,
    system_used: str = SYSTEM_USED,
) -> dict[str, Any]:
    """Build bounded logical XMP fields before handing them to ExifTool."""
    category_text = _clean_text(category, limit=256) or "Unknown"
    subject_values = _normalise_subjects(subjects)
    if category_text.casefold() not in {value.casefold() for value in subject_values}:
        subject_values.insert(0, category_text)
    writer = _clean_text(prompt_writer_name, limit=256) or "FileOrganizer"
    return {
        AI_SYSTEM_TAG: _clean_text(system_used, limit=256) or SYSTEM_USED,
        AI_PROMPT_TAG: _clean_text(prompt_information),
        AI_WRITER_TAG: writer,
        SUBJECT_TAG: subject_values,
        RATING_TAG: confidence_rating(confidence),
        CATEGORY_TAG: category_text,
    }


def _tool_tag(tag: str) -> str:
    # ExifTool's family-1 group prefix is XMP-iptcExt even though the XML
    # namespace and IPTC specification call it Iptc4xmpExt.
    if tag.startswith("Iptc4xmpExt:"):
        return "XMP-iptcExt:" + tag.split(":", 1)[1]
    return tag


def _tag_arguments(tags: Mapping[str, Any]) -> list[str]:
    args: list[str] = []
    for logical_name in (AI_SYSTEM_TAG, AI_PROMPT_TAG, AI_WRITER_TAG, RATING_TAG, CATEGORY_TAG):
        value = tags.get(logical_name, "")
        args.append(f"-{_tool_tag(logical_name)}={_clean_text(value, limit=256)}")
    for subject in tags.get(SUBJECT_TAG, ()):
        args.append(f"-{_tool_tag(SUBJECT_TAG)}+={_clean_text(subject, limit=256)}")
    return args


def _result(status: str, path: Path, detail: str = "", tags: Mapping[str, Any] | None = None) -> XmpSidecarResult:
    return XmpSidecarResult(status, str(path), detail[:512], dict(tags or {}))


def write_xmp_sidecar(
    asset_path: str | os.PathLike[str],
    *,
    category: str,
    confidence: Any,
    prompt_information: str = "",
    prompt: str | None = None,
    prompt_writer_name: str | None = None,
    subjects: Iterable[Any] | None = None,
    system_used: str = SYSTEM_USED,
    exiftool_path: str | os.PathLike[str] | None = None,
    exiftool_module: Any | None = None,
) -> XmpSidecarResult:
    """Create or update a sidecar without mutating the source asset.

    Missing tools, unsafe paths, and ExifTool errors are returned as a status
    so callers can keep the classification/move operation successful.
    """
    asset = Path(os.path.abspath(os.fspath(asset_path)))
    sidecar = sidecar_path(asset)
    try:
        validate_path(asset)
        if not asset.is_file():
            return _result(_STATUS_SKIPPED, sidecar, "source is not a regular file")
        validate_path(sidecar, require_exists=False)
    except (OSError, PathSafetyError, ValueError) as exc:
        return _result(_STATUS_SKIPPED, sidecar, f"sidecar path rejected: {exc}")

    if asset.suffix.casefold() == SIDECAR_SUFFIX:
        return _result(_STATUS_SKIPPED, sidecar, "XMP files do not receive nested sidecars")

    if prompt is not None and not prompt_information:
        prompt_information = prompt
    tags = build_xmp_tags(
        category=category,
        confidence=confidence,
        prompt_information=prompt_information,
        prompt_writer_name=prompt_writer_name,
        subjects=subjects,
        system_used=system_used,
    )
    health = probe_exiftool(exiftool_path, exiftool_module=exiftool_module)
    if not health.get("available"):
        return _result(_STATUS_UNAVAILABLE, sidecar, str(health.get("reason", "unavailable")), tags)

    module = exiftool_module if exiftool_module is not None else _load_exiftool_module()
    tool_type = getattr(module, "ExifTool", None)
    if not callable(tool_type):
        return _result(_STATUS_UNAVAILABLE, sidecar, "PyExifTool ExifTool class is unavailable", tags)

    arguments = _tag_arguments(tags)
    try:
        with tool_type(executable=str(health["path"])) as tool:
            if sidecar.exists():
                tool.execute("-overwrite_original", *arguments, str(sidecar))
            else:
                # ExifTool creates XMP files from scratch with -o; the source
                # asset is only read and is never rewritten.
                tool.execute("-o", str(sidecar), *arguments, str(asset))
    except Exception as exc:  # PyExifTool exposes several version-specific errors.
        return _result(_STATUS_FAILED, sidecar, f"ExifTool sidecar write failed: {exc}", tags)

    if not sidecar.is_file():
        return _result(_STATUS_FAILED, sidecar, "ExifTool reported success but no sidecar was created", tags)
    return _result(_STATUS_WRITTEN, sidecar, "XMP sidecar written", tags)


def _default_writer_name() -> str:
    try:
        return _clean_text(getpass.getuser(), limit=256) or "FileOrganizer"
    except (OSError, RuntimeError):
        return "FileOrganizer"


def write_classification_sidecar(
    asset_path: str | os.PathLike[str],
    *,
    category: str,
    confidence: Any,
    method: str = "",
    detail: str = "",
    metadata: Mapping[str, Any] | None = None,
    prompt_writer_name: str | None = None,
    **kwargs: Any,
) -> XmpSidecarResult:
    """Write the common classification provenance shape used by workers."""
    metadata = metadata or {}
    subject_values: list[Any] = [category]
    for key in ("keywords", "project_names", "title", "genre", "artist", "album"):
        value = metadata.get(key)
        if isinstance(value, (list, tuple, set)):
            subject_values.extend(value)
        elif value:
            subject_values.append(value)
    prompt_information = (
        "FileOrganizer classification; "
        f"category={_clean_text(category, limit=256) or 'Unknown'}; "
        f"confidence={confidence_rating(confidence)}/5; "
        f"method={_clean_text(method, limit=128) or 'unknown'}; "
        f"evidence={_clean_text(detail, limit=3000)}"
    )
    return write_xmp_sidecar(
        asset_path,
        category=category,
        confidence=confidence,
        prompt_information=prompt_information,
        prompt_writer_name=prompt_writer_name or _default_writer_name(),
        subjects=subject_values,
        **kwargs,
    )


__all__ = [
    "AI_PROMPT_TAG",
    "AI_SYSTEM_TAG",
    "AI_WRITER_TAG",
    "CATEGORY_TAG",
    "MIN_EXIFTOOL_VERSION",
    "PYEXIFTOOL_VERSION",
    "RATING_TAG",
    "SIDECAR_SUFFIX",
    "SUBJECT_TAG",
    "SYSTEM_USED",
    "XmpSidecarResult",
    "build_xmp_tags",
    "confidence_rating",
    "find_exiftool",
    "parse_exiftool_version",
    "probe_exiftool",
    "sidecar_path",
    "write_classification_sidecar",
    "write_xmp_sidecar",
]
