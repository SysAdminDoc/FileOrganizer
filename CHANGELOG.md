# Changelog

All notable changes to FileOrganizer will be documented in this file.

## [v8.2.0] - Unreleased

### Added
- `build_source_index.py` — index builder for additional source directories
  - `--source design_org` → walks G:\Design Organized, captures `legacy_category` (parent folder name)
    for 2,625 items (Backgrounds, Posters, Flyers, Design Elements subcategories, etc.)
  - `--source loose_files` → scans G:\Design Unorganized root by file extension whitelist,
    produces 19,531-item index with `is_file: True` and `file_ext` fields
- `deepseek_research.py` — DeepSeek-powered product ID researcher and `_Review` resolver
  - `--research-ids`: scrapes DesignBundles/CreativeMarket product pages (HTTP) for ground truth,
    falls back to DeepSeek training knowledge for all IDs in a single query
  - `--resolve-review`: moves resolved items from `G:\Organized\_Review` to correct categories
  - `--dry-run`: preview mode before live apply
  - Saves `review_research_results.json` as auditable record of all AI-suggested moves
- Multi-source support across the full pipeline (classify → review → apply):
  - `SOURCE_CONFIGS` dict in `classify_design.py`, `organize_run.py`, `review_resolver.py`
  - `--source` flag accepts: `ae` | `design` | `design_org` | `loose_files`
  - Each source auto-configures: index file, batch prefix, source dir, file mode, has_legacy flag
- `classify_design.py` enhancements:
  - Rule 17: `legacy_category` field injected as strong domain hint in `build_prompt()`
  - `file_mode` support: `loose_files` items peek inside archives, use `file_ext` as classifier hint
  - Dynamic `INDEX_FILE` and `BATCH_PREFIX` set from `SOURCE_CONFIGS` at argparse time
- `organize_run.py` enhancements:
  - `safe_dest_path_file()` — flat file move with collision-suffix on stem (for loose_files)
  - `apply_moves()` detects `is_file` items → `os.rename` fast path (same drive) + shutil fallback
  - `load_index_for_source()`, `batch_offset()`, `load_all_with_index()` support all 4 sources
- `review_resolver.py` enhancements:
  - `FILE_MODE` global controls `enrich_item()` — resolves path from `item['path']` for file items
  - `legacy_category` items get hint prepended as `"legacy: X"` for resolver context
  - `peek_inside_zip` now imported and used for loose archive files

### Fixed
- `G:\Organized\_Review` fully cleared: 9 items moved to correct categories via deepseek_research.py
  - db_1888916 → Illustrator - Vectors & Assets (Boho Rainbow SVG Bundle)
  - db_1889031 → Illustrator - Vectors & Assets (Watercolor Floral Clipart Bundle)
  - db_1889889 → Fonts & Typography (Retro Groovy Font Duo)
  - designbundles_1894534 → Fonts & Typography (Modern Calligraphy Font)
  - designbundles_1894553 → Photoshop - Patterns & Textures (Gold Foil Texture Pack)
  - designbundles_1894603 → Print - Social Media Graphics (Social Media Story Templates)
  - designbundles_1894615 → Print - Invitations & Events (Floral Wedding Invitation Suite)
  - designbundles_1894905 → Procreate - Brushes & Stamps (Procreate Stamp Brush Set - Floral)
  - Misc (web UI kit) → UI Resources & Icon Sets (Web UI Template Kit)
  - Documentation (help PDFs/TXT) → Deleted (not a design asset)

### Documented (CLAUDE.md)
- `_Review-CategoryName` flat folder pattern at G:\Organized root — cause under investigation
- Preview-only ZIP in product ID folders — deepseek_research.py workaround + limitation notes
- Web kit subfolder separation (css/images/js orphan dirs) — resolved, they move with parent
- Documentation/Help File folders as bundle components — should be deleted, not organized
- `merge_stock.py` integration: handles Flyers + AE Organized, skips Design Elements for AI
- DeepSeek product ID research is speculative (10-15% confidence penalty vs stated confidence)
- loose_files classification: 326 batches, file extension is strong signal, ~0% _Review rate
- design_org classification: legacy_category hint dramatically reduces _Review rate to <1%

### Known Issues
- `deepseek_research.py` line 3 docstring: `SyntaxWarning: invalid escape sequence '\O'` (harmless)
- `_Review-_Review` (9 dirs) and `_Review-After Effects - Other` (35 dirs) need investigation
  — AE template subfolders that got detached from parent during move, NOT standalone templates
- 5 trailing-space path errors in `organize_errors.json` — need Rename-Item fix + --retry-errors
- loose_files classify run: 312/326 batches remaining — overnight run expected



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
