"""Safe folder reclassification used by the Browse drag-and-drop surface."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass

from fileorganizer import move_journal
from fileorganizer.adaptive_corrector import AdaptiveCorrector
from fileorganizer.cache import (
    increment_user_corrections,
    save_correction,
    user_corrections_count,
)
from fileorganizer.folder_cache import compute_folder_fingerprint
from fileorganizer.path_safety import (
    PathSafetyError,
    absolute_path,
    source_signature,
    validate_move,
    validate_path,
    validate_storage_name,
)


@dataclass(frozen=True)
class ReclassificationResult:
    """Outcome of one Browse drag/drop reclassification."""

    source: str
    destination: str
    old_category: str
    new_category: str
    fingerprint: str
    correction_recorded: bool
    user_corrections: int
    status: str = "moved"
    message: str = ""


def reclassify_folder(
    source_path: str,
    library_root: str,
    target_category: str,
    *,
    original_confidence: int = 0,
) -> ReclassificationResult:
    """Move one category child and persist an exact-fingerprint correction.

    The source is validated under ``library_root`` and journaled before the
    move. The fingerprint is captured before mutation and supplied to the
    adaptive store after the move, so a successful move never loses its
    learning signal merely because the source path changed.
    """
    approved_root = validate_path(library_root)
    source = validate_path(source_path, root=approved_root)
    if not os.path.isdir(source):
        raise PathSafetyError("Browse reclassification only supports folders")
    target = validate_storage_name(target_category.strip())
    old_category = os.path.basename(os.path.dirname(source))
    if old_category == target:
        return ReclassificationResult(
            source=source,
            destination=source,
            old_category=old_category,
            new_category=target,
            fingerprint=compute_folder_fingerprint(source),
            correction_recorded=False,
            user_corrections=user_corrections_count(),
            status="unchanged",
            message="Folder is already in that category.",
        )

    fingerprint = compute_folder_fingerprint(source)
    if not fingerprint:
        raise PathSafetyError("could not fingerprint the folder before reclassification")

    target_dir = absolute_path(os.path.join(approved_root, target))
    validate_path(target_dir, root=approved_root, require_exists=False)
    os.makedirs(target_dir, exist_ok=True)
    destination = absolute_path(os.path.join(target_dir, os.path.basename(source)))
    validate_move(
        source,
        destination,
        source_root=approved_root,
        dest_root=approved_root,
    )

    action_id = f"reclassify-{uuid.uuid4().hex}"
    journal_id = move_journal.plan_action_move(
        action_id,
        source,
        destination,
        approved_root,
        approved_root,
        source_signature(source),
    )
    moved = False
    try:
        shutil.move(source, destination)
        moved = True
        move_journal.finish_action_move(
            journal_id,
            "moved",
            destination_signature=source_signature(destination),
        )
    except Exception as exc:
        if moved and os.path.lexists(destination) and not os.path.lexists(source):
            try:
                shutil.move(destination, source)
            except OSError:
                pass
        move_journal.finish_action_move(journal_id, "error", error=str(exc))
        raise

    correction_recorded = False
    try:
        corrector = AdaptiveCorrector()
        corrector.record_correction(
            os.path.basename(source),
            destination,
            target,
            original_confidence,
            fingerprint_override=fingerprint,
        )
        # Retain the name-based compatibility entry used by older scans.
        save_correction(os.path.basename(source), target)
        correction_recorded = True
    except Exception:
        # The move is journaled and complete; report the learning failure to
        # the caller rather than pretending the correction was persisted.
        correction_recorded = False

    count = increment_user_corrections() if correction_recorded else user_corrections_count()
    message = (
        f"Moved {os.path.basename(source)} to {target}."
        if correction_recorded else
        f"Moved {os.path.basename(source)} to {target}; correction was not persisted."
    )
    return ReclassificationResult(
        source=source,
        destination=destination,
        old_category=old_category,
        new_category=target,
        fingerprint=fingerprint,
        correction_recorded=correction_recorded,
        user_corrections=count,
        message=message,
    )


__all__ = ["ReclassificationResult", "reclassify_folder"]
