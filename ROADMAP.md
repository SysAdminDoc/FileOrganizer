# ROADMAP

Backlog for FileOrganizer. The core (Ollama LLM classifier + 384 categories + cleanup + duplicates
+ photos) is mature; this focuses on accuracy, performance, automation, and pulling features from
Czkawka, Hazel, and File Juggler.

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
