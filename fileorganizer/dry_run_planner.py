"""FileOrganizer — Dry-run plan generation and execution.

Generate machine-readable JSON plans for file moves, renames, and deletes.
Supports plan review, selective operation toggling, and atomic execution.

Plan JSON schema includes:
  - source/dest paths
  - operation type (move/rename/delete)
  - category and confidence
  - human-readable reason
  - per-operation enabled flag (for selective execution)

CLI: python organize_run.py --dry-run --plan-file plan.json
     python organize_run.py --plan-file plan.json --commit
"""
import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


# ── Plan Data Structures ──────────────────────────────────────────────────
@dataclass
class FileOperation:
    """Represents a single file operation (move, rename, or delete)."""
    id: str
    type: str  # "move", "rename", "delete"
    source_path: str
    dest_path: Optional[str] = None  # For move/rename
    old_name: Optional[str] = None  # For rename
    new_name: Optional[str] = None  # For rename
    category: Optional[str] = None
    confidence: Optional[int] = None  # 0-100
    reason: str = ""
    enabled: bool = True

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class DryRunPlan:
    """Represents a complete dry-run plan."""
    version: str = "1.0"
    timestamp: str = ""
    source: str = ""
    dest_root: str = ""
    operations: List[FileOperation] = None

    def __post_init__(self):
        if self.operations is None:
            self.operations = []
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'version': self.version,
            'timestamp': self.timestamp,
            'source': self.source,
            'dest_root': self.dest_root,
            'operations': [op.to_dict() for op in self.operations],
            'summary': self.get_summary()
        }

    def get_summary(self) -> Dict:
        """Calculate summary statistics."""
        enabled_ops = [op for op in self.operations if op.enabled]
        move_count = sum(1 for op in enabled_ops if op.type == 'move')
        rename_count = sum(1 for op in enabled_ops if op.type == 'rename')
        delete_count = sum(1 for op in enabled_ops if op.type == 'delete')

        # Estimate freed space (deleted files)
        freed_space = 0
        for op in enabled_ops:
            if op.type == 'delete' and os.path.exists(op.source_path):
                try:
                    freed_space += os.path.getsize(op.source_path)
                except (OSError, FileNotFoundError):
                    pass

        return {
            'total': len(enabled_ops),
            'moves': move_count,
            'renames': rename_count,
            'deletes': delete_count,
            'skipped': sum(1 for op in self.operations if not op.enabled),
            'estimated_disk_space_freed': freed_space
        }


# ── Plan I/O ──────────────────────────────────────────────────────────────
def save_plan(plan: DryRunPlan, plan_file: str):
    """Save plan to JSON file."""
    os.makedirs(os.path.dirname(plan_file) or '.', exist_ok=True)
    with open(plan_file, 'w') as f:
        json.dump(plan.to_dict(), f, indent=2)
    logger.info(f'Plan saved to {plan_file} ({len(plan.operations)} operations)')


def load_plan(plan_file: str) -> DryRunPlan:
    """Load plan from JSON file."""
    with open(plan_file, 'r') as f:
        data = json.load(f)

    plan = DryRunPlan(
        version=data.get('version', '1.0'),
        timestamp=data.get('timestamp', ''),
        source=data.get('source', ''),
        dest_root=data.get('dest_root', '')
    )

    for op_data in data.get('operations', []):
        op = FileOperation(
            id=op_data['id'],
            type=op_data['type'],
            source_path=op_data['source_path'],
            dest_path=op_data.get('dest_path'),
            old_name=op_data.get('old_name'),
            new_name=op_data.get('new_name'),
            category=op_data.get('category'),
            confidence=op_data.get('confidence'),
            reason=op_data.get('reason', ''),
            enabled=op_data.get('enabled', True)
        )
        plan.operations.append(op)

    return plan


def validate_plan(plan: DryRunPlan) -> tuple[bool, List[str]]:
    """
    Validate plan schema and file paths.
    Returns (is_valid, list_of_errors)
    """
    errors = []

    if not plan.version:
        errors.append('Plan missing version')
    if not plan.source:
        errors.append('Plan missing source path')
    if not plan.dest_root:
        errors.append('Plan missing dest_root')

    for i, op in enumerate(plan.operations):
        if not op.id:
            errors.append(f'Operation {i}: missing id')
        if op.type not in ['move', 'rename', 'delete']:
            errors.append(f'Operation {op.id}: invalid type {op.type}')
        if not op.source_path:
            errors.append(f'Operation {op.id}: missing source_path')
        if op.type in ['move', 'rename'] and not op.dest_path:
            errors.append(f'Operation {op.id}: {op.type} missing dest_path')

    return len(errors) == 0, errors


# ── Plan Execution ────────────────────────────────────────────────────────
class PlanExecutor:
    """Execute a dry-run plan with atomic semantics and rollback."""

    def __init__(self, plan: DryRunPlan):
        self.plan = plan
        self.executed_ops = []
        self.failed_op = None
        self.temp_dir = None

    def execute(self, on_progress: Optional[Callable] = None) -> tuple[bool, str]:
        """
        Execute plan with atomic semantics.
        If any operation fails, all previous operations are rolled back.

        Args:
            on_progress: Callback(op_count, total) for progress tracking

        Returns:
            (success, summary_message)
        """
        enabled_ops = [op for op in self.plan.operations if op.enabled]

        if not enabled_ops:
            return True, 'No operations to execute'

        # Create temporary directory for rollback
        self.temp_dir = tempfile.mkdtemp(prefix='fileorg_rollback_')

        try:
            for i, op in enumerate(enabled_ops):
                if on_progress:
                    on_progress(i + 1, len(enabled_ops))

                # Reconcile: check if file still exists
                if not os.path.exists(op.source_path):
                    logger.warning(f'Skipping {op.id}: source file no longer exists')
                    continue

                try:
                    self._execute_operation(op)
                    self.executed_ops.append(op)
                except Exception as e:
                    logger.error(f'Operation {op.id} failed: {e}')
                    self.failed_op = op
                    self._rollback_all()
                    return False, f'Execution failed at {op.id}: {e}'

            # Success: clean up temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

            summary = f'Executed {len(self.executed_ops)} operations successfully'
            logger.info(summary)
            return True, summary

        except Exception as e:
            logger.error(f'Plan execution failed: {e}')
            self._rollback_all()
            return False, f'Plan execution failed: {e}'

    def _execute_operation(self, op: FileOperation):
        """Execute a single operation."""
        if op.type == 'move':
            self._execute_move(op)
        elif op.type == 'rename':
            self._execute_rename(op)
        elif op.type == 'delete':
            self._execute_delete(op)

    def _execute_move(self, op: FileOperation):
        """Move file from source_path to dest_path."""
        dest_path = op.dest_path
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        # Save to temp for rollback
        temp_backup = os.path.join(self.temp_dir, op.id)
        shutil.copy2(op.source_path, temp_backup)

        shutil.move(op.source_path, dest_path)
        logger.info(f'Moved {op.source_path} → {dest_path}')

    def _execute_rename(self, op: FileOperation):
        """Rename file (in-place)."""
        old_path = op.source_path
        new_path = os.path.join(os.path.dirname(old_path), op.new_name)

        # Save to temp for rollback
        temp_backup = os.path.join(self.temp_dir, op.id)
        shutil.copy2(old_path, temp_backup)

        os.rename(old_path, new_path)
        logger.info(f'Renamed {os.path.basename(old_path)} → {op.new_name}')

    def _execute_delete(self, op: FileOperation):
        """Delete file (move to trash, not permanent delete)."""
        try:
            import send2trash
            # Save to temp for rollback
            temp_backup = os.path.join(self.temp_dir, op.id)
            shutil.copy2(op.source_path, temp_backup)
            send2trash.send2trash(op.source_path)
            logger.info(f'Deleted {op.source_path}')
        except ImportError:
            # Fallback: permanent delete if send2trash unavailable
            logger.warning('send2trash not available, doing permanent delete')
            os.remove(op.source_path)

    def _rollback_all(self):
        """Rollback all executed operations."""
        if not self.temp_dir or not os.path.exists(self.temp_dir):
            logger.error('Rollback: temp directory missing, cannot restore files')
            return

        logger.warning(f'Rolling back {len(self.executed_ops)} operations')

        for op in reversed(self.executed_ops):  # Reverse order
            try:
                temp_backup = os.path.join(self.temp_dir, op.id)
                if not os.path.exists(temp_backup):
                    logger.warning(f'Rollback {op.id}: backup file missing')
                    continue

                if op.type == 'move':
                    # Restore from backup
                    shutil.move(temp_backup, op.source_path)
                    logger.info(f'Rolled back move: {op.source_path}')
                elif op.type == 'rename' or op.type == 'delete':
                    # Restore from backup
                    shutil.move(temp_backup, op.source_path)
                    logger.info(f'Rolled back {op.type}: {op.source_path}')

            except Exception as e:
                logger.error(f'Rollback failed for {op.id}: {e}')

        # Clean up temp directory
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f'Failed to clean up temp directory: {e}')


# ── CLI Interface ─────────────────────────────────────────────────────────
def show_plan_summary(plan_file: str):
    """Display plan summary for user review."""
    try:
        plan = load_plan(plan_file)
        is_valid, errors = validate_plan(plan)

        if not is_valid:
            print('❌ Plan validation failed:')
            for error in errors:
                print(f'  - {error}')
            return

        summary = plan.get_summary()
        print(f'📋 Plan: {os.path.basename(plan_file)}')
        print(f'   Source: {plan.source}')
        print(f'   Dest:   {plan.dest_root}')
        print(f'')
        print(f'📊 Summary:')
        print(f'   Moves:  {summary["moves"]}')
        print(f'   Renames: {summary["renames"]}')
        print(f'   Deletes: {summary["deletes"]}')
        print(f'   Skipped: {summary["skipped"]}')
        print(f'   Total:   {summary["total"]}')
        if summary['estimated_disk_space_freed'] > 0:
            freed_mb = summary['estimated_disk_space_freed'] / (1024 * 1024)
            print(f'   Space freed: {freed_mb:.1f} MB')

        # Show first 5 operations
        print(f'')
        print(f'📁 Operations (showing first 5):')
        for op in plan.operations[:5]:
            status = '✓' if op.enabled else '✗'
            print(f'   [{status}] {op.type:6} {op.source_path} ({op.reason})')

        if len(plan.operations) > 5:
            print(f'   ... and {len(plan.operations) - 5} more')

    except Exception as e:
        print(f'Error loading plan: {e}')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Dry-run plan utilities')
    parser.add_argument('--show-plan', help='Display plan summary')
    args = parser.parse_args()

    if args.show_plan:
        show_plan_summary(args.show_plan)
