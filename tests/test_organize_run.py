import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import organize_run as runner


class OrganizeRunPlanTests(unittest.TestCase):
    def setUp(self):
        self._old_journal = runner.JOURNAL_FILE
        self._old_log = runner.LOG_FILE
        self._old_get_dest_root = runner.get_dest_root

    def tearDown(self):
        runner.JOURNAL_FILE = self._old_journal
        runner.LOG_FILE = self._old_log
        runner.get_dest_root = self._old_get_dest_root

    def _configure_temp_runner(self, tmp: str) -> tuple[Path, Path]:
        root = Path(tmp)
        src_root = root / "src"
        dest_root = root / "organized"
        src_root.mkdir()
        dest_root.mkdir()
        runner.JOURNAL_FILE = str(root / "moves.db")
        runner.LOG_FILE = str(root / "run.log")
        runner.get_dest_root = lambda: str(dest_root)
        return src_root, dest_root

    def test_build_move_plan_routes_low_confidence_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_root, dest_root = self._configure_temp_runner(tmp)
            (src_root / "Template A").mkdir()

            plan = runner.build_move_plan(
                [
                    (
                        {
                            "name": "Template A",
                            "clean_name": "Intro: Template",
                            "category": "After Effects - Opener & Intro",
                            "confidence": 40,
                        },
                        {"folder": str(src_root), "name": "Template A"},
                    )
                ],
                source_mode="ae",
                plan_id="test-plan",
            )

            self.assertEqual(plan.item_count, 1)
            item = plan.items[0]
            self.assertEqual(item["category"], "After Effects - Intro & Opener")
            self.assertTrue(item["low_confidence"])
            self.assertIn("_Review", item["dest"])
            self.assertIn(str(dest_root), item["dest"])
            self.assertTrue(item["dest"].endswith("Intro- Template"))

    def test_build_move_plan_reserves_duplicate_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_root, _ = self._configure_temp_runner(tmp)
            (src_root / "One").mkdir()
            (src_root / "Two").mkdir()

            plan = runner.build_move_plan(
                [
                    (
                        {"name": "One", "clean_name": "Same Name", "category": "Mockups", "confidence": 90},
                        {"folder": str(src_root), "name": "One"},
                    ),
                    (
                        {"name": "Two", "clean_name": "Same Name", "category": "Mockups", "confidence": 90},
                        {"folder": str(src_root), "name": "Two"},
                    ),
                ],
                source_mode="design",
                plan_id="collision-plan",
            )

            self.assertEqual(plan.item_count, 2)
            self.assertNotEqual(plan.items[0]["dest"], plan.items[1]["dest"])
            self.assertTrue(plan.items[1]["dest"].endswith("Same Name (1)"))

    def test_build_move_plan_flags_destination_duplicate_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_root, dest_root = self._configure_temp_runner(tmp)
            src = src_root / "Incoming"
            src.mkdir()
            (src / "preview-copy.png").write_bytes(b"same image bytes")
            existing = dest_root / "Mockups" / "Existing Asset"
            existing.mkdir(parents=True)
            existing_file = existing / "preview.png"
            existing_file.write_bytes(b"same image bytes")

            plan = runner.build_move_plan(
                [
                    (
                        {"name": "Incoming", "clean_name": "Incoming", "category": "Mockups", "confidence": 90},
                        {"folder": str(src_root), "name": "Incoming"},
                    ),
                ],
                source_mode="design",
                plan_id="dedup-plan",
            )

            self.assertEqual(plan.item_count, 1)
            item = plan.items[0]
            self.assertEqual(item["status"], "blocked_duplicate")
            self.assertEqual(item["reason"], "destination_duplicate")
            self.assertEqual(item["duplicate_policy"], "skip")
            self.assertEqual(item["duplicate_matches"][0]["source_file"], str(src / "preview-copy.png"))
            self.assertEqual(item["duplicate_matches"][0]["existing_file"], str(existing_file))

    def test_apply_move_plan_skips_duplicate_and_journals_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_root, dest_root = self._configure_temp_runner(tmp)
            src = src_root / "Incoming"
            src.mkdir()
            source_file = src / "preview-copy.png"
            source_file.write_bytes(b"same image bytes")
            existing = dest_root / "Mockups" / "Existing Asset"
            existing.mkdir(parents=True)
            existing_file = existing / "preview.png"
            existing_file.write_bytes(b"same image bytes")

            plan = runner.build_move_plan(
                [
                    (
                        {"name": "Incoming", "clean_name": "Incoming", "category": "Mockups", "confidence": 90},
                        {"folder": str(src_root), "name": "Incoming"},
                    ),
                ],
                source_mode="design",
                plan_id="dedup-apply",
            )

            result = runner.apply_move_plan(plan, dry_run=False, verbose=False)

            self.assertEqual(result["moved"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertTrue(src.exists())
            con = sqlite3.connect(runner.JOURNAL_FILE)
            row = con.execute(
                "SELECT status, duplicate_source_file, duplicate_existing_file, duplicate_sha256 "
                "FROM moves"
            ).fetchone()
            con.close()
            self.assertEqual(row[0], "skipped_duplicate")
            self.assertEqual(row[1], str(source_file))
            self.assertEqual(row[2], str(existing_file))
            self.assertEqual(len(row[3]), 64)

    def test_apply_move_plan_records_status_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_root, _ = self._configure_temp_runner(tmp)
            (src_root / "Template B").mkdir()

            plan = runner.build_move_plan(
                [
                    (
                        {
                            "name": "Template B",
                            "clean_name": "Template B",
                            "category": "Flyers",
                            "confidence": 95,
                        },
                        {"folder": str(src_root), "name": "Template B"},
                    )
                ],
                source_mode="design",
                plan_id="apply-plan",
            )

            result = runner.apply_move_plan(plan, dry_run=False, verbose=False)
            self.assertEqual(result["moved"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertFalse((src_root / "Template B").exists())
            self.assertTrue(Path(plan.items[0]["dest"]).exists())

            con = sqlite3.connect(runner.JOURNAL_FILE)
            row = con.execute("SELECT status, plan_id, run_id FROM moves").fetchone()
            con.close()
            self.assertEqual(row[0], "done")
            self.assertEqual(row[1], "apply-plan")
            self.assertEqual(row[2], result["run_id"])

            report_path = Path(tmp) / "report.md"
            written = runner.generate_report(result["run_id"], str(report_path))
            self.assertEqual(str(report_path), written)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("FileOrganizer Move Report", report)
            self.assertIn("Flyers", report)

    def test_old_journal_schema_is_migrated_before_status_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.JOURNAL_FILE = str(root / "old_moves.db")
            con = sqlite3.connect(runner.JOURNAL_FILE)
            con.executescript(
                """
                CREATE TABLE moves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src TEXT NOT NULL,
                    dest TEXT NOT NULL,
                    disk_name TEXT NOT NULL,
                    clean_name TEXT,
                    category TEXT,
                    confidence INTEGER,
                    moved_at TEXT NOT NULL,
                    undone_at TEXT
                );
                INSERT INTO moves (src, dest, disk_name, clean_name, category, confidence, moved_at)
                VALUES ('a', 'b', 'disk', 'clean', 'cat', 90, '2026-04-28T00:00:00Z');
                """
            )
            con.commit()
            con.close()

            migrated = runner._journal_conn()
            columns = {row[1] for row in migrated.execute("PRAGMA table_info(moves)").fetchall()}
            status = migrated.execute("SELECT status FROM moves").fetchone()[0]
            migrated.close()

            self.assertIn("status", columns)
            self.assertIn("run_id", columns)
            self.assertIn("duplicate_source_file", columns)
            self.assertIn("duplicate_existing_file", columns)
            self.assertIn("duplicate_sha256", columns)
            self.assertEqual(status, "done")


if __name__ == "__main__":
    unittest.main()
