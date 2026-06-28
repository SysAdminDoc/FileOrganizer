# Research - FileOrganizer

## Executive Summary
FileOrganizer is a Windows-first hybrid organizer: a Python classification and cleanup core plus a .NET 8 WinUI 3 shell. Its strongest shape is not "LLM file sorting" alone; it is high-volume, plan-first creative-asset operations with metadata, fingerprints, rollback, and a native desktop shell. Highest-value direction: close trust gaps before adding breadth. Priority opportunities: harden archive extraction in `fileorganizer/archive_extractor.py`, wire existing provider budget/backoff logic into `fileorganizer/providers.py`, make watch mode actually start from `SOURCE_CONFIGS`, replace placeholder RAW/comic sidecar behavior, add sidecar contract tests, align version metadata, and then deepen portable metadata/search work already tracked by NEXT-61/NEXT-93.

## Product Map
- Core workflows: classify design assets into canonical categories; preview/apply/undo move plans; cleanup empty/temp/broken/large/old files; deduplicate by staged hashes and perceptual image hashes; browse per-media shell pages through Python sidecars.
- User personas: creative-asset hoarder with multi-TB libraries; Windows power user sorting Downloads; designer needing visual review; local-first user avoiding mandatory cloud indexing.
- Platforms and distribution: Python 3.10+ package and PyQt6 legacy GUI; Windows WinUI 3 shell in `src/FileOrganizer.UI/`; source checkout and release zip paths; MIT license.
- Key integrations and data flows: DeepSeek/GitHub Models/Ollama via `fileorganizer/providers.py`; content metadata via Magika, WinRT, Pillow, fontTools, mutagen, ffprobe, psd-tools; movement journal in `organize_moves.db`; sidecars emit NDJSON to the WinUI shell.

## Competitive Landscape
- Local-File-Organizer and LlamaFS do local/model-assisted sorting well. Learn from their watch/batch split and local multimodal direction; avoid copying their weaker Windows-native shell story because FileOrganizer's native shell is a differentiator.
- organize-cli, Hazel, File Juggler, DropIt, and hazelnut show that rule chains remain table stakes. FileOrganizer should keep AI as one classifier in an auditable rule/metadata/fingerprint chain; avoid opaque "model decided" flows.
- Czkawka, fclones, rmlint, and dupeGuru set the bar for cleanup and dedup trust. Learn staged hashing, specialized scanners, resumable state, and explicit keeper policies; avoid expensive full hashing before cheap grouping.
- Eagle, Adobe Bridge, TagStudio, and digiKam show the asset-browser expectation: thumbnails, tags, metadata, color/search filters, sidecars, and relinking. FileOrganizer should build toward visual review and portable metadata without forcing a tag-only model.
- Paperless-ngx is adjacent but useful: saved views, custom fields, rule matching, and bulk edit patterns map well to asset catalogs. Avoid document-management assumptions that do not fit huge binary design libraries.
- IPTC 2025.1, XMP, C2PA, DNG, and Windows Storage APIs create new metadata opportunities. FileOrganizer should expose them through optional sidecars and catalog fields rather than mutating originals by default.

## Security, Privacy, and Reliability
- `fileorganizer/archive_extractor.py` still uses ad hoc `abspath().startswith()` checks and `py7zr.SevenZipFile.extractall(tmp)` before validation. `fileorganizer/safe_archive.py` has the correct primitive; extraction paths should be routed through it for ZIP, TAR, RAR, and 7z.
- `fileorganizer/provider_cost_manager.py` implements budgets, backoff, and failover, but `fileorganizer/providers.py` does not call it around `_chat_completion()`. A 429 or budget breach can still burn the active provider path until generic exceptions fall through.
- `raw_run.py` and `comics_run.py` still auto-install dependencies at runtime and report placeholder organize work. That contradicts deterministic install guidance in `requirements.txt` and can make release sidecars mutate environments unexpectedly.
- `fileorganizer/watch_mode.py` records events but `--start` exits with a TODO instead of loading `SOURCE_CONFIGS`, generating a plan, and applying through the journaled path.
- `src/Directory.Build.props` sets assembly version `0.1.0` while README badges claim `FileOrganizer.UI v0.6.0` and Python core `v8.5.10`. Release metadata drift weakens support/debug reports.

## Architecture Assessment
- Boundary improvement: make a single sidecar contract test suite for `*_run.py` scripts so every WinUI page gets `start/progress/item/error/complete`, cancellation behavior, non-zero exit codes, and no runtime package installation.
- Refactor candidate: replace duplicated extraction guards in `fileorganizer/archive_extractor.py` with `safe_extract_path()` and test all archive formats against sibling-prefix, absolute-path, drive-letter, UNC, and traversal payloads.
- Refactor candidate: move provider policy into one call wrapper in `fileorganizer/providers.py` that checks `provider_cost_manager`, records usage when response metadata is present, and distinguishes retryable rate limits from permanent auth/model failures.
- Test gap: add source-config integration tests for `fileorganizer/watch_mode.py --start` so a watched path produces the same dry-run plan schema used by `organize_run.py`.
- Documentation gap: when version drift is fixed, sync README badges, `CHANGELOG.md`, `SECURITY.md`, `CLAUDE.md`, WinUI assembly metadata, and release tags in one commit.

## Rejected Ideas
- Mandatory hosted sync: rejected because Eagle/TagStudio/Paperless patterns are useful without taking ownership of a user's multi-TB local library.
- New Electron or web-only shell: rejected because the repo already has a WinUI shell and Python sidecar boundary; replacing that would spend effort away from trust and parity gaps.
- Broad taxonomy expansion as the next focus: rejected because current code already has hundreds of categories and the verified gaps are safety, wiring, and review workflows.
- Training custom category models first: rejected until correction capture, calibrated confidence, and evaluation sets are stronger.

## Sources
### OSS competitors and adjacent projects
- https://github.com/QiuYannnn/Local-File-Organizer
- https://github.com/iyaja/llama-fs
- https://github.com/tfeldmann/organize
- https://github.com/TagStudioDev/TagStudio
- https://github.com/qarmin/czkawka
- https://github.com/pkolaczk/fclones
- https://github.com/arsenetar/dupeguru
- https://rmlint.readthedocs.io/
- https://docs.paperless-ngx.com/usage/

### Commercial products
- https://www.eagle.cool/
- https://helpx.adobe.com/bridge/using/organize-files.html
- https://www.noodlesoft.com/manual/hazel/hazel-basics/about-folders-rules/
- https://www.filejuggler.com/documentation/introduction-to-file-juggler/
- https://www.dropitproject.com/

### Standards and platform APIs
- https://developer.adobe.com/xmp/docs/
- https://iptc.org/std/photometadata/specification/IPTC-PhotoMetadata
- https://spec.c2pa.org/specifications/specifications/2.2/index.html
- https://learn.microsoft.com/windows/apps/windows-app-sdk/
- https://learn.microsoft.com/uwp/api/windows.storage.fileproperties

### Dependency and security
- https://docs.pydantic.dev/latest/changelog/
- https://www.python-httpx.org/changelog/
- https://ollama.readthedocs.io/en/structured-outputs/
- https://github.com/google/magika
- https://github.com/advisories/GHSA-24p2-j2jr-386w
- https://github.com/advisories/GHSA-6673-4983-2vx5
- https://github.com/python-pillow/Pillow/releases

### Internal evidence
- `fileorganizer/archive_extractor.py`
- `fileorganizer/safe_archive.py`
- `fileorganizer/provider_cost_manager.py`
- `fileorganizer/providers.py`
- `fileorganizer/watch_mode.py`
- `raw_run.py`
- `comics_run.py`
- `src/Directory.Build.props`
- `README.md`

## Open Questions
- Which release stream owns user-visible versioning: Python core `v8.x`, shell `ui-v0.x`, or a single product version for installers and diagnostics?
