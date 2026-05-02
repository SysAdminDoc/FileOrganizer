# ROADMAP -- FileOrganizer
<!-- v8.3.0-planning · Updated 2026-05 · Phase 2 refresh · Supersedes all prior ROADMAP.md versions -->

FileOrganizer is a Python/PyQt6 desktop tool for classifying and moving creative design assets
into a canonical folder taxonomy. Core use case: 33 TB+ of Envato/Creative Market/Freepik
templates (After Effects, Photoshop, Illustrator, Premiere Pro, etc.) on Windows.
Multi-provider AI backbone (DeepSeek, GitHub Models, Ollama).

---

## State of the Repo (v8.3.0 planning, June 2026)

v8.2.0 is **fully shipped** — the original 8 NOW items (N-1..N-8) and the extended sprint items
(N-10, N-11, N-13, N-15, N-16, N-17). See [Shipped — v8.2.0](#shipped--v820) below.

**v8.3.0 sprint** — N-9 (metadata extractors), N-12 (provenance tracking), and N-14 (broken file
detection) all landed in May 2026 against the **Unreleased** section of CHANGELOG.md. Subject to
a Q3 release pass to bump the Python core to v8.3.0. No NOW items remain blocking.

A 2026-04-30 audit pass on the N-1..N-8 commits surfaced source-config drift, an unsafe
ReviewPanel move path, missing SQLite pragmas on the journal DB, an invalid pip-audit flag,
and a few smaller resilience gaps. All fixes are merged. The audit motivated **N-15**
(SOURCE_CONFIGS parity test), **N-16** (catalog sync conditional requests), **N-17** (robocopy
/MT), **NEXT-33** through **NEXT-38** (xxhash/blake3, provider failover, reparse-point detection,
free-space reserve, journal vacuum, crash dialog), **L-19** (executable quarantine), and
**L-20** (localized destination folder names) — all now shipped.

The WinUI 3 shell reached **ui-v0.5.0** (2026-05-01) with 15 live pages covering all major media
and design-asset domains. See [Shipped — WinUI Shell](#shipped--winui-shell-ui-v010--ui-v050) below.
**ui-v0.6.0 targets**: WindowsAppSDK 1.7 upgrade (NEXT-39), RAWPage (NEXT-40), ComicsPage (NEXT-41).

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
  confidence threshold panel (N-5), two-phase commit (N-6), _Review batch panel (N-8)
- PyInstaller release: `FileOrganizer.exe` + CLI ZIP on GitHub Releases
- CI: syntax check + `test_organize_run.py` + `pip-audit --fail-on-cvss 7` (N-7) on
  `windows-latest`

### Built but not fully wired
- `metadata_extractors/`: psd-tools/fonttools/mutagen/ffprobe metadata pipeline planned in
  RESEARCH_IDEAS.md; no implementation yet — this is the primary N-9 target for v8.3.0
- `marketplace_enrich.py`: built, but stage 2 pipeline call not always reachable via GUI
- `archive_extractor.py`: scaffolded; archive content peek not integrated into classifier
- ReviewPanel (N-8): `thumbnail` path collected but QTableWidget renders text only — N-11 fixes
- `deepseek_research.py` CLI exists but not surfaced in GUI as first-class flow
- Watch mode: not implemented

### Stubbed / incomplete
- **Embeddings classifier**: planned in RESEARCH_IDEAS.md #7; not implemented (N-10 target)
- **Provenance tracking**: source_domain + first_seen not in `asset_fingerprints.db` (N-12 target)
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

## NOW -- Active / Blocking (target: v8.3.0)

The original v8.3.0 NOW slate (N-9, N-12, N-14) is now in **Shipped — v8.3.0 (Unreleased)**
below. No NOW items remain blocking; the next sprint pulls from NEXT.

---

## Shipped -- v8.3.0 (Unreleased)

Three Python-core features landed in May 2026 against the Unreleased section of CHANGELOG.md.
A Q3 release pass will mint these as v8.3.0 once the next batch of NEXT items is also ready
to ship (or sooner if the user explicitly cuts a patch).

### N-9: ~~Metadata extractors MVP~~ ✓ Shipped (Unreleased)
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

### N-12: ~~Provenance tracking~~ ✓ Shipped (Unreleased)
`source_domain TEXT` + `first_seen_ts INTEGER` columns added to `assets` via idempotent
PRAGMA-table_info migration. UPDATE path uses `COALESCE` so `first_seen_ts` is immutable
across re-builds. New `fileorganizer/provenance.py` recognises 12 marketplace patterns plus a
7-domain piracy blocklist; piracy match wins over marketplace match. UI-safe `display_domain()`
strips blocked domains. New `python build_source_index.py --source <name> --show-provenance`
prints a per-domain histogram.
- Tests: 33 tests in `tests/test_provenance.py` (parser, piracy override, COALESCE immutability,
  legacy-DB migration).
- **Source**: [S34] RESEARCH_IDEAS.md #6, [S33] RESEARCH.md provenance track

### N-14: ~~Broken file detection~~ ✓ Shipped (Unreleased)
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

### Provenance back-fill ✓ Shipped (Unreleased — iter 2 follow-up to N-12)
`asset_db.cmd_backfill_provenance(db_path, dry_run)` populates `source_domain` +
`first_seen_ts` on assets rows that pre-date N-12. Idempotent (WHERE source_domain IS NULL
OR first_seen_ts IS NULL). Dry-run mode does not mutate the schema even on legacy DBs that
need the N-12 columns added — surfaces a `migration_pending` flag instead. CLI:
`python asset_db.py --backfill-provenance [--dry-run]`.
- Tests: 5 in `tests/test_provenance.py` (happy path, dry-run no-commit, idempotency,
  unmatched-name, legacy-schema dry-run safety).

---

## NEXT -- High Value, Well-Scoped (target: v8.3 / v9.x)

### Automation & Workflow

**NEXT-1: Watch mode daemon**
Monitor source folders for new files. Auto-classify+move when files stabilize (debounce window:
default 30s -- avoids partially-downloaded-archive false positives). Option to register as a
Windows background task or Task Scheduler trigger.
- **Impact**: 4 | **Effort**: 4 | Risk: debounce stability on network drives
- **Parity with**: [S1] LlamaFS, [S5] aifiles, [S20] Hazel, [S21] File Juggler

**NEXT-2: ~~YAML rule export~~** ✓ Shipped (Unreleased — iter 2)
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

**NEXT-4: Dry-run simulation (all operations)**
Every CLI command and GUI action must have a full dry-run path that previews the exact list of
moves, renames, and deletes without touching the filesystem. Emit an editable JSON plan file
before commit.
- **Impact**: 4 | **Effort**: 2 | Parity with: [S8] organize-cli `sim` mode, [S20] Hazel "Test Rule"

**NEXT-5: Minimal-diff re-scan index**
Cache folder fingerprint + mtime from each run. On re-scan, skip folders whose fingerprint and
mtime are unchanged. Reduces re-run cost ~70% on large libraries where most items are already
classified.
- **Impact**: 4 | **Effort**: 3 | Parity with: [S1] LlamaFS minimal-diff index
- Source: [S1] https://github.com/iyaja/llama-fs

**NEXT-6: Parallel LLM calls**
Batch DeepSeek/GitHub Models API calls concurrently via `asyncio` + `aiohttp`. Current serial
approach is the primary throughput bottleneck on 19,531-item loose-files runs. Benchmark optimal
queue depth (2, 4, 8) against rate limits.
- **Impact**: 4 | **Effort**: 3

**NEXT-7: Adaptive learning from corrections**
When a user corrects a classification, record the correction in `corrections.json` keyed by
folder fingerprint AND extracted keyword pattern. On next run: exact-fingerprint matches
auto-apply the correction; keyword-pattern matches inject it as a few-shot example into the
batch prompt.
- **Impact**: 4 | **Effort**: 3 | Parity with: [S6] thebearwithabite adaptive learning loop
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
Route image and PDF mimes to a local multimodal model (`llava:7b`, `qwen2.5-vl`, or `moondream`)
when extension-only confidence is low. The preview image path is already known from
`asset_db.find_preview_image()`.
- **Impact**: 4 | **Effort**: 4
- Source: [S2] QiuYannnn Local-File-Organizer, [S6] thebearwithabite

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

---

## LATER -- Strategic, Not Yet Urgent

Depend on NEXT-tier items, or have high effort relative to current user base.

**L-1: Semantic / embedding search**
Embed file path + AI classification description at move time via `sentence-transformers`. Store in
SQLite-Vec or FAISS. Enable "find assets similar to this one" queries in Browse tab (NEXT-20).
Bookmark-Organizer-Pro [S55] already ships a tested embedding service plus a vector store and
hybrid search (BM25 + cosine via Reciprocal Rank Fusion) — those modules are directly portable
and shorten this work substantially.
- **Impact**: 4 | **Effort**: 5 | Leapfrog: no OSS desktop organizer has done this for design assets
- Source: [S34] RESEARCH_IDEAS.md, [S17] electron-dam, [S7] DocMind, [S55] Bookmark-Organizer-Pro
  `services/embeddings.py` + `services/vector_store.py` + `services/hybrid_search.py`

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
| **Security** | Covered | N-7 (Pillow/PyQt6 pins + pip-audit CI, shipped), N-13 (fonttools CVE pin + psd-tools subprocess isolation + archive path-traversal guard, **shipped v8.2.0**), L-7 (archive content full implementation), L-19 (executable quarantine on archive scan), UC-6 (EXIF remover — on hold) |
| **Accessibility** | Covered | L-15 (WCAG 2.1, keyboard nav, screen reader) |
| **i18n / l10n** | Covered | L-14 (QTranslator UI strings, CJK locale), L-20 (localized destination folder names) |
| **Observability / telemetry** | Covered | L-16 (opt-in analytics), N-4 (pre-flight report), NEXT-25 (post-apply report), NEXT-31 (scan time measurement), NEXT-38 (crash dialog + log viewer) |
| **Testing** | Covered | NEXT-29 (unit test expansion to 10+ functions), N-7 (pip-audit CI gate), N-14 (broken file detection as pre-run validation), N-15 (SOURCE_CONFIGS parity test, **shipped v8.2.0**) |
| **Distribution / packaging** | Covered | N-3 (catalog auto-download), N-16 (catalog sync conditional requests, **shipped v8.2.0**), NEXT-30 (multiplatform CI), L-10 (portable mode) |
| **Plugin ecosystem** | Covered | NEXT-27 (SDK + 3 reference plugins), NEXT-28 (webhook) |
| **Mobile** | Rejected | Android app rejected (no server backend); revisit after UC-1 |
| **Offline / resilience** | Covered | N-6 (two-phase commit), N-2 (incremental journal), N-17 (robocopy multi-thread, **shipped v8.2.0**), NEXT-34 (provider failover), NEXT-35 (reparse-point detection), NEXT-36 (free-space reserve), NEXT-37 (journal vacuum + retention), Ollama local fallback already in prod |
| **Performance** | Covered | N-17 (robocopy /MT, **shipped**), NEXT-6 (parallel async LLM), NEXT-33 (xxhash/blake3 fast fingerprint), NEXT-5 (minimal-diff re-scan), NEXT-44 (LLM summary cache) |
| **Multi-user / collaboration** | Rejected | Single-user tool by design; see Rejected table |
| **Migration paths** | Covered | N-1 (I:\ legacy reclassification), CATEGORY_ALIASES expansion (already shipped) |
| **Upgrade strategy** | Covered | N-3 (schema version gate on catalog sync), UC-5 (in-app update notification) |
| **WinUI Shell** | Active | ui-v0.5.0 shipped (15 pages); NEXT-39 (WinAppSDK 2.0 upgrade), NEXT-40 (RAWPage), NEXT-41 (ComicsPage) target ui-v0.6.0 |

### Security -- additional notes
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
| LlamaFS [S1] | OSS Electron | Watch mode, minimal-diff index, Groq/Ollama backends | NEXT-1, NEXT-5 |
| Czkawka/Krokiet [S10] | OSS Rust GUI | Perceptual hash dedup, broken video detection (v11), bad-names scanner, video optimizer, EXIF remover | NEXT-19, NEXT-32, N-14, NEXT-42, L-21, UC-6 |
| fclones [S11] | OSS Rust CLI | Reflinks, cross-library dedup, JSON, fclones-gui (pre-release), blake3 default | NEXT-20, NEXT-33 |
| TagStudio [S9] | OSS Python/Qt | Non-destructive tagging, infinite scrolling (v9.5.6), CB7/CBR/CBT thumbnails, 7+ locales | Different model (move vs tag) -- intentional; NEXT-41 pattern |
| electron-dam [S43] | OSS Electron | Semantic search, virtual bundles, 3D/audio preview, Ollama embedding | L-1, L-17, L-18 |
| AIFileSorterShellExtension [S45] | OSS C# | Windows Explorer context menu, 2-min undo, OpenRouter LLM, game/mod file recognition | L-6 (context menu -- prior art confirmed) |
| hazelnut [S68] | OSS Rust TUI | TOML rules, daemon, 15 TUI themes, desktop error notifications, age/size conditions, archive action | NEXT-1, NEXT-42 pattern |
| Foldr [S67] | OSS Rust CLI | Preview → confirm → move flow, keep-newest/keep-largest/keep-oldest dedup, per-op undo IDs, TOML config | NEXT-19 UX, NEXT-24 |
| hyperfield AI File Sorter [S3] | OSS Python+Qt | Local GGUF, Vulkan/CUDA/Metal GPU inference, Microsoft Store distribution | L-5 (GGUF), NEXT-30 distribution |
| Eagle App [S19] | Commercial | Visual search, designer UX | NEXT-22 (thumbnail browser) |
| Hazel [S20] | Commercial macOS | Rule chains, Spotlight conditions | NEXT-3, NEXT-1 |
| File Juggler [S21] | Commercial Win | Folder watch, content conditions | NEXT-1, NEXT-3 |
| Paperless-ngx [S14] | OSS Docker | OCR, multi-user, REST API | Single-user; OCR in L-3 |
| Adobe Bridge [S22] | Commercial | AEP/PSD preview, CC integration | NEXT-22 |

**FileOrganizer's unique position**: design-asset-specialist classifier (384 categories, Envato
marketplace ID enrichment, AEP-aware pipeline) + multi-TB real-world hardening + metadata-first
AI cost reduction (N-9) + WinUI 3 shell (15 live pages, ui-v0.5.0). No OSS competitor combines
all three. Primary gaps closing in v8.3.0: metadata extractors (N-9, NOW), provenance (N-12,
NOW), broken file detection (N-14, NOW). N-10 (embeddings), N-11 (thumbnails), N-13 (security
hardening) are **already shipped**.

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
