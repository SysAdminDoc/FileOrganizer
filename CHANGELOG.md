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
- `organize_run.py` — `_lp(path)` helper: prepends `\\?\` extended-length path prefix to both
  `src` and `dst` passed to robocopy. Previous code only passed `/256` flag which handles the
  *destination* side; source directory scanning still hit MAX_PATH (260 chars) causing ERROR 3
  on deeply nested AE template items (e.g. fast-typography-promo-25863265, 263-char src path).
  `_lp()` normalises slashes and handles UNC paths correctly.
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

### Added (session 2026-04-28 AE review)
- `research_ae_review.py` — resolver for 35 detached AE subfolders in `_Review\After Effects - Other\`
  - `inspect_item()` — enumerates AEP filenames and dir structure for each item
  - `find_parent_candidates()` — token-overlap search across all `G:\Organized\After Effects - *` categories
  - `build_batch_prompt()` / `cmd_analyze()` — batched DeepSeek analysis (4 batches × 10 items)
  - `cmd_apply()` — three actions: `merge` (into existing parent template), `categorize` (new standalone),
    `keep-in-review` (insufficient context); `safe_dest()` handles name collisions
  - Journal-writes all moves to `organize_moves.db`; `--dry-run` preview mode
  - `ae_review_results.json` — full audit record of all 35 DeepSeek recommendations
  - Results: 30 moved (24 categorize, 6 merge), 5 kept in review
  - Chinese AE template items (11 items): decoded via AEP internal filenames → correctly classified to
    Cinematic, Photo Slideshow, Sport & Action, Titles & Typography, Christmas & Holiday, Corporate & Business
  - `tmpAEtoAMEProject-*` items (7 items): AEP project names decoded project identity (Christmas, slideshow,
    race game, travel memories) → moved to matching categories
  - 6 merged items: `Chinese AE Template Open` → `Event & Party\Open Event`,
    `Chinese Metal 2017 Template 2` → `Intro & Opener\Gold Metal and Particles`,
    `Master Photo Pages Comps` → `Christmas & Holiday\Christmas Photo Tree`,
    `Race Machine Main Composition` → `Intro & Opener\Drift Car Race Automotive Opener`,
    `Unknown VH Template 4 (2)` → `Product Promo\Minimal Product Display`,
    `Warming Display` → `Slideshow\Leaves Relaxing Photo and Video Display`

### Added (session 2026-04-28 unorg reclassify)
- `reclassify_unorg.py` — Post-processing corrector for 88 I:\Unorganized items that were incorrectly
  routed through the AE apply pipeline into After Effects category folders.
  - Root cause: `org_index.json` (AE pipeline) included 88 stock/design folders from I:\Unorganized
    (Shutterstock EPS/JPG, PSD bundles, ZIP packs) — these are NOT AE templates.
  - `--status`: shows all I:\Unorganized moves from `organize_moves.db` journal grouped by AE category.
  - `--analyze`: inspects each moved folder's extension profile; rule-based classification for clear
    cases (PSD-heavy → Photoshop, JPG/EPS-heavy → Stock Photos, etc.); DeepSeek for ambiguous/ZIP-only.
    Has-AE-files guard: folders with `.aep`/`.mogrt`/`.ffx` files are kept in AE category unchanged.
  - `--apply [--dry-run]`: moves each reclassified item to correct `G:\Organized\<new_category>` dir;
    journals each correction back to `organize_moves.db`; `safe_dest()` handles name collisions.
  - `unorg_reclassify_results.json` — audit record of all analyze recommendations.

### Added (session 2026-04-28 design_elements)
- `build_source_index.py --source design_elements` — new indexer for `G:\Design Organized\Design Elements\`
  - Treats each non-empty first-level subfolder as one directory-move item (not file-level).
  - Profiles file extensions for each subfolder (`ext_profile`, `dominant_ext`, `file_count`).
  - Skips 40 empty folders; produces 18-item `design_elements_index.json`.
  - `is_file_batch: true` flag distinguishes these dir-of-files items from normal nested dirs.
- `classify_design.py` + `organize_run.py` — `design_elements` source config added to `SOURCE_CONFIGS`.
  - Batch prefix `de_batch_`, index `design_elements_index.json`, source dir `G:\Design Organized\Design Elements`.
  - `organize_run.py --source design_elements` choice added to argparse and `_SOURCE_DIRS` map.
  - `load_index_for_source('design_elements')`, `batch_offset()` de_batch_ handler, `load_all_with_index()`
    filter all updated.
- Design Elements classification + apply — COMPLETE:
  - `de_batch_001.json` — 18 items classified in 1 DeepSeek batch (all ≥70% confidence, 0 _Review).
  - 18 moves applied (same-drive G: → G:, instant via os.rename):
    - Backgrounds (95 JPG) → `Photoshop - Patterns & Textures`
    - Business Cards (164 JPG) → `Print - Business Cards & Stationery\Business Cards (2)`
    - Cards (168 PSD) → `Print - Business Cards & Stationery`
    - Indesign (295 INDD) → `Print - Brochures & Books`
    - Print Inspiration Pack 7200 images (2330 JPG/PSD/INDD) → `Print - Other`
    - Cover Action Pro v1.3, v2.0 and v2.5 → `Photoshop - Actions & Presets`
    - Facebook Covers (73 JPG) → `Photoshop - Smart Objects & Templates`
    - The Big Bundle - Photoshop Brushes & Elements → `Photoshop - Brushes`
    - Isolated Food Items (47 JPG) → `Stock Photos - Food & Drink`
    - Polaroid Photo Template (9 PSD) → `Photoshop - Mockups`
    - JuiceDrops (15 PSD) → `Photoshop - Overlays & FX\Juice Drops`
    - + 7 more (Banners, Buttons, Ribbons, Infographics, Titles, CoverActionPro-rar-2008-Bandit,
      Main File Editorial Template Bundle)
  - G:\Design Organized\Design Elements\ fully cleared (18 non-empty → organized; 40 empty skipped).

### Fixed (session 2026-04-28 design_elements)
- `organize_run.py` — `datetime.utcnow()` DeprecationWarning replaced with
  `datetime.now(timezone.utc)` in both journal insert and undo update paths.
- `build_source_index.py` — removed `Design Elements` from `BRANCHES` dict (depth=2 config was broken:
  Design Elements has files at level 2, not directories — so depth=2 produced 0 items). Replaced with
  dedicated `build_design_elements_index()` that correctly treats level-1 subfolders as items.

### Known Issues (as of 2026-04-28)
- 5 trailing-space/long-path errors in `organize_errors_ae.json` — all 5 source paths now GONE from I:\;
  pending `--retry-errors --source ae` after AE apply (PID 22500) completes (will auto-skip + clear).
- AE apply (PID 22500): `fast-typography-promo-25863265` (263-char path) and `light-streaks-logo-reveal`
  will fail with old robocopy code; both will land in errors file; fixed via `--retry-errors` with _lp().
- `_Review\After Effects - Other\` 5 remaining (keep-in-review): `Unknown LP Video 2`, `Unknown VH Template`,
  `Unknown VH Template (2)`, `Unknown VH Template 2 (1)`, `Unknown VH Template 3` — insufficient context.
- `_Review\Orphaned Documentation\` — 4 detached doc items, no parent packages.
- loose_files classify: 152/326 batches done — pipeline still running (PID 22848).
- I:\Unorganized reclassification: 88 stock/design items routed into AE categories by AE pipeline;
  `reclassify_unorg.py --analyze` + `--apply` ready to run after AE apply (PID 22500) exits.
- merge_stock (PID 23164): copying `Stock_Footage` folder (358 GB at ~63 MB/s, ~95 min remaining).
  2 Videohive AE items (VH-6185510, Parallax Footage Reel) in G:\Stock\Stock Footage & Photos will be
  moved by merge_stock; may land in Stock Footage category — verify post-apply.

### Added (session 2026-04-28 resumed — deduplication & tooling)
- `fix_stock_ae_items.py` — Post-apply scanner for AE templates misrouted to non-AE categories.
  - Scans: `Stock Footage - General`, `Stock Photos - General`, `Stock Music & Audio`, `Print - Templates & Layouts`.
  - 30+ `AE_KEYWORD_RULES`: keyword→AE-subcategory evaluated in order; DeepSeek fallback for unmatched.
  - `has_ae_files()` checks folder tree for `.aep/.aet/.ffx/.mogrt/.aex`.
  - `--scan`, `--analyze`, `--apply [--dry-run]`, `--scan-dirs` CLI flags.
  - Applied: 21 AE templates corrected (6 keyword-rule, 15 DeepSeek). All journaled in DB.
  - Must be re-run after `merge_stock` completes to catch VH items landing in Stock Footage.
- `status.py` — Single-command pipeline health dashboard.
  - Displays: batch counts per source, DB move counts, running PIDs (Python + robocopy children), error counts.
  - `--errors`: dumps all items from all `organize_errors_*.json` files.
  - `--review`: breakdown of `G:\Organized\_Review` subcategories and file counts.
- `fix_duplicates.py` — Merger for 563 collision-pair duplicate folders in `G:\Organized`.
  - Root cause discovered: `design_org` pipeline pre-populated `G:\Organized\AE-*\<Name>` from G:\Design Organized;
    AE pipeline then re-moved same items (different source: I:\After Effects\*) to the same `clean_name`
    destination, triggering collision suffix `Name (1)` / `Name (2)`.
  - 994 total collision dirs, 46,670 files. Top affected: After Effects - Slideshow (148), Intro & Opener (127).
  - Strategy: `robocopy /E /COPYALL` merge collision → original (union), then `shutil.rmtree` collision, update DB.
  - `--scan`, `--analyze`, `--apply [--dry-run]` CLI flags.
  - Blocked: do NOT run while AE apply (PID 22500) is actively writing. Run after apply + retry-errors exits.

### Fixed (session 2026-04-28 resumed)
- `reclassify_unorg.py` — SQL LIKE double-backslash bug: `"I:\\\\Unorganized%"` produced SQL pattern
  `I:\\Unorganized%` (double backslash) matching 0 rows. Fixed to single-backslash Python string
  `"I:\\Unorganized%"` → SQL pattern `I:\Unorganized%` → matches 56 rows correctly.
- `organize_run.py` — Added `journal_src_set()` preload + `src in already_moved` skip in `apply_moves()`.
  Prevents items already journaled in the DB from being re-processed across sessions. This eliminates
  future collision duplicates at the source level. Retroactive fix for 563 existing collision pairs:
  use `fix_duplicates.py --apply` after all active apply processes have exited.



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
