# ROADMAP -- FileOrganizer

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

- [ ] **`shutil.move` cross-drive leaves partial copies on failure**: Source is always safe (rmtree
  never runs on exception), but a partial destination exists. `retry_errors()` handles this.

- [ ] **Every move must be journaled**: `organize_moves.db` (SQLite) with `--undo-last N` and
  `--undo-all` support. Without this, a partial run is irreversible.

- [ ] **Pre-flight validation prevents >90% of errors**: `--validate` before `--apply` surfaces
  trailing-space and long-path issues in advance.

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

- [ ] **Remaining**: WinUI 3 Settings → Watch Mode tab (enable/disable, debounce slider, log viewer).
  Task Scheduler registration for Windows background task startup.

- [ ] **Impact**: 4 | **Effort**: 4 (core 2 + UI 2) | Risk: debounce stability on network drives

- [ ] **Parity with**: [S1] LlamaFS, [S5] aifiles, [S20] Hazel, [S21] File Juggler

**NEXT-3: Hazel-style rule chains** ✓ Core shipped
Multi-condition chains: "if source matches X AND LLM confidence < 70 AND file size > Z, move to
A THEN rename as B THEN webhook C". Nested conditions with AND/OR. AST-based.

- [ ] **Remaining**: GUI rule builder (visual condition/action editor). Integration into organize_run.py
  pipeline (evaluate chains before classification, skip/move based on rules).

- [ ] **Impact**: 4 | **Effort**: 4 (core 3 + UI 1) | Parity with: [S20] Hazel, [S21] File Juggler, [S8] organize-cli

- [ ] Source: [S20] https://www.noodlesoft.com/hazel/ , [S21] https://www.filejuggler.com/features/

**NEXT-4: Dry-run simulation (all operations)** ✓ Core shipped
Every CLI command and GUI action must have a full dry-run path that previews the exact list of
moves, renames, and deletes without touching the filesystem. Emit an editable JSON plan file
before commit.

- [ ] **Remaining**: GUI integration (PreflightDialog Step 6 with operation list + toggles).
  organize_run.py CLI flags (--dry-run, --plan-file, --commit).

- [ ] **Impact**: 4 | **Effort**: 2 (core 1 + UI 1) | Parity with: [S8] organize-cli `sim` mode, [S20] Hazel "Test Rule"

**NEXT-5: Minimal-diff re-scan index** ✓ Core shipped
Cache folder fingerprint + mtime from each run. On re-scan, skip folders whose fingerprint and
mtime are unchanged. Reduces re-run cost ~70% on large libraries where most items are already
classified.

- [ ] **Remaining**: Integration into organize_run.py (--skip-unchanged, --invalidate-cache flags).

- [ ] **Impact**: 4 | **Effort**: 3 (core 2 + integration 1) | Parity with: [S1] LlamaFS minimal-diff index

- [ ] Source: [S1] https://github.com/iyaja/llama-fs

**NEXT-6: Parallel LLM calls** ✓ Core shipped
Batch DeepSeek/GitHub Models API calls concurrently via `asyncio` + `aiohttp`. Current serial
approach is the primary throughput bottleneck on 19,531-item loose-files runs.

- [ ] **Remaining**: Integration into organize_run.py classification pipeline (CLI --parallel flag,
  settings UI for concurrency/batch tuning). Benchmarking on real large runs (1000+ folders).

- [ ] **Impact**: 4 | **Effort**: 3 (core 2 + integration 1)

**NEXT-7: Adaptive learning from corrections** ✓ Core shipped
When a user corrects a classification, record the correction in `corrections.json` keyed by
folder fingerprint AND extracted keyword pattern. On next run: exact-fingerprint matches
auto-apply the correction; keyword-pattern matches inject it as a few-shot example into the batch prompt.

- [ ] **Remaining**: GUI hook in rename dialog (offer "correct" button). Integration into classify pipeline
  (check apply_correction before LLM, inject few-shot into system prompt).

- [ ] **Impact**: 4 | **Effort**: 3 (core 2 + integration 1) | Parity with: [S6] thebearwithabite adaptive learning loop

- [ ] Source: [S6] https://github.com/thebearwithabite/ai-file-organizer

**NEXT-8: Scheduled scans per profile** ✓ Core shipped
Register scan profiles with Windows Task Scheduler (or launchd/systemd on macOS/Linux).

- [ ] **Remaining**: GUI hook (Settings → Schedules), CLI flag --schedule, background daemon integration.

- [ ] **Impact**: 3 | **Effort**: 3 (core 3 + integration 0)

- [ ] Source: [S21] File Juggler task scheduling, [S20] Hazel run-at-schedule

- [ ] **Remaining**: Integration into asset classifier (use font requirements and parameter count as routing signals).

- [ ] **Impact**: 4 | **Effort**: 2 (core 2 + integration 0)

**NEXT-11: Video metadata deep routing (FFmpeg expansion)** ✓ Core shipped
Extend `video_extractor.py` with intelligent routing: 9:16 vertical → `Social Media`, 
looping ≤15s + ProRes/DNXHD → `Motion Graphic`, broadcast codec → `Broadcast / Cinema Stock`,
duration > 5min → `Tutorial Video`, 60fps 4K+ → `High-Performance`, etc.

- [ ] **Remaining**: Integration into classify pipeline (call analyze_video_metadata on .mp4/.mov/.mxf files before LLM).

- [ ] **Impact**: 4 | **Effort**: 2 (core 2 + integration 0) | Depends on: N-9 (ffprobe integration)

- [ ] Source: [S15] digiKam FFmpeg pipeline, [S44] Czkawka v11.0.0, [S34] `docs/archive/research/RESEARCH_IDEAS.md`

**NEXT-12: LLaVA visual classification**
Route image and PDF mimes to a local multimodal model (`gemma3:4b` or `qwen3.5:4b` — both
support Ollama structured outputs via `format=schema` as of v0.22.1 [S77]) when extension-only
confidence is low. The preview image path is already known from `asset_db.find_preview_image()`.
Pass `format=ClassifyResult.model_json_schema()` to `ollama.chat()` to guarantee schema-valid JSON
without the current regex extraction fallback.

- [ ] **Impact**: 4 | **Effort**: 4

- [ ] Source: [S2] QiuYannnn Local-File-Organizer, [S6] thebearwithabite, [S77] Ollama structured outputs

**NEXT-13: Confidence calibration display**
Show per-category probability bars in the preview panel. Let user click a runner-up label to
override AI suggestion. Record overrides as corrections (feeds NEXT-7).

- [ ] **Impact**: 4 | **Effort**: 2

**NEXT-14: Two-stage AI prompt (file type then subcategory)**
Stage 1 asks "what file type is this template?" (AE/Premiere/PSD/AI/etc.) with zero context
needed. Stage 2 uses the confirmed file type as context for a tighter subcategory prompt.
Current single-stage approach conflates file-type detection with subcategory selection, causing
cross-type misclassifications (e.g., a PSD classified as an After Effects template).

- [ ] **Impact**: 4 | **Effort**: 2

- [ ] Source: [S36] CLAUDE.md, existing `classify_design.py` analysis

**NEXT-17: Marketplace enrichment expansion**
Extend `marketplace_enrich.py` beyond Envato to: Creative Market (API available), Freepik (API
key), Motion Array, FilterGrade, Shutterstock, Adobe Stock. Each needs a URL pattern + parser.
mnamer [S58] models exactly this pattern in `mnamer/providers.py` (Provider ABC) +
`mnamer/endpoints.py` (low-level wrappers for OMDb/TMDb/TVDb/TvMaze with ID caching, error
handling, and retry logic) — port the Provider ABC verbatim and add one subclass per
marketplace.

- [ ] **Impact**: 4 | **Effort**: 3

- [ ] Source: [S34] `docs/archive/research/RESEARCH_IDEAS.md`, [S33] `docs/archive/research/RESEARCH.md`, [S58] mnamer Provider ABC pattern

**NEXT-18: Marketplace update alerts**
For items with a known marketplace ID, periodically check if a newer version has been published.
Flag in UI: "Update available for 3 items in After Effects - Slideshow".

- [ ] **Impact**: 3 | **Effort**: 3

**NEXT-20: Cross-library fingerprint dedup**
Compare G:\ + I:\ (and external drives) by `folder_fingerprint` SHA-256 across roots. Show a
merge/keep/archive dialog per duplicate group.

- [ ] **Impact**: 4 | **Effort**: 3

- [ ] Source: [S11] fclones cross-library pattern https://github.com/pkolaczk/fclones

**NEXT-21: Version-aware dedup**
If two items share a marketplace ID but have different file counts or fingerprints, one is likely
a newer version. Keep the one with more files; archive the other with a reason note.

- [ ] **Impact**: 3 | **Effort**: 2

**NEXT-23: Drag-and-drop reclassification**
Drag any item from one category to another in the Browse tab tree. Records the correction in
`corrections.json` and increments a `user_corrections` counter in the DB. Same-fingerprint items
in future runs auto-apply the correction without AI.

- [ ] **Impact**: 4 | **Effort**: 3

**NEXT-24: Undo history visualizer**
"History" tab: timeline of all moves from `organize_moves.db` with per-item or per-run undo.
Show: timestamp, source, destination, confidence score, undo button. Completes N-6.

- [ ] **Impact**: 5 | **Effort**: 3

- [ ] Source: [S3] hyperfield/ai-file-sorter undo-after-close

**NEXT-26: Batch rename with preview**
GUI dialog showing old name -> proposed canonical name (`{CAT_CODE}_{ID}_{CLEAN_NAME}`) for all
items in a category, with inline edit before committing. CLI: opt-in `--rename` flag. mnamer
[S58] already has the template formatter (`MetadataMovie.__format__()` with regex-based
placeholder substitution + `{name}`, `{year}`, `{season:02d}` style padding/case converters)
and a `--test` dry-run path — both directly portable to the GUI preview dialog.

- [ ] **Impact**: 3 | **Effort**: 2

- [ ] Source: [S22] Adobe Bridge batch rename, [S15] digiKam rename templates, [S58] mnamer
  `MetadataMovie.__format__()` + `--test` dry-run

**NEXT-32: Dedup similarity grouping improvements**
When running perceptual hash dedup (NEXT-19), group near-identical items into clusters before
presenting the merge/keep dialog. Use complete-linkage clustering: two items in the same cluster
only if every pair is within Hamming distance threshold. Prevents over-merging when a cluster
contains both a genuine duplicate and a similar-but-different item.

- [ ] **Impact**: 3 | **Effort**: 2 | **Depends on**: NEXT-19

- [ ] Source: [S44] Czkawka v11.0.0 similarity grouping overhaul, [S47] imagehash clustering patterns

**NEXT-61: IPTC 2025.1 AI metadata XMP sidecar writing**
Write IPTC 2025.1 AI metadata fields to `.xmp` sidecars using PyExifTool 0.5.6 (the only viable
Windows XMP writer). New fields: `Iptc4xmpExt:AISystemUsed` (store "FileOrganizer v8.x"), 
`Iptc4xmpExt:AIPromptInformation` (store classification prompt + category result), 
`Iptc4xmpExt:AIPromptWriterName` (store "FileOrganizer" or logged-in user). Also write standard
`XMP-dc:Subject` (keyword array), `XMP-xmp:Rating` (confidence as 1–5 stars), and 
`photoshop:Category` (for Adobe CC compatibility). **Requires**: ExifTool ≥12.15 on PATH.
Sidecars survive NTFS copy-with-robocopy-/COPYALL; add to documentation.

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT

- [ ] Source: [S114] IPTC 2025.1 AI fields spec (Nov 2025);
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

- [ ] **Impact**: 1 | **Effort**: 1 | **Tier**: NEXT | **Blocks**: v9.0 release

- [ ] Source: [S117] PyMuPDF 1.27.2.3 license (AGPL-3.0) https://pypi.org/pypi/pymupdf/json

**NEXT-65: WinAppSDK 2.0.1 SystemBackdropElement**
Use `SystemBackdropElement` (placed FrameworkElement, not full-window) to apply Mica/Acrylic
backdrop to specific panels in WinUI shell. This allows in-content Mica effect on Browse tab,
Settings panel, or Apply Review dialogs — matching modern Windows 11 UI patterns without
full-window backdrop blur performance hit. Replaces the current backdrop-on-window pattern with
more granular control. This is a UX polish task with low effort; high visual impact.
**Depends on**: NEXT-39 (WindowsAppSDK 2.0.1).

- [ ] **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-39

- [ ] Source: [S121] WinAppSDK 2.0.1 release notes (April 29, 2026);
   [S122] SystemBackdropElement docs https://learn.microsoft.com/en-us/windows/winui/api/microsoft.ui.xaml.media.systembackdropelement

**NEXT-66: FolderPicker.PickMultipleFoldersAsync**
WinAppSDK 2.0.1 adds `FolderPicker.PickMultipleFoldersAsync()` on the standard `FolderPicker` type
(new in 2.0.1; was preview-only in 1.x). Integrate into SourcePanel to allow multi-folder source
selection in a single picker dialog. Users can now drag multiple folders into FileOrganizer in one
interaction, reducing friction for multi-project workflows. Saves a separate PickFolderAsync call
for each folder. Low-effort UX improvement; high convenience value.
**Depends on**: NEXT-39 (WindowsAppSDK 2.0.1).

- [ ] **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-39

- [ ] Source: [S123] WinAppSDK 2.0.1 FolderPicker API docs

**NEXT-68: Task Scheduler-based watch mode MVP**
Implement watch-mode daemon registration via Windows Task Scheduler (not a Windows Service).
Register `FileOrganizer_WatchMode` task with logon trigger + indefinite duration using 
`win32com.client.Dispatch('Schedule.Service')` (Task Scheduler 2.0 COM API) or `schtasks.exe`.
This runs the watch daemon at user logon without requiring admin elevation. Use `watchfiles` v1.1.1
(NEXT-60) for filesystem monitoring; async loop with 60-second "deep-quiet protocol" (wait for
stability before applying moves). Task runs as the logged-in user, with standard `%APPDATA%\FileOrganizer`
settings access. **Upgrade path**: provide `--as-windows-service` flag for future v9.x to install
as `LocalService`; this MVP is user-only. **Depends on**: NEXT-60 (watchfiles foundation).

- [ ] **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Unblocks**: NEXT-1 (partial) | **Depends on**: NEXT-60

- [ ] Source: [S126] Task Scheduler 2.0 API https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page;
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

- [ ] **Impact**: 5 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-39 | **Unblocks**: NEXT-71, NEXT-72

- [ ] Source: [S135] open_clip library https://github.com/mlfoundations/open_clip (ViT-L-14 zero-shot 79.2%
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

- [ ] **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-69 | **Unblocks**: L-1

- [ ] Source: [S138] Chroma v0.5.6 https://github.com/chroma-core/chroma (persistent SQLite backend;
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

- [ ] **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-69 | **Unblocks**: L-3, NEXT-73

- [ ] Source: [S140] Qwen2.5-VL-7B model card https://huggingface.co/Qwen/Qwen2.5-VL-7B (0.5 TB param
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

- [ ] **Impact**: 4 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-71 | **Unblocks**: NEXT-73

- [ ] Source: [S142] llama.cpp KV-cache persistence docs https://github.com/ggerganov/llama.cpp#kv-cache-reuse-strategy
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

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: NEXT-74, NEXT-75

- [ ] Source: [S144] loguru v0.7.2 https://github.com/Delgan/loguru (JSON sink via custom formatter;
   trace ID propagation pattern in docs; ~2.5 MB on disk per 100K logs);
   [S145] FileOrganizer telemetry design (NEXT-73 anchor for observability tier)

**NEXT-74: Prometheus metrics export for performance monitoring**
Emit Prometheus-format metrics to a local HTTP endpoint (`http://localhost:9999/metrics`). Track:

- [ ] `fileorganizer_classify_duration_seconds` (histogram; 0.1 ms — 10 s buckets)

- [ ] `fileorganizer_files_moved_total` (counter; cumulative)

- [ ] `fileorganizer_classification_confidence` (histogram; 0.5–1.0 quantiles)

- [ ] `fileorganizer_cache_hit_ratio` (gauge; thumbnail cache)

- [ ] `fileorganizer_gpu_vram_used_bytes` (gauge; if CUDA/ROCm active)
Use `prometheus-client` (PyPI, v0.20.0+, April 2026). Metrics accessible to external monitoring tools
(Grafana, Prometheus server) via scrape endpoint. This is **optional telemetry**: user can opt-in via
Settings checkbox "Enable metrics export". Metrics are **not sent anywhere**; they're only available to
local consumers on the machine. Enables power users to create custom dashboards for their organize runs
(e.g., "batch performance over time").

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-73 | **Unblocks**: observability tier

- [ ] Source: [S146] prometheus-client PyPI https://pypi.org/project/prometheus-client/ (v0.20.0 supports
   histogram quantiles; ASGI integration via starlette)

**NEXT-75: Sentry SDK crash reporting (opt-in)**
Integrate `sentry-sdk` (v1.54+, May 2026) for crash reporting **only on explicit user consent**. When
FileOrganizer encounters an unhandled exception, present a dialog: "Error: [msg]. Send crash report to help
us improve? Yes/No/Always". If "Yes", attach the traceback + FileOrganizer version + OS info + Qwen model
version (if active) to a Sentry event; post to a private Sentry project. **No file paths or classification
results are sent**; errors only. Rate-limit: max 1 error report per hour per user. This **must be opt-in**
and clearly labeled. Enables rapid identification of VLM model compatibility issues (e.g., "Qwen2.5-VL
crashes on ARM64 Macs") without phoning home constantly.

- [ ] **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-73 | **Unblocks**: reliability tier

- [ ] Source: [S147] sentry-sdk v1.54 https://github.com/getsentry/sentry-sdk-python (PII stripping via
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

- [ ] **Impact**: 3 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-39 (optional USD 26.05 runtime) | **Unblocks**: later 3D specialist tier

- [ ] Source: [S150] KhronosGroup/glTF:specification/2.0 (JSON schema for glTF; Draco extension; ~150 KB per asset typical);
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

- [ ] **Impact**: 3 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: optional `dcraw` or ImageMagick

- [ ] Source: [S156] Adobe Digital Negative (DNG) spec https://www.adobe.io/content/dam/udp/assets/open/standards/TIFF_DNG/DNG_1_7_1_spec.pdf
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

- [ ] **Impact**: 4 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: NEXT-82–85 (distribution tier)

- [ ] Source: [S161] Microsoft Authenticode documentation https://learn.microsoft.com/en-us/windows/win32/seccrypto/authenticode;
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

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-81 (signing architecture) | **Unblocks**: NEXT-84 (Homebrew)

- [ ] Source: [S164] Apple Gatekeeper docs https://developer.apple.com/documentation/security/gatekeeper;
   [S165] macOS notarization workflow https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution;
   [S166] Homebrew Cask requirements (code signing prerequisite)

**NEXT-83: Multi-platform CI/CD matrix builds (Windows/macOS/Linux)**
Restructure `.github/workflows/release.yml` to build FileOrganizer.exe (Windows), FileOrganizer.app (macOS),
and FileOrganizer.AppImage (Linux) in parallel using GitHub Actions matrix strategy. Specify Python 3.13,
PyInstaller 6.20+, and platform-specific tools (signtool for Windows, codesign for macOS, linuxdeploy for Linux).
Each build produces signed, ready-to-distribute binaries. This is the **foundation for multi-platform distribution**
(v9.1+). Build time: ~15 min per platform (45 min total, parallelized). Store all artifacts in release assets.
Enables one-button release across all platforms.

- [ ] **Impact**: 5 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-81, NEXT-82 | **Unblocks**: NEXT-84–86

- [ ] Source: [S167] GitHub Actions matrix builds https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idstrategmatrix;
   [S168] PyInstaller cross-platform documentation https://pyinstaller.org/en/stable/common-issues-and-support.html#i-can-t-import-my-module-using-the-imports-statement;
   [S169] FileOrganizer:.github/workflows/release.yml (current single-platform pattern)

**NEXT-84: macOS Homebrew Cask submission + maintenance**
Create and submit a Homebrew Cask formula for FileOrganizer. Once `NEXT-82` (macOS signing) is complete,
submit a PR to `homebrew/cask` with a `fileorganizer.rb` formula. Formula specifies download URL, DMG hash,
and desktop app target. Effort is minimal (~30 min review process). Once merged, users can install via
`brew install fileorganizer` and auto-updates are managed by Homebrew (user runs `brew upgrade`). This is
**high-value low-effort** distribution: ~5% macOS user base discovers via Homebrew (second most popular
macOS package manager after App Store). Pairs with NEXT-85 for Linux distribution parity.

- [ ] **Impact**: 3 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-82 (signed app) | **Unblocks**: enterprise macOS adoption

- [ ] Source: [S170] Homebrew Cask guidelines https://docs.brew.sh/Cask-Cookbook;
   [S171] Homebrew Cask submission workflow (PR to homebrew/homebrew-cask);
   [S172] Example formula (existing OSS projects)

**NEXT-85: Linux AppImage packaging + GPG signature**
Bundle FileOrganizer as a portable `FileOrganizer-9.x.x-x86_64.AppImage` using `linuxdeploy` +
`linuxdeploy-plugin-qt`. Single file (~150 MB) runs on any glibc 2.23+ system (Ubuntu 16.04+, Debian 9+,
Fedora 25+). No installation needed; users download and run. GPG-sign the AppImage: `gpg --armor --detach-sign
FileOrganizer*.AppImage` → ships .asc file for verification. This **expands reach to ~25% Linux user base** with
zero friction. Users can also run in bubblewrap sandbox for security. Defer Snap/Flatpak to community
contributions (high maintenance burden). AppImage is the **community standard** for cross-distro portability.

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-83 (CI/CD matrix) | **Unblocks**: Linux user adoption

- [ ] Source: [S173] AppImage documentation https://docs.appimage.org/;
   [S174] linuxdeploy + linuxdeploy-plugin-qt https://github.com/linuxdeploy/linuxdeploy;
   [S175] GPG signature verification pattern

**NEXT-86: WinSparkle auto-update integration (Windows)**
Integrate WinSparkle (Windows port of Sparkle) for delta-update downloads. Add to `requirements.txt`:
`pysparkle>=1.0` (or equivalent C++ binding). On startup, check releases.json from GitHub Releases API for new
versions. If update available, download delta patch (~5–20 MB vs full 150 MB binary); apply in background;
restart on next close. This provides **seamless auto-updates with 80–90% bandwidth savings** (delta patching).
Users never manually download; v9.0.1 → v9.0.2 is transparent. Pairs with NEXT-87 (macOS Sparkle) for
cross-platform auto-update parity.

- [ ] **Impact**: 4 | **Effort**: 3 | **Tier**: NEXT | **Depends on**: NEXT-81 (code signing for update verification) | **Unblocks**: user delight (auto-updates)

- [ ] Source: [S176] WinSparkle documentation https://github.com/vslavik/winsparkle;
   [S177] Delta patching strategy (reduce download size);
   [S178] Auto-update security (signature verification of patches)

**NEXT-87: Sparkle auto-update integration (macOS)**
Use Sparkle (de facto standard for macOS app updates) for macOS binary delta updates. Bundle Sparkle framework
in FileOrganizer.app. Configure `Info.plist` with update feed URL (GitHub Releases Atom feed). On startup,
Sparkle checks feed; if new version, prompts user or updates silently in background. Delta patching reduces
download to 5–20 MB. This is **expected behavior** for macOS users; builds professional polish. Pairs with
NEXT-86 for cross-platform parity.

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-82 (code signing) | **Unblocks**: macOS user delight

- [ ] Source: [S179] Sparkle framework https://sparkle-project.org/;
   [S180] macOS app auto-update best practices

**NEXT-88: REUSE.software compliance audit + LICENSES.md**
Implement REUSE.software compliance to satisfy GDPR/AGPL derivative work licensing requirements. Create
`LICENSES/` directory; store full text of all dependency licenses (MIT, Apache-2.0, BSD-3, LGPL-3.0, GPL-2.0, etc.).
Add SPDX headers to all source files: `# SPDX-License-Identifier: MIT`. Generate `LICENSES.md` via `pip-licenses
--format=markdown`. This **audits FileOrganizer's open-source compliance** and enables confident distribution
in regulated environments (enterprises, government). Effort is primarily documentation; zero code changes.

- [ ] **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Unblocks**: enterprise legal review

- [ ] Source: [S181] REUSE.software https://reuse.software/;
   [S182] SPDX license identifiers https://spdx.org/licenses/;
   [S183] pip-licenses tool https://pypi.org/project/pip-licenses/

**NEXT-89: Keyboard shortcuts customization panel**
Add Settings panel enabling users to customize all keyboard shortcuts (e.g., Ctrl+O to open, Ctrl+Shift+O
to organize, F5 to refresh). Store in `keyboard_shortcuts.json`. Reload on Settings change (no restart required).
Enable power users (and accessibility users who prefer keyboard navigation over mouse) to match their muscle
memory. This pairs with LATER-5 (full accessibility audit) as a low-hanging accessibility win.

- [ ] **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT

- [ ] Source: [S184] PyQt6 keyboard event handling (QKeySequence, QShortcut)

**NEXT-90: Basic accessibility audit (WCAG 2.1 Level A compliance)**
Run automated accessibility checker (axe DevTools for desktop, or WAVE) on FileOrganizer UI. Fix high-priority
failures: (1) Add alt text to all image buttons; (2) Ensure 4.5:1 color contrast on text; (3) Implement tab
navigation (focus rect visibility); (4) Test with keyboard-only (no mouse); (5) Test with screen reader (NVDA
on Windows, VoiceOver on macOS). This achieves **WCAG 2.1 Level A baseline** (minimum legal requirement in many
jurisdictions). Effort is primarily testing + incremental UI fixes. Full Level AA requires NEXT-89 (keyboard
shortcuts) + LATER-6 (screen reader testing).

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Unblocks**: LATER-5, LATER-6

- [ ] Source: [S185] WCAG 2.1 Level A criteria https://www.w3.org/WAI/WCAG21/quickref/;
   [S186] axe DevTools for automated a11y testing;
   [S187] PyQt6 accessibility APIs (QAccessibleInterface, QAccessibleWidget)

**NEXT-91: Privacy policy + telemetry opt-out mechanism**
Create a privacy policy (required for GDPR compliance if any telemetry is enabled in NEXT-74 + NEXT-75). Policy
must explicitly state: (1) no user data is collected by default; (2) metrics (NEXT-74) are local-only; (3) crash
reports (NEXT-75) are opt-in; (4) audit logs (NEXT-73) are stored locally in `%APPDATA%`. Add Settings toggle:
"Send crash reports to help improve FileOrganizer". Document data retention (audit logs kept 90 days, then deleted).
This is **legally required** in EU (GDPR), California (CCPA), and many other regions.

- [ ] **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Unblocks**: enterprise deployment

- [ ] Source: [S188] GDPR privacy policy template (example from Django/Flask projects);
   [S189] CCPA requirements https://oag.ca.gov/privacy/ccpa;
   [S190] Privacy policy best practices (Mozilla, EFF)

**NEXT-92: PyQt6 LGPL licensing disclosure (README + About dialog)**
Update `README.md` with explicit LGPL-3.0 disclosure for PyQt6. Add to About dialog: "FileOrganizer uses PyQt6 (LGPL-3.0)
— see https://www.riverbankcomputing.com/software/pyqt/". This is required for enterprise legal review. PyQt6 is dynamically
linked (not embedded), so users can theoretically recombine with alternate Qt bindings, but this is non-trivial. The LGPL
linkage exception allows proprietary distribution; document this clearly. Also audit and document GPL v2 mutagen conditional
load (N-62): "mutagen is optionally loaded only when processing audio files; it is not required for core functionality and
can be disabled at compile time". This brings FileOrganizer to **enterprise-ready licensing transparency** (6/10 → 8/10 readiness).

- [ ] **Impact**: 2 | **Effort**: 1 | **Tier**: NEXT | **Depends on**: NEXT-88 (REUSE compliance first)

- [ ] Source: [S219] PyQt6 licensing docs https://www.riverbankcomputing.com/software/pyqt/license/;
   [S220] LGPL-3.0 text https://www.gnu.org/licenses/lgpl-3.0.en.html

**NEXT-94: Ollama model benchmarking & auto-selection**
Add Settings panel feature: "Benchmark selected Ollama model" — runs inference speed test on 5 representative assets
and reports tokens/sec, memory, and classification time estimates. Auto-suggest model (Qwen2.5-VL vs Llama2 vs CLIP)
based on device RAM/GPU. Validates NEXT-88 (Ollama integration) and prepares for Q3 2026 new models (Wave 5c signal).

- [ ] **Impact**: 2 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-88

- [ ] Source: [S222] Ollama model benchmarking patterns (GitHub)

**NEXT-95: Cross-LLM provider abstraction layer (defensive vs Local-File-Organizer)**
Formalize provider-agnostic abstraction for switching between DeepSeek, OpenAI, GitHub Models, Ollama, and Claude.
Local-File-Organizer v2.0 (Wave 5b) already implements this—adopt similar pattern. Create `providers/base.py` (abstract),
`providers/deepseek.py`, `providers/openai.py`, `providers/ollama.py`. Future-proofs against API deprecations and dependency
churn (Wave 5c signal: llama.cpp, transformers, Ollama all evolving H2 2026).

- [ ] **Impact**: 4 | **Effort**: 4 | **Tier**: NEXT | **Depends on**: NEXT-88

- [ ] **Unblocks**: Competitive parity with Local-File-Organizer architecture

- [ ] Source: [S223] Local-File-Organizer provider routing https://github.com/curdriceaurora/fo-core

**NEXT-96: PyMuPDF licensing audit + alternative path (Artifex vs pdfplumber)**
Wave 5d audit reveals PyMuPDF hard-pinned with AGPL-3.0 risk (blocks commercial distribution). Two paths: (1) Artifex
commercial license (~$2–5K/yr); (2) Migrate to `pdfplumber` (MIT, pure Python, slower but adequate). Recommend: Keep
PyMuPDF for v9.0, plan pdfplumber migration for v10.x. Document in licensing disclosure.

- [ ] **Impact**: 3 | **Effort**: 2 | **Tier**: NEXT | **Depends on**: NEXT-88

- [ ] **Unblocks**: Commercial licensing (L-30)

- [ ] Source: [S224] PyMuPDF licensing https://pymupdf.io/0.25.0/faq/;
   [S225] pdfplumber MIT alternative https://github.com/jsvine/pdfplumber

---

**L-2: Few-shot teaching panel**
Drag a handful of files into a category to generate 3-5 in-context examples prepended to future
LLM prompts for that category. Stored in `few_shot_examples.json`. Depends on NEXT-21.

- [ ] **Impact**: 4 | **Effort**: 3

- [ ] Source: [S6] thebearwithabite adaptive learning

**L-3: OCR pipeline**
Tesseract OCR on import for screenshots and scanned PDFs. Pass extracted text to LLM for
content-based classification. Optional dependency -- skip gracefully if Tesseract not installed.

- [ ] **Impact**: 3 | **Effort**: 4

- [ ] Source: [S14] Paperless-ngx OCR, [S20] Hazel run-script action

**L-4: Natural-language search**
FTS5 full-text search over organized file paths + AI-generated descriptions. NL query interface
in Browse tab. Depends on NEXT-20 (Browse tab) and NEXT-5 (description stored at move time).
Two local prior-art repos materially shorten this:
PromptCompanion [S61] has the FTS5 BM25 schema + tuned weights (10.0, 1.0, 5.0, 2.0) and the
favorites/history pattern; Bookmark-Organizer-Pro [S55] has `services/nl_query.py` (NL → JSON
schema translation) + `services/rag_chat.py` (citation-aware summaries) + `services/hybrid_search.py`
(keyword + semantic fusion).

- [ ] **Impact**: 4 | **Effort**: 3

- [ ] Source: [S4] FileWizardAI https://github.com/AIxHunter/FileWizardAI , [S34] `docs/archive/research/RESEARCH_IDEAS.md`,
  [S61] PromptCompanion FTS5+BM25 schema, [S55] Bookmark-Organizer-Pro `nl_query.py` +
  `hybrid_search.py` + `rag_chat.py`

**L-5: Custom GGUF model registration**
GUI dialog to register any local `.gguf` model file. App auto-detects context window size and
chat template from GGUF metadata. Routes Ollama calls to the registered model.

- [ ] **Impact**: 3 | **Effort**: 3

- [ ] Source: [S3] https://github.com/hyperfield/ai-file-sorter

**L-6: Windows context menu integration**
Right-click any folder -> "Organize with FileOrganizer". Launches GUI pre-loaded with that
source folder, or triggers headless classify+apply via COM shell extension.

- [ ] **Impact**: 3 | **Effort**: 3

**L-7: Archive content inspection**
Complete `archive_extractor.py`: list top-level items inside ZIP/RAR/7z/tar, extract preview
image if present, feed filelist to keyword classifier. No extraction required for classification.
Add path-traversal guard (validate extracted paths against target dir) as part of this work.
EXTRACTORX [S59] has a clean `ExtractionService` threading + queue model and magic-byte archive
detection in `extractorx/archive.py` worth porting; note that EXTRACTORX itself does NOT ship
a path-traversal guard, so N-13 still owns that guarantee.

- [ ] **Impact**: 3 | **Effort**: 3

- [ ] Source: [S59] EXTRACTORX `extractorx/extractor.py` ExtractionService + `extractorx/archive.py`

**L-8: Bi-directional sync (symlink mode)**
Optional "keep original in place, symlink into organized tree" mode for users who cannot move
files. Useful for DJs and photographers whose DAM tools track original paths.

- [ ] **Impact**: 3 | **Effort**: 3

- [ ] Source: [S9] TagStudio non-destructive philosophy

**L-9: GPU quantization controls (Ollama)**
Expose `num_gpu`, `num_thread`, and model quantization (Q4/Q5/Q8) in Ollama settings panel.
Add a "Benchmark Ollama speed" helper reporting tokens/sec for current settings.

- [ ] **Impact**: 3 | **Effort**: 2

**L-10: Portable mode**
`portable.flag` file next to the executable switches config, DB, and cache to the same directory
instead of `%APPDATA%\FileOrganizer\`. Enables USB-drive deployment.

- [ ] **Impact**: 2 | **Effort**: 2

**L-11: ComfyUI / A1111 output sorter preset**
Plugin (NEXT-25 SDK) that classifies Stable Diffusion / Flux outputs by prompt keywords,
checkpoint hash, sampler settings, image dimensions. Routes to `AI Art - Landscape` vs
`AI Art - Portrait`, etc.

- [ ] **Impact**: 3 | **Effort**: 3

**L-12: Progressive dedup checkpointing**
Save partial hash state to disk after every N files during dedup scan. On cancel/resume, skip
already-hashed files. Essential for multi-TB dedup interrupted runs.

- [ ] **Impact**: 3 | **Effort**: 3

- [ ] Source: [S11] fclones checkpointing pattern

**L-13: macOS / Linux parity**
Abstract watch mode behind a `WatchBackend` protocol so macOS (`FSEvents`) and Linux (`inotify`)
backends can be swapped in. Address symlinks vs junction points and `shutil` fallback differences.

- [ ] **Impact**: 3 | **Effort**: 4

- [ ] Source: [S8] organize-cli, [S1] LlamaFS, [S2] Local-File-Organizer

**L-14: i18n / localization**
Externalize all UI strings to `locale/en_US.json`. Add Chinese (Simplified) as first non-English
locale (CJK filenames are an existing pain point). Use Qt `QTranslator` + `.qm` files.

- [ ] **Impact**: 2 | **Effort**: 4

- [ ] Source: [S9] TagStudio Weblate, [S10] Czkawka localization

**L-15: Accessibility (WCAG 2.1)**
Add `accessibleName()` / `accessibleDescription()` to all interactive PyQt6 widgets. Full Tab
order through all panels, Enter to activate. Test with NVDA/JAWS screen reader.

- [ ] **Impact**: 2 | **Effort**: 3

- [ ] Source: [S9] TagStudio accessibility issues, WCAG 2.1 guidelines

**L-16: Opt-in telemetry**
On explicit opt-in: anonymously report category distribution, confidence score histogram, and
provider selection ratios. No file names, no paths. Used to identify categories most often sent
to `_Review` to prioritize classifier improvements.

- [ ] **Impact**: 3 | **Effort**: 3

**L-17: Virtual bundles**
Allow users to create named groupings of assets that span multiple categories without moving files.
A bundle is a named list of asset fingerprints stored in `asset_bundles.db`. Bundles appear as
virtual folders in the Browse tab. Useful for "all assets used in Project X" groupings that do
not map to taxonomy categories. Non-destructive by design — no filesystem changes.

- [ ] **Impact**: 3 | **Effort**: 4

- [ ] Source: [S43] electron-dam virtual bundles pattern

**L-18: Audio waveform preview in Browse tab**
In the Browse tab (NEXT-22) details panel, render a waveform visualization for audio assets
(`.mp3`, `.wav`, `.aiff`, `.flac`, `.ogg`). Use `librosa` or `soundfile` + `matplotlib` to
compute and render a static waveform PNG, cached alongside the thumbnail. electron-dam ships this
via Wavesurfer.js [S43]; the Qt equivalent is a `QLabel` holding a cached waveform `QPixmap`.
TagStudio's `previews/renderer.py` [S56] already implements an audio waveform path in PySide6
that maps directly onto FileOrganizer's PyQt6 stack — the renderer dispatcher and waveform
QPainter logic are nearly portable line-for-line.

- [ ] **Impact**: 2 | **Effort**: 4 | **Depends on**: NEXT-22

- [ ] Source: [S43] electron-dam audio waveform visualization, [S56] TagStudio
  `src/tagstudio/qt/previews/renderer.py`

**L-19: Source quarantine for executables found in archives**
When archive_extractor (L-7) lands and starts inspecting archive contents pre-classify, any
`.exe`, `.bat`, `.ps1`, `.scr`, `.cmd`, `.msi`, `.lnk`, `.vbs` discovered inside what looks
like a design-asset bundle should be routed to `<dest>/_Quarantine/<source_name>/` instead of
the asset library. Pirated AE templates have repeatedly shipped with bundled malware
loaders disguised as install helpers. Pair with the path-traversal guard in N-13 to cover
both classes of archive risk in one feature surface.

- [ ] **Why later**: Gates on L-7 (archive content inspection) shipping; the quarantine bucket
  itself is a dozen lines once L-7 exists.

- [ ] **Impact**: 3 | **Effort**: 3 | **Depends on**: L-7, N-13

- [ ] Source: [S32] AUDIT_LESSONS.md, GHSA archive risk corpus, internal pen-test pattern

**L-20: Localized destination folder names**
Distinct from L-14 (UI string i18n). The 384-category taxonomy is English-only; a CJK user
may want destination folders to read `フォトショップ - パターン` instead of
`Photoshop - Patterns & Textures`. Add `category_translations.json` mapping canonical
category → locale → display name; resolve at apply time in `_cat_path()`. The canonical
English name remains the storage key in `asset_db.py` so the DB stays portable across locales.
Ship Simplified Chinese first (CJK filenames are an existing pain point in `loose_files`).

- [ ] **Why later**: No active user demand yet, and the migration story for users switching
  locales mid-library is non-trivial (rename every existing folder or maintain symlinks?).
  Revisit after L-14 ships and we have a translator workflow in place.

- [ ] **Impact**: 2 | **Effort**: 4 | **Depends on**: L-14

- [ ] Source: [S9] TagStudio Weblate workflow, [S43] electron-dam multi-locale design assets

**L-21: Video optimizer / re-encode**
After VideoPage (ui-v0.3.0 WinUI) organizes video assets, offer an optional post-organize step
that re-encodes to HEVC (H.265) or AV1 to reclaim disk space on large video libraries. Scope:

- [ ] ffmpeg subprocess: `ffmpeg -i <src> -c:v libx265 -crf 28 -preset slow -c:a copy <dst>`.

- [ ] "Crop black bars" option: `ffmpeg -vf cropdetect` pass before encode.

- [ ] Safety: keep original until encode finishes and passes a size-sanity check (output ≥ 10% of
  original size), then replace. Progress in WinUI shell VideoPage.

- [ ] Opt-in only: never runs as part of an automated organize; requires explicit user action.
Czkawka v11.0.0 [S44] ships this as a first-class mode (video optimizer), confirming demand.

- [ ] **Why later**: Windows ffmpeg availability is not guaranteed; requires a new "Optimize" surface
  in VideoPage not designed yet; lossiness concerns require clear user consent UI.

- [ ] **Impact**: 2 | **Effort**: 4

- [ ] Source: [S44] Czkawka v11.0.0 video optimizer mode, ffmpeg documentation

**L-22: Full WCAG 2.1 AA accessibility compliance**
Complete audit + remediation to achieve Level AA (not just Level A from NEXT-90). Specific targets:
(1) Screen reader testing on Windows (NVDA), macOS (VoiceOver), Linux (Orca). (2) Ensure all images have
descriptive alt text. (3) Maintain 7:1 color contrast on focus indicators. (4) Test with high-zoom (200%)
and magnification tools. (5) Support RTL text rendering (for Arabic/Hebrew file paths). (6) Verify all
dynamic content updates are announced to assistive tech. This is **Level AA** (GDPR "accessibility by design"
requirement in many EU jurisdictions). Benefit: enables use by visually impaired users and users with motor
disabilities. Requires professional accessibility testing (~$2–5K externally); can be self-tested using NVDA
(free) + axe (free).

- [ ] **Why later**: Requires sustained UX + testing effort; demand from accessibility community not yet visible.
  Revisit after NEXT-90 ships and we see real-world usage patterns.

- [ ] **Impact**: 3 | **Effort**: 5 | **Depends on**: NEXT-90

- [ ] Source: [S191] WCAG 2.1 Level AA https://www.w3.org/WAI/WCAG21/quickref/;
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

- [ ] **Why later**: No active non-English user base yet. Revisit after v9.0 ships and we measure geographic usage.

- [ ] **Impact**: 2 | **Effort**: 3 | **Depends on**: code cleanup (ensure all UI strings are wrapped in `QCoreApplication.translate()`)

- [ ] Source: [S194] Qt Linguist documentation https://doc.qt.io/qt-6/linguist-manager.html;
   [S195] Weblate https://weblate.org/;
   [S196] PyQt6 QTranslator https://www.riverbankcomputing.com/static/Docs/PyQt6/api/qtcore/qtranslator.html

**L-24: Category taxonomy translation (localized folder names)**
Extend i18n to the 384-category taxonomy (Photoshop, Blender, Adobe, etc.). Ship category name + description
translations for top-5 languages (Chinese, Japanese, Spanish, French, German). At application time, resolve
category to localized folder name via `category_translations.json`. Store canonical English category in DB
so assets remain portable across locale switches. Example: `Photoshop - Patterns & Textures` → `フォトショップ

- [ ] パターンとテクスチャ` on Japanese system. Complexity: handling users switching locales mid-library (do we
rename folders or maintain symlinks?). Recommend: ship folder-rename safe mode + symlink fallback.

- [ ] **Why later**: Depends on L-23 (i18n infrastructure); no current demand from non-English users.

- [ ] **Impact**: 2 | **Effort**: 4 | **Depends on**: L-23

- [ ] Source: [S197] Qt file system locale handling;
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

- [ ] **Why later**: Requires stable v9.x API + user demand for extensibility not yet visible.

- [ ] **Impact**: 3 | **Effort**: 5 | **Depends on**: API stabilization (NEXT-1 through NEXT-30)

- [ ] Source: [S200] pluggy https://pluggy.readthedocs.io/;
   [S201] pytest plugin tutorial (reference architecture);
   [S202] stevedore (alternative: entry_points-based plugins) https://stevedore.readthedocs.io/

**L-26: Snap package distribution (Ubuntu/Linux)**
Create Snapcraft manifest (`snapcraft.yaml`) for Ubuntu Snap Store. Snaps run in containers with restricted
file system access (users can override with `--devmode` for full access). This is **Ubuntu's preferred** package
format but has lower adoption than AppImage (L-25 ships AppImage first). Snap auto-updates via Store. Effort:
~2 days to write + test the manifest. Defer to post-v9.0 unless significant Ubuntu user demand emerges.

- [ ] **Why later**: AppImage (NEXT-85) is more portable and community-preferred. Snap adoption is concentrated in
  Ubuntu; we serve broader Linux via AppImage first. Revisit if Ubuntu users request it.

- [ ] **Impact**: 2 | **Effort**: 3 | **Depends on**: NEXT-85 (AppImage shipping first)

- [ ] Source: [S203] Snapcraft https://snapcraft.io/;
   [S204] Snap confinement model https://snapcraft.io/docs/snap-confinement

**L-27: Flatpak distribution (GNOME/KDE/XFCE desktops)**
Create Flatpak manifest for Flatseal Sandbox. Flatpak is the **community-preferred containerization** on
GNOME and KDE desktops. Permissions sandbox model (declare home, documents, download access). Ship via Flathub
(community-run app store). Effort: similar to Snap (~2 days). Like Snap, defer to post-v9.0; AppImage (NEXT-85)
handles the Linux long-tail more efficiently. Revisit if GNOME/KDE user demand emerges.

- [ ] **Why later**: AppImage is the cross-distro standard; Flatpak adoption is concentrated in newer desktops.

- [ ] **Impact**: 2 | **Effort**: 3 | **Depends on**: NEXT-85 (AppImage priority)

- [ ] Source: [S205] Flatpak https://flatpak.org/;
   [S206] Flathub https://flathub.org/;
   [S207] Flatpak permission sandbox https://docs.flatpak.org/en/latest/sandbox-permissions.html

**L-28: Windows MSIX / Microsoft Store distribution**
Package FileOrganizer as MSIX (Microsoft's modern Windows app format) for distribution via Microsoft Store.
MSIX enables automatic updates via Store, but requires sandboxing (limited file system access; users must
grant folder permissions via system UI). This is **enterprise-preferred** but restrictive for a file organizer.
Effort: 1–2 weeks to refactor file I/O paths to respect sandbox boundaries. Defer to v9.5+ or later when we
have stable cloud sync (LATER-15). Requires $19 USD annual registration fee in Microsoft Partner Center.

- [ ] **Why later**: Sandbox refactoring is high-effort; demand from Store users not yet visible. Better to ship
  portable exe + Homebrew + AppImage first. Enterprise adoption may eventually justify MSIX effort.

- [ ] **Impact**: 2 | **Effort**: 5 | **Depends on**: file system abstraction refactoring

- [ ] Source: [S208] MSIX containerization https://learn.microsoft.com/en-us/windows/msix/overview;
   [S209] Microsoft Partner Center https://partner.microsoft.com/;
   [S210] MSIX file system sandbox constraints

**L-29: Debian/AUR package maintenance (community-driven)**
Create `.deb` package (Debian/Ubuntu) and AUR (Arch User Repository) manifest. These are lower-priority than
AppImage (NEXT-85) because: (1) Debian requires recurring review + rebuilds per distro version; (2) AUR is
community-maintained (we don't control release cycle). Acceptable path: publish AppImage, let community
contributors submit .deb + AUR packages if they want. If we ship this ourselves, effort is ~1 week per format.
Prefer to defer to community volunteers.

- [ ] **Why later**: AppImage + Snap + Flatpak cover Linux users well. .deb + AUR are high-maintenance with
  minimal reach increase. Community-driven is acceptable.

- [ ] **Impact**: 1 | **Effort**: 4 | **Depends on**: NEXT-85 (AppImage established first)

- [ ] Source: [S211] Debian package creation https://www.debian.org/doc/manuals/maint-guide/;
   [S212] AUR submission https://wiki.archlinux.org/title/AUR_submission_guidelines

**L-30: Commercial licensing model (optional v10.x+ revenue)**
Design + implement a licensing tier system: (1) **Community Edition** — free, open-source, unlimited use for
individuals + educational institutions. (2) **Team Edition** — $49/yr per user, includes team collaboration
(multi-user library sharing, LATER-16). (3) **Enterprise Edition** — custom pricing, includes priority support

- [ ] on-premise deployment. Implement via License Key + validation server (Lemonsqueezy or Gumroad integration).
No server-side functionality change; license check is local. This is **optional revenue stream** for funding
continued development. Requires legal review (terms of service, refund policy, export compliance for non-US
users). Defer to v10.x or later; ship v9.x as fully free/open-source first to build community trust.

- [ ] **Why later**: Revenue is not required for v9.x viability; community-first positioning builds trust.
  Licensing complexity introduces friction for adoption. Revisit after v9.0 ships + user base stabilizes.

- [ ] **Impact**: 1 | **Effort**: 4

- [ ] Source: [S213] Lemonsqueezy licensing https://www.lemonsqueezy.com/;
   [S214] Gumroad licensing https://gumroad.com/;
   [S215] Open-source dual-licensing model (example: JetBrains IntelliJ IDEA Community + Ultimate)

**L-31: Analytics dashboard (observability + user insights)**
Ship an optional in-app dashboard reporting: (1) Total files organized by category (bar chart). (2) ML model
accuracy over time (confusion matrix trending). (3) Duplicate files detected (% of library). (4) Storage reclaimed
(GB moved to archive). (5) Top 10 file types processed. Data is local-only (no phone-home); stored in SQLite.
Dashboard helps users understand their library structure + FileOrganizer's impact. Pairs with NEXT-74 (metrics)

- [ ] NEXT-75 (crash reporting) for observability. Low user value but high marketing/retention impact. Effort:
UI + SQLite queries (~1 week).

- [ ] **Why later**: Nice-to-have; core organize functionality (NEXT-1 through NEXT-50) is higher priority.

- [ ] **Impact**: 2 | **Effort**: 3 | **Depends on**: NEXT-74 (metrics collection)

- [ ] Source: [S216] Analytics dashboard patterns (Metabase, Superset);
   [S217] SQLite aggregation queries;
   [S218] PyQt6 charting (PyQtGraph, matplotlib integration)

---

- [ ] **sentence-transformers < 5.4.1**: activation function injection from Hub models → arbitrary
  code execution. Fixed in v5.4.1. Pin `sentence-transformers>=5.4.1` in requirements.txt.
  Source: [S97] sentence-transformers 5.4.1 release notes

---

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

- [ ] P2 — WinUI runtime visual, keyboard, screen-reader, and all-theme matrix remains unaudited
  Category: testing
  Where: all routed pages under `src/FileOrganizer.UI/Views/Pages`; `src/FileOrganizer.UI/App.xaml`; `src/FileOrganizer.UI/Services/ThemeService.cs`; `src/build.ps1`
  Problem: Static review identified concrete theme/focus/contrast risks, but a full runtime matrix could not be executed: the prescribed build stopped at the missing Visual Studio MSBuild prerequisite, and operator-display isolation prohibits physical-display GUI walkthroughs. Runtime layout, modal/popover nesting, screen-reader announcements, keyboard order, high contrast, reduced motion, and live theme switching therefore still need direct verification.
  Evidence: The build baseline above exits before compilation, and no safe headless/virtual-display run was available in this audit environment. Static inspection covered route/page XAML and token definitions but cannot prove rendered behavior or accessibility-tree output.
  Fix: Provide a pinned Windows CI/virtual-display fixture that builds and launches every routed page, drives keyboard/focus and screen-reader/automation properties, checks high contrast and reduced motion, and captures automated contrast/layout assertions for all seven themes and nested surfaces.
  Acceptance: A repeatable headless/virtual-display matrix launches every route, exercises loading/empty/error/long-content/dialog states in every theme, verifies focus/automation announcements and reduced-motion behavior, and publishes failures as CI artifacts.
  Confidence: Verified
  Effort: L

- [ ] P3 — README feature matrix, theme count, and architecture description are stale
  Category: docs
  Where: `README.md:32-37,215-239`; current route map in `src/FileOrganizer.UI/Views/MainWindow.xaml.cs:83-105`; theme picker in `src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml:21-74`
  Problem: The README calls Files, Duplicates, Photos, Watch, and Toolbox placeholders, says there are six dark themes and no WinUI theme picker, and describes an architecture with only Cleanup/Placeholder pages. The current shell routes those pages and exposes seven themes including Light, so onboarding and support guidance gives users the wrong product model.
  Evidence: The route map wires the named pages, SettingsPage contains the seven-theme picker, and README statements contradict both files. The mismatch is visible before any optional feature is configured.
  Fix: Update the feature matrix, screenshots/walkthrough language, theme list, architecture diagram, and known-limitations section to match the routed shell and actual Python sidecars. Clearly distinguish read-only pages and incomplete actions until the P1 Cleanup/Duplicates flow is resolved.
  Acceptance: A fresh reader can follow README to the current route names/themes and receives no “placeholder” or “six themes/no picker” claim that contradicts the source; CI or a documentation check flags route/theme drift.
  Confidence: Verified
  Effort: S

- [ ] P1 — Establish a versioned, schema-validated WinUI-to-Python sidecar protocol
  Why: Multiple root runners emit ad hoc NDJSON while the WinUI shell parses generic JSON; a malformed event, missing field, or changed terminal state can crash or strand a page even when the Python work is recoverable.
  Evidence: src/FileOrganizer.UI/Services/PythonRunner.cs and SidecarRunner.cs forward parsed JsonDocument values without a shared event schema; each *_run.py defines its own payload shape. tests/test_sidecar_contracts.py checks event names and fatal/cancel behavior but does not define versioned field constraints. Ollama’s structured-output guidance and PyPA/pluggy contract patterns support schema-first boundaries.
  Touches: all root *_run.py sidecars; src/FileOrganizer.UI/Services/PythonRunner.cs; src/FileOrganizer.UI/Services/SidecarRunner.cs; tests/test_sidecar_contracts.py; a shared Python schema and C# DTO/validation layer.
  Acceptance: Every sidecar begins with a protocol version/capability handshake and emits validated progress/item/log/error/terminal records with required fields, bounded strings, totals, and stable error codes; unknown events are isolated, malformed records cannot terminate the run, cancellation has one deterministic terminal state, and fixture tests cover every routed sidecar plus the C# parser.
  Complexity: L

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
