"""Notify Windows Explorer and Search after file moves (NEXT-67).

Calls SHChangeNotify via ctypes to invalidate Explorer's cached metadata
and trigger Windows Search re-indexing of moved files.
"""
import ctypes
import os
import sys
from typing import List, Tuple

SHCNE_RENAMEITEM = 0x00000001
SHCNE_CREATE = 0x00000002
SHCNE_DELETE = 0x00000004
SHCNE_UPDATEDIR = 0x00001000
SHCNE_UPDATEITEM = 0x00008000
SHCNF_PATH = 0x0005
SHCNF_FLUSH = 0x1000

_IS_WINDOWS = sys.platform == "win32"


def notify_shell_moves(moves: List[Tuple[str, str]]):
    """Notify Explorer that files moved from src to dst.

    Args:
        moves: list of (source_path, dest_path) tuples
    """
    if not _IS_WINDOWS or not moves:
        return

    try:
        shell32 = ctypes.windll.shell32
    except (AttributeError, OSError):
        return

    notified_dirs = set()
    for src, dst in moves:
        src_dir = os.path.dirname(src)
        dst_dir = os.path.dirname(dst)
        notified_dirs.add(src_dir)
        notified_dirs.add(dst_dir)

    for d in notified_dirs:
        if d:
            shell32.SHChangeNotify(
                SHCNE_UPDATEDIR,
                SHCNF_PATH,
                ctypes.c_wchar_p(d),
                None,
            )

    shell32.SHChangeNotify(SHCNE_UPDATEDIR, SHCNF_FLUSH, None, None)


def notify_shell_single(src: str, dst: str):
    """Notify Explorer of a single file move."""
    notify_shell_moves([(src, dst)])
