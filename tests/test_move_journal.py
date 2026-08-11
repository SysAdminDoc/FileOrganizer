"""Tests for fileorganizer.move_journal — two-phase commit journal + NEXT-37 retention."""
import os
import sqlite3
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import fileorganizer.move_journal as mj
import fileorganizer.config as config


def _make_item(folder_name="test_folder", src="/src/a", dst="/dst/a",
               category="After Effects - Slideshow", confidence=85.0,
               cleaned_name="test_folder", source_root="", dest_root=""):
    return SimpleNamespace(
        folder_name=folder_name,
        full_source_path=src,
        full_dest_path=dst,
        category=category,
        confidence=confidence,
        cleaned_name=cleaned_name,
        source_root=source_root,
        dest_root=dest_root,
    )


class TestMoveJournal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_db = mj._JOURNAL_DB
        self._orig_protected_paths = config._cached_protected_paths
        mj._JOURNAL_DB = os.path.join(self._tmp, "test_journal.db")
        config._cached_protected_paths = {
            "system": [], "custom": [], "enabled": False,
        }
        mj._init()

    def tearDown(self):
        mj._JOURNAL_DB = self._orig_db
        config._cached_protected_paths = self._orig_protected_paths

    def test_plan_run_inserts_pending(self):
        items = [(0, _make_item()), (1, _make_item(folder_name="b"))]
        mj.plan_run("run-1", items)
        pending = mj.get_pending_moves("run-1")
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["folder_name"], "test_folder")
        self.assertEqual(pending[1]["folder_name"], "b")

    def test_mark_done_updates_status(self):
        mj.plan_run("run-2", [(0, _make_item())])
        mj.mark_done("run-2", 0, "done")
        pending = mj.get_pending_moves("run-2")
        self.assertEqual(len(pending), 0)

    def test_clear_run_deletes_all(self):
        mj.plan_run("run-3", [(0, _make_item()), (1, _make_item())])
        mj.clear_run("run-3")
        pending = mj.get_pending_moves("run-3")
        self.assertEqual(len(pending), 0)

    def test_clear_run_retains_completed_history(self):
        mj.plan_run("run-3-done", [(0, _make_item())])
        mj.mark_done("run-3-done", 0, "done")
        mj.clear_run("run-3-done")
        con = sqlite3.connect(mj._JOURNAL_DB)
        count = con.execute(
            "SELECT COUNT(*) FROM moves WHERE run_id='run-3-done'"
        ).fetchone()[0]
        con.close()
        self.assertEqual(count, 1)

    def test_history_and_item_undo_restore_a_completed_run_move(self):
        source_root = os.path.join(self._tmp, "source")
        dest_root = os.path.join(self._tmp, "destination")
        source = os.path.join(source_root, "asset")
        destination = os.path.join(dest_root, "asset")
        os.makedirs(source_root)
        os.makedirs(dest_root)
        with open(source, "w", encoding="utf-8") as stream:
            stream.write("asset")

        item = _make_item(
            src=source,
            dst=destination,
            source_root=source_root,
            dest_root=dest_root,
        )
        mj.plan_run("run-history", [(0, item)])
        shutil.move(source, destination)
        mj.mark_done(
            "run-history",
            0,
            "done",
            destination_signature=mj.source_signature(destination),
            merge_manifest=[],
        )

        history = mj.get_move_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["kind"], "run")
        self.assertEqual(history[0]["source"], source)
        self.assertTrue(history[0]["can_undo"])

        result = mj.undo_move_entry(history[0]["id"])

        self.assertEqual(result["status"], "undone")
        self.assertTrue(os.path.isfile(source))
        self.assertFalse(os.path.lexists(destination))
        self.assertEqual(mj.get_move_history()[0]["status"], "undone")

    def test_item_undo_refuses_changed_destination(self):
        source_root = os.path.join(self._tmp, "source-guard")
        dest_root = os.path.join(self._tmp, "destination-guard")
        source = os.path.join(source_root, "asset")
        destination = os.path.join(dest_root, "asset")
        os.makedirs(source_root)
        os.makedirs(dest_root)
        with open(source, "w", encoding="utf-8") as stream:
            stream.write("original")
        item = _make_item(
            src=source,
            dst=destination,
            source_root=source_root,
            dest_root=dest_root,
        )
        mj.plan_run("run-guard", [(0, item)])
        shutil.move(source, destination)
        mj.mark_done(
            "run-guard",
            0,
            "done",
            destination_signature=mj.source_signature(destination),
            merge_manifest=[],
        )
        with open(destination, "w", encoding="utf-8") as stream:
            stream.write("changed")

        move_id = mj.get_move_history()[0]["id"]
        with self.assertRaises(ValueError):
            mj.undo_move_entry(move_id)
        self.assertFalse(os.path.exists(source))
        self.assertTrue(os.path.isfile(destination))

    def test_action_history_and_undo_restore_a_completed_action(self):
        source_root = os.path.join(self._tmp, "action-source")
        dest_root = os.path.join(self._tmp, "action-destination")
        source = os.path.join(source_root, "asset.bin")
        destination = os.path.join(dest_root, "asset.bin")
        os.makedirs(source_root)
        os.makedirs(dest_root)
        with open(source, "wb") as stream:
            stream.write(b"action")

        move_id = mj.plan_action_move(
            "history-action", source, destination, source_root, dest_root,
            mj.source_signature(source),
        )
        shutil.move(source, destination)
        mj.finish_action_move(
            move_id,
            "moved",
            destination_signature=mj.source_signature(destination),
        )

        history = mj.get_move_history()
        action = next(entry for entry in history if entry["kind"] == "action")
        self.assertEqual(action["action_id"], "history-action")
        self.assertTrue(action["can_undo"])
        mj.undo_action_move(action["id"])
        self.assertTrue(os.path.isfile(source))
        self.assertFalse(os.path.lexists(destination))

    def test_clear_all_pending(self):
        mj.plan_run("run-4", [(0, _make_item())])
        mj.plan_run("run-5", [(0, _make_item())])
        mj.clear_all()
        self.assertEqual(mj.get_pending_summary(), [])

    def test_get_pending_summary(self):
        mj.plan_run("run-6", [(0, _make_item()), (1, _make_item())])
        summary = mj.get_pending_summary()
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0], ("run-6", 2))

    def test_cleanup_expired_deletes_old(self):
        mj.plan_run("run-7", [(0, _make_item())])
        mj.mark_done("run-7", 0, "done")
        con = sqlite3.connect(mj._JOURNAL_DB)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime('%Y-%m-%dT%H:%M:%SZ')
        con.execute("UPDATE moves SET ts_done=? WHERE run_id='run-7'", (old_ts,))
        con.commit()
        con.close()
        mj.cleanup_expired(days=90)
        con = sqlite3.connect(mj._JOURNAL_DB)
        count = con.execute("SELECT COUNT(*) FROM moves WHERE run_id='run-7'").fetchone()[0]
        con.close()
        self.assertEqual(count, 0)

    def test_cleanup_expired_keeps_recent(self):
        mj.plan_run("run-8", [(0, _make_item())])
        mj.mark_done("run-8", 0, "done")
        mj.cleanup_expired(days=90)
        con = sqlite3.connect(mj._JOURNAL_DB)
        count = con.execute("SELECT COUNT(*) FROM moves WHERE run_id='run-8'").fetchone()[0]
        con.close()
        self.assertEqual(count, 1)

    def test_vacuum_runs_without_error(self):
        mj.plan_run("run-9", [(0, _make_item())])
        mj.vacuum()

    def test_confidence_stored_correctly(self):
        mj.plan_run("run-10", [(0, _make_item(confidence=92.5))])
        pending = mj.get_pending_moves("run-10")
        self.assertAlmostEqual(pending[0]["confidence"], 92.5, places=1)


if __name__ == "__main__":
    unittest.main()
