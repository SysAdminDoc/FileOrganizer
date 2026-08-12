from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from fileorganizer.asset_bundles import (
    add_assets, add_fingerprints, asset_fingerprint, bundle_members,
    create_bundle, delete_bundle, list_bundles, remove_members,
)
from fileorganizer.dialogs.browse import BUNDLE_ID_ROLE, BrowsePanel


_APP = QApplication.instance() or QApplication([])


def test_bundle_membership_is_local_and_non_destructive(tmp_path):
    first = tmp_path / "library" / "Photos" / "sunset"
    second = tmp_path / "library" / "Photos" / "forest"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "image.jpg").write_bytes(b"sunset")
    (second / "image.jpg").write_bytes(b"forest")
    db_path = str(tmp_path / "asset_bundles.db")

    bundle = create_bundle("Vacation", db_path=db_path)
    assert add_assets(bundle["id"], [first, second], db_path=db_path) == 2
    assert add_assets(bundle["id"], [first], db_path=db_path) == 0
    assert len(bundle_members(bundle["id"], db_path=db_path)) == 2
    assert (first / "image.jpg").read_bytes() == b"sunset"
    assert list_bundles(db_path=db_path)[0]["member_count"] == 2

    fingerprint = asset_fingerprint(first)
    assert remove_members(bundle["id"], [fingerprint], db_path=db_path) == 1
    assert len(bundle_members(bundle["id"], db_path=db_path)) == 1
    assert delete_bundle(bundle["id"], db_path=db_path) is True
    assert list_bundles(db_path=db_path) == []


def test_bundle_accepts_external_fingerprints(tmp_path):
    db_path = str(tmp_path / "asset_bundles.db")
    bundle = create_bundle("References", db_path=db_path)

    assert add_fingerprints(
        bundle["id"], ["fp-a", "fp-b"],
        path_hints={"fp-a": str(tmp_path / "a.psd")},
        db_path=db_path,
    ) == 2
    members = bundle_members(bundle["id"], db_path=db_path)
    by_fingerprint = {member["fingerprint"]: member for member in members}
    assert by_fingerprint["fp-a"]["path_hint"].endswith("a.psd")


def test_browse_renders_virtual_bundle_members(tmp_path):
    root = tmp_path / "organized"
    asset = root / "Photos" / "sunset"
    asset.mkdir(parents=True)
    (asset / "image.jpg").write_bytes(b"sunset")
    db_path = str(tmp_path / "asset_bundles.db")
    bundle = create_bundle("Vacation", db_path=db_path)
    add_assets(bundle["id"], [asset], db_path=db_path)

    panel = BrowsePanel(bundle_db_path=db_path)
    try:
        panel.txt_root.setText(str(root))
        panel.refresh()
        virtual_root = next(
            panel.tree.topLevelItem(index)
            for index in range(panel.tree.topLevelItemCount())
            if panel.tree.topLevelItem(index).text(0) == "Virtual Bundles"
        )
        bundle_item = virtual_root.child(0)
        member = bundle_item.child(0)
        assert bundle_item.data(0, BUNDLE_ID_ROLE) == bundle["id"]
        assert member.text(0) == "sunset"
        assert member.data(0, Qt.ItemDataRole.UserRole).endswith("sunset")
    finally:
        panel.close()
