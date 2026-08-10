"""Restartable NTFS USN Change Journal tracking with safe full-scan fallback.

The native reader is deliberately isolated from the catalog integration so the
checkpoint, wrap, rename, and deletion behavior can be tested with a fixture
backend on every platform.  Persisted paths are relative to the selected root.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import sqlite3
import struct
import sys
from dataclasses import dataclass, field
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FSCTL_QUERY_USN_JOURNAL = 0x000900F4
FSCTL_READ_USN_JOURNAL = 0x000900BB
FSCTL_READ_UNPRIVILEGED_USN_JOURNAL = 0x000903AB
FILE_ATTRIBUTE_DIRECTORY = 0x10
USN_REASON_FILE_CREATE = 0x00000100
USN_REASON_FILE_DELETE = 0x00000200
USN_REASON_RENAME_OLD_NAME = 0x00001000
USN_REASON_RENAME_NEW_NAME = 0x00002000
USN_REASON_CLOSE = 0x80000000
_SCHEMA_VERSION = 1
_MAX_CHANGES = 500_000
_READ_BUFFER_BYTES = 1024 * 1024


class UsnUnavailableError(RuntimeError):
    """The journal cannot be read safely for this root."""


@dataclass(frozen=True)
class VolumeInfo:
    supported: bool
    volume_root: str = ""
    serial: str = ""
    filesystem: str = ""
    is_remote: bool = False
    reason: str = ""


@dataclass(frozen=True)
class JournalCursor:
    journal_id: str
    first_usn: int
    next_usn: int
    lowest_valid_usn: int


@dataclass(frozen=True)
class UsnChange:
    file_reference: str
    parent_reference: str
    usn: int
    reason: int
    name: str
    is_directory: bool = False


@dataclass(frozen=True)
class ResolvedChange:
    change: UsnChange
    old_relative_path: str = ""
    new_relative_path: str = ""
    change_type: str = "modified"


@dataclass
class IncrementalPlan:
    mode: str
    reason: str
    root_path: str
    root_key: str
    volume: VolumeInfo
    cursor: JournalCursor | None = None
    start_usn: int = 0
    end_usn: int = 0
    lag_bytes: int = 0
    changes: list[ResolvedChange] = field(default_factory=list)
    affected_assets: set[tuple[str, str]] = field(default_factory=set)
    previous_assets: set[tuple[str, str]] = field(default_factory=set)
    path_events: list[tuple[str, str]] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root_key(root_path: str) -> str:
    normalized = os.path.normcase(os.path.abspath(root_path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _relative_path(root_path: str, path: str) -> str:
    relative = os.path.relpath(path, root_path)
    return relative.replace("\\", "/")


def _join_relative(parent: str, name: str) -> str:
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
        return ""
    if parent in ("", "."):
        return name
    return f"{parent.rstrip('/')}/{name}"


def _asset_key(relative_path: str) -> tuple[str, str] | None:
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def ensure_schema(con: sqlite3.Connection) -> None:
    """Create the journal checkpoint and relative file-reference map."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS usn_volume_state (
            root_key TEXT PRIMARY KEY,
            volume_root TEXT NOT NULL,
            volume_serial TEXT NOT NULL,
            journal_id TEXT NOT NULL,
            next_usn INTEGER NOT NULL,
            lowest_valid_usn INTEGER NOT NULL,
            status TEXT NOT NULL,
            last_mode TEXT NOT NULL,
            lag_bytes INTEGER NOT NULL DEFAULT 0,
            tracked_entries INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usn_path_map (
            root_key TEXT NOT NULL,
            file_reference TEXT NOT NULL,
            parent_reference TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            is_directory INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(root_key, file_reference)
        );
        CREATE INDEX IF NOT EXISTS idx_usn_path_relative
            ON usn_path_map(root_key, relative_path);
        CREATE TABLE IF NOT EXISTS usn_index_schema (
            schema_name TEXT PRIMARY KEY,
            version INTEGER NOT NULL
        );
        """
    )
    con.execute(
        """
        INSERT INTO usn_index_schema(schema_name, version)
        VALUES ('usn_index', ?)
        ON CONFLICT(schema_name) DO UPDATE SET version=excluded.version
        WHERE usn_index_schema.version < excluded.version
        """,
        (_SCHEMA_VERSION,),
    )


class NativeUsnReader:
    """Minimal native reader for NTFS USN_RECORD_V2/V3 streams."""

    def __init__(self, max_changes: int = _MAX_CHANGES) -> None:
        self.max_changes = max_changes

    def probe(self, root_path: str) -> VolumeInfo:
        if sys.platform != "win32":
            return VolumeInfo(False, reason="USN is available only on Windows")
        absolute = os.path.abspath(root_path)
        drive, _ = os.path.splitdrive(absolute)
        if not drive or absolute.startswith("\\\\"):
            return VolumeInfo(False, is_remote=True, reason="network or non-volume root")
        volume_root = f"{drive}\\"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetDriveTypeW.restype = ctypes.c_uint32
        kernel32.GetVolumeInformationW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_wchar_p,
            ctypes.c_uint32,
        ]
        kernel32.GetVolumeInformationW.restype = ctypes.c_int
        drive_type = int(kernel32.GetDriveTypeW(ctypes.c_wchar_p(volume_root)))
        if drive_type == 4:
            return VolumeInfo(False, volume_root, is_remote=True, reason="remote volume")

        volume_name = ctypes.create_unicode_buffer(261)
        filesystem_name = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_uint32()
        max_component = ctypes.c_uint32()
        flags = ctypes.c_uint32()
        ok = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(volume_root),
            volume_name,
            len(volume_name),
            ctypes.byref(serial),
            ctypes.byref(max_component),
            ctypes.byref(flags),
            filesystem_name,
            len(filesystem_name),
        )
        if not ok:
            error = ctypes.get_last_error()
            return VolumeInfo(False, volume_root, reason=f"volume query failed ({error})")
        filesystem = filesystem_name.value.upper()
        if filesystem != "NTFS":
            return VolumeInfo(
                False,
                volume_root,
                str(serial.value),
                filesystem,
                reason=f"unsupported filesystem {filesystem or 'unknown'}",
            )
        return VolumeInfo(True, volume_root, str(serial.value), filesystem)

    def _open_volume(
        self, volume: VolumeInfo, desired_access: int = 0
    ) -> tuple[Any, Any]:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.DeviceIoControl.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        kernel32.DeviceIoControl.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.CreateFileW(
            ctypes.c_wchar_p(f"\\\\.\\{volume.volume_root[:2]}"),
            desired_access,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            3,
            0,
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if handle in (None, invalid):
            error = ctypes.get_last_error()
            raise UsnUnavailableError(f"volume open failed ({error})")
        return kernel32, handle

    @staticmethod
    def _device_io(
        kernel32: Any,
        handle: Any,
        control_code: int,
        input_bytes: bytes | None,
        output_size: int,
    ) -> bytes:
        output = ctypes.create_string_buffer(output_size)
        returned = ctypes.c_uint32()
        if input_bytes is None:
            input_buffer = None
            input_size = 0
        else:
            input_buffer = ctypes.create_string_buffer(input_bytes)
            input_size = len(input_bytes)
        ok = kernel32.DeviceIoControl(
            handle,
            control_code,
            input_buffer,
            input_size,
            output,
            output_size,
            ctypes.byref(returned),
            None,
        )
        if not ok:
            error = ctypes.get_last_error()
            raise UsnUnavailableError(f"DeviceIoControl 0x{control_code:x} failed ({error})")
        return output.raw[: returned.value]

    def query(self, volume: VolumeInfo) -> JournalCursor:
        if not volume.supported:
            raise UsnUnavailableError(volume.reason)
        data = b""
        last_error: UsnUnavailableError | None = None
        for desired_access in (0, 0x80, 0x80000000):
            try:
                kernel32, handle = self._open_volume(volume, desired_access)
            except UsnUnavailableError as exc:
                last_error = exc
                continue
            try:
                data = self._device_io(
                    kernel32, handle, FSCTL_QUERY_USN_JOURNAL, None, 128
                )
                break
            except UsnUnavailableError as exc:
                last_error = exc
            finally:
                kernel32.CloseHandle(handle)
        if not data:
            unpriv_handle = None
            try:
                kernel32, unpriv_handle = self._open_volume(volume)
                request = struct.pack("<qIIQQQ", 0, 0, 0, 0, 0, 0)
                tail = self._device_io(
                    kernel32,
                    unpriv_handle,
                    FSCTL_READ_UNPRIVILEGED_USN_JOURNAL,
                    request,
                    _READ_BUFFER_BYTES,
                )
                if len(tail) >= 8:
                    next_usn = struct.unpack_from("<q", tail)[0]
                    return JournalCursor("unprivileged", 0, next_usn, 0)
            except UsnUnavailableError as exc:
                last_error = exc
            finally:
                if unpriv_handle is not None:
                    kernel32.CloseHandle(unpriv_handle)
            raise last_error or UsnUnavailableError("journal query failed")
        if len(data) < 56:
            raise UsnUnavailableError("journal query returned a short record")
        journal_id, first, next_usn, lowest, _max_usn, _size, _delta = struct.unpack_from(
            "<QqqqqQQ", data
        )
        return JournalCursor(str(journal_id), first, next_usn, lowest)

    @staticmethod
    def parse_records(data: bytes) -> tuple[int, list[UsnChange]]:
        """Parse one FSCTL_READ_USN_JOURNAL output buffer."""
        if len(data) < 8:
            raise UsnUnavailableError("journal read returned a short buffer")
        next_usn = struct.unpack_from("<q", data, 0)[0]
        offset = 8
        changes: list[UsnChange] = []
        while offset + 8 <= len(data):
            record_length, major, _minor = struct.unpack_from("<IHH", data, offset)
            minimum_length = 76 if major == 3 else 60
            if record_length < minimum_length or offset + record_length > len(data):
                raise UsnUnavailableError("journal record has an invalid length")
            if major == 2:
                file_reference = str(struct.unpack_from("<Q", data, offset + 8)[0])
                parent_reference = str(struct.unpack_from("<Q", data, offset + 16)[0])
                usn = struct.unpack_from("<q", data, offset + 24)[0]
                reason = struct.unpack_from("<I", data, offset + 40)[0]
                attributes = struct.unpack_from("<I", data, offset + 52)[0]
                name_length, name_offset = struct.unpack_from("<HH", data, offset + 56)
            elif major == 3:
                file_reference = data[offset + 8 : offset + 24].hex()
                parent_reference = data[offset + 24 : offset + 40].hex()
                usn = struct.unpack_from("<q", data, offset + 40)[0]
                reason = struct.unpack_from("<I", data, offset + 56)[0]
                attributes = struct.unpack_from("<I", data, offset + 68)[0]
                name_length, name_offset = struct.unpack_from("<HH", data, offset + 72)
            else:
                offset += record_length
                continue
            name_end = offset + name_offset + name_length
            if name_end > offset + record_length:
                raise UsnUnavailableError("journal filename exceeds its record")
            name = data[offset + name_offset : name_end].decode("utf-16le", errors="replace")
            changes.append(
                UsnChange(
                    file_reference=file_reference,
                    parent_reference=parent_reference,
                    usn=usn,
                    reason=reason,
                    name=name,
                    is_directory=bool(attributes & FILE_ATTRIBUTE_DIRECTORY),
                )
            )
            offset += record_length
        return next_usn, changes

    def read_changes(
        self,
        volume: VolumeInfo,
        start_usn: int,
        journal_id: str,
        stop_usn: int,
    ) -> tuple[list[UsnChange], int]:
        def read_with(
            kernel32: Any, handle: Any, control_code: int
        ) -> tuple[list[UsnChange], int]:
            changes: list[UsnChange] = []
            cursor = start_usn
            while cursor < stop_usn:
                request = struct.pack(
                    "<qIIQQQ",
                    cursor,
                    0xFFFFFFFF,
                    0,
                    0,
                    0,
                    0 if journal_id == "unprivileged" else int(journal_id),
                )
                data = self._device_io(
                    kernel32,
                    handle,
                    control_code,
                    request,
                    _READ_BUFFER_BYTES,
                )
                next_usn, batch = self.parse_records(data)
                changes.extend(batch)
                if len(changes) > self.max_changes:
                    raise UsnUnavailableError("journal delta exceeds the safe record limit")
                if next_usn <= cursor:
                    raise UsnUnavailableError("journal cursor did not advance")
                cursor = min(next_usn, stop_usn)
            return changes, cursor

        kernel32, handle = self._open_volume(volume)
        try:
            return read_with(
                kernel32, handle, FSCTL_READ_UNPRIVILEGED_USN_JOURNAL
            )
        except UsnUnavailableError:
            pass
        finally:
            kernel32.CloseHandle(handle)
        kernel32, handle = self._open_volume(volume, desired_access=0x80000000)
        try:
            return read_with(kernel32, handle, FSCTL_READ_USN_JOURNAL)
        finally:
            kernel32.CloseHandle(handle)


class UsnIncrementalIndex:
    """Plan and checkpoint root-scoped changes in an existing SQLite database."""

    def __init__(self, db_path: str, backend: Any | None = None) -> None:
        self.db_path = db_path
        self.backend = backend or NativeUsnReader()

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        ensure_schema(con)
        con.commit()
        return con

    def prepare(
        self, root_path: str, *, catalog_mode: bool = True
    ) -> IncrementalPlan:
        root = os.path.abspath(root_path)
        key = _root_key(root)
        volume = self.backend.probe(root)
        if not volume.supported:
            return IncrementalPlan("full_fallback", volume.reason, root, key, volume)
        try:
            cursor = self.backend.query(volume)
        except (OSError, UsnUnavailableError) as exc:
            return IncrementalPlan("full_fallback", str(exc), root, key, volume)

        con = self._connect()
        try:
            state = con.execute(
                "SELECT * FROM usn_volume_state WHERE root_key=?", (key,)
            ).fetchone()
            if state is None:
                return IncrementalPlan(
                    "full_rebuild",
                    "initial USN checkpoint",
                    root,
                    key,
                    volume,
                    cursor=cursor,
                    end_usn=cursor.next_usn,
                )
            previous_assets = self._known_assets(con, key)
            start_usn = int(state["next_usn"])
            invalid_reason = ""
            if str(state["volume_serial"]) != volume.serial:
                invalid_reason = "volume identity changed"
            elif str(state["journal_id"]) != cursor.journal_id:
                invalid_reason = "journal identity changed"
            elif start_usn < cursor.lowest_valid_usn:
                invalid_reason = "journal wrapped past the saved cursor"
            elif start_usn > cursor.next_usn:
                invalid_reason = "saved cursor is ahead of the journal"
            if invalid_reason:
                return IncrementalPlan(
                    "full_rebuild",
                    invalid_reason,
                    root,
                    key,
                    volume,
                    cursor=cursor,
                    start_usn=start_usn,
                    end_usn=cursor.next_usn,
                    previous_assets=previous_assets,
                )
            try:
                raw_changes, end_usn = self.backend.read_changes(
                    volume, start_usn, cursor.journal_id, cursor.next_usn
                )
            except (OSError, UsnUnavailableError) as exc:
                return IncrementalPlan(
                    "full_rebuild",
                    f"journal read failed: {exc}",
                    root,
                    key,
                    volume,
                    cursor=cursor,
                    start_usn=start_usn,
                    end_usn=cursor.next_usn,
                    previous_assets=previous_assets,
                )
            resolved, affected, path_events, needs_full = self._resolve_changes(
                con, key, root, raw_changes
            )
            if needs_full and catalog_mode:
                return IncrementalPlan(
                    "full_rebuild",
                    "root or category-level change requires catalog rediscovery",
                    root,
                    key,
                    volume,
                    cursor=cursor,
                    start_usn=start_usn,
                    end_usn=end_usn,
                    lag_bytes=max(0, cursor.next_usn - start_usn),
                    previous_assets=previous_assets,
                )
            return IncrementalPlan(
                "incremental",
                "journal resumed",
                root,
                key,
                volume,
                cursor=cursor,
                start_usn=start_usn,
                end_usn=end_usn,
                lag_bytes=max(0, cursor.next_usn - start_usn),
                changes=resolved,
                affected_assets=affected,
                path_events=path_events,
            )
        finally:
            con.close()

    @staticmethod
    def _known_assets(
        con: sqlite3.Connection, root_key: str
    ) -> set[tuple[str, str]]:
        assets: set[tuple[str, str]] = set()
        rows = con.execute(
            "SELECT relative_path FROM usn_path_map "
            "WHERE root_key=? AND is_directory=1 "
            "AND relative_path LIKE '%/%' AND relative_path NOT LIKE '%/%/%'",
            (root_key,),
        ).fetchall()
        for row in rows:
            key = _asset_key(str(row["relative_path"]))
            if key is not None:
                assets.add(key)
        return assets

    @staticmethod
    def _load_map_rows(
        con: sqlite3.Connection,
        root_key: str,
        references: set[str],
    ) -> dict[str, tuple[str, bool]]:
        rows: dict[str, tuple[str, bool]] = {}
        ordered = sorted(references)
        for offset in range(0, len(ordered), 800):
            chunk = ordered[offset : offset + 800]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            query = (
                "SELECT file_reference, relative_path, is_directory FROM usn_path_map "
                f"WHERE root_key=? AND file_reference IN ({placeholders})"
            )
            for row in con.execute(query, (root_key, *chunk)).fetchall():
                rows[str(row["file_reference"])] = (
                    str(row["relative_path"]),
                    bool(row["is_directory"]),
                )
        return rows

    def _resolve_changes(
        self,
        con: sqlite3.Connection,
        root_key: str,
        root_path: str,
        changes: list[UsnChange],
    ) -> tuple[
        list[ResolvedChange],
        set[tuple[str, str]],
        list[tuple[str, str]],
        bool,
    ]:
        references = {
            reference
            for change in changes
            for reference in (change.file_reference, change.parent_reference)
        }
        overlay = self._load_map_rows(con, root_key, references)
        resolved: list[ResolvedChange] = []
        affected: set[tuple[str, str]] = set()
        events: dict[str, str] = {}
        needs_full = False

        for change in sorted(changes, key=lambda item: item.usn):
            existing = overlay.get(change.file_reference)
            parent = overlay.get(change.parent_reference)
            old_relative = existing[0] if existing else ""
            derived = _join_relative(parent[0], change.name) if parent else ""
            new_relative = old_relative or derived
            change_type = "modified"

            if change.reason & USN_REASON_RENAME_OLD_NAME:
                change_type = "renamed"
                new_relative = ""
            if change.reason & USN_REASON_FILE_DELETE:
                change_type = "deleted"
                new_relative = ""
                overlay.pop(change.file_reference, None)
            elif change.reason & (USN_REASON_RENAME_NEW_NAME | USN_REASON_FILE_CREATE):
                change_type = (
                    "renamed" if change.reason & USN_REASON_RENAME_NEW_NAME else "created"
                )
                new_relative = derived
                if derived:
                    overlay[change.file_reference] = (derived, change.is_directory)
                elif old_relative:
                    overlay.pop(change.file_reference, None)

            relevant_paths = [path for path in (old_relative, new_relative) if path]
            if not relevant_paths:
                continue
            for relative in relevant_paths:
                key = _asset_key(relative)
                if key is None:
                    needs_full = True
                else:
                    affected.add(key)
                absolute = os.path.abspath(
                    os.path.join(root_path, relative.replace("/", os.sep))
                )
                if os.path.commonpath((root_path, absolute)) == root_path:
                    events[absolute] = change_type
            resolved.append(
                ResolvedChange(
                    change,
                    old_relative_path=old_relative,
                    new_relative_path=new_relative,
                    change_type=change_type,
                )
            )
        return resolved, affected, sorted(events.items()), needs_full

    @staticmethod
    def _file_reference(path: str) -> str:
        stat = os.stat(path, follow_symlinks=False)
        if not stat.st_ino:
            raise UsnUnavailableError("filesystem did not expose stable file references")
        return str(stat.st_ino)

    def _mapping_rows(
        self, root_path: str, start_path: str
    ) -> Iterator[tuple[str, str, str, str, int]]:
        root_identifier = _root_key(root_path)

        def row_for(
            path: str, is_directory: bool
        ) -> tuple[str, str, str, str, int] | None:
            try:
                reference = self._file_reference(path)
                if os.path.normcase(path) == os.path.normcase(root_path):
                    parent_reference = ""
                else:
                    parent_reference = self._file_reference(os.path.dirname(path))
                return (
                    root_identifier,
                    reference,
                    parent_reference,
                    _relative_path(root_path, path),
                    int(is_directory),
                )
            except (OSError, UsnUnavailableError):
                return None

        root_row = row_for(start_path, True)
        if root_row is not None:
            yield root_row
        for current, directories, files in os.walk(start_path, followlinks=False):
            for name in directories:
                row = row_for(os.path.join(current, name), True)
                if row is not None:
                    yield row
            for name in files:
                row = row_for(os.path.join(current, name), False)
                if row is not None:
                    yield row

    @staticmethod
    def _delete_mapping_prefix(
        con: sqlite3.Connection, root_key: str, relative_prefix: str
    ) -> None:
        escaped = (
            relative_prefix.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        con.execute(
            "DELETE FROM usn_path_map WHERE root_key=? AND "
            "(relative_path=? OR relative_path LIKE ? ESCAPE '\\')",
            (root_key, relative_prefix, f"{escaped}/%"),
        )

    @staticmethod
    def _insert_mapping_rows(
        con: sqlite3.Connection,
        rows: Iterable[tuple[str, str, str, str, int]],
    ) -> None:
        con.executemany(
            """
            INSERT INTO usn_path_map(
                root_key, file_reference, parent_reference, relative_path, is_directory
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(root_key, file_reference) DO UPDATE SET
                parent_reference=excluded.parent_reference,
                relative_path=excluded.relative_path,
                is_directory=excluded.is_directory
            """,
            rows,
        )

    def _write_state(
        self,
        con: sqlite3.Connection,
        plan: IncrementalPlan,
        mode: str,
        error: str = "",
    ) -> None:
        if plan.cursor is None:
            return
        tracked = con.execute(
            "SELECT COUNT(*) FROM usn_path_map WHERE root_key=?", (plan.root_key,)
        ).fetchone()[0]
        con.execute(
            """
            INSERT INTO usn_volume_state(
                root_key, volume_root, volume_serial, journal_id, next_usn,
                lowest_valid_usn, status, last_mode, lag_bytes, tracked_entries,
                last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(root_key) DO UPDATE SET
                volume_root=excluded.volume_root,
                volume_serial=excluded.volume_serial,
                journal_id=excluded.journal_id,
                next_usn=excluded.next_usn,
                lowest_valid_usn=excluded.lowest_valid_usn,
                status=excluded.status,
                last_mode=excluded.last_mode,
                lag_bytes=excluded.lag_bytes,
                tracked_entries=excluded.tracked_entries,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            (
                plan.root_key,
                plan.volume.volume_root,
                plan.volume.serial,
                plan.cursor.journal_id,
                plan.end_usn,
                plan.cursor.lowest_valid_usn,
                "ready" if not error else "error",
                mode,
                0,
                int(tracked),
                error,
                _utc_now(),
            ),
        )

    def complete_full_scan(self, plan: IncrementalPlan) -> None:
        """Seed the file-reference map and save the pre-scan cursor."""
        if plan.cursor is None:
            return
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM usn_path_map WHERE root_key=?", (plan.root_key,))
            batch: list[tuple[str, str, str, str, int]] = []
            seeded = False
            for row in self._mapping_rows(plan.root_path, plan.root_path):
                seeded = True
                batch.append(row)
                if len(batch) >= 5000:
                    self._insert_mapping_rows(con, batch)
                    batch.clear()
            if batch:
                self._insert_mapping_rows(con, batch)
            if not seeded:
                raise UsnUnavailableError("full scan could not seed the root file reference")
            self._write_state(con, plan, "full_rebuild")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def complete_incremental(self, plan: IncrementalPlan) -> None:
        """Refresh affected path mappings and atomically advance the cursor."""
        if plan.cursor is None or plan.mode != "incremental":
            return
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            for category, asset in sorted(plan.affected_assets):
                relative = f"{category}/{asset}"
                self._delete_mapping_prefix(con, plan.root_key, relative)
                asset_path = os.path.join(plan.root_path, category, asset)
                if os.path.isdir(asset_path):
                    self._insert_mapping_rows(
                        con, self._mapping_rows(plan.root_path, asset_path)
                    )
                if self._table_exists(con, "folder_cache"):
                    escaped_asset_path = (
                        asset_path.replace("\\", "\\\\")
                        .replace("%", "\\%")
                        .replace("_", "\\_")
                    )
                    escaped_separator = os.sep.replace("\\", "\\\\")
                    con.execute(
                        "DELETE FROM folder_cache WHERE folder_path=? "
                        "OR folder_path LIKE ? ESCAPE '\\'",
                        (asset_path, f"{escaped_asset_path}{escaped_separator}%"),
                    )
            self._write_state(con, plan, "incremental")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def complete_watch_incremental(self, plan: IncrementalPlan) -> None:
        """Apply generic relative-path changes and advance a watcher cursor."""
        if plan.cursor is None or plan.mode != "incremental":
            return
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            for resolved in plan.changes:
                old_relative = resolved.old_relative_path
                new_relative = resolved.new_relative_path
                if old_relative and old_relative != new_relative:
                    self._delete_mapping_prefix(con, plan.root_key, old_relative)
                if not new_relative:
                    continue
                absolute = os.path.join(
                    plan.root_path, new_relative.replace("/", os.sep)
                )
                if os.path.isdir(absolute):
                    self._delete_mapping_prefix(con, plan.root_key, new_relative)
                    self._insert_mapping_rows(
                        con, self._mapping_rows(plan.root_path, absolute)
                    )
                elif os.path.isfile(absolute):
                    try:
                        row = (
                            plan.root_key,
                            self._file_reference(absolute),
                            self._file_reference(os.path.dirname(absolute)),
                            new_relative,
                            0,
                        )
                    except (OSError, UsnUnavailableError):
                        continue
                    self._insert_mapping_rows(con, [row])
            self._write_state(con, plan, "watch_incremental")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        ).fetchone() is not None

    def stats(self, root_path: str) -> dict[str, object]:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT * FROM usn_volume_state WHERE root_key=?",
                (_root_key(root_path),),
            ).fetchone()
        finally:
            con.close()
        if row is None:
            return {"status": "not_initialized", "lag_bytes": 0, "tracked_entries": 0}
        lag_bytes = int(row["lag_bytes"])
        live_status = str(row["status"])
        try:
            volume = self.backend.probe(os.path.abspath(root_path))
            if volume.supported:
                cursor = self.backend.query(volume)
                if (
                    volume.serial != str(row["volume_serial"])
                    or cursor.journal_id != str(row["journal_id"])
                    or int(row["next_usn"]) < cursor.lowest_valid_usn
                ):
                    live_status = "rebuild_required"
                else:
                    lag_bytes = max(0, cursor.next_usn - int(row["next_usn"]))
            else:
                live_status = "full_fallback"
        except (OSError, UsnUnavailableError):
            live_status = "unavailable"
        return {
            "status": live_status,
            "last_mode": row["last_mode"],
            "next_usn": int(row["next_usn"]),
            "lag_bytes": lag_bytes,
            "tracked_entries": int(row["tracked_entries"]),
            "updated_at": row["updated_at"],
            "last_error": row["last_error"],
        }


def resume_usn_changes(
    root_path: str,
    db_path: str,
    backend: Any | None = None,
) -> dict[str, object]:
    """Resume a generic watcher checkpoint and return root-scoped path events."""
    tracker = UsnIncrementalIndex(db_path, backend=backend)
    plan = tracker.prepare(root_path, catalog_mode=False)
    if plan.mode == "full_rebuild":
        tracker.complete_full_scan(plan)
        return {
            "mode": "full_checkpoint",
            "reason": plan.reason,
            "events": [],
            "lag_bytes": plan.lag_bytes,
        }
    if plan.mode == "incremental":
        tracker.complete_watch_incremental(plan)
        return {
            "mode": "incremental",
            "reason": plan.reason,
            "events": [
                {"path": path, "change_type": change_type}
                for path, change_type in plan.path_events
            ],
            "lag_bytes": plan.lag_bytes,
        }
    return {
        "mode": "full_fallback",
        "reason": plan.reason,
        "events": [],
        "lag_bytes": 0,
    }
