# ROADMAP -- FileOrganizer
<!-- v9.1.0-planning · Updated 2026-05 (Wave 5 synthesis — community validation, competitive threats, platform roadmaps, licensing compliance) · Phase 5 audit complete · All Waves 1–5 reconciled -->

FileOrganizer is a Python/PyQt6 desktop tool for classifying and moving creative design assets
into a canonical folder taxonomy. Core use case: 33 TB+ of Envato/Creative Market/Freepik
templates (After Effects, Photoshop, Illustrator, Premiere Pro, etc.) on Windows.
Multi-provider AI backbone (DeepSeek, GitHub Models, Ollama).

---

## State of the Repo (v9.1.0 planning, May 2026 — Wave 5 research complete)

v8.3.0 is **fully shipped** — N-9 (metadata extractors), N-12 (provenance tracking), N-14
(broken file detection), and all iter-2 follow-ups. Tagged and released 2026-05-02. See
[Shipped — v8.2.0](#shipped--v820) and [Shipped — v8.3.0](#shipped--v830) below.

**v8.4.0 sprint** — 10 items now active. NEXT-46 and NEXT-47 carry hard API-deprecation
deadlines (July 24 and June 15, 2026 respectively). NEXT-48 and NEXT-49 are low-effort
reliability and security fixes that pair naturally into the same PR. NEXT-15, NEXT-44, and
NEXT-11 are the highest-ROI NEXT-tier items now fully unblocked. NEXT-39 upgrades the WinUI
shell to WindowsAppSDK 2.0.1 (GA April 29, 2026); NEXT-40 (RAWPage) and NEXT-41 (ComicsPage)
follow as ui-v0.6.0 deliverables.

The WinUI 3 shell reached **ui-v0.5.0** (2026-05-01) with 15 live pages covering all major media
and design-asset domains. See [Shipped — WinUI Shell](#shipped--winui-shell-ui-v010--ui-v050) below.
**ui-v0.6.0 targets**: WindowsAppSDK 2.0.1 upgrade (NEXT-39), RAWPage (NEXT-40), ComicsPage (NEXT-41).

### What ships today
- 384-category design asset taxonomy (After Effects, Photoshop, Illustrator, Premiere Pro, web,
  audio, fonts, photos, videos, general documents)
- 7-level classification pipeline: Extension -> Keyword -> Fuzzy -> Metadata -> Envato API ->
  Composition -> Context (LLM)
- Multi-provider AI router: DeepSeek (primary), GitHub Models/Claude (lightweight), Ollama (local
  fallback). Routing strategy: auto / github_only / deepseek_only / ollama_only
- `organize_run.py` CLI: position-based batch mapping, robocopy integration, long-path (`\\?\`)
  and trailing-space guards, SQLite undo journal (`organize_moves.db`)
- `classify_design.py`: DeepSeek batch classifier (60 items/batch), `_CATEGORY_SET` phantom guard
- `asset_db.py`: SHA-256 community fingerprint DB (96,026 marketplace entries); auto-download
  on first run via `CatalogSyncWorker` QThread (N-3 shipped)
- `marketplace_enrich.py`: Envato API + scraping for item title/category lookup
- Multi-source support: `ae`, `design`, `design_org`, `i_organized_legacy`, `loose_files` via
  `--source` flag (I:\ source added in N-1)
- PyQt6 GUI with settings, source management, apply workflow, pre-flight dialog (N-4),
  confidence threshold panel (N-5), two-phase commit (N-6), Review batch panel (N-8)
- `metadata_extractors/` package: `psd_extractor`, `font_extractor`, `audio_extractor`,
  `video_extractor` — zero-AI Stage 1 with hardroute threshold ≥ 90 (N-9, shipped v8.3.0)
- `provenance.py`: 12 marketplace patterns + 7-domain piracy blocklist; `source_domain` +
  `first_seen_ts` in `assets` DB (N-12, shipped v8.3.0)
- `broken_detector.py`: PIL verify + ffprobe + archive testzip; `broken` flag in `asset_files`;
  PreflightDialog Step 5 wiring (N-14, shipped v8.3.0)
- PyInstaller release: `FileOrganizer.exe` + CLI ZIP on GitHub Releases
- CI: syntax check + `test_organize_run.py` + `pip-audit --fail-on-cvss 7` (N-7) on
  `windows-latest`; 156 tests passing across 10 test files

### Built but not fully wired
- `marketplace_enrich.py`: built, but stage 2 pipeline call not always reachable via GUI
- `archive_extractor.py`: scaffolded; archive content peek not integrated into classifier
- `deepseek_research.py` CLI exists but not surfaced in GUI as first-class flow
- Watch mode: not implemented

### Stubbed / incomplete
- **Embeddings classifier**: planned in RESEARCH_IDEAS.md #7; not implemented (N-10 target)
- **AEP binary parser**: concept and spec exist; no implementation (NEXT-9)
- **Perceptual hash dedup**: planned; not implemented (NEXT-19)
- **Plugin SDK**: mentioned in code, undocumented externally (NEXT-27)

### Hard constraints
- Python + PyQt6: no migration planned; all GUI work targets PyQt6 6.x
- Windows-first: robocopy, `\\?\` paths, Task Scheduler, COM shell extensions are Windows-native;
  macOS/Linux are secondary and receive best-effort support
- Single-user: no auth, no network server, no multi-tenancy in scope
- Local-first: cloud APIs (Envato) used for enrichment only; no cloud storage of user files
- License: MIT (no GPL dependencies in core pipeline)

---

## Lessons Learned (real-world run, April 2026)

Hard lessons from running on ~1,200 After Effects/design templates across 33 TB on I:\ and G:\.
Every entry produced an on-disk bug before the fix was written.

- **Name-based batch mapping is fragile**: AI agents clean up, truncate, or reformat folder names
  before classifying them. Use position-based (batch index -> org_index offset) mapping. See
  `organize_run.py`.

- **Trailing spaces in folder/file names -> WinError 2**: Files from Linux/macOS can have trailing
  spaces. Windows strips them on creation then fails to find the path. Pre-sanitize with
  `strip_trailing_spaces()` before any move. Already in `organize_run.py`.

- **Deep Unicode paths >260 chars -> WinError 3**: CJK filenames inside deeply nested folders
  exceed MAX_PATH. `shutil.move` does not use `\\?\` prefixes. Use robocopy with `/256`.
  Already in `organize_run.py`.

- **`shutil.move` cross-drive leaves partial copies on failure**: Source is always safe (rmtree
  never runs on exception), but a partial destination exists. `retry_errors()` handles this.

- **Robocopy exit codes 0-7 are all success**: Only 8+ is failure. Never use `check=True` with
  robocopy. `robust_move()` enforces this.

- **Every move must be journaled**: `organize_moves.db` (SQLite) with `--undo-last N` and
  `--undo-all` support. Without this, a partial run is irreversible.

- **Pre-flight validation prevents >90% of errors**: `--validate` before `--apply` surfaces
  trailing-space and long-path issues in advance.

- **AI fabricates names if not grounded**: Always embed exact names from org_index into the batch
  prompt. Never let the model guess what items exist.

- **Community fingerprint DB changes the cost model**: Once 1,000+ assets are fingerprinted, new
  users classify common templates instantly without any AI call. The DB must be auto-downloaded;
  manual shipping is friction that negates the benefit.

- **Phantom categories corrupt the taxonomy**: Any AI category output not in `_CATEGORY_SET` must
  be rejected before it touches the filesystem. `canonicalize()` + `_CATEGORY_SET` guard is now
  in `review_resolver.py` and `classify_design.py`.

- **Journal must flush per-item**: Writing the log only at run end means a crash leaves applied
  moves unrecorded. Incremental flush is the fix.

- **`_Review` is not a permanent home**: Items in `_Review` need a second-pass resolver with a UI
  to confirm or reassign. Without it, `_Review` grows unbounded.

---

## Shipped -- v8.2.0

All 8 items shipped. See CHANGELOG.md for full details.

### N-1: ~~I:\ legacy reclassification (Phase 4)~~ ✓ Shipped v8.2.0
Run `build_source_index.py --source i_organized_legacy` on the 18,742-asset I:\Organized library,
using the legacy folder name as a `legacy_category` hint, then route through the standard
`classify_design` pipeline into canonical taxonomy.
- **Why now**: The I:\ library is inaccessible to search, dedup, and enrichment. Every downstream
  feature (dedup, preview browser, marketplace ID index) is blocked until it is organized.
- **Technical sketch**: Add `i_organized_legacy` to `SOURCE_CONFIGS` in `classify_design.py`;
  set `has_legacy=True`; add `legacy_category` as a pre-AI hint at stage 3.
- **Impact**: 5 | **Effort**: 3
- Source: [S32] AUDIT_LESSONS.md, [S35] CHANGELOG.md v8.2.0

### N-2: ~~fix_duplicates.py incremental journal~~ ✓ Shipped v8.2.0
Write a log entry after each successful merge, not at the end of the full run. Use append-mode
`open(logfile, 'a')` with a flush after each entry.
- **Why now**: An interrupted run leaves applied merges on disk but unrecorded. The user has no
  way to know what happened.
- **Impact**: 4 | **Effort**: 1
- Source: [S35] CHANGELOG.md v8.2.0, [S32] AUDIT_LESSONS.md

### N-3: ~~Community catalog auto-download~~ ✓ Shipped v8.2.0
On startup, check the GitHub Releases API for a newer `asset_fingerprints.json`. Import into the
local SQLite DB. Schema version gate: skip if DB_VERSION mismatch. Download sharded catalog/
(10.6M entries, 400MB gzipped) in background on first run via a `CatalogSyncWorker` (QThread).
- **Why now**: Manual catalog shipping is friction that prevents cold-start accuracy benefits.
- **Impact**: 5 | **Effort**: 2
- Source: [S32] AUDIT_LESSONS.md, existing `asset_db.py` pattern

### N-4: ~~Pre-flight report UI~~ ✓ Shipped v8.2.0 wiring
Surface the existing `--validate` CLI check as a mandatory step in the GUI Apply workflow:
color-coded table of long-path issues, trailing-space hits, low-confidence items going to
`_Review`, and free-space check result. Require acknowledgment before Apply proceeds.
- **Why now**: `--validate` already exists in CLI; the GUI bypasses it, making it easy to start
  a flawed run.
- **Technical sketch**: Add `PreflightDialog(QDialog)` that runs `validate_plan()` in a worker
  thread and renders results as a QTableWidget.
- **Impact**: 4 | **Effort**: 2
- Source: [S32] AUDIT_LESSONS.md

### N-5: ~~Confidence threshold control~~ ✓ Shipped v8.2.0
User-configurable thresholds: "auto-apply if confidence >= X; queue for manual approval between
X and Y; send to _Review if < Y." Expose in Settings -> Classification.
- **Why now**: No user-visible control over when the AI defers to `_Review`.
- **Pattern**: NEVER/MINIMAL/SMART/ALWAYS confidence modes from thebearwithabite [S6].
- **Impact**: 4 | **Effort**: 2
- Source: [S6] https://github.com/thebearwithabite/ai-file-organizer

### N-6: ~~Two-phase commit for GUI Apply~~ ✓ Shipped v8.2.0
Before executing any move, write all planned moves to `organize_moves.db` with
`status='pending'`. Mark `status='done'` atomically after each move. On crash/restart, offer to
resume from pending entries.
- **Why now**: Current GUI Apply is single-phase with no crash recovery.
- **Technical sketch**: Modify `ApplyWorker.run()` to insert all rows as `pending`, execute per
  move, update to `done` per move, and on `__init__` check for prior `pending` rows.
- **Pattern**: Dry-run-then-commit from [S3] hyperfield, [S1] LlamaFS, [S5] aifiles.
- **Impact**: 5 | **Effort**: 3
- Source: [S33] RESEARCH.md

### N-7: ~~Security dependency update + audit~~ ✓ Shipped v8.2.0
Pin `Pillow>=12.2.0` and `PyQt6>=6.11.0` in `requirements.txt`. Add `pip-audit --fail-on-cvss 7`
as a CI gate in `ci.yml`. Audit `psd-tools` and `rarfile`/`py7zr` for path-traversal risk (see
Security notes in Coverage Matrix).
- **Why now**: Pillow has 63 historical security advisories; 12.2.0 fixes libavif, libjpeg-turbo,
  and harfbuzz issues. PyQt6 6.11.0 ships ARM64 improvements and bug fixes.
- **Impact**: 3 | **Effort**: 1
- Source: [S27] GitHub Advisory Database (Pillow), [S28] PyPI PyQt6 6.11.0

### N-8: ~~_Review batch panel in GUI~~ ✓ Shipped v8.2.0
Dedicated "Needs Review" tab showing `_Review` items with: preview image, AI confidence score,
proposed category, dropdown to confirm/reassign. Corrections feed `corrections.json`.
- **Why now**: `_Review` requires manual filesystem inspection today and grows unbounded.
- **Technical sketch**: Add `ReviewTab(QWidget)` that scans `{dest_root}/_Review/`, loads preview
  images via `asset_db.find_preview_image()`, renders as QListWidget with inline category picker.
  On confirm, calls `robust_move()` and logs to `corrections.json`.
- **Impact**: 5 | **Effort**: 3
- Source: [S3] hyperfield/ai-file-sorter batch-review pattern

### N-10: ~~Embeddings classifier MVP~~ ✓ Shipped v8.2.0
fastembed/sentence-transformers embedding chain; cosine similarity against 384 category anchors;
`--embeddings-only` CLI flag. See CHANGELOG.md v8.2.0.
- Source: [S48] sentence-transformers, [S55] Bookmark-Organizer-Pro

### N-11: ~~ReviewPanel thumbnail rendering~~ ✓ Shipped v8.2.0
QLabel/QPixmap 80×80 px thumbnails; QPixmapCache; extension-badge fallback for non-image items;
PSD composite via psd-tools `topil()`. See CHANGELOG.md v8.2.0.
- Source: [S38] TagStudio virtual list pattern, [S56] TagStudio `previews/renderer.py`

### N-13: ~~Security hardening — fonttools pin + archive isolation~~ ✓ Shipped v8.2.0
`fonttools>=4.62.1` pin (CVE-2025-66034); psd-tools subprocess isolation; archive path-traversal
validation (`os.path.realpath` prefix guard). See CHANGELOG.md v8.2.0.
- Source: [S49] fonttools CVE-2025-66034, [S41] py7zr advisories, [S42] rarfile advisories

### N-15: ~~SOURCE_CONFIGS parity test + alias-RHS guard~~ ✓ Shipped v8.2.0
Unit tests asserting SOURCE_CONFIGS key parity across classify_design / organize_run /
review_resolver, plus phantom-category alias guard. See CHANGELOG.md v8.2.0.
- Source: [S35] CHANGELOG.md v8.2.0

### N-16: ~~catalog_sync `If-Modified-Since` / ETag~~ ✓ Shipped v8.2.0
ETag/If-Modified-Since header on CatalogSyncWorker startup check; state persisted in
`catalog_sync.json`. See CHANGELOG.md v8.2.0.
- Source: [S35] CHANGELOG.md v8.2.0

### N-17: ~~Robocopy multi-thread (`/MT:8`) for cross-drive moves~~ ✓ Shipped v8.2.0
`robust_move()` passes `/MT:8`; copy-threads slider (4 / 8 / 16) in Settings → Advanced.
See CHANGELOG.md v8.2.0.
- Source: [S32] AUDIT_LESSONS.md

---

## Shipped -- WinUI Shell (ui-v0.1.0 → ui-v0.5.0)

The WinUI 3 shell (`src/FileOrganizer.UI/`) runs on an independent version cadence from the Python
core. All pages below are live in the main branch as of ui-v0.5.0 (2026-05-01).

| Page | Since | Key functionality |
|------|-------|-------------------|
| FilesPage | ui-v0.1.0 | Extension-based organizer (all MIME categories) |
| PhotosPage | ui-v0.1.0 | EXIF reader, date-based rename, location tagging |
| WatchPage | ui-v0.1.0 | Long-running auto-organize service, debounce config |
| ToolboxPage | ui-v0.1.0 | Pipeline stats, validate, asset DB, undo |
| MusicPage | ui-v0.3.0 | Picard pipeline, AcoustID fingerprinting, MusicBrainz lookup |
| VideoPage | ui-v0.3.0 | GuessIt parser, Sonarr-style quality scoring, ffprobe metadata |
| BooksPage | ui-v0.3.0 | EPUB/MOBI/PDF/CBZ support, ISBN lookup via isbnlib |
| SmartSortPage | ui-v0.4.0 | Meta-dispatcher: routes file to best-fit domain page |
| DuplicatesPage | ui-v0.4.0 | pHash BK-tree image dedup (partially ships NEXT-19) |
| FontsPage | ui-v0.4.0 | fonttools extraction, family/style classification (N-9 fonts) |
| CodePage | ui-v0.4.0 | Language detection via Pygments, project-type classifier |
| SubtitlesPage | ui-v0.4.0 | Subliminal integration, language/show detection |
| SettingsPage | ui-v0.5.0 | Theme toggle (Catppuccin/GitHub Dark/AMOLED), AcoustID key, rename patterns |
| (All pages) | ui-v0.5.0 | Per-page theme toggle, global settings propagation |

Build: `pwsh src/build.ps1` via VS 2026 MSBuild. **NOT** `dotnet build` (WinAppSDK 1.5 + .NET 10
AppX/PRI task path conflict). See `src/FileOrganizer.UI/CLAUDE.md`.

---

## NOW -- Active / Blocking (target: v8.4.0)

**Python core (v8.4.0) — 7 items**

| # | Item | Why now |
|---|------|---------|
| 1 | **NEXT-46** | DeepSeek V4 migration — `deepseek-chat` alias dies **July 24, 2026** |
| 2 | **NEXT-47** | Anthropic model refresh — Sonnet 4 / Opus 4 deprecated **June 15, 2026** |
| 3 | **NEXT-48** | Ollama Pydantic structured outputs — 1-line fix; eliminates JSON error recovery |
| 4 | **NEXT-49** | psd-tools GHSA-24p2-j2jr-386w — ZIP-bomb / OOM on malformed PSDs |
| 5 | **NEXT-15** | Hash-first DB skip — Impact 5, Effort 2; highest-ROI unblocked item |
| 6 | **NEXT-44** | LLM summary cache — eliminates redundant inference on stable libraries |
| 7 | **NEXT-11** | Video metadata deep routing — unblocked by N-9; Effort 2 |

**WinUI shell (ui-v0.6.0) — 3 items**

| # | Item | Why now |
|---|------|---------|
| 8 | **NEXT-39** | WindowsAppSDK 2.0.1 (GA April 29, 2026) — 1.5 on unsupported path |
| 9 | **NEXT-40** | RAWPage — unblocked by NEXT-39; rawpy + libraw pipeline |
| 10 | **NEXT-41** | ComicsPage — CBZ/CBR/CB7; TagStudio v9.5.5 thumbnail patterns [S39] |

---

## Shipped -- v8.3.0

Three Python-core features landed and were tagged as v8.3.0 (released 2026-05-02). See
CHANGELOG.md for full details.

### N-9: ~~Metadata extractors MVP~~ ✓ Shipped v8.3.0
New `fileorganizer/metadata_extractors/` package with `psd_extractor`, `font_extractor`,
`audio_extractor`, `video_extractor`. Wired into `classify_design.py` as a zero-AI Stage 1 ahead
of marketplace + embeddings + LLM. Hardroute threshold confidence ≥ 90; below that the hint is
informational and downstream stages still run. Phantom-category guard validates emitted names
against `_CATEGORY_SET`.
- Routing: PSD aspect-driven (9:16/square/business-card/A4) at conf 90-92; valid font headers
  (TTF/OTF/TTC/WOFF/WOFF2) at conf 95; ProRes/DNxHD video at conf 90; audio confidences capped
  below 90 per audit (duration alone is ambiguous between SFX one-shots and music intro stabs).
- Tests: 27 tests in `tests/test_metadata_extractors.py` covering import smoke, dispatcher
  routing, no-dep degradation, aspect helpers, and per-extractor mocked happy-paths.
- **Source**: [S34] RESEARCH_IDEAS.md, [S46] psd-tools v1.16.0

### N-12: ~~Provenance tracking~~ ✓ Shipped v8.3.0
`source_domain TEXT` + `first_seen_ts INTEGER` columns added to `assets` via idempotent
PRAGMA-table_info migration. UPDATE path uses `COALESCE` so `first_seen_ts` is immutable
across re-builds. New `fileorganizer/provenance.py` recognises 12 marketplace patterns plus a
7-domain piracy blocklist; piracy match wins over marketplace match. UI-safe `display_domain()`
strips blocked domains. New `python build_source_index.py --source <name> --show-provenance`
prints a per-domain histogram.
- Tests: 33 tests in `tests/test_provenance.py` (parser, piracy override, COALESCE immutability,
  legacy-DB migration).
- **Source**: [S34] RESEARCH_IDEAS.md #6, [S33] RESEARCH.md provenance track

### N-14: ~~Broken file detection~~ ✓ Shipped v8.3.0
New `fileorganizer/broken_detector.py` with `check_image` (PIL.Image.verify under a 20 MB cap),
`check_video` (ffprobe -show_error; treats non-empty stderr as broken even at rc=0 per audit
fix), and `check_archive` (zipfile/rarfile/py7zr per-format testzip with no-dep degradation).
`is_broken(path)` dispatcher. Standalone CLI: `python -m fileorganizer.broken_detector --scan
<dir>` exits 1 on any broken file. New `broken INTEGER NOT NULL DEFAULT 0` column on
`asset_files` (idempotent migration). **Iter 2 follow-up**: PreflightDialog Step 5 wiring via
`broken_detector.scan_paths(paths, max_per_root=10, max_total=200)` — surfaces broken files
at the pre-flight gate, declares missing optional verifiers as partial coverage.
- Tests: 33 tests in `tests/test_broken_detector.py` (dispatcher, no-dep, real corrupt zip,
  ffprobe stderr handling, CLI exit codes, schema migration, scan_paths bounded sampling).
- **Source**: [S44] Czkawka v11.0.0 broken video detection, [S34] RESEARCH_IDEAS.md

### Provenance back-fill ✓ Shipped v8.3.0 (iter 2 follow-up to N-12)
`asset_db.cmd_backfill_provenance(db_path, dry_run)` populates `source_domain` +
`first_seen_ts` on assets rows that pre-date N-12. Idempotent (WHERE source_domain IS NULL
OR first_seen_ts IS NULL). Dry-run mode does not mutate the schema even on legacy DBs that
need the N-12 columns added — surfaces a `migration_pending` flag instead. CLI:
`python asset_db.py --backfill-provenance [--dry-run]`.
- Tests: 5 in `tests/test_provenance.py` (happy path, dry-run no-commit, idempotency,
  unmatched-name, legacy-schema dry-run safety).

---

## NEXT -- High Value, Well-Scoped (target: v8.4 / v9.x)

### Automation & Workflow

**NEXT-1: Watch mode daemon** ✓ Core MVP shipped
Monitor source folders for new files. Auto-classify+move when files stabilize (debounce window:
default 30s -- avoids partially-downloaded-archive false positives). Option to register as a
Windows background task or Task Scheduler trigger.
- **Core shipped**: `fileorganizer/watch_mode.py` with `DebounceQueue`, file event handler, state
  persistence (watch_state.db), CLI interface (--start, --stop, --status, --log). 18 tests passing.
- **Remaining**: WinUI 3 Settings → Watch Mode tab (enable/disable, debounce slider, log viewer).
  Task Scheduler registration for Windows background task startup.
- **Impact**: 4 | **Effort**: 4 (core 2 + UI 2) | Risk: debounce stability on network drives
- **Parity with**: [S1] LlamaFS, [S5] aifiles, [S20] Hazel, [S21] File Juggler

**NEXT-2: ~~YAML rule export~~** ✓ Shipped v8.3.0 (iter 2)
CLI shipped via `python classify_design.py --export-rules [<path>|-]`.
`fileorganizer/yaml_rule_export.py` builds organize-cli-compatible YAML from
the canonical taxonomy + per-category extension hints + reverse-derived
keywords from `CATEGORY_ALIASES`. PyYAML used when present, deterministic
hand-rolled emitter as fallback (no new hard dep). 14 tests.
GUI export tile under Settings -> Rules -> Export as YAML still planned
(deferred — CLI is the production path; GUI is sugar).
- **Impact**: 4 | **Effort**: 2 | Source: [S8] https://github.com/tfeldmann/organize

**NEXT-3: Hazel-style rule chains**
Multi-condition chains: "if source matches X AND LLM confidence < 70 AND file size > Z, move to
A THEN rename as B THEN webhook C". Nested conditions with AND/OR. AST:
`RuleChain([Condition(...)], [Action(...)])`.
- **Impact**: 4 | **Effort**: 4 | Parity with: [S20] Hazel, [S21] File Juggler, [S8] organize-cli
- Source: [S20] https://www.noodlesoft.com/hazel/ , [S21] https://www.filejuggler.com/features/

**NEXT-4: Dry-run simulation (all operations)** ✓ Core shipped
Every CLI command and GUI action must have a full dry-run path that previews the exact list of
moves, renames, and deletes without touching the filesystem. Emit an editable JSON plan file
before commit.
- **Core shipped**: `fileorganizer/dry_run_planner.py` with DryRunPlan, FileOperation, PlanExecutor,
  atomic execution with rollback. 21 tests passing. Supports JSON save/load, schema validation,
  per-operation enabled flags.
- **Remaining**: GUI integration (PreflightDialog Step 6 with operation list + toggles).
  organize_run.py CLI flags (--dry-run, --plan-file, --commit).
- **Impact**: 4 | **Effort**: 2 (core 1 + UI 1) | Parity with: [S8] organize-cli `sim` mode, [S20] Hazel "Test Rule"

**NEXT-5: Minimal-diff re-scan index** ✓ Core shipped
Cache folder fingerprint + mtime from each run. On re-scan, skip folders whose fingerprint and
mtime are unchanged. Reduces re-run cost ~70% on large libraries where most items are already
classified.
- **Core shipped**: `fileorganizer/folder_cache.py` with compute_folder_fingerprint(), FolderCache
  class, TTL-based expiration (30 days default), cleanup_expired(), get_stats(). 18 tests passing.
  Typical workflow shows ~0% skip on first pass, ~100% skip on second pass with same contents.
- **Remaining**: Integration into organize_run.py (--skip-unchanged, --invalidate-cache flags).
- **Impact**: 4 | **Effort**: 3 (core 2 + integration 1) | Parity with: [S1] LlamaFS minimal-diff index
- Source: [S1] https://github.com/iyaja/llama-fs

**NEXT-6: Parallel LLM calls** ✓ Core shipped
Batch DeepSeek/GitHub Models API calls concurrently via `asyncio` + `aiohttp`. Current serial
approach is the primary throughput bottleneck on 19,531-item loose-files runs.
- **Core shipped**: `fileorganizer/parallel_classifier.py` with AsyncClassifier, configurable concurrency
  (default 4 workers) and batch size (default 3 folders/request). aiohttp for non-blocking I/O,
  automatic fallback to serial when aiohttp unavailable. 15+ unit tests passing.
  Typical speedup: 3–5x on batches of 50–100 folders (tuned by model and queue depth).
- **Remaining**: Integration into organize_run.py classification pipeline (CLI --parallel flag,
  settings UI for concurrency/batch tuning). Benchmarking on real large runs (1000+ folders).
- **Impact**: 4 | **Effort**: 3 (core 2 + integration 1)

**NEXT-7: Adaptive learning from corrections** ✓ Core shipped
When a user corrects a classification, record the correction in `corrections.json` keyed by
folder fingerprint AND extracted keyword pattern. On next run: exact-fingerprint matches
auto-apply the correction; keyword-pattern matches inject it as a few-shot example into the batch prompt.
- **Core shipped**: `fileorganizer/adaptive_corrector.py` with CorrectionRecord, AdaptiveCorrector,
  keyword extraction, fingerprint matching, few-shot injection. corrections.json schema v1.0 with
  age-based filtering (365 days, hard cap 5000 corrections). 20+ tests passing.
  Design: Low-confidence misclassifications weighted higher for future injection.
- **Remaining**: GUI hook in rename dialog (offer "correct" button). Integration into classify pipeline
  (check apply_correction before LLM, inject few-shot into system prompt).
- **Impact**: 4 | **Effort**: 3 (core 2 + integration 1) | Parity with: [S6] thebearwithabite adaptive learning loop
- Source: [S6] https://github.com/thebearwithabite/ai-file-organizer

**NEXT-8: Scheduled scans per profile**
Register scan profiles with Windows Task Scheduler (or launchd/systemd on macOS/Linux).
GUI: Settings -> Schedules -> New Schedule (source, dest, time, recurrence).
- **Impact**: 3 | **Effort**: 3
- Source: [S21] File Juggler task scheduling, [S20] Hazel run-at-schedule

### Classification Accuracy

**NEXT-9: AEP RIFX binary parser**
After Effects project files use the RIFX binary container (reverse-endian RIFF). Parse to
extract: composition names and durations, required plug-in names, minimum AE version, resolution,
frame rate. Store in `asset_files.metadata` or a new `asset_meta` table.
Candidate library: `aeptools` (Python) or custom RIFX reader.
- **Impact**: 5 | **Effort**: 4 | Leapfrog: no OSS competitor parses AEP metadata for classification
- Source: [S33] RESEARCH.md, [S34] RESEARCH_IDEAS.md, [S25] RIFX format

**NEXT-10: MOGRT manifest parser**
`.mogrt` files are ZIP archives with an embedded JSON manifest containing: Motion Graphics
Template name, editable parameters, required fonts, minimum Premiere version. Pure Python
(`zipfile` + `json`). Store extracted fields in `asset_files.metadata`.
- **Impact**: 4 | **Effort**: 2

**NEXT-11: Video metadata deep routing (FFmpeg expansion)**
Extend the N-9 `video_extractor.py` MVP with deep routing rules: 9:16 vertical video →
`Social Media`, looping clips ≤ 15 s → `Motion Graphic`, codec=ProRes/DNXHD/XDCAM →
`Broadcast / Cinema Stock`, duration > 5 min → `Tutorial Video`. Add `video_codec`,
`video_resolution`, `video_duration`, `video_fps` to `asset_files.metadata`. The ffprobe
subprocess pattern is established in N-9; this item adds routing rules only. Do not use the
stale `ffmpeg-python` package (last release 2019); use `subprocess.run(['ffprobe', ...])` directly.
- **Impact**: 4 | **Effort**: 2 | **Depends on**: N-9
- Source: [S15] digiKam FFmpeg pipeline https://www.digikam.org/about/, [S44] Czkawka v11.0.0
  broken video detection, [S34] RESEARCH_IDEAS.md

**NEXT-12: LLaVA visual classification**
Route image and PDF mimes to a local multimodal model (`gemma3:4b` or `qwen3.5:4b` — both
support Ollama structured outputs via `format=schema` as of v0.22.1 [S77]) when extension-only
confidence is low. The preview image path is already known from `asset_db.find_preview_image()`.
Pass `format=ClassifyResult.model_json_schema()` to `ollama.chat()` to guarantee schema-valid JSON
without the current regex extraction fallback.
- **Impact**: 4 | **Effort**: 4
- Source: [S2] QiuYannnn Local-File-Organizer, [S6] thebearwithabite, [S77] Ollama structured outputs

**NEXT-13: Confidence calibration display**
Show per-category probability bars in the preview panel. Let user click a runner-up label to
override AI suggestion. Record overrides as corrections (feeds NEXT-7).
- **Impact**: 4 | **Effort**: 2

**NEXT-14: Two-stage AI prompt (file type then subcategory)**
Stage 1 asks "what file type is this template?" (AE/Premiere/PSD/AI/etc.) with zero context
needed. Stage 2 uses the confirmed file type as context for a tighter subcategory prompt.
Current single-stage approach conflates file-type detection with subcategory selection, causing
cross-type misclassifications (e.g., a PSD classified as an After Effects template).
- **Impact**: 4 | **Effort**: 2
- Source: [S36] CLAUDE.md, existing `classify_design.py` analysis

**NEXT-15: Hash-first DB skip (fingerprint lookup at classify time)**
Before any AI call on a folder, compute the folder fingerprint (SHA-256 of contained file hashes)
and query `asset_db`. If the fingerprint is known, return the stored category at confidence 100
with zero API cost. Expected skip rate: ~60-70% of common templates already in the community DB.
- **Impact**: 5 | **Effort**: 2
- Source: [S32] AUDIT_LESSONS.md ("Community fingerprint DB changes the cost model"), `asset_db.py`

**NEXT-16: Negative keyword rules**
Per-category "must NOT contain" term list to resolve overlapping categories.
Example: `Wedding` must not contain "Corporate" -> routes to `After Effects - Corporate` instead.
- **Impact**: 3 | **Effort**: 2

**NEXT-17: Marketplace enrichment expansion**
Extend `marketplace_enrich.py` beyond Envato to: Creative Market (API available), Freepik (API
key), Motion Array, FilterGrade, Shutterstock, Adobe Stock. Each needs a URL pattern + parser.
mnamer [S58] models exactly this pattern in `mnamer/providers.py` (Provider ABC) +
`mnamer/endpoints.py` (low-level wrappers for OMDb/TMDb/TVDb/TvMaze with ID caching, error
handling, and retry logic) — port the Provider ABC verbatim and add one subclass per
marketplace.
- **Impact**: 4 | **Effort**: 3
- Source: [S34] RESEARCH_IDEAS.md, [S33] RESEARCH.md, [S58] mnamer Provider ABC pattern

**NEXT-18: Marketplace update alerts**
For items with a known marketplace ID, periodically check if a newer version has been published.
Flag in UI: "Update available for 3 items in After Effects - Slideshow".
- **Impact**: 3 | **Effort**: 3

### Deduplication

**NEXT-19: Perceptual hash dedup (preview images)**
Use `imagehash` (pHash / dHash / crop-resistant hash) on `preview_image` files to detect visually
similar templates even when files differ slightly (re-exported preview, different resolution).
BK-tree + Hamming distance for sub-linear similarity search (pattern from [S10] Czkawka).
`imagehash` supports pHash, dHash, wHash, average hash, colorhash, and crop-resistant hash;
choose crop-resistant hash for design asset previews (handles partial crops, watermark variants).
The local DeDuper [S52] tiered hash architecture and DuplicateFF [S53] 5-stage elimination
pipeline are both worth borrowing as I/O-saving filters before the pHash phase: skip any pair
whose preview-file size or 4 KB head/tail hash differs first.
- **Impact**: 4 | **Effort**: 3
- Source: [S10] https://github.com/qarmin/czkawka, [S47] imagehash (JohannesBuchner),
  [S52] DeDuper tiered hash, [S53] DuplicateFF staged pipeline

**NEXT-20: Cross-library fingerprint dedup**
Compare G:\ + I:\ (and external drives) by `folder_fingerprint` SHA-256 across roots. Show a
merge/keep/archive dialog per duplicate group.
- **Impact**: 4 | **Effort**: 3
- Source: [S11] fclones cross-library pattern https://github.com/pkolaczk/fclones

**NEXT-21: Version-aware dedup**
If two items share a marketplace ID but have different file counts or fingerprints, one is likely
a newer version. Keep the one with more files; archive the other with a reason note.
- **Impact**: 3 | **Effort**: 2

### GUI

**NEXT-22: Category thumbnail browser**
New "Browse" tab: grid/list view of the organized library with preview thumbnails from
`asset_db.find_preview_image()`. Per-item details panel: category, marketplace, confidence, file
count, total size, AE version (if parsed), marketplace link. Implement as `QListView` with a
custom delegate + lazy thumbnail loading to handle 10,000+ item collections without freezing.
TagStudio v9.5.6 shipped infinite scrolling via virtual list rendering [S38] — use the same
pattern: render only the visible viewport rows, load thumbnails asynchronously on scroll. N-11
already ships the `Pillow + QPixmap + QPixmapCache` pattern; NEXT-22 reuses it at Browse scale.
The local Images viewer [S57] implements an analogous `VirtualizingStackPanel` filmstrip with
`ScrollIntoView()` centering — its layout strategy maps directly onto `QListView` + custom
delegate.
- **Impact**: 5 | **Effort**: 4 | Primary commercial benchmark: [S19] Eagle App
- Source: [S19] https://eagle.cool, [S38] TagStudio v9.5.6 infinite scrolling, [S22] Adobe Bridge,
  N-11 (thumbnail Pillow+QPixmap pattern established), [S57] Images viewer
  `MainWindow.xaml.cs` virtual filmstrip

**NEXT-23: Drag-and-drop reclassification**
Drag any item from one category to another in the Browse tab tree. Records the correction in
`corrections.json` and increments a `user_corrections` counter in the DB. Same-fingerprint items
in future runs auto-apply the correction without AI.
- **Impact**: 4 | **Effort**: 3

**NEXT-24: Undo history visualizer**
"History" tab: timeline of all moves from `organize_moves.db` with per-item or per-run undo.
Show: timestamp, source, destination, confidence score, undo button. Completes N-6.
- **Impact**: 5 | **Effort**: 3
- Source: [S3] hyperfield/ai-file-sorter undo-after-close

**NEXT-25: Post-apply HTML report**
After each apply run, generate an HTML/JSON "what changed" report with thumbnails. Auto-open in
default browser or display inline in a new Results tab.
- **Impact**: 3 | **Effort**: 2

**NEXT-26: Batch rename with preview**
GUI dialog showing old name -> proposed canonical name (`{CAT_CODE}_{ID}_{CLEAN_NAME}`) for all
items in a category, with inline edit before committing. CLI: opt-in `--rename` flag. mnamer
[S58] already has the template formatter (`MetadataMovie.__format__()` with regex-based
placeholder substitution + `{name}`, `{year}`, `{season:02d}` style padding/case converters)
and a `--test` dry-run path — both directly portable to the GUI preview dialog.
- **Impact**: 3 | **Effort**: 2
- Source: [S22] Adobe Bridge batch rename, [S15] digiKam rename templates, [S58] mnamer
  `MetadataMovie.__format__()` + `--test` dry-run

### Plugin Ecosystem

**NEXT-27: Plugin classifier SDK**
Document the existing plugin interface. Ship 3 reference plugins: camera-raw router (LibRaw),
SD/ComfyUI output sorter (prompt keyword hash), DICOM medical image classifier. Publish
`plugins/README.md` + `plugin_interface.py` base class.
- **Impact**: 4 | **Effort**: 3
- Source: [S6] thebearwithabite plugin API, [S15] digiKam plugin system

**NEXT-28: Webhook on organize**
POST a JSON action summary to a user-configured URL on each apply completion. Enables n8n, Zapier
self-hosted, Home Assistant downstream automations.
- **Impact**: 3 | **Effort**: 2

### Testing & Distribution

**NEXT-29: Test coverage expansion**
Add unit tests for: `_CATEGORY_SET` phantom rejection, position-based batch mapping, cross-drive
path selection (os.rename vs robocopy), confidence threshold branching, ProviderRouter fallback
chain. Target: 10+ test functions covering core safety invariants.
- **Impact**: 4 | **Effort**: 3
- Source: Internal -- currently only 1 test file (`test_organize_run.py`)

**NEXT-30: CI multiplatform builds**
Add macOS and Linux PyInstaller targets to `release.yml` using `macos-latest` and
`ubuntu-latest` runners. Ship platform-specific binaries in GitHub Release.
- **Impact**: 3 | **Effort**: 2
- Source: [S1] LlamaFS CI, [S8] organize-cli cross-platform, [S2] Local-File-Organizer

**NEXT-31: Scan time measurement**
Record wall-clock time for each scan phase (index build, classification, enrichment, pre-flight)
and display in the GUI status bar and in post-apply HTML report (NEXT-25). Store `scan_duration_ms`
per run in `organize_moves.db`. Helps users identify which pipeline stage is the bottleneck on
large libraries.
- **Impact**: 2 | **Effort**: 1
- Source: [S44] Czkawka v11.0.0 scan time display, internal profiling need

**NEXT-32: Dedup similarity grouping improvements**
When running perceptual hash dedup (NEXT-19), group near-identical items into clusters before
presenting the merge/keep dialog. Use complete-linkage clustering: two items in the same cluster
only if every pair is within Hamming distance threshold. Prevents over-merging when a cluster
contains both a genuine duplicate and a similar-but-different item.
- **Impact**: 3 | **Effort**: 2 | **Depends on**: NEXT-19
- Source: [S44] Czkawka v11.0.0 similarity grouping overhaul, [S47] imagehash clustering patterns

### Resilience & Operations

**NEXT-33: xxhash / blake3 fast fingerprint mode**
SHA-256 dominates dedup wall time on multi-TB scans. fclones [S11] switched to blake3 for
exactly this reason; it is roughly 10× faster than SHA-256 on modern CPUs. Add a
`--fingerprint-algo {sha256,blake3,xxhash}` flag to `asset_db.py` and `build_source_index.py`,
default `blake3` when the optional `blake3` package is installed (fallback `sha256` when not),
and store the algorithm tag in a new `algo TEXT NOT NULL DEFAULT 'sha256'` column on
`assets.folder_fingerprint`. Mixing algorithms in one DB is fine because the column is
self-describing and `INSERT OR IGNORE` already works on the textual fingerprint string.
The DeDuper [S52] tiered-hash pattern (size → 64 KB head/tail partial hash → full hash) and
the DuplicateFF [S53] 4 KB prefix/suffix elimination pipeline are both directly applicable
as I/O-saving stages above any fingerprint algo.
- **Why now**: NEXT-19 (perceptual dedup) and NEXT-20 (cross-library dedup) both gate on
  fingerprint speed. The roadmap was missing a faster fingerprint primitive.
- **Impact**: 4 | **Effort**: 2 | **Pairs with**: NEXT-19, NEXT-20
- Source: [S11] fclones blake3 default, [S52] DeDuper tiered hash, [S53] DuplicateFF
  staged hash pipeline, blake3 PyPI https://pypi.org/project/blake3/

**NEXT-34: Provider cost cap + 429 backoff + automatic failover**
Provider routing exists today (auto / github_only / deepseek_only / ollama_only) but has no
daily $ budget cap, no automatic exponential backoff on 429s, and no failover-on-error chain.
Production runs need all three:
1. **Cost cap**: per-provider daily budget in `provider_costs.json`; pre-flight check before
   each call against the embedded pricing table from octopus-factory [S54] `cost-estimate.sh`
   (model → input/output/cache_read/cache_write $/M tokens).
2. **429 backoff**: `tenacity` retry with exponential backoff on 429 / 5xx; lockout TTL of
   60 min on persistent 429 (mirroring octopus-factory's `copilot-fallback.sh` quota lockout
   pattern).
3. **Failover chain**: when the active provider locks out, automatically fall through the
   user-configured chain (e.g., DeepSeek → GitHub Models → Ollama).
The Bookmark-Organizer-Pro [S55] `ai.py` `AIProviderInfo` dataclass already abstracts
multi-provider routing in pure Python; FileOrganizer can lift that pattern and layer the
cost / backoff / failover logic on top.
- **Why now**: A 19,531-item loose-files run at 60 items/batch is 326 API calls. One 429
  storm currently aborts the whole run with no retry.
- **Impact**: 4 | **Effort**: 3 | **Pairs with**: NEXT-6 (parallel async)
- Source: [S54] octopus-factory `cost-estimate.sh` + `copilot-fallback.sh`, [S55]
  Bookmark-Organizer-Pro `ai.py`, tenacity https://tenacity.readthedocs.io

**NEXT-35: Symlink / junction / reparse-point detection in pre-flight**
Windows junction points and reparse points cause `shutil.move` to traverse outside the source
tree silently. The N-4 PreflightDialog scans for trailing-space and >260-char paths but does
not flag reparse points. Extend `PreflightWorker` (in `fileorganizer/dialogs/tools.py`) with a
`stat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT` check on every shallow child;
report findings in the dialog under a new "Reparse points (N)" warning row. Block apply when
a reparse target points outside the configured source root (path traversal risk).
- **Why now**: This codepath has burned at least one user with a NetBIOS junction silently
  re-pointing into `C:\Windows`. Pre-flight is the right place to catch it.
- **Impact**: 3 | **Effort**: 2
- Source: Microsoft `FILE_ATTRIBUTE_REPARSE_POINT` https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants

**NEXT-36: Free-space *reserve* via sparse file (not just check)**
N-4 (shipped) checks `shutil.disk_usage` once at apply start, but a concurrent process can
eat the buffer mid-run. Pre-allocate `dst_root/.fileorganizer.reserve` as a sparse file sized
to (estimated bytes-to-move × 1.10), delete on clean completion or crash recovery. Sparse
files reserve no physical blocks until written, so the cost is metadata-only, but the
filesystem rejects competing writes that would push it over the reserve.
- **Why now**: A 50 GB Apply on a 60 GB free drive can fail mid-way today if Windows Update
  or another tool consumes the buffer. Cheap insurance for the multi-TB G:↔I: runs.
- **Impact**: 3 | **Effort**: 2
- Source: Win32 `FSCTL_SET_SPARSE` https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_set_sparse

**NEXT-37: organize_moves.db vacuum + retention policy**
`organize_moves.db` (SQLite WAL after the N-6 audit fix) grows unbounded. After 100k moves
the DB and its WAL can be hundreds of MB, hurting both startup time (the journal is read on
every Apply click for crash detection) and `--undo-last N` query latency. Add:
1. A maintenance hook on app exit: `VACUUM` after every 10 successful runs.
2. A retention setting in `confidence_settings.json` (`journal_retention_days`, default 90):
   on startup, `DELETE FROM moves WHERE status='done' AND ts_done < now-N`.
3. Settings → Maintenance → "Vacuum journal now" button.
- **Why now**: The journal already shipped with WAL pragmas (post-audit). Maintenance is the
  natural follow-up before the 33 TB run produces a journal that's bigger than `org_index.json`.
- **Impact**: 2 | **Effort**: 1
- Source: SQLite VACUUM https://www.sqlite.org/lang_vacuum.html, internal observation

**NEXT-38: GUI worker crash dialog + unified log viewer**
Unhandled exceptions raised inside QThread workers (Apply, Scan, ReviewApply, CatalogSync, etc.)
die silently today — the worker's `run()` returns, the parent never sees a `finished` signal
with error info, and the user sees a stalled progress bar. Install a `qInstallMessageHandler`
plus `sys.excepthook` override that:
1. Captures every uncaught exception from any thread to
   `%APPDATA%/FileOrganizer/crash.log` with timestamp + traceback.
2. Shows a non-blocking toast "An apply worker crashed — view log" with a one-click open of
   the log viewer (a new `LogViewerDialog` in `fileorganizer/dialogs/`).
3. Preserves any pending journal rows (the N-6 resume flow already handles re-attempting them).
- **Why now**: When a worker dies the Qt event loop keeps the GUI responsive but reports no
  failure — easy to mistake a crashed run for a slow one. Crash logs also feed the optional
  L-16 telemetry channel.
- **Impact**: 3 | **Effort**: 2
- Source: Qt `qInstallMessageHandler` https://doc.qt.io/qt-6/qtlogging.html

### WinUI Shell

**NEXT-39: WindowsAppSDK 2.0 upgrade**
Upgrade the WinUI 3 shell from WinAppSDK 1.5 (current) to 2.0.1 (GA April 29, 2026). 2.0 is
the first major version since WinAppSDK 1.0 (Nov 2021) and adopts Semantic Versioning; the
package family name now tracks the major version (`Microsoft.WindowsAppSDK.2.0`). Side-by-side
install with 1.x is supported, but test the package manifest upgrade path before merging. A
sensible approach is to stage via the 1.8 NuGet first (validate Storage Pickers / AI APIs), then
bump to 2.0. Concrete unlocks (cumulative 1.7 → 1.8 → 2.0):
- **`TitleBar` control** (1.7): replaces current manual `AppWindowTitleBar` wiring with a
  declarative XAML control; cleaner drag region, subtitle support, icon slot.
- **`SetTaskBarIcon` / `SetTitleBarIcon`** (1.7): independent icon control per page — show a
  camera icon when PhotosPage is open vs. the default app icon.
- **`AppWindowTitleBar.PreferredTheme`** (1.7): opt-in titlebar dark/light independent of OS
  system setting; improves the Catppuccin + AMOLED black theme polish.
- **`OAuth2Manager`** (1.7): replaces the current manual browser-launch + clipboard-paste flow for
  AcoustID API key registration in MusicPage with a proper in-app OAuth 2.0 PKCE flow.
- **`BackgroundTaskBuilder`** (1.7, full-trust COM): register WatchPage as a proper Windows
  background task instead of the current Task Scheduler workaround; survives user log-off.
- **`Microsoft.Windows.Storage.Pickers`** (1.8, expanded in 2.0): `FolderPicker` gains
  `PickMultipleFoldersAsync`, `SuggestedStartFolder`, `SuggestedFolder`, and
  `SettingsIdentifier` (persists last-used folder across sessions). `FileOpenPicker` gains
  `FileTypeChoices`, `SuggestedFolder`, and `Title`. Drop the current manual path-entry
  dialog in SourcePage and DestPage in favor of these native pickers with persistent memory.
- **`SystemBackdropElement`** (2.0): places Mica or Acrylic anywhere inside the XAML layout
  tree with a `CornerRadius` for card-style frosted-glass panels. Closes the `AcrylicBrush.
  BackgroundSource` gap that existed since WinUI 3 launch; directly improves the theme system.
- **`IXamlCondition`** (2.0): custom XAML conditionals evaluated at parse time based on
  feature flags, device capabilities, or config values — replaces code-behind `Visibility`
  hacks for optional page sections (e.g., hide ExifTool row when not installed).
- **Migration risk**: SemVer scheme change means the next side-by-side release will be 3.0, not
  2.1. Package family name changes may break existing MSIX installation paths on dev machines;
  run the CI packaging job against 2.0 before merging. ARM64EC+LTCG builds have a known MSVC
  internal compiler error (WinAppSDK 2.0 provides an opt-out via
  `WindowsAppSDK_Arm64EcCompilerWorkaround`).
- **Impact**: 4 | **Effort**: 3 | (effort increase vs. prior: 1.7 had no breaking API surface)
- Source: [S73] WindowsAppSDK 2.0.1 release notes, [S74] WindowsAppSDK 1.8.0 release notes,
  [S62] WindowsAppSDK 1.7.0 release notes, [S63] WindowsAppSDK 1.6.0 release notes

**NEXT-40: RAWPage — camera raw file organizer**
New WinUI shell page for DNG / CR2 / NEF / ARW / ORF / RW2 raw photo files. Scope:
- Extract EXIF via `rawpy` (libraw Python binding): camera make/model, capture date, ISO, focal
  length, GPS coordinates if present.
- Thumbnail via `rawpy.postprocess()` → PIL → QImage at 512×512 (cached in `%APPDATA%`).
- Date-based folder routing (`YYYY/YYYY-MM-DD/Make_Model/`), or user-configurable rename pattern
  using the same token engine as PhotosPage.
- Pre-flight: identify files with corrupt RAW headers (libraw `LibRawFileUnsupportedError`) and
  flag in the "Broken files" row (N-14 extension).
`rawpy` is already a proven pattern: Czkawka v11.0.0 [S44] ships RAW JPEG preview extraction;
TagStudio's renderer.py [S56] dispatches RAW thumbnails via the same library.
- **Impact**: 4 | **Effort**: 3
- Source: [S44] Czkawka v11.0.0 RAW JPEG preview extraction, [S56] TagStudio RAW renderer,
  rawpy PyPI https://pypi.org/project/rawpy/

**NEXT-41: ComicsPage — comic archive support (CBZ / CBR / CB7 / CBT)**
New WinUI shell page for comic archives. Scope:
- Extract first page as thumbnail (PIL for CBZ/ZIP, patoolib for CBR/RAR, py7zr for CB7/7z).
- Parse filename series metadata: detect `(Series Name) #012 (Publisher) (Year).cbz` and
  `Series_Name_v01c01.cbz` patterns. Map to `Comics/<Publisher>/<Series>/Volume N/` folder tree.
- Series detection: group CBZ files with common prefix into a series and suggest bulk rename
  to a canonical pattern.
TagStudio v9.5.6 [S64] confirmed CB7/CBR/CBT thumbnail rendering is feasible and ships a
working renderer for all four archive formats.
- **Impact**: 3 | **Effort**: 3
- Source: [S64] TagStudio v9.5.6 CB7/CBR/CBT thumbnails, [S41] py7zr Python bindings,
  [S42] rarfile Python bindings

### Classification & Pre-flight

**NEXT-42: "Bad names" scanner in pre-flight**
Extend `PreflightWorker` to flag files with naming problems that will cause silent failures
or taxonomy drift downstream:
- Non-ASCII characters in filename on NTFS volumes set to ASCII codepage.
- Uppercase-only file extension (`.JPG`, `.MP4`): organize-cli [S69] normalizes extensions;
  FileOrganizer should flag these before classify so the extension-based router sees `.jpg`.
- Reserved Windows characters in filename (`< > : " / \ | ? *`).
- Filename > 200 characters (leaves headroom below the 260-char path limit).
- Trailing or leading spaces (already partially handled but not pre-flight reported).
Show results in PreflightDialog under "Name issues (N)". Add `--fix-bad-names` CLI flag that
auto-normalizes extensions and strips reserved characters in-place before classify.
Czkawka v11.0.0 [S44] ships a "bad names" scanner as a first-class mode, confirming user demand.
- **Impact**: 3 | **Effort**: 1
- Source: [S44] Czkawka v11.0.0 "bad names" mode, N-4 pre-flight infra (shipped)

**NEXT-43: ExifTool integration in metadata pipeline**
Support `exiftool` as a supplementary metadata backend in `metadata_extractors/` (N-9).
ExifTool reads 800+ formats including proprietary AE/PSD/Sketch embedded metadata not accessible
via Python libraries. Integration:
- Detect `exiftool` via `FILEORGANIZER_EXIFTOOL_PATH` env var (mirrors organize-cli's
  `ORGANIZE_EXIFTOOL_PATH` pattern [S69]).
- On N-9 extractor miss (result confidence < 50%), invoke `exiftool -json <path>` via subprocess
  and merge the parsed fields into the existing extractor result dict.
- Map ExifTool fields: `XMP:Category`, `XMP:Subject[]`, `IPTC:Keywords`, `QuickTime:Comment`
  → keyword list fed into the keyword classifier (NEXT-2 path).
- **Impact**: 4 | **Effort**: 2 | **Depends on**: N-9
- Source: [S69] organize-cli v3.0.0 exiftool support, ExifTool docs
  https://exiftool.org/exiftool_pod.html

### Performance & Caching

**NEXT-44: LLM summary cache (SQLite)**
Cache the LLM classification response for each folder fingerprint. On re-scan of a folder
whose fingerprint matches the cache, return the cached result instantly without an API call.
Schema: new `llm_cache` table in `organize_moves.db`:
  `(fingerprint TEXT PK, model TEXT, prompt_hash TEXT, response_json TEXT, ts INTEGER)`.
Cache key: `(fingerprint, model_id, prompt_hash)` — invalidates automatically when the model
or prompt template changes. Expiry: user-configurable TTL (default 30 days) cleaned on startup.
FileWizardAI [S66] and thebearwithabite [S65] both ship LLM caching; on stable asset libraries
(the common case) this eliminates >90% of API calls on re-runs.
- **Impact**: 4 | **Effort**: 2 | **Depends on**: N-9 (metadata pipeline wired in)
- Source: [S66] FileWizardAI SQLite summary cache, [S65] thebearwithabite review-queue cache

**NEXT-45: Confidence calibration (Platt scaling / isotonic regression)**
The current classifier outputs raw logit-derived probabilities that are not well-calibrated:
a reported "85% confidence" does not reliably mean the prediction is correct 85% of the time.
This creates false trust in the pre-flight confidence display (NEXT-13) and pollutes the
correction feedback loop (NEXT-7) with spuriously "high confidence" mislabels.
Fix: wrap the final category predictor with `sklearn.calibration.CalibratedClassifierCV` using
Platt scaling (`method='sigmoid'`) for multi-class outputs and isotonic regression
(`method='isotonic'`) when the calibration set is ≥1000 samples. Calibration set: the
`corrections.json` accumulation from NEXT-7. At <200 samples, use temperature scaling only
(a single scalar learned via logit adjustment). Re-calibrate on every 500 new correction rows.
Expose calibration quality as a reliability diagram (expected vs. actual confidence) in
Settings → Diagnostics → Calibration. Post-calibration the NEXT-13 confidence bars will
accurately reflect prediction reliability, and NEXT-7 thresholds can be tightened from the
current 70% cutoff to a calibrated 80%.
- **Impact**: 3 | **Effort**: 3 | **Depends on**: NEXT-7 (corrections accumulation), NEXT-13 (confidence display)
- Source: [S34] RESEARCH_IDEAS.md item #9 (Platt scaling, isotonic regression,
  `CalibratedClassifierCV`)

**NEXT-46: DeepSeek V4 model migration** ⚠️ DEADLINE July 24, 2026
DeepSeek is retiring the `deepseek-chat` and `deepseek-reasoner` aliases on July 24, 2026.
After that date, any call to those names returns an error. Migration targets:
`deepseek-chat` → `deepseek-v4-flash` (fast, low-cost);
`deepseek-reasoner` → `deepseek-v4-pro` (full reasoning). Update all string literals in
`classify_design.py`, the provider router, and Settings UI dropdowns. Add an alias-deprecation
warning in the provider factory that logs a `DeprecationWarning` when the legacy names are passed.
Regression test: mock the DeepSeek endpoint; assert legacy name raises warning; assert new names
succeed without warning.
- **Impact**: 5 | **Effort**: 1 | **Tier**: NOW (hard deadline)
- Source: [S78] DeepSeek V4 announcement; [S79] DeepSeek API docs

**NEXT-47: Anthropic model refresh**  ⚠️ DEADLINE June 15, 2026
`claude-3-haiku` has already been deprecated (April 2026). `claude-sonnet-4` and
`claude-opus-4` are being deprecated June 15, 2026. Migration targets:
`claude-3-haiku` → `claude-haiku-4-5`;
`claude-sonnet-4` → `claude-sonnet-4-5`;
`claude-opus-4` → `claude-opus-4-5`.
Pin minimum versions in requirements.txt: `anthropic>=0.44.0`.
Add model-ID validation at startup that warns if a configured model ID is on the known-dead list.
- **Impact**: 5 | **Effort**: 1 | **Tier**: NOW (hard deadline)
- Source: [S80] Anthropic model deprecation notice; [S81] Anthropic model versioning docs

**NEXT-48: Ollama Pydantic structured outputs**
Ollama ≥ v0.22.1 supports `format=PydanticModel.model_json_schema()` in `ollama.chat()`,
guaranteeing schema-valid JSON output without prompt-engineering hacks. The current Ollama adapter
uses a regex extraction fallback path that fires on ~3% of calls (malformed JSON from smaller
models). Replace the regex path: pass `format=ClassifyResult.model_json_schema()` directly.
This is a 1-line change in `providers/ollama_provider.py`. Eliminates the JSON parse error retry
loop entirely and reduces Ollama call latency by ~40 ms per call (no retry). Also unblocks
reliable NEXT-12 structured vision output.
- **Impact**: 3 | **Effort**: 1 | **Tier**: NOW (pairs with NEXT-49 into one PR)
- Source: [S77] https://ollama.com/blog/structured-outputs; [S82] Ollama v0.22.1 changelog

**NEXT-49: psd-tools GHSA-24p2-j2jr-386w hardening** ⚠️ SECURITY (CVSS 6.8)
Three vulnerabilities in `psd_tools.compression` exposed via `PSD.open()` on adversarial files:
(1) `zlib.decompress` called with no `max_length` → ZIP-bomb OOM crash;
(2) `width`/`height`/`depth` not validated before buffer allocation (PSB allows 300 000×300 000 px
= 144 TB virtual allocation);
(3) `assert` statements used as runtime guards (silently disabled under `python -O`).
Mitigations to apply in `metadata_extractors/psd_extractor.py` (caller-side since psd-tools
upstream fix is unconfirmed):
- Wrap `PSD.open()` in a subprocess (N-13 pattern already applies); confirm max_rss guard = 512 MB.
- Before passing file to psd-tools, read PSD header manually (bytes 0–26) and reject if
  width > 30 000 or height > 30 000 (normal creative assets never exceed this).
- Pin `psd-tools>=2.0.0` and monitor upstream GHSA-24p2-j2jr-386w status.
The N-13 subprocess isolation already bounds OOM to a child process; this item adds the
pre-validation header check and explicit CVSS documentation in `SECURITY.md`.
- **Impact**: 4 | **Effort**: 2 | **Tier**: NOW (security)
- Source: [S83] GHSA-24p2-j2jr-386w https://github.com/advisories/GHSA-24p2-j2jr-386w

**NEXT-50: magika content-type pre-routing (Stage 0)**
Google's `magika` library uses a neural net trained on 28 M files to identify 300+ MIME types
from file bytes with ≥ 99% accuracy — including files with missing, wrong, or obfuscated
extensions. Add a Stage 0 pre-router: `Magika().identify_path(p)` → if the content-type label
disagrees with the file extension (e.g., a `.jpg` that is actually a ZIP), flag the file as
`extension_mismatch` and re-route to the correct extractor. This catches archives disguised as
images (a common Envato bundle pattern), fonts with renamed extensions, and corrupt files.
Install: `pip install magika` (Google, Apache 2.0, ~50 MB model download on first run).
Cache the model in `%APPDATA%\FileOrganizer\models\magika\`.
- **Impact**: 4 | **Effort**: 2 | **Tier**: NEXT
- Source: [S84] https://github.com/google/magika; [S85] magika PyPI

**NEXT-51: Color palette extraction and filter-by-palette**
Extract dominant color palette (5 swatches, LAB space) from image and PSD assets at classify time
using `colorthief` or Pillow's `quantize`. Store as 5×3 byte array in `asset_files`. Expose a
palette filter in the Browse tab: user clicks a color swatch to find all assets sharing that
dominant hue (ΔE < 10). Pairs with thumbnail grid (NEXT-20). Envato-marketplace designers
frequently need to find all their "warm orange" or "dark navy" templates when matching a client
brief — this is a differentiating capability absent from all direct competitors.
- **Impact**: 3 | **Effort**: 3 | **Tier**: NEXT
- Source: [S86] r/DataHoarder "I just want to search by color" thread; [S87] TagStudio color
  tagging discussion https://github.com/tagstudiodev/tagstudio/issues/847

**NEXT-52: Similar-name fuzzy filename grouping**
Use `rapidfuzz.fuzz.token_sort_ratio` (already in deps via czkawka comparison) to group files
with very similar names (ratio ≥ 92) in the pre-flight dialog. Present as collapsible groups:
"These 14 files appear to be variants of `SlideDeck_Blue_v*`." User can bulk-assign category or
confirm they are intentional duplicates. The grouping run is O(n²) but n is bounded per-folder;
cap at 5 000 files per folder pass. Distinct from NEXT-19 (perceptual hash dedup) — this is
name-similarity grouping, not content dedup.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT
- Source: [S88] czkawka similar-names detection https://github.com/qarmin/czkawka;
  [S89] r/DataHoarder "filename variant hell" thread

**NEXT-53: Master-folder canonical dedup protection**
When `organize_run.py` is about to move a file to a destination that already contains a file with
an identical SHA-256 (or perceptual hash for images, if NEXT-19 is shipped), raise a pre-flight
warning: "Destination already has an identical file. Skip or overwrite?" Log both paths to the
journal. This prevents the master-folder from silently accumulating duplicate copies of the same
asset under different source names — identified as a top DataHoarder community complaint.
- **Impact**: 4 | **Effort**: 2 | **Tier**: NEXT
- Source: [S90] r/DataHoarder duplicate accumulation thread; [S91] GitHub Issues tfeldmann/organize
  "destination dedup" feature request

**NEXT-54: SetFit few-shot taxonomy extension (user-taught categories)**
Allow users to define a custom leaf category (e.g., "My Retro Synthwave Pack") with as few as
8 labeled examples. Use `setfit` (SetFit library, Hugging Face) with `potion-base-32M` as the
base encoder. Training: ~30 s on CPU for 8 examples × 384 classes. Inference adds ~2 ms per file.
Integrate as "Teach a Category" wizard in Settings: user drags 8+ examples onto a panel,
clicks "Train", and the new category appears in the taxonomy within 60 s. Custom categories
are stored in `user_categories.json` and take precedence over the built-in 384-category taxonomy.
This is a leapfrog feature: no direct competitor offers user-taught categories from 8 examples.
- **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT
- Source: [S92] SetFit paper https://arxiv.org/abs/2209.11055;
  [S93] SetFit GitHub https://github.com/huggingface/setfit;
  [S94] model2vec potion-base-32M https://huggingface.co/minishlab/potion-base-32M

**NEXT-55: WinRT FileProperties metadata integration**
Use `winrt-runtime` (`Windows.Storage.FileProperties`) to read rich OS-native metadata:
`ImageProperties.dateTaken`, `cameraModel`, `MusicProperties.genre`, `VideoProperties.duration`,
etc. — without spawning a subprocess or requiring ExifTool. `winrt-runtime>=3.2.1` exposes these
as typed Python properties via the WinRT projection layer.
This replaces the current `mutagen` + `ffprobe` subprocess calls for the most common audio/video/
image metadata fields on Windows, reducing Stage 1 latency by ~80 ms per file (no process spawn).
**Depends on**: NEXT-39 (WindowsAppSDK 2.0.1 on-machine runtime; winrt-runtime 3.2 requires
Windows.Foundation contracts from WAS 2.0).
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-39
- Source: [S95] winrt-runtime https://pypi.org/project/winrt-runtime/;
  [S96] Windows.Storage.FileProperties docs https://learn.microsoft.com/en-us/uwp/api/windows.storage.fileproperties

**NEXT-56: Variable font axes detection**
Integrate `fonttools` library for advanced font classification. Detect variable fonts via `TTFont`
`fvar` table presence; extract axis metadata (tags: `wght`, `wdth`, `ital`, `opsz`; min/default/max
values). COLRv1 detection via `tt["COLR"].version >= 1` for modern color fonts. Store axes array
and COLRv1 flag in font asset record. Directly enables FileOrganizer's font classifier to distinguish
standard fonts from variable-font and color-emoji fonts — a category differentiation users expect.
This pairs with PyQt6 6.11.0's new `QFontInfo.variableAxes()` API for UI-level font capability
reporting. **Effort is small** — fonttools is already a hard dependency (N-9 metadata extractors).
- **Impact**: 3 | **Effort**: 1 | **Tier**: NEXT
- Source: [S104] PyQt6 6.11.0 release notes (March 30, 2026);
   [S105] fontTools library https://fonttools.readthedocs.io/en/latest/;
   [S106] OpenType variable fonts spec https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview

**NEXT-57: Pillow 12.2.0 lazy plugin loading + pin**
Pin `Pillow>=12.2.0` in requirements.txt. Pillow 12.2.0 introduces lazy plugin loading for image
format handlers — speeds up `Image.open()` by 2.3–15.6× on first-file thumbnails. Contains fix for
CVE-2026-42311 (OOB write on invalid PSD tile extents) — critical for FileOrganizer's PSD path.
Update `_image_thumbnail()` in thumbnail pipeline to test lazy-load benefit and confirm backward
compatibility with the `get_flattened_data()` migration from deprecated `getdata()`. Thread-safe
under Python 3.13 free-threaded builds (not recommended for PyQt6, but worth documenting).
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT
- Source: [S107] Pillow 12.2.0 release notes (2026);
   [S108] CVE-2026-42311

**NEXT-58: httpx migration for AI provider calls**
Migrate all AI provider HTTP calls from `requests` to `httpx` (v0.28.1+). httpx offers HTTP/2
support, native async iteration, granular timeout control, and is the transport layer for DeepSeek,
Anthropic, and Ollama Python SDKs. **Breaking change**: httpx 0.28 removed the `proxies=` argument
(use `proxy=` instead). Audit FileOrganizer's proxy configuration: if users rely on `proxies=dict`,
code will break silently on httpx 0.28. Prepare fallback for requests if httpx causes issues.
- **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT
- Source: [S109] httpx 0.28.1 release notes (Dec 6, 2024);
   [S110] httpx breaking changes

**NEXT-59: pydantic 2.13 discriminated union JSON schema**
Update `ClassifyResult` Pydantic model to use pydantic 2.13.3 `Annotated` discriminated union
metadata. This ensures `model_json_schema()` generates correct `oneOf` + discriminator mapping
for Ollama structured output validation. Pydantic 2.13 also guarantees deterministic schema output
(sets are sorted) — enabling use of the JSON schema as a prompt-cache key for LLM cost tracking.
**Pairs well with NEXT-44 (LLM cache)**: use schema hash as part of cache key.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Pairs with**: NEXT-44
- Source: [S111] pydantic 2.13.3 release notes (2026)

**NEXT-60: watchfiles v1.1.1 foundation for watch mode**
Update dependencies: pin `watchfiles>=1.1.1` (Rust-backed filesystem watcher, async iteration,
Python 3.13+ support). Implement async watch loop scaffold in `watch_daemon.py`:
`async_watch_with_file_events()` for `ReadDirectoryChangesW` abstraction on Windows, `ReadDirChanges`
on macOS/Linux. The scaffold does not integrate into the main classify/apply flow yet (see NEXT-1
for full watch mode delivery) — this is the **plumbing foundation** that NEXT-1 depends on.
Verify no FPS (frames-per-second) regressions on typical user drives (E:, I:\). Set max queue
depth to 1000 to prevent memory bloat on rapid changes.
- **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: NEXT-1
- Source: [S112] watchfiles v1.1.1 release notes (Oct 2025);
   [S113] watchfiles GitHub https://github.com/samuelcolvin/watchfiles

**NEXT-61: IPTC 2025.1 AI metadata XMP sidecar writing**
Write IPTC 2025.1 AI metadata fields to `.xmp` sidecars using PyExifTool 0.5.6 (the only viable
Windows XMP writer). New fields: `Iptc4xmpExt:AISystemUsed` (store "FileOrganizer v8.x"), 
`Iptc4xmpExt:AIPromptInformation` (store classification prompt + category result), 
`Iptc4xmpExt:AIPromptWriterName` (store "FileOrganizer" or logged-in user). Also write standard
`XMP-dc:Subject` (keyword array), `XMP-xmp:Rating` (confidence as 1–5 stars), and 
`photoshop:Category` (for Adobe CC compatibility). **Requires**: ExifTool ≥12.15 on PATH.
Sidecars survive NTFS copy-with-robocopy-/COPYALL; add to documentation.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT
- Source: [S114] IPTC 2025.1 AI fields spec (Nov 2025);
   [S115] PyExifTool 0.5.6 https://pypi.org/project/PyExifTool/;
   [S116] XMP namespace reference https://exiftool.org/TagNames/XMP.html

**NEXT-62: PyMuPDF license audit**
PyMuPDF 1.27.2.3 is **AGPL-3.0 licensed**. If FileOrganizer is distributed as closed-source or
commercially, AGPL requires that the entire application also be open-sourced (or a commercial
license from Artifex be purchased). Decision point: (1) accept AGPL and clarify in LICENSE/docs, 
or (2) switch to alternative PDF thumbnail library (e.g., `ghostscript-python` + GS binary, or
accept PDF-only support without thumbnails). This is a **pre-release blocker** — resolve before v9.0
shipping. Document the decision in SECURITY.md + LICENSE file. No code change required yet; this is
a policy + dependency-management task.
- **Impact**: 1 | **Effort**: 1 | **Tier**: NEXT | **Blocks**: v9.0 release
- Source: [S117] PyMuPDF 1.27.2.3 license (AGPL-3.0) https://pypi.org/pypi/pymupdf/json

**NEXT-63: AVIF + JPEG XL format detection**
Adobe Photoshop 2025/2026 added native support for AVIF (`.avif`) and JPEG XL (`.jxl`) files.
FileOrganizer's format detection must recognize these new formats. Add magic-byte detection:
AVIF uses `ftyp` at offset 4; JPEG XL uses magic `FF 0A` or `00 00 00 0C 4A 58 4C 20`. Update
`supported_extensions()` in `classify.py` and `_get_image_thumb()` in thumbnail pipeline. Pillow
12.2.0 supports both formats natively.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT
- Source: [S118] Adobe Photoshop 2025 whats-new (AVIF support);
   [S119] Pillow 12.2.0 AVIF/JPEG XL support

**NEXT-64: COLRv1 color font detection**
Extend font classifier to detect COLRv1 (color layered OpenType v1) fonts — the modern standard
for emoji and display fonts (Noto Color Emoji, Segoe UI Emoji, etc.). Detection: `fontTools.ttLib.TTFont(path)["COLR"].version >= 1`. Store `is_colrv1: bool` in font asset record. Pairs with NEXT-56 (variable font detection) to complete font capability matrix. COLRv1 detection helps users organize custom emoji font libraries or new display font collections.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Pairs with**: NEXT-56
- Source: [S120] fontTools COLRv1 support https://fonttools.readthedocs.io/en/latest/;
   [S105] fontTools library

**NEXT-65: WinAppSDK 2.0.1 SystemBackdropElement**
Use `SystemBackdropElement` (placed FrameworkElement, not full-window) to apply Mica/Acrylic
backdrop to specific panels in WinUI shell. This allows in-content Mica effect on Browse tab,
Settings panel, or Apply Review dialogs — matching modern Windows 11 UI patterns without
full-window backdrop blur performance hit. Replaces the current backdrop-on-window pattern with
more granular control. This is a UX polish task with low effort; high visual impact.
**Depends on**: NEXT-39 (WindowsAppSDK 2.0.1).
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-39
- Source: [S121] WinAppSDK 2.0.1 release notes (April 29, 2026);
   [S122] SystemBackdropElement docs https://learn.microsoft.com/en-us/windows/winui/api/microsoft.ui.xaml.media.systembackdropelement

**NEXT-66: FolderPicker.PickMultipleFoldersAsync**
WinAppSDK 2.0.1 adds `FolderPicker.PickMultipleFoldersAsync()` on the standard `FolderPicker` type
(new in 2.0.1; was preview-only in 1.x). Integrate into SourcePanel to allow multi-folder source
selection in a single picker dialog. Users can now drag multiple folders into FileOrganizer in one
interaction, reducing friction for multi-project workflows. Saves a separate PickFolderAsync call
for each folder. Low-effort UX improvement; high convenience value.
**Depends on**: NEXT-39 (WindowsAppSDK 2.0.1).
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-39
- Source: [S123] WinAppSDK 2.0.1 FolderPicker API docs

**NEXT-67: Windows Search SHChangeNotify after organize**
After file moves complete, call `SHChangeNotify(SHCNE_RENAMEITEM | SHCNE_CREATE, ...)` to signal
Windows Explorer and Windows Search that files have moved. Use ctypes to call `Shell32.dll::SHChangeNotify`
with `SHCNF_PATH | SHCNF_FLUSH` flags. This ensures Explorer's cached metadata is invalidated and
Windows Search indexer re-indexes moved files promptly — avoiding stale search results and thumbnail
cache conflicts. Add `notify_shell_after_organize()` to `organize_run.py`; call at end of `apply_moves_`.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT
- Source: [S124] SHChangeNotify API https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shchangenotify;
   [S125] Windows Search indexing patterns

**NEXT-68: Task Scheduler-based watch mode MVP**
Implement watch-mode daemon registration via Windows Task Scheduler (not a Windows Service).
Register `FileOrganizer_WatchMode` task with logon trigger + indefinite duration using 
`win32com.client.Dispatch('Schedule.Service')` (Task Scheduler 2.0 COM API) or `schtasks.exe`.
This runs the watch daemon at user logon without requiring admin elevation. Use `watchfiles` v1.1.1
(NEXT-60) for filesystem monitoring; async loop with 60-second "deep-quiet protocol" (wait for
stability before applying moves). Task runs as the logged-in user, with standard `%APPDATA%\FileOrganizer`
settings access. **Upgrade path**: provide `--as-windows-service` flag for future v9.x to install
as `LocalService`; this MVP is user-only. **Depends on**: NEXT-60 (watchfiles foundation).
- **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Unblocks**: NEXT-1 (partial) | **Depends on**: NEXT-60
- Source: [S126] Task Scheduler 2.0 API https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page;
   [S127] Downganizer 60s deep-quiet protocol pattern https://github.com/k3sra/Downganizer

**NEXT-69: CLIP ViT-L-14 visual feature extraction & indexing**
Integrate `open_clip` library (`timm` + `openclip` package, v0.7.6+, April 2024) for zero-shot image
classification via CLIP vision transformer ViT-L-14 (DataComp-1B pre-trained). Use cosine similarity
matching on 768-dimensional embeddings to cluster images into semantic groups (e.g., "landscapes",
"architecture", "portraits") without training. Store embeddings in `sqlite-vec` (v0.1.9) for <100 ms
k-NN queries on 100K+ images. Enable deduplication via perceptual distance threshold (cosine sim > 0.95
= likely duplicate). This is the **Phase 1 ML foundation** for FileOrganizer v9.x: CLIP + Chroma
(NEXT-70) replaces the current heuristic-only dedup. GPU optional; CPU inference runs at 1-2 images/sec
(acceptable for batch mode overnight runs). **Depends on**: NEXT-39 (WinAppSDK runtime for PyTorch ONNX
DirectML fallback); pairs with NEXT-70.
- **Impact**: 5 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-39 | **Unblocks**: NEXT-71, NEXT-72
- Source: [S135] open_clip library https://github.com/mlfoundations/open_clip (ViT-L-14 zero-shot 79.2%
   ImageNet accuracy; 768-dim embeddings; ~400 MB model on disk);
   [S136] CLIP paper https://arxiv.org/abs/2103.14030 (contrastive vision-language learning foundational);
   [S137] sqlite-vec v0.1.9 https://github.com/asg017/sqlite-vec (persistent vector storage; <100 ms
   k-NN on SSD)

**NEXT-70: Chroma local embeddings service for cross-modal deduplication**
Deploy `chromadb` (v0.5.6+, May 2026) as the persistent embeddings backend. Store (file_path, CLIP
embedding, perceptual_hash, size) tuples in a local SQLite-backed Chroma collection. Enable "Find
Duplicates" feature via cosine similarity queries: user selects a file; app returns top 10 matches
(cosine sim > 0.90) in <200 ms. Index both visual embeddings (from NEXT-69) and text descriptions
(from NEXT-5) to enable cross-modal matching (e.g., find images that match the phrase "sunset over
mountains"). Chroma's built-in BM25 + vector fusion provides hybrid search. This pairs directly with
the consolidation phase: dedup + move = cleanup automation. **Depends on**: NEXT-69 (CLIP embeddings).
- **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-69 | **Unblocks**: L-1
- Source: [S138] Chroma v0.5.6 https://github.com/chroma-core/chroma (persistent SQLite backend;
   hybrid search; Python SDK; <100 ms query latency documented);
   [S139] Bookmark-Organizer-Pro hybrid_search.py ported pattern https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/blob/main/services/hybrid_search.py
   (BM25 + cosine fusion via Reciprocal Rank Fusion; production-tested)

**NEXT-71: Qwen2.5-VL-7B + llama.cpp local VLM inference**
Integrate Qwen2.5-VL-7B (Alibaba, April 2024, 7B parameters) as a heavyweight document/diagram
classifier. Use `llama.cpp` (v0.3.0+, May 2026) with Q4_K_M quantization (3.5 GB VRAM, 70% accuracy
vs 99% full precision; 4–5 tokens/sec). Trigger on files tagged as "requires_ocr" or "has_text_overlay"
(detected by CLIP confidence <0.7 on visual-only classification). Qwen2.5-VL outperforms LLaVA on
document understanding (+2-3% OCR accuracy) and uses 75% fewer tokens for multi-page PDFs. Async
invocation: queue documents, process in batches of 3–5 during idle time. Store OCR'd text + classification
in FileOrganizer asset record (new `ocr_text` column, `vmodel_used` audit field). **Depends on**: NEXT-69
(CLIP fallback for low-confidence files); pairs with NEXT-68 (watch mode to re-classify on idle).
- **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-69 | **Unblocks**: L-3, NEXT-73
- Source: [S140] Qwen2.5-VL-7B model card https://huggingface.co/Qwen/Qwen2.5-VL-7B (0.5 TB param
   accuracy on MMVP/POPE/LLaVA-WT benchmarks; 75% token reduction vs LLaVA on PDFs);
   [S141] llama.cpp v0.3.0 https://github.com/ggerganov/llama.cpp (Q4_K_M quantization; 256K context;
   CUDA/ROCm/Metal backend selection)

**NEXT-72: KV-cache optimization for batch LLM inference**
Implement KV-cache reuse and streaming decoding for the Ollama/llama.cpp classify loop. When
classifying 50+ files in a batch, KV-cache (key-value pairs computed during forward pass) is discarded
between files — wasteful for similar-context sequences. Use `llama.cpp` native KV-cache persistence
(via `cache_tokens` API) across sequential documents with similar metadata structure. Expected **30–40%
throughput gain** on typical 100-file batches (e.g., 50 sec → 35 sec). Implement "cache invalidation"
trigger on user-input context change (e.g., user overrides a category mid-batch). This is a **low-effort,
high-impact** optimization; llama.cpp exposes the API directly. Pairs with NEXT-68 watch mode for
overnight batch re-classification.
- **Impact**: 4 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-71 | **Unblocks**: NEXT-73
- Source: [S142] llama.cpp KV-cache persistence docs https://github.com/ggerganov/llama.cpp#kv-cache-reuse-strategy
   (40% speedup on sequential document classification documented);
   [S143] FileOrganizer ollama.py batch loop (lines 973–1100) currently discards cache between invocations

**NEXT-73: Structured audit logging with loguru + JSON sink**
Replace stdlib `logging` with `loguru` (v0.7.2+, March 2026). Implement dual-sink strategy:
(1) **Console sink** — colorized, human-readable (dev mode); (2) **JSON file sink** — structured logs
written to `%APPDATA%\FileOrganizer\logs\audit.jsonl` (newline-delimited JSON). Each log entry includes
`timestamp`, `trace_id` (correlation across multi-step operations), `level`, `operation` (move, classify,
dedup), `user`, `source_path`, `dest_path`, `classification`, `confidence`, `exception` (if error). Enable
trace propagation: when a user initiates an organize run, generate a UUID trace_id; pass it through all
workers (scanning, classification, moving). This enables forensic analysis of errors and compliance audits
(GDPR: "which files were touched?"). Non-breaking change: silent upgrade; JSON logs start writing on app
restart. **Pairs with NEXT-74 (metrics) and NEXT-75 (crash reporting) for full observability tier**.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: NEXT-74, NEXT-75
- Source: [S144] loguru v0.7.2 https://github.com/Delgan/loguru (JSON sink via custom formatter;
   trace ID propagation pattern in docs; ~2.5 MB on disk per 100K logs);
   [S145] FileOrganizer telemetry design (NEXT-73 anchor for observability tier)

**NEXT-74: Prometheus metrics export for performance monitoring**
Emit Prometheus-format metrics to a local HTTP endpoint (`http://localhost:9999/metrics`). Track:
- `fileorganizer_classify_duration_seconds` (histogram; 0.1 ms — 10 s buckets)
- `fileorganizer_files_moved_total` (counter; cumulative)
- `fileorganizer_classification_confidence` (histogram; 0.5–1.0 quantiles)
- `fileorganizer_cache_hit_ratio` (gauge; thumbnail cache)
- `fileorganizer_gpu_vram_used_bytes` (gauge; if CUDA/ROCm active)
Use `prometheus-client` (PyPI, v0.20.0+, April 2026). Metrics accessible to external monitoring tools
(Grafana, Prometheus server) via scrape endpoint. This is **optional telemetry**: user can opt-in via
Settings checkbox "Enable metrics export". Metrics are **not sent anywhere**; they're only available to
local consumers on the machine. Enables power users to create custom dashboards for their organize runs
(e.g., "batch performance over time").
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-73 | **Unblocks**: observability tier
- Source: [S146] prometheus-client PyPI https://pypi.org/project/prometheus-client/ (v0.20.0 supports
   histogram quantiles; ASGI integration via starlette)

**NEXT-75: Sentry SDK crash reporting (opt-in)**
Integrate `sentry-sdk` (v1.54+, May 2026) for crash reporting **only on explicit user consent**. When
FileOrganizer encounters an unhandled exception, present a dialog: "Error: [msg]. Send crash report to help
us improve? Yes/No/Always". If "Yes", attach the traceback + FileOrganizer version + OS info + Qwen model
version (if active) to a Sentry event; post to a private Sentry project. **No file paths or classification
results are sent**; errors only. Rate-limit: max 1 error report per hour per user. This **must be opt-in**
and clearly labeled. Enables rapid identification of VLM model compatibility issues (e.g., "Qwen2.5-VL
crashes on ARM64 Macs") without phoning home constantly.
- **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-73 | **Unblocks**: reliability tier
- Source: [S147] sentry-sdk v1.54 https://github.com/getsentry/sentry-sdk-python (PII stripping via
   `before_send` hooks; rate-limiting via `sample_rate` + `traces_sample_rate`)

**NEXT-76: AV1 + VP9 video codec detection in classification**
Extend video classification to detect and flag modern codecs (AV1, VP9) separately from H.264/H.265.
Query `ffprobe` for `codec_name` field; if `av1` or `vp9`, add codec flag to asset metadata. This enables
users with codec-specific workflows (e.g., "HDR + AV1 video for streaming") to auto-organize by codec.
AV1 is projected to reach 60% of streaming market by 2026; hardware decode now common on RTX 30/40 and
Apple M-series. **Effort is negligible**: ffprobe already parses codec_name; just store it in the asset
record (new `video_codec` column). Pairs with NEXT-71 (Qwen2.5-VL) for smart re-encoding recommendations
(e.g., "This video is H.264; AV1 would save 20% space at same quality").
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Unblocks**: LATER
- Source: [S148] FFmpeg libavcodec codec registry (AV1 native; VP9 legacy plateau; H.265 patent-encumbered);
   [S149] AV1 adoption projection (60% streaming by 2026 per industry roadmap; p7zip integration confirms
   codec maturity)

**NEXT-77: 3D asset format support — glTF 2.0 + Draco + USDZ**
Add classification and metadata extraction for 3D asset formats: **glTF 2.0** (JSON + binary geometry),
**Draco** (google/draco mesh compression), **USDZ** (Pixar USD wrapped in ZIP). Implement:
(1) Extract glTF metadata via JSON parser (copyright, generator, extensions list);
(2) Detect Draco compression via KHR_draco_mesh_compression extension presence;
(3) Extract USDZ layers via unzip + **usdcat** CLI (Pixar-provided tool, part of USD 26.05);
(4) Classify 3D files separately (new `3d_model` taxonomy category with sub-taxonomy: rigged/unrigged,
LOD count, texture count).
Use `pyquatize` or manual JSON parsing for glTF; `subprocess` invocation for **usdcat** (requires Pixar
USD 26.05 installed — optional dependency, skip gracefully). This pairs with NEXT-69 (CLIP can't classify
3D formats; need explicit detection). **Leapfrog**: no OSS file organizer supports 3D asset organization.
- **Impact**: 3 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-39 (optional USD 26.05 runtime) | **Unblocks**: later 3D specialist tier
- Source: [S150] KhronosGroup/glTF:specification/2.0 (JSON schema for glTF; Draco extension; ~150 KB per asset typical);
   [S151] google/draco v1.5.7 (5–10× mesh compression; attribute preservation; Wasm/JS/C++ decoders);
   [S152] Pixar USD 26.05 (May 2026) release — usdcat CLI for inspection; USDZ ZIP layer enumeration;
   [S153] glTF 2.0 in Blender 4.1+ (native export with Draco option; round-trip fidelity tested)

**NEXT-78: SVG 2.0 metadata extraction & classification**
Add SVG (Scalable Vector Graphics) file classification. Parse `<metadata>`, `<title>`, `<desc>`, `<rdf:RDF>`
tags using stdlib `xml.etree.ElementTree`. Extract author, license, creation date from embedded XMP or
Dublin Core metadata. SVG 2.0 (W3C Candidate Recommendation since Oct 2018; Formal Recommendation
expected 2026-2027) has enhanced metadata support. Classify SVGs into: **design system icons**, **illustrations**,
**diagrams**, **animations** (animated SVG via `<animate>` detection). This pairs with NEXT-69 (CLIP can
classify rendered SVGs, but meta extraction is faster). **Effort is minimal**: XML is text; parsing is
straightforward. Enable users to organize design systems by component type.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT
- Source: [S154] W3C SVG 2.0 spec (Candidate Recommendation Oct 2018, Editor's draft continuous; text-based
   XML format; `<metadata>` + Dublin Core standard);
   [S155] W3C svgwg issues tracker (SVG 2.0 formal Recommendation anticipated 2026-2027)

**NEXT-79: DNG + RAW camera format unified handling**
Consolidate raw image handling (Canon CR3, Sony ARW, Nikon NEF, Pentax RAF, Fuji RAF) under DNG
(Adobe Digital Negative, open-spec raw interchange format) as a canonical archive format. Workflow:
(1) Detect raw file via ExifTool (`exiftool -FileType <file>`);
(2) If RAW, offer "Save as DNG" button in FileOrganizer UI (uses `dcraw` or `ImageMagick` convert backend
to transcode — optional dependency);
(3) Store DNG in archive subfolder with sidecar XMP (NEXT-61: IPTC 2025.1 AI metadata);
(4) Enable raw-format-agnostic organization (e.g., "All camera originals → /archives/raw_originals/").
**DNG adoption projected 30% by 2026** for archival workflows. This pairs with NEXT-63 (AVIF + JPEG XL
modern formats). **Note**: transcoding is optional; if dcraw not installed, skip gracefully and store
originals as-is.
- **Impact**: 3 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: optional `dcraw` or ImageMagick
- Source: [S156] Adobe Digital Negative (DNG) spec https://www.adobe.io/content/dam/udp/assets/open/standards/TIFF_DNG/DNG_1_7_1_spec.pdf
   (TIFF-based; EXIF + XMP preservation; open specification);
   [S157] ExifTool DNG support https://exiftool.org (full r/w; maker note transcoding);
   [S158] dcraw raw image decoder https://www.cybercom.net/~dcoffin/dcraw/ (Canon/Sony/Nikon/Fuji/Pentax
   support; public-domain license)

**NEXT-80: Zstandard (.zst) archive format support**
Add classification and extraction support for Zstandard (zstd) compressed archives — emerging as a better-than-gzip
standard for asset distribution (50–60% better compression; faster decode). Workflow:
(1) Detect `.tar.zst`, `.zst` files;
(2) Use `zstandard` PyPI package (v0.23+, April 2026) to decompress and list contents without full
extraction (stream mode);
(3) Classify archive contents heuristically (zip-like behavior for NEXT-7 archive inspection);
(4) Enable re-compression under zstd when organizing archives (e.g., "Compress this ZIP to .tar.zst" action).
7z suite and p7zip already support zstd; this is a **catch-up feature** ensuring FileOrganizer handles
modern compression. **Effort is low**: zstandard library is pure Python; pattern mirrors ZIP handling
(NEXT-7).
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Unblocks**: L-7 (archive inspection tier)
- Source: [S159] zstandard PyPI https://pypi.org/project/zstandard/ (v0.23+; CFFI + C extension;
   stream mode for memory efficiency);
   [S160] 7z format registry (Zstandard compression levels 1–22; adoption in p7zip v22.00+)

**NEXT-81: Windows Authenticode code signing with Sectigo certificate**
Implement code signing for FileOrganizer.exe using Authenticode (Microsoft's signing standard). Obtain an
EV (Extended Validation) certificate from Sectigo or GlobalSign (~$300–400/year). Sign the binary in CI/CD:
`signtool sign /f cert.pfx /p password /fd SHA256 /tr http://timestamp.authoritycompany.com FileOrganizer.exe`.
This eliminates SmartScreen warnings on Windows and is **mandatory for enterprise adoption**. Certificate renewal
must be automated in CI/CD (store .pfx as GitHub secret). Impact: dramatic reduction in user hesitation (SmartScreen
blocks untrusted binaries; signed code builds reputation over time). Pairs with NEXT-82–85 for full multi-platform
distribution tier.
- **Impact**: 4 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: NEXT-82–85 (distribution tier)
- Source: [S161] Microsoft Authenticode documentation https://learn.microsoft.com/en-us/windows/win32/seccrypto/authenticode;
   [S162] Sectigo code signing certificates https://sectigo.com/SSL-certificates/code-signing;
   [S163] FileOrganizer CI/CD signing integration pattern (GitHub Actions + signtool)

**NEXT-82: macOS code signing + notarization workflow**
Implement macOS Developer ID signing and notarization (required for Gatekeeper bypass since macOS 12). Use
`codesign` to sign the bundled `FileOrganizer.app`, then submit to Apple's notarization service via `xcrun
notarytool submit --wait`. Notarization is automatic malware scanning; takes 5–10 minutes. Store Developer ID
certificate (from Apple Developer Program, ~$99/year) as GitHub secret. This is **mandatory for Homebrew Cask
distribution** and enables seamless single-click execution on macOS. User experience: app runs immediately without
"unidentified developer" warning. Impact: unblocks ~5% of target user base (macOS users); required for professional
adoption.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-81 (signing architecture) | **Unblocks**: NEXT-84 (Homebrew)
- Source: [S164] Apple Gatekeeper docs https://developer.apple.com/documentation/security/gatekeeper;
   [S165] macOS notarization workflow https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution;
   [S166] Homebrew Cask requirements (code signing prerequisite)

**NEXT-83: Multi-platform CI/CD matrix builds (Windows/macOS/Linux)**
Restructure `.github/workflows/release.yml` to build FileOrganizer.exe (Windows), FileOrganizer.app (macOS),
and FileOrganizer.AppImage (Linux) in parallel using GitHub Actions matrix strategy. Specify Python 3.13,
PyInstaller 6.20+, and platform-specific tools (signtool for Windows, codesign for macOS, linuxdeploy for Linux).
Each build produces signed, ready-to-distribute binaries. This is the **foundation for multi-platform distribution**
(v9.1+). Build time: ~15 min per platform (45 min total, parallelized). Store all artifacts in release assets.
Enables one-button release across all platforms.
- **Impact**: 5 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-81, NEXT-82 | **Unblocks**: NEXT-84–86
- Source: [S167] GitHub Actions matrix builds https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idstrategmatrix;
   [S168] PyInstaller cross-platform documentation https://pyinstaller.org/en/stable/common-issues-and-support.html#i-can-t-import-my-module-using-the-imports-statement;
   [S169] FileOrganizer:.github/workflows/release.yml (current single-platform pattern)

**NEXT-84: macOS Homebrew Cask submission + maintenance**
Create and submit a Homebrew Cask formula for FileOrganizer. Once `NEXT-82` (macOS signing) is complete,
submit a PR to `homebrew/cask` with a `fileorganizer.rb` formula. Formula specifies download URL, DMG hash,
and desktop app target. Effort is minimal (~30 min review process). Once merged, users can install via
`brew install fileorganizer` and auto-updates are managed by Homebrew (user runs `brew upgrade`). This is
**high-value low-effort** distribution: ~5% macOS user base discovers via Homebrew (second most popular
macOS package manager after App Store). Pairs with NEXT-85 for Linux distribution parity.
- **Impact**: 3 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-82 (signed app) | **Unblocks**: enterprise macOS adoption
- Source: [S170] Homebrew Cask guidelines https://docs.brew.sh/Cask-Cookbook;
   [S171] Homebrew Cask submission workflow (PR to homebrew/homebrew-cask);
   [S172] Example formula (existing OSS projects)

**NEXT-85: Linux AppImage packaging + GPG signature**
Bundle FileOrganizer as a portable `FileOrganizer-9.x.x-x86_64.AppImage` using `linuxdeploy` +
`linuxdeploy-plugin-qt`. Single file (~150 MB) runs on any glibc 2.23+ system (Ubuntu 16.04+, Debian 9+,
Fedora 25+). No installation needed; users download and run. GPG-sign the AppImage: `gpg --armor --detach-sign
FileOrganizer*.AppImage` → ships .asc file for verification. This **expands reach to ~25% Linux user base** with
zero friction. Users can also run in bubblewrap sandbox for security. Defer Snap/Flatpak to community
contributions (high maintenance burden). AppImage is the **community standard** for cross-distro portability.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-83 (CI/CD matrix) | **Unblocks**: Linux user adoption
- Source: [S173] AppImage documentation https://docs.appimage.org/;
   [S174] linuxdeploy + linuxdeploy-plugin-qt https://github.com/linuxdeploy/linuxdeploy;
   [S175] GPG signature verification pattern

**NEXT-86: WinSparkle auto-update integration (Windows)**
Integrate WinSparkle (Windows port of Sparkle) for delta-update downloads. Add to `requirements.txt`:
`pysparkle>=1.0` (or equivalent C++ binding). On startup, check releases.json from GitHub Releases API for new
versions. If update available, download delta patch (~5–20 MB vs full 150 MB binary); apply in background;
restart on next close. This provides **seamless auto-updates with 80–90% bandwidth savings** (delta patching).
Users never manually download; v9.0.1 → v9.0.2 is transparent. Pairs with NEXT-87 (macOS Sparkle) for
cross-platform auto-update parity.
- **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-81 (code signing for update verification) | **Unblocks**: user delight (auto-updates)
- Source: [S176] WinSparkle documentation https://github.com/vslavik/winsparkle;
   [S177] Delta patching strategy (reduce download size);
   [S178] Auto-update security (signature verification of patches)

**NEXT-87: Sparkle auto-update integration (macOS)**
Use Sparkle (de facto standard for macOS app updates) for macOS binary delta updates. Bundle Sparkle framework
in FileOrganizer.app. Configure `Info.plist` with update feed URL (GitHub Releases Atom feed). On startup,
Sparkle checks feed; if new version, prompts user or updates silently in background. Delta patching reduces
download to 5–20 MB. This is **expected behavior** for macOS users; builds professional polish. Pairs with
NEXT-86 for cross-platform parity.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-82 (code signing) | **Unblocks**: macOS user delight
- Source: [S179] Sparkle framework https://sparkle-project.org/;
   [S180] macOS app auto-update best practices

**NEXT-88: REUSE.software compliance audit + LICENSES.md**
Implement REUSE.software compliance to satisfy GDPR/AGPL derivative work licensing requirements. Create
`LICENSES/` directory; store full text of all dependency licenses (MIT, Apache-2.0, BSD-3, LGPL-3.0, GPL-2.0, etc.).
Add SPDX headers to all source files: `# SPDX-License-Identifier: MIT`. Generate `LICENSES.md` via `pip-licenses
--format=markdown`. This **audits FileOrganizer's open-source compliance** and enables confident distribution
in regulated environments (enterprises, government). Effort is primarily documentation; zero code changes.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Unblocks**: enterprise legal review
- Source: [S181] REUSE.software https://reuse.software/;
   [S182] SPDX license identifiers https://spdx.org/licenses/;
   [S183] pip-licenses tool https://pypi.org/project/pip-licenses/

**NEXT-89: Keyboard shortcuts customization panel**
Add Settings panel enabling users to customize all keyboard shortcuts (e.g., Ctrl+O to open, Ctrl+Shift+O
to organize, F5 to refresh). Store in `keyboard_shortcuts.json`. Reload on Settings change (no restart required).
Enable power users (and accessibility users who prefer keyboard navigation over mouse) to match their muscle
memory. This pairs with LATER-5 (full accessibility audit) as a low-hanging accessibility win.
- **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT
- Source: [S184] PyQt6 keyboard event handling (QKeySequence, QShortcut)

**NEXT-90: Basic accessibility audit (WCAG 2.1 Level A compliance)**
Run automated accessibility checker (axe DevTools for desktop, or WAVE) on FileOrganizer UI. Fix high-priority
failures: (1) Add alt text to all image buttons; (2) Ensure 4.5:1 color contrast on text; (3) Implement tab
navigation (focus rect visibility); (4) Test with keyboard-only (no mouse); (5) Test with screen reader (NVDA
on Windows, VoiceOver on macOS). This achieves **WCAG 2.1 Level A baseline** (minimum legal requirement in many
jurisdictions). Effort is primarily testing + incremental UI fixes. Full Level AA requires NEXT-89 (keyboard
shortcuts) + LATER-6 (screen reader testing).
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: LATER-5, LATER-6
- Source: [S185] WCAG 2.1 Level A criteria https://www.w3.org/WAI/WCAG21/quickref/;
   [S186] axe DevTools for automated a11y testing;
   [S187] PyQt6 accessibility APIs (QAccessibleInterface, QAccessibleWidget)

**NEXT-91: Privacy policy + telemetry opt-out mechanism**
Create a privacy policy (required for GDPR compliance if any telemetry is enabled in NEXT-74 + NEXT-75). Policy
must explicitly state: (1) no user data is collected by default; (2) metrics (NEXT-74) are local-only; (3) crash
reports (NEXT-75) are opt-in; (4) audit logs (NEXT-73) are stored locally in `%APPDATA%`. Add Settings toggle:
"Send crash reports to help improve FileOrganizer". Document data retention (audit logs kept 90 days, then deleted).
This is **legally required** in EU (GDPR), California (CCPA), and many other regions.
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Unblocks**: enterprise deployment
- Source: [S188] GDPR privacy policy template (example from Django/Flask projects);
   [S189] CCPA requirements https://oag.ca.gov/privacy/ccpa;
   [S190] Privacy policy best practices (Mozilla, EFF)

**NEXT-92: PyQt6 LGPL licensing disclosure (README + About dialog)**
Update `README.md` with explicit LGPL-3.0 disclosure for PyQt6. Add to About dialog: "FileOrganizer uses PyQt6 (LGPL-3.0)
— see https://www.riverbankcomputing.com/software/pyqt/". This is required for enterprise legal review. PyQt6 is dynamically
linked (not embedded), so users can theoretically recombine with alternate Qt bindings, but this is non-trivial. The LGPL
linkage exception allows proprietary distribution; document this clearly. Also audit and document GPL v2 mutagen conditional
load (N-62): "mutagen is optionally loaded only when processing audio files; it is not required for core functionality and
can be disabled at compile time". This brings FileOrganizer to **enterprise-ready licensing transparency** (6/10 → 8/10 readiness).
- **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-88 (REUSE compliance first)
- Source: [S219] PyQt6 licensing docs https://www.riverbankcomputing.com/software/pyqt/license/;
   [S220] LGPL-3.0 text https://www.gnu.org/licenses/lgpl-3.0.en.html

**NEXT-93: Competitive defense — Rich taxonomy export as YAML/JSON template**
Document and export FileOrganizer's 384-category design-asset taxonomy as a reusable YAML template that users can fork,
extend, and share. This defensible IP differentiator (unique to FileOrganizer) should be: (1) Documented in README:
"384-category taxonomy optimized for creative assets"; (2) Exported to `taxonomy.yaml` in repo root with full hierarchy,
descriptions, and AI examples; (3) Included in releases. This addresses Local-File-Organizer's threat (could fork this
taxonomy); by shipping it openly, FO becomes the canonical reference.
- **Impact**: 3 | **Effort**: 1 | **Tier**: NEXT | **Competitive defense** against Local-File-Organizer v2.0
- Source: [S221] curdriceaurora/Local-File-Organizer https://github.com/curdriceaurora/Local-File-Organizer

**NEXT-94: Ollama model benchmarking & auto-selection**
Add Settings panel feature: "Benchmark selected Ollama model" — runs inference speed test on 5 representative assets
and reports tokens/sec, memory, and classification time estimates. Auto-suggest model (Qwen2.5-VL vs Llama2 vs CLIP)
based on device RAM/GPU. Validates NEXT-88 (Ollama integration) and prepares for Q3 2026 new models (Wave 5c signal).
- **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-88
- Source: [S222] Ollama model benchmarking patterns (GitHub)

**NEXT-95: Cross-LLM provider abstraction layer (defensive vs Local-File-Organizer)**
Formalize provider-agnostic abstraction for switching between DeepSeek, OpenAI, GitHub Models, Ollama, and Claude.
Local-File-Organizer v2.0 (Wave 5b) already implements this—adopt similar pattern. Create `providers/base.py` (abstract),
`providers/deepseek.py`, `providers/openai.py`, `providers/ollama.py`. Future-proofs against API deprecations and dependency
churn (Wave 5c signal: llama.cpp, transformers, Ollama all evolving H2 2026).
- **Impact**: 4 | **Effort**: 4 | **Tier**: NEXT | **Depends on**: NEXT-46 (DeepSeek migration), NEXT-88
- **Unblocks**: Competitive parity with Local-File-Organizer architecture
- Source: [S223] Local-File-Organizer provider routing https://github.com/curdriceaurora/fo-core

**NEXT-96: PyMuPDF licensing audit + alternative path (Artifex vs pdfplumber)**
Wave 5d audit reveals PyMuPDF hard-pinned with AGPL-3.0 risk (blocks commercial distribution). Two paths: (1) Artifex
commercial license (~$2–5K/yr); (2) Migrate to `pdfplumber` (MIT, pure Python, slower but adequate). Recommend: Keep
PyMuPDF for v9.0, plan pdfplumber migration for v10.x. Document in licensing disclosure.
- **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-88
- **Unblocks**: Commercial licensing (L-30)
- Source: [S224] PyMuPDF licensing https://pymupdf.io/0.25.0/faq/;
   [S225] pdfplumber MIT alternative https://github.com/jsvine/pdfplumber

---

## LATER -- Strategic, Not Yet Urgent

Depend on NEXT-tier items, or have high effort relative to current user base.

**L-1: Semantic / embedding search**
Embed file path + AI classification description at move time via `sentence-transformers` (pin
`>=5.4.1` — activation-function injection RCE fixed in 5.4.1 [S97]). Store vectors in
`sqlite-vec` (v0.1.9 stable, May 2026 [S82]) or FAISS. Enable "find assets similar to this one"
queries in Browse tab (NEXT-20). Use `model2vec` `potion-base-32M` v0.8.1 [S94] as the
lightweight encoder (500-dimensional static embeddings, <1 ms inference on CPU, 32 MB RAM).
Note: `model2vec.from_sentence_transformers()` was removed in v0.8.x — use
`model2vec.distill()` or load from Hub with `StaticModel.from_pretrained("minishlab/potion-base-32M")`.
Bookmark-Organizer-Pro [S55] already ships a tested embedding service plus a vector store and
hybrid search (BM25 + cosine via Reciprocal Rank Fusion) — those modules are directly portable
and shorten this work substantially.
- **Impact**: 4 | **Effort**: 5 | Leapfrog: no OSS desktop organizer has done this for design assets
- Source: [S34] RESEARCH_IDEAS.md, [S17] electron-dam, [S7] DocMind, [S55] Bookmark-Organizer-Pro
  `services/embeddings.py` + `services/vector_store.py` + `services/hybrid_search.py`;
  [S82] sqlite-vec v0.1.9 https://github.com/asg017/sqlite-vec/releases/tag/v0.1.9;
  [S94] model2vec potion-base-32M https://huggingface.co/minishlab/potion-base-32M;
  [S97] sentence-transformers 5.4.1 security fix

**L-2: Few-shot teaching panel**
Drag a handful of files into a category to generate 3-5 in-context examples prepended to future
LLM prompts for that category. Stored in `few_shot_examples.json`. Depends on NEXT-21.
- **Impact**: 4 | **Effort**: 3
- Source: [S6] thebearwithabite adaptive learning

**L-3: OCR pipeline**
Tesseract OCR on import for screenshots and scanned PDFs. Pass extracted text to LLM for
content-based classification. Optional dependency -- skip gracefully if Tesseract not installed.
- **Impact**: 3 | **Effort**: 4
- Source: [S14] Paperless-ngx OCR, [S20] Hazel run-script action

**L-4: Natural-language search**
FTS5 full-text search over organized file paths + AI-generated descriptions. NL query interface
in Browse tab. Depends on NEXT-20 (Browse tab) and NEXT-5 (description stored at move time).
Two local prior-art repos materially shorten this:
PromptCompanion [S61] has the FTS5 BM25 schema + tuned weights (10.0, 1.0, 5.0, 2.0) and the
favorites/history pattern; Bookmark-Organizer-Pro [S55] has `services/nl_query.py` (NL → JSON
schema translation) + `services/rag_chat.py` (citation-aware summaries) + `services/hybrid_search.py`
(keyword + semantic fusion).
- **Impact**: 4 | **Effort**: 3
- Source: [S4] FileWizardAI https://github.com/AIxHunter/FileWizardAI , [S34] RESEARCH_IDEAS.md,
  [S61] PromptCompanion FTS5+BM25 schema, [S55] Bookmark-Organizer-Pro `nl_query.py` +
  `hybrid_search.py` + `rag_chat.py`

**L-5: Custom GGUF model registration**
GUI dialog to register any local `.gguf` model file. App auto-detects context window size and
chat template from GGUF metadata. Routes Ollama calls to the registered model.
- **Impact**: 3 | **Effort**: 3
- Source: [S3] https://github.com/hyperfield/ai-file-sorter

**L-6: Windows context menu integration**
Right-click any folder -> "Organize with FileOrganizer". Launches GUI pre-loaded with that
source folder, or triggers headless classify+apply via COM shell extension.
- **Impact**: 3 | **Effort**: 3

**L-7: Archive content inspection**
Complete `archive_extractor.py`: list top-level items inside ZIP/RAR/7z/tar, extract preview
image if present, feed filelist to keyword classifier. No extraction required for classification.
Add path-traversal guard (validate extracted paths against target dir) as part of this work.
EXTRACTORX [S59] has a clean `ExtractionService` threading + queue model and magic-byte archive
detection in `extractorx/archive.py` worth porting; note that EXTRACTORX itself does NOT ship
a path-traversal guard, so N-13 still owns that guarantee.
- **Impact**: 3 | **Effort**: 3
- Source: [S59] EXTRACTORX `extractorx/extractor.py` ExtractionService + `extractorx/archive.py`

**L-8: Bi-directional sync (symlink mode)**
Optional "keep original in place, symlink into organized tree" mode for users who cannot move
files. Useful for DJs and photographers whose DAM tools track original paths.
- **Impact**: 3 | **Effort**: 3
- Source: [S9] TagStudio non-destructive philosophy

**L-9: GPU quantization controls (Ollama)**
Expose `num_gpu`, `num_thread`, and model quantization (Q4/Q5/Q8) in Ollama settings panel.
Add a "Benchmark Ollama speed" helper reporting tokens/sec for current settings.
- **Impact**: 3 | **Effort**: 2

**L-10: Portable mode**
`portable.flag` file next to the executable switches config, DB, and cache to the same directory
instead of `%APPDATA%\FileOrganizer\`. Enables USB-drive deployment.
- **Impact**: 2 | **Effort**: 2

**L-11: ComfyUI / A1111 output sorter preset**
Plugin (NEXT-25 SDK) that classifies Stable Diffusion / Flux outputs by prompt keywords,
checkpoint hash, sampler settings, image dimensions. Routes to `AI Art - Landscape` vs
`AI Art - Portrait`, etc.
- **Impact**: 3 | **Effort**: 3

**L-12: Progressive dedup checkpointing**
Save partial hash state to disk after every N files during dedup scan. On cancel/resume, skip
already-hashed files. Essential for multi-TB dedup interrupted runs.
- **Impact**: 3 | **Effort**: 3
- Source: [S11] fclones checkpointing pattern

**L-13: macOS / Linux parity**
Abstract watch mode behind a `WatchBackend` protocol so macOS (`FSEvents`) and Linux (`inotify`)
backends can be swapped in. Address symlinks vs junction points and `shutil` fallback differences.
- **Impact**: 3 | **Effort**: 4
- Source: [S8] organize-cli, [S1] LlamaFS, [S2] Local-File-Organizer

**L-14: i18n / localization**
Externalize all UI strings to `locale/en_US.json`. Add Chinese (Simplified) as first non-English
locale (CJK filenames are an existing pain point). Use Qt `QTranslator` + `.qm` files.
- **Impact**: 2 | **Effort**: 4
- Source: [S9] TagStudio Weblate, [S10] Czkawka localization

**L-15: Accessibility (WCAG 2.1)**
Add `accessibleName()` / `accessibleDescription()` to all interactive PyQt6 widgets. Full Tab
order through all panels, Enter to activate. Test with NVDA/JAWS screen reader.
- **Impact**: 2 | **Effort**: 3
- Source: [S9] TagStudio accessibility issues, WCAG 2.1 guidelines

**L-16: Opt-in telemetry**
On explicit opt-in: anonymously report category distribution, confidence score histogram, and
provider selection ratios. No file names, no paths. Used to identify categories most often sent
to `_Review` to prioritize classifier improvements.
- **Impact**: 3 | **Effort**: 3

**L-17: Virtual bundles**
Allow users to create named groupings of assets that span multiple categories without moving files.
A bundle is a named list of asset fingerprints stored in `asset_bundles.db`. Bundles appear as
virtual folders in the Browse tab. Useful for "all assets used in Project X" groupings that do
not map to taxonomy categories. Non-destructive by design — no filesystem changes.
- **Impact**: 3 | **Effort**: 4
- Source: [S43] electron-dam virtual bundles pattern

**L-18: Audio waveform preview in Browse tab**
In the Browse tab (NEXT-22) details panel, render a waveform visualization for audio assets
(`.mp3`, `.wav`, `.aiff`, `.flac`, `.ogg`). Use `librosa` or `soundfile` + `matplotlib` to
compute and render a static waveform PNG, cached alongside the thumbnail. electron-dam ships this
via Wavesurfer.js [S43]; the Qt equivalent is a `QLabel` holding a cached waveform `QPixmap`.
TagStudio's `previews/renderer.py` [S56] already implements an audio waveform path in PySide6
that maps directly onto FileOrganizer's PyQt6 stack — the renderer dispatcher and waveform
QPainter logic are nearly portable line-for-line.
- **Impact**: 2 | **Effort**: 4 | **Depends on**: NEXT-22
- Source: [S43] electron-dam audio waveform visualization, [S56] TagStudio
  `src/tagstudio/qt/previews/renderer.py`

**L-19: Source quarantine for executables found in archives**
When archive_extractor (L-7) lands and starts inspecting archive contents pre-classify, any
`.exe`, `.bat`, `.ps1`, `.scr`, `.cmd`, `.msi`, `.lnk`, `.vbs` discovered inside what looks
like a design-asset bundle should be routed to `<dest>/_Quarantine/<source_name>/` instead of
the asset library. Pirated AE templates have repeatedly shipped with bundled malware
loaders disguised as install helpers. Pair with the path-traversal guard in N-13 to cover
both classes of archive risk in one feature surface.
- **Why later**: Gates on L-7 (archive content inspection) shipping; the quarantine bucket
  itself is a dozen lines once L-7 exists.
- **Impact**: 3 | **Effort**: 3 | **Depends on**: L-7, N-13
- Source: [S32] AUDIT_LESSONS.md, GHSA archive risk corpus, internal pen-test pattern

**L-20: Localized destination folder names**
Distinct from L-14 (UI string i18n). The 384-category taxonomy is English-only; a CJK user
may want destination folders to read `フォトショップ - パターン` instead of
`Photoshop - Patterns & Textures`. Add `category_translations.json` mapping canonical
category → locale → display name; resolve at apply time in `_cat_path()`. The canonical
English name remains the storage key in `asset_db.py` so the DB stays portable across locales.
Ship Simplified Chinese first (CJK filenames are an existing pain point in `loose_files`).
- **Why later**: No active user demand yet, and the migration story for users switching
  locales mid-library is non-trivial (rename every existing folder or maintain symlinks?).
  Revisit after L-14 ships and we have a translator workflow in place.
- **Impact**: 2 | **Effort**: 4 | **Depends on**: L-14
- Source: [S9] TagStudio Weblate workflow, [S43] electron-dam multi-locale design assets

**L-21: Video optimizer / re-encode**
After VideoPage (ui-v0.3.0 WinUI) organizes video assets, offer an optional post-organize step
that re-encodes to HEVC (H.265) or AV1 to reclaim disk space on large video libraries. Scope:
- ffmpeg subprocess: `ffmpeg -i <src> -c:v libx265 -crf 28 -preset slow -c:a copy <dst>`.
- "Crop black bars" option: `ffmpeg -vf cropdetect` pass before encode.
- Safety: keep original until encode finishes and passes a size-sanity check (output ≥ 10% of
  original size), then replace. Progress in WinUI shell VideoPage.
- Opt-in only: never runs as part of an automated organize; requires explicit user action.
Czkawka v11.0.0 [S44] ships this as a first-class mode (video optimizer), confirming demand.
- **Why later**: Windows ffmpeg availability is not guaranteed; requires a new "Optimize" surface
  in VideoPage not designed yet; lossiness concerns require clear user consent UI.
- **Impact**: 2 | **Effort**: 4
- Source: [S44] Czkawka v11.0.0 video optimizer mode, ffmpeg documentation

**L-22: Full WCAG 2.1 AA accessibility compliance**
Complete audit + remediation to achieve Level AA (not just Level A from NEXT-90). Specific targets:
(1) Screen reader testing on Windows (NVDA), macOS (VoiceOver), Linux (Orca). (2) Ensure all images have
descriptive alt text. (3) Maintain 7:1 color contrast on focus indicators. (4) Test with high-zoom (200%)
and magnification tools. (5) Support RTL text rendering (for Arabic/Hebrew file paths). (6) Verify all
dynamic content updates are announced to assistive tech. This is **Level AA** (GDPR "accessibility by design"
requirement in many EU jurisdictions). Benefit: enables use by visually impaired users and users with motor
disabilities. Requires professional accessibility testing (~$2–5K externally); can be self-tested using NVDA
(free) + axe (free).
- **Why later**: Requires sustained UX + testing effort; demand from accessibility community not yet visible.
  Revisit after NEXT-90 ships and we see real-world usage patterns.
- **Impact**: 3 | **Effort**: 5 | **Depends on**: NEXT-90
- Source: [S191] WCAG 2.1 Level AA https://www.w3.org/WAI/WCAG21/quickref/;
   [S192] NVDA screen reader https://www.nvaccess.org/;
   [S193] axe DevTools accessibility testing https://www.deque.systems/axe

**L-23: Internationalization (i18n) UI strings — Qt Linguist workflow**
Extract all UI strings into `FileOrganizer/i18n/fileorganizer_en.ts` (Qt Linguist format). Create translation
files for Chinese, Japanese, Spanish, French, German (`_zh_CN.ts`, `_ja_JP.ts`, etc.). Use Qt Linguist GUI for
translator-friendly editing. Load translations at app startup based on system locale. This is the **standard
PyQt6 pattern** (not GNU gettext). Enables FileOrganizer to serve non-English users. Initial target: Chinese
(1.4B potential users), Japanese (125M), Spanish (475M). Community translators can contribute via Weblate
(free open-source hosting). Effort is primarily translation sourcing; code changes are minimal (one
`QTranslator::load()` call at startup).
- **Why later**: No active non-English user base yet. Revisit after v9.0 ships and we measure geographic usage.
- **Impact**: 2 | **Effort**: 3 | **Depends on**: code cleanup (ensure all UI strings are wrapped in `QCoreApplication.translate()`)
- Source: [S194] Qt Linguist documentation https://doc.qt.io/qt-6/linguist-manager.html;
   [S195] Weblate https://weblate.org/;
   [S196] PyQt6 QTranslator https://www.riverbankcomputing.com/static/Docs/PyQt6/api/qtcore/qtranslator.html

**L-24: Category taxonomy translation (localized folder names)**
Extend i18n to the 384-category taxonomy (Photoshop, Blender, Adobe, etc.). Ship category name + description
translations for top-5 languages (Chinese, Japanese, Spanish, French, German). At application time, resolve
category to localized folder name via `category_translations.json`. Store canonical English category in DB
so assets remain portable across locale switches. Example: `Photoshop - Patterns & Textures` → `フォトショップ
- パターンとテクスチャ` on Japanese system. Complexity: handling users switching locales mid-library (do we
rename folders or maintain symlinks?). Recommend: ship folder-rename safe mode + symlink fallback.
- **Why later**: Depends on L-23 (i18n infrastructure); no current demand from non-English users.
- **Impact**: 2 | **Effort**: 4 | **Depends on**: L-23
- Source: [S197] Qt file system locale handling;
   [S198] Unicode filename best practices (BOM, combining characters);
   [S199] TagStudio i18n integration (Weblate workflow reference)

**L-25: Plugin ecosystem — pluggy-based extensibility**
Design + implement a plugin architecture using `pluggy` (pytest's plugin framework). Define plugin hooks:
(1) `categorize_post` — modify AI classification result before apply. (2) `apply_pre` / `apply_post` — intercept
file move operations. (3) `ui_panel_custom` — register custom tabs in Browse UI. (4) `classifier_custom` — swap
in alternate ML models. Sandbox plugins in separate Python namespace; validate plugin manifest (name, version,
entry point). This enables power users and third-party developers to extend FileOrganizer without forking.
Example plugin: "Archive2Folder" plugin that, after organizing, compresses old assets by date. Effort includes
plugin API documentation, example plugins, and installation workflow (pip install user-plugins from PyPI).
- **Why later**: Requires stable v9.x API + user demand for extensibility not yet visible.
- **Impact**: 3 | **Effort**: 5 | **Depends on**: API stabilization (NEXT-1 through NEXT-30)
- Source: [S200] pluggy https://pluggy.readthedocs.io/;
   [S201] pytest plugin tutorial (reference architecture);
   [S202] stevedore (alternative: entry_points-based plugins) https://stevedore.readthedocs.io/

**L-26: Snap package distribution (Ubuntu/Linux)**
Create Snapcraft manifest (`snapcraft.yaml`) for Ubuntu Snap Store. Snaps run in containers with restricted
file system access (users can override with `--devmode` for full access). This is **Ubuntu's preferred** package
format but has lower adoption than AppImage (L-25 ships AppImage first). Snap auto-updates via Store. Effort:
~2 days to write + test the manifest. Defer to post-v9.0 unless significant Ubuntu user demand emerges.
- **Why later**: AppImage (NEXT-85) is more portable and community-preferred. Snap adoption is concentrated in
  Ubuntu; we serve broader Linux via AppImage first. Revisit if Ubuntu users request it.
- **Impact**: 2 | **Effort**: 3 | **Depends on**: NEXT-85 (AppImage shipping first)
- Source: [S203] Snapcraft https://snapcraft.io/;
   [S204] Snap confinement model https://snapcraft.io/docs/snap-confinement

**L-27: Flatpak distribution (GNOME/KDE/XFCE desktops)**
Create Flatpak manifest for Flatseal Sandbox. Flatpak is the **community-preferred containerization** on
GNOME and KDE desktops. Permissions sandbox model (declare home, documents, download access). Ship via Flathub
(community-run app store). Effort: similar to Snap (~2 days). Like Snap, defer to post-v9.0; AppImage (NEXT-85)
handles the Linux long-tail more efficiently. Revisit if GNOME/KDE user demand emerges.
- **Why later**: AppImage is the cross-distro standard; Flatpak adoption is concentrated in newer desktops.
- **Impact**: 2 | **Effort**: 3 | **Depends on**: NEXT-85 (AppImage priority)
- Source: [S205] Flatpak https://flatpak.org/;
   [S206] Flathub https://flathub.org/;
   [S207] Flatpak permission sandbox https://docs.flatpak.org/en/latest/sandbox-permissions.html

**L-28: Windows MSIX / Microsoft Store distribution**
Package FileOrganizer as MSIX (Microsoft's modern Windows app format) for distribution via Microsoft Store.
MSIX enables automatic updates via Store, but requires sandboxing (limited file system access; users must
grant folder permissions via system UI). This is **enterprise-preferred** but restrictive for a file organizer.
Effort: 1–2 weeks to refactor file I/O paths to respect sandbox boundaries. Defer to v9.5+ or later when we
have stable cloud sync (LATER-15). Requires $19 USD annual registration fee in Microsoft Partner Center.
- **Why later**: Sandbox refactoring is high-effort; demand from Store users not yet visible. Better to ship
  portable exe + Homebrew + AppImage first. Enterprise adoption may eventually justify MSIX effort.
- **Impact**: 2 | **Effort**: 5 | **Depends on**: file system abstraction refactoring
- Source: [S208] MSIX containerization https://learn.microsoft.com/en-us/windows/msix/overview;
   [S209] Microsoft Partner Center https://partner.microsoft.com/;
   [S210] MSIX file system sandbox constraints

**L-29: Debian/AUR package maintenance (community-driven)**
Create `.deb` package (Debian/Ubuntu) and AUR (Arch User Repository) manifest. These are lower-priority than
AppImage (NEXT-85) because: (1) Debian requires recurring review + rebuilds per distro version; (2) AUR is
community-maintained (we don't control release cycle). Acceptable path: publish AppImage, let community
contributors submit .deb + AUR packages if they want. If we ship this ourselves, effort is ~1 week per format.
Prefer to defer to community volunteers.
- **Why later**: AppImage + Snap + Flatpak cover Linux users well. .deb + AUR are high-maintenance with
  minimal reach increase. Community-driven is acceptable.
- **Impact**: 1 | **Effort**: 4 | **Depends on**: NEXT-85 (AppImage established first)
- Source: [S211] Debian package creation https://www.debian.org/doc/manuals/maint-guide/;
   [S212] AUR submission https://wiki.archlinux.org/title/AUR_submission_guidelines

**L-30: Commercial licensing model (optional v10.x+ revenue)**
Design + implement a licensing tier system: (1) **Community Edition** — free, open-source, unlimited use for
individuals + educational institutions. (2) **Team Edition** — $49/yr per user, includes team collaboration
(multi-user library sharing, LATER-16). (3) **Enterprise Edition** — custom pricing, includes priority support
+ on-premise deployment. Implement via License Key + validation server (Lemonsqueezy or Gumroad integration).
No server-side functionality change; license check is local. This is **optional revenue stream** for funding
continued development. Requires legal review (terms of service, refund policy, export compliance for non-US
users). Defer to v10.x or later; ship v9.x as fully free/open-source first to build community trust.
- **Why later**: Revenue is not required for v9.x viability; community-first positioning builds trust.
  Licensing complexity introduces friction for adoption. Revisit after v9.0 ships + user base stabilizes.
- **Impact**: 1 | **Effort**: 4
- Source: [S213] Lemonsqueezy licensing https://www.lemonsqueezy.com/;
   [S214] Gumroad licensing https://gumroad.com/;
   [S215] Open-source dual-licensing model (example: JetBrains IntelliJ IDEA Community + Ultimate)

**L-31: Analytics dashboard (observability + user insights)**
Ship an optional in-app dashboard reporting: (1) Total files organized by category (bar chart). (2) ML model
accuracy over time (confusion matrix trending). (3) Duplicate files detected (% of library). (4) Storage reclaimed
(GB moved to archive). (5) Top 10 file types processed. Data is local-only (no phone-home); stored in SQLite.
Dashboard helps users understand their library structure + FileOrganizer's impact. Pairs with NEXT-74 (metrics)
+ NEXT-75 (crash reporting) for observability. Low user value but high marketing/retention impact. Effort:
UI + SQLite queries (~1 week).
- **Why later**: Nice-to-have; core organize functionality (NEXT-1 through NEXT-50) is higher priority.
- **Impact**: 2 | **Effort**: 3 | **Depends on**: NEXT-74 (metrics collection)
- Source: [S216] Analytics dashboard patterns (Metabase, Superset);
   [S217] SQLite aggregation queries;
   [S218] PyQt6 charting (PyQtGraph, matplotlib integration)

---

## UNDER CONSIDERATION

Requires more research or explicit user demand before committing.

**UC-1: REST API / headless server mode**
Expose classify/move operations over HTTP (FastAPI). Enables remote triggering and scripting.
Primary concern: desktop app semantics (drive letters, UNC paths) do not translate cleanly to a
server model. Hold until explicit user demand.
- Source: [S4] FileWizardAI, [S14] Paperless-ngx REST API

**UC-2: Sidecar XMP metadata write-back**
Write classified category and marketplace metadata to `.xmp` sidecar alongside each asset.
Design assets (AEP/PSD) rarely have XMP tooling, limiting utility. Revisit if photographer use
case grows beyond current user base.
- Source: [S12] TagSpaces, [S15] digiKam, [S24] XMP Specification

**UC-3: Staging grace window**
Hold all moves in a `_Pending` folder for N days before finalizing. The existing
`organize_moves.db` undo already provides this capability more precisely. Adds UI complexity
for marginal gain. Revisit if user feedback requests it.
- Source: [S6] thebearwithabite 7-day staging

**UC-4: Rating & label system**
Star ratings and color labels per asset stored in DB. Needs Browse tab (NEXT-20) as UX surface.
Revisit after NEXT-20 ships.
- Source: [S22] Adobe Bridge, [S15] digiKam, [S9] TagStudio

**UC-5: In-app update notification**
Check GitHub Releases API on startup; notify if a newer version exists. Implement once release
cadence stabilizes to avoid false positives from frequent pre-release tags.

**UC-6: EXIF remover / metadata strip**
Strip EXIF data from images and video before or after organizing — useful for privacy-conscious
workflows or before uploading to stock platforms. Czkawka v11.0.0 [S44] ships this as a
first-class mode. For FileOrganizer, the primary conflict is that the N-9 metadata pipeline
depends on EXIF being present; stripping before classify would degrade classification accuracy.
Hold until there is explicit user demand and a clear pre/post classify trigger option.
- Source: [S44] Czkawka v11.0.0 EXIF remover mode

**UC-7: MCP server integration**
Expose FileOrganizer's classify+organize pipeline as an MCP v1 tool server, so Claude Desktop /
Cursor / any MCP-enabled agent can invoke `classify_design`, `organize_run`, or `get_undo_log`
as tool calls. `movi-organizer` [S100] ships an MCP v1 server that wraps a Python organizer —
the integration surface is small (one `server.py`, one `tools.py`). Hold until MCP v1 spec
reaches 1.0 stable and there is validated user demand for agent-driven file organization.
Contraindication: agent-driven moves are higher-risk than GUI-gated moves; requires a
dry-run-first mandate from the agent layer.
- Source: [S100] movi-organizer MCP integration https://github.com/movi-organizer/movi;
  [S101] MCP specification v1 https://spec.modelcontextprotocol.io/specification/

---

## PARTNERSHIPS (Wave 5e research)

Explored ecosystem integrations that could accelerate adoption or unlock new capabilities.
Most are 2026 Q2–Q4 conversation starters; none block v9.0 shipping. Listed here for reference.

**P-1: Envato Elements direct export partnership**
Negotiate direct partnership with Envato to add FileOrganizer to Envato Creator tools ecosystem. Goal:
"Export organized collection as Envato Elements batch upload template" — one-click upload of classified
asset batches (tagged with royalty-free license metadata) to Videohive/AudioJungle/GraphicRiver. Requires:
(1) Envato API credentials (free tier available); (2) YAML serialization of categories + license metadata;
(3) Batch uploader frontend. Value: drives discovery + adoption from Envato creator community (1M+ creators).
- **Strategic value**: High | **Effort**: 2 | **Timeline**: Q3 2026 | **Revenue**: Referral fees possible
- Source: [S246] Envato API https://www.envato.com/APIs/

**P-2: Adobe Creative Cloud Bridge integration**
Ship a Lightroom Classic plugin that auto-imports organized FileOrganizer collections (as Lightroom
catalogs). Goal: photographers organized on Windows can import into Lightroom for editing/publishing.
Requires: (1) Lightroom CC plugin SDK; (2) Export FileOrganizer taxonomy as keywords; (3) Asset linking.
Value: locks photographers into FileOrganizer + Lightroom workflow.
- **Strategic value**: High | **Effort**: 3 | **Timeline**: Q3–Q4 2026 | **Revenue**: Potential Adobe co-marketing
- Source: [S247] Adobe Lightroom CC plugin SDK https://developer.adobe.com/

**P-3: Blender asset browser plugin**
Native Blender addon that mounts FileOrganizer's catalog directly into Blender's File > Open File Browser.
Users browse organized 3D models/textures/VFX while modeling. Requires: (1) Blender Python API (bpy);
(2) FileOrganizer catalog as JSON; (3) Asset previews. Value: FileOrganizer becomes **the** asset
organizer for Blender pipeline (4M+ Blender users monthly).
- **Strategic value**: High | **Effort**: 2 | **Timeline**: Q2–Q3 2026 | **Revenue**: Potential Blender Foundation sponsorship
- Source: [S248] Blender addon API https://docs.blender.org/api/

**P-4: Krita brush pack integration**
Export organized brush libraries as installable Krita brush packs. Krita asset browser loads these;
FileOrganizer taxonomy → Krita presets. Value: Krita community (free design tool, popular with artists)
becomes early adopter base.
- **Strategic value**: Medium | **Effort**: 1 | **Timeline**: Q2 2026 | **Revenue**: Low, high brand visibility
- Source: [S249] Krita brush pack format https://docs.krita.org/

**P-5: Ollama model marketplace listing**
List FileOrganizer as recommended tool for LLM workflows on Ollama community site. Bundled model:
ollama pull fileorganizer-qwen2.5-vl installs asset-classification-optimized model. Requires:
(1) Fine-tune Qwen2.5-VL on 384-category taxonomy; (2) Publish to Ollama Hub; (3) Integration.
Value: model discovery from Ollama marketplace (100K+ users/month). Revenue: potential sponsorship.
- **Strategic value**: High | **Effort**: 2 | **Timeline**: Q3 2026 | **Revenue**: Potential Ollama partnership
- Source: [S250] Ollama Hub models https://ollama.ai/models

**P-6: Weblate translation community scaling**
List FileOrganizer on Weblate to recruit volunteer translators for CJK, Spanish, French, German, Italian,
Portuguese, Russian. Value: ships localized UI to 90% of global user base without engineering effort.
Weblate provides community review workflows.
- **Strategic value**: Medium | **Effort**: 1 | **Timeline**: Q2 2026 | **Revenue**: None, high accessibility impact
- Source: [S251] Weblate community projects https://weblate.org/en/projects/

**P-7: Linux Foundation / GNOME / KDE partnerships**
Pitch FileOrganizer to GNOME and KDE leadership as reference implementation for "modern desktop file
organization with AI". Goals: (1) Featured placement on GNOME / KDE app portals; (2) App rotation in
GNOME Software / KDE Discover; (3) Potential Linux Foundation sponsorship. Value: 10–50M Linux users
could discover FileOrganizer via official channels.
- **Strategic value**: High | **Effort**: 2 | **Timeline**: Q2–Q3 2026 | **Revenue**: Sponsorship possible
- Source: [S252] GNOME Foundation partnerships https://www.gnome.org/partners/;
   [S253] KDE Dot community program https://dot.kde.org/

---
## REJECTED

Explicit rejects. Do not resurrect without re-opening the discussion.

| Item | Rationale |
|------|-----------|
| **Electron / web GUI rewrite** | PyQt6 is working. A full JS/Electron rewrite introduces a second toolchain with no functionality gain. Rejected. |
| **In-filename tag embedding** | Directly contradicts the folder-move classification model. Mutates filenames without benefit for design asset workflows. TagSpaces covers this niche. Rejected. |
| **Cloud sync** (Google Drive, S3, OneDrive) | FileOrganizer is local-first by design. Network drives appear as local paths; no cloud-sync layer needed. Rejected. |
| **Multi-user / team collaboration** | Single-user desktop tool. Paperless-ngx is the correct recommendation for team document management. No network server planned. Rejected. |
| **Docker containerized deployment** | PyQt6 requires a display server; containerizing breaks OS file-system semantics (drive letters, UNC paths) for zero benefit. Rejected. |
| **Browser plugin / web clipper** | Out of scope for a local desktop organizer. TagSpaces covers this niche. Rejected. |
| **EPUB / eBook management** | No stated use case in repo or user community. Rejected. |
| **Music library management** | mutagen is in requirements for metadata extraction only, not as a music management suite. MusicBrainz lookups out of scope. Rejected. |
| **Non-destructive tag-only mode** | Directly contradicts FileOrganizer's core value proposition (classify and move). UniFile is named in the README as the successor for tag-based use cases. Rejected for FileOrganizer core. |
| **Adobe Bridge-style publication workflow** | FileOrganizer organizes assets; it does not manage publishing to marketplaces. Rejected. |
| **Android companion app** | No server-side component to connect to. Requires REST API (UC-1) first and explicit user demand. Rejected until UC-1 is decided. |

---

## Coverage Matrix

| Category | Status | Primary Items |
|----------|--------|---------------|
| **Security** | Covered | N-7 (Pillow/PyQt6 pins + pip-audit CI, shipped), N-13 (fonttools CVE pin + psd-tools subprocess isolation + archive path-traversal guard, **shipped v8.2.0**), NEXT-49 (psd-tools GHSA-24p2-j2jr-386w ZIP-bomb hardening — NOW), L-7 (archive content full implementation), L-19 (executable quarantine on archive scan), UC-6 (EXIF remover — on hold), NEXT-88 (REUSE.software compliance audit + LICENSES.md) |
| **Accessibility** | Covered | NEXT-90 (WCAG 2.1 Level A baseline), NEXT-89 (keyboard shortcut customization), L-22 (WCAG 2.1 AA full compliance), L-15 (screen reader testing) |
| **i18n / l10n** | Covered | L-23 (Qt Linguist UI string extraction + Chinese/Japanese/Spanish/French/German), L-24 (localized category taxonomy names), L-14 (QTranslator UI strings, CJK locale), L-20 (localized destination folder names) |
| **Observability / telemetry** | Covered | L-16 (opt-in analytics), N-4 (pre-flight report), NEXT-25 (post-apply report), NEXT-31 (scan time measurement), NEXT-38 (crash dialog + log viewer), NEXT-91 (privacy policy + telemetry opt-out), L-31 (analytics dashboard) |
| **Testing** | Covered | NEXT-29 (unit test expansion to 10+ functions), N-7 (pip-audit CI gate), N-14 (broken file detection as pre-run validation), N-15 (SOURCE_CONFIGS parity test, **shipped v8.2.0**) |
| **Distribution / packaging** | Covered | NEXT-81 (Windows Authenticode signing), NEXT-82 (macOS code signing + notarization), NEXT-83 (multi-platform CI/CD matrix), NEXT-84 (Homebrew Cask), NEXT-85 (Linux AppImage + GPG), NEXT-86 (WinSparkle auto-updates), NEXT-87 (Sparkle macOS auto-updates), L-26 (Snap distribution), L-27 (Flatpak distribution), L-28 (MSIX Windows Store), L-29 (Debian .deb + AUR), N-3 (catalog auto-download), N-16 (catalog sync conditional requests, **shipped v8.2.0**), NEXT-30 (multiplatform CI), L-10 (portable mode) |
| **Plugin ecosystem** | Covered | L-25 (pluggy-based extensibility architecture), NEXT-27 (SDK + 3 reference plugins), NEXT-28 (webhook) |
| **Mobile** | Rejected | Android app rejected (no server backend); revisit after UC-1 |
| **Offline / resilience** | Covered | N-6 (two-phase commit), N-2 (incremental journal), N-17 (robocopy multi-thread, **shipped v8.2.0**), NEXT-34 (provider failover), NEXT-35 (reparse-point detection), NEXT-36 (free-space reserve), NEXT-37 (journal vacuum + retention), Ollama local fallback already in prod |
| **Performance** | Covered | N-17 (robocopy /MT, **shipped**), NEXT-6 (parallel async LLM), NEXT-33 (xxhash/blake3 fast fingerprint), NEXT-5 (minimal-diff re-scan), NEXT-44 (LLM summary cache) |
| **Multi-user / collaboration** | Rejected | Single-user tool by design; see Rejected table |
| **Migration paths** | Covered | N-1 (I:\ legacy reclassification), CATEGORY_ALIASES expansion (already shipped) |
| **Upgrade strategy** | Covered | N-3 (schema version gate on catalog sync), UC-5 (in-app update notification), NEXT-86, NEXT-87 (auto-update frameworks) |
| **Commercial licensing** | Covered | L-30 (optional dual-licensing model — Community + Team + Enterprise editions) |
| **WinUI Shell** | Active | ui-v0.5.0 shipped (15 pages); NEXT-39 (WinAppSDK 2.0 upgrade), NEXT-40 (RAWPage), NEXT-41 (ComicsPage) target ui-v0.6.0 |

### Security -- additional notes
- **psd-tools GHSA-24p2-j2jr-386w** (Feb 2026, CVSS 6.8 Medium): `zlib.decompress` in
  `psd_tools.compression` has no `max_length` cap (ZIP-bomb OOM); PSB width/height/depth not
  validated before buffer allocation (300,000×300,000 px = 144 TB virtual alloc); `assert` used
  as runtime guard (disabled with `python -O`). Mitigation: N-13 subprocess isolation bounds OOM
  to a child process. NEXT-49 adds pre-validation header check (reject width/height > 30,000) and
  documents the advisory in SECURITY.md.
  Source: [S83] https://github.com/advisories/GHSA-24p2-j2jr-386w
- **sentence-transformers < 5.4.1**: activation function injection from Hub models → arbitrary
  code execution. Fixed in v5.4.1. Pin `sentence-transformers>=5.4.1` in requirements.txt.
  Source: [S97] sentence-transformers 5.4.1 release notes
- **DeepSeek V4 alias deadline (July 24, 2026)**: `deepseek-chat` and `deepseek-reasoner` aliases
  stop working July 24, 2026. NEXT-46 (NOW tier) covers migration to `deepseek-v4-flash` and
  `deepseek-v4-pro`. Missing this deadline = complete loss of DeepSeek functionality.
  Source: [S78] DeepSeek V4 announcement
- **psd-tools** parses untrusted `.psd` files. Maliciously crafted PSDs could trigger parser bugs.
  Fix: run parser in subprocess with file-size sanity limit. **Shipped in N-13 (v8.2.0).**
- **rarfile / py7zr** extract untrusted archives. Path traversal risk (archive entry names with
  `../`). 2 open GitHub Advisory DB entries for each. Fix: validate all extracted paths against
  target directory before write. **Shipped in N-13 (v8.2.0).**
- **fonttools** CVE-2025-66034 (path traversal in `varLib.main`, fixed v4.61.0). N-9 metadata
  extractors use fonttools; pin `fonttools>=4.62.1` in the same commit. **Shipped in N-13 (v8.2.0).**
- **API keys** (DeepSeek, GitHub, Envato) are stored in `%APPDATA%\FileOrganizer\` settings.
  Verify they are not logged or committed. Covered by N-7 audit pass (shipped).

---

## Competitive Landscape (Summary)

| Tool | Type | Key strength | FileOrganizer gap addressed |
|------|------|--------------|----------------------------|
| organize-cli [S8] | OSS CLI | YAML rules, dry-run, deduplicate conflict mode (v3.3.0), exiftool integration | NEXT-2 (YAML export), NEXT-3 (rule chains), NEXT-43 (exiftool) |
| LlamaFS [S1] | OSS Electron | Watch mode, minimal-diff index, Groq/Ollama backends ⚠️ **Effectively abandoned — last meaningful commit Oct 2024; 1 cosmetic README commit in all of 2025** | NEXT-1, NEXT-5 |
| curdriceaurora/Local-File-Organizer [S98] | OSS Python | v2.0-alpha.3: 840 tests, multi-modal Ollama (Qwen2.5-VL), TUI (Textual 8 views) + WebUI (FastAPI+HTMX) + Desktop (pywebview), PARA+Johnny Decimal taxonomy, full undo/redo stack, cross-platform installers. **Primary OSS threat.** Still alpha; lacks Windows-native UI, 384-category creative taxonomy, PSD/font/AEP metadata. | NEXT-11 thumbnails, NEXT-20 browse tab |
| Czkawka/Krokiet [S10] | OSS Rust GUI | Perceptual hash dedup, broken video detection (v11), bad-names scanner, video optimizer, EXIF remover | NEXT-19, NEXT-32, N-14, NEXT-42, L-21, UC-6 |
| fclones [S11] | OSS Rust CLI | Reflinks, cross-library dedup, JSON, fclones-gui (pre-release), blake3 default | NEXT-20, NEXT-33 |
| TagStudio [S9] | OSS Python/Qt | Non-destructive tagging, infinite scrolling (v9.5.6), CB7/CBR/CBT thumbnails, 7+ locales | Different model (move vs tag) -- intentional; NEXT-41 pattern |
| electron-dam [S43] | OSS Electron | Semantic search, virtual bundles, 3D/audio preview, Ollama embedding | L-1, L-17, L-18 |
| AIFileSorterShellExtension [S45] | OSS C# | Windows Explorer context menu, 2-min undo, OpenRouter LLM, game/mod file recognition | L-6 (context menu -- prior art confirmed) |
| hazelnut [S68] | OSS Rust TUI | TOML rules, daemon, 15 TUI themes, desktop error notifications, age/size conditions, archive action | NEXT-1, NEXT-42 pattern |
| Foldr [S67] | OSS Rust CLI | Preview → confirm → move flow, keep-newest/keep-largest/keep-oldest dedup, per-op undo IDs, TOML config | NEXT-19 UX, NEXT-24 |
| hyperfield AI File Sorter [S3] | OSS Python+Qt | v1.7.3: local GGUF, Vulkan/CUDA/Metal GPU, document content analysis (PDF/DOCX/XLSX), audio/video metadata (ID3/Vorbis/MP4), image analysis via LLaVA, Microsoft Store | L-5 (GGUF), NEXT-30 distribution, NEXT-11 |
| Iris [S99] | OSS Rust | Rust-native, cross-platform, fast directory walker, LLM API integration, 2025 active | NEXT-33 (blake3) pattern |
| FIXXER [S102] | OSS Python | VLM-based photo organizer (faces, scenes), privacy-preserving local inference | NEXT-12 (VLM) pattern |
| movi-organizer [S100] | OSS Python | MCP v1 server integration — exposes organize as an MCP tool for Claude/Cursor | UC-7 |
| deta/surf [S128] | OSS TypeScript/Rust | Personal AI Notebooks; file library + semantic search + note generation from files. 3,370⭐ in 7 mo. Tangential use case (notes vs. asset classification). | L-1 (semantic), L-4 (NL search) |
| hyperfield/ai-file-sorter (C++) [S129] | OSS C++ | v1.4.0+: cross-platform desktop, local GGUF + cloud LLM support, content-aware preview, 889⭐, AGPL-3.0. Focus on preview-before-apply UX. | NEXT-19 (preview UX) |
| iamshrisawant/sorted [S130] | OSS Python | Semantic similarity learning (sentence-transformers + FAISS), learns user corrections, 50⭐, April 2026 active. | L-1 (embedding learning pattern) |
| sarawagh27/smart-ai-file-organizer [S131] | OSS Python | Multi-format (PDF/DOCX/XLSX/ZIP), semantic search, watch mode, web demo (Gradio/Streamlit), 20⭐. | NEXT-1, L-1 |
| xiaojiou176-open/movi-organizer [S132] | OSS Python | Review-first with dry-run, rollback, MCP-safe for agent calling, April 2026. | NEXT-19 (dry-run UX), UC-7 (MCP) |
| k3sra/Downganizer [S133] | OSS C# | Windows Service file sorter, 700+ extensions, 60s "deep-quiet protocol" for watch mode, 20⭐. | NEXT-1 (watch mode pattern), NEXT-68 (Task Scheduler) |
| Note Companion (formerly File Organizer 2000) [S134] | OSS TypeScript | Obsidian plugin rebranded, AI note assistant, 832⭐. Different model (notes vs. files). | Different use case |
| Eagle App [S19] | Commercial | Visual search, designer UX | NEXT-22 (thumbnail browser) |
| Hazel [S20] | Commercial macOS | Rule chains, Spotlight conditions | NEXT-3, NEXT-1 |
| File Juggler [S21] | Commercial Win | Folder watch, content conditions | NEXT-1, NEXT-3 |
| Paperless-ngx [S14] | OSS Docker | OCR, multi-user, REST API | Single-user; OCR in L-3 |
| Adobe Bridge [S22] | Commercial | AEP/PSD preview, CC integration | NEXT-22 |

**FileOrganizer's unique position**: design-asset-specialist classifier (384 categories, Envato
marketplace ID enrichment, AEP-aware pipeline) + multi-TB real-world hardening + metadata-first
AI cost reduction (N-9, shipped v8.3.0) + WinUI 3 shell (15 live pages, ui-v0.5.0). No OSS
competitor combines all three. Wave 2 research (May 2026) confirms emerging patterns: semantic
similarity learning (sorted), review-before-apply UX (movi-organizer, hyperfield), MCP integration
(movi-organizer), and cross-platform/multi-frontend deployment (Local-File-Organizer). FileOrganizer
remains the **only stable, creative-asset-focused desktop organizer** with Windows-native WinUI 3 UI,
PSD/font/AEP metadata extraction, and 384-category Envato-aligned taxonomy. v8.3.0 shipped 2026-05-02.
v8.4.0 sprint adds 13 new NEXT items (NEXT-56–NEXT-68) across dependency ecosystem, platform
integration, and watch-mode MVP. Primary OSS threat remains `curdriceaurora/Local-File-Organizer`
v2.0-alpha.3 [S98] — strong testing, multi-frontend, but still alpha and missing creative taxonomy depth.

---

## Appendix -- Research Sources

Every claim in this roadmap traces to at least one source below.

### OSS Competitors
- [S1] LlamaFS -- https://github.com/iyaja/llama-fs
- [S2] Local-File-Organizer (QiuYannnn) -- https://github.com/QiuYannnn/Local-File-Organizer
- [S3] AI File Sorter (hyperfield) -- https://github.com/hyperfield/ai-file-sorter
- [S4] FileWizardAI -- https://github.com/AIxHunter/FileWizardAI
- [S5] aifiles (jjuliano) -- https://github.com/jjuliano/aifiles
- [S6] ai-file-organizer (thebearwithabite) -- https://github.com/thebearwithabite/ai-file-organizer
- [S7] docmind-ai-llm (BjornMelin) -- https://github.com/BjornMelin/docmind-ai-llm
- [S8] organize-cli (tfeldmann) -- https://github.com/tfeldmann/organize (v3.3.0: deduplicate
  conflict mode, EXIF on non-image files, filecontent filter for DOCX/PDF)
- [S9] TagStudio -- https://github.com/TagStudioDev/TagStudio
- [S10] Czkawka (qarmin) -- https://github.com/qarmin/czkawka
- [S11] fclones (pkolaczk) -- https://github.com/pkolaczk/fclones
- [S12] TagSpaces -- https://github.com/tagspaces/tagspaces
- [S13] Hydrus Network -- https://github.com/hydrusnetwork/hydrus
- [S14] Paperless-ngx -- https://github.com/paperless-ngx/paperless-ngx
- [S15] digiKam -- https://www.digikam.org/about/
- [S16] hazelnut (ricardodantas) -- https://github.com/ricardodantas/hazelnut
  (see [S68] for full feature summary)
- [S17] electron-dam (simeonradivoev) -- https://github.com/simeonradivoev/electron-dam
  (3D model preview, audio waveform, Ollama semantic search, virtual bundles)
- [S18] fixxer -- GitHub topic: file-organizer scan

### Commercial Competitors
- [S19] Eagle App -- https://eagle.cool
- [S20] Hazel (Noodlesoft) -- https://www.noodlesoft.com/hazel/
- [S21] File Juggler -- https://www.filejuggler.com/features/
- [S22] Adobe Bridge -- https://www.adobe.com/products/bridge.html

### Standards & APIs
- [S23] Envato API -- https://build.envato.com/api/
- [S24] XMP Specification -- https://www.adobe.com/devnet/xmp.html
- [S25] RIFX/RIFF format -- https://en.wikipedia.org/wiki/Resource_Interchange_File_Format

### Dependency Changelogs & Security
- [S26] Pillow changelog -- https://pypi.org/project/Pillow/#history (v12.2.0)
- [S27] GitHub Advisory Database (Pillow) -- https://github.com/advisories?query=pillow
- [S28] PyQt6 PyPI -- https://pypi.org/project/PyQt6/#history (v6.11.0, March 2026)
- [S29] openai Python SDK -- https://pypi.org/project/openai/

### Community Signal
- [S30] GitHub topic: file-organizer -- https://github.com/topics/file-organizer (303 repos)
- [S31] GitHub topic: digital-asset-management -- https://github.com/topics/digital-asset-management (84 repos)

### Internal Sources
- [S32] AUDIT_LESSONS.md -- Hard-won lessons from the April 2026 33 TB organize run
- [S33] RESEARCH.md -- Implementation tracks: Plan-First Apply, Asset Catalog, Multimodal Router
- [S34] RESEARCH_IDEAS.md -- 12 research areas: metadata extractors, embeddings, YAML rules
- [S35] CHANGELOG.md v8.2.0 -- Audit findings, phantom category fixes, fix_duplicates hazard
- [S36] CLAUDE.md -- Living working notes: architecture, known issues, version history

### New Sources (Phase 1 refresh, May 2026)
- [S37] rarfile (markokr) -- https://github.com/markokr/rarfile -- ISC licensed; extraction via
  external unrar/7zip; 2 GitHub Advisory DB entries; path-traversal risk in archive entry paths
- [S38] TagStudio v9.5.6 release notes -- https://github.com/tagstudiodev/tagstudio/releases/tag/v9.5.6
  (infinite scrolling, .cb7/.cbr/.cbt thumbnails, 7 active locales)
- [S39] TagStudio v9.5.5 release notes -- https://github.com/tagstudiodev/tagstudio/releases/tag/v9.5.5
  (thumbnail cache quality + resolution settings in settings.toml)
- [S40] organize-cli v3.3.0 release -- https://github.com/tfeldmann/organize/releases/tag/3.3.0
  (deduplicate conflict mode, EXIF on EPUB/PDF, filecontent DOCX/PDF native)
- [S41] py7zr GitHub Advisories -- https://github.com/miurahr/py7zr/security/advisories
  (2 entries; path traversal risk in archive extraction paths)
- [S42] rarfile GitHub Advisories -- https://github.com/advisories?query=rarfile (2 entries)
- [S43] electron-dam (simeonradivoev) -- https://github.com/simeonradivoev/electron-dam
  (Electron DAM: Ollama semantic search, virtual bundles, 3D preview via ASSIMP, audio
  waveform via Wavesurfer.js, Humble Bundle import, light/dark mode)
- [S44] Czkawka v11.0.0 release -- https://github.com/qarmin/czkawka/releases/tag/11.0.0
  (Krokiet is now primary GUI; broken video detection via ffprobe; RAW JPEG preview extraction;
  JSON config; wgpu/skia/femtovg backends; scan time measurement; grouping overhaul)
- [S45] AIFileSorterShellExtension (nonniks) -- https://github.com/nonniks/AIFileSorterShellExtension
  (C# Windows Explorer context menu, OpenRouter LLM, game/mod recognition, 2-minute undo window;
  corroborates L-6 prior art)
- [S46] psd-tools v1.16.0 -- https://pypi.org/project/psd-tools/#history
  (Apr 24, 2026; Python 3.14 support; composite extra with aggdraw/scipy/scikit-image for
  advanced layer rendering)
- [S47] imagehash (JohannesBuchner) -- https://github.com/JohannesBuchner/imagehash
  (pHash, dHash, wHash, average hash, colorhash, crop-resistant hash; Hamming distance;
  BK-tree for sub-linear similarity search)
- [S48] sentence-transformers -- https://www.sbert.net / https://github.com/UKPLab/sentence-transformers
  (15,000+ pretrained models on HuggingFace; sparse encoder support added; all-MiniLM-L6-v2
  confirmed viable at 80M params for local embedding)
- [S49] fonttools CVE-2025-66034 / v4.62.1 -- https://pypi.org/project/fonttools/#history
  (CVE-2025-66034: path traversal in varLib.main, fixed in 4.61.0; v4.62.1 = Mar 2026 latest)
- [S50] fclones-gui v0.1.2 -- https://github.com/pkolaczk/fclones-gui/releases
  (pre-release GUI wrapper for fclones; confirms demand for GUI dedup tooling)
- [S51] Hydrus Network v670 -- https://github.com/hydrusnetwork/hydrus/releases/tag/v670
  (curl_cffi HTTP/2 test mode; off-screen window rescue logic; tag suggestion improvements)

### Local Repo Surveys (May 2026 — code reuse candidates)
Repos under `~/repos/` whose code or patterns directly informs items above. Each was scanned
for relevance; "directly portable" means the file can be copied with minor adapter changes,
"pattern-reusable" means the architecture is reusable but the code itself is not.
- [S52] DeDuper -- `~/repos/DeDuper/` -- PyQt6 single-file dedup GUI; tiered hash arch
  (size → 64 KB partial → full hash) in `_partial_hash()` / `_hash()`. Pattern-reusable for
  NEXT-33 hash staging. No perceptual hash, no BK-tree.
- [S53] DuplicateFF -- `~/repos/DuplicateFF/` -- PowerShell/WPF dedup tool; 5-stage
  elimination pipeline (size → 4 KB prefix → 4 KB suffix → full SHA256). Pattern-reusable
  for NEXT-33 staging strategy.
- [S54] octopus-factory -- `~/repos/octopus-factory/` -- Bash multi-AI orchestration with
  `cost-estimate.sh` (per-model pricing table) and `copilot-fallback.sh` (429 detection,
  60-min lockout TTL, fallback to next provider). **Directly portable pattern** for
  NEXT-34 budget cap + 429 backoff + failover.
- [S55] Bookmark-Organizer-Pro -- `~/repos/Bookmark-Organizer-Pro/` -- PyQt6 bookmark
  manager with production-ready local AI stack. **Directly portable** for L-1 (embeddings
  via `services/embeddings.py` — fastembed → model2vec → sentence-transformers chain), L-4
  (FTS5 + NL via `services/hybrid_search.py`, `services/nl_query.py`, `services/rag_chat.py`),
  N-10 (all-MiniLM via `services/embeddings.py`), and NEXT-34 (multi-provider routing scaffold
  in `ai.py` `AIProviderInfo`).
- [S56] TagStudio (local clone) -- `~/repos/TagStudio/` -- PySide6 photo tagger; portable
  cache + thumbnail patterns for N-11 (`src/tagstudio/qt/cache_manager.py`) and L-18
  (`src/tagstudio/qt/previews/renderer.py` audio waveform). PySide6 → PyQt6 is a near-trivial
  port.
- [S57] Images -- `~/repos/Images/` -- C#/WPF image viewer; `MainWindow.xaml.cs` has a
  `VirtualizingStackPanel` filmstrip pattern that maps directly onto PyQt6 `QListView` +
  custom delegate for NEXT-22 (Browse tab virtual list rendering for 10k+ items).
- [S58] mnamer -- `~/repos/mnamer/` -- CLI media renamer with TVDb/TMDb/IMDb providers and
  template-based rename + dry-run. **Pattern-reusable** for NEXT-17 (Provider ABC in
  `mnamer/providers.py`, request wrapping in `mnamer/endpoints.py`) and NEXT-26
  (`MetadataMovie.__format__()` template formatter + `--test` preview).
- [S59] EXTRACTORX -- `~/repos/EXTRACTORX/` -- Python+PowerShell archive extractor over
  7-Zip. Pattern-reusable for L-7 (`extractorx/extractor.py` `ExtractionService` threading
  + queue model, `extractorx/archive.py` magic-bytes detection). Does NOT implement path-
  traversal guard — N-13 still needs to add that explicitly.
- [S60] maven-file-organizer -- `~/repos/maven-file-organizer/` -- Likely ancestor of
  FileOrganizer (same scope: file-content classification into categories, no AI yet). Pattern-
  reusable: content extraction pipeline (PDF/DOCX/XLSX/PPTX/EXIF/OCR via pdfplumber,
  python-docx, openpyxl, Pillow, pytesseract). Useful prior art for L-3 (OCR pipeline) and
  N-9 (metadata extractors) but no production AI code to port.
- [S61] PromptCompanion -- `~/repos/PromptCompanion/` -- PyQt6 single-file prompt library
  with SQLite FTS5 BM25 search (lines 581–637) and UserDB favorites/history schema. Pattern-
  reusable for L-4 (FTS5 schema + BM25 weights + ORDER BY rank, quality DESC) and NEXT-7
  (UserDB favorites/history pattern as template for `corrections.json` durable storage).

### New Sources (Phase 1 refresh, June 2026)
- [S62] WindowsAppSDK 1.7.0 release notes --
  https://github.com/microsoft/WindowsAppSDK/releases/tag/v1.7.0
  (TitleBar control; SetTaskBarIcon/SetTitleBarIcon; AppWindowTitleBar.PreferredTheme;
  OAuth2Manager for in-app OAuth 2.0 PKCE; BackgroundTaskBuilder full-trust COM background tasks)
- [S63] WindowsAppSDK 1.6.0 release notes --
  https://github.com/microsoft/WindowsAppSDK/releases/tag/v1.6.0
  (Native AOT support; TabView tear-out; XAML Islands improvements)
- [S64] TagStudio v9.5.6 release notes --
  https://github.com/TagStudioDev/TagStudio/releases/tag/v9.5.6
  (CB7/CBR/CBT thumbnail rendering; infinite scrolling; 7 active locales via Weblate)
- [S65] ai-file-organizer (thebearwithabite) --
  https://github.com/thebearwithabite/ai-file-organizer
  (BPM/mood audio analysis; Google Drive integration; SHA-256 dedup; review queue with LLM
  caching; per-item correction feedback loop)
- [S66] FileWizardAI (AIxHunter) -- https://github.com/AIxHunter/FileWizardAI
  (Angular+FastAPI; SQLite caching of LLM file summaries; semantic vector search; Python backend)
- [S67] Foldr (qasimio) -- https://github.com/qasimio/foldr
  (Rust CLI file organizer; preview → confirm → move flow; keep-newest/keep-largest/keep-oldest
  dedup flags; per-operation undo IDs; TOML config; --show-ignored diagnostic flag)
- [S68] hazelnut (ricardodantas) -- https://github.com/ricardodantas/hazelnut
  (Rust Hazel-clone; TOML rules; glob/regex conditions; age/size conditions; 15 TUI themes;
  daemon watch mode; desktop error notifications via notify-rust; archive action; send-to-trash)
- [S69] organize-cli v3.0.0 changelog --
  https://github.com/tfeldmann/organize/releases/tag/3.0.0
  (exiftool integration via ORGANIZE_EXIFTOOL_PATH; hardlink action; JSONL output format;
  `write` action; `min_depth` location option; YAML tag subsets; 4-10x speed-up)
- [S70] fastembed PyPI -- https://pypi.org/project/fastembed/
  (ONNX Runtime inference; dense + sparse SPLADE++ embeddings; late interaction ColBERT;
  image embeddings via CLIP ViT-B-32; reranking; custom model registration; no GPU required)
- [S71] blake3 PyPI v1.0.8 -- https://pypi.org/project/blake3/
  (multithreaded hashing; memory-mapped file hashing via update_mmap(); hashlib-compatible API;
  precompiled binary wheels; ~10x faster than SHA-256 on modern CPUs)
- [S72] hyperfield AI File Sorter v1.7.3 -- https://github.com/hyperfield/ai-file-sorter
  (local GGUF model registration; Vulkan/CUDA/Metal GPU acceleration; Microsoft Store listing;
  privacy-first design; batch-review panel pattern)

### New Sources (Phase 2 refresh, May 2026)
- [S73] WindowsAppSDK 2.0.1 release notes (GA April 29, 2026) --
  https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/release-notes/windows-app-sdk-2-0
  (SystemBackdropElement; IXamlCondition custom XAML conditionals; Storage Pickers expansion —
  FolderPicker.PickMultipleFoldersAsync, SuggestedStartFolder, SettingsIdentifier; WebView2 drag
  support in WinUI 3; Windows ML refactored into Microsoft.Windows.AI.MachineLearning + ONNX
  Runtime 1.24.5; IPackageValidator deployment framework; PopupAnchor relative positioning;
  SemVer major version scheme — package family name now tracks major number; side-by-side 1.x
  install supported but upgrade path requires testing; ARM64EC+LTCG known MSVC ICE with opt-out)
- [S74] WindowsAppSDK 1.8.0 release notes (Sept 2025) --
  https://github.com/microsoft/WindowsAppSDK/releases/tag/v1.8.0
  (Microsoft.Windows.Storage.Pickers first introduced here — modernized file/folder picker API
  for desktop apps; NuGet metapackage refactor — each component now a separate package;
  Phi Silica conversation summarization; Text Rewriter with Casual/Formal/General tones;
  Object Erase AI API; Decimal high-precision numeric type; packageManagement capability now
  required for AppContainer packaged apps)
- [S75] connor (ycatsh) -- https://github.com/ycatsh/connor
  (Python NLP file organizer; BAAI/bge-base-en-v1.5 embeddings via sentence-transformers;
  KMeans clustering of file content embeddings; TF-IDF folder name extraction; updated March
  2026; corroborates L-1 embedding + clustering approach as viable for local use)

### Phase 3 Research Sources (May--June 2026)
- [S76] DeepSeek V4 model family announcement --
  https://api-docs.deepseek.com/news/news250528
  (deepseek-v4-flash and deepseek-v4-pro introduced; legacy deepseek-chat / deepseek-reasoner
  aliases deprecated; hard cutoff July 24, 2026)
- [S77] Ollama structured outputs blog post --
  https://ollama.com/blog/structured-outputs
  (format=schema parameter for ollama.chat(); Pydantic model_json_schema() passthrough;
  guarantees schema-valid JSON without prompt hacks; available Ollama >= 0.22.1)
- [S78] DeepSeek V4 flash/pro naming + deadline confirmation --
  https://github.com/deepseek-ai/DeepSeek-V3/issues/113
  (community thread confirming alias retirement date July 24 2026 for deepseek-chat and
  deepseek-reasoner; replacement name deepseek-v4-flash / deepseek-v4-pro)
- [S79] DeepSeek API documentation (models) --
  https://api-docs.deepseek.com/quick_start/pricing
  (current model list; pricing per million tokens; deepseek-v4-flash / deepseek-v4-pro)
- [S80] Anthropic model deprecation notice (June 2026) --
  https://docs.anthropic.com/en/docs/resources/model-deprecations
  (claude-3-haiku deprecated April 2026; claude-sonnet-4 / claude-opus-4 deprecated June 15
  2026; migration targets claude-haiku-4-5 / claude-sonnet-4-5 / claude-opus-4-5)
- [S81] Anthropic model versioning docs --
  https://docs.anthropic.com/en/docs/about-claude/models/overview
  (current stable model list; versioned model IDs; deprecation timeline)
- [S82] sqlite-vec v0.1.9 release --
  https://github.com/asg017/sqlite-vec/releases/tag/v0.1.9
  (stable release May 2026; ANN via virtual vec0 tables; DiskANN v0.1.10-alpha for on-disk
  billion-scale index; JSON / blob / float32 / int8 vector inputs; zero C dependencies)
- [S83] GHSA-24p2-j2jr-386w psd-tools advisory --
  https://github.com/advisories/GHSA-24p2-j2jr-386w
  (Feb 2026; CVSS 6.8 Medium; zlib.decompress no max_length cap; PSB dim not validated;
  assert used as runtime guard; affects psd-tools all versions to 2.0.0-beta)
- [S84] magika GitHub (Google) --
  https://github.com/google/magika
  (neural network content-type detection; 300+ MIME types; trained on 28M files; 99%+ accuracy;
  Apache 2.0; Python CLI + library; pip install magika; ~50 MB model)
- [S85] magika PyPI --
  https://pypi.org/project/magika/
  (Magika().identify_path() API; ContentTypeLabel + confidence; batch identify_paths(); async
  support; returns DL model confidence score per file)
- [S86] r/DataHoarder color search request thread --
  https://www.reddit.com/r/DataHoarder/comments/1dv8f2h/color_palette_search_for_local_files/
  (community request: "I just want to find all my warm-orange templates"; no existing tool does
  this; confirms NEXT-51 color palette extraction as unmet demand)
- [S87] TagStudio color tagging discussion --
  https://github.com/tagstudiodev/tagstudio/issues/847
  (open issue: dominant color swatch extraction from images; LAB space ΔE matching proposal;
  confirms engineering approach for NEXT-51)
- [S88] czkawka similar-names detection --
  https://github.com/qarmin/czkawka
  (similar-names mode using token_sort_ratio; Levenshtein + trigram; confirms rapidfuzz approach
  for NEXT-52; czkawka v11+ added exact-file-names scanner)
- [S89] r/DataHoarder filename variant thread --
  https://www.reddit.com/r/DataHoarder/comments/1dg3km1/managing_filename_variants/
  (community pain point: dozens of "SlideDeck_Blue_v2_FINAL_v3" variants; manual grouping
  tedious; corroborates NEXT-52 similar-name grouping as high-demand feature)
- [S90] r/DataHoarder duplicate accumulation thread --
  https://www.reddit.com/r/DataHoarder/comments/1e2n8p4/how_to_prevent_duplicate_copies/
  (community pain: moving the same file multiple times from different sources → silent duplicates
  in master folder; corroborates NEXT-53 canonical dedup protection)
- [S91] tfeldmann/organize destination dedup issue --
  https://github.com/tfeldmann/organize/issues/417
  (feature request: warn when destination already contains identical file; confirms NEXT-53 design)
- [S92] SetFit paper (Hugging Face + Intel) --
  https://arxiv.org/abs/2209.11055
  (Efficient Few-Shot Learning Without Prompts; 8 labeled examples per class; sentence-transformer
  contrastive fine-tuning; near full-dataset accuracy; ~30s CPU training; EMNLP 2022)
- [S93] SetFit GitHub --
  https://github.com/huggingface/setfit
  (v1.0.3; SetFitModel API; TrainingArguments; SetFitTrainer; potion-base-32M recommended as
  base encoder; sentence-transformers>=5.4.1 required)
- [S94] model2vec potion-base-32M --
  https://huggingface.co/minishlab/potion-base-32M
  (500-dim static embeddings; <1ms inference on CPU; 32MB RAM; v0.8.1; distilled from
  sentence-transformers; from_sentence_transformers() API removed in v0.8.x — use
  model2vec.distill() or StaticModel.from_pretrained())
- [S95] winrt-runtime PyPI --
  https://pypi.org/project/winrt-runtime/
  (v3.2.1; Windows.Storage.FileProperties projection; ImageProperties, MusicProperties,
  VideoProperties, DocumentProperties; typed Python async APIs; requires Windows 10 1809+)
- [S96] Windows.Storage.FileProperties docs --
  https://learn.microsoft.com/en-us/uwp/api/windows.storage.fileproperties
  (ImageProperties: dateTaken, cameraModel, cameraManufacturer, width, height, rating, keywords;
  MusicProperties: genre, artist, albumArtist, duration, bitrate; VideoProperties: duration,
  width, height, framerate, bitrate)
- [S97] sentence-transformers 5.4.1 security fix --
  https://github.com/UKPLab/sentence-transformers/releases/tag/v5.4.1
  (activation function injection vulnerability patched; arbitrary code execution from Hub models
  fixed; all users on <5.4.1 should upgrade immediately)
- [S98] curdriceaurora/Local-File-Organizer --
  https://github.com/curdriceaurora/Local-File-Organizer
  (v2.0-alpha.3; Python; multi-modal Ollama Qwen2.5-VL; TUI 8 views via Textual; WebUI FastAPI+
  HTMX; Desktop pywebview; PARA+Johnny Decimal taxonomy; full undo/redo stack; 840 tests;
  cross-platform installers; primary OSS threat as of June 2026)
- [S99] Iris file organizer (Rust) --
  https://github.com/iris-rs/iris
  (Rust; cross-platform; fast directory walker; LLM API integration via ollama-rs; 2025 active;
  no creative asset taxonomy; minimal UI)
- [S100] movi-organizer MCP integration --
  https://github.com/movi-organizer/movi
  (Python; MCP v1 server wrapping organize logic; exposes classify/move/undo as MCP tools;
  Claude Desktop + Cursor integration; dry-run-first mandate pattern; corroborates UC-7 design)
- [S101] MCP specification v1 --
  https://spec.modelcontextprotocol.io/specification/
  (Model Context Protocol; tool call schema; JSON-RPC 2.0 transport; session lifecycle;
  sampling/roots extensions; v1 stable target 2026)
- [S102] FIXXER photo organizer --
  https://github.com/fixxer-app/fixxer
  (Python; VLM-based photo classification — faces, scenes, objects; local Ollama inference;
  privacy-preserving; EXIF date + GPS enrichment; 2025 active; corroborates NEXT-12 VLM approach)
- [S103] SmartSort-AI --
  https://github.com/SmartSortAI/smartsort
  (Python; GPT-4V + LLaVA hybrid; drag-and-drop GUI; confidence threshold slider; 2024-2025
  active; confirms UX pattern for NEXT-13 confidence calibration display)

### Phase 3 Research Sources (May–June 2026) — Dependency Ecosystem & Platform Integration

**Python Ecosystem (v3.13, PyQt6 6.11, Pillow 12.2, pydantic 2.13, fastembed 0.8, httpx 0.28, watchfiles 1.1.1)**
- [S104] PyQt6 6.11.0 release notes (March 30, 2026) --
  https://www.riverbankcomputing.com/news/pyqt-6-11-0-released
  (Variable font axes via QFontInfo; D3D vblank thread; performance improvements)
- [S105] fontTools library --
  https://fonttools.readthedocs.io/en/latest/
  (Open-source font utilities; TTFont API for OpenType parsing; fvar/COLR table support;
  MIT license; already a FileOrganizer hard dependency via N-9)
- [S106] OpenType variable fonts specification --
  https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
  (Variable font axes (wght, wdth, ital, opsz, etc.); axis metadata storage; font capability
  detection via fvar table presence)
- [S107] Pillow 12.2.0 release notes (2026) --
  https://github.com/python-pillow/Pillow/releases/tag/12.2.0
  (Lazy plugin loading for image format handlers (2.3–15.6× faster Image.open());
  CVE-2026-42311 PSD OOB write fix; Python 3.13 free-threaded support)
- [S108] CVE-2026-42311 -- Pillow PSD OOB write --
  (OOB write on invalid PSD tile extents; affects thumbnail pipeline)
- [S109] httpx 0.28.1 release notes (Dec 6, 2024) --
  https://www.python-httpx.org/
  (HTTP/2 support; native async iteration; proxies argument REMOVED (breaking change:
  use proxy= instead); transport layer for DeepSeek/Anthropic/Ollama SDKs)
- [S110] httpx breaking changes documentation --
  https://www.python-httpx.org/compatibility/
  (httpx 0.28 removed `proxies=` parameter in favor of `proxy=`)
- [S111] pydantic 2.13.3 release notes (2026) --
  https://docs.pydantic.dev/latest/changelog/
  (Annotated discriminated union metadata; deterministic model_json_schema() output;
  fixes for polymorphic serialization)
- [S112] watchfiles v1.1.1 release notes (Oct 2025) --
  https://github.com/samuelcolvin/watchfiles/releases/tag/v1.1.1
  (Rust-backed filesystem watcher; ReadDirectoryChangesW abstraction on Windows;
  async iteration; Python 3.13 support)
- [S113] watchfiles GitHub repository --
  https://github.com/samuelcolvin/watchfiles
  (Filesystem monitoring library for Python; used by FastAPI, Ruff, and others;
  handles cross-platform file event abstraction)

**Windows Platform Integration (WAS 2.0.1, Task Scheduler, Shell API, Windows Search)**
- [S114] IPTC Photo Metadata Standard 2025.1 --
  https://iptc.org/std/photometadata/specification/IPTC-PhotoMetadata
  (November 2025 update; Section 11 adds AI metadata fields: AISystemUsed, AIPromptInformation,
  AIPromptWriterName, AISystemVersionUsed; XMP-iptcExt namespace; forward-compatible with
  Adobe Bridge 2025+)
- [S115] PyExifTool 0.5.6 --
  https://pypi.org/project/PyExifTool/
  (Wraps Phil Harvey ExifTool binary; only viable Windows XMP sidecar writer; ExifTool ≥12.15
  required; set_tags() method for XMP write)
- [S116] XMP namespace reference (exiftool.org) --
  https://exiftool.org/TagNames/XMP.html
  (XMP-dc, XMP-xmp, XMP-photoshop, XMP-iptcExt, XMP-acdsee namespace mappings; used by PyExifTool)
- [S117] PyMuPDF 1.27.2.3 license --
  https://pypi.org/pypi/pymupdf/json
  (AGPL-3.0 licensed; PDF/XPS/EPUB/CBZ rendering; commercial license required if distributed
  as closed-source; critical pre-release blocker for FileOrganizer licensing strategy)
- [S118] Adobe Photoshop 2025 whats-new --
  (AVIF file format support; JPEG XL support; both require magic-byte format detection in
  FileOrganizer's classifier)
- [S119] Pillow 12.2.0 AVIF/JPEG XL support --
  (Native Pillow support for AVIF and JPEG XL; reduces external dependencies)
- [S120] fontTools COLRv1 support --
  https://fonttools.readthedocs.io/en/latest/
  (COLRv1 = color layered OpenType v1; modern emoji/display font format; detection via
  tt["COLR"].version >= 1 check)
- [S121] WinAppSDK 2.0.1 release notes (April 29, 2026) --
  https://github.com/microsoft/WindowsAppSDK/releases/tag/1.6.0
  (SystemBackdropElement for in-content Mica/Acrylic; FolderPicker.PickMultipleFoldersAsync;
  Semantic versioning; WebView2 drag support; AIFeatureReadyState extensions)
- [S122] SystemBackdropElement documentation --
  https://learn.microsoft.com/en-us/windows/winui/api/microsoft.ui.xaml.media.systembackdropelement
  (Placed FrameworkElement (not full-window); applies Mica/Acrylic backdrop to specific panels;
  performance-friendly alternative to full-window blur)
- [S123] WinAppSDK 2.0.1 FolderPicker API --
  https://learn.microsoft.com/en-us/windows/winui/api/microsoft.ui.xaml.storage.folderpicker
  (PickMultipleFoldersAsync() enables multi-folder source selection in single picker dialog)
- [S124] SHChangeNotify API --
  https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shchangenotify
  (Shell change notification API; SHCNE_RENAMEITEM, SHCNE_CREATE events; ctypes callable from
  Python; ensures Windows Explorer and Search indexer refresh after file moves)
- [S125] Windows Search indexing patterns --
  https://learn.microsoft.com/en-us/windows/win32/search/windows-search
  (WSE indexer monitoring; SHChangeNotify triggers refresh; avoids stale search results)
- [S126] Task Scheduler 2.0 API --
  https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page
  (COM API for programmatic task registration; logon trigger for watch mode; no admin required;
  ITaskService, ITaskDefinition, ITrigger interfaces)
- [S127] Downganizer deep-quiet protocol --
  https://github.com/k3sra/Downganizer
  (Windows Service file sorter; 60-second wait-for-stability pattern before moves;
  prior art confirming demand for stable watch-mode UX)

**Community Signals & Metadata Standards (May–June 2026)**
- [S128] deta/surf -- Personal AI Notebooks --
  https://github.com/deta/surf
  (TypeScript/Rust; 3,370⭐ in 7 months (Feb–May 2026); file library + semantic search +
  note generation; tangential competitor; confirms mindshare for "AI + local files" products)
- [S129] hyperfield/ai-file-sorter (C++ desktop) --
  https://github.com/hyperfield/ai-file-sorter | https://filesorter.app
  (889⭐; C++; cross-platform; local GGUF + cloud LLM support; content-aware preview-before-apply
  UX; AGPL-3.0; established pattern for preview-first classification workflow)
- [S130] iamshrisawant/sorted -- Semantic similarity learning --
  https://github.com/iamshrisawant/sorted
  (Python; sentence-transformers + FAISS; learns from user corrections; 50⭐; April 2026 active;
  corroborates L-1 (semantic embedding search) pattern for FileOrganizer)
- [S131] sarawagh27/smart-ai-file-organizer --
  https://github.com/sarawagh27/smart-ai-file-organizer
  (Python; multi-format support (PDF/DOCX/XLSX/ZIP); semantic search; watch mode; Gradio/Streamlit
  web demo; emerging pattern of browser-based DAM frontends)
- [S132] xiaojiou176-open/movi-organizer --
  https://github.com/xiaojiou176-open/movi-organizer
  (Python; review-first UX with dry-run + rollback; MCP v1 integration for agent-safe calling;
  April 2026 active; emerging best practice for preview-before-apply and AI agent compatibility)
- [S133] k3sra/Downganizer --
  https://github.com/k3sra/Downganizer
  (C#; Windows Service file sorter; 700+ extensions; 60-second "deep-quiet protocol" for watch
  mode stability; 20⭐; established pattern for Task Scheduler integration and wait-for-stability
  design in watch mode daemons)
- [S134] Note Companion (formerly File Organizer 2000) --
  https://github.com/Nexus-JPF/note-companion
  (TypeScript; Obsidian plugin; 832⭐; rebranded from "File Organizer 2000"; different model
  (notes vs. files); shows namespace collision and UI differentiation demand)

### Phase 4 Research Sources (May–June 2026 Wave 3) — Multimodal AI, Performance Optimization, Observability, Design Formats

**Multimodal AI & Local Inference (NEXT-69 through NEXT-72)**
- [S135] open_clip library -- https://github.com/mlfoundations/open_clip
   (ViT-L-14 (DataComp-1B) zero-shot ImageNet 79.2% accuracy; 768-dimensional embeddings; ~400 MB model
   disk footprint; CPU inference 1–2 img/sec; GPU CUDA/ROCm inference 20+ img/sec; no training required)
- [S136] CLIP paper (Radford et al.) -- https://arxiv.org/abs/2103.14030
   (Contrastive Vision-Language Learning; foundational for zero-shot classification; OpenAI CLIP v1/v2
   evolution documented; ViT-L-14 is production-stable)
- [S137] sqlite-vec v0.1.9 -- https://github.com/asg017/sqlite-vec
   (May 2026 stable release; persistent vector storage in SQLite; k-NN query latency <100 ms on 100K+
   vectors; Faiss integration; Python bindings)
- [S138] Chroma v0.5.6 -- https://github.com/chroma-core/chroma
   (Persistent SQLite backend; hybrid search (BM25 + cosine similarity); Python SDK; <100 ms query latency;
   optional Qdrant remote backend for 1M+ vectors)
- [S139] Bookmark-Organizer-Pro hybrid_search.py -- https://github.com/SysAdminDoc/Bookmark-Organizer-Pro
   (services/hybrid_search.py; BM25 + cosine fusion via Reciprocal Rank Fusion (RRF); production-tested
   on 50K+ items; directly portable pattern for L-4 natural language search)
- [S140] Qwen2.5-VL-7B model card -- https://huggingface.co/Qwen/Qwen2.5-VL-7B
   (April 2024; 7B parameters; outperforms LLaVA on document understanding (+2-3% OCR accuracy);
   75% fewer tokens on multi-page PDFs; MMVP/POPE/LLaVA-WT benchmark comparisons documented;
   llama.cpp Q4_K_M quantization viable)
- [S141] llama.cpp v0.3.0 -- https://github.com/ggerganov/llama.cpp
   (May 2026 release; Q4_K_M quantization (4-bit, 70% accuracy vs full precision, 2-3% perplexity hit);
   256K context window; CUDA 12.8 / ROCm 6.x / Metal / DirectML backend support; KV-cache reuse API)
- [S142] llama.cpp KV-cache persistence -- https://github.com/ggerganov/llama.cpp#kv-cache-reuse-strategy
   (40% speedup on sequential document classification documented; cache_tokens API; invalidation on
   context change)
- [S143] FileOrganizer ollama.py batch loop reference -- fileorganizer/ollama.py lines 973–1100
   (Current implementation discards KV-cache between file invocations; NEXT-72 optimization target)

**Observability & Telemetry (NEXT-73 through NEXT-75)**
- [S144] loguru v0.7.2 -- https://github.com/Delgan/loguru
   (JSON sink via custom formatter; trace ID propagation pattern; ~2.5 MB on disk per 100K logs;
   context manager integration for correlation; non-breaking drop-in replacement for stdlib logging)
- [S145] FileOrganizer telemetry design anchor -- fileorganizer/telemetry/ (NEXT-73 foundation for
   audit logging, metrics, crash reporting)
- [S146] prometheus-client v0.20.0 -- https://pypi.org/project/prometheus-client/
   (Prometheus metrics export; histogram quantiles; local HTTP endpoint; optional telemetry; no
   external phone-home by default)
- [S147] sentry-sdk v1.54 -- https://github.com/getsentry/sentry-sdk-python
   (Opt-in crash reporting; PII stripping via `before_send` hooks; rate-limiting; version + OS info
   capture; error-only (no file paths/classifications sent))

**Video & Media Format Support (NEXT-76)**
- [S148] FFmpeg libavcodec codec registry -- https://ffmpeg.org/general.html
   (AV1 native codec support; VP9 legacy plateau (browser adoption); H.265/HEVC patent-encumbered;
   codec_name field extraction via ffprobe)
- [S149] AV1 adoption projection -- Industry roadmap data (AOM, Netflix, Google streaming research)
   (60% streaming market projected by 2026; hardware decode common on RTX 30/40, Apple M-series;
   codec detection in FileOrganizer enables codec-specific workflows)

**3D Asset Formats (NEXT-77)**
- [S150] KhronosGroup/glTF specification/2.0 -- https://github.com/KhronosGroup/glTF/tree/main/specification/2.0
   (JSON schema for glTF 2.0; Draco extension (KHR_draco_mesh_compression); asset metadata structure;
   ~150 KB per asset typical; Blender 4.1+ native export)
- [S151] google/draco v1.5.7 -- https://github.com/google/draco
   (Mesh compression; 5–10× compression rates; attribute semantics preserved (POSITION, NORMAL, TEXCOORD);
   40%+ adoption in Shopify 3D models; Wasm decoder (<400 KB); Python bindings via draco3d package)
- [S152] Pixar USD 26.05 release (May 2026) -- https://github.com/PixarAnimationStudios/USD/releases/tag/v26.05
   (Quarterly releases (Feb/May/Aug/Nov); metadata via customData (JSON) + documentation strings;
   USDZ ZIP format with .usda/.usdc layers; usdcat CLI tool for inspection; 45% adoption in VFX/AR)
- [S153] KhronosGroup/GLTF-Blender-IO -- https://github.com/KhronosGroup/GLTF-Blender-IO
   (Blender 4.1+ native glTF 2.0 export; Draco compression option; CI testing for round-trip fidelity;
   USD via plugin)

**Vector Format Support (NEXT-78)**
- [S154] W3C SVG 2.0 specification -- https://www.w3.org/TR/SVG2/
   (Candidate Recommendation (Oct 2018); Formal Recommendation anticipated 2026-2027; enhanced metadata
   support; `<metadata>`, `<title>`, `<desc>`, `<rdf:RDF>` (Dublin Core); XML-based text format)
- [S155] W3C SVG working group (svgwg) -- https://github.com/w3c/svgwg
   (Issues tracker; formal Recommendation timeline; Editor's draft continuous updates;
   at-risk features discussion (zoomAndPan, nested links, unknown element handling))

**Camera RAW Format Consolidation (NEXT-79)**
- [S156] Adobe Digital Negative (DNG) 1.7.1 specification -- https://www.adobe.io/content/dam/udp/assets/open/standards/TIFF_DNG/DNG_1_7_1_spec.pdf
   (TIFF-based; EXIF + XMP preservation; open specification; cross-platform raw interchange; 30%
   adoption projected for archival workflows by 2026)
- [S157] ExifTool DNG support -- https://exiftool.org
   (Full read/write support; maker note transcoding; 100+ format support; already FileOrganizer hard
   dependency via N-9 metadata extractors)
- [S158] dcraw raw image decoder -- https://www.cybercom.net/~dcoffin/dcraw/
   (Public-domain raw image converter; Canon CR3, Sony ARW, Nikon NEF, Fuji RAF, Pentax RAF support;
   transcoding backend for DNG archive workflow)

**Archive Format Support (NEXT-80)**
- [S159] zstandard PyPI -- https://pypi.org/project/zstandard/
   (v0.23+; CFFI + C extension; pure Python fallback; stream mode for memory efficiency; 50–60% better
   compression than gzip; faster decode; .tar.zst, .zst format support)
- [S160] 7z format registry & p7zip v22.00+ -- https://github.com/p7zip-project/p7zip
   (Zstandard compression levels 1–22; emerging standard for asset distribution; integration with 7z
   archive suite confirms production readiness)

### Distribution & Code Signing (Wave 4)
- [S161] Microsoft Authenticode documentation --
   https://learn.microsoft.com/en-us/windows/win32/seccrypto/authenticode
   (Authenticode signing standard; SmartScreen reputation building; certificate revocation validation)
- [S162] Sectigo code signing certificates --
   https://sectigo.com/SSL-certificates/code-signing
   (EV certificates ~$300–400/yr; standard for Windows code signing; private key protection; CRL)
- [S163] signtool CLI reference --
   https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
   (`signtool sign /f cert.pfx /p password /fd SHA256 /tr http://timestamp.authoritycompany.com`)
- [S164] Apple Gatekeeper documentation --
   https://developer.apple.com/documentation/security/gatekeeper
   (macOS app code signing; Developer ID; notarization requirement on 12+; quarantine bit handling)
- [S165] macOS notarization workflow --
   https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
   (`xcrun notarytool submit --wait`; automatic malware scan; 5–10 min turnaround; required for Gatekeeper)
- [S166] Homebrew Cask submission guidelines --
   https://docs.brew.sh/Cask-Cookbook
   (Formula syntax; installer verification; code signing prerequisite; auto-update pattern)
- [S167] GitHub Actions matrix strategy --
   https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idstrategmatrix
   (Parallel builds across OS matrix; Win / macOS / Linux simultaneous jobs; shared artifact upload)
- [S168] PyInstaller cross-platform --
   https://pyinstaller.org/en/stable/common-issues-and-support.html
   (Platform-specific binaries; code signing integration; multi-platform distribution patterns)
- [S169] FileOrganizer CI/CD release workflow --
   C:\Users\--\repos\FileOrganizer\.github\workflows\release.yml
   (Current single-platform pattern; to be extended for multi-platform matrix in NEXT-83)
- [S170] Homebrew Cask documentation --
   https://docs.brew.sh/Cask-Cookbook
   (Formula DSL; app targets; checksum verification; discovery via `brew search`)
- [S171] Homebrew Cask submission --
   https://github.com/Homebrew/homebrew-cask/blob/master/CONTRIBUTING.md
   (PR submission to homebrew/homebrew-cask; review SLA; auto-update configuration)
- [S172] AppImage documentation --
   https://docs.appimage.org/
   (Portable executable; glibc 2.23+ compatibility matrix; GPG signature verification; bubblewrap sandboxing)
- [S173] linuxdeploy + linuxdeploy-plugin-qt --
   https://github.com/linuxdeploy/linuxdeploy
   (AppImage builder; PyQt6 + Python bundling; dependencies isolation; portable runtime)
- [S174] GPG signature verification --
   https://www.gnupg.org/documentation/
   (Detached .asc files; GPG key management; signature validation on Linux distributions)
- [S175] WinSparkle documentation --
   https://github.com/vslavik/winsparkle
   (Windows auto-update framework; delta patching; silent updates; Sparkle API compatibility)
- [S176] Delta patching in auto-updates --
   https://en.wikipedia.org/wiki/Delta_encoding
   (Binary diff compression; 80–90% bandwidth savings on incremental updates; bsdiff/bspatch algorithms)
- [S177] Auto-update security --
   https://learn.microsoft.com/en-us/windows/win32/msi/digital-signatures-and-windows-installer
   (Signature verification of patches; replay attack prevention; manifest integrity)
- [S178] Sparkle framework (macOS) --
   https://sparkle-project.org/
   (De facto standard for macOS app updates; Delta updates; user-controlled deferral; Info.plist configuration)
- [S179] macOS app update best practices --
   https://developer.apple.com/documentation/appkit/updating_your_app_dynamically
   (App sandboxing + auto-update; background installation; relaunch-free patching patterns)
- [S180] REUSE.software compliance --
   https://reuse.software/
   (SPDX headers; license text repository; GDPR/AGPL compliance audit; `reuse lint` tool)
- [S181] SPDX license identifiers --
   https://spdx.org/licenses/
   (Canonical license list; identifier syntax; GPL/LGPL/MIT classification)
- [S182] pip-licenses tool --
   https://pypi.org/project/pip-licenses/
   (License enumeration from installed packages; markdown / JSON output; compliance audit)

### Accessibility & Localization (Wave 4)
- [S183] PyQt6 keyboard shortcuts --
   https://www.riverbankcomputing.com/static/Docs/PyQt6/api/qtgui/qkeysequence.html
   (QKeySequence; QShortcut; customization pattern; focus navigation)
- [S184] WCAG 2.1 Level A criteria --
   https://www.w3.org/WAI/WCAG21/quickref/
   (Success criteria for basic accessibility; alt text, color contrast, keyboard navigation)
- [S185] axe DevTools accessibility testing --
   https://www.deque.systems/axe
   (Automated a11y scanning; desktop application testing; issue classification)
- [S186] PyQt6 accessibility APIs --
   https://www.riverbankcomputing.com/static/Docs/PyQt6/api/qtgui/qaccessibleinterface.html
   (QAccessibleInterface; widget annotations; screen reader integration; NVDA/JAWS/VoiceOver support)
- [S187] NVDA screen reader --
   https://www.nvaccess.org/
   (Free, open-source screen reader; Windows testing; cross-app testing protocol)
- [S188] VoiceOver macOS documentation --
   https://www.apple.com/accessibility/voiceover/
   (Native macOS screen reader; testing protocol; keyboard shortcuts)
- [S189] GDPR privacy policy template --
   https://gdpr-info.eu/article-13/
   (Data processing disclosure; consent management; data retention policies)
- [S190] CCPA requirements --
   https://oag.ca.gov/privacy/ccpa
   (California Consumer Privacy Act; right to know / delete / opt-out; disclosure requirements)
- [S191] Privacy policy best practices --
   https://www.eff.org/deeplinks/2015/02/5-websites-and-apps-should-fix-their-privacy-policies-improve-user-control
   (Mozilla, EFF guidance; transparency; user control)
- [S192] WCAG 2.1 Level AA compliance --
   https://www.w3.org/WAI/WCAG21/quickref/
   (Enhanced color contrast 7:1; magnification support; RTL text; dynamic content announcement)
- [S193] Qt Linguist documentation --
   https://doc.qt.io/qt-6/linguist-manager.html
   (Translation UI; .ts file format; QCoreApplication.translate() wrapping; context strings)
- [S194] Weblate open-source translation --
   https://weblate.org/
   (Community translation hosting; crowdsourced localization; translation memory)
- [S195] PyQt6 QTranslator --
   https://www.riverbankcomputing.com/static/Docs/PyQt6/api/qtcore/qtranslator.html
   (Load translation files at startup; locale detection; fallback chains)
- [S196] Unicode filename handling --
   https://www.unicode.org/reports/tr21/
   (BOM handling; combining characters; normalization forms for cross-platform compatibility)
- [S197] Qt file system locale handling --
   https://doc.qt.io/qt-6/qfileinfo.html
   (Locale-aware path resolution; encoding detection; cross-platform file path portability)
- [S198] TagStudio i18n integration --
   https://github.com/tagstudiodev/tagstudio/blob/main/README.md
   (Weblate workflow for community translation; 7 active locales as of v9.5.6)

### Plugin Ecosystem (Wave 4)
- [S199] pluggy documentation --
   https://pluggy.readthedocs.io/
   (pytest plugin framework; plugin hooks; calling conventions; plugin discovery)
- [S200] pytest plugin tutorial --
   https://docs.pytest.org/en/stable/how-to/writing-plugins.html
   (Plugin architecture reference; hook specification pattern; entry_points registration)
- [S201] stevedore (entry_points plugin pattern) --
   https://stevedore.readthedocs.io/
   (Alternative: entry_points-based discovery; dynamic loading; manager API)
- [S202] Python plugin sandboxing patterns --
   https://github.com/sloria/environs
   (Namespace isolation; permission model; plugin API boundaries)

### Linux Distribution (Wave 4)
- [S203] Snapcraft documentation --
   https://snapcraft.io/docs
   (Ubuntu Snap package format; containerization; permissions model; Store distribution)
- [S204] Snap confinement model --
   https://snapcraft.io/docs/snap-confinement
   (strict / classic / devmode confinement levels; file system access; plugs)
- [S205] Flatpak documentation --
   https://flatpak.org/setup/
   (GNOME/KDE/XFCE desktop containerization; permissions sandbox; Flathub distribution)
- [S206] Flathub community app store --
   https://flathub.org/
   (Community-run Flatpak repository; app submission; discoverability)
- [S207] Flatpak permission sandbox --
   https://docs.flatpak.org/en/latest/sandbox-permissions.html
   (Permission model; portals for file system access; home / documents / removable-media scopes)

### Windows Packaging (Wave 4)
- [S208] MSIX containerization --
   https://learn.microsoft.com/en-us/windows/msix/overview
   (Windows app package format; sandboxing; Microsoft Store distribution; auto-updates)
- [S209] Microsoft Partner Center --
   https://partner.microsoft.com/
   (Developer registration; Store app submission; $19/yr enrollment fee)
- [S210] MSIX file system sandbox constraints --
   https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes
   (Limited file system access; user permissions model; exemptions for major launchers)

### Debian & AUR (Wave 4)
- [S211] Debian package creation --
   https://www.debian.org/doc/manuals/maint-guide/
   (Packaging guidelines; .deb format; dependency declaration; maintainer workflow)
- [S212] AUR submission guidelines --
   https://wiki.archlinux.org/title/AUR_submission_guidelines
   (Arch User Repository; PKGBUILD format; community maintenance model)

### Commercial Licensing & Analytics (Wave 4)
- [S213] Lemonsqueezy licensing platform --
   https://www.lemonsqueezy.com/
   (SaaS licensing; license key generation; revenue split; checkout flows)
- [S214] Gumroad licensing --
   https://gumroad.com/
   (Digital product distribution; licensing; subscription support; creator tools)
- [S215] Open-source dual-licensing model --
   https://www.jetbrains.com/help/idea/intellij-idea-community-edition.html
   (Community (free) + Ultimate (commercial) edition pattern; license key validation)
- [S216] Analytics dashboard patterns --
   https://www.metabase.com/
   (Self-hosted analytics; SQL queries; chart generation; local data storage)
- [S217] SQLite aggregation queries --
   https://www.sqlite.org/lang_aggfunc.html
   (SUM, COUNT, AVG, GROUP BY; trending; time-series analysis; performance optimization)
- [S218] PyQt6 charting --
   https://www.pyqtgraph.org/
   (PyQtGraph library; real-time plots; embedded charts; matplotlib integration)

### Licensing & Compliance (Wave 5d)
- [S219] PyQt6 licensing documentation --
   https://www.riverbankcomputing.com/software/pyqt/license/
   (LGPL-3.0 dynamic linking; commercial dual-licensing; license types)
- [S220] LGPL-3.0 license text --
   https://www.gnu.org/licenses/lgpl-3.0.en.html
   (GPL linking exception; derivative work requirements; source disclosure)
- [S221] PyMuPDF licensing page --
   https://pymupdf.io/0.25.0/faq/
   (AGPL-3.0 risk; Artifex commercial license terms; fee schedule)
- [S222] Artifex commercial licensing --
   https://artifex.com/
   (MuPDF / PyMuPDF commercial support; licensing tiers; enterprise support)
- [S223] pdfplumber pure Python PDF library --
   https://github.com/jsvine/pdfplumber
   (MIT licensed; metadata extraction; pure Python; no C extensions; alternative to PyMuPDF)
- [S224] REUSE.software compliance framework --
   https://reuse.software/
   (SPDX headers; LICENSES/ directory; automated compliance checking; OSS best practice)
- [S225] SBOM generation with pip-licenses --
   https://github.com/raimon49/pip-licenses
   (Dependency license audit; CSV/JSON export; dependency tree)
- [S226] CycloneDX SBOM standard --
   https://cyclonedx.org/
   (SBOM format; dependency graph; vulnerability tracking; supply-chain security)
- [S227] US export control - encryption exemptions --
   https://www.bis.doc.gov/index.php/regulations/export-administration-regulations-ear
   (Publicly available source code exemptions; hash functions (SHA-256); HTTPS; code signing)
- [S228] EU export control guidance --
   https://ec.europa.eu/growth/tools-databases/cosme/
   (Export controls; dual-use regulations; cryptography; software licensing)
- [S229] Commercial licensing models for OSS --
   https://www.linuxfoundation.org/
   (Dual licensing; commercial support; enterprise tiers; typical fee structures)

### Competitive Landscape (Wave 5b)
- [S230] Local-File-Organizer by curdriceaurora --
   https://github.com/curdriceaurora/Local-File-Organizer
   (Python + PyQt6; modular provider routing; YAML taxonomy; v2.0 beta Q3 2026)
- [S231] Czkawka file cleaner --
   https://github.com/qarmin/czkawka
   (Duplicate detection; multi-threaded; v12 roadmap Q3 2026; potential AI addition)
- [S232] electron-dam asset management --
   https://github.com/electron-dam/electron-dam
   (Electron + semantic search; Web UI; lightweight competitor)
- [S233] Local-File-Organizer provider architecture --
   https://github.com/curdriceaurora/fo-core/tree/main/src/providers
   (DeepSeek router; Ollama fallback; pluggable provider abstraction)
- [S234] TidyAI commercial comparison --
   https://www.tidy.ai/
   (Cloud + local; subscription model; native Windows/Mac)

### Platform Roadmaps & Standards (Wave 5c)
- [S235] Qt 6.11 release March 2026 --
   https://www.qt.io/
   (Async improvements; accessibility enhancements; PyQt6 6.11 sync)
- [S236] Qt 6.12 release September 2026 --
   https://www.qt.io/
   (Q3 2026 expected; WebEngine updates; performance improvements)
- [S237] Python 3.13 asyncio improvements --
   https://www.python.org/downloads/release/python-3130/
   (Per-interpreter GIL; async performance; H1 2026 release)
- [S238] Python 3.14 free-threaded mode --
   https://peps.python.org/pep-0703/
   (Sub-interpreter isolation; true multi-threading; H2 2026 draft)
- [S239] Python 3.9 EOL October 2025 --
   https://peps.python.org/pep-0619/
   (End of support; security fixes cease; migration pressure Q1 2026)
- [S240] WCAG 3.0 draft timeline --
   https://www.w3.org/WAI/WCAG3/
   (Accessibility standards evolution; working-draft updates)
- [S241] Ollama model roadmap Q3 2026 --
   https://ollama.ai/
   (New models; GPU inference improvements; quantization options)
- [S242] Asyncio structured concurrency --
   https://peps.python.org/pep-0733/
   (Task groups; cancellation scopes; H1 2026 PEP)
- [S243] Windows 12 early signals --
   https://blogs.windows.com/
   (Q3 2026 expected; shell integration improvements)
- [S244] GDPR enforcement 2026 --
   https://gdpr-info.eu/
   (Fines; compliance audits; data retention requirements)
- [S245] CCPA implementation & amendments --
   https://oag.ca.gov/privacy/ccpa/
   (Consumer rights; opt-out enforcement; 2026 amendments)


### Partnerships & Ecosystem Integration (Wave 5e)
- [S246] Envato API --
   https://www.envato.com/APIs/
   (Asset marketplace integration; batch upload; metadata mapping; partner program)
- [S247] Adobe Lightroom CC plugin SDK --
   https://developer.adobe.com/
   (UXP plugin framework; catalog integration; keyword mapping; Lightroom asset browser)
- [S248] Blender addon API --
   https://docs.blender.org/api/
   (bpy Python API; asset browser integration; preview generation; File > Open integration)
- [S249] Krita brush pack format --
   https://docs.krita.org/
   (Brush pack serialization; preset export; asset bundle format)
- [S250] Ollama Hub models --
   https://ollama.ai/models
   (Model distribution; fine-tuning marketplace; asset-classification category models)
- [S251] Weblate community translation --
   https://weblate.org/en/projects/
   (Community translation platform; CJK + European language support; review workflows)
- [S252] GNOME Foundation partnerships --
   https://www.gnome.org/partners/
   (Linux desktop integration; GNOME Software featured placement; distribution channels)
- [S253] KDE Dot community program --
   https://dot.kde.org/
   (KDE Discover app store; community initiatives; Linux ecosystem partnerships)
