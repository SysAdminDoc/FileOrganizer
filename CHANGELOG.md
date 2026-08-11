# Changelog

All notable changes to FileOrganizer will be documented in this file.

## [Unreleased]

### Added

- Completed folder scans now launch a throttled background marketplace refresh;
  explicit provider version/date changes are grouped into non-flashing update
  alerts by category.
- Added a Tools → Cross-Library Dedup reviewer that compares independent roots
  with complete folder SHA-256 fingerprints and offers revalidated per-group
  keep, merge, or archive decisions.
- Marketplace enrichment now recognizes Creative Market, Freepik, Motion Array,
  FilterGrade, Shutterstock, and Adobe Stock IDs/URLs, with shared HTML/JSON-LD
  parsing and an optional keyed Freepik resource lookup.
- DeepSeek design batches now use a cached two-stage prompt: a context-light
  file-family pass constrains the destination-category pass, with a safe
  unknown-type fallback when the first provider response is unusable.
- AI category previews now show the current confidence and bounded runner-up
  probabilities; selecting a runner-up applies and remembers the correction.
- MOGRT manifests now route through canonical Premiere categories using editable
  parameter counts, required-font evidence, and title/transition/social signals;
  the same metadata is retained by the legacy folder classifier. Video metadata
  now also carries deep FFmpeg routing flags such as vertical format, broadcast
  codec/frame rate, looping clips, and 4K/60fps signals into provider prompts.
- Ambiguous image and PDF assets can now use an installed local multimodal model
  through the modern batch pipeline, with ranked vision-model selection, preview
  resolution, and the shared structured classification schema; missing models,
  previews, or invalid responses safely fall through to later stages.
- Saved scan profiles can now be registered from WinUI Settings or the
  `--schedule` CLI with daily, weekly, monthly, and logon cadences. One
  cross-platform scheduler writes atomic state, launches a hidden/offscreen
  profile runner, retains bounded logs and last-run results, defaults to
  preview-only scans, and saves a validated plan before explicit auto-apply.
- Category overrides now feed one adaptive correction store shared by the
  rename dialog, review queue, rule/LLM workers, and design classifier: exact
  folder fingerprints bypass providers and related keyword examples are
  injected into bounded DeepSeek/Ollama prompts, with legacy corrections
  migrated without data loss.
- Design classification can now split unresolved DeepSeek work into
  order-preserving cached request chunks with bounded concurrency;
  `classify_design.py` and `organize_run.py` expose parallel CLI controls, and
  AI Provider settings persist safe concurrency and request-size defaults.
- `organize_run.py --skip-unchanged` now uses the durable folder fingerprint
  cache to omit stable source folders from generated plans, while
  `--invalidate-cache` clears the cache as an explicit standalone action.
- Legacy desktop Preview and Apply now share a Step 6 preflight operation
  table with per-row toggles and atomically save the selected moves/renames as
  editable JSON before mutation; `organize_run.py` also accepts the plan-first
  `--dry-run --plan-file` and `--plan-file --commit` command forms.
- Hazel-style nested rule chains now have a visual IF/AND/OR/THEN editor and
  participate in organize planning before category routing; skip, destination,
  and rename decisions flow through dry-run plans, path validation, collision
  handling, journaling, and undo instead of mutating files out of band.
- WinUI Settings now configures opt-in Watch Mode startup at user logon with a
  2–120 second quiet window, hidden least-privilege Task Scheduler execution,
  validated atomic configuration, enable/disable/removal controls, and a
  bounded rollover log viewer.
- Local NTFS catalogs can now resume from a persisted USN Change Journal
  cursor, rehash only affected asset roots, reconcile deletes and renames,
  invalidate folder caches, expose lag/status, and recover watcher downtime;
  journal wrap, volume changes, network roots, and unsupported filesystems
  automatically take the existing full-scan path.
- AI-assisted batch classifications now write bounded, migratable evaluation
  provenance with input/provider/model/prompt/schema/taxonomy/response hashes,
  durable correction and final-decision linkage, redacted JSONL export, fixture
  replay scoring, and provenance IDs in move plans, journals, and reports.

### Fixed

- README shell guidance now matches every routed page, the read-only review
  boundaries, the seven-theme picker, and the current sidecar architecture;
  a source-backed documentation contract prevents future route/theme drift.
- Every shell workflow now publishes a shared capability-health preflight with
  dependency/tool versions, scope, online status, and remediation; the shell
  displays the bounded matrix globally and dependency failures use one schema.
- Cleanup and duplicate scans now persist to a bounded, migratable SQLite
  review store with scan IDs, import/export, durable keeper decisions, and
  fail-closed path/metadata/hash revalidation before action adapters run.
- Critical contract coverage now directly exercises persisted move-plan replay,
  source-identity revalidation, and fail-closed undo of tampered journal roots,
  alongside classifier, watch, NDJSON, retry, collision, and WinUI service paths.
- Windows CI now runs the isolated Python suite, compiled sidecar/service
  contracts, the WinUI release build, and exact-version Ruff/mypy/pyright
  ratchets, while publishing test, quality, build-log, and shell artifacts.
- Streamed WinUI result views now retain bounded recent and error rows with
  exact totals and coalesced updates; page and sidecar output buffers retain a
  capped recent tail and clearly report truncation.
- Helper/status text and destructive controls now use semantic colors that meet
  WCAG AA across all seven themes and card surfaces, with explicit accessible
  danger-button hover and pressed states.
- All custom WinUI button styles now retain the Windows system focus indicator,
  including its built-in high-contrast behavior for keyboard navigation.
- Default pytest runs now use unique workspace-owned temp roots and guarded
  teardown, avoiding Windows `pytest-current` lock collisions across repeated
  and concurrent runs.
- Settings now report success only after LocalSettings values are written and
  reread; partial failures roll back the durable batch and clearly distinguish
  restored settings from edits that remain only in the form.
- WinUI title-bar buttons now derive their normal, inactive, hover, and pressed
  colors from the active theme and refresh immediately on theme and window
  activation changes.

### Security

- Python startup no longer invokes pip, retries with elevated environment
  override flags, or writes an installation-failure cache; dependencies are
  installed explicitly from the checked-in requirements manifest.
- Community catalog updates now require a pinned GitHub release asset and
  verified SHA-256 digest, enforce bounded schemas, stage and integrity-check
  SQLite imports before atomic replacement, retain rollback backups, preserve
  offline startup, and expose opt-out and last-success status in settings.
- WinUI crash reports now use bounded atomic rotation, enforce file and record
  retention caps, redact secret-bearing arguments and environment values, and
  minimize private paths while retaining actionable stack context.
- Provider and Envato credentials now use Windows-user DPAPI storage instead of
  plaintext app-data JSON/text files, and configurable cloud endpoints are
  restricted to approved HTTPS provider hosts.
- Rename templates are parsed against an allowlist, must resolve beneath the
  selected destination root, and use collision suffixes instead of overwriting
  existing files across the media/code/font sidecars.
- Move plans, retry records, journals, undo entries, watcher roots, and sidecar
  mutations now use canonical/reparse-aware source and destination boundary
  checks with source identity validation and no-overwrite defaults.
- Profile and category-preset names now stay within validated app-data files,
  reject traversal/device names, and use atomic JSON replacement.
- RAW and Comics WinUI progress handlers now dispatch through the registered
  application window instead of the nonexistent `MainWindow.Current` member.
- WinUI NDJSON sidecar events now execute page callbacks on the captured
  dispatcher queue, preserve event ordering, and propagate callback failures.
- WinUI Cleanup and Duplicates now clearly identify their shell scans as
  read-only and direct users to the Python desktop action flows.
- WinUI AcoustID credentials now migrate to Windows Credential Locker and are
  supplied to the music sidecar through an explicit environment channel rather
  than process arguments.
- The WinUI build wrapper now discovers compatible MSBuild installations or an
  explicit `MSBUILD_EXE_PATH`, and reports a missing .NET SDK resolver before
  attempting a misleading restore/build.
- Python dependencies now have a hash-pinned Windows/Python 3.10 lock with
  reproducible freshness checks, dry-run hash validation, vulnerability audit,
  and CI license-report generation.

### Fixed

- Restored missing runtime imports across classification, metadata, PC-file,
  face-detection, Ollama, rule, plugin, worker, and secondary PyQt paths.
- Watch folders now reject equal, nested, ancestor, junction, and symbolic-link
  source/destination roots before persistence or startup.
- Watch auto-apply now propagates through the PyQt and standalone paths, remains
  preview-only by default, and blocks malformed or overlapping roots before a
  real move can start.
- Archive extraction now enforces entry, byte, compression-ratio, and free-space
  quotas, checks cancellation during streaming, and promotes only clean staging
  output with structured limit and cancellation results.
- DeepSeek batch results are now schema-checked across fresh and cached paths;
  malformed entries become retry-marked review records, cardinality failures are
  controlled, and batch result files are written atomically.
- LLM cache connections now create or migrate their schema, indexes, and version
  marker transactionally at the canonical database path on first use.
- Directory merges now preserve differing destination files with collision
  suffixes and record guarded per-file manifests for selective undo.
- Ollama batch classification now passes the configured endpoint and model
  explicitly, and optional face-recognition failures no longer terminate GUI
  startup.
- Plan-based deletes now fail closed when the Recycle Bin provider is missing or
  unavailable; no permanent-delete fallback is attempted, and failed trash
  operations preserve the source for retry.
- Ollama startup no longer downloads or executes installers or implicitly pulls
  models; missing setup is reported with an explicit Settings/Model Manager
  path for visible user-initiated acquisition.
- Routed NDJSON sidecars now negotiate a versioned capability handshake and
  emit bounded, sequence-checked records; the WinUI runners isolate malformed
  events and produce deterministic terminal results for completion and cancel.
- Classification-cache access is serialized across GUI and worker threads,
  while move-journal and provider-cost schemas now initialize lazily on first
  database use instead of creating files during module import.
- Watch configuration now fails closed with one structured error for malformed
  schemas or unsafe timing values, and long-running watches retain bounded,
  identity-aware file state with observable eviction counts.
- Community catalog downloads are restricted to the owned GitHub release
  asset, stream within fixed metadata/payload byte budgets, validate media
  types and schema limits, and support cancellation between chunks.
- Loose-file plans now pre-sanitize trailing-space path components before
  hashing, preserve colliding siblings with numbered suffixes, and journal the
  renamed source path used by the move.
- Retry cleanup now removes only unchanged, identity-recorded partial files or
  directories whose contents match the live source; reparse points, stale
  output, legacy records, and unrelated occupied destinations fail closed.
- Duplicate move actions now use a shared no-overwrite executor, suffix
  different-content collisions, preserve identical sources, report per-file
  outcomes, and retain source-bound journal records for guarded undo.
- Python and native sidecar runners now drain redirected streams before
  returning from cancellation and serialize same-sidecar restart leases;
  repeated cancel/restart contract runs reject stale callbacks.

## [v8.5.19] - 2026-07-01

### Security

- **Webhook SSRF protection** — `send_webhook()` now validates URL scheme
  (HTTP/HTTPS only) and blocks loopback, metadata, and link-local addresses.
- **XML entity expansion defense** — SVG parser uses `defusedxml` when available
  to prevent billion-laughs and XXE attacks on untrusted SVG files.
- **HTML report XSS** — confidence field in post-apply report is now HTML-escaped.

### Fixed

- **Provider cost tracking 1,270,000x error** — `cost_per_token` rates were
  $700/1M tokens instead of $0.55/1M. Cost estimates now use correct rates
  ($0.00000055/token for DeepSeek, $0.00000075 for GitHub Models). Combined with
  the `max_tokens`-as-actual fix, daily budget caps now behave correctly.
- **Provider records estimated tokens instead of max_tokens** — `classify()` and
  `classify_batch()` now estimate actual token usage instead of passing the
  response limit parameter to cost tracking.
- **Cancelled apply creates false resume prompt** — journal rows from user
  cancellation are now cleaned up; only crash-orphaned rows trigger resume.
- **Crash handler thread-safety** — `_record_crash()` now holds a lock during
  log rotation and write, preventing concurrent crash entries from corrupting
  each other.
- **SQLite connection leaks** — All functions in `move_journal.py`,
  `provider_cost_manager.py`, and `folder_cache.py` now use try/finally to
  guarantee connection closure even on exceptions.
- **ctypes handle truncation on 64-bit** — `space_reserve.py` now sets
  `CreateFileW.restype = c_void_p` to prevent 64-bit handle truncation.
- **sys.path pollution** — `_fingerprint_db_lookup()` now uses `importlib.util`
  instead of prepending to sys.path on every call.
- **API empty choices crash** — provider httpx transport handles empty `choices`
  array from rate-limited API responses without `IndexError`.
- **LLM cache TTL based on created_at** — cache entries now expire based on
  creation time, not last access time, preventing stale results from persisting
  indefinitely when frequently accessed.
- **Missing CorrectionRecord.folder_path** — `from_dict()` deserialization now
  sets `folder_path` attribute, preventing `AttributeError` on restored records.
- **GUI dest path sanitization** — `scan_mixin.py` now strips reserved Windows
  characters from categories and folder names before constructing destination
  paths.
- **strip_trailing_spaces empty-name guard** — names consisting entirely of
  spaces are now skipped instead of attempting rename to empty string.
- **Video routing division by zero** — aspect ratio calculation now guards
  against zero height.
- **workers.py f-string backslash** — fixed re.sub pattern inside f-string
  expression for Python <3.12 compatibility.

## [v8.5.18] - 2026-07-01

### Added

- **NEXT-15: Hash-first DB skip** — fingerprint lookup at classify time
  skips all AI calls when the folder fingerprint is already in asset_db.
- **NEXT-16: Negative keyword rules** — per-category "must NOT contain" terms
  that prevent cross-category misclassifications. 12 categories covered.
- **NEXT-25: Post-apply HTML report** — generates a Catppuccin-themed HTML
  report with category distribution, move details, confidence, and timing.
- **NEXT-28: Webhook on organize** — POSTs JSON summary to user-configured
  URLs after each apply run for n8n/Zapier/Home Assistant integrations.
- **NEXT-31: Scan time measurement** — `ScanTimer` tracks wall-clock time per
  pipeline phase with human-readable summary formatting.
- **NEXT-33: Fast fingerprint mode** — blake3/xxhash/SHA-256 algorithm
  selection with tiered hash (size → partial → full) for dedup I/O savings.
- **NEXT-34: Provider cost/backoff integration** — daily budget cap, exponential
  backoff on 429s, and automatic failover chain wired into ProviderRouter.
- **NEXT-36: Free-space reserve** — sparse file pre-allocation prevents
  mid-apply disk exhaustion from concurrent writes.
- **NEXT-38: Crash handler** — `crash_handler.py` installs sys.excepthook +
  threading.excepthook, writes to crash.log with rotation, fires GUI callback.
- **NEXT-60: Watchfiles daemon scaffold** — async `WatchDaemon` with debounce
  queue, watchfiles/polling dual-backend, and configurable ignore patterns.
- **NEXT-63: AVIF + JPEG XL format detection** — `.avif` and `.jxl` added to
  all image extension sets, magika MIME routes, and content-type detection.
- **NEXT-67: Windows Search SHChangeNotify** — `shell_notify.py` calls
  `SHChangeNotify(SHCNE_UPDATEDIR)` via ctypes after apply.
- **NEXT-76: AV1/VP9/HEVC codec detection** — video routing classifies
  codec family with `is_modern_codec` and `codec_family` fields.
- **NEXT-78: SVG metadata extraction** — `svg_extractor.py` parses title,
  description, author, license, dimensions, animation; classifies type.
- **NEXT-80: Zstandard archive support** — `.zst` and `.tar.zst` recognized.
- **NEXT-93: Taxonomy export** — `taxonomy_export.py` exports the 384-category
  taxonomy as JSON or YAML with negative keywords and statistics.

### Fixed

- **NEXT-42: Bad names scanner bug** — extension check flagging lowercase
  `.jpg` as uppercase; now only flags when extension differs from lowercase.
- **NEXT-34: Provider cost manager timestamp bug** — `_now()` double-appended
  timezone info causing `ValueError` on backoff expiry checks.
- **classifier.py SyntaxError** — f-string with backslash broke Python <3.12.

### Changed

- **NEXT-29: Test coverage expansion** — 162 new tests across 14 test files.
  Suite grew from 425 to 587 tests.

## [Unreleased]

### Docs

- Consolidated planning docs: active work remains in `ROADMAP.md`, shipped
  roadmap history is summarized in `COMPLETED.md`, and research context is
  summarized in `RESEARCH_REPORT.md` with the previous root research Markdown
  files archived under `docs/archive/research/`.

## [v8.5.17] - 2026-06-28

### Changed

- **P2: release and diagnostic version alignment** - Synchronized WinUI
  assembly, file, package, manifest, Home footer, README badge, and security
  policy metadata to FileOrganizer.UI v0.6.0 / Python core v8.5.17, with a
  regression test for future drift.

## [v8.5.16] - 2026-06-28

### Added

- **P2: WinUI sidecar contract tests** - Added coverage for every live NDJSON
  sidecar used by the WinUI shell, proving valid fatal-error NDJSON, stable
  event names, graceful cancellation hooks, and no runtime package installation
  paths.

## [v8.5.15] - 2026-06-28

### Added

- **P1: Comic sidecar safe inspection and plans** - `comics_run.py` now
  validates CBZ/CBT/CBR/CB7 archives without extracting to disk, rejects unsafe
  member paths through `safe_extract_path()`, emits per-item archive errors,
  and writes dry-run organize plans under `Comics/<Publisher>/<Series>/` before
  optional moves.

## [v8.5.14] - 2026-06-28

### Added

- **P1: RAW sidecar metadata and dry-run plans** - `raw_run.py` no longer
  installs `rawpy` at runtime, emits a deterministic missing-dependency error,
  reports real date/camera/ISO/focal fields when metadata is available, and
  writes JSON dry-run organize plans before any optional move.

## [v8.5.13] - 2026-06-28

### Added

- **P1: Watch mode source-config startup** - `python -m fileorganizer.watch_mode
  --source design --start` now resolves `classify_design.SOURCE_CONFIGS`,
  debounces new file events, classifies the changed asset through the existing
  pipeline, writes a dry-run `organize_run.py` move plan, and persists latest
  plan state in `watch_state.db`.

## [v8.5.12] - 2026-06-28

### Changed

- **NEXT-59: Pydantic 2.13 discriminated union JSON schema** - Ollama
  structured output now uses a tagged `classification`/`review` union schema
  with deterministic schema hashing, and review responses defer cleanly instead
  of becoming invalid categories.

## [v8.5.11] - 2026-06-28

### Fixed

- **P0: Archive extraction path traversal hardening** - Routed ZIP, TAR, RAR,
  and 7z extraction through `safe_extract_path()`. 7z members are now validated
  before extraction and no longer use unfiltered `extractall()`.

## [v8.5.10] - 2026-06-27

### Changed

- **NEXT-58: httpx migration for AI provider calls** - GitHub Models and
  DeepSeek provider calls now use a shared `httpx` chat-completions transport
  with HTTP/2 enabled, explicit JSON headers, per-call timeouts, and fallback
  error handling. `httpx[http2]>=0.28.1` is now a runtime dependency and
  bootstrap optional install target.

## [v8.5.9] - 2026-06-27

### Changed

- **NEXT-57: Pillow 12.2.0 lazy plugin loading + pin** - The repo already
  pins `Pillow>=12.2.0`; perceptual duplicate hashing now uses Pillow
  12.1+'s `get_flattened_data()` pixel API with a legacy `getdata()` fallback,
  and closes opened images through a context manager.

## [v8.5.8] - 2026-06-27

### Added

- **NEXT-56: Variable font axes detection** - Font metadata extraction now
  records OpenType `fvar` axes with tag, display name, and min/default/max
  values. COLR fonts also expose `has_color`, `has_colrv1`, and `is_colrv1`
  raw metadata so variable and modern color fonts can be routed later without
  reparsing the file.

## [v8.5.7] - 2026-06-27

### Added

- **NEXT-55: WinRT FileProperties metadata integration** - Added optional
  PyWinRT `Windows.Storage.FileProperties` extraction for Windows image,
  audio, and video files. General metadata and Stage-1 audio/video hint paths
  now try WinRT first, then fall back to Pillow, mutagen, or ffprobe.

## [v8.5.6] - 2026-06-27

### Added

- **NEXT-54: SetFit few-shot taxonomy extension** - Added user-taught
  categories stored in `user_categories.json`, loaded ahead of the built-in
  taxonomy, and surfaced through Settings -> Teach Category. The wizard accepts
  8+ dragged or browsed examples, trains a SetFit model when the optional stack
  is installed, and saves a keyword-only category when SetFit is unavailable.

## [v8.5.5] - 2026-06-27

### Added

- **NEXT-53: Master-folder canonical dedup protection** - Move plans now hash
  source files against the destination category tree, flag duplicate SHA-256
  hits before apply, and skip duplicate plan items by default while journaling
  both file paths and the matching hash.

## [v8.5.4] - 2026-06-27

### Added

- **NEXT-52: Similar-name fuzzy filename grouping** - Added
  `fileorganizer/similar_names.py` for RapidFuzz token-sort clustering of
  filename variants, plus pre-flight warning rows that surface grouped
  variants before apply.

### Fixed

- Extension badge fallback colors now use a deterministic hash instead of
  Python's process-randomized `hash()`.

## [v8.5.3] - 2026-06-27

### Added

- **NEXT-51: Color palette extraction and filter-by-palette** - Added
  `fileorganizer/color_palette.py` for dominant swatch extraction, RGB byte
  packing, CIE LAB conversion, and Delta-E matching. Image metadata now carries
  `_palette_hex`, `_palette_rgb`, and `_palette_rgb_bytes`.
- `asset_db.py` now stores `asset_files.palette_rgb` as a packed 5x3 RGB BLOB,
  keeps `palette_hex` for readable output, and exposes `find_by_palette()` plus
  `--palette #RRGGBB` CLI filtering.

## [v8.5.2] - 2026-06-27

### Added

- **NEXT-50: Magika content-type pre-routing** - Added optional Google
  Magika detection with `python-magic` fallback in `magika_router.py`, wired
  content-detected extension overrides into the Stage-1 metadata dispatcher,
  and routes disguised archives to `_Review` with `extension_mismatch`
  metadata instead of trusting misleading suffixes.

### Changed

- PSD, font, audio, video, and AEP extractors now accept a content-detected
  extension while still validating file bytes with their existing parsers.
- `requirements.txt` now installs `magika` and keeps `python-magic-bin` as the
  Windows fallback.

## [v8.5.1] - 2026-06-27

### Added

- **NEXT-9: AEP RIFX binary parser** — Added `aep_extractor` to the
  Stage-1 metadata pipeline. It validates RIFX/RIFF containers, reads chunk
  payload strings, extracts composition names, plug-in names, AE versions,
  resolutions, durations, frame rates, and chunk IDs, then hardroutes
  canonical After Effects categories at confidence 90+.

### Changed

- Metadata pre-classification results now include the extractor `metadata`
  payload so AEP and other Stage-1 hints can persist parsed fields in batch
  output.

## [v8.5.0] - 2026-05-02

### Added

- **NEXT-42: Bad names scanner in pre-flight dialog** — New `fileorganizer/bad_names.py` module detects filename issues that cause silent failures. Checks: non-ASCII characters (NTFS ASCII codepage), uppercase-only extensions (.JPG → .jpg), reserved Windows characters (<>:|?*), filenames >200 chars, leading/trailing spaces. Integrated into PreflightWorker as Stage 2 (after path checks, before disk space). Issues reported per-folder with capping at 5 items per folder to keep UI responsive. Enables pre-flight validation before high-volume batch operations.

- **NEXT-37: organize_moves.db vacuum and retention policy** — Prevent database bloat by automatically purging old journal records. New `move_journal.py` functions: `cleanup_expired()` deletes journal records with status='done' older than 90 days (configurable), `vacuum()` reclaims disk space. Integrated into MainWindow.closeEvent() so cleanup runs on app exit. No UI dialog needed; best-effort so failures don't block shutdown. Expected to reduce database size by 70-80% after 4-6 months of heavy use.

- **NEXT-35: Symlink and junction detection in pre-flight scanner** — Identify and block path traversal risks. New `fileorganizer/symlink_detector.py` with: `is_symlink_or_junction()` classifies reparse points (symlink/junction/other), `scan_for_reparse_points()` shallow scans for issues, `validate_junction_target()` checks for system dir escapes (Windows, Program Files, AppData, ProgramData, Recycle.Bin). Integrated into PreflightWorker as Stage 3 (after bad names, before disk space). Blocks junctions to C:\\Windows and similar; warns on all symlinks.

- **NEXT-50: Magika content-type pre-routing for Stage 0** — Integrate Google magika for 99%+ accurate MIME type detection across 300+ types. New `fileorganizer/magika_router.py` with: `detect_mime_type()` uses libmagic, `route_by_mime_type()` maps MIME→category with confidence 92, `is_obfuscated_archive()` catches renamed archives. New requirements: `python-magic-bin` (Windows) / `libmagic1` (Linux). Enables detection of obfuscated files (.txt that's .zip, .doc that's PDF, etc.) before extension-based routing. Superseded by v8.5.2, which wires the router into Stage-1 metadata dispatch.

- **NEXT-43: ExifTool integration for metadata extraction** — Fallback for N-9 extractors with <50% confidence. New `fileorganizer/exiftool_extractor.py` with functions: `is_available()` checks for ExifTool binary, `extract_metadata()` returns full JSON, `get_creation_date()` / `get_image_dimensions()` / `get_camera_info()` / `get_audio_info()` / `get_video_info()` provide normalized access to 800+ format support. Gracefully degrades if ExifTool not installed (Windows: will bundle binary in future, Linux: user runs 'apt-get install exiftool'). Added `piexif` to requirements as photo metadata supplement. Integration into metadata extraction pipeline pending.

- **NEXT-34: Provider cost cap, 429 backoff, and failover chain** — Implement budget controls and graceful degradation. New `fileorganizer/provider_cost_manager.py` module with: `record_api_call()` tracks daily spend per provider ($10.00/day budget default, configurable), `is_over_budget()` blocks over-budget providers, `set_backoff()` implements exponential backoff (2^n seconds, max 60 min) on 429/5xx errors, `handle_rate_limit_response()` extracts X-RateLimit-* headers, `get_next_available_provider()` returns next provider in failover chain (DeepSeek → GitHub Models → Ollama), `get_cost_summary()` for dashboard display. All state persisted in `provider_costs.db` (WAL mode). Dry-run ready pending integration into provider selection logic in workers.py.

### Changed

- **requirements.txt**: Added `magika`, `python-magic-bin`, and `piexif` for NEXT-50 (content-type pre-routing) and NEXT-43 (exiftool) support.
- **PreflightWorker**: Expanded from 4 to 6 stages (added bad names detection, symlink/junction validation).

### Infrastructure

- All 7 sprint items are modular, stand-alone, and degrade gracefully if dependencies unavailable.
- New databases: `provider_costs.db` (cost tracking), existing `organize_moves.db` extended with retention.
- New metadata files stored via piexif and exiftool integration points.

## [v8.4.0] - 2026-05-02


### Added

- **NEXT-15: Hash-first DB skip** — Stage 0 fingerprint lookup in classification pipeline. Query `asset_db.lookup_folder()` for exact folder fingerprint matches before any AI/metadata/marketplace enrichment. Returns confidence 100 at zero API cost. Expected skip rate 60-70% for common templates already in community DB. Graceful fallback if `asset_db` unavailable.

- **NEXT-44: LLM response caching (SQLite)** — New `llm_cache.py` module caches DeepSeek/GitHub Models/Ollama responses by `(fingerprint, model_id, prompt_hash)`. Cache key schema supports automatic invalidation when model or prompt template changes. TTL: 30 days (configurable, cleaned on startup). Eliminates >90% of API calls on re-runs of stable asset libraries. Cache stored in `organize_moves.db` with indices on fingerprint and accessed_at for efficient cleanup. Per-item cache hits reported in batch output.

- **NEXT-11: Video metadata deep routing** — Extend `video_extractor.py` with duration-based routing rules. New routes:
    - ≤15s clips → "After Effects - Motion Graphics" (confidence 80) for looping content
    - >5 min duration → "Tutorial Video" (confidence 75) for course/tutorial content
    - 9:16 vertical ratio → "Social Media - Templates" (confidence 85, up from 72)
    - 1:1 square ratio → "Social Media - Templates" (confidence 78, up from 68)
    - ProRes/DNxHD/DNxHR/XDCAM codecs → "Broadcast / Cinema Stock" (confidence 90)
  Decision tree prioritizes codec signals, then duration, then aspect ratio for robust routing across diverse video libraries.

- **NEXT-39: WindowsAppSDK 2.0.1 upgrade** — Migrate WinUI 3 shell from 1.5.240311000 to 2.0.1 GA (released April 29, 2026). Update SDK.BuildTools from 10.0.22621.3233 to 10.0.26100.4654. Unlocks modern Windows UI capabilities and unblocks NEXT-40/41 (RAWPage, ComicsPage).

- **NEXT-40: RAWPage** — New WinUI 3 component for DNG/CR2/NEF/ARW/ORF/RW2 raw photo metadata extraction and organization. UI: folder browsing, preview/organize mode toggle, metadata results grid. Python runner (`raw_run.py`) scaffolds EXIF extraction (placeholder for rawpy.exifdata expansion), folder scanning with graceful rawpy fallback. Integrated into MainWindow navigation as "Raw Photos" tab.

- **NEXT-41: ComicsPage** — New WinUI 3 component for CBZ/CBR/CB7/CBT comic archive metadata extraction. UI: folder browsing, series detection results grid. Python runner (`comics_run.py`) with regex series/volume/publisher parsing (handles "Series #NNN" and "(Series) #NNN (Publisher)" patterns), first-page thumbnail extraction via PIL/zipfile. Integrated into MainWindow navigation as "Comics" tab.

- **NEXT-46: DeepSeek V4 model migration** — Migrate from deprecated `deepseek-chat` / `deepseek-reasoner` aliases to `deepseek-v4-flash` (streaming) and `deepseek-v4-pro` (complex reasoning). Add deprecation warnings for legacy aliases. Hard deadline: July 24, 2026. Missing this deadline results in complete loss of DeepSeek functionality.

- **NEXT-47: Anthropic model refresh** — Migrate from `claude-3-haiku` / `claude-3-sonnet-4` / `claude-3-opus-4` to `claude-haiku-4-5` / `claude-sonnet-4-5` / `claude-opus-4-5`. Fix critical GitHub Models UI bug where model dropdown was storing short model names instead of full model IDs (e.g. storing "claude-sonnet-4-5" but API expects "Anthropic/claude-3-5-sonnet-20241022"). Fix routes through _GITHUB_MODEL_CATALOG to load authoritative catalog and map display labels to full IDs. Hard deadline: June 15, 2026.

- **NEXT-48: Ollama Pydantic structured outputs** — Add `ClassifyResult` Pydantic model to Ollama integration. Pass `format=ClassifyResult.model_json_schema()` to Ollama >=v0.22.1 chat endpoint for guaranteed schema-valid JSON output. Eliminates ~3% of calls that fail regex extraction on smaller models. Reduces inference latency ~40ms/call due to elimination of retry loop. Graceful fallback to regex extraction for older Ollama versions.

- **NEXT-49: psd-tools security hardening (GHSA-24p2-j2jr-386w)** — Add PSD header pre-validation before invoking `psd_tools.PSD.open()` to mitigate CVSS 6.8 vulnerability. Validate "8BPS" magic signature, extract width/height from big-endian uint32 at bytes 10–13/14–17, reject if > 30,000 px. Blocks ZIP-bomb OOM attack (zlib.decompress with no max_length cap) and integer-overflow attack (height×width buffer allocation). Use safe_psd_open wrapper. Document advisory in new `SECURITY.md` file. Add pre-validation guard inline for maximum safety.

### Changed

- **ui-v0.6.0**: Shell version incremented to 0.6.0 (from 0.5.0) reflecting RAWPage, ComicsPage, and WindowsAppSDK 2.0.1 upgrade.
- **Deprecation notices**: Legacy model aliases now emit DeprecationWarning with sunset date and migration guidance.

### Fixed

- GitHub Models dropdown now correctly maps user-selected models to full model IDs for API calls.
- PSD file attacks no longer cause OOM or integer overflow in child process.

## [v8.3.0] - 2026-05-02

### Added

- **N-9: Metadata extractors MVP** — new `fileorganizer/metadata_extractors/`
  package with four file-content readers (`psd_extractor`, `font_extractor`,
  `audio_extractor`, `video_extractor`) wired into `classify_design.py` as a
  zero-AI Stage 1 ahead of marketplace + embeddings + LLM. Hardroute
  threshold is confidence ≥ 90; below that the hint is informational and
  downstream stages still run. Phantom-category guard validates emitted
  names against `CATEGORIES` before they can write to a batch JSON.
  Routing today:
    - PSD 9:16 / square / business-card / A4 canvases → Print or Photoshop
      subcategories at confidence 90-92
    - Valid font header (TTF/OTF/TTC/WOFF/WOFF2) → "Fonts & Typography"
      at confidence 95
    - ProRes/DNxHD video → "Stock Footage - General" at confidence 90
    - Audio: short clips (<30s) hint Sound Effects, long tracks (>3min)
      hint Stock Music — both stay below the hardroute threshold
- **N-12: Provenance tracking** — `source_domain` + `first_seen_ts` columns
  added to `assets` via idempotent migration. New `fileorganizer/provenance.py`
  recognises 12 marketplace patterns (Videohive, MotionElements, Envato
  Elements, Creative Market, DesignBundles, Motion Array, AEriver, Freepik,
  Adobe Stock, Dribbble, Behance) and a 7-domain piracy blocklist
  (intro-hd.net, aidownload.net, gfxdrug, shareae, freegfx, graphicux,
  gfxlooks). Piracy match wins over marketplace match. UI-safe
  `display_domain()` returns empty string for blocked domains so they
  never surface in CSV exports or review-panel captions. New CLI flag
  `python build_source_index.py --source <name> --show-provenance` prints
  a per-domain histogram across the source root.
- **N-14: Broken file detection** — `fileorganizer/broken_detector.py`
  module with `check_image` (PIL.Image.verify under a 20 MB cap),
  `check_video` (ffprobe -show_error, treats non-empty stderr as broken
  even at rc=0), and `check_archive` (zipfile/rarfile/py7zr per-format
  testzip). `is_broken(path)` dispatcher routes by extension. Standalone
  CLI: `python -m fileorganizer.broken_detector --scan <dir>` exits 1 on
  any broken file. New `broken INTEGER NOT NULL DEFAULT 0` column on
  `asset_files` (idempotent migration) for future GUI pre-flight wiring.

### Tests

- 50 new tests across the three features + 5 audit-pass regression tests.
  Suite at 128 passing (excludes one pre-existing PyQt6 GUI test that
  fails on a DLL-load error unrelated to these changes).

### Audit notes (cross-family review pass)

- Audio MVP confidences capped below 90 — duration alone can't distinguish
  a 4s music intro stab from a 4s SFX one-shot.
- `check_video` honors the rubric's stderr-non-empty rule (catches
  "moov atom not found" warnings on truncated MP4s that ffprobe parses).
- Folder-mode font dispatch now picks `.woff` / `.woff2`.
- Provenance: `share.ae` dotted variant added to piracy blocklist; the
  over-broad second Videohive numeric pattern (matched any 8-9 digit
  prefix without separator) was removed.

### Iteration 2 — N-12/N-14 follow-ups + NEXT-2

- **Provenance back-fill CLI** — `python asset_db.py --backfill-provenance
  [--dry-run]` populates `source_domain` + `first_seen_ts` on rows that
  pre-date N-12. Idempotent; per-domain summary on completion. Dry-run
  inspects without committing (does not eagerly migrate the schema).
- **PreflightDialog "Broken files (N)"** — N-14 broken_detector wired into
  the GUI pre-flight gate as Step 5. Sampled (max 10/source, 200 total) to
  stay snappy on 33TB-scale runs. Surfaces missing verifier dependencies
  (Pillow / ffprobe / rarfile / py7zr) so users know what isn't being
  checked. Underlying scan logic lives in `broken_detector.scan_paths()`
  and is fully testable without PyQt6.
- **NEXT-2: YAML rule export** —
  `python classify_design.py --export-rules [<path>|-]` serialises the
  canonical taxonomy + alias map into an organize-cli-compatible
  (tfeldmann/organize) YAML rules file. Per-category extension hints +
  reverse-derived name keywords from `CATEGORY_ALIASES`. Default output
  always lands at repo root regardless of CWD. PyYAML used when available,
  hand-rolled deterministic emitter as fallback.

### Iteration 2 audit fixes (cross-family review pass)

- `--backfill-provenance --dry-run` no longer commits a schema migration
  via `init_db()` on legacy DBs; surfaces `migration_pending=True` instead.
- PreflightDialog suppresses the "no broken detected" all-clear line
  when verification was partial (missing optional deps) or the probe
  failed outright.
- `--export-rules` default path resolved against the script's directory,
  not the caller's CWD.

### Release-gate hardening

- `bootstrap.py` adds an `_is_frozen()` guard around `_bootstrap()` and
  the inner `_try_install()` — when running inside a PyInstaller bundle,
  pip subprocess calls are short-circuited so the frozen GUI exe cannot
  re-spawn itself in a fork-bomb loop.
- `fileorganizer/__main__.py` calls `multiprocessing.freeze_support()`
  as the first executable statement (canonical PyInstaller fork-bomb
  defense for any Pool/Process worker re-entry path).

## [FileOrganizer.UI v0.5.0] - 2026-05-01

### Added (themes + missing pages + UX overhaul)

The shell goes from 11 to **15 live pages** — all the placeholder routes
ship live. Plus a 7-theme picker, persisted user defaults, and a
sweeping pass over every page so settings read in plain English instead
of CLI jargon.

**Themes** — 7 dark + 1 light (Steam Dark default · Catppuccin Mocha ·
OLED Black · GitHub Dark · Nord · Dracula · Light). Live preview tile
grid in the new **Settings** page; click any tile to switch instantly.
Choice persists between launches via `ApplicationData.LocalSettings`.

**`SettingsPage`** — central hub for preferences. Theme picker,
AcoustID API key (saved securely in user settings, auto-applied to the
Music page), default rename patterns for Music / Video / Books, default
subtitle languages.

**`FilesPage`** + `files_run.py` — extension-based file organizer for
users who don't need AI in the loop. Routes any folder into clean
buckets (Pictures/JPEGs, Music/Lossless, Documents/PDFs, Archives,
Installers, Disk Images, 3D Models, Torrents, …) with finer subcategory
splits than Smart Sort.

**`PhotosPage`** + `photos_run.py` — EXIF reader. Pulls date taken,
camera, lens, ISO, aperture, shutter, focal length, GPS lat/lon. Optional
date-based rename groups photos into `Pictures/{year}/{year-month-day}/`.

**`WatchPage`** + `watch_run.py` — long-running auto-organize service.
Per-watch (source, destination) pairs persist between launches in
`ApplicationData.LocalSettings`. New files trigger Smart Sort
classification + move (or copy). Live event log + heartbeat metrics.

**`ToolboxPage`** — power-user tile grid: pipeline stats, validate
sources, asset DB summary, undo last 10 moves, audit organized library,
phantom-category scan. Each tile streams the script's stdout into a
shared output panel.

### UX overhaul on existing pages

- **Mode dropdowns** rewritten in plain English. Examples:
  - Music: "Just identify my songs (safe, no changes)" /
    "Tag and (optionally) rename — writes ID3/Vorbis/MP4 tags"
  - Video: "Find duplicates of the same movie/show — keep the highest-
    quality copy" / "Reorganize into Movies/TV folders (moves files)"
  - Cleanup: every scanner gets a one-line description of what it finds
    inline in the dropdown
  - Duplicates: replaced "Hamming threshold 0-32" with a 5-step
    similarity preset (Identical / Very strict / Strict (recommended) /
    Loose / Very loose)
- **Rename patterns moved into Advanced expanders** — collapsed by
  default, pre-filled from Settings page defaults. Music + Video gain
  preset buttons (Movies preset / TV preset).
- **AcoustID API key** moved out of the Music page header and into the
  Advanced expander; reads from Settings if not entered locally.
- **Subtitles language picker** is now a dropdown of common combos
  (en, en+es, en+fr, en+es+fr+de, ja, ko, zh, pt-BR) instead of a free-
  text box requiring babelfish code knowledge.
- **Organize page source picker** gets human-readable labels with the
  CLI flag in parentheses + a guidance line steering most users to
  Smart Sort or Files instead.

### Sourcing

Theme palettes adapted from: Catppuccin (MIT), GitHub Primer (MIT),
Nord (MIT), Dracula (MIT), and a from-scratch Steam-Dark + OLED Black.

## [FileOrganizer.UI v0.4.0] - 2026-04-30

### Added (Wave 2 — five new live pages, plus the Smart Sort dispatcher)

The shell goes from 6 to 11 live pages this release. Highlight is the
**Smart Sort** page — drop a folder, get an organized library — which
auto-routes every file to the right pipeline using the same Python
helpers each media-type sidecar already exposes.

- **`SmartSortPage`** + `smart_run.py` — meta-dispatcher. Walks a source
  root, classifies each file by extension into one of ten buckets
  (audio / video / image / book / pdf / font / archive / code /
  document / other), then delegates the *destination naming* to the
  matching media-type sidecar's pure-Python helpers (no subprocess
  spawn — one process for the whole run). `preview` shows the planned
  destination tree; `apply` moves (or copies, with `--copy`). Live
  category-count strip at the top of the page updates as the walk
  progresses.
- **`DuplicatesPage`** + `dedup_run.py` — replaces the Duplicates
  placeholder with two engines:
  - `files`: Czkawka-style progressive size → 4 KB-prefix SHA-256 →
    full SHA-256, byte-identical only.
  - `images`: pHash via `imagehash` indexed in a `pybktree` BK-tree for
    sublinear similarity search; configurable Hamming threshold.
  Results display as grouped cards showing the keeper (shortest path)
  with each duplicate's size and (for images) Hamming distance.
- **`FontsPage`** + `fonts_run.py` — TTF/OTF/WOFF/WOFF2/TTC/OTC reader.
  fontTools pulls family, subfamily, OS/2 weight class, italic /
  monospace flags, designer, foundry, version. Optional rename into
  `Fonts/{family}/{family} - {style}.{ext}`.
- **`CodePage`** + `code_run.py` — source-code project detector. Looks
  for marker files (package.json, Cargo.toml, pyproject.toml, go.mod,
  pom.xml, build.gradle, *.sln, .git, …) at each immediate child
  folder, then walks the tree to count file extensions and pick the
  primary language. Optional rename into `Code/{language}/{name}`.
  Knows ~70 file extensions / 30 languages.
- **`SubtitlesPage`** + `subtitles_run.py` — Subliminal-based auto-fetch.
  Skips MKV files that already have embedded subs (via enzyme), then
  asks Subliminal for matching .srt per requested language(s) with a
  configurable min-score threshold. Saves next to the video.

### Added (libraries)

`requirements.txt` gains `subliminal`, `Pygments`. The `imagehash` /
`pybktree` deps from v0.3.0 are now exercised by the Duplicates page.

### Sourcing

Pillaged from: Czkawka (BK-tree dedup index, MIT), Subliminal (subtitle
matching, MIT), MusicBrainz Picard / FileBot / Calibre (re-used for
Smart Sort dispatch via the existing music_run / video_run / books_run
helpers), tfeldmann/organize (the ten-bucket category model).

## [FileOrganizer.UI v0.3.0] - 2026-04-30

### Added (Wave 1 — per-media-type organization)

Three new live pages in the WinUI 3 shell, each backed by a new NDJSON
sidecar at the repo root. Together they take FileOrganizer from
"design-asset organizer" to "well-rounded organizer for any media type".

- **`MusicPage`** — Picard pipeline as a sidecar. `music_run.py` reads
  existing tags via mutagen, falls back to a MusicBrainz text-search
  ranked by RapidFuzz, then falls back again to a Chromaprint fingerprint
  + AcoustID lookup when text matching is too weak. In `tag` mode it
  writes ID3/Vorbis/MP4 tags via mutagen and (optionally) renames the
  file into a beets-style template path like
  `Music/{albumartist}/{year} - {album}/{disc:02}-{track:02} {title}.{ext}`.
  Requires `pyacoustid` + `musicbrainzngs` + `mutagen` + `rapidfuzz` from
  `requirements.txt`. AcoustID API key supplied via the `ACOUSTID_API_KEY`
  env var or the page's password box (free registration at
  https://acoustid.org/api-key).
- **`VideoPage`** — `video_run.py` runs GuessIt (the parser FileBot,
  Sonarr, Radarr all use under the hood) over each file's basename, then
  scores every result with a Sonarr-style custom-format ladder
  (resolution + source + video codec + audio codec + size tie-breaker).
  Three modes: `preview`, `keepers` (group by `(type, title, year, S/E)`,
  mark the highest-scoring file in each group as the keeper), `rename`
  (move into `Movies/{title} ({year})/...` or
  `TV/{title}/Season {season:02}/...`).
- **`BooksPage`** — `books_run.py` reads embedded metadata from EPUB
  (ebooklib), MOBI/AZW3 (PalmDB header), PDF (pikepdf docinfo + ISBN scan
  over the first 5 pages of pdfminer text), and CBZ (ComicInfo.xml).
  Optional `--isbn-lookup` enriches missing fields via isbnlib's default
  provider chain. Calibre series metadata
  (`<meta name="calibre:series">`) is preserved.

### Added (libraries)

`requirements.txt` gains `pyacoustid`, `musicbrainzngs`, `guessit`,
`EbookLib`, `isbnlib`, `imagehash`, `pybktree`. The Picard pipeline also
needs `fpcalc.exe` (Chromaprint) on PATH or pointed at via the `FPCALC`
env var — download from https://acoustid.org/chromaprint, no install
needed.

### Sourcing

Pillaged from: MusicBrainz Picard (the audio pipeline), beets (path-format
DSL), FileBot / Sonarr / Radarr (`guessit` + custom-format scoring),
Calibre (EPUB metadata + ISBN-from-content), Komga/Kavita
(ComicInfo.xml read), Czkawka (BK-tree dedup — landing in a future wave).
Licenses: GPL/MIT/Apache-2.0 mix; per project rules, all OSS licenses are
fine.

## [FileOrganizer.UI v0.2.0] - 2026-04-30

### Added (Cleanup wired live)

- **`CleanupPage`** — folder picker + six-scanner combo (empty folders,
  empty files, temp/junk, broken/corrupt, big files, old downloads),
  scanner-specific options (min size MB, days old, include logs, archive
  validation toggle), live results table with size + reason columns,
  cancellable mid-scan. Live metric tiles: scanned, found, total size.
- **`cleanup_run.py`** — NDJSON sidecar wrapper around
  `fileorganizer.cleanup`. Streams `start` / `progress` / `item` /
  `complete` / `error` events on stdout, throttles `progress` to ~10
  events/sec to avoid drowning the UI.
- **`PythonRunner.RunScriptNdjsonAsync`** — new method on `IPythonRunner`
  that parses NDJSON line-by-line and forwards `(eventName, JsonElement)`
  to the caller. Non-JSON lines are wrapped in a synthetic `log` event so
  the UI never sees a malformed payload.
- Home page Cleanup tile bumped from "Planned" to "Ready".

## [FileOrganizer.UI v0.1.0] - 2026-04-30

### Added (WinUI 3 shell scaffold)

- **`src/FileOrganizer.UI/`** — C# / .NET 8 / WinUI 3 desktop shell mirroring
  the UniversalConverterX design system: side-tab `NavigationView`, dark Steam
  palette with cyan accent, hero card + tile grid + cluster cards on Home,
  search box in pane header.
- **Side-tab nav**: Home · Organize · Files · Cleanup · Duplicates · Photos ·
  Watch · Toolbox. Routes resolve to live pages where wired, otherwise to a
  `PlaceholderPage` that names the Python module the route will wrap.
- **`OrganizePage`** — first live workflow. Source picker (ae/design/design_org/
  loose_files) plus three actions wired to `organize_run.py`: `--stats`,
  `--preview --quiet`, `--validate`. Streams stdout line-by-line into a code
  panel. Cancellation kills the child Python tree.
- **`PythonRunner`** service — locates the repo root, resolves Python via
  `FILEORGANIZER_PYTHON` env override → `.venv/Scripts/python.exe` → `py.exe` →
  PATH. Forces `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1` so Unicode filenames
  don't crash the child.
- **`SidecarRunner`** service — UCX-style NDJSON event runner (`progress`,
  `log`, `complete`, `error`) with watchdog silence-timeout. Ready for future
  PyInstaller-frozen sidecars under `tools/<name>/`.
- **`src/build.ps1`** — VS 2026 MSBuild wrapper. Cleans `obj/`+`bin/` first
  (MarkupCompilePass2 stale-state guard) and runs `Restore` and `Build` as
  separate invocations (combined target reproduces the same cascade per UCX
  experience).
- **`.gitignore`** — added `src/**/bin/`, `src/**/obj/`, `src/**/.vs/`.

### Why C# / WinUI 3 alongside Python

Python keeps the AI/classification/dedup/photo logic (psd-tools, rapidfuzz,
Ollama/DeepSeek clients, Pillow, archive inspection — ~20K LOC). WinUI 3
provides side-tab nav, tile grids, and native window chrome that PyQt6 cannot
match visually. The two halves talk over `stdout` (text or NDJSON). The
existing CLI runners (`organize_run.py`, `asset_db.py`, `classify_design.py`,
etc.) already match the sidecar contract.

## [v8.2.0] - Unreleased

### Added (2026-04-30, N-13 security hardening — fonttools pin + archive + PSD guards)

- **N-13.1: fonttools pin** — `requirements.txt` now pins `fonttools>=4.62.1`
  so CVE-2025-66034 (path traversal in `varLib.main`, fixed in 4.61.0) cannot
  reach FileOrganizer transitively.  Lands ahead of N-9, which will use the
  TTFont name table.

- **N-13.2: Archive path-traversal guard** — new
  `fileorganizer/safe_archive.py` exposes `safe_extract_path(target_root,
  entry_name)` that rejects:
    * `..` traversal (anywhere in the entry path)
    * absolute paths (POSIX `/etc/...`, Windows `C:\...`)
    * UNC roots (`\\server\share\...`, `//server/share/...`)
    * drive-letter prefixes (`C:relative.txt`)
    * sibling-prefix collisions (`targetX` masquerading as `target`)
    * empty / whitespace-only names
  Plus `filter_safe_entries()` for bulk shape-checking.  Hardens any future
  zipfile/rarfile/py7zr extraction (L-7, L-19) without relying on the
  upstream library's own path handling.

- **N-13.3: PSD parser size + exception isolation** — new
  `fileorganizer/psd_safe.py` exposes `safe_psd_open(path)` which:
    * skips files larger than 200 MB (configurable per call) — prevents OOM
      on layer-tree parses that have hit 1 GB+ PSDs in real organize runs
    * isolates psd_tools parser exceptions so a malformed PSD returns None
      instead of crashing the GUI worker
    * returns None when psd_tools is not installed
  Wired into both psd_tools call sites in `fileorganizer/metadata.py`
  (`extract_psd_metadata`, content extraction in `extract_folder_metadata`)
  and the thumbnail loader in `fileorganizer/thumbnail_cache.py`.  The
  duplicate `PSD_PARSE_LIMIT_BYTES` constant in `thumbnail_cache.py` was
  removed so every entry point shares the same threshold.

- 26 new tests across `tests/test_safe_archive.py` (16 — every traversal
  attack shape plus happy paths) and `tests/test_psd_safe.py` (6 — size
  guard short-circuits, missing-file return, garbage-content isolation).
  Suite total: **57/57 pass**.

### Added (2026-04-30, N-11 ReviewPanel thumbnail rendering)

- **N-11: ReviewPanel thumbnails** — new `fileorganizer/thumbnail_cache.py`
  with three layers ported from local TagStudio [S56] `cache_manager.py` +
  `previews/renderer.py`:
  1. In-process `QPixmapCache` (50 MiB, RAM only) keyed by absolute thumbnail
     source path + target size.  Fast scroll cache hits, no disk I/O.
  2. `ThumbnailLoaderWorker(QThread)` — single per-panel worker with a
     non-blocking job queue (`queue(row, path, ext)`) that emits
     `loaded(row, pixmap)` per job.  Stops cleanly on `stop()` via a sentinel
     job; `wait(timeout_ms)` for graceful teardown.
  3. `extension_badge(ext, size)` synthetic fallback — colored rounded rect +
     ext text rendered with `QPainter`.  Stable color per extension via a
     hash into an 8-color palette so `.psd` always renders the same blue.
  4. PSD support via `psd_tools.PSDImage.composite()` (or `.topil()` on older
     versions); skipped for files > 200 MB to avoid OOM on layer-tree parses.
  5. Pillow path for raster types (jpg/jpeg/png/gif/bmp/webp/tiff/tif).

  ReviewPanel changes (`fileorganizer/dialogs/marketplace.py`):
  - `_ReviewScanWorker` now records the most-frequent extension per item
    (`primary_ext`) so the badge fallback shows something meaningful when
    the item has no preview image.  PSD added to thumbnail-source extension
    set.
  - `ReviewPanel.__init__` instantiates a `ThumbnailLoaderWorker` and connects
    its `loaded` signal to a slot that swaps the placeholder badge for the
    real preview.  Row height grows to fit the 64×64 thumbnail.
  - `_on_scan_result` immediately sets an extension badge as the row icon
    (so the table never appears blank during a scan), then queues the real
    thumbnail for async load.  When the worker finishes, the icon swaps.
  - `closeEvent()` stops + waits the worker (≤2s) so the thread doesn't
    outlive the panel.

  PyQt6 compatibility: `QPixmapCache.find()` is the single-argument form in
  PyQt6 (the legacy two-arg `find(key, &pm)` overload from PyQt5/Qt-C++ is
  gone).  `cached_pixmap` uses the new return-Optional[QPixmap] shape.

  11 new tests in `tests/test_thumbnail_cache.py` cover the cache key
  (case-insensitive, size-aware), the badge renderer (valid pixmap, stable
  color per extension), the QPixmapCache round-trip (including the null-
  pixmap rejection), the synchronous `render_pixmap` fallback when the
  source path is missing or empty, and the loader worker's stop-unblocks-
  queue contract.

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

## Roadmap archive — 2026-08-10 — ROADMAP.md

<details>
<summary>Original roadmap snapshot</summary>

```markdown
# ROADMAP -- FileOrganizer
<!-- v9.1.0-planning · Updated 2026-05 (Wave 5 synthesis — community validation, competitive threats, platform roadmaps, licensing compliance) · Phase 5 audit complete · All Waves 1–5 reconciled -->

FileOrganizer is a Python/PyQt6 desktop tool for classifying and moving creative design assets
into a canonical folder taxonomy. Core use case: 33 TB+ of Envato/Creative Market/Freepik
templates (After Effects, Photoshop, Illustrator, Premiere Pro, etc.) on Windows.
Multi-provider AI backbone (DeepSeek, GitHub Models, Ollama).

Shipped work is summarized in [COMPLETED.md](COMPLETED.md) and detailed in
[CHANGELOG.md](CHANGELOG.md). Research context is summarized in
[RESEARCH_REPORT.md](RESEARCH_REPORT.md), with the prior root research notes
archived under `docs/archive/research/`.

---

## State of the Repo (v9.1.0 planning, May 2026 — Wave 5 research complete)

v8.3.0 is **fully shipped** — N-9 (metadata extractors), N-12 (provenance tracking), N-14
(broken file detection), and all iter-2 follow-ups. Tagged and released 2026-05-02. See
[Shipped — v8.2.0](#shipped--v820) and [Shipped — v8.3.0](#shipped--v830) below.

**v8.4.0 shipped** — NEXT-44 (LLM cache), NEXT-46 (DeepSeek V4), NEXT-47 (Anthropic refresh),
NEXT-48 (Ollama structured outputs), and NEXT-49 (psd-tools hardening) all landed.
NEXT-39 upgrades the WinUI shell to WindowsAppSDK 2.0.1 (GA April 29, 2026); NEXT-40 (RAWPage)
and NEXT-41 (ComicsPage) follow as ui-v0.6.0 deliverables.

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
  `video_extractor`, `aep_extractor` — zero-AI Stage 1 with hardroute threshold ≥ 90
- `magika_router.py`: optional Google Magika + python-magic content-type pre-router; flags
  extension mismatches, routes renamed extractor-supported files by detected bytes, and sends
  disguised archives to `_Review`
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
- **Embeddings classifier**: planned in `docs/archive/research/RESEARCH_IDEAS.md` #7; not implemented (N-10 target)
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

All items shipped. See CHANGELOG.md for full details.
Items: N-1, N-2, N-3, N-4, N-5, N-6, N-7, N-8, N-10, N-11, N-13, N-15, N-16, N-17.

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

## NOW -- Active / Blocking (target: v8.5.19)

| # | Item | Why now |
|---|------|---------|

### Audit findings (v8.5.19 — deferred, need human decision or larger refactor)

- [ ] P2 — **cache.py thread safety** — module-level `_cache_conn` created with default
  `check_same_thread=True` but accessed from both GUI and worker threads.
  Where: `fileorganizer/cache.py:83-112`

- [ ] P2 — **_init() at import time** — `move_journal.py:59` and
  `provider_cost_manager.py:71` create DB files on import. Lazy-init on first use
  would improve testability and avoid side effects.

- [ ] P3 — **bootstrap.py runtime pip install** — auto-installs packages at startup
  including with `--break-system-packages`. Consider removing or gating behind
  explicit user opt-in.
  Where: `fileorganizer/bootstrap.py:84-92`

---

## Shipped -- v8.5.x

All items shipped. See CHANGELOG.md for full details.
Items: NEXT-50 (v8.5.2), NEXT-51 (v8.5.3), NEXT-52 (v8.5.4), NEXT-53 (v8.5.5),
NEXT-54 (v8.5.6), NEXT-55 (v8.5.7), NEXT-56 (v8.5.8), NEXT-57 (v8.5.9), NEXT-58 (v8.5.10).

## Shipped -- v8.3.0

All items shipped (released 2026-05-02). See CHANGELOG.md for full details.
Items: N-9, N-12, N-14, Provenance back-fill, NEXT-2 (YAML rule export).

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

**NEXT-3: Hazel-style rule chains** ✓ Core shipped
Multi-condition chains: "if source matches X AND LLM confidence < 70 AND file size > Z, move to
A THEN rename as B THEN webhook C". Nested conditions with AND/OR. AST-based.
- **Core shipped**: `fileorganizer/rule_chains.py` with RuleCondition (12+ condition types),
  RuleAction (move, rename, delete, webhook, skip), RuleChain (recursive nesting), RuleChainManager.
  JSON schema v1.0. Full variable substitution ($HOME, $CATEGORY, $YEAR/$MONTH/$DAY). 20+ tests passing.
- **Remaining**: GUI rule builder (visual condition/action editor). Integration into organize_run.py
  pipeline (evaluate chains before classification, skip/move based on rules).
- **Impact**: 4 | **Effort**: 4 (core 3 + UI 1) | Parity with: [S20] Hazel, [S21] File Juggler, [S8] organize-cli
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

**NEXT-8: Scheduled scans per profile** ✓ Core shipped
Register scan profiles with Windows Task Scheduler (or launchd/systemd on macOS/Linux).
- **Core shipped**: `fileorganizer/scheduler.py` with ScheduledProfile + SchedulerManager.
  Cross-platform abstraction: Windows Task Scheduler (via schtasks.exe + win32com fallback),
  macOS launchd (plist + ~/Library/LaunchAgents/), Linux systemd timers (with cron fallback).
  Frequency: daily / weekly / monthly. Full CRUD: create, list, delete, enable, disable.
  Persistent JSON storage. 20+ tests covering all platforms and edge cases.
- **Remaining**: GUI hook (Settings → Schedules), CLI flag --schedule, background daemon integration.
- **Impact**: 3 | **Effort**: 3 (core 3 + integration 0)
- Source: [S21] File Juggler task scheduling, [S20] Hazel run-at-schedule

### Classification Accuracy

**NEXT-10: MOGRT manifest parser** ✓ Core shipped
`.mogrt` files are ZIP archives with an embedded JSON manifest containing: Motion Graphics
Template name, editable parameters, required fonts, minimum Premiere version. Pure Python
(`zipfile` + `json`).
- **Core shipped**: `fileorganizer/mogrt_parser.py` with parse_mogrt(), extract_mogrt_fonts(),
  mogrt_to_category_hints(), batch parsing support. Handles parameter/font fields as dict or list.
  Graceful fallback for corrupted/invalid MOGRTs. 20+ tests passing.
- **Remaining**: Integration into asset classifier (use font requirements and parameter count as routing signals).
- **Impact**: 4 | **Effort**: 2 (core 2 + integration 0)

**NEXT-11: Video metadata deep routing (FFmpeg expansion)** ✓ Core shipped
Extend `video_extractor.py` with intelligent routing: 9:16 vertical → `Social Media`, 
looping ≤15s + ProRes/DNXHD → `Motion Graphic`, broadcast codec → `Broadcast / Cinema Stock`,
duration > 5min → `Tutorial Video`, 60fps 4K+ → `High-Performance`, etc.
- **Core shipped**: `fileorganizer/video_routing.py` with VideoRoutingMetadata class,
  analyze_video_metadata(), _route_video() with 7 routing rules (vertical, looping, broadcast codec,
  high-performance, long duration, broadcast fps, default). extract_video_codecs() via ffprobe.
  30+ tests covering all routing paths, codec detection, frame rate edge cases.
- **Remaining**: Integration into classify pipeline (call analyze_video_metadata on .mp4/.mov/.mxf files before LLM).
- **Impact**: 4 | **Effort**: 2 (core 2 + integration 0) | Depends on: N-9 (ffprobe integration)
- Source: [S15] digiKam FFmpeg pipeline, [S44] Czkawka v11.0.0, [S34] `docs/archive/research/RESEARCH_IDEAS.md`

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

**NEXT-17: Marketplace enrichment expansion**
Extend `marketplace_enrich.py` beyond Envato to: Creative Market (API available), Freepik (API
key), Motion Array, FilterGrade, Shutterstock, Adobe Stock. Each needs a URL pattern + parser.
mnamer [S58] models exactly this pattern in `mnamer/providers.py` (Provider ABC) +
`mnamer/endpoints.py` (low-level wrappers for OMDb/TMDb/TVDb/TvMaze with ID caching, error
handling, and retry logic) — port the Provider ABC verbatim and add one subclass per
marketplace.
- **Impact**: 4 | **Effort**: 3
- Source: [S34] `docs/archive/research/RESEARCH_IDEAS.md`, [S33] `docs/archive/research/RESEARCH.md`, [S58] mnamer Provider ABC pattern

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

### Testing & Distribution

**NEXT-30: CI multiplatform builds**
Add macOS and Linux PyInstaller targets to `release.yml` using `macos-latest` and
`ubuntu-latest` runners. Ship platform-specific binaries in GitHub Release.
- **Impact**: 3 | **Effort**: 2
- Source: [S1] LlamaFS CI, [S8] organize-cli cross-platform, [S2] Local-File-Organizer

**NEXT-32: Dedup similarity grouping improvements**
When running perceptual hash dedup (NEXT-19), group near-identical items into clusters before
presenting the merge/keep dialog. Use complete-linkage clustering: two items in the same cluster
only if every pair is within Hamming distance threshold. Prevents over-merging when a cluster
contains both a genuine duplicate and a similar-but-different item.
- **Impact**: 3 | **Effort**: 2 | **Depends on**: NEXT-19
- Source: [S44] Czkawka v11.0.0 similarity grouping overhaul, [S47] imagehash clustering patterns

### Resilience & Operations

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

### Performance & Caching

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
- Source: [S34] `docs/archive/research/RESEARCH_IDEAS.md` item #9 (Platt scaling, isotonic regression,
  `CalibratedClassifierCV`)


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
- **Impact**: 4 | **Effort**: 4 | **Tier**: NEXT | **Depends on**: NEXT-88
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
- Source: [S34] `docs/archive/research/RESEARCH_IDEAS.md`, [S17] electron-dam, [S7] DocMind, [S55] Bookmark-Organizer-Pro
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
- Source: [S4] FileWizardAI https://github.com/AIxHunter/FileWizardAI , [S34] `docs/archive/research/RESEARCH_IDEAS.md`,
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
| **Security** | Covered | N-7 (Pillow/PyQt6 pins + pip-audit CI, shipped), N-13 (fonttools CVE pin + psd-tools subprocess isolation + archive path-traversal guard, **shipped v8.2.0**), NEXT-49 (psd-tools GHSA-24p2-j2jr-386w ZIP-bomb hardening, **shipped v8.4.0**), L-7 (archive content full implementation), L-19 (executable quarantine on archive scan), UC-6 (EXIF remover — on hold), NEXT-88 (REUSE.software compliance audit + LICENSES.md) |
| **Accessibility** | Covered | NEXT-90 (WCAG 2.1 Level A baseline), NEXT-89 (keyboard shortcut customization), L-22 (WCAG 2.1 AA full compliance), L-15 (screen reader testing) |
| **i18n / l10n** | Covered | L-23 (Qt Linguist UI string extraction + Chinese/Japanese/Spanish/French/German), L-24 (localized category taxonomy names), L-14 (QTranslator UI strings, CJK locale), L-20 (localized destination folder names) |
| **Observability / telemetry** | Covered | L-16 (opt-in analytics), N-4 (pre-flight report), NEXT-25 (post-apply report), NEXT-31 (scan time measurement), NEXT-38 (crash dialog + log viewer), NEXT-91 (privacy policy + telemetry opt-out), L-31 (analytics dashboard) |
| **Testing** | Covered | NEXT-29 (unit test expansion to 10+ functions), N-7 (pip-audit CI gate), N-14 (broken file detection as pre-run validation), N-15 (SOURCE_CONFIGS parity test, **shipped v8.2.0**) |
| **Distribution / packaging** | Covered | NEXT-81 (Windows Authenticode signing), NEXT-82 (macOS code signing + notarization), NEXT-83 (multi-platform CI/CD matrix), NEXT-84 (Homebrew Cask), NEXT-85 (Linux AppImage + GPG), NEXT-86 (WinSparkle auto-updates), NEXT-87 (Sparkle macOS auto-updates), L-26 (Snap distribution), L-27 (Flatpak distribution), L-28 (MSIX Windows Store), L-29 (Debian .deb + AUR), N-3 (catalog auto-download), N-16 (catalog sync conditional requests, **shipped v8.2.0**), NEXT-30 (multiplatform CI), L-10 (portable mode) |
| **Plugin ecosystem** | Covered | L-25 (pluggy-based extensibility architecture), NEXT-27 (SDK + 3 reference plugins), NEXT-28 (webhook) |
| **Mobile** | Rejected | Android app rejected (no server backend); revisit after UC-1 |
| **Offline / resilience** | Covered | N-6 (two-phase commit), N-2 (incremental journal), N-17 (robocopy multi-thread, **shipped v8.2.0**), NEXT-34 (provider failover), NEXT-35 (reparse-point detection), NEXT-36 (free-space reserve), NEXT-37 (journal vacuum + retention), Ollama local fallback already in prod |
| **Performance** | Covered | N-17 (robocopy /MT, **shipped**), NEXT-6 (parallel async LLM), NEXT-33 (xxhash/blake3 fast fingerprint), NEXT-5 (minimal-diff re-scan), NEXT-44 (LLM summary cache, **shipped v8.4.0**) |
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
  to a child process. NEXT-49 (shipped v8.4.0) added pre-validation header check (reject
  width/height > 30,000) and documents the advisory in SECURITY.md.
  Source: [S83] https://github.com/advisories/GHSA-24p2-j2jr-386w
- **sentence-transformers < 5.4.1**: activation function injection from Hub models → arbitrary
  code execution. Fixed in v5.4.1. Pin `sentence-transformers>=5.4.1` in requirements.txt.
  Source: [S97] sentence-transformers 5.4.1 release notes
- **DeepSeek V4 alias deadline (July 24, 2026)**: `deepseek-chat` and `deepseek-reasoner` aliases
  stop working July 24, 2026. NEXT-46 (shipped v8.4.0) covers migration to `deepseek-v4-flash` and
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
- [S33] `docs/archive/research/RESEARCH.md` -- Implementation tracks: Plan-First Apply, Asset Catalog, Multimodal Router
- [S34] `docs/archive/research/RESEARCH_IDEAS.md` -- 12 research areas: metadata extractors, embeddings, YAML rules
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
## Research-Driven Additions

## Audit Findings — 2026-08-10

### P1 — Correctness, security, and release blockers

### P2 — Reliability, performance, accessibility, and test-system findings

- [ ] P2 — Malformed watch configuration JSON raises uncaught exceptions
  Category: reliability
  Where: `watch_run.py:55-73`
  Problem: The watch loader catches JSON decoding errors but assumes the decoded value is a list of dictionaries with string paths. A scalar, object, or non-dictionary entry reaches `w.get(...)` and raises a traceback; negative, NaN, or infinite timing values can also make the long-running loop fail or behave unpredictably.
  Evidence: `load_watches()` validates only the `json.load()` call. It immediately iterates entries and reads `src`, `dest`, `interval`, and `settle` without type, finite-number, or bounds checks. The CLI accepts the file path and has no outer schema/error result.
  Fix: Validate the root array, each entry's object type, nonempty string source/destination, finite nonnegative interval/settle values, and bounded heartbeat/timeout values. Emit one structured configuration error and exit with a documented nonzero code instead of a traceback or partially started watcher.
  Acceptance: `--watches {}`, `--watches '[1]'`, missing fields, nonnumeric values, negative values, and NaN/Infinity fixtures all terminate quickly with an actionable error and no watcher; a valid file starts normally.
  Confidence: Verified
  Effort: S

- [ ] P2 — Long-running watch processes retain every historical path in an unbounded set
  Category: perf
  Where: `watch_run.py:70-73,80-84,105-129`; `src/FileOrganizer.UI/Views/Pages/WatchPage.xaml.cs:146-149`
  Problem: Each watch keeps every seen path in a Python set for the lifetime of the process, with no eviction, identity/mtime policy, persistence, or bound. UI event trimming only limits displayed events and does not release sidecar memory.
  Evidence: `seen` is initialized once per watch, prepopulated once, and only grows when a file is processed. A long-lived folder ingesting millions of distinct files therefore grows memory linearly even after the files are gone.
  Fix: Replace the unbounded set with bounded state keyed by canonical path plus file identity/mtime, persist only the minimum deduplication window if needed, and prune entries by age/size while preserving the no-repeat guarantee for unchanged files.
  Acceptance: A synthetic watch run processes more than the configured retention threshold and reports bounded state/memory; an unchanged file is not reprocessed within the retention window, while a changed/new file is processed once.
  Confidence: Verified
  Effort: M

- [ ] P2 — Catalog synchronization reads a remote response with no byte limit
  Category: security
  Where: `fileorganizer/workers.py:2796-2832`
  Problem: The catalog worker downloads a GitHub release asset with `resp.read()` before validating JSON or size. A compromised/misconfigured endpoint or unexpectedly large response can allocate unbounded memory and block the worker; the URL and content type are also not constrained before the read.
  Evidence: The reachable catalog worker opens the release URL, reads the entire body into memory, then parses/validates it. There is no maximum `Content-Length`, streaming counter, timeout/cancellation quota, host allowlist, or content-type check before allocation.
  Fix: Restrict the URL to the approved release host/path, enforce a maximum from both headers and streamed byte count, set connect/read timeouts and cancellation, validate content type/schema, and reject/clean up oversized responses before parsing.
  Acceptance: A mocked oversized, chunked, wrong-host, wrong-content-type, and invalid-JSON response aborts before exceeding the configured byte budget and reports a controlled error; a normal catalog still imports.
  Confidence: Verified
  Effort: M

- [ ] P2 — Loose files skip the trailing-space pre-sanitization required for Windows moves
  Category: correctness
  Where: `organize_run.py:18-20,1144-1149,1201-1216`
  Problem: The direct file-item branch calls `os.rename`/`shutil.move` without `strip_trailing_spaces()`, while the directory branch does sanitize. Files with trailing spaces in their filename can therefore fail to move on Windows even though the organizer documents pre-sanitization and the retry path attempts it.
  Evidence: `build_move_plan()` marks loose files with `is_file_item`; `_move_plan_item()` only calls `strip_trailing_spaces(src)` in the `else` directory branch. The file branch goes directly to `os.rename` and fallback `shutil.move`, with no source-path update after sanitization.
  Fix: Sanitize file-item source components before hashing/planning and before the file move, update the plan/journal to the renamed source, and apply the documented collision policy to the sanitized name. Preserve the existing directory behavior.
  Acceptance: Windows tests create loose files and nested files with trailing-space components; generated plans point to the sanitized source and apply successfully, with no duplicate/orphan record. Ordinary files remain unchanged.
  Confidence: Verified
  Effort: M

- [ ] P2 — Retry cleanup silently leaves partial file destinations in place
  Category: reliability
  Where: `organize_run.py:1342-1402`
  Problem: When an error record marks `partial_dest_exists`, retry unconditionally calls `shutil.rmtree(dest, ignore_errors=True)`. `rmtree` does not remove a partial destination that is a regular file (the observed file remains), so the subsequent move still collides and the retry is retained as failed instead of recovering.
  Evidence: A probe created a regular destination file and ran the exact `shutil.rmtree(path, ignore_errors=True)` call; the file still existed afterward. `retry_errors()` has no `isfile`/unlink branch before `robust_move()`.
  Fix: Inspect the destination type with reparse-safe semantics and unlink a regular partial file, remove a directory only when it is an approved directory, and handle cleanup errors inside the retry try/except with a structured reason. Never delete an unrelated occupied destination.
  Acceptance: Retry fixtures with a partial file, partial directory, symlink, and unrelated occupied destination produce the documented safe outcome; a valid partial file is removed and the source is retried successfully without deleting unrelated data.
  Confidence: Verified
  Effort: S

- [ ] P2 — Duplicate move actions have no collision policy and give misleading failure feedback
  Category: reliability
  Where: `fileorganizer/dialogs/duplicates.py:596-605,937-946`
  Problem: Duplicate “move” uses raw `shutil.move(path, dest/basename)` without a unique-name/no-overwrite policy. On POSIX an existing same-name target can be replaced; on Windows it commonly raises. Both cases collapse into a generic failed count with no per-item outcome or recovery path.
  Evidence: The two dialog paths build the destination from `os.path.basename()` and call `shutil.move` directly; there is no existence/hash check, suffix allocation, confirmation, or result detail. A pair of different files with the same basename reaches this call.
  Fix: Route duplicate moves through the shared safe executor with canonical destination-root/protected checks and an explicit unique-suffix or no-overwrite conflict policy. Return per-item moved/skipped/conflict/error results and preserve an undo record.
  Acceptance: Same-basename/different-content fixtures on Windows and POSIX retain both files, display the chosen collision result, and can be undone; identical files follow the documented deduplication policy without silent replacement.
  Confidence: Verified
  Effort: M

- [ ] P2 — Cancelling a Python runner returns before stdout/stderr reader tasks finish
  Category: reliability
  Where: `src/FileOrganizer.UI/Services/PythonRunner.cs:126-159,221-271`
  Problem: On cancellation both text and NDJSON runners kill the child process and return immediately, leaving `stdoutTask` and `stderrTask` unawaited while `using` disposes the process/streams. Reader tasks can fault or continue invoking callbacks after cancellation, creating unobserved exceptions, stale UI events, and overlap with the next run.
  Evidence: The `OperationCanceledException` branches return before the later `Task.WhenAll(stdoutTask, stderrTask)` statement. The reader delegates still reference `process.StandardOutput/StandardError` and the NDJSON delegate can call the page callback.
  Fix: After killing the process, await/observe both reader tasks with cancellation-safe draining, suppress only expected cancellation/pipe errors, then dispose the process. Serialize start/cancel/restart state and prevent callbacks after cancellation.
  Acceptance: Repeated start/cancel/restart cycles leave no child process or unobserved task exception, deliver no stale item after cancellation, and allow the next run to consume its own events.
  Confidence: Verified
  Effort: M

- [ ] P2 — WinUI streamed result collections and log builders grow without bounds
  Category: perf
  Where: `src/FileOrganizer.UI/Views/Pages/SmartSortPage.xaml.cs:103`; `FilesPage.xaml.cs:76`; `CleanupPage.xaml.cs:159`; `DuplicatesPage.xaml.cs:116`; analogous media-page event handlers; `src/FileOrganizer.UI/Views/Pages/OrganizePage.xaml.cs:13,67-77,90-94`; `ToolboxPage.xaml.cs:14,64-83`
  Problem: Every file event is appended permanently to `ObservableCollection`/`ItemsRepeater` data and full stdout/log text is appended to `StringBuilder`. A large scan or verbose sidecar creates unbounded UI memory and progressively slower collection notifications, potentially exhausting the process despite list virtualization.
  Evidence: The handlers add one model per streamed item with no cap, paging, aggregation, or spill-to-disk policy; Organize/Toolbox retain all output text. UI display trimming is not present for these collections.
  Fix: Use bounded/paged or virtualized result storage, aggregate counters and recent errors, and optionally write the full log to a capped rotating file with a “show more/open log” action. Keep total counts and cancellation state available after older rows are evicted.
  Acceptance: A synthetic 100,000-event run keeps UI memory and update latency within configured limits, displays useful recent/error rows and accurate totals, and exposes the bounded full log without an unbounded in-memory string.
  Confidence: Verified
  Effort: L

- [ ] P2 — Keyboard focus visuals are disabled globally in every WinUI button style
  Category: a11y
  Where: `src/FileOrganizer.UI/App.xaml:219-291`
  Problem: Primary, Secondary, Ghost, Danger, and Icon button styles all set `UseSystemFocusVisuals=False`, and no replacement focus visual state is defined. Keyboard users cannot see which navigation/action control is focused, in either theme or high-contrast mode.
  Evidence: The style definitions explicitly disable system focus visuals at lines 232, 247, 261, 276, and 290; repository search found no matching custom focus border/visual state for these styles.
  Fix: Re-enable system focus visuals or add a theme-aware `Focused` visual with a sufficiently thick, high-contrast border/outline that does not rely on color alone. Validate buttons, navigation, text inputs, list selection, dialogs, and high-contrast mode.
  Acceptance: Keyboard-only traversal across every page exposes a visible focus indicator on every interactive element in all supported themes and Windows high-contrast settings, with no focus loss after dialogs close.
  Confidence: Verified
  Effort: M

- [ ] P2 — Subtle text and light danger-button colors fail WCAG AA contrast
  Category: a11y
  Where: `src/FileOrganizer.UI/App.xaml:42-45,71-75,140-155,180-185,263-276`; `src/FileOrganizer.UI/Services/ThemeService.cs:163-391`; uses in `MainWindow.xaml:31-33`, `DuplicatesPage.xaml:140`, `ToolboxPage.xaml:43`, `RAWPage.xaml.cs`, and `ComicsPage.xaml.cs`
  Problem: `SubtleTextStyle`/secondary status text uses low-contrast theme tokens at normal text size, and the light danger button foreground/background pair is below the normal-text AA threshold. This makes helper/status text and destructive actions difficult to read, with the failure varying across the seven themes.
  Evidence: Calculated foreground/background ratios from the shipped resources include Steam 2.51:1, OLED 2.16:1, Nord 3.50:1, Dracula 3.03:1, Light `#878f99` on `#f6f8fa` about 3.07:1, and light danger text about 4.39:1; these are below 4.5:1 for normal text. The styles are used on real page status/helper surfaces.
  Fix: Define semantic role/size tokens that meet WCAG AA on each actual surface in all seven themes, including nested cards/list rows and danger buttons. Add an automated contrast test over the resource/style pairs rather than checking only the base palette.
  Acceptance: Automated contrast tests pass for every normal/large text and control pair, and a theme matrix confirms helper/status text, hover/pressed danger states, and nested list/card surfaces remain legible.
  Confidence: Verified
  Effort: M

- [ ] P2 — WinUI title-bar button colors stay dark after switching to Light theme
  Category: visual
  Where: `src/FileOrganizer.UI/Views/MainWindow.xaml.cs:49-64`; `src/FileOrganizer.UI/Services/ThemeService.cs:68-126`
  Problem: The custom title-bar foreground, hover, and pressed colors are assigned as dark-theme constants during window construction. ThemeService updates resource brushes and `RequestedTheme` but never reapplies title-bar colors, leaving pale icons and dark hover surfaces on the light title bar (and stale colors after switching themes).
  Evidence: `MainWindow` sets literal `#e8ecf3`/dark colors once; `ThemeService.Apply()` contains no title-bar update. The Settings page exposes live theme switching including Light.
  Fix: Centralize title-bar color selection in ThemeService, derive normal/hover/pressed/inactive colors from the active semantic tokens, and invoke it on every theme apply and window activation change.
  Acceptance: Toggling Light and every dark theme updates normal, hover, pressed, and inactive title-bar buttons immediately with readable contrast and no stale color after navigation/restart.
  Confidence: Verified
  Effort: S

- [ ] P2 — WinUI crash logging is unbounded and can persist sensitive paths/secrets
  Category: reliability
  Where: `src/FileOrganizer.UI/App.xaml.cs:61-78`
  Problem: Each unhandled exception is appended to `%LOCALAPPDATA%\FileOrganizer\logs\fileorganizer_crash.log` without a size cap, rotation, retention limit, or redaction. A crash loop can exhaust disk, and exception messages/stack traces can retain user paths or accidentally propagated credentials.
  Evidence: `HandleUnhandledException()` calls `File.AppendAllText` on every crash; no byte-count, rotation, or secret/path redaction exists. The Python bootstrap has a 512 KB rotation policy, so the shell is inconsistent and less safe.
  Fix: Implement bounded rolling crash logs with atomic rotation and a maximum record count/size, redact known secret values and sensitive command-line/path data, and keep the last useful crash context without unbounded retention.
  Acceptance: A simulated repeated-crash test keeps the log below the configured cap, rotates deterministically, and proves API keys/tokens are absent while preserving exception type and actionable stack context.
  Confidence: Verified
  Effort: M

- [ ] P2 — Settings reports “Saved” even when LocalSettings persistence fails
  Category: reliability
  Where: `src/FileOrganizer.UI/Services/UserSettings.cs:23-41`; `src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml.cs:52-60`
  Problem: UserSettings catches all read/write exceptions and returns fallbacks or nothing, while the Settings page sets the status text to “Saved.” unconditionally after assigning values. Quota, corruption, or unavailable-storage failures therefore lose preferences on restart while falsely claiming success.
  Evidence: The setter catch blocks swallow persistence errors; the click handler performs assignments and immediately writes the success status without receiving a result. There is no retry, error state, or distinction between in-memory and durable settings.
  Fix: Return a success/error result from persistence, surface a calm actionable failure with retry, and state explicitly when only in-memory state changed. Preserve last-known-good values and test corrupt/unavailable storage.
  Acceptance: Injected LocalSettings failures show an error/retry state and never “Saved”; a successful save survives restart, and the status only changes to Saved after durable writes complete.
  Confidence: Verified
  Effort: M

- [ ] P2 — The repository has no automated CI gate for its documented baseline and release checks
  Category: testing
  Where: repository root (no `.github/workflows` or equivalent workflow); `src/build.ps1`; test/lint/type-check commands; roadmap claims at `ROADMAP.md:57-59`
  Problem: No CI workflow was found, although the roadmap describes CI. The isolated test suite passes, but lint/type/build failures and sidecar contracts are not automatically enforced, so regressions can merge without a Windows build or quality gate.
  Evidence: `rg --files` found no workflow directory/config. Baseline commands in this audit produced 614 passed/9 skipped tests only when using an isolated basetemp, 1,133 Ruff errors, 439 mypy errors, 963 pyright errors, and a failing WinUI wrapper; no automation reports or blocks them.
  Fix: Add Windows CI jobs using the supported Python/Qt environment and an isolated writable pytest basetemp, Ruff, mypy/pyright with an explicit ratchet policy, sidecar NDJSON/schema tests, and `pwsh src/build.ps1` on a pinned Visual Studio image. Publish artifacts/logs and keep credentials out of jobs.
  Acceptance: A pull request runs all gates, fails on new errors or build failure, publishes the shell artifact/test reports, and documents any temporary baseline ratchet so the error count cannot silently grow.
  Confidence: Verified
  Effort: L

- [ ] P2 — The default Windows pytest command exits nonzero during temp cleanup (pre-existing baseline)
  Category: testing
  Where: pytest invocation/configuration and Windows temp cleanup; repository test suite
  Problem: The normal test command completes the tests but exits with an access-denied cleanup exception, so a clean developer/CI invocation reports failure despite all test assertions passing.
  Evidence: Exact command `QT_QPA_PLATFORM=offscreen python -m pytest -q --disable-warnings` completed 614 passed and 9 skipped, then exited 1 with `PermissionError: [WinError 5] Access is denied` for `%TEMP%\pytest-of---\pytest-current`. Re-running with `--basetemp C:\Users\--\AppData\Local\Temp\FileOrganizer-audit-basetemp2` exited 0 with the same 614/9 result.
  Fix: Configure a per-run writable basetemp under the repository/CI workspace or otherwise identify and close the process/handle retaining `pytest-current`; ensure teardown removes only the run-owned directory and works under parallel/repeated runs.
  Acceptance: The exact default command exits 0 on a clean Windows checkout, still reports 614+ passing tests, and repeated/parallel runs do not leave locked `pytest-current` directories.
  Confidence: Verified
  Effort: M

- [ ] P2 — Ruff reports 1,133 pre-existing violations with no enforced ratchet (pre-existing baseline)
  Category: maintainability
  Where: repository Python source/tests; lint configuration (none found); `ruff check fileorganizer tests *.py`
  Problem: The repository-wide lint command fails with 1,133 findings, including 440 auto-fixable and 33 requiring unsafe fixes. Without a configured baseline/CI ratchet, dead imports, undefined names, and inconsistent code remain mixed with production paths and new violations can accumulate.
  Evidence: Exact command `ruff check fileorganizer tests *.py` returned `Found 1133 errors`, `440 fixable`, and `33 hidden unsafe fixes`. No workflow or checked-in lint configuration was found to make the failure actionable.
  Fix: Establish the supported Ruff version/configuration, triage unsafe versus mechanical fixes, remove or baseline existing findings with an explicit count, and fail CI on any newly introduced violation. Keep runtime-critical undefined-name findings covered by focused tests.
  Acceptance: The documented lint command has a reproducible zero/new-error policy, CI blocks regressions, and the tracked baseline decreases or is removed without suppressing real runtime errors.
  Confidence: Verified
  Effort: L

- [ ] P2 — mypy fails on 439 errors across 54 files with no type-check gate (pre-existing baseline)
  Category: maintainability
  Where: `fileorganizer/` and mypy configuration; command `mypy fileorganizer`
  Problem: Static typing is not release-enforceable: mypy exits 1 with hundreds of errors, including paths handling `None`, untyped external results, and incompatible collections that can conceal runtime defects.
  Evidence: Exact command `mypy fileorganizer` returned `Found 439 errors in 54 files (checked 78 source files)`. No CI job or explicit staged baseline policy was found.
  Fix: Define the supported mypy config and staged scope, fix high-risk boundary/module errors first, add typed protocols for sidecar JSON and providers, and ratchet the remaining count in CI until zero or a documented justified exception set.
  Acceptance: CI reports the count against a checked-in baseline, rejects increases, and the target release scope reaches zero errors with focused tests for any intentionally dynamic boundary.
  Confidence: Verified
  Effort: L

- [ ] P2 — pyright fails on 963 errors with no release type-safety gate (pre-existing baseline)
  Category: maintainability
  Where: `fileorganizer/` and pyright configuration; command `pyright fileorganizer`
  Problem: A second type checker fails broadly, so the repository has no consistent signal for missing names, incompatible optional values, or incorrect provider/sidecar contracts before release.
  Evidence: Exact command `pyright fileorganizer` returned `963 errors, 0 warnings, 0 informations`, exit 1. No workflow or checked-in baseline/ratchet was found.
  Fix: Choose the authoritative checker or reconcile both configurations, define Python version/dependency stubs, fix boundary errors in the selected release scope, and enforce a non-increasing baseline with CI annotations.
  Acceptance: The documented checker produces a reproducible baseline in CI, new errors fail the build, and the release scope reaches the selected zero-error/approved-exception target.
  Confidence: Verified
  Effort: L

- [ ] P2 — Critical classifier/sidecar/UI contracts have no direct regression coverage
  Category: testing
  Where: `tests/`; untested `classify_design.py`, `organize_run.py` replay/apply paths, `watch_run.py`, and `src/FileOrganizer.UI/Views/Pages/*`/`PythonRunner.cs`
  Problem: The 614-test suite exercises many Python helpers but has no direct tests for the DeepSeek batch schema/merge path, watch configuration/loop behavior, persisted move-plan safety, or WinUI page/runner orchestration. These are the exact boundaries where this audit found crashes, data loss, and threading failures.
  Evidence: Repository test-file search found no direct `classify_design` or C# UI/runner test project; the existing tests do not invoke the listed secondary pages or run the sidecar event/cancellation contract end to end. The baseline suite therefore passes while these defects remain reachable.
  Fix: Add pytest fixtures for malformed/valid sidecar NDJSON, classification response schemas, watch configs, generated plans, retry/journal/undo tampering, and collision/rollback behavior. Add a .NET testable runner/page-state layer or UI automation suite on an isolated virtual display for dispatch, cancellation, settings, and theme contracts.
  Acceptance: Each critical path has a deterministic regression test that fails for the current defect and passes after repair; CI executes the suite on Windows without a physical-display dependency.
  Confidence: Verified
  Effort: L

### P2 — Areas requiring a runtime/release pass

- [ ] P2 — WinUI runtime visual, keyboard, screen-reader, and all-theme matrix remains unaudited
  Category: testing
  Where: all routed pages under `src/FileOrganizer.UI/Views/Pages`; `src/FileOrganizer.UI/App.xaml`; `src/FileOrganizer.UI/Services/ThemeService.cs`; `src/build.ps1`
  Problem: Static review identified concrete theme/focus/contrast risks, but a full runtime matrix could not be executed: the prescribed build stopped at the missing Visual Studio MSBuild prerequisite, and operator-display isolation prohibits physical-display GUI walkthroughs. Runtime layout, modal/popover nesting, screen-reader announcements, keyboard order, high contrast, reduced motion, and live theme switching therefore still need direct verification.
  Evidence: The build baseline above exits before compilation, and no safe headless/virtual-display run was available in this audit environment. Static inspection covered route/page XAML and token definitions but cannot prove rendered behavior or accessibility-tree output.
  Fix: Provide a pinned Windows CI/virtual-display fixture that builds and launches every routed page, drives keyboard/focus and screen-reader/automation properties, checks high contrast and reduced motion, and captures automated contrast/layout assertions for all seven themes and nested surfaces.
  Acceptance: A repeatable headless/virtual-display matrix launches every route, exercises loading/empty/error/long-content/dialog states in every theme, verifies focus/automation announcements and reduced-motion behavior, and publishes failures as CI artifacts.
  Confidence: Verified
  Effort: L

- [ ] P2 — Clean-machine packaging, install, upgrade, rollback, and signing are unaudited
  Category: testing
  Where: `src/FileOrganizer.UI.sln`, `src/build.ps1`, `src/FileOrganizer.UI/FileOrganizer.UI.csproj`, repository packaging/release surface
  Problem: The audit verified source tests, static quality commands, and the build entry-point failure, but did not exercise a produced installer/package on a clean Windows machine. Installation prerequisites, Python/sidecar discovery, file associations, upgrade preservation of settings/credentials, uninstall cleanup, rollback, and artifact signing can fail outside the repository test environment.
  Evidence: No checked-in installer/release workflow or clean-machine smoke test was found; the available build wrapper cannot currently produce an artifact in this environment. Existing `bin/obj` outputs do not prove a clean install or upgrade path.
  Fix: Define the supported package format and signing/verification process, add a clean-VM install/uninstall/upgrade/rollback smoke suite, verify sidecar discovery and migrations, and publish hashes/signatures plus a release manifest.
  Acceptance: A clean Windows VM installs the release artifact, launches every routed page, runs a representative scan, upgrades without losing safe settings/credentials, uninstalls cleanly, and verifies the signed/hash-pinned artifact; a failed upgrade rolls back without data loss.
  Confidence: Verified
  Effort: L

### P3 — Documentation consistency

- [ ] P3 — README feature matrix, theme count, and architecture description are stale
  Category: docs
  Where: `README.md:32-37,215-239`; current route map in `src/FileOrganizer.UI/Views/MainWindow.xaml.cs:83-105`; theme picker in `src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml:21-74`
  Problem: The README calls Files, Duplicates, Photos, Watch, and Toolbox placeholders, says there are six dark themes and no WinUI theme picker, and describes an architecture with only Cleanup/Placeholder pages. The current shell routes those pages and exposes seven themes including Light, so onboarding and support guidance gives users the wrong product model.
  Evidence: The route map wires the named pages, SettingsPage contains the seven-theme picker, and README statements contradict both files. The mismatch is visible before any optional feature is configured.
  Fix: Update the feature matrix, screenshots/walkthrough language, theme list, architecture diagram, and known-limitations section to match the routed shell and actual Python sidecars. Clearly distinguish read-only pages and incomplete actions until the P1 Cleanup/Duplicates flow is resolved.
  Acceptance: A fresh reader can follow README to the current route names/themes and receives no “placeholder” or “six themes/no picker” claim that contradicts the source; CI or a documentation check flags route/theme drift.
  Confidence: Verified
  Effort: S

## Research-Driven Additions

### P1 — Safety and release foundations

- [ ] P1 — Lock and attest the resolved Python dependency set
  Why: Broad lower bounds plus many optional packages make clean installs and security remediation non-reproducible, even though the application parses untrusted archives, images, fonts, and documents.
  Evidence: requirements.txt has no exact resolution, hashes, or lock file and includes unpinned archive/media/metadata dependencies. Pillow states that security fixes are not expected to be backported; the py7zr changelog consulted on 2026-08-10 lists fixed arbitrary-file-write, decompression-bomb, and complexity-DoS vulnerabilities; fonttools documents CVE-2025-66034. The PyPA pylock.toml specification and pip-audit provide compatible foundations.
  Touches: requirements.txt; a checked-in pylock.toml or equivalent supported lock artifact; packaging/build scripts; CI; SBOM/license output; clean-machine install tests.
  Acceptance: A clean supported Python/Windows environment installs only the locked, hash-verified graph; pip-audit/OSV and license checks run against the resolved graph; vulnerable archive/font/image versions fail the gate; updating a dependency produces a reviewed lock diff and a reproducible release manifest.
  Complexity: M

- [ ] P1 — Establish a versioned, schema-validated WinUI-to-Python sidecar protocol
  Why: Multiple root runners emit ad hoc NDJSON while the WinUI shell parses generic JSON; a malformed event, missing field, or changed terminal state can crash or strand a page even when the Python work is recoverable.
  Evidence: src/FileOrganizer.UI/Services/PythonRunner.cs and SidecarRunner.cs forward parsed JsonDocument values without a shared event schema; each *_run.py defines its own payload shape. tests/test_sidecar_contracts.py checks event names and fatal/cancel behavior but does not define versioned field constraints. Ollama’s structured-output guidance and PyPA/pluggy contract patterns support schema-first boundaries.
  Touches: all root *_run.py sidecars; src/FileOrganizer.UI/Services/PythonRunner.cs; src/FileOrganizer.UI/Services/SidecarRunner.cs; tests/test_sidecar_contracts.py; a shared Python schema and C# DTO/validation layer.
  Acceptance: Every sidecar begins with a protocol version/capability handshake and emits validated progress/item/log/error/terminal records with required fields, bounded strings, totals, and stable error codes; unknown events are isolated, malformed records cannot terminate the run, cancellation has one deterministic terminal state, and fixture tests cover every routed sidecar plus the C# parser.
  Complexity: L

### P2 — Scale, resilience, and explainability

- [ ] P2 — Make community catalog updates authenticated, bounded, atomic, and offline-first
  Why: A startup catalog update should never be able to consume unbounded resources, import tampered classification data, or make a local-only workflow depend on network availability.
  Evidence: fileorganizer/workers.py:2817-2930 calls the GitHub Releases API, selects asset_fingerprints.json by name, reads the entire browser_download_url response, and passes the parsed object to asset_db.import_community_json(); there is no signature/checksum verification or staged rollback. The active roadmap item covers the missing byte limit, while TagSpaces documents offline-first operation.
  Touches: fileorganizer/workers.py; asset_db.py import_community_json; catalog sync state/migrations; settings/diagnostics UI; catalog fixtures and network-failure tests.
  Acceptance: Startup completes without network access and reports a non-blocking offline state; the response has a hard byte cap and schema/version limits; the artifact is accepted only from the pinned owner/release asset and a verified checksum/signature; import occurs in a staging database with atomic swap, backup, rollback, opt-out, and visible last-success metadata.
  Complexity: M

- [ ] P2 — Persist and resume cleanup/duplicate review results with stale-file revalidation
  Why: Long secondary scans currently stream results into in-memory UI collections, so a restart or cancellation loses the user’s review context and encourages repeating expensive scans or acting on stale paths.
  Evidence: CleanupPage.xaml.cs and DuplicatesPage.xaml.cs append streamed results to page-owned collections and expose no persisted scan ID, export, keeper decision, or resume path. The active P1 item addresses the missing action controls and the active P2 item addresses unbounded collections; this addition supplies the durable review artifact modeled by Czkawka result/cache workflows and community “review before delete” feedback.
  Touches: cleanup_run.py; dedup_run.py; src/FileOrganizer.UI/Views/Pages/CleanupPage.*; DuplicatesPage.*; a versioned SQLite review-results store; apply/quarantine adapters; tests for restart, stale paths, and hash changes.
  Acceptance: A scan can be paused/cancelled, closed, reopened by scan ID, exported/imported, and resumed without losing selections; before any action, every path is rechecked for existence, size, mtime, and hash/reference policy; changed or missing files become explicit stale results and cannot be deleted/moved; the persisted store is bounded and migratable.
  Complexity: L

- [ ] P2 — Add a capability and dependency health matrix to every shell workflow
  Why: Optional extractors and external tools are intentionally supported, but a missing verifier can currently look like a clean result until a sidecar emits a late error or a legacy log mentions an absent package.
  Evidence: requirements.txt mixes core and optional packages; fileorganizer/scan_mixin.py:485-495 only logs missing capabilities, while sidecars such as raw_run.py, comics_run.py, music_run.py, books_run.py, and fonts_run.py emit different missing-dependency messages. WinUI pages advertise optional ISBN, AcoustID, RAW, archive, and media behavior without a shared preflight capability report.
  Touches: fileorganizer/metadata.py and metadata_extractors; scan_mixin.py; all *_run.py capability checks; WinUI Home/Settings and page preflight models; tests under tests/test_sidecar_contracts.py and capability fixtures.
  Acceptance: Before a scan, the UI and CLI expose a deterministic matrix of capability, dependency/tool, detected version, scope, online requirement, and remediation; unavailable capability is shown as “not checked/unavailable,” never “no findings”; sidecars use one machine-readable capability error schema and the matrix is covered by a clean-environment test.
  Complexity: M

- [ ] P2 — Persist classification provenance and replayable evaluation records
  Why: FileOrganizer already stores marketplace provenance and adaptive corrections, but a user cannot reconstruct which provider/model/prompt/taxonomy version produced a move suggestion or measure whether corrections improve future batches.
  Evidence: fileorganizer/provenance.py records source-domain/first-seen asset facts, while organize_run.py MovePlan/journal records paths, status, hashes, and run IDs without provider, model, prompt/schema, taxonomy, or response identifiers. fileorganizer/adaptive_corrector.py stores correction hints but not a replayable evaluation record. Human-in-the-loop research and C2PA/IPTC interoperability both favor explicit decision provenance.
  Touches: organize_run.py MovePlan/journal/report schema; classify_design.py and provider adapters; llm_cache.py/adaptive_corrector.py; review UI/export; migration and privacy-redaction tests.
  Acceptance: Each AI-assisted classification can export a redacted JSONL record containing input fingerprint, provider/model, prompt/schema/taxonomy hashes, response hash, confidence, user correction, final decision, and timestamps; records survive restart and schema migration, can be replayed against fixtures, and never contain API keys or raw sensitive paths unless the user explicitly exports them.
  Complexity: M

- [ ] P2 — Add an NTFS USN-backed incremental index path for large Windows volumes
  Why: Folder fingerprints and watchdog events reduce repeat work but do not provide a durable volume-scale change stream for the multi-terabyte libraries documented in CLAUDE.md and the repository’s real-world notes.
  Evidence: asset_db.py build/verify flows still walk and hash the selected tree, fileorganizer/folder_cache.py is folder/mtime based, and fileorganizer/watch_mode.py maintains event/debounce state rather than a volume journal. Microsoft’s USN Change Journal records file changes per NTFS volume; Czkawka/fclones/rmlint show persistent cache and staged-hash patterns, while DataHoarder users report scans across multi-terabyte drives as a practical pain point.
  Touches: asset_db.py; folder_cache.py; watch_mode.py/watch_daemon.py; Windows-specific index service; SQLite schema; full-scan fallback and benchmark tests.
  Acceptance: On NTFS, a restarted incremental scan resumes from a persisted journal ID, processes only changed/created/deleted paths, detects journal wrap/volume changes and automatically rebuilds, produces the same catalog/dedup results as a full scan, and exposes progress/lag; non-NTFS, network, and unsupported-volume paths use the existing full-scan fallback without data loss.
  Complexity: L
```

</details>
