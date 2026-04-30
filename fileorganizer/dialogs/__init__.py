"""FileOrganizer dialogs subpackage — re-exports all dialog classes for backward compatibility."""

from fileorganizer.dialogs.settings import (
    OllamaSettingsDialog, PhotoSettingsDialog, FaceManagerDialog, ModelManagerDialog,
    AIProviderSettingsDialog, DesignWorkflowSettingsDialog,
)
from fileorganizer.dialogs.editors import (
    CustomCategoriesDialog, DestTreeDialog, PCCategoryEditorDialog,
    TemplateBuilderWidget, _FileBrowserDialog, RuleEditorDialog
)
from fileorganizer.dialogs.cleanup import (
    _CleanupScanWorker, CleanupToolsDialog, CleanupPanel
)
from fileorganizer.dialogs.duplicates import (
    _DupScanWorker, DuplicateFinderDialog, DuplicatePanel, DuplicateCompareDialog
)
from fileorganizer.dialogs.tools import (
    BeforeAfterDialog, EventGroupDialog, ScheduleDialog,
    UndoTimelineDialog, UndoBatchDialog, PluginManagerDialog,
    RelationshipGraphWidget, WatchHistoryDialog,
    PreflightWorker, PreflightDialog,
)
from fileorganizer.dialogs.theme import (
    ThemePickerDialog, ProtectedPathsDialog
)
from fileorganizer.dialogs.marketplace import (
    LibraryAuditorPanel, ArchiveNormalizerPanel, CatalogManagerPanel
)

__all__ = [
    'OllamaSettingsDialog', 'PhotoSettingsDialog', 'FaceManagerDialog', 'ModelManagerDialog',
    'AIProviderSettingsDialog', 'DesignWorkflowSettingsDialog',
    'CustomCategoriesDialog', 'DestTreeDialog', 'PCCategoryEditorDialog',
    'TemplateBuilderWidget', '_FileBrowserDialog', 'RuleEditorDialog',
    '_CleanupScanWorker', 'CleanupToolsDialog', 'CleanupPanel',
    '_DupScanWorker', 'DuplicateFinderDialog', 'DuplicatePanel', 'DuplicateCompareDialog',
    'BeforeAfterDialog', 'EventGroupDialog', 'ScheduleDialog',
    'UndoTimelineDialog', 'UndoBatchDialog', 'PluginManagerDialog',
    'RelationshipGraphWidget', 'WatchHistoryDialog',
    'PreflightWorker', 'PreflightDialog',
    'ThemePickerDialog', 'ProtectedPathsDialog',
    'LibraryAuditorPanel', 'ArchiveNormalizerPanel', 'CatalogManagerPanel',
]
