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

### Fixed (session 2026-04-28)
- `organize_run.py` — `_Review-CategoryName` flat folder bug: `sanitize()` was stripping the
  backslash from `_Review\Category` (produced by `os.path.join(REVIEW_SUBDIR, category)`),
  collapsing it to `_Review-Category` as a top-level flat folder instead of a nested subdirectory.
  Root cause: `sanitize()` regex `[<>:"/\\|?*]` includes `\\` (backslash), which ate the separator.
  Fix: new `_cat_path()` helper splits category on `/` and `\\` BEFORE sanitizing each component,
  then re-joins with `os.path.join()`. Both `safe_dest_path()` and `safe_dest_path_file()` updated.
- Migrated 45 items from three malformed flat folders at G:\Organized root into correct
  `G:\Organized\_Review\` subdirectories:
  - `_Review-_Review` (9 dirs) → `G:\Organized\_Review\_Review\` (cm_*, Help File, etc.)
  - `_Review-After Effects - Other` (35 dirs) → `G:\Organized\_Review\After Effects - Other\`
    (detached AE template subfolders — queued for manual parent-matching)
  - `_Review-After Effects - Sport & Action` (1 dir) → `G:\Organized\_Review\After Effects - Sport & Action\`
- `deepseek_research.py` SyntaxWarning: confirmed already resolved (double-backslash in docstring
  is valid; no warning emitted by Python 3.12)
- `organize_run.py` — source-specific errors files: `organize_errors_{source}.json` per source
  instead of a single `organize_errors.json`; prevents concurrent apply runs from clobbering each
  other's error records. `retry_errors(source_mode)` and `errors_file(source_mode)` added.
  Legacy `organize_errors.json` migrated to `organize_errors_ae.json`.

### Added (session 2026-04-28)
- `resolve_review_items.py` — manual curator script for `_Review\_Review` items. Moves 9 items
  that were AI-classified as `_Review` (conf 30-40) but manually identified via archive inspection:
  - cm_4804020 → `Photoshop - Overlays & FX\Film Dust Textures (20 JPG)` (identified via PDF)
  - cm_4840406 → `Photoshop - Patterns & Textures\Roller Textures (17 JPG)` (from zip contents)
  - cm_7116381 → `Stock Photos - General\CM Stock Pack (53 JPG)` (53 numbered JPGs, no metadata)
  - cm_7119925 → `Photoshop - Overlays & FX\Light Flare Overlays (PNG)` (from RAR filename)
  - c4 (Video Copilot Collection) → `After Effects - Plugin & Script\Video Copilot Full Collection`
  - Help File - Avelina Studio, Main Print, Read Me (GraphixTree), readme
    → `_Review\Orphaned Documentation\` (detached doc files, no parent packages)
  Updates organize_moves.db with corrected destinations.

### Added (session 2026-04-28 continued)
- `marketplace_enrich.py` — Stage 2 of 4-stage classification pipeline: zero-AI-cost ID lookup
  - `extract_id(folder_name)` — 9 regex patterns covering Videohive (VH- prefix, leading-zero 9-digit,
    7–9 digit numeric prefix), MotionElements (nnnnnnnn_MotionElements_ prefix), CreativeMarket (cm_),
    DesignBundles (db_/designbundles_), Motion Array (ma_), Envato/GraphicRiver (ID-at-end pattern)
  - `enrich(folder_name)` — fetches marketplace metadata from public APIs/scraping; DeepSeek fallback
    when scraping fails; caches all results in `marketplace_cache.json`
  - `CATEGORY_MAP` — 60+ marketplace category strings mapped to our 84-category taxonomy
  - Fetchers: `fetch_videohive()` (og: tag scrape), `fetch_motionelements()` (API + scrape fallback),
    `fetch_creativemarket()`, `fetch_envato()` (tries Videohive then GraphicRiver)
  - `enrich_results_glob(pattern, min_improvement, dry_run)` — post-processes existing batch JSONs
    in-place without interrupting running pipelines; upgrades items that gain ≥5 conf points
  - CLI: `--scan-index`, `--scan-folder`, `--lookup NAME`, `--enrich-results GLOB`,
    `--stats`, `--export-unmapped`
  - ID coverage: 481/1224 AE items (39%), 223/2625 design_org items (8%), 129/19531 loose files (0.7%)
- `classify_design.py` — marketplace pre-enrichment integration in `cmd_run()`:
  - `_try_marketplace_enrich(batch_items)` called before DeepSeek for each batch
  - Items with marketplace ID + conf ≥ 95 are pre-classified; remaining items go to AI
  - Merged back in original order, preserving position-based index mapping invariant
  - Saves `_marketplace_id` annotation in batch JSON for audit trail
  - Shows `[MKT]` tag in per-batch sample output for pre-classified items
- `.gitignore` updated: `organize_errors_*.json`, `marketplace_cache.json`, `unmapped_ids.json`

### Known Issues (as of 2026-04-28)
- 5 trailing-space/long-path errors in `organize_errors_ae.json` — pending
  `--retry-errors --source ae` after current AE apply run (PID 22500) completes.
  Note: all 5 sources are GONE from I:\; destinations exist in G:\Organized. Retry will
  auto-skip them ("src gone") and clear the error file.
- `G:\Organized\_Review\After Effects - Other\` (35 dirs): 32 untracked detached AE project
  subfolders (no DB records) + 3 VH templates (low confidence). Need parent-matching pass.
- loose_files classify: ~246/326 batches remaining — pipeline running (PID 22848)
- design_org apply: ~1691/2625 items moved — pipeline running (PID 17144)
- AE apply (PID 22500): phantom nested-path storm on `fast-typography-promo-25863265` item —
  robocopy exit 9 (>= 8 = actual error), item will land in `organize_errors_ae.json` for retry



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
