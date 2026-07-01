"""Tests for fileorganizer.move_journal — two-phase commit journal + NEXT-37 retention."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import fileorganizer.move_journal as mj


def _make_item(folder_name="test_folder", src="/src/a", dst="/dst/a",
               category="After Effects - Slideshow", confidence=85.0,
               cleaned_name="test_folder"):
    return SimpleNamespace(
        folder_name=folder_name,
        full_source_path=src,
        full_dest_path=dst,
        category=category,
        confidence=confidence,
        cleaned_name=cleaned_name,
    )


class TestMoveJournal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_db = mj._JOURNAL_DB
        mj._JOURNAL_DB = os.path.join(self._tmp, "test_journal.db")
        mj._init()

    def tearDown(self):
        mj._JOURNAL_DB = self._orig_db

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
