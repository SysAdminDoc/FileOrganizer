"""Optional dependency imports with graceful feature fallbacks.

Dependency installation is deliberately kept out of application startup.
Install the project's declared requirements during setup; importing this module
only detects which optional capabilities are already available.
"""

from importlib import import_module


def _available(module_name: str) -> bool:
    """Return whether an optional module imports without terminating startup."""
    try:
        import_module(module_name)
    except (ImportError, SystemExit):
        return False
    return True


HAS_RAPIDFUZZ = _available("rapidfuzz.fuzz")
HAS_PSD_TOOLS = _available("psd_tools")
HAS_UNIDECODE = _available("unidecode")
HAS_PILLOW = _available("PIL.Image")

try:
    pillow_heif = import_module("pillow_heif")
    pillow_heif.register_heif_opener()
    HAS_PILLOW_HEIF = True
except ImportError:
    HAS_PILLOW_HEIF = False

HAS_EXIFREAD = _available("exifread")
if HAS_EXIFREAD:
    # Suppress exifread's noisy "File format not recognized" / "does not have exif" warnings
    import logging as _logging
    _logging.getLogger('exifread').setLevel(_logging.CRITICAL)

HAS_MUTAGEN = _available("mutagen")
HAS_WINRT_STORAGE = _available("winrt.windows.storage")
HAS_PYPDF = _available("pypdf")
HAS_PYTHON_DOCX = _available("docx")
HAS_OPENPYXL = _available("openpyxl")
HAS_PYTHON_PPTX = _available("pptx")
HAS_MAGIC = _available("magic")
HAS_REVERSE_GEOCODER = _available("reverse_geocoder")
HAS_CV2 = _available("cv2")
# face_recognition calls quit() when its model package is absent.
HAS_FACE_RECOGNITION = _available("face_recognition") and _available("numpy")
HAS_RARFILE = _available("rarfile")
HAS_PY7ZR = _available("py7zr")
