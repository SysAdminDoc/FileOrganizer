"""Optional local OCR for screenshots and scanned PDF imports.

OCR is deliberately subprocess-based so FileOrganizer does not need to ship a
large native OCR runtime.  Tesseract and Poppler are discovered at runtime;
when either optional tool is unavailable the caller simply receives no OCR
text.  All subprocess inputs are argument lists, bounded by time and size, and
never executed through a shell.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fileorganizer.config import _APP_DATA_DIR


_OCR_SETTINGS_FILE = os.path.join(_APP_DATA_DIR, "ocr_settings.json")
_OCR_DEFAULTS = {
    "enabled": True,
    "image_mode": "smart",  # smart=screenshots, always=all supported images
    "language": "eng",
    "max_chars": 4000,
    "timeout": 20,
    "max_pdf_pages": 3,
}

_IMAGE_EXTENSIONS = {
    ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif",
    ".tiff", ".webp",
}
_MAX_INPUT_BYTES = 50 * 1024 * 1024
_MAX_RENDERED_PAGE_BYTES = 25 * 1024 * 1024
_SCREENSHOT_WORDS = (
    "screenshot", "screen_shot", "screen capture", "screen_capture",
    "screen-grab", "screen_grab", "snipping", "snip", "capture",
    "scanned", "scan", "receipt", "invoice",
)


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _validate_settings(settings: dict | None) -> dict:
    raw = settings or {}
    mode = str(raw.get("image_mode", _OCR_DEFAULTS["image_mode"])).strip().lower()
    if mode not in {"smart", "always"}:
        mode = _OCR_DEFAULTS["image_mode"]
    language = str(raw.get("language", _OCR_DEFAULTS["language"])).strip()
    if not re.fullmatch(r"[A-Za-z0-9_+\-]+", language):
        language = _OCR_DEFAULTS["language"]
    return {
        "enabled": bool(raw.get("enabled", _OCR_DEFAULTS["enabled"])),
        "image_mode": mode,
        "language": language[:64],
        "max_chars": _bounded_int(raw.get("max_chars"), 4000, 200, 20000),
        "timeout": _bounded_int(raw.get("timeout"), 20, 5, 120),
        "max_pdf_pages": _bounded_int(raw.get("max_pdf_pages"), 3, 1, 10),
    }


def load_ocr_settings() -> dict:
    """Load validated OCR preferences from the app-data directory."""
    try:
        with open(_OCR_SETTINGS_FILE, "r", encoding="utf-8") as handle:
            return _validate_settings(json.load(handle))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return dict(_OCR_DEFAULTS)


def save_ocr_settings(settings: dict) -> dict:
    """Persist validated OCR preferences and return the stored values."""
    validated = _validate_settings(settings)
    temp_name = ""
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix="ocr_settings.", suffix=".tmp", dir=_APP_DATA_DIR,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(validated, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, _OCR_SETTINGS_FILE)
    except OSError:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
    return validated


def _configured_binary(env_name: str) -> str | None:
    value = os.environ.get(env_name, "").strip()
    if value and Path(value).is_file():
        return value
    return None


def find_tesseract() -> str | None:
    """Return the configured or PATH-discovered Tesseract executable."""
    configured = _configured_binary("FILEORGANIZER_TESSERACT")
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for root_name in ("PROGRAMFILES", "LOCALAPPDATA"):
            root = os.environ.get(root_name, "")
            if root:
                candidate = Path(root) / "Tesseract-OCR" / "tesseract.exe"
                if candidate.is_file():
                    return str(candidate)
    return None


def find_pdf_renderer() -> str | None:
    """Return the optional Poppler ``pdftoppm`` executable."""
    configured = _configured_binary("FILEORGANIZER_PDF_RENDERER")
    if configured:
        return configured
    return shutil.which("pdftoppm")


def tesseract_available() -> bool:
    return find_tesseract() is not None


def pdf_ocr_available() -> bool:
    return find_tesseract() is not None and find_pdf_renderer() is not None


def is_likely_screenshot(filepath: str | os.PathLike[str]) -> bool:
    """Return whether a filename strongly suggests a screenshot or scan."""
    stem = Path(filepath).stem.casefold().replace("-", "_")
    compact = re.sub(r"[^a-z0-9_ ]+", " ", stem)
    return any(word in compact for word in _SCREENSHOT_WORDS)


def _sanitize_text(text: str, max_chars: int) -> str:
    # OCR is untrusted file content.  Keep it useful for classification while
    # removing common prompt-structure characters and bounding its size.
    text = re.sub(r"[{}\[\]<>]", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _subprocess_kwargs() -> dict:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def _safe_input(path: str | os.PathLike[str]) -> bool:
    try:
        candidate = Path(path)
        size = candidate.stat().st_size
        return candidate.is_file() and 0 < size <= _MAX_INPUT_BYTES
    except OSError:
        return False


def _run_tesseract(
    filepath: str | os.PathLike[str],
    *,
    tesseract: str,
    language: str,
    max_chars: int,
    timeout: int,
) -> str:
    command = [
        tesseract, str(filepath), "stdout", "-l", language,
        "--psm", "6",
    ]
    kwargs = _subprocess_kwargs()
    kwargs["timeout"] = timeout
    try:
        result = subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return _sanitize_text(result.stdout, max_chars)


def extract_image_text(
    filepath: str | os.PathLike[str],
    *,
    image_mode: str = "smart",
    language: str = "eng",
    max_chars: int = 4000,
    timeout: int = 20,
    force: bool = False,
) -> str:
    """Extract bounded text from a supported image, or return ``""``.

    ``smart`` mode limits work to filenames that look like screenshots/scans;
    ``always`` is useful for users who have image-heavy document libraries.
    """
    path = Path(filepath)
    if path.suffix.casefold() not in _IMAGE_EXTENSIONS or not _safe_input(path):
        return ""
    if not force and image_mode != "always" and not is_likely_screenshot(path):
        return ""
    tesseract = find_tesseract()
    if not tesseract:
        return ""
    validated = _validate_settings({
        "image_mode": image_mode,
        "language": language,
        "max_chars": max_chars,
        "timeout": timeout,
    })
    return _run_tesseract(
        path,
        tesseract=tesseract,
        language=validated["language"],
        max_chars=validated["max_chars"],
        timeout=validated["timeout"],
    )


def extract_scanned_pdf_text(
    filepath: str | os.PathLike[str],
    *,
    language: str = "eng",
    max_chars: int = 4000,
    timeout: int = 20,
    max_pages: int = 3,
) -> str:
    """OCR the first bounded pages of a PDF using Poppler and Tesseract."""
    path = Path(filepath)
    if path.suffix.casefold() != ".pdf" or not _safe_input(path):
        return ""
    tesseract = find_tesseract()
    renderer = find_pdf_renderer()
    if not tesseract or not renderer:
        return ""
    validated = _validate_settings({
        "language": language,
        "max_chars": max_chars,
        "timeout": timeout,
        "max_pdf_pages": max_pages,
    })
    try:
        with tempfile.TemporaryDirectory(prefix="fileorganizer-ocr-") as temp_dir:
            prefix = str(Path(temp_dir) / "page")
            command = [
                renderer, "-f", "1", "-l", str(validated["max_pdf_pages"]),
                "-r", "150", "-png", str(path), prefix,
            ]
            kwargs = _subprocess_kwargs()
            kwargs["timeout"] = validated["timeout"] * validated["max_pdf_pages"]
            try:
                rendered = subprocess.run(command, **kwargs)
            except (OSError, subprocess.SubprocessError):
                return ""
            if rendered.returncode != 0:
                return ""

            pages = sorted(Path(temp_dir).glob("page-*.png"))
            parts = []
            remaining = validated["max_chars"]
            for page in pages[:validated["max_pdf_pages"]]:
                try:
                    if page.stat().st_size > _MAX_RENDERED_PAGE_BYTES:
                        continue
                except OSError:
                    continue
                text = _run_tesseract(
                    page,
                    tesseract=tesseract,
                    language=validated["language"],
                    max_chars=remaining,
                    timeout=validated["timeout"],
                )
                if text:
                    parts.append(text)
                    remaining -= len(text)
                    if remaining <= 0:
                        break
            return _sanitize_text(" ".join(parts), validated["max_chars"])
    except OSError:
        return ""


def extract_ocr(filepath: str | os.PathLike[str], *, searchable_text: str = "") -> str:
    """Run configured OCR for an imported image or scanned PDF."""
    settings = load_ocr_settings()
    if not settings["enabled"]:
        return ""
    path = Path(filepath)
    ext = path.suffix.casefold()
    if ext in _IMAGE_EXTENSIONS:
        return extract_image_text(
            path,
            image_mode=settings["image_mode"],
            language=settings["language"],
            max_chars=settings["max_chars"],
            timeout=settings["timeout"],
        )
    if ext == ".pdf" and not (searchable_text or "").strip():
        return extract_scanned_pdf_text(
            path,
            language=settings["language"],
            max_chars=settings["max_chars"],
            timeout=settings["timeout"],
            max_pages=settings["max_pdf_pages"],
        )
    return ""


__all__ = [
    "extract_image_text", "extract_ocr", "extract_scanned_pdf_text",
    "find_pdf_renderer", "find_tesseract", "is_likely_screenshot",
    "load_ocr_settings", "pdf_ocr_available", "save_ocr_settings",
    "tesseract_available",
]
