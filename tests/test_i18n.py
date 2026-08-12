from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QWidget

from fileorganizer import i18n


_APP = QApplication.instance() or QApplication([])


def test_shipped_catalogs_and_locale_resolution():
    assert "en_US" in i18n.available_locales()
    assert "zh_CN" in i18n.available_locales()
    assert i18n.resolve_locale("zh-TW") == "zh_CN"
    assert i18n.load_catalog("zh_CN")["Scan"] == "扫描"


def test_json_translator_updates_existing_widget_text():
    root = QWidget()
    root.setWindowTitle("Settings")
    button = QPushButton("Scan", root)
    combo = QComboBox(root)
    combo.addItem("Browse")

    translator = i18n.JsonTranslator({
        "Settings": "设置",
        "Scan": "扫描",
        "Browse": "浏览",
    })
    i18n.translate_widget_tree(translator, root)

    assert root.windowTitle() == "设置"
    assert button.text() == "扫描"
    assert combo.itemText(0) == "浏览"


def test_install_locale_prefers_compiled_qm_with_json_fallback():
    manager = i18n.install_locale(_APP, "zh_CN")
    try:
        assert manager.locale == "zh_CN"
        assert manager.translator.translate("FileOrganizer", "Scan") == "扫描"
        assert manager.translator.translate("FileOrganizer", "Browse") == "浏览"
    finally:
        _APP.removeEventFilter(manager)
        _APP.removeTranslator(manager.translator)
        manager.deleteLater()
        if getattr(_APP, "_fileorganizer_locale_manager", None) is manager:
            delattr(_APP, "_fileorganizer_locale_manager")

