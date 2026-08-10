"""No-overwrite, journaled move actions shared by interactive workflows."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import asdict, dataclass

from fileorganizer import move_journal
from fileorganizer.path_safety import (
    source_signature,
    validate_move,
    validate_path,
    validate_source_signature,
)


@dataclass(frozen=True)
class MoveOutcome:
    action_id: str
    source: str
    destination: str
    status: str
    message: str = ''
    journal_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _files_identical(source: str, destination: str) -> bool:
    try:
        return (
            os.path.isfile(source)
            and os.path.isfile(destination)
            and os.path.getsize(source) == os.path.getsize(destination)
            and _file_sha256(source) == _file_sha256(destination)
        )
    except OSError:
        return False


def _unique_destination(path: str) -> str:
    if not os.path.lexists(path):
        return path
    stem, extension = os.path.splitext(path)
    index = 1
    while index <= 10_000:
        candidate = f'{stem} ({index}){extension}'
        if not os.path.lexists(candidate):
            return candidate
        index += 1
    raise OSError('could not allocate a collision-free destination name')


def move_duplicate_files(
    paths: list[str],
    destination_root: str,
    *,
    source_root: str,
    action_id: str | None = None,
) -> list[MoveOutcome]:
    """Move files with suffix-on-conflict and skip-identical semantics."""
    action_id = action_id or f'duplicate-move-{uuid.uuid4().hex}'
    outcomes: list[MoveOutcome] = []
    try:
        approved_source_root = validate_path(source_root)
        approved_dest_root = validate_path(destination_root)
    except Exception as exc:
        return [
            MoveOutcome(action_id, path, '', 'error', str(exc))
            for path in paths
        ]

    for source in paths:
        requested = os.path.join(approved_dest_root, os.path.basename(source))
        target = requested
        journal_id = None
        moved_to_target = False
        try:
            validate_path(source, root=approved_source_root)
            if not os.path.isfile(source):
                raise ValueError('duplicate move supports regular files only')

            if os.path.lexists(requested) and _files_identical(source, requested):
                outcomes.append(MoveOutcome(
                    action_id,
                    source,
                    requested,
                    'skipped_identical',
                    'An identical destination file already exists; source was preserved.',
                ))
                continue

            collision = os.path.lexists(requested)
            target = _unique_destination(requested)
            validate_move(
                source,
                target,
                source_root=approved_source_root,
                dest_root=approved_dest_root,
            )
            journal_id = move_journal.plan_action_move(
                action_id,
                source,
                target,
                approved_source_root,
                approved_dest_root,
                source_signature(source),
            )
            shutil.move(source, target)
            moved_to_target = True
            try:
                destination_signature = source_signature(target)
                move_journal.finish_action_move(
                    journal_id,
                    'moved',
                    destination_signature=destination_signature,
                )
            except Exception:
                if not os.path.lexists(source) and os.path.lexists(target):
                    shutil.move(target, source)
                    moved_to_target = False
                raise
            outcomes.append(MoveOutcome(
                action_id,
                source,
                target,
                'conflict_renamed' if collision else 'moved',
                (
                    f'Collision preserved as {os.path.basename(target)}.'
                    if collision else 'Moved.'
                ),
                journal_id,
            ))
        except Exception as exc:
            if moved_to_target and not os.path.lexists(source) and os.path.lexists(target):
                try:
                    shutil.move(target, source)
                except Exception:
                    pass
            if journal_id is not None:
                try:
                    if moved_to_target:
                        move_journal.finish_action_move(
                            journal_id,
                            'moved',
                            destination_signature=source_signature(target),
                            error=f'move completed but rollback failed: {exc}',
                        )
                    else:
                        move_journal.finish_action_move(
                            journal_id, 'error', error=str(exc))
                except Exception:
                    pass
            outcomes.append(MoveOutcome(
                action_id, source, target, 'error', str(exc), journal_id))
    return outcomes


def undo_move_action(action_id: str) -> list[MoveOutcome]:
    """Undo every completed move in an action, preserving changed destinations."""
    outcomes: list[MoveOutcome] = []
    records = move_journal.get_action_moves(action_id)
    for record in reversed(records):
        if record['status'] != 'moved':
            continue
        source = record['source']
        destination = record['destination']
        try:
            validate_source_signature(
                destination, record.get('destination_signature', {}))
            validate_move(
                destination,
                source,
                source_root=record['dest_root'],
                dest_root=record['source_root'],
            )
            os.makedirs(os.path.dirname(source), exist_ok=True)
            shutil.move(destination, source)
            move_journal.mark_action_undone(record['id'])
            outcomes.append(MoveOutcome(
                action_id,
                destination,
                source,
                'undone',
                'Restored.',
                record['id'],
            ))
        except Exception as exc:
            try:
                move_journal.mark_action_undone(record['id'], error=str(exc))
            except Exception:
                pass
            outcomes.append(MoveOutcome(
                action_id,
                destination,
                source,
                'error',
                str(exc),
                record['id'],
            ))
    return outcomes
