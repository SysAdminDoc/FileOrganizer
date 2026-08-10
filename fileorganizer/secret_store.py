"""Small Windows-user scoped secret store backed by DPAPI.

The application is Windows-first and stores provider credentials in user app
data.  Plain JSON is not an acceptable credential store, so values in this
module are encrypted with the current Windows user's DPAPI key before they
are written.  On non-Windows systems the store refuses to persist secrets;
callers can still use environment variables for local development.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import tempfile
from ctypes import wintypes

from fileorganizer.config import _APP_DATA_DIR

log = logging.getLogger(__name__)

_SECRETS_FILE = os.path.join(_APP_DATA_DIR, "secrets.json")
_PREFIX = "dpapi:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecretStoreError(RuntimeError):
    """Raised when a secret cannot be encrypted or persisted safely."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _crypt32():
    if os.name != "nt":
        raise SecretStoreError("DPAPI secret storage is only available on Windows")
    return ctypes.WinDLL("crypt32", use_last_error=True)


def _kernel32():
    if os.name != "nt":
        raise SecretStoreError("DPAPI secret storage is only available on Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _last_error(operation: str) -> SecretStoreError:
    code = ctypes.get_last_error()
    return SecretStoreError(f"{operation} failed with Win32 error {code}")


def _free_blob(blob: _DataBlob) -> None:
    if blob.pbData:
        kernel32 = _kernel32()
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def _dpapi_protect(value: str) -> str:
    raw = value.encode("utf-8")
    if not raw:
        return ""

    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    protected = _DataBlob()
    crypt32 = _crypt32()
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(protected),
    ):
        raise _last_error("CryptProtectData")

    try:
        encrypted = ctypes.string_at(protected.pbData, protected.cbData)
        return _PREFIX + base64.b64encode(encrypted).decode("ascii")
    finally:
        _free_blob(protected)


def _dpapi_unprotect(encoded: str) -> str:
    if not encoded.startswith(_PREFIX):
        raise SecretStoreError("secret is not DPAPI-protected")
    try:
        raw = base64.b64decode(encoded[len(_PREFIX):], validate=True)
    except (ValueError, TypeError) as exc:
        raise SecretStoreError("secret has invalid DPAPI encoding") from exc
    if not raw:
        return ""

    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    unprotected = _DataBlob()
    crypt32 = _crypt32()
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    description = ctypes.c_wchar_p()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        ctypes.byref(description),
        None,
        None,
        None,
        0,
        ctypes.byref(unprotected),
    ):
        raise _last_error("CryptUnprotectData")

    try:
        return ctypes.string_at(unprotected.pbData, unprotected.cbData).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretStoreError("DPAPI secret is not valid UTF-8") from exc
    finally:
        _free_blob(unprotected)
        if description:
            _kernel32().LocalFree.argtypes = [ctypes.c_void_p]
            _kernel32().LocalFree.restype = ctypes.c_void_p
            _kernel32().LocalFree(ctypes.cast(description, ctypes.c_void_p))


def _read_store() -> dict[str, str]:
    try:
        with open(_SECRETS_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        log.warning("Ignoring malformed secret store at %s", _SECRETS_FILE)
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, str)}


def _write_store(value: dict[str, str]) -> None:
    directory = os.path.dirname(_SECRETS_FILE) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="secrets.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, _SECRETS_FILE)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def get_secret(name: str) -> str:
    """Return a decrypted secret or an empty string when it is unavailable."""
    encoded = _read_store().get(name, "")
    if not encoded:
        return ""
    try:
        return _dpapi_unprotect(encoded)
    except SecretStoreError as exc:
        log.warning("Could not decrypt secret %r: %s", name, exc)
        return ""


def set_secret(name: str, value: str) -> None:
    """Encrypt and persist ``value``; empty values remove the entry."""
    if not name or any(char in name for char in "\\/\r\n"):
        raise ValueError("secret name must be a single safe key")
    stored = _read_store()
    if value:
        stored[name] = _dpapi_protect(value)
    else:
        stored.pop(name, None)
    _write_store(stored)

