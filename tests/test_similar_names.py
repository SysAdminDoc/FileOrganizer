from __future__ import annotations

from fileorganizer import similar_names


def test_group_similar_names_detects_filename_variants():
    groups = similar_names.group_similar_names(
        [
            "ClientBrand_social_post_01.psd",
            "ClientBrand social post 02.psd",
            "ClientBrand-social-post-FINAL.psd",
            "Quarterly invoice.pdf",
        ],
        threshold=92,
    )

    assert len(groups) == 1
    assert len(groups[0].names) == 3
    assert "Quarterly invoice.pdf" not in groups[0].names
    assert groups[0].score >= 92


def test_scan_paths_finds_nested_similar_files(tmp_path):
    root = tmp_path / "asset"
    nested = root / "exports"
    nested.mkdir(parents=True)
    (nested / "SlideDeck_Blue_v1.png").write_bytes(b"x")
    (nested / "SlideDeck Blue v2.png").write_bytes(b"x")
    (nested / "unrelated.txt").write_text("x")

    groups = similar_names.scan_paths([root], threshold=92)

    assert len(groups) == 1
    assert groups[0].root == str(root)
    assert len(groups[0].paths) == 2
    assert all("SlideDeck" in name for name in groups[0].names)


def test_scan_paths_respects_max_per_root(tmp_path):
    root = tmp_path / "asset"
    root.mkdir()
    (root / "SlideDeck_Blue_v1.png").write_bytes(b"x")
    (root / "SlideDeck Blue v2.png").write_bytes(b"x")

    groups = similar_names.scan_paths([root], threshold=92, max_per_root=1)

    assert groups == []


def test_group_similar_names_no_rapidfuzz_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(similar_names, "_fuzz", None)

    groups = similar_names.group_similar_names([
        "SlideDeck_Blue_v1.png",
        "SlideDeck Blue v2.png",
    ])

    assert groups == []
