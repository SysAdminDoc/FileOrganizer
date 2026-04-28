# External Research Notes

Last researched: 2026-04-28

This is a repo-specific synthesis of related projects and current product patterns that can improve
FileOrganizer. It intentionally separates source research from `ROADMAP.md`, which already contains
implementation backlog items.

## Executive Priorities

1. Build the organizer around a persistent asset catalog, not only move operations.
2. Make every destructive operation plan-first: scan -> editable plan -> journaled apply -> report.
3. Add a first-class review/browser workflow for visual assets before adding more classification
   breadth.
4. Treat rules, AI, metadata, and fingerprints as cooperating classifiers with visible confidence.
5. Keep the file system portable and inspectable; avoid trapping users in opaque app-only metadata.

## Related Projects And Product Lessons

### Automation Rules

- Hazel: folder watchers, multiple ordered rules per folder, nested conditions, and multiple actions
  per match are still the clearest rule model to copy. FileOrganizer should evolve its single-step
  rules into rule chains with an explicit "first matching rule wins" or "continue after match"
  policy.
  Source: https://www.noodlesoft.com/manual/hazel/hazel-basics/about-folders-rules/
- File Juggler: Windows-native change notifications matter. It processes created/modified files
  quickly, avoids reprocessing unchanged files, and falls back to full scans for startup/network
  locations. FileOrganizer watch mode should track file signatures and pending state, not just
  "seen path" state.
  Source: https://www.filejuggler.com/documentation/introduction-to-file-juggler/
- DropIt: the durable pattern is simple associations: rule, action, drag/drop or watched folder.
  FileOrganizer can expose a simplified "association preset" layer for non-AI workflows so the app
  stays useful even when model providers are disabled.
  Source: https://www.dropitproject.com/index.php

### AI File Organizers

- LlamaFS: useful distinction between batch mode and watch mode, plus multimodal extraction for
  images and audio. FileOrganizer should preserve its batch runner but add a daemon/watch runner
  that emits the same JSON plan schema.
  Source: https://github.com/iyaja/llama-fs
- Local-File-Organizer: privacy-first local LLM/VLM routing is a strong positioning point. For
  FileOrganizer, text-like assets should go through metadata/text extraction while preview images
  and PDFs should use a local vision model when confidence is low.
  Source: https://github.com/QiuYannnn/Local-File-Organizer
- llm-file-organizer and similar CLI tools show that provider selection is becoming commodity.
  FileOrganizer's advantage should be safety, visual review, fingerprint reuse, and design taxonomy,
  not just "it calls an LLM."
  Source: https://pypi.org/project/llm-file-organizer/

### Design Asset Managers

- Adobe Bridge: the core creative workflow is browse, preview, batch rename, move/delete, edit
  metadata, filter/search, and process camera/video assets. FileOrganizer already moves and
  classifies, but it needs a stronger "asset browser" surface to compete for daily use.
  Source: https://helpx.adobe.com/bridge/desktop/organize-and-find-files/organize-files-and-folders/organize-content-and-assets.html
- Eagle: designers value very fast visual browsing, diverse categorization, and broad file-format
  preview. FileOrganizer should index previews and show a fast thumbnail grid for organized assets,
  review queues, and duplicate groups.
  Source: https://www.eagle.cool/
- TagStudio: the important lesson is open, portable, private metadata and resilience when users move
  files outside the app. FileOrganizer should support relinking by fingerprint/path hints and avoid
  requiring users to rewrite their existing directory structures.
  Source: https://github.com/TagStudioDev/TagStudio
- XMP: for Adobe-heavy workflows, metadata should travel with assets where possible. FileOrganizer
  should support XMP/IPTC sidecar/writeback for tags, marketplace IDs, clean titles, ratings,
  copyright, and source URLs.
  Sources:
  - https://developer.adobe.com/xmp/docs/
  - https://developer.adobe.com/xmp/docs/xmp-namespaces/xmp-mm/

### Search, Tags, And Review

- Paperless-ngx: multi-axis metadata works better than a single folder category. Its pattern of
  tags, document types, custom fields, saved views, bulk editing, and scored search maps well to
  design assets.
  Source: https://docs.paperless-ngx.com/usage/
- Paperless-ngx matching: rule-driven auto-tagging based on exact/contains/regex-style matching is a
  useful non-AI confidence source. FileOrganizer should expose similar matching algorithms for
  marketplace names, IDs, file contents, and metadata.
  Source: https://docs.paperless-ngx.com/advanced_usage/
- TagSpaces: offline local file management plus tagging is a useful fallback model. FileOrganizer
  should let users choose tags without requiring a hosted account or cloud index.
  Source: https://github.com/tagspaces/tagspaces

### Cleanup And Deduplication

- Czkawka: the strongest borrow is specialized modes with tuned pipelines: duplicates, similar
  images, empty folders, large files, broken files. FileOrganizer should keep cleanup tools as
  focused workflows with their own progress, filters, and exportable results instead of blending
  everything into one scan.
  Source: https://czkawka.net/
- Czkawka/duplicate-finder patterns suggest using staged work: size grouping, partial hashes,
  full hashes, perceptual hashes, and reference-folder rules. FileOrganizer already has progressive
  hashing; the next improvement is a resumable checkpoint database and "prefer this library root"
  duplicate decisions.

## Recommended Implementation Tracks

### Track 1: Plan-First Apply Pipeline

- Define a stable `MovePlan` JSON schema shared by GUI and CLI.
- Generate plans from AI, rules, marketplace enrichment, and fingerprint lookups.
- Let users edit the plan before execution.
- Journal every plan item as `pending`, `done`, `failed`, or `undone`.
- Emit an HTML/Markdown "what changed" report with thumbnails, confidence, source, destination,
  and rollback command.

This is the highest trust improvement because it reduces fear around multi-TB moves.

### Track 2: Asset Catalog And Browser

- Add `assets`, `asset_files`, `asset_tags`, `asset_sources`, and `asset_previews` tables.
- Index every organized item whether it moved in the current run or was already present.
- Show thumbnail grid, list view, category tree, `_Review`, duplicates, and missing/relinked items.
- Add bulk edit for category, tags, marketplace ID, rating, source URL, and note.
- Use FTS5 over clean name, disk name, category, tags, marketplace, text snippets, and metadata.

This turns FileOrganizer from a one-shot sorter into a daily design library tool.

### Track 3: Multimodal Classification Router

- Route by content type:
  - text/document: extracted text + metadata
  - image/PDF preview: local VLM caption/classification
  - audio/video: metadata first, optional Whisper/thumbnail frame later
  - archive/template folder: project file plus preview image plus marketplace ID
- Only call expensive AI after fingerprint, marketplace ID, cache, and rules fail.
- Store classifier provenance per field: `category.source`, `clean_name.source`,
  `confidence.source`, and `needs_review_reason`.

This improves accuracy while lowering API spend.

### Track 4: Rule Chains And Watch Service

- Model rules as ordered chains: conditions, actions, stop/continue, and notes.
- Add condition groups: all/any/none/nested.
- Add actions: move, copy, rename, tag, set category, add to review, run script/webhook.
- Add watch stability window: wait for size/hash to stop changing before processing.
- Track pending files so restart catches missed events without reprocessing unchanged files.

This gives FileOrganizer a credible Windows alternative to Hazel/File Juggler.

### Track 5: Metadata Interoperability

- Export/import catalog JSON and CSV.
- Write optional sidecar metadata next to folders: `.fileorganizer.json`.
- For Adobe-compatible single files, optionally write XMP/IPTC fields.
- Store marketplace IDs, product URLs, license/source, tags, rating, and user corrections.
- Add "relink library" using folder fingerprint, project-file hash, and basename similarity.

This protects users from lock-in and makes metadata useful outside the app.

### Track 6: Dedup And Library Hygiene

- Add duplicate workspaces: exact duplicate, near duplicate, same marketplace ID, same preview hash,
  same project hash, and pack/bundle overlap.
- Add "reference root" rules: keep items under chosen drives/categories and mark others as
  duplicates.
- Add resume checkpoints for long hash runs.
- Add duplicate result export to Markdown/CSV/JSON.

This aligns with the current 33 TB real-world use case.

## Features To Avoid Or Delay

- Do not split into Electron/FastAPI unless PyQt becomes a blocker; the current app already has a
  working desktop stack.
- Do not train custom models before building correction capture and evaluation sets.
- Do not make cloud sync mandatory. The design-file niche is privacy- and disk-heavy.
- Do not prioritize another broad taxonomy expansion until review workflow and catalog search are
  stronger.

## Concrete Next Sprint

1. Add `MovePlan` dataclasses/schema and convert `organize_run.py --preview` to write a plan file.
2. Add `--apply-plan plan.json` and record pending/done/failed states in `organize_moves.db`.
3. Add `--report run_id --output report.md` with changed items and `_Review` breakdown.
4. Add a small test suite around path sanitization, category aliasing, plan generation, and
   journal transitions.
5. Add a GitHub Actions CI workflow running syntax checks and those unit tests.

