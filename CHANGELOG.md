# Changelog

All notable changes to FileOrganizer will be documented in this file.

## [v8.1.0] - 2026-01-26

### Added
- `asset_db.py` — community SHA-256 fingerprint database builder/lookup/exporter
  - Three-tier lookup: exact folder fingerprint → project file hash → ≥75% file overlap
  - `--build PATH`, `--lookup PATH`, `--export`, `--stats` CLI commands
  - Integrated into `catalog.py::lookup_by_fingerprint()` as pre-AI check
- Moves journal (`organize_moves.db`): SQLite record of every applied move
  - `--undo-last N` / `--undo-all` — reverse moves in order
- `--validate` pre-flight flag: scans all sources for WinError 2/3 candidates before apply
- `classify_design.py` — batch classifier for G:\Design Unorganized (7,102 dirs, 119 batches)
  - 84-category taxonomy covering AE, Premiere, Photoshop, Illustrator, LUTs, Mockups, Fonts, Plugins
  - `peek_inside_zip()` reads .aep filename from inside zip without extracting
  - `looks_generic()` detects numeric/ID-only folder names, triggers filename-based hinting
  - `peek_extensions()` returns both extensions AND meaningful filenames for ambiguous folders
  - `--run` / `--batch N` / `--stats` CLI
- `design_unorg_index.json` — 7,102-item index of G:\Design Unorganized dirs
- `organize_run.py --source design` — second source mode for G:\Design Unorganized
  - Uses `design_unorg_index.json`, `design_batch_NNN.json`, source dir `G:\Design Unorganized`
  - Same position-based mapping, robocopy, error tracking, journal as AE mode
- `CATEGORY_ALIASES` dict in `organize_run.py`: normalizes cross-batch naming inconsistencies
  at apply time without touching batch result files
- `_win_longpath()` helper in `organize_run.py` for `\\\\?\\`-prefixed path building

### Fixed
- `strip_trailing_spaces()` now uses `\\\\?\\` extended-length path prefix for `os.rename()` calls
  — the normal Win32 API normalises trailing spaces away before the syscall, causing silent
  no-op renames. This was the root cause of WinError 2 on all trailing-space error cases.
- Removed ~358-line duplicate code block appended to end of `organize_run.py` in prior session
- `--source` flag changed from a directory string override to a mode selector (`ae`|`design`);
  design mode auto-sets `G:\\Design Unorganized` as the source directory
- `load_all_with_index()` now filters batch files by source mode (design vs AE) to prevent
  cross-contamination when both batch types exist in `classification_results/`
- Merged split category folders in `G:\Organized`:
  - `After Effects - Opener & Intro` → `After Effects - Intro & Opener`
  - `After Effects - Typography` → `After Effects - Title & Typography`

## [v8.0.0] - 2025-07-12

### Added
- Multi-provider AI system (`providers.py`): GitHub Models (Claude), DeepSeek API, Ollama — unified routing by task type
- Marketplace catalog lookup (`catalog.py`): DeepSeek identifies Videohive/Envato/Motion Array items by filename, returns clean name + category + confidence; SQLite cache
- Archive extraction pipeline (`archive_extractor.py`): ZIP/RAR/7z/TAR inspection + extraction with path-traversal protection and strip-top-folder logic
- `CatalogLookupWorker` and `ArchiveExtractionWorker` background threads in `workers.py`
- Dynamic category creation (`add_dynamic_category`, `get_or_create_category` in `categories.py`)
- Destination-aware output path helper (`get_dest_path` in `config.py`): switches from `I:\Organized` to `G:\` overflow when free space drops below threshold
- `AIProviderSettingsDialog` — GitHub Models + DeepSeek credentials, model selection, per-task routing
- `DesignWorkflowSettingsDialog` — primary/overflow destination paths, pipeline feature toggles
- Settings menu: "AI Providers..." and "Design Workflow..." items

## [v7.5.0] - 2025

- docs: add Related Tools cross-reference to UniFile
- Modularize into Python package, audit and polish all GUI elements
- Added: Add files via upload
- Changed: Update FileOrganizer.py
- Added: Add files via upload
- Added: Add files via upload
- Added: Add files via upload
