# ROADMAP -- FileOrganizer
<!-- v8.3.0-planning · Updated 2026-05 · Supersedes all prior ROADMAP.md versions -->

FileOrganizer is a Python/PyQt6 desktop tool for classifying and moving creative design assets
into a canonical folder taxonomy. Core use case: 33 TB+ of Envato/Creative Market/Freepik
templates (After Effects, Photoshop, Illustrator, Premiere Pro, etc.) on Windows.
Multi-provider AI backbone (DeepSeek, GitHub Models, Ollama).

---

## State of the Repo (v8.3.0 planning, May 2026)

v8.2.0 is **fully shipped** (all 8 NOW items: I:\ source infrastructure, fix_duplicates incremental
journal, catalog auto-download, pre-flight UI, confidence thresholds, two-phase commit, security
dependency pins, and _Review batch panel). See [Shipped — v8.2.0](#shipped--v820) below.

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

---

## NOW -- Active / Blocking (target: v8.3.0)

These items extend v8.2.0 directly; all have clear implementation paths given the shipped stack.

### AI Pipeline

**N-9: Metadata extractors MVP**
Create `fileorganizer/metadata_extractors/` package with four extractors wired into
`classify_design.py` as pre-AI stages. Classification order: metadata first → keyword/fuzzy
fallback → AI last. Eliminates AI calls for ~40-60% of well-structured assets.
- `psd_extractor.py`: psd-tools 1.16.0 layer names, document width/height → classify mockups,
  social-media templates (9:16 canvas), print layouts without AI
- `font_extractor.py`: fonttools `TTFont['name'].names` → font family, style variants → route to
  `Fonts & Typography` subcategories at confidence 95
- `audio_extractor.py`: mutagen → title, artist, BPM, duration → differentiate stock music,
  SFX packs, tutorial audio tracks
- `video_extractor.py`: `subprocess(['ffprobe', '-v', 'quiet', '-print_format', 'json',
  '-show_streams', path])` → duration, codec, resolution, aspect ratio → route 9:16 vertical
  video to `Social Media`, ProRes/DNXHD to `Broadcast / Cinema Stock`
- **Why now**: psd-tools 1.16.0 (Apr 2026) adds Python 3.14 support; fonttools CVE-2025-66034
  security pin (N-13) must land with or before fonttools use in code. RESEARCH_IDEAS.md rates
  this the #1 priority for reducing per-item AI cost.
- **Impact**: 5 | **Effort**: 3
- Source: [S34] RESEARCH_IDEAS.md, [S8] organize-cli v3.3.0 filecontent filter, [S44] Czkawka
  v11.0.0 ffprobe video analysis, [S46] psd-tools v1.16.0

**N-10: Embeddings classifier MVP**
Add `fileorganizer/embeddings_classifier.py`. On first run, embed all 384 category display names
via `sentence-transformers` `all-MiniLM-L6-v2` (80 M params, fully local, ~40 ms per batch)
and store vectors as REAL columns in a new `category_embeddings` SQLite table. At classify time:
embed item `name + extension_set` → cosine similarity against all 384 anchors → if top-1 ≥ 0.65
AND margin over top-2 ≥ 0.15, apply category at confidence 90; otherwise fall through to AI.
Add `--embeddings-only` CLI flag for benchmarking skip rate against a known-classified sample.
- **Why now**: Reduces AI API cost ~50-70% on well-named assets; fully local; no cloud dependency.
  electron-dam confirmed Ollama-based embedding is a viable DAM pattern [S43]; sentence-
  transformers is production-stable with 15,000+ pretrained models [S48].
- **Impact**: 5 | **Effort**: 3
- Source: [S34] RESEARCH_IDEAS.md #7, [S48] sentence-transformers, [S43] electron-dam Ollama
  embedding

### UX Completion

**N-11: ReviewPanel thumbnail rendering**
N-8 shipped the _Review batch panel but the thumbnail column is text-only. Replace the folder-name
cell with a `QLabel` holding a `QPixmap` scaled to 80×80 px via `PIL.Image.thumbnail()`. Use
`QPixmapCache` (key = folder fingerprint) to prevent re-loading on scroll. For items with no
image: render an extension badge (colored rectangle + extension text) as a fallback `QPixmap`.
For PSD files: load the embedded composite via `psd_tools.PSDImage(path).topil()` at native
thumbnail resolution. The `thumbnail` path is already collected by `_ReviewScanWorker`; this item
only changes rendering.
- **Why now**: ReviewPanel is actively used for the I:\ reclassification pass; text-only cells
  make visual asset review impractical for 18,000+ mixed-media items.
- **Impact**: 4 | **Effort**: 2
- Source: [S38] TagStudio v9.5.6 virtual list + thumbnail, [S43] electron-dam thumbnail grid,
  [S19] Eagle App, [S34] RESEARCH_IDEAS.md

### Data Enrichment

**N-12: Provenance tracking**
Add `source_domain TEXT`, `first_seen_ts INTEGER` columns to `asset_fingerprints.db` via
`ALTER TABLE IF NOT COLUMN` migration guard (safe for existing installs). Populate at index time:
`source_domain` by normalizing folder path through a known-source parser (Envato, Creative Market,
Freepik, Motion Array) plus a piracy-domain blocklist; `first_seen_ts` = Unix epoch at insert.
Expose `source_domain` as sub-text in ReviewPanel row and in Browse tab tooltip. Strip piracy
domains from UI display names and CSV exports. CLI: `build_source_index.py --show-provenance`.
- **Why now**: RESEARCH_IDEAS.md #6 rates this high; N-10 embeddings can use domain as a prior
  weight; NEXT-20 cross-library dedup needs stable domain metadata.
- **Impact**: 4 | **Effort**: 2
- Source: [S34] RESEARCH_IDEAS.md #6, [S33] RESEARCH.md provenance track

### Security

**N-13: Security hardening — fonttools pin + archive isolation**
Three concrete changes in a single PR:
1. Pin `fonttools>=4.62.1` in `requirements.txt`. CVE-2025-66034 is a path traversal bug in
   `fonttools.varLib.main` fixed in 4.61.0. FileOrganizer uses TTFont name table reads (N-9),
   not varLib, but the explicit pin prevents transitive exposure and covers future sub-path use.
2. Run psd-tools PSD parsing in a subprocess with a configurable file-size sanity limit (default
   500 MB). Maliciously crafted PSDs can trigger parser bugs; the Coverage Matrix flagged this
   as pending since N-7. N-9 adds active psd-tools use, making isolation urgent.
3. In `archive_extractor.py` and any RAR/7z/ZIP extraction path: validate all extracted entry
   paths against the target directory before write:
   `assert os.path.realpath(dest).startswith(os.path.realpath(safe_root))`.
   Covers the 2 open GitHub Advisory DB entries for rarfile and 2 for py7zr [S42, S41].
- **Why now**: N-9 will use fonttools heavily; pin must land first or in the same commit.
  fonttools CVE-2025-66034 was published 2025 — the outstanding pin is now overdue.
- **Impact**: 3 | **Effort**: 1
- Source: [S49] fonttools CVE-2025-66034 (fixed v4.61.0), [S42] rarfile GitHub Advisories,
  [S41] py7zr advisories, Coverage Matrix security notes

### Quality

**N-14: Broken file detection**
During `build_source_index.py` scan, detect and flag corrupt/truncated assets before classify:
- **Images**: `PIL.Image.verify()` on images ≤ 20 MB; catch `PIL.UnidentifiedImageError`,
  `OSError` → flag `broken=True`
- **Videos**: `subprocess(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_error',
  path])` → flag if `error` key present in parsed JSON output
- **Archives**: `zipfile.ZipFile(f).testzip()`, `rarfile.RarFile(f).testrar()`,
  `py7zr.SevenZipFile(f).testzip()` → flag if any returns non-None
Add `broken INTEGER DEFAULT 0` column to `asset_files` table (schema migration). Pre-flight dialog
(N-4, shipped) gets a collapsible "Broken files (N)" section listing affected paths before any
move is attempted.
- **Why now**: Running classify+move on a corrupt archive silently fails mid-extraction; broken
  images cause Pillow tracebacks mid-batch. Czkawka v11.0.0 shipped broken-video detection via
  ffprobe in 2026 — the pattern is proven and the tooling (Pillow, ffprobe, zipfile) is already
  present.
- **Impact**: 3 | **Effort**: 2
- Source: [S44] Czkawka v11.0.0 broken video detection, [S34] RESEARCH_IDEAS.md, N-4 pre-flight
  infra

---

## NEXT -- High Value, Well-Scoped (target: v8.3 / v9.x)

### Automation & Workflow

**NEXT-1: Watch mode daemon**
Monitor source folders for new files. Auto-classify+move when files stabilize (debounce window:
default 30s -- avoids partially-downloaded-archive false positives). Option to register as a
Windows background task or Task Scheduler trigger.
- **Impact**: 4 | **Effort**: 4 | Risk: debounce stability on network drives
- **Parity with**: [S1] LlamaFS, [S5] aifiles, [S20] Hazel, [S21] File Juggler

**NEXT-2: YAML rule export**
Serialize the classifier's learned category-keyword rules as portable YAML. Structure compatible
with [S8] organize-cli format so users can move rules to organize-cli without rework.
Export from GUI: Settings -> Rules -> Export as YAML.
- **Impact**: 4 | **Effort**: 2 | Leapfrog: bridges AI-generated rules to portable OSS format
- Source: [S8] https://github.com/tfeldmann/organize

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
- **Impact**: 4 | **Effort**: 3
- Source: [S34] RESEARCH_IDEAS.md, [S33] RESEARCH.md

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
- **Impact**: 4 | **Effort**: 3
- Source: [S10] https://github.com/qarmin/czkawka, [S47] imagehash (JohannesBuchner)

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
- **Impact**: 5 | **Effort**: 4 | Primary commercial benchmark: [S19] Eagle App
- Source: [S19] https://eagle.cool, [S38] TagStudio v9.5.6 infinite scrolling, [S22] Adobe Bridge,
  N-11 (thumbnail Pillow+QPixmap pattern established)

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
items in a category, with inline edit before committing. CLI: opt-in `--rename` flag.
- **Impact**: 3 | **Effort**: 2
- Source: [S22] Adobe Bridge batch rename, [S15] digiKam rename templates

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

---

## LATER -- Strategic, Not Yet Urgent

Depend on NEXT-tier items, or have high effort relative to current user base.

**L-1: Semantic / embedding search**
Embed file path + AI classification description at move time via `sentence-transformers`. Store in
SQLite-Vec or FAISS. Enable "find assets similar to this one" queries in Browse tab (NEXT-20).
- **Impact**: 4 | **Effort**: 5 | Leapfrog: no OSS desktop organizer has done this for design assets
- Source: [S34] RESEARCH_IDEAS.md, [S17] electron-dam, [S7] DocMind

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
- **Impact**: 4 | **Effort**: 3
- Source: [S4] FileWizardAI https://github.com/AIxHunter/FileWizardAI , [S34] RESEARCH_IDEAS.md

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
- **Impact**: 3 | **Effort**: 3

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
- **Impact**: 2 | **Effort**: 4 | **Depends on**: NEXT-22
- Source: [S43] electron-dam audio waveform visualization

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
| **Security** | Covered | N-7 (Pillow/PyQt6 pins + pip-audit CI, shipped), N-13 (fonttools CVE-2025-66034 pin + psd-tools subprocess isolation + archive path-traversal guard), L-7 (archive content full implementation) |
| **Accessibility** | Covered | L-15 (WCAG 2.1, keyboard nav, screen reader) |
| **i18n / l10n** | Covered | L-14 (QTranslator, CJK locale) |
| **Observability / telemetry** | Covered | L-16 (opt-in analytics), N-4 (pre-flight report), NEXT-25 (post-apply report), NEXT-31 (scan time measurement) |
| **Testing** | Covered | NEXT-29 (unit test expansion to 10+ functions), N-7 (pip-audit CI gate), N-14 (broken file detection as pre-run validation) |
| **Distribution / packaging** | Covered | N-3 (catalog auto-download), NEXT-30 (multiplatform CI), L-10 (portable mode) |
| **Plugin ecosystem** | Covered | NEXT-27 (SDK + 3 reference plugins), NEXT-28 (webhook) |
| **Mobile** | Rejected | Android app rejected (no server backend); revisit after UC-1 |
| **Offline / resilience** | Covered | N-6 (two-phase commit), N-2 (incremental journal), Ollama local fallback already in prod |
| **Multi-user / collaboration** | Rejected | Single-user tool by design; see Rejected table |
| **Migration paths** | Covered | N-1 (I:\ legacy reclassification), CATEGORY_ALIASES expansion (already shipped) |
| **Upgrade strategy** | Covered | N-3 (schema version gate on catalog sync), UC-5 (in-app update notification) |

### Security -- additional notes
- **psd-tools** parses untrusted `.psd` files. Maliciously crafted PSDs could trigger parser bugs.
  Fix: run parser in subprocess with file-size sanity limit. **Scheduled in N-13.**
- **rarfile / py7zr** extract untrusted archives. Path traversal risk (archive entry names with
  `../`). 2 open GitHub Advisory DB entries for each. Fix: validate all extracted paths against
  target directory before write. **Scheduled in N-13.**
- **fonttools** CVE-2025-66034 (path traversal in `varLib.main`, fixed v4.61.0). N-9 metadata
  extractors will use fonttools; pin `fonttools>=4.62.1` in the same commit. **Scheduled in N-13.**
- **API keys** (DeepSeek, GitHub, Envato) are stored in `%APPDATA%\FileOrganizer\` settings.
  Verify they are not logged or committed. Covered by N-7 audit pass (shipped).

---

## Competitive Landscape (Summary)

| Tool | Type | Key strength | FileOrganizer gap addressed |
|------|------|--------------|----------------------------|
| organize-cli [S8] | OSS CLI | YAML rules, dry-run, deduplicate conflict mode (v3.3.0) | NEXT-2 (YAML export), NEXT-3 (rule chains) |
| LlamaFS [S1] | OSS Electron | Watch mode, minimal-diff index | NEXT-1, NEXT-5 |
| Czkawka/Krokiet [S10] | OSS Rust GUI | Perceptual hash dedup, broken video detection (v11) | NEXT-19, NEXT-32, N-14 |
| fclones [S11] | OSS Rust CLI | Reflinks, cross-library dedup, JSON, fclones-gui (pre-release) | NEXT-20 |
| TagStudio [S9] | OSS Python/Qt | Non-destructive tagging, infinite scrolling (v9.5.6), 7+ locales | Different model (move vs tag) -- intentional |
| electron-dam [S43] | OSS Electron | Semantic search, virtual bundles, 3D/audio preview, Ollama embedding | L-1, L-17, L-18, N-10 pattern |
| AIFileSorterShellExtension [S45] | OSS C# | Windows Explorer context menu, 2-min undo, OpenRouter LLM | L-6 (context menu -- prior art confirmed) |
| Eagle App [S19] | Commercial | Visual search, designer UX | NEXT-22 (thumbnail browser) |
| Hazel [S20] | Commercial macOS | Rule chains, Spotlight conditions | NEXT-3, NEXT-1 |
| File Juggler [S21] | Commercial Win | Folder watch, content conditions | NEXT-1, NEXT-3 |
| Paperless-ngx [S14] | OSS Docker | OCR, multi-user, REST API | Single-user; OCR in L-3 |
| Adobe Bridge [S22] | Commercial | AEP/PSD preview, CC integration | NEXT-22 |

**FileOrganizer's unique position**: design-asset-specialist classifier (384 categories, Envato
marketplace ID enrichment, AEP-aware pipeline) + multi-TB real-world hardening + metadata-first
AI cost reduction (N-9). No OSS competitor combines all three. Primary gaps closing in v8.3.0:
metadata extractors (N-9), embeddings classifier (N-10), ReviewPanel thumbnails (N-11).

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
