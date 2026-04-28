# ROADMAP

Backlog for FileOrganizer. The core (multi-provider AI classifier + 384 categories + cleanup +
duplicates + photos + community fingerprint DB) is mature; this focuses on accuracy, performance,
automation, and lessons learned from organizing 1,200+ real design asset templates.

---

## Lessons Learned (from real-world run — April 2026)

These are not theoretical; they came from running the tool on ~1,200 After Effects/design templates
across 33 TB on I:\ and G:\.

- **Name-based matching is fragile**: AI agents clean up, truncate, or reformat folder names before
  classifying them. The original disk name and the classified name may not match. Use position-based
  (batch index → org_index offset) mapping instead of name lookups. See `organize_run.py`.

- **Trailing spaces in folder/file names → WinError 2**: Files copied from Linux/macOS can have
  `folder ` (with trailing space). Windows silently strips trailing spaces on creation, then fails
  to find the original path. Pre-sanitize every source tree with `strip_trailing_spaces()` before
  any move. Already implemented in `organize_run.py`.

- **Deep Unicode paths >260 chars → WinError 3**: Chinese/CJK filenames inside deeply nested folders
  exceed MAX_PATH. `shutil.move` and `shutil.copytree` don't use `\\?\` prefixes. Solution:
  robocopy with `/256` flag handles up to 32,767 chars. Already implemented in `organize_run.py`.

- **shutil.move cross-drive leaves partial copies on failure**: Source is always safe (rmtree never
  runs on exception), but a partial destination exists. Retrying without cleaning dest first creates
  `(1)` suffix collisions. `retry_errors()` in `organize_run.py` handles this correctly.

- **Robocopy exit codes 0-7 are all success**: Only 8+ is failure. Never use `check=True` with
  robocopy. `robust_move()` enforces this correctly.

- **Every move should be journaled**: `organize_run.py` now writes to `organize_moves.db` (SQLite)
  with `--undo-last N` and `--undo-all` support. Without this, a partial run is irreversible.

- **Pre-flight validation prevents >90% of errors**: Running `--validate` before `--apply` surfaces
  all trailing-space and long-path issues in advance. Implemented in `organize_run.py`.

- **AI fabricates names if not grounded**: In batch 10, the agent invented plausible-looking names
  instead of reading the actual index. Rule: ALWAYS embed the exact names from org_index into the
  batch prompt. Never let the model guess what items exist.

- **Community fingerprint DB changes the cost model**: Once we have 1,000+ fingerprinted assets,
  new users can classify common templates instantly without any AI call. Already implemented in
  `asset_db.py`. The DB should be shipped as a GitHub Release artifact and auto-downloaded.

- **Preview images are embedded in nearly every template**: Finding and indexing
  `preview.jpg`/`thumbnail.png` at build time unlocks thumbnail display in the GUI at zero cost.
  Implemented in `asset_db.py::find_preview_image()`.

---

## Planned Features

### Classification pipeline — highest priority

- **Four-stage lookup pipeline** (no AI cost for known assets):
  1. Community fingerprint DB exact match → confidence 100, instant
  2. Marketplace ID extraction + API/scrape lookup → confidence 95, 1 network call
  3. Name heuristics + corrections cache → confidence 45-70, zero cost
  4. AI classification → confidence 70-95, API cost
  Currently only stages 3 and 4 are wired together. Stage 1 is built but not auto-downloaded.
  Stage 2 needs `marketplace_enrich.py` (see below).

- **`marketplace_enrich.py`** — Extract numeric marketplace IDs from folder names (Videohive,
  MotionElements, etc.) and fetch the actual item title, tags, and primary category directly from
  the marketplace's public API or scrape endpoint. Videohive: `videohive.net/item/slug/{ID}` or
  Envato API with user token. MotionElements: `api.motionelements.com/v1/elements/{ID}` (free tier).
  This gets near-100% accuracy for items with known IDs with zero AI cost and no classification
  ambiguity.

- **Two-stage AI prompt**: Stage 1 asks "what FILE TYPE is this template?" (AE/Premiere/PSD/AI/etc)
  with zero context needed. Stage 2 uses the file type as context for a tighter subcategory prompt.
  Current single-stage approach conflates file-type detection with subcategory selection.

- **Vision-aware classification for images/PDFs** — send thumbnails to a local multimodal model
  (`llava:7b`, `qwen2.5-vl`, `moondream`) when extension-only classification confidence is low.
  Now that `asset_db.py` extracts preview images, the path to the thumbnail is already known.

- **Confidence calibration display** — show per-category probability bars in the preview; let
  user click to force the runner-up label.

- **Few-shot teaching panel** — drag a handful of example files into a category to generate 3-5
  in-context examples that get prepended to future LLM prompts for that category.

- **Negative keyword rules** — per-category "must NOT contain" terms to resolve overlapping
  categories (e.g. Wedding vs Elegant).

- **Marketplace-specific cleanup dictionaries** — expand beyond Envato/Creative Market/Freepik to
  also strip Motion Array, FilterGrade, Shutterstock, Adobe Stock, AEriver, LP-video identifiers.
  See `catalog.py::_MARKETPLACE_PREFIXES` — these patterns are now documented in CLAUDE.md.

### Community fingerprint DB

- **Auto-download on first run**: On startup, check GitHub Releases for a newer `asset_fingerprints.json`
  and import it into the local SQLite DB. Schema version gate: skip if DB_VERSION mismatch.
- **Contribution workflow**: After a successful `--apply` run, optionally POST new fingerprints to a
  central aggregator (or open a PR to the `fingerprints` branch of the FileOrganizer repo).
- **Incremental JSON diff exports**: Instead of shipping the full JSON every release, ship a
  `fingerprints_patch_{date}.json` with only new/changed assets. Apply patches on top of the base.
- **Marketplace ID index**: Alongside SHA-256 hashes, store the extracted marketplace item ID
  (e.g. `13357739` for Videohive) as a secondary lookup key. Faster for items with known IDs.
- **Duplicate detection query**: `SELECT a1.clean_name, a2.clean_name FROM assets a1 JOIN assets a2
  ON a1.folder_fingerprint = a2.folder_fingerprint WHERE a1.id < a2.id` — surfaces exact duplicates
  across the whole library instantly. Add `--find-dupes` flag to `asset_db.py`.
- **Near-duplicate detection**: Query `asset_files` for assets where >75% of file hashes overlap
  but fingerprints differ (same template, different extra files). Flag as "probable duplicate".

### Moves journal and safety

- **Two-phase commit for the GUI apply**: Write all planned moves to `organize_moves.db` first with
  status='pending'. Mark each 'done' atomically after the move succeeds. On crash/restart, resume
  from pending entries.
- **Undo history visualizer in GUI**: Timeline view of all moves with one-click undo per item or
  per run. Expose `organize_moves.db` through a dedicated "History" tab in the main window.
- **Pre-flight report UI**: Before any apply, show a color-coded table of:
  - Items that would fail (trailing spaces, long paths)
  - Items already organized (dest exists)
  - Low-confidence items going to `_Review`
  - Free space check result
- **Quota-aware apply**: Already checks free space at dest root. Add per-category space estimate
  (sum of source sizes for items going to each category) so user knows if space will run out
  mid-run.

### Duplicate detection (cross-drive, cross-library)

- **Cross-library fingerprint dedup**: Given two organized roots (I:\ + G:\ + external drives),
  find all identical assets by `folder_fingerprint`. Show a merge/delete dialog.
- **Near-duplicate pack detection**: Templates that share a marketplace prefix AND >60% file hash
  overlap are likely from the same bundle/pack. Group them under a Pack label.
- **Perceptual hash dedup for preview images**: Use `imagehash` (perceptual hash) on the
  `preview_image` files to detect visually similar templates even if the files differ slightly
  (re-exported preview, different resolution). Borrow bk-tree + Hamming distance from Czkawka.
- **Version-aware dedup**: If two items have the same marketplace ID but different file counts or
  fingerprints, one is likely a newer version. Keep the one with more files; archive the other.

### AEP / project file deep inspection

- **AEP binary parser** — After Effects project files have a documented binary format (RIFX).
  Parsing the tree reveals: composition names and durations, required plug-ins, AE version,
  resolution and frame rate, number of layers. This is much richer signal than the folder name.
  Library: `aeptools` (Python) or custom RIFX reader. Store extracted fields in `asset_files`
  metadata or a new `asset_meta` table.
- **Plug-in dependency tracking** — AEP files embed required plug-in names. An asset that requires
  Element 3D, Trapcode Particular, or Video Copilot plug-ins gets a `requires_plugins` tag. Let
  users filter out templates they can't open.
- **AE version gate** — Extract minimum AE version from RIFX. Flag templates that need AE CC 2024
  when the user only has CC 2020.
- **MOGRT metadata** — `.mogrt` files are ZIP archives with an embedded JSON manifest. Parse to
  extract: Motion Graphics Template name, parameters, fonts required.

### Rename engine improvements

- **Standardized rename format**: After classifying, optionally rename each organized folder to a
  canonical format: `{CAT_CODE}_{MARKETPLACE_ID}_{CLEAN_NAME}`.
  Example: `AE-SL-13357739-Photo Slideshow` for a Videohive slideshow with ID 13357739.
  This makes cross-reference, search, and dedup trivially easy. Add as an opt-in `--rename` flag
  to `organize_run.py`.
- **Batch rename with preview**: GUI dialog showing old name → new name for all items in a
  category, with inline edit before committing.

### GUI — thumbnail browser

- **Category tree with preview thumbnails**: Main window gets a new "Browse" tab showing the
  organized library as a grid/list with the `preview_image` from `asset_db.py`.
  Click any item to see: category, marketplace, confidence, file count, total size, required
  AE version (if extracted), marketplace item ID with a link.
- **Batch review panel for `_Review` items**: Instead of routing low-confidence items to a folder
  and leaving them there, show a dedicated "Needs Review" tab with the preview image, AI
  confidence, and a dropdown to confirm or reassign the category. Recording corrections feeds the
  corrections cache for future runs.
- **Drag-and-drop reclassification**: Drag any item from one category to another in the tree view.
  Records the correction in `corrections.json` and increments a `user_corrections` counter on the
  asset in the DB. When the same item is seen again (same fingerprint, different location), the
  correction is auto-applied without AI.

### Performance

- **Parallel LLM calls** via async Ollama API (currently serial). Benchmark queue depth 2-8.
- **Result cache by SHA-256 + path basename** — avoid re-classifying the same file in repeat scans.
- **GPU quantization selection** — expose `num_gpu`, `num_thread`, model quantization (Q4/Q5/Q8)
  in Ollama settings.
- **Progressive dedup checkpointing** — save partial hash state so cancel/resume works on
  multi-TB scans.
- **Hash-first skip**: Before any AI call on a folder, compute the folder fingerprint and check
  the DB. Zero-cost for the ~60-70% of common templates already in the community DB.

### Workflow

- **Hazel-style rule chains** — "if source matches X and LLM says Y and file size > Z, do A then
  B". Current rule engine is single-step.
- **Bi-directional sync with source** — optional "keep original in place, symlink into organized
  tree" mode for users who don't want files moved.
- **Scheduled scans per profile** with OS-native scheduler (Task Scheduler on Windows, launchd,
  systemd timers).
- **Watch-mode stability window** — wait N seconds for file size to stabilize before processing
  (fixes partially-downloaded-archive false positives).

### New modules

- **OCR-based classification** for screenshots and scanned PDFs using Tesseract + the LLM.
- **Audio tagging classifier** — use file metadata (ID3) and optional Whisper transcription for
  podcasts vs music.
- **Video metadata classifier** — detect codec/resolution/aspect and route 16:9 vs 9:16 into
  different subfolders.
- **Archive inspection** — peek into ZIP/RAR contents to classify without extracting. Already
  scaffolded in `archive_extractor.py`.

### Safety

- **Two-phase commit** — write all moves to a journal first, make them atomic, rollback on mid-run
  crash. `organize_moves.db` is the foundation; the GUI apply worker needs to use it.
- **Quota-aware apply** — verify destination volume has enough free space before starting.
- **"What changed" report** after apply — HTML/JSON summary with thumbnails for image workflows.
- **Long-path auto-detection in pre-flight** — `--validate` flag already surfaces these; wire it
  into the GUI pre-apply dialog so users see the warning before clicking Apply.

### Plugin / extensibility

- **Published plugin SDK** — document the existing plugin system, ship 3-5 sample plugins
  (camera-raw router, receipts-to-YNAB-export, voice-memos-to-whisper).
- **Webhook on organize** — POST JSON of the action set to a user-configured URL for downstream
  automations (n8n, Zapier self-hosted, Home Assistant).

---

## Competitive Research

- **Hazel (macOS)** — the gold standard for rule-based automation. Rule chain + nested conditions
  + "sort into subfolder by rule output" are the patterns to match.
- **File Juggler (Windows)** — commercial competitor, clean rule UI, watch folders. FileOrganizer
  already matches most of it; the gap is the nested rule chain.
- **Czkawka** — open-source duplicate/empty/broken finder. FileOrganizer already borrows the
  sidebar look; borrow its perceptual hash engine (bk-tree + Hamming distance) next.
- **TagStudio / UniFile (sibling project)** — tag-based cross-reference. README already links
  UniFile as the successor for tag-based use cases; keep FileOrganizer focused on classify/move.
- **Hyper (DoYourData), DropIt, Maid** — lighter rule-only tools; worth scanning for edge-case
  rule primitives (e.g. Maid's "older than X days" in a clean DSL).

---

## Nice-to-Haves

- **Natural-language query to filter the scan** — "show me all PDFs over 5 MB from 2023 in the
  Financial category".
- **Undo history visualizer** — timeline graph of every action with a one-click "back to this
  point". `organize_moves.db` is the backing store; the GUI needs a History tab.
- **Portable mode** (like the EXTRACTORX `portable.flag` convention) to run off a USB stick.
- **Mobile companion** (Android) that queues a scan on the desktop from phone photo-library paths.
- **ComfyUI / A1111 output sorter** preset — classify SD/Flux outputs by prompt keywords and
  checkpoint hash.
- **Receipts to finance export** — OCR + LLM parse total/date/vendor, emit OFX/CSV.
- **Marketplace update alerts** — for items in the DB with a known marketplace ID, periodically
  check if a newer version has been published. Flag for update in the UI.

---

## Open-Source Research (Round 2)

### Related OSS Projects
- **LlamaFS** — https://github.com/iyaja/llama-fs — Self-organizing FS with Llama 3 via Groq + Ollama for incognito; Electron frontend; sub-500ms watch-mode updates via cached minimal-diff index.
- **Local-File-Organizer (QiuYannnn)** — https://github.com/QiuYannnn/Local-File-Organizer — Llama3.2 3B + LLaVA v1.6 via Nexa SDK; 100% local; dual-model text/image handling.
- **AI File Sorter (hyperfield)** — https://github.com/hyperfield/ai-file-sorter — Qt6 cross-platform GUI; registers custom GGUF models; preview + undo-after-close.
- **FileWizardAI** — https://github.com/AIxHunter/FileWizardAI — Python + Angular; NL search over organized files; result cache to minimize re-inference.
- **aifiles (jjuliano)** — https://github.com/jjuliano/aifiles — Multi-provider CLI (Ollama / LM Studio / OpenAI / Grok / DeepSeek); file-watching daemon; XDG templates.
- **ai-file-organizer (thebearwithabite)** — https://github.com/thebearwithabite/ai-file-organizer — Computer vision + audio analysis + plugin classifier API + adaptive learning.
- **docmind-ai-llm** — https://github.com/BjornMelin/docmind-ai-llm — Streamlit + LlamaIndex + LangGraph over local LLMs; rich extraction pipeline worth borrowing for "read file contents before classify."

### Features to Borrow
- Minimal-diff index rewrite from `LlamaFS` — only re-classify files whose hash changed since last scan; slashes re-run cost.
- LLaVA visual-classification path (`QiuYannnn`, `thebearwithabite`) — route image mimes to vision model, text mimes to LLM. Current single-model approach is wasteful.
- Custom-GGUF registration dialog (`hyperfield/ai-file-sorter`) — users point to any `*.gguf`, app discovers context size + chat template.
- NL-search over organized folders (`FileWizardAI`) — embed path + AI description at move time, then FTS5 + vector recall.
- File-watching daemon mode (`aifiles`) — run as Windows Service / systemd; classify on-create instead of batch.
- Plugin classifier API (`thebearwithabite`) — load user-authored Python classes for niche domains (DICOM, RAW photo, CAD).
- Adaptive-learning loop: store user corrections ("moved X from `/Invoices` to `/Receipts`") and feed into a LoRA / few-shot prefix (from `thebearwithabite`).

### Patterns & Architectures Worth Studying
- **Content Extractor / AI Classifier / Undo Manager triad** (Medium deep-dive referenced in `docmind-ai-llm`): hard separation with stable interfaces — classifier is swappable without touching extraction or undo.
- **Dry-run JSON plan → user-edit → commit** (`hyperfield`, `LlamaFS`, `aifiles`): never move files directly from the model output; emit a plan, let user tweak, then execute atomically.
- **Electron + FastAPI split** (`LlamaFS`): keep model server in Python, UI in web stack — enables shipping UI-only updates without touching the model runtime.
- **Tree-of-Moves transaction log**: journal every move/rename to a single JSON Lines file keyed by content hash; "undo last run" replays in reverse. Used across `hyperfield`, `aifiles`. We now use SQLite in `organize_moves.db`.


## Planned Features

### Classifier accuracy
- **Vision-aware classification for images/PDFs** — send thumbnails to a local multimodal model
  (`llava:7b`, `qwen2.5-vl`, `moondream`) when extension-only classification confidence is low.
- **Confidence calibration display** — show per-category probability bars in the preview; let
  user click to force the runner-up label.
- **Few-shot teaching panel** — drag a handful of example files into a category to generate 3-5
  in-context examples that get prepended to future LLM prompts for that category.
- **Negative keyword rules** — per-category "must NOT contain" terms to resolve overlapping
  categories (e.g. Wedding vs Elegant).
- **Marketplace-specific cleanup dictionaries** — expand beyond Envato/Creative Market/Freepik to
  also strip Motion Array, FilterGrade, Shutterstock, Adobe Stock identifiers.

### Performance
- **Parallel LLM calls** via async Ollama API (currently serial). Benchmark queue depth 2-8.
- **Result cache by SHA-256 + path basename** — avoid re-classifying the same file in repeat
  scans.
- **GPU quantization selection** — expose `num_gpu`, `num_thread`, model quantization (Q4/Q5/Q8)
  in Ollama settings.
- **Progressive dedup checkpointing** — save partial hash state so cancel/resume works on
  multi-TB scans.

### Workflow
- **Hazel-style rule chains** — "if source matches X and LLM says Y and file size > Z, do A then
  B". Current rule engine is single-step.
- **Bi-directional sync with source** — optional "keep original in place, symlink into organized
  tree" mode for users who don't want files moved.
- **Scheduled scans per profile** with OS-native scheduler (Task Scheduler on Windows, launchd,
  systemd timers).
- **Watch-mode stability window** — wait N seconds for file size to stabilize before processing
  (fixes partially-downloaded-archive false positives).

### New modules
- **OCR-based classification** for screenshots and scanned PDFs using Tesseract (already common
  dependency) + the LLM.
- **Audio tagging classifier** — use file metadata (ID3) and optional Whisper transcription for
  podcasts vs music.
- **Video metadata classifier** — detect codec/resolution/aspect and route 16:9 vs 9:16 into
  different subfolders.
- **Archive inspection** — peek into ZIP/RAR contents to classify, without extracting.

### Safety
- **Two-phase commit** — write all moves to a journal first, make them atomic, rollback on mid-run
  crash.
- **Quota-aware apply** — verify destination volume has enough free space before starting.
- **"What changed" report** after apply — HTML summary with thumbnails for image workflows.

### Plugin / extensibility
- **Published plugin SDK** — document the existing plugin system, ship 3-5 sample plugins
  (camera-raw router, receipts-to-YNAB-export, voice-memos-to-whisper).
- **Webhook on organize** — POST JSON of the action set to a user-configured URL for downstream
  automations (n8n, Zapier self-hosted, Home Assistant).

## Competitive Research

- **Hazel (macOS)** — the gold standard for rule-based automation. Rule chain + nested conditions
  + "sort into subfolder by rule output" are the patterns to match.
- **File Juggler (Windows)** — commercial competitor, clean rule UI, watch folders. FileOrganizer
  already matches most of it; the gap is the nested rule chain.
- **Czkawka** — open-source duplicate/empty/broken finder. FileOrganizer already borrows the
  sidebar look; borrow its perceptual hash engine (bk-tree + Hamming distance) next.
- **TagStudio / UniFile (sibling project)** — tag-based cross-reference. README already links
  UniFile as the successor for tag-based use cases; keep FileOrganizer focused on classify/move.
- **Hyper (DoYourData), DropIt, Maid** — lighter rule-only tools; worth scanning for edge-case
  rule primitives (e.g. Maid's "older than X days" in a clean DSL).

## Nice-to-Haves

- **Natural-language query to filter the scan** — "show me all PDFs over 5 MB from 2023 in the
  Financial category".
- **Undo history visualizer** — timeline graph of every action with a one-click "back to this
  point".
- **Portable mode** (like the EXTRACTORX `portable.flag` convention) to run off a USB stick.
- **Mobile companion** (Android) that queues a scan on the desktop from phone photo-library paths.
- **ComfyUI / A1111 output sorter** preset — classify SD/Flux outputs by prompt keywords and
  checkpoint hash.
- **Receipts to finance export** — OCR + LLM parse total/date/vendor, emit OFX/CSV.

## Open-Source Research (Round 2)

### Related OSS Projects
- **LlamaFS** — https://github.com/iyaja/llama-fs — Self-organizing FS with Llama 3 via Groq + Ollama for incognito; Electron frontend; sub-500ms watch-mode updates via cached minimal-diff index.
- **Local-File-Organizer (QiuYannnn)** — https://github.com/QiuYannnn/Local-File-Organizer — Llama3.2 3B + LLaVA v1.6 via Nexa SDK; 100% local; dual-model text/image handling.
- **AI File Sorter (hyperfield)** — https://github.com/hyperfield/ai-file-sorter — Qt6 cross-platform GUI; registers custom GGUF models; preview + undo-after-close.
- **FileWizardAI** — https://github.com/AIxHunter/FileWizardAI — Python + Angular; NL search over organized files; result cache to minimize re-inference.
- **aifiles (jjuliano)** — https://github.com/jjuliano/aifiles — Multi-provider CLI (Ollama / LM Studio / OpenAI / Grok / DeepSeek); file-watching daemon; XDG templates.
- **ai-file-organizer (thebearwithabite)** — https://github.com/thebearwithabite/ai-file-organizer — Computer vision + audio analysis + plugin classifier API + adaptive learning.
- **docmind-ai-llm** — https://github.com/BjornMelin/docmind-ai-llm — Streamlit + LlamaIndex + LangGraph over local LLMs; rich extraction pipeline worth borrowing for "read file contents before classify."

### Features to Borrow
- Minimal-diff index rewrite from `LlamaFS` — only re-classify files whose hash changed since last scan; slashes re-run cost.
- LLaVA visual-classification path (`QiuYannnn`, `thebearwithabite`) — route image mimes to vision model, text mimes to LLM. Current single-model approach is wasteful.
- Custom-GGUF registration dialog (`hyperfield/ai-file-sorter`) — users point to any `*.gguf`, app discovers context size + chat template.
- NL-search over organized folders (`FileWizardAI`) — embed path + AI description at move time, then FTS5 + vector recall.
- File-watching daemon mode (`aifiles`) — run as Windows Service / systemd; classify on-create instead of batch.
- Plugin classifier API (`thebearwithabite`) — load user-authored Python classes for niche domains (DICOM, RAW photo, CAD).
- Adaptive-learning loop: store user corrections ("moved X from `/Invoices` to `/Receipts`") and feed into a LoRA / few-shot prefix (from `thebearwithabite`).

### Patterns & Architectures Worth Studying
- **Content Extractor / AI Classifier / Undo Manager triad** (Medium deep-dive referenced in `docmind-ai-llm`): hard separation with stable interfaces — classifier is swappable without touching extraction or undo.
- **Dry-run JSON plan → user-edit → commit** (`hyperfield`, `LlamaFS`, `aifiles`): never move files directly from the model output; emit a plan, let user tweak, then execute atomically.
- **Electron + FastAPI split** (`LlamaFS`): keep model server in Python, UI in web stack — enables shipping UI-only updates without touching the model runtime.
- **Tree-of-Moves transaction log**: journal every move/rename to a single JSON Lines file keyed by content hash; "undo last run" replays in reverse. Used across `hyperfield`, `aifiles`.
