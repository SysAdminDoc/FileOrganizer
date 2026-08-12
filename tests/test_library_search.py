"""Contracts for the local FTS5 library search index."""

from __future__ import annotations

from fileorganizer.library_search import index_entry, index_library, search_library


def test_indexed_paths_and_descriptions_are_searchable(tmp_path):
    root = tmp_path / "organized"
    asset = root / "Documents" / "Invoices"
    asset.mkdir(parents=True)
    document = asset / "2026-08-invoice.pdf"
    document.write_bytes(b"pdf")
    db_path = tmp_path / "search.db"

    assert index_library(root, db_path=str(db_path)) == 3
    index_entry(
        asset,
        library_root=root,
        category="Documents",
        description="Scanned vendor invoice for the August campaign",
        kind="folder",
        db_path=str(db_path),
    )

    results = search_library("show August invoice scans", library_root=root, db_path=str(db_path))

    assert results
    assert results[0]["path"] == str(asset)
    assert results[0]["description"].startswith("Scanned vendor invoice")
    assert results[0]["citation"].startswith("[1] ")


def test_natural_language_filters_limit_results(tmp_path):
    root = tmp_path / "organized"
    category = root / "Photos" / "Landscape"
    category.mkdir(parents=True)
    image = category / "mountain-lake.jpg"
    image.write_bytes(b"image")
    db_path = tmp_path / "search.db"
    index_library(root, db_path=str(db_path))

    results = search_library(
        "mountain category:Photos type:file",
        library_root=root,
        db_path=str(db_path),
    )

    assert len(results) == 1
    assert results[0]["name"] == "mountain-lake.jpg"
    assert results[0]["kind"] == "file"


def test_reindex_preserves_move_time_description(tmp_path):
    root = tmp_path / "organized"
    asset = root / "Design" / "Product"
    asset.mkdir(parents=True)
    (asset / "hero.png").write_bytes(b"image")
    db_path = tmp_path / "search.db"
    index_entry(
        asset,
        library_root=root,
        category="Design",
        description="AI description: product hero artwork",
        kind="folder",
        db_path=str(db_path),
    )

    index_library(root, db_path=str(db_path))

    results = search_library("hero artwork", library_root=root, db_path=str(db_path))
    assert results
    assert results[0]["description"] == "AI description: product hero artwork"
