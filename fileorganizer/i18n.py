"""Qt localization support for the legacy PyQt6 desktop application.

The checked-in JSON catalogs are the editable source of truth.  Release builds
prefer the matching Qt ``.qm`` catalog, while development installs can use the
JSON-backed QTranslator directly when the generated binary is unavailable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEvent, QLocale, QObject, QTranslator, Qt
from PyQt6.QtWidgets import (
    QAbstractButton, QComboBox, QDialog, QGroupBox, QLabel, QLineEdit,
    QMenu, QTabWidget, QWidget,
)


MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_TRANSLATIONS = 20_000
_SOURCE_ROLE = Qt.ItemDataRole.UserRole + 700
_SOURCE_PROPERTY = "_fileorganizer_i18n_source"


def locale_directory() -> Path:
    """Return the locale directory for source and frozen application layouts."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        frozen_dir = Path(meipass) / "locale"
        if frozen_dir.is_dir():
            return frozen_dir
    package_root = Path(__file__).resolve().parent
    for candidate in (package_root.parent / "locale", package_root / "locale"):
        if candidate.is_dir():
            return candidate
    return package_root.parent / "locale"


def _catalog_path(locale: str, directory: Path) -> Path:
    return directory / f"{locale}.json"


def available_locales(directory: str | os.PathLike[str] | None = None) -> tuple[str, ...]:
    """Return bounded, deterministic locale identifiers shipped with the app."""
    root = Path(directory) if directory is not None else locale_directory()
    if not root.is_dir():
        return ()
    return tuple(sorted(path.stem for path in root.glob("*.json") if path.is_file()))


def normalize_locale(value: str | None) -> str:
    """Normalize Windows/Qt locale spellings to the shipped catalog names."""
    raw = (value or "").strip().replace("-", "_")
    if not raw or raw.lower() in {"system", "default"}:
        raw = QLocale.system().name()
    language, _, territory = raw.partition("_")
    language = language.lower()
    if language == "zh":
        return "zh_CN" if territory.lower() in {"", "cn", "hans", "sg"} else "zh_TW"
    if language == "en":
        return "en_US"
    return raw or "en_US"


def resolve_locale(
    requested: str | None = None,
    directory: str | os.PathLike[str] | None = None,
) -> str:
    """Choose an installed catalog, falling back to English safely."""
    root = Path(directory) if directory is not None else locale_directory()
    available = set(available_locales(root))
    requested_name = normalize_locale(requested or os.environ.get("FILEORGANIZER_LOCALE"))
    if requested_name in available:
        return requested_name
    language = requested_name.split("_", 1)[0].lower()
    language_match = next(
        (candidate for candidate in sorted(available)
         if candidate.split("_", 1)[0].lower() == language),
        None,
    )
    if language_match:
        return language_match
    return "en_US" if "en_US" in available or not available else sorted(available)[0]


def load_catalog(
    locale: str,
    directory: str | os.PathLike[str] | None = None,
) -> dict[str, str]:
    """Load and validate one flat JSON translation catalog.

    Invalid, oversized, or untrusted catalog values fail closed to an empty
    mapping; the source text remains visible rather than breaking the UI.
    """
    root = Path(directory) if directory is not None else locale_directory()
    path = _catalog_path(locale, root)
    try:
        if path.stat().st_size > MAX_CATALOG_BYTES:
            return {}
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    translations = payload.get("translations", payload)
    if not isinstance(translations, dict) or len(translations) > MAX_TRANSLATIONS:
        return {}
    result = {}
    for source, translated in translations.items():
        if (
            isinstance(source, str)
            and isinstance(translated, str)
            and source
            and len(source) <= 4096
            and len(translated) <= 4096
        ):
            result[source] = translated
    return result


def tr(source: str, context: str = "FileOrganizer") -> str:
    """Translate one source string through Qt's currently installed catalog."""
    return QCoreApplication.translate(context, source)


class JsonTranslator(QTranslator):
    """QTranslator-compatible fallback for editable JSON catalogs."""

    def __init__(self, translations: dict[str, str], parent: QObject | None = None):
        super().__init__(parent)
        self.translations = dict(translations)

    def translate(
        self,
        context: str,
        sourceText: str,
        disambiguation: str | None = None,
        n: int = -1,
    ) -> str:
        del disambiguation, n
        source = str(sourceText or "")
        contextual = f"{context}\x04{source}"
        return self.translations.get(contextual, self.translations.get(source, ""))


class CompositeTranslator(QTranslator):
    """Use a compiled Qt catalog first, with JSON as the editable fallback."""

    def __init__(
        self,
        compiled: QTranslator,
        fallback: JsonTranslator,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.compiled = compiled
        self.fallback = fallback

    def translate(
        self,
        context: str,
        sourceText: str,
        disambiguation: str | None = None,
        n: int = -1,
    ) -> str:
        try:
            translated = self.compiled.translate(context, sourceText, disambiguation, n)
        except (TypeError, UnicodeError):
            # A QM built by a different Qt binding can reject non-ASCII source
            # text; the JSON catalog remains the safe, complete fallback.
            translated = ""
        return translated or self.fallback.translate(context, sourceText, disambiguation, n)


def _translate_text(translator: QTranslator, source: str) -> str:
    if not source:
        return source
    leading = source[:len(source) - len(source.lstrip())]
    trailing = source[len(source.rstrip()):]
    core = source.strip()
    translated = translator.translate("FileOrganizer", core, None, -1)
    if not translated:
        return source
    return f"{leading}{translated}{trailing}"


def _apply_text(
    translator: QTranslator,
    obj: QObject,
    getter,
    setter,
    property_suffix: str,
) -> None:
    property_name = f"{_SOURCE_PROPERTY}_{property_suffix}"
    source = obj.property(property_name)
    if not isinstance(source, str):
        source = str(getter() or "")
        obj.setProperty(property_name, source)
    translated = _translate_text(translator, source)
    if translated != getter():
        setter(translated)


def _translate_action(translator: QTranslator, action) -> None:
    _apply_text(translator, action, action.text, action.setText, "text")
    _apply_text(translator, action, action.toolTip, action.setToolTip, "tooltip")


def translate_widget_tree(translator: QTranslator, root: QWidget) -> None:
    """Translate supported visible Qt text properties below ``root``.

    The source value is stored as a dynamic property so future retranslation
    never attempts to translate an already-translated string.
    """
    widgets = (root, *root.findChildren(QWidget))
    for widget in widgets:
        if isinstance(widget, (QDialog, QWidget)):
            _apply_text(
                translator, widget, widget.windowTitle, widget.setWindowTitle, "title"
            )
        if isinstance(widget, (QAbstractButton, QLabel)):
            _apply_text(translator, widget, widget.text, widget.setText, "text")
        if isinstance(widget, QGroupBox):
            _apply_text(translator, widget, widget.title, widget.setTitle, "group-title")
        if isinstance(widget, QLineEdit):
            _apply_text(
                translator, widget, widget.placeholderText, widget.setPlaceholderText,
                "placeholder",
            )
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                source = widget.itemData(index, _SOURCE_ROLE)
                if not isinstance(source, str):
                    source = widget.itemText(index)
                    widget.setItemData(index, source, _SOURCE_ROLE)
                translated = _translate_text(translator, source)
                if translated != widget.itemText(index):
                    widget.setItemText(index, translated)
        if isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                source = widget.tabBar().tabData(index)
                if not isinstance(source, str):
                    source = widget.tabText(index)
                    widget.tabBar().setTabData(index, source)
                translated = _translate_text(translator, source)
                if translated != widget.tabText(index):
                    widget.setTabText(index, translated)
        for action in widget.actions():
            _translate_action(translator, action)
        if isinstance(widget, QMenu):
            for action in widget.actions():
                _translate_action(translator, action)


class LocaleManager(QObject):
    """Keep dialogs created after startup covered by the active catalog."""

    def __init__(self, app, translator: QTranslator, locale: str, parent=None):
        super().__init__(parent or app)
        self.app = app
        self.translator = translator
        self.locale = locale

    def apply(self, root: QWidget) -> None:
        translate_widget_tree(self.translator, root)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt virtual method name
        if event.type() in {QEvent.Type.Show, QEvent.Type.Polish} and isinstance(watched, QWidget):
            self.apply(watched)
        return False


def install_locale(app, requested: str | None = None) -> LocaleManager:
    """Install the requested/system locale and return its lifecycle manager."""
    old_manager = getattr(app, "_fileorganizer_locale_manager", None)
    if old_manager is not None:
        app.removeEventFilter(old_manager)
        app.removeTranslator(old_manager.translator)
    root = locale_directory()
    locale = resolve_locale(requested, root)
    translations = load_catalog(locale, root)
    fallback_translator = JsonTranslator(translations, app)
    qt_translator: QTranslator = fallback_translator
    qm_path = root / f"fileorganizer_{locale}.qm"
    if qm_path.is_file():
        compiled = QTranslator(app)
        if compiled.load(str(qm_path)):
            qt_translator = CompositeTranslator(compiled, fallback_translator, app)
    app.installTranslator(qt_translator)
    manager = LocaleManager(app, qt_translator, locale, app)
    app.installEventFilter(manager)
    app._fileorganizer_locale_manager = manager
    return manager
