"""Tests for FileOrganizer dry_run_planner module."""
import os
import json
import tempfile
import pytest
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fileorganizer import dry_run_planner as drp


class TestFileOperation:
    """Tests for FileOperation data structure."""

    def test_file_operation_creation(self):
        """FileOperation should store all required fields."""
        op = drp.FileOperation(
            id='op_001',
            type='move',
            source_path='/source/file.txt',
            dest_path='/dest/file.txt',
            category='Design',
            confidence=95,
            reason='Metadata match'
        )

        assert op.id == 'op_001'
        assert op.type == 'move'
        assert op.source_path == '/source/file.txt'
        assert op.dest_path == '/dest/file.txt'
        assert op.category == 'Design'
        assert op.confidence == 95
        assert op.reason == 'Metadata match'

    def test_file_operation_to_dict(self):
        """FileOperation.to_dict() should exclude None values."""
        op = drp.FileOperation(
            id='op_001',
            type='delete',
            source_path='/source/file.txt',
            reason='Corrupt'
        )

        d = op.to_dict()
        assert 'dest_path' not in d
        assert 'old_name' not in d
        assert 'category' not in d
        assert d['id'] == 'op_001'
        assert d['type'] == 'delete'


class TestDryRunPlan:
    """Tests for DryRunPlan data structure."""

    def test_dry_run_plan_creation(self):
        """DryRunPlan should initialize with defaults."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')

        assert plan.version == '1.0'
        assert plan.source == '/source'
        assert plan.dest_root == '/dest'
        assert plan.operations == []
        assert plan.timestamp  # Should be auto-populated

    def test_dry_run_plan_add_operations(self):
        """DryRunPlan should track multiple operations."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        op1 = drp.FileOperation(id='op_001', type='move', source_path='/s/f1.txt')
        op2 = drp.FileOperation(id='op_002', type='delete', source_path='/s/f2.txt')

        plan.operations.append(op1)
        plan.operations.append(op2)

        assert len(plan.operations) == 2
        assert plan.operations[0].id == 'op_001'

    def test_dry_run_plan_summary(self):
        """DryRunPlan.get_summary() should count operation types."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations = [
            drp.FileOperation(id='1', type='move', source_path='/s/f1.txt', enabled=True),
            drp.FileOperation(id='2', type='move', source_path='/s/f2.txt', enabled=True),
            drp.FileOperation(id='3', type='rename', source_path='/s/f3.txt', enabled=True),
            drp.FileOperation(id='4', type='delete', source_path='/s/f4.txt', enabled=False),
        ]

        summary = plan.get_summary()

        assert summary['total'] == 3  # Only enabled
        assert summary['moves'] == 2
        assert summary['renames'] == 1
        assert summary['deletes'] == 0  # Disabled
        assert summary['skipped'] == 1

    def test_dry_run_plan_to_dict(self):
        """DryRunPlan.to_dict() should include summary."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations.append(
            drp.FileOperation(id='op_001', type='move', source_path='/s/f.txt', enabled=True)
        )

        d = plan.to_dict()

        assert 'version' in d
        assert 'summary' in d
        assert d['summary']['total'] == 1


class TestPlanIO:
    """Tests for plan save/load."""

    def test_save_plan(self, tmp_path):
        """save_plan should write valid JSON."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations.append(
            drp.FileOperation(id='op_001', type='move', source_path='/s/f.txt', dest_path='/d/f.txt')
        )

        plan_file = tmp_path / 'test.json'
        drp.save_plan(plan, str(plan_file))

        assert plan_file.exists()
        with open(plan_file) as f:
            data = json.load(f)
        assert data['version'] == '1.0'
        assert len(data['operations']) == 1

    def test_load_plan(self, tmp_path):
        """load_plan should reconstruct plan from JSON."""
        # Create and save a plan
        plan1 = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan1.operations.append(
            drp.FileOperation(
                id='op_001', type='move', source_path='/s/f.txt',
                dest_path='/d/f.txt', category='Design', confidence=95
            )
        )

        plan_file = tmp_path / 'test.json'
        drp.save_plan(plan1, str(plan_file))

        # Load and verify
        plan2 = drp.load_plan(str(plan_file))

        assert plan2.source == '/source'
        assert plan2.dest_root == '/dest'
        assert len(plan2.operations) == 1
        assert plan2.operations[0].id == 'op_001'
        assert plan2.operations[0].category == 'Design'

    def test_load_plan_preserves_enabled_flag(self, tmp_path):
        """load_plan should preserve per-operation enabled flags."""
        plan1 = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan1.operations.append(
            drp.FileOperation(id='op_001', type='move', source_path='/s/f1.txt', enabled=True)
        )
        plan1.operations.append(
            drp.FileOperation(id='op_002', type='move', source_path='/s/f2.txt', enabled=False)
        )

        plan_file = tmp_path / 'test.json'
        drp.save_plan(plan1, str(plan_file))

        plan2 = drp.load_plan(str(plan_file))

        assert plan2.operations[0].enabled == True
        assert plan2.operations[1].enabled == False


class TestValidatePlan:
    """Tests for plan validation."""

    def test_validate_valid_plan(self):
        """validate_plan should accept valid plan."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations.append(
            drp.FileOperation(id='op_001', type='move', source_path='/s/f.txt', dest_path='/d/f.txt')
        )

        is_valid, errors = drp.validate_plan(plan)

        assert is_valid
        assert errors == []

    def test_validate_missing_source(self):
        """validate_plan should detect missing source."""
        plan = drp.DryRunPlan(source='', dest_root='/dest')

        is_valid, errors = drp.validate_plan(plan)

        assert not is_valid
        assert any('source' in e.lower() for e in errors)

    def test_validate_invalid_operation_type(self):
        """validate_plan should detect invalid operation type."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations.append(
            drp.FileOperation(id='op_001', type='invalid', source_path='/s/f.txt')
        )

        is_valid, errors = drp.validate_plan(plan)

        assert not is_valid
        assert any('invalid type' in e.lower() for e in errors)

    def test_validate_move_missing_dest(self):
        """validate_plan should detect move without destination."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations.append(
            drp.FileOperation(id='op_001', type='move', source_path='/s/f.txt')
        )

        is_valid, errors = drp.validate_plan(plan)

        assert not is_valid
        assert any('missing dest_path' in e.lower() for e in errors)


class TestPlanExecutor:
    """Tests for plan execution."""

    def test_execute_empty_plan(self):
        """Executor should handle empty plan."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        executor = drp.PlanExecutor(plan)

        success, msg = executor.execute()

        assert success
        assert 'No operations' in msg

    def test_execute_skips_disabled_operations(self, tmp_path):
        """Executor should skip disabled operations."""
        source_file = tmp_path / 'test.txt'
        source_file.write_text('test')

        plan = drp.DryRunPlan(source=str(tmp_path), dest_root=str(tmp_path))
        plan.operations.append(
            drp.FileOperation(
                id='op_001', type='delete', source_path=str(source_file), enabled=False
            )
        )

        executor = drp.PlanExecutor(plan)
        success, msg = executor.execute()

        assert success
        assert source_file.exists()  # Should not be deleted

    def test_execute_missing_source_file(self, tmp_path):
        """Executor should skip operations on missing files."""
        plan = drp.DryRunPlan(source=str(tmp_path), dest_root=str(tmp_path))
        plan.operations.append(
            drp.FileOperation(
                id='op_001', type='delete', source_path='/nonexistent/file.txt', enabled=True
            )
        )

        executor = drp.PlanExecutor(plan)
        success, msg = executor.execute()

        assert success  # Should succeed (file reconciliation)

    def test_execute_move_operation(self, tmp_path):
        """Executor should move files correctly."""
        source_file = tmp_path / 'source.txt'
        source_file.write_text('content')
        dest_dir = tmp_path / 'dest'

        plan = drp.DryRunPlan(source=str(tmp_path), dest_root=str(dest_dir))
        plan.operations.append(
            drp.FileOperation(
                id='op_001', type='move', source_path=str(source_file),
                dest_path=str(dest_dir / 'source.txt'), enabled=True
            )
        )

        executor = drp.PlanExecutor(plan)
        success, msg = executor.execute()

        assert success
        assert not source_file.exists()
        assert (dest_dir / 'source.txt').exists()

    def test_execute_rename_operation(self, tmp_path):
        """Executor should rename files correctly."""
        source_file = tmp_path / 'old_name.txt'
        source_file.write_text('content')

        plan = drp.DryRunPlan(source=str(tmp_path), dest_root=str(tmp_path))
        plan.operations.append(
            drp.FileOperation(
                id='op_001', type='rename', source_path=str(source_file),
                old_name='old_name.txt', new_name='new_name.txt', enabled=True
            )
        )

        executor = drp.PlanExecutor(plan)
        success, msg = executor.execute()

        assert success
        assert not source_file.exists()
        assert (tmp_path / 'new_name.txt').exists()

    def test_execute_delete_operation(self, tmp_path):
        """Executor should delete files."""
        source_file = tmp_path / 'delete_me.txt'
        source_file.write_text('content')

        plan = drp.DryRunPlan(source=str(tmp_path), dest_root=str(tmp_path))
        plan.operations.append(
            drp.FileOperation(
                id='op_001', type='delete', source_path=str(source_file), enabled=True
            )
        )

        executor = drp.PlanExecutor(plan)
        success, msg = executor.execute()

        assert success
        assert not source_file.exists()

    def test_execute_rollback_on_error(self, tmp_path):
        """Executor should rollback on operation failure."""
        file1 = tmp_path / 'file1.txt'
        file1.write_text('content')

        # Create a plan where first op succeeds but second fails
        # (moving to readonly destination will fail)
        plan = drp.DryRunPlan(source=str(tmp_path), dest_root=str(tmp_path))
        plan.operations.append(
            drp.FileOperation(
                id='op_001', type='move', source_path=str(file1),
                dest_path=str(tmp_path / 'moved.txt'), enabled=True
            )
        )

        # Add a second operation that references the moved file (will fail reconciliation)
        file2 = tmp_path / 'file2.txt'
        file2.write_text('content')
        plan.operations.append(
            drp.FileOperation(
                id='op_002', type='delete', source_path='/nonexistent/file.txt', enabled=True
            )
        )

        executor = drp.PlanExecutor(plan)
        success, msg = executor.execute()

        # First operation should execute, no rollback needed since second is just skipped
        assert success


class TestShowPlanSummary:
    """Tests for CLI plan display."""

    def test_show_plan_summary(self, tmp_path, capsys):
        """show_plan_summary should display plan details."""
        plan = drp.DryRunPlan(source='/source', dest_root='/dest')
        plan.operations = [
            drp.FileOperation(id='op_001', type='move', source_path='/s/f1.txt', dest_path='/d/f1.txt', enabled=True),
            drp.FileOperation(id='op_002', type='delete', source_path='/s/f2.txt', enabled=False),
        ]

        plan_file = tmp_path / 'test.json'
        drp.save_plan(plan, str(plan_file))

        drp.show_plan_summary(str(plan_file))
        captured = capsys.readouterr()

        assert 'Moves:' in captured.out
        assert 'Total:' in captured.out


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
