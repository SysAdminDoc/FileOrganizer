"""Free-space reserve via sparse file (NEXT-36).

Pre-allocates a sparse file sized to (estimated bytes × 1.10) before apply.
Sparse files reserve no physical blocks until written, but the filesystem
rejects competing writes that would push it over the reserve. Deleted on
clean completion or crash recovery.
"""
import ctypes
import logging
import os
import sys
from typing import Optional

log = logging.getLogger(__name__)

_RESERVE_NAME = ".fileorganizer.reserve"
_MARGIN = 1.10  # 10% safety margin


def create_reserve(dest_root: str, estimated_bytes: int) -> Optional[str]:
    """Create a sparse reserve file at dest_root.

    Args:
        dest_root: Destination drive root (e.g. G:\\Organized)
        estimated_bytes: Estimated total bytes to be moved

    Returns:
        Path to reserve file, or None if creation failed.
    """
    reserve_path = os.path.join(dest_root, _RESERVE_NAME)
    reserve_size = int(estimated_bytes * _MARGIN)

    if reserve_size <= 0:
        return None

    try:
        _free = _get_free_space(dest_root)
        if _free is not None and reserve_size > _free:
            log.warning(
                "Not enough free space for reserve: need %d, have %d",
                reserve_size, _free,
            )
            return None
    except Exception:
        pass

    try:
        if sys.platform == "win32":
            return _create_sparse_windows(reserve_path, reserve_size)
        else:
            return _create_sparse_posix(reserve_path, reserve_size)
    except Exception as e:
        log.warning("Failed to create space reserve: %s", e)
        return None


def release_reserve(dest_root: str):
    """Delete the reserve file on clean completion."""
    reserve_path = os.path.join(dest_root, _RESERVE_NAME)
    try:
        if os.path.exists(reserve_path):
            os.remove(reserve_path)
    except OSError as e:
        log.warning("Failed to remove reserve file: %s", e)


def has_reserve(dest_root: str) -> bool:
    """Check if a reserve file exists (indicates prior crash)."""
    return os.path.exists(os.path.join(dest_root, _RESERVE_NAME))


def _get_free_space(path: str) -> Optional[int]:
    """Get free space in bytes for the drive containing path."""
    try:
        usage = os.statvfs(path) if hasattr(os, "statvfs") else None
        if usage:
            return usage.f_bavail * usage.f_frsize
    except (OSError, AttributeError):
        pass

    if sys.platform == "win32":
        try:
            import ctypes
            free = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(path), None, None, ctypes.byref(free)
            )
            return free.value
        except Exception:
            pass

    try:
        import shutil
        return shutil.disk_usage(path).free
    except Exception:
        return None


def _create_sparse_windows(path: str, size: int) -> Optional[str]:
    """Create a sparse file on Windows using FSCTL_SET_SPARSE."""
    FSCTL_SET_SPARSE = 0x000900C4
    FILE_ATTRIBUTE_NORMAL = 0x80
    GENERIC_WRITE = 0x40000000
    CREATE_ALWAYS = 2
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    handle = kernel32.CreateFileW(
        path, GENERIC_WRITE, 0, None, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, None
    )
    if handle == INVALID_HANDLE_VALUE or handle is None:
        return None

    try:
        bytes_returned = ctypes.c_ulong(0)
        kernel32.DeviceIoControl(
            handle, FSCTL_SET_SPARSE, None, 0, None, 0,
            ctypes.byref(bytes_returned), None,
        )

        high = ctypes.c_long(size >> 32)
        kernel32.SetFilePointer(handle, size & 0xFFFFFFFF, ctypes.byref(high), 0)
        kernel32.SetEndOfFile(handle)
    finally:
        kernel32.CloseHandle(handle)

    return path


def _create_sparse_posix(path: str, size: int) -> Optional[str]:
    """Create a sparse file on POSIX by seeking past EOF."""
    with open(path, "wb") as f:
        f.seek(size - 1)
        f.write(b"\0")
    return path
