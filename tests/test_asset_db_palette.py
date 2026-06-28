from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

import asset_db


def test_asset_db_palette_schema_is_idempotent(tmp_path: Path):
    db = tmp_path / "asset.db"
    con1 = asset_db.init_db(str(db))
    con1.close()
    con2 = asset_db.init_db(str(db))
    cols = [r[1] for r in con2.execute("PRAGMA table_info(asset_files)").fetchall()]
    version = con2.execute("SELECT value FROM db_meta WHERE key='version'").fetchone()[0]
    con2.close()

    assert cols.count("palette_rgb") == 1
    assert cols.count("palette_hex") == 1
    assert version == str(asset_db.DB_VERSION)


def test_build_database_stores_palette_and_finds_by_color(tmp_path: Path):
    root = tmp_path / "organized"
    asset = root / "Stock Photos - General" / "Warm Red"
    asset.mkdir(parents=True)
    Image.new("RGB", (32, 32), (255, 0, 0)).save(asset / "preview.png")
    db = tmp_path / "asset.db"

    result = asset_db.build_database(str(root), str(db))

    assert result["added"] == 1
    con = sqlite3.connect(db)
    row = con.execute("SELECT palette_rgb, palette_hex FROM asset_files").fetchone()
    con.close()
    assert row is not None
    assert row[0] is not None
    assert "#ff0000" in row[1]

    matches = asset_db.find_by_palette("#ff0000", tolerance=10, db_path=str(db))

    assert matches
    assert matches[0]["clean_name"] == "Warm Red"
    assert matches[0]["delta_e"] <= 10
