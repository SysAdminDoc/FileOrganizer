"""FileOrganizer dialogs subpackage — re-exports all dialog classes for backward compatibility."""

from fileorganizer.dialogs.settings import (
    OllamaSettingsDialog, PhotoSettingsDialog, FaceManagerDialog, ModelManagerDialog,
    AIProviderSettingsDialog, DesignWorkflowSettingsDialog, KeyboardShortcutsDialog,
    GGUFRegistrationDialog,
)
from fileorganizer.dialogs.editors import (
    CustomCategoriesDialog, TeachCategoryDialog, DestTreeDialog, PCCategoryEditorDialog,
    TemplateBuilderWidget, _FileBrowserDialog, RuleEditorDialog
)
from fileorganizer.dialogs.cleanup import (
    _CleanupScanWorker, CleanupToolsDialog, CleanupPanel
)
from fileorganizer.dialogs.duplicates import (
    _DupScanWorker, DuplicateFinderDialog, DuplicatePanel, DuplicateCompareDialog,
    CrossLibraryDedupDialog, CrossLibraryReviewDialog,
)
from fileorganizer.dialogs.version_dedup import VersionDedupDialog
from fileorganizer.dialogs.browse import BrowsePanel, BrowseTreeWidget
from fileorganizer.dialogs.batch_rename import BatchRenameDialog
from fileorganizer.dialogs.tools import (
    BeforeAfterDialog, EventGroupDialog, ScheduleDialog,
    UndoTimelineDialog, MoveHistoryDialog, UndoBatchDialog, PluginManagerDialog,
    RelationshipGraphWidget, WatchHistoryDialog,
    PreflightWorker, PreflightDialog,
)
from fileorganizer.dialogs.theme import (
    ThemePickerDialog, ProtectedPathsDialog
)
from fileorganizer.dialogs.marketplace import (
    LibraryAuditorPanel, ArchiveNormalizerPanel, CatalogManagerPanel, ReviewPanel
)
from fileorganizer.dialogs.rule_chain_editor import RuleChainEditorDialog

__all__ = [
    'OllamaSettingsDialog', 'PhotoSettingsDialog', 'FaceManagerDialog', 'ModelManagerDialog',
    'AIProviderSettingsDialog', 'DesignWorkflowSettingsDialog', 'KeyboardShortcutsDialog',
    'GGUFRegistrationDialog',
    'CustomCategoriesDialog', 'TeachCategoryDialog', 'DestTreeDialog', 'PCCategoryEditorDialog',
    'TemplateBuilderWidget', '_FileBrowserDialog', 'RuleEditorDialog',
    '_CleanupScanWorker', 'CleanupToolsDialog', 'CleanupPanel',
    '_DupScanWorker', 'DuplicateFinderDialog', 'DuplicatePanel', 'DuplicateCompareDialog',
    'CrossLibraryDedupDialog', 'CrossLibraryReviewDialog',
    'VersionDedupDialog',
    'BrowsePanel', 'BrowseTreeWidget',
    'BatchRenameDialog',
    'BeforeAfterDialog', 'EventGroupDialog', 'ScheduleDialog',
    'UndoTimelineDialog', 'MoveHistoryDialog', 'UndoBatchDialog', 'PluginManagerDialog',
    'RelationshipGraphWidget', 'WatchHistoryDialog',
    'PreflightWorker', 'PreflightDialog',
    'ThemePickerDialog', 'ProtectedPathsDialog',
    'LibraryAuditorPanel', 'ArchiveNormalizerPanel', 'CatalogManagerPanel', 'ReviewPanel',
    'RuleChainEditorDialog',
]
