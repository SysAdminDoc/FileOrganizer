# Changelog

All notable changes to FileOrganizer will be documented in this file.

## [v8.2.0] - Unreleased

### Added (2026-04-30, N-10 embeddings classifier MVP)

- **N-10: Embeddings classifier MVP** — new `fileorganizer/embeddings_classifier.py`
  inserts a Stage-3 local cosine match between marketplace_enrich (Stage 2) and
  the DeepSeek call (Stage 4) inside `classify_design.cmd_run`.  Backend chain
  mirrors Bookmark-Organizer-Pro [S55] `services/embeddings.py`: fastembed →
  model2vec → sentence-transformers → none (graceful no-op).  Anchors for the
  full 384-category taxonomy are embedded once and cached in
  `%APPDATA%/FileOrganizer/category_embeddings.db` keyed by (backend, model);
  switching backends rebuilds anchors on first call automatically.

  Gating: returns the canonical category at confidence 90 only when the top-1
  cosine ≥ 0.65 AND the margin over the runner-up ≥ 0.15; otherwise None and
  the item falls through to AI.  Pure-Python cosine with optional numpy fast
  path.  When no embedding backend is installed the classifier is a no-op and
  the existing AI flow is unchanged.

  New `--embeddings-only` flag on `classify_design.py` runs Stages 2+3 only,
  recording sub-threshold items as `_Unresolved` at confidence 0 — useful for
  benchmarking the embeddings skip-rate before paying for a full AI run.

  Optional dependencies (commented in `requirements.txt`): `fastembed`,
  `model2vec`, `sentence-transformers`.

  13 new tests in `tests/test_embeddings_classifier.py` cover cosine math,
  singleton contract, graceful degradation when no backend is installed, the
  top-1 + margin gating rules with a hand-rolled fake backend, and the
  text-builder format.

### Added (2026-04-30, post-audit roadmap items)

- **N-15: SOURCE_CONFIGS parity test** — `tests/test_source_configs_parity.py`
  asserts (1) every key in `classify_design.SOURCE_CONFIGS` (modulo the
  `design_unorg`↔`design` rename) appears in `organize_run --source` choices
  and `review_resolver.SOURCE_CONFIGS`; (2) every right-hand side of
  `CATEGORY_ALIASES` is a real canonical category in `classify_design.CATEGORIES`;
  (3) every declared `batch_prefix` is wired into both `batch_offset` and the
  `load_all_with_index` glob dispatcher.  Six tests; would have caught the N-1
  drift bug at PR time.

- **N-16: catalog_sync conditional requests** — `CatalogSyncWorker` now sends
  `If-None-Match: <etag>` (or `If-Modified-Since` as fallback) on the GitHub
  Releases API call.  Server returns 304 when the release hasn't changed,
  costing zero against the unauthenticated 60-req/hr rate-limit and skipping
  JSON parsing entirely.  ETag and Last-Modified persisted in
  `%APPDATA%/FileOrganizer/catalog_sync.json` alongside `last_published_at`.

- **N-17: Robocopy `/MT:n` multi-thread cross-drive moves** — `robust_move()`
  now passes `/MT:8` by default (configurable 0..128 in
  `%APPDATA%/FileOrganizer/advanced_settings.json` via `robocopy_mt`).  4–6×
  faster on cross-drive bulk moves; setting `robocopy_mt=0` or `1` disables
  multi-thread for slow USB drives.  New `load_advanced_settings()` /
  `save_advanced_settings()` helpers in `fileorganizer/config.py` clamp to
  robocopy's accepted 0..128 range.

### Audit + fixes (2026-04-30, post N-1..N-8)

Reviewed every N-* commit for accuracy. Fixed:

- **N-1**: `organize_run.py` `--source` choices and `_SOURCE_DIRS` did not include
  `i_organized_legacy`; CLI rejected the new source. `review_resolver.py`
  `SOURCE_CONFIGS` likewise missing the new key. Both now mirror
  `classify_design.py`. Added `i_org_batch_*.json` glob and `batch_offset`
  prefix branch in `organize_run.py`.
- **N-7**: CI used `pip-audit --fail-on-cvss 7`, which is not a real flag
  (pip-audit has no CVSS-severity gate). Replaced with `--strict` so any
  vulnerability fails the build.
- **N-8**: `_ReviewApplyWorker` used `dest / cat` (no `_cat_path` sanitization,
  re-introducing the `_Review-CategoryName` flat-folder bug from 2026-04-28),
  bare `os.rename` + `shutil.move` (no `\\?\` long-path support, no trailing-
  space strip). Replaced with `organize_run._cat_path` + `safe_dest_path` +
  `strip_trailing_spaces` + `robust_move`. Fixed dead `continue` that silently
  dropped any row whose dropdown started with `_Review/`. Added
  `finished.connect(deleteLater)` to scan and apply workers to plug a slow
  Qt-object leak across rescans.
- **N-6**: `move_journal.py` opened raw `sqlite3.connect()` calls with no
  `timeout`, no `journal_mode=WAL`, and no `synchronous` pragma — worker
  thread + GUI thread could deadlock on lock contention. Now routes through a
  `_connect()` helper that sets WAL + NORMAL + 30s busy timeout.
  `apply_mixin._apply_cat()` only handled `pending[0]`, silently leaving
  older interrupted runs to resurrect on every Apply. Now reports the total
  across all pending runs and chains resumes through a queue drained in
  `_on_resume_done`.
- **N-5**: `load_confidence_settings` / `save_confidence_settings` had no
  validation — a hand-edited `confidence_settings.json` with
  `review_below=99, auto_above=80` would silently disable auto-apply. Added
  `_validate_confidence` that clamps to 1..100 and falls back to defaults if
  `auto_above <= review_below`.
- **N-3**: `CatalogSyncWorker` only caught `urllib.error.URLError`; a
  `socket.timeout`, malformed JSON, or wrong asset schema would surface as a
  noisy `Catalog sync error` instead of a graceful skip. Added explicit
  `socket.timeout`, `json.JSONDecodeError`, and asset-payload shape guards.

### Added (2026-04-30)

- **N-1: I:\ legacy reclassification (Phase 4)** — added `i_organized_legacy` source to
  `classify_design.py` `SOURCE_CONFIGS` (index: `i_organized_legacy_index.json`, batch
  prefix: `i_org_batch_`, source: `I:\Organized`, `has_legacy=True`). Added
  `build_i_organized_index()` to `build_source_index.py` — walks
  `I:\Organized\<category_dir>\<asset_folder>`, stores `legacy_category = category_dir.name`,
  skips `_Review`/`_Skip`/system dirs. Usage:
  ```
  python build_source_index.py --source i_organized_legacy
  python classify_design.py --source i_organized_legacy --run
  ```

- **N-8: Review Queue panel** — new "Review Queue" entry in sidebar MARKETPLACE section
  (content stack index 6). Scans `<Organized root>/_Review/<subcategory>/<item>` in a
  background `_ReviewScanWorker`; displays each item with its current subcategory and a
  category dropdown. User sets each row to Move/Keep; clicking "Apply Corrections" runs
  `_ReviewApplyWorker` which calls `save_correction()` for every moved item and relocates
  the folder to `<dest>/<chosen_category>/`. Implemented in
  `fileorganizer/dialogs/marketplace.py` (`_ReviewScanWorker`, `_ReviewApplyWorker`,
  `ReviewPanel`).

- **N-6: Two-phase commit for GUI Apply** — `ApplyCatWorker` now writes every planned
  move to `%APPDATA%/FileOrganizer/organize_moves.db` as `pending` before touching disk,
  then updates each record to `done`/`error` as moves complete, and clears the journal on
  clean exit. If the app crashes mid-apply, pending rows persist. On the next Apply click,
  `_apply_cat()` detects the interrupted run and prompts: Resume / Discard / Cancel.
  `ResumeApplyWorker` re-executes the pending moves by src/dst path without requiring a
  rescan. New `fileorganizer/move_journal.py` owns all journal I/O.

- **N-3: Community catalog auto-download** — `CatalogSyncWorker(QThread)` runs silently
  on startup, checks the GitHub Releases API for a new `asset_fingerprints.json` attached
  to the latest release, and merges it into the local `asset_fingerprints.db` via a new
  `import_community_json()` function in `asset_db.py`. Existing local entries are never
  overwritten (INSERT OR IGNORE on `folder_fingerprint`). Sync state persisted in
  `%APPDATA%/FileOrganizer/catalog_sync.json`; status bar updated only when a real update
  is downloaded.

- **N-4: Pre-flight report UI** — `PreflightDialog` (backed by `PreflightWorker` QThread)
  runs automatically before every category/smart-scan Apply. Shallow-scans source folders
  for trailing-space names and >260-char paths, reports destination free space, and shows
  how many items will route to _Review based on the current confidence threshold. Errors
  (missing source, <5 GB free) block continuation with a red "Continue Anyway" button;
  warnings and info allow a normal green "Continue". Cancel aborts the apply without
  touching disk.

- **N-5: Confidence threshold control** — `confidence_settings.json` in `%APPDATA%/FileOrganizer`
  persists two user-configurable thresholds: "auto-apply if confidence ≥ X" (default 80%) and
  "send to _Review if confidence < Y" (default 50%). Exposed in Design Workflow Settings dialog
  under a new "Classification thresholds" section. `organize_run.py` loads the `review_below`
  threshold at startup so CLI runs respect the same setting.


- `fix_duplicates.py` — switched from a single `write_text` at run-end (plus an every-50
  checkpoint that also overwrites) to per-item JSONL append with immediate `flush()`. A killed or
  crashed run now has a complete audit trail of every merge that completed before the interruption.
  Log file renamed from `fix_duplicates_log.json` to `fix_duplicates_log.jsonl`.


- `requirements.txt` — pinned `Pillow>=12.2.0` (fixes libavif, libjpeg-turbo, harfbuzz CVEs) and
  `PyQt6>=6.11.0` (ARM64 stability, upstream Qt 6.11 bug fixes).
- `.github/workflows/ci.yml` — added `pip-audit --fail-on-cvss 7` gate; any future dependency CVE
  scoring ≥ 7 will fail CI before it ships.

### Audit (session 2026-04-28 — phantom-category cleanup)

A full project audit uncovered three source-code bugs that produced
non-canonical "phantom" category folders and a fourth oversight that left
the I:\Organized legacy library un-reclassified. The on-disk damage at
audit time:

- **G:\Organized**: 13 phantom top-level dirs (57 items)
  - `After Effects - Promo & Advertising` (2 items, from `fix_stock_ae_items.py`)
  - `After Effects - CINEPUNCH.V20`, `After Effects - Photo Slideshow` (3 items, from `merge_stock.py` fallback)
  - 10x `Web Template - <subcat>` (52 items, from review_resolver bad rules)
- **I:\Organized**: 253 phantom top-level dirs (~11,400+ items in just the 19
  largest), all leftover from the pre-existing legacy library that Phase 4
  never reclassified into the canonical taxonomy.
- **fix_duplicates.py** had only logged 2 of 1,229+ collision pairs — the
  prior session's apply was interrupted before completion.

### Fixed (session 2026-04-28 — phantom categories)

- `fix_stock_ae_items.py` — keyword rule `(['promo', 'advertising', 'ad '],
  'After Effects - Promo & Advertising')` produced a phantom category not in
  `classify_design.CATEGORIES`. Merged into the legitimate
  `After Effects - Product Promo` rule.
- `fix_stock_ae_items.py` — `cmd_apply()` now uses `organize_run.robust_move`
  + `strip_trailing_spaces` instead of bare `shutil.move`, gaining
  `\\?\` long-path support and trailing-space safety on cross-drive moves.
- `merge_stock.py` — AE Organized fallback `f"After Effects - {sub.name}"`
  invented phantom categories from arbitrary subdirectory names. Replaced
  with a strict `AE_ORGANIZED_REMAP` allowlist plus
  `AE_ORGANIZED_FALLBACK = "After Effects - Other"`. Added entries for
  Slideshows, Intros & Openers, Transitions, Wedding & Events, Templates,
  Logo Reveals so common legacy names now round-trip cleanly.
- `review_resolver.py` — SYSTEM_PROMPT contained 11 ground-truth rules
  pointing to non-existent categories (`Photoshop - Print & Stationery`,
  `Photoshop - Social Media Templates`, `Illustrator - Logos & Branding`,
  `After Effects - Backgrounds`, `After Effects - Elements`,
  `After Effects - Film Grain & Overlays`, `After Effects - Overlay & Transition`,
  `After Effects - Motion Graphics`, `Photoshop - Templates & Mockups`,
  `Cinematic FX`, `Motion Graphics - Multi-Tool Pack` mapping). DeepSeek would
  have faithfully returned these names on every re-resolved batch. All
  rewritten to canonical taxonomy entries.
- `review_resolver.py` — added defensive `canonicalize()` + `_CATEGORY_SET`
  validator. Any category from DeepSeek that isn't in the canonical set or
  the explicit phantom→canonical map is rejected and the item stays in
  `_Review` (instead of silently writing a new phantom into batch JSON).
  `Web Template - <subcat>` collapses to `Web Template`.
- `organize_run.py` — `CATEGORY_ALIASES` expanded by ~190 entries covering
  every phantom found at audit time: AE phantoms (`After Effects - Slideshows`,
  `After Effects - Logo Reveals`, `After Effects - Intros & Openers`, etc.),
  Photoshop/Illustrator phantoms, the entire I:\Organized legacy hierarchy
  (Flyers & Print, Resume & CV, Logo & Identity, holiday/event/industry
  buckets, mockup variants, etc.), and a `_web_template_collapse()` helper
  that folds `Web Template - <subcat>` into the canonical `Web Template`.

### Added (session 2026-04-28 — phantom categories)

- `fix_phantom_categories.py` — top-level migration tool. Walks every
  non-canonical dir under G:\Organized and I:\Organized, looks each up in
  the expanded `CATEGORY_ALIASES`, and either (a) `robocopy /E /MOVE /256
  /COPY:DAT` merges it into the canonical destination or (b) removes the
  empty stub. Writes an audit log to `fix_phantom_categories_log.json`.
  CLI: `--scan`, `--apply [--dry-run]`, `--root G:|I:|all`.

### Documented (session 2026-04-28 — audit findings)

- I:\Organized legacy reclassification (Phase 4) was never executed. The
  pre-existing 18,742-asset library is still in old folder names. Audit
  decision: do not bulk-migrate via aliases (too coarse for AE/Photoshop
  decisions); instead, run a future `build_source_index.py --source
  i_organized_legacy` pass with the existing folder name as
  `legacy_category` hint, then route through the normal classify_design
  pipeline. Logged to ROADMAP.md as Phase 4.
- `fix_duplicates.py` interrupted-run hazard: the script writes its log
  file only at the end of `cmd_apply`. If the process is killed mid-run,
  any merges it did complete are still on disk but unrecorded. Future
  enhancement: write log incrementally (every N merges).


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

### Fixed (session 2026-04-28 emergency continuation)
- `post_apply_sequence.py` — removed dependence on a single stale hardcoded AE apply PID.
  - New `detect_ae_apply_pid()` auto-detects a live `python organize_run.py --apply` AE process
    via WMIC when possible.
  - New `--wait-pid` override preserves explicit wait behavior when a specific PID is known.
  - `--step 0` now correctly runs only the category-merge step; previous selection logic
    accidentally ran steps 1-6 after step 0.
  - `is_merge_stock_done()` now reuses the same WMIC key/value parser used by AE apply detection.
- Runtime artifact hygiene:
  - `organize_errors_ae.json` removed from version control. It is a transient per-source retry file
    that is expected to auto-delete when `organize_run.py --retry-errors --source ae` clears all errors.
  - `.gitignore` now ignores `migrate_*.log`, covering emergency robocopy transcripts such as the
    earlier `/COPYALL` failures that would otherwise leave noisy untracked files in the repo root.

### Documented (session 2026-04-28 emergency continuation)
- Resume-state facts confirmed at restart:
  - AE apply had already finished by `2026-04-28 11:20`, and the retry pass resolved all 5 prior
    AE error entries by auto-skipping missing sources and deleting `organize_errors_ae.json`.
  - All 326 `loose_batch_*.json` files are present, so orchestrator step 4 is ready once step 0
    and the unorganized reclassification steps complete.
  - The only remaining variant-category merge at resume time was
    `I:\Organized\After Effects - Titles & Typography` -> `I:\Organized\After Effects - Title & Typography`.
  - Emergency stock migrations had completed by the restart check; `G:\` free space had recovered
    to roughly `129.5 GB` and `I:\` free space was roughly `2301.3 GB`.

### Fixed (session 2026-04-28 post-apply follow-up)
- `fix_duplicates.py` — Windows cleanup hardening after live step-5 failure:
  - `log()` now uses CP1252-safe console output so garbled/trailing-space paths cannot crash the
    dedupe pass while reporting an error.
  - `robocopy_merge()` and the new purge helper decode subprocess output with replacement, avoiding
    secondary Unicode decode failures on odd filenames.
  - `rmtree_safe()` now treats already-missing collision folders as success and falls back to
    `robocopy EMPTY -> collision /MIR` before a second delete attempt for directories that contain
    trailing-space or non-standard filenames that `shutil.rmtree()` cannot remove directly.
- `post_apply_sequence.py` — step 0 now treats the post-`/MOVE` source-already-gone case as a clean
  success instead of emitting a misleading warning.

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

### Known Issues (as of 2026-04-28, session 2)
- 5 trailing-space/long-path errors in `organize_errors_ae.json` — all 5 source paths now GONE from I:\;
  pending `--retry-errors --source ae` after AE apply (PID 22500) completes (will auto-skip + clear).
- AE apply (PID 22500): still running — robocopy-ing `I:\Unorganized\Social Media` (39K files, 175 GB).
  Progress: ~65% by size as of last check. `post_apply_sequence.py` (PID 14644) watching for exit.
- I:\Unorganized reclassification: 88 stock/design items routed into AE categories by AE pipeline;
  `reclassify_unorg.py --analyze` + `--apply` blocked until AE apply exits.
- merge_stock (PID 11432): copying `G:\Stock\Stock Footage & Photos` (robocopy PID 23164). Not yet done.
  2 Videohive AE items (VH-6185510, Parallax Footage Reel) in G:\Stock\Stock Footage & Photos will be
  moved by merge_stock; may land in Stock Footage category — verify post-apply.
- loose_files classify: 238/326 batches done (72.4%) — pipeline running (PID 22848). Apply blocked.
- `_Review\After Effects - Other\` 5 remaining: `Unknown LP Video 2`, `Unknown VH Template`,
  `Unknown VH Template (2)`, `Unknown VH Template 2 (1)`, `Unknown VH Template 3` — insufficient context.
- `_Review\Orphaned Documentation\` — 4 detached doc items, no parent packages.

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

### Fixed (session 2026-04-28 resumed — deduplication & tooling)
- `reclassify_unorg.py` — SQL LIKE double-backslash bug: `"I:\\\\Unorganized%"` produced SQL pattern
  `I:\\Unorganized%` (double backslash) matching 0 rows. Fixed to single-backslash Python string
  `"I:\\Unorganized%"` → SQL pattern `I:\Unorganized%` → matches 56 rows correctly.
- `organize_run.py` — Added `journal_src_set()` preload + `src in already_moved` skip in `apply_moves()`.
  Prevents items already journaled in the DB from being re-processed across sessions. This eliminates
  future collision duplicates at the source level. Retroactive fix for 563 existing collision pairs:
  use `fix_duplicates.py --apply` after all active apply processes have exited.

### Added (session 2026-04-28 continued — post-apply tooling)

- `post_apply_sequence.py` — Automated cleanup orchestrator for when AE apply exits.
  Waits for Python AE apply PID, then runs in sequence: retry-errors, reclassify_unorg, fix_duplicates,
  fix_stock_ae_items (if merge_stock done). Flags: `--dry-run`, `--step N`, `--skip N`, `--no-wait`.

- `verify_organized.py` — Post-apply library health reporter.
  - `--summary`: fast 2-level shallow scan of all 108 category dirs (current: 41,815 files).
  - `--collisions`: lists remaining `Name (N)` suffix files by category.
  - `--missing`: DB entries whose destination file no longer exists on disk.
  - `--orphans`: category dirs with no corresponding DB entries.
  - `--review`: `_Review` breakdown with remediation suggestions.
  - `--export FILE`: saves report as Markdown.

### Fixed (session 2026-04-28 continued)

- `status.py` — WMIC CSV field order bug: code unpacked `(node, cmd, pid, ppid)` but wmic
  `/format:csv` outputs fields alphabetically `(CommandLine, ParentProcessId, ProcessId)`,
  so `pid` was actually the parent PID and `ppid` was the process's own PID.
  Result: dashboard showed parent PIDs (20864, 4984, 23868) instead of real process PIDs
  (22500, 22848, 11432). Fixed: `_, cmd, _ppid, pid = parts`.

- `organize_run.py` — file-mode (loose_files) destination filename was using AI `clean_name`
  instead of original disk filename stem. This caused 213 files to share `clean_name = 'psd template'`
  (plus 58 sharing `'photoshop template'`, 22 `'vector asset'`, etc.) → would have created
  floods of `(N)` collision suffixes on apply. Fix: file-mode now uses `sanitize(Path(disk_name).stem)`
  as destination filename stem; `clean_name` is still used for folder-mode (directory moves).

- `organize_run.py` — `log()` UnicodeEncodeError for garbled-encoding filenames on Windows
  cp1252 consoles. Fix: `line.encode('cp1252', errors='replace').decode('cp1252')` before print.
  Log file still written with full UTF-8.

### Fixed (session 3)

- `verify_organized.py` — `detect_issues(path: Path)` function definition line was missing; its body
  (5 lines: `issues = []`, two `if COLLISION_PAT/REPLACEMENT_CHARS` appends, `return issues`) existed
  as unreachable dead code inside `category_quick_counts()` after its `return counts` statement.
  Python accepted the orphaned code as dead code (no SyntaxError), but any call to `detect_issues()`
  raised `NameError: name 'detect_issues' is not defined`, crashing `--collisions`, `--missing`,
  `--orphans`, and `--review` scan modes. Only `--summary` worked because it returns before the call site.
  Fix: extracted the 5-line body out of `category_quick_counts()` and wrapped it in a proper
  `def detect_issues(path: Path) -> list[str]:` definition after that function.

### Added (session 3 — I:\\ overflow support)

- `organize_run.py` — `DEST_OVERFLOW = r'I:\Organized'` constant added. `get_dest_root()` now actually
  uses the overflow: when `shutil.disk_usage('G:\\')` free space drops below `MIN_FREE_GB` (50 GB),
  returns `I:\Organized` instead of `G:\Organized`. Also creates `I:\Organized` if it doesn't exist yet.
  Previous implementation was a stub that always returned `DEST_PRIMARY` regardless of free space.
- `organize_run.py` — `dest_root = get_dest_root()` moved from once-per-run to **per-item** inside the
  `apply_moves()` loop. Logs `[OVERFLOW]` message on first transition. This allows a single long-running
  apply process to automatically redirect mid-run when G:\\ hits the threshold — previously the dest_root
  was fixed for the entire run even if disk filled up partway through.
- `organize_run.py` — `retry_errors()` now recomputes destination using current `get_dest_root()` +
  stored `category` / `clean_name` from error log, instead of reusing the stored `dest` path from the
  failed attempt. This ensures disk-full retries automatically redirect to `I:\Organized` when G:\\ is
  still below the threshold.
- `verify_organized.py` — `ORGANIZED_OVERFLOW = Path(r'I:\Organized')` + `all_org_roots()` helper added.
  All scan functions updated to iterate over both roots: `walk_organized()`, `category_quick_counts()`,
  `report_summary()`, `report_collisions()`, `report_empty_categories()`. `category_quick_counts()` now
  uses `+=` to accumulate across roots (same category name on both drives merged in the counter).
  `report_collisions()` resolves category from whichever root the file belongs to.
- `fix_stock_ae_items.py` — `ORGANIZED_OVERFLOW` + `_overflow_scan_dirs()` helper added. `DEFAULT_SCAN_DIRS`
  automatically appends matching I:\\Organized subdirs (Stock Footage, Stock Photos, Print) when they exist.
- `post_apply_sequence.py` — `ORGANIZED_OVERFLOW` + `all_org_roots()` added. Step 0 category merge now
  iterates all roots — both `G:\Organized` and `I:\Organized` will have variant dirs merged to canonical names.

### Known Issues (as of session 3)

- AE apply (PID 22500): **still running** — robocopy for `I:\Unorganized\Wedding` (223 GB, ~53 MB/s).
  G:\\ free: ~342 GB and dropping. Will overflow to I:\Organized automatically around the Text Effects /
  Social Media items (when G:\\ drops to 50 GB). Overflow items go to `organize_errors_ae.json` for the
  *current* PID (old code loaded in memory); re-run `--retry-errors` after to redirect via new overflow.
- loose_files classify: **100% complete** — 326/326 batches done. Orchestrator step 4 polls; apply pending.
- merge_stock (PID 23164): still copying G:\\Stock → G:\\Organized\\Stock Footage - General.
- fix_duplicates / reclassify_unorg / loose_files apply: all blocked pending AE apply exit (orchestrator).
- `_Review\\After Effects - Other\\` 5 remaining items: insufficient context for automated resolution.
- `_Review\\Orphaned Documentation\\` — 4 detached doc items, no parent packages.


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
