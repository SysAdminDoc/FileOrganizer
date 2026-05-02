"""Tests for fileorganizer.provenance — source-domain parser + asset_db migration."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fileorganizer.provenance import (  # noqa: E402
    all_known_domains,
    all_piracy_domains,
    display_domain,
    is_piracy_domain,
    parse_source_domain,
)


# ── Empty / null inputs ────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["", "   ", None])
def test_empty_input_returns_none(name):
    assert parse_source_domain(name) is None


# ── Marketplace recognition ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        # Videohive (3 forms + numeric prefix)
        ("Videohive_Modern_Logo_43215678", "videohive.net"),
        ("VH-12345678-broadcast-pack", "videohive.net"),
        ("12345678-modern-titles", "videohive.net"),
        ("28331308 promo opener", "videohive.net"),
        # MotionElements
        ("17385619_MotionElements_corporate_intro", "motionelements.com"),
        # Envato Elements
        ("elements-modern-broadcast-XYZ123-2026-04-01", "elements.envato.com"),
        # AEriver
        ("aeriver.com-pack-9821", "aeriver.com"),
        # Creative Market
        ("cm_4804020", "creativemarket.com"),
        # DesignBundles
        ("db_7116381", "designbundles.net"),
        # Motion Array
        ("motionarray-broadcast-99211", "motionarray.com"),
        ("MA-12345-template", "motionarray.com"),
        # Freepik
        ("freepik-flyer-12345", "freepik.com"),
        # Adobe Stock
        ("AS_123456789_business_cards", "stock.adobe.com"),
    ],
)
def test_marketplace_recognition(name, expected):
    assert parse_source_domain(name) == expected


# ── Piracy blocklist ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("12345678-INTRO-HD.NET", "intro-hd.net"),
        ("freegfx_pack_2026", "freegfx.net"),
        ("AIDOWNLOAD.NET-template-bundle", "aidownload.net"),
        ("ShareAE.com-modern-titles", "shareae.com"),
        ("share.ae-modern-titles", "shareae.com"),  # audit fix: dotted variant
        ("GFXDRUG.COM-stuff", "gfxdrug.com"),
        ("graphicux-flyer-pack", "graphicux.com"),
        ("gfxlooks-mockup-bundle", "gfxlooks.com"),
    ],
)
def test_piracy_recognition(name, expected):
    assert parse_source_domain(name) == expected
    assert is_piracy_domain(expected)


def test_videohive_numeric_prefix_requires_separator(tmp_path):
    """Audit fix: bare numeric folders (no separator after the ID) must NOT
    be tagged as Videohive — that pattern is a strong false-positive risk."""
    # Healthy: 8-9 digits + separator (the canonical Videohive folder shape)
    assert parse_source_domain("12345678-promo") == "videohive.net"
    assert parse_source_domain("123456789_titles") == "videohive.net"
    # Negative cases: 8-9 digits with no separator after.
    assert parse_source_domain("12345678abc") is None
    assert parse_source_domain("12345678") is None
    assert parse_source_domain("123456789xyz") is None


def test_display_domain_strips_piracy():
    assert display_domain("intro-hd.net") == ""
    assert display_domain("freegfx.net") == ""
    assert display_domain("videohive.net") == "videohive.net"
    assert display_domain(None) == ""
    assert display_domain("") == ""


def test_piracy_overrides_marketplace():
    """A `123-INTRO-HD.NET` Videohive bundle should resolve to intro-hd.net,
    not videohive.net — IP origin matters more than upstream vendor for UI."""
    name = "12345678-INTRO-HD.NET-broadcast-titles"
    assert parse_source_domain(name) == "intro-hd.net"


def test_unknown_name_returns_none():
    assert parse_source_domain("totally-random-unsourced-folder-name") is None
    assert parse_source_domain("MyCustomProject") is None


def test_known_domains_listing():
    domains = all_known_domains()
    assert "videohive.net" in domains
    assert "creativemarket.com" in domains
    assert "motionelements.com" in domains
    # Stable ordering — calling twice returns the same list
    assert all_known_domains() == domains


def test_piracy_domains_listing():
    piracy = all_piracy_domains()
    assert "intro-hd.net" in piracy
    assert "gfxdrug.com" in piracy
    # Sorted alphabetically
    assert piracy == sorted(piracy)


# ── asset_db migration ────────────────────────────────────────────────────


def test_init_db_adds_provenance_columns(tmp_path):
    """Fresh DB should have source_domain + first_seen_ts on the assets table."""
    import asset_db

    db_path = tmp_path / "fp.db"
    con = asset_db.init_db(str(db_path))
    cols = {row[1] for row in con.execute("PRAGMA table_info(assets)").fetchall()}
    assert "source_domain" in cols
    assert "first_seen_ts" in cols
    con.close()


def test_init_db_migration_idempotent(tmp_path):
    """Running init_db twice on the same path must not raise or duplicate columns."""
    import asset_db

    db_path = tmp_path / "fp.db"
    con1 = asset_db.init_db(str(db_path))
    con1.close()
    con2 = asset_db.init_db(str(db_path))
    cols = [row[1] for row in con2.execute("PRAGMA table_info(assets)").fetchall()]
    # Columns exist exactly once.
    assert cols.count("source_domain") == 1
    assert cols.count("first_seen_ts") == 1
    con2.close()


def test_init_db_migrates_legacy_db_without_provenance(tmp_path):
    """A pre-N-12 DB (no provenance columns) gets migrated on first init_db()."""
    import asset_db

    db_path = tmp_path / "legacy.db"
    # Simulate the pre-N-12 schema: assets table without source_domain / first_seen_ts.
    with sqlite3.connect(str(db_path)) as legacy:
        legacy.execute("""
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clean_name TEXT NOT NULL,
                category TEXT NOT NULL,
                marketplace TEXT,
                confidence INTEGER DEFAULT 0,
                disk_name TEXT,
                file_count INTEGER DEFAULT 0,
                total_bytes INTEGER DEFAULT 0,
                skipped_bytes INTEGER DEFAULT 0,
                folder_fingerprint TEXT UNIQUE,
                preview_image TEXT,
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Insert a pre-existing row to confirm it survives the migration.
        legacy.execute(
            "INSERT INTO assets (clean_name, category, added_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("OldAsset", "_Review", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

    con = asset_db.init_db(str(db_path))
    cols = {row[1] for row in con.execute("PRAGMA table_info(assets)").fetchall()}
    assert "source_domain" in cols
    assert "first_seen_ts" in cols
    # Pre-existing row still there.
    row = con.execute("SELECT clean_name, source_domain, first_seen_ts FROM assets").fetchone()
    assert row[0] == "OldAsset"
    assert row[1] is None  # back-fills lazily on next index pass
    assert row[2] is None
    con.close()


def test_backfill_populates_null_columns(tmp_path):
    """Back-fill walks rows where source_domain or first_seen_ts is NULL and
    sets them from disk_name + added_at."""
    import asset_db
    db_path = tmp_path / "fp.db"
    con = asset_db.init_db(str(db_path))
    # Two pre-N-12 rows (both NULLs) + one fully populated row.
    con.execute(
        "INSERT INTO assets (clean_name, category, disk_name, added_at, updated_at, "
        "                   source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("modern logo", "After Effects - Logo Reveal",
         "12345678-modern-logo-reveal", "2026-04-15T10:00:00Z", "2026-04-15T10:00:00Z",
         None, None),
    )
    con.execute(
        "INSERT INTO assets (clean_name, category, disk_name, added_at, updated_at, "
        "                   source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("freegfx pack", "Print - Other",
         "freegfx_pack_2026", "2026-04-16T11:00:00Z", "2026-04-16T11:00:00Z",
         None, None),
    )
    con.execute(
        "INSERT INTO assets (clean_name, category, disk_name, added_at, updated_at, "
        "                   source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("already populated", "After Effects - Other",
         "12345678-already-populated", "2026-04-17T12:00:00Z", "2026-04-17T12:00:00Z",
         "videohive.net", 1700000000),
    )
    con.commit()
    con.close()

    summary = asset_db.cmd_backfill_provenance(str(db_path), dry_run=False)

    assert summary['rows_scanned'] == 2  # only NULL-column rows
    assert summary['rows_updated'] == 2
    assert summary['domains'].get('videohive.net') == 1
    assert summary['domains'].get('freegfx.net') == 1
    assert summary['no_match'] == 0
    assert summary['dry_run'] is False

    # Verify the populated row was NOT touched.
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT source_domain, first_seen_ts FROM assets WHERE clean_name='already populated'"
    ).fetchone()
    assert row['source_domain'] == "videohive.net"
    assert row['first_seen_ts'] == 1700000000
    # Verify back-filled rows.
    row1 = con.execute(
        "SELECT source_domain, first_seen_ts FROM assets WHERE clean_name='modern logo'"
    ).fetchone()
    assert row1['source_domain'] == "videohive.net"
    assert row1['first_seen_ts'] is not None
    assert row1['first_seen_ts'] > 0
    row2 = con.execute(
        "SELECT source_domain, first_seen_ts FROM assets WHERE clean_name='freegfx pack'"
    ).fetchone()
    assert row2['source_domain'] == "freegfx.net"
    assert row2['first_seen_ts'] is not None
    con.close()


def test_backfill_dry_run_does_not_commit(tmp_path):
    import asset_db
    db_path = tmp_path / "fp.db"
    con = asset_db.init_db(str(db_path))
    con.execute(
        "INSERT INTO assets (clean_name, category, disk_name, added_at, updated_at, "
        "                   source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("dry run", "After Effects - Other",
         "VH-99887766-dry-run", "2026-04-18T09:00:00Z", "2026-04-18T09:00:00Z",
         None, None),
    )
    con.commit()
    con.close()

    summary = asset_db.cmd_backfill_provenance(str(db_path), dry_run=True)
    assert summary['dry_run'] is True
    assert summary['rows_updated'] == 1

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT source_domain, first_seen_ts FROM assets").fetchone()
    assert row['source_domain'] is None  # nothing committed
    assert row['first_seen_ts'] is None
    con.close()


def test_backfill_idempotent(tmp_path):
    """Second back-fill is a no-op once columns are populated."""
    import asset_db
    db_path = tmp_path / "fp.db"
    con = asset_db.init_db(str(db_path))
    con.execute(
        "INSERT INTO assets (clean_name, category, disk_name, added_at, updated_at, "
        "                   source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("once", "After Effects - Other",
         "12345678-modern", "2026-04-19T09:00:00Z", "2026-04-19T09:00:00Z",
         None, None),
    )
    con.commit()
    con.close()

    s1 = asset_db.cmd_backfill_provenance(str(db_path), dry_run=False)
    s2 = asset_db.cmd_backfill_provenance(str(db_path), dry_run=False)
    assert s1['rows_updated'] == 1
    assert s2['rows_scanned'] == 0
    assert s2['rows_updated'] == 0


def test_backfill_unmatched_still_sets_first_seen(tmp_path):
    """A row whose disk_name matches no known marketplace pattern should still
    get first_seen_ts populated (source_domain stays NULL).
    """
    import asset_db
    db_path = tmp_path / "fp.db"
    con = asset_db.init_db(str(db_path))
    con.execute(
        "INSERT INTO assets (clean_name, category, disk_name, added_at, updated_at, "
        "                   source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("custom",  "After Effects - Other",
         "MyOwnAssetFolder", "2026-04-20T09:00:00Z", "2026-04-20T09:00:00Z",
         None, None),
    )
    con.commit()
    con.close()

    summary = asset_db.cmd_backfill_provenance(str(db_path), dry_run=False)
    assert summary['no_match'] == 1
    assert summary['rows_updated'] == 1

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT source_domain, first_seen_ts FROM assets").fetchone()
    assert row['source_domain'] is None
    assert row['first_seen_ts'] is not None  # back-fill still set the timestamp
    con.close()


def test_first_seen_ts_immutable_via_coalesce(tmp_path):
    """Simulate the cmd_build UPDATE path: a row's first_seen_ts must not change
    when COALESCE is the source of truth."""
    import asset_db

    db_path = tmp_path / "fp.db"
    con = asset_db.init_db(str(db_path))
    # Insert a row with a known first_seen_ts.
    con.execute(
        "INSERT INTO assets "
        "(clean_name, category, added_at, updated_at, source_domain, first_seen_ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("Asset1", "Fonts & Typography", "2026-01-01T00:00:00Z",
         "2026-01-01T00:00:00Z", "videohive.net", 1700000000),
    )
    asset_id = con.execute("SELECT id FROM assets").fetchone()[0]
    # Run the same UPDATE shape cmd_build uses.
    con.execute("""
        UPDATE assets SET
            updated_at=?,
            source_domain=COALESCE(source_domain, ?),
            first_seen_ts=COALESCE(first_seen_ts, ?)
        WHERE id=?
    """, ("2026-05-01T00:00:00Z", "creativemarket.com", 1800000000, asset_id))
    row = con.execute(
        "SELECT source_domain, first_seen_ts FROM assets WHERE id=?", (asset_id,)
    ).fetchone()
    assert row[0] == "videohive.net"  # NOT overwritten
    assert row[1] == 1700000000       # NOT overwritten
    con.close()
