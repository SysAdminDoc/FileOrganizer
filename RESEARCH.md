# Research — FileOrganizer
Date: 2026-08-10 — replaces all prior research.

## Executive Summary

FileOrganizer is a Windows-first, local-first asset organizer: a .NET 8/WinUI 3 shell launches a Python/PyQt6 core that classifies design assets, builds previewable move plans, journals applied moves, and exposes cleanup, deduplication, media, watch, catalog, and research workflows. The strongest product shape is the plan-first filesystem boundary and broad metadata/provider pipeline; the highest-value direction is to make every secondary workflow equally trustworthy, observable, resumable, and release-verifiable before adding more AI or format breadth. On 2026-08-10 the isolated Python baseline passed 642 tests with 9 skips, but the prescribed WinUI build stopped at its missing MSBuild prerequisite, Ruff reported 1,133 findings, mypy 439 errors, and pyright 963 errors. Those are release risks, not feature opportunities, and are already represented by active roadmap items.

Priority opportunities:

1. Finish the active P1 safety and shell-boundary work: path containment, watch-loop prevention, archive quotas, collision-safe merge/undo, secret handling, and WinUI dispatcher correctness.
2. Add fail-closed destructive-operation semantics and a durable quarantine/recovery contract; community users explicitly distrust automatic deletion, while fclones, rmlint, and Czkawka make review, reference folders, caches, and staged decisions visible.
3. Replace the implicit WinUI-to-Python event convention with a versioned, schema-validated sidecar protocol so malformed provider/sidecar output becomes a bounded review result instead of a page crash.
4. Make installation and updates reproducible and verifiable: lock Python dependencies, scan the resolved graph, and remove unverified live installer execution from the Ollama first-run path.
5. Make the community catalog authenticated, size-bounded, atomic, opt-out, and usable offline; its startup download currently feeds directly into a local database.
6. Add a persisted review/export layer for long cleanup and duplicate scans, then add a Windows NTFS incremental index path for the multi-terabyte workloads documented in the repository.
7. Persist per-item classification evidence and replayable evaluation data (provider/model/schema/taxonomy/input fingerprint) so confidence calibration and user corrections can be measured rather than inferred.
8. Treat metadata portability, localization, accessibility, plugin APIs, distribution, and semantic search as staged follow-ons already present in the existing roadmap; do not create duplicate proposals.

## Product Map

- Core workflows: scan a configured source; classify by deterministic stages plus optional AI; generate an editable destination/rename plan; preview, apply, journal, report, and undo filesystem changes.
- Secondary workflows: cleanup scanners, exact/perceptual duplicate detection, type-specific media/book/font/code/subtitle/photo/RAW/comic actions, watch folders, community fingerprint lookup, and research resolution.
- Static route coverage: Home, Smart Sort, Organize, Files, Cleanup, Duplicates, Music, Video, Books, Fonts, Source Code, Subtitles, Photos, Raw Photos, Comics, Watch, Toolbox, and Settings are mapped in src/FileOrganizer.UI/Views/MainWindow.xaml.cs; rendered runtime/theme/accessibility behavior remains an explicit unaudited release pass because the build/display prerequisites were unavailable on 2026-08-10.
- Personas: a design-asset professional managing large marketplace libraries; a privacy-conscious media/document collector; and a technical operator who needs deterministic CLI plans, logs, and rollback. The repository explicitly constrains the product to a single user and local filesystem.
- Platforms and distribution: Windows x64 and ARM64 WinUI 3 shell targeting .NET 8/WindowsAppSDK 2.0.1, self-contained and unpackaged; Python 3.10+ with PyQt6 for the legacy GUI and CLI/NDJSON runners; GitHub release ZIP/PyInstaller paths; optional Ollama and external provider APIs.
- Data flows: filesystem paths and metadata enter Python extractors/classifiers; SQLite stores move journals, cache/catalog/fingerprint state; the shell consumes text or NDJSON from child processes; DeepSeek/GitHub Models/Anthropic/Ollama, Envato, AcoustID/MusicBrainz, GitHub Releases, and optional metadata binaries are external trust boundaries.

## Prioritized Direction

### Now

Ship the active roadmap’s P1 correctness/security items and the new fail-closed delete, sidecar protocol, Ollama installer, and dependency-lock items. They protect user data and determine whether the WinUI shell can be trusted as the primary product.

### Next

Ship the active CI/build, runtime accessibility/theme, packaging, and documentation items alongside the new catalog trust, persisted review, capability-health, provenance/evaluation, and NTFS incremental-index items. These turn working modules into a repeatable desktop product.

### Later

Use the existing roadmap’s semantic/embedding search, OCR, metadata write-back, i18n, accessibility completion, plugin SDK, local model registration, broader format support, and signed distribution work after the safety and release foundations are green.

### Under Consideration

REST/MCP/server mode, multi-user collaboration, cloud storage, and shared libraries remain product decisions rather than engineering defaults. They conflict with the stated single-user, local-first boundary and should not displace desktop reliability.

## Competitive Landscape

- [organize](https://github.com/tfeldmann/organize) does rule chains, all/any filters, content/EXIF filters, dry-run simulation, conflict policies, and JSON/YAML configuration well. FileOrganizer should finish its existing rule-builder/pipeline integration and make conflict behavior explicit; it should avoid exposing arbitrary shell/Python actions as an unguarded default.
- [AI File Sorter](https://github.com/hyperfield/ai-file-sorter) combines local/remote LLMs with taxonomy normalization, whitelists, cached decisions, a review-before-apply flow, and learning from approved corrections. FileOrganizer should make review corrections and provenance first-class; its AGPL license and broader taxonomy should not be copied into the MIT core.
- [TagSpaces](https://github.com/tagspaces/tagspaces) and its [documentation](https://docs.tagspaces.org/) demonstrate an offline, filesystem-oriented organizer using tags, notes, previews, and sidecar-friendly data rather than mandatory vendor storage. FileOrganizer should preserve portable metadata and offline operation; it should not become a general knowledge-management suite before its move safety is complete.
- [Czkawka](https://github.com/qarmin/czkawka), [fclones](https://github.com/pkolaczk/fclones), and [rmlint](https://rmlint.readthedocs.io/en/latest/) show the table stakes for large dedup jobs: staged hashing, persistent caches, reference/keep semantics, inspectable results, export/replay, and conservative deletion. FileOrganizer should borrow the safety and scale patterns, not undertake a Rust rewrite or adopt GPL code in the core.
- [digiKam](https://www.digikam.org/about/features/) and [Immich](https://github.com/immich-app/immich) show how metadata, labels, ratings, visual similarity, people, maps, and saved search make large libraries retrievable after organization. FileOrganizer should add a filesystem-preserving review/search layer; it should avoid Immich’s server, multi-user, and managed-library scope under the current constraints.
- [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx) demonstrates mature ingest, OCR, metadata, tags, automation, and searchable archive workflows. It is useful evidence for review queues and full-text retrieval, but its server/archive model is not the right near-term architecture for this desktop utility.
- Commercial tools provide clear parity signals: [File Juggler](https://www.filejuggler.com/documentation/) exposes condition/action rules, exclusions, schedules, templates, and extraction; [Eagle](https://en.eagle.cool/support/desktop/organize) exposes tags, smart folders, ratings, comments, duplicate review, and batch operations; Adobe Bridge’s [batch rename](https://helpx.adobe.com/bridge/desktop/organize-and-find-files/tag-and-find-files/batch-rename-files.html) preserves original names in XMP. FileOrganizer should learn the explicit rule/review language and metadata-preservation affordances without adopting cloud lock-in or proprietary assumptions.

## Security, Privacy, and Reliability

- Verified local risk: fileorganizer/dry_run_planner.py:258-271 permanently calls os.remove when send2trash is unavailable, despite the operation being described as “move to trash.” This is a separate gap from the active cleanup/dedup UI work and is added to ROADMAP.md.
- Verified local software-installation supply-chain risk: fileorganizer/workers.py:972-1017 downloads the live OllamaSetup.exe URL and executes it silently; the code does not pin a release, verify an Authenticode signature/hash, or request an explicit user decision. NVD CVE-2026-42248 documents an Ollama-for-Windows update-integrity weakness, so the repository must not make live installer execution an invisible prerequisite.
- Verified dependency risk: requirements.txt contains broad lower bounds and many optional packages but no resolved lock/hashes. Pillow’s release policy says security fixes are not expected to be backported, the py7zr changelog consulted on 2026-08-10 lists arbitrary-file-write, decompression-bomb, and complexity-DoS fixes in 1.1.3, and fonttools documents CVE-2025-66034. The active archive-quota item must be paired with patched dependency floors and a repeatable dependency audit.
- Existing active findings cover archive traversal, archive expansion limits, path-template/preset traversal, watch-root overlap, credentials in WinUI settings/argv, destructive directory merge, malformed classifier responses, cache initialization, partial retries, unbounded logs/results, and settings false-success states. New recommendations deliberately do not duplicate those items.
- The catalog sync in fileorganizer/workers.py:2817-2930 uses GitHub Releases metadata and browser_download_url, reads the full asset into memory, validates shape, and imports it through asset_db.import_community_json(). The active byte-limit item addresses resource exhaustion; a separate roadmap item addresses authenticity, rollback, consent, and offline operation.
- Privacy boundary: cloud providers receive classification payloads, the catalog contacts GitHub, and media enrichment can contact Envato, AcoustID, MusicBrainz, or ISBN services. The existing local-first and privacy-policy items should expose provider selection, payload scope, network use, retention, and opt-out before enabling automatic enrichment.
- Recovery needs to be per operation, not only per run: preserve original bytes or use the Recycle Bin/quarantine, record source/destination identity and hashes, validate paths again at apply/undo time, and make stale review results fail closed. A directory-level undo record is not sufficient for merged trees.

## Architecture Assessment

- The plan/journal boundary in organize_run.py is the best foundation: MovePlan, source/destination containment, source signatures, staged preflight, journal statuses, reports, and undo already exist. Extend that boundary with a per-operation recovery manifest and classification provenance rather than adding mutation logic to individual pages.
- The two shell paths are a sustained maintenance cost: WinUI pages launch many root-level runners through PythonRunner.cs/SidecarRunner.cs while legacy PyQt workers call the same core directly. Define one event schema, one capability/error vocabulary, and one action policy so a feature cannot silently behave differently in the two UIs.
- PythonRunner.cs parses stdout in background reader tasks while page callbacks mutate XAML controls; the active roadmap item correctly prioritizes dispatcher ownership. A versioned protocol should sit above that fix and include cancellation, terminal status, error codes, progress totals, and bounded log semantics.
- Several databases initialize on module import (catalog.py, move_journal.py, cache.py, llm_cache.py). The active initialization/thread-safety items should converge on idempotent migrations, explicit connections, WAL/busy-timeout policy, and a schema version. This is more important than adding another cache.
- Optional dependencies are handled by scattered ImportError fallbacks and sidecar-specific messages. A capability registry can make “metadata unavailable” distinct from “no metadata found,” give the WinUI shell deterministic feature availability, and prevent a degraded scan from looking successful.
- Testing is strong around Python helpers but weak at cross-process and C# boundaries: no direct .NET runner/page test project was found, and the full runtime/theme/accessibility and clean-machine package passes remain unaudited. The active CI/runtime/package items plus the new protocol and review fixtures should be prerequisites for new media integrations.

## Security, Accessibility, and Operations Coverage

- Security/data safety: active path/archive/secret findings plus the new fail-closed delete, installer verification, dependency lock, and catalog authenticity items.
- Accessibility: active focus, contrast, runtime matrix, and keyboard/screen-reader items; Microsoft’s WinUI guidance requires UI Automation names/roles, keyboard completion, high contrast, and contrast verification. Qt’s translation/accessibility stack should be covered when the legacy shell remains supported.
- i18n/l10n: existing roadmap items L-14, L-23, and L-24 cover resource extraction and taxonomy translation; no duplicate addition is made. Use WinUI .resw/x:Uid, Qt Linguist, and CLDR formatting when that work starts.
- Observability: existing NEXT-73 through NEXT-75 cover structured logs, metrics, and opt-in crash reporting; the new provenance item is per-decision evidence, not a duplicate telemetry proposal.
- Testing/docs/distribution: active CI, type/lint, README, runtime matrix, and clean-machine packaging items remain authoritative; the new lock item supplies resolved dependency evidence.
- Plugin ecosystem: existing NEXT-27/L-25 covers extensibility; PyPA entry points and pluggy are the recommended boundary when it is implemented. Plugins must be isolated from privileged filesystem mutations.
- Offline/resilience: the new catalog policy, persisted review results, and NTFS journal fallback extend the local-first design. Non-NTFS/network sources must retain a full-scan fallback.
- Mobile and multi-user: intentionally excluded under CLAUDE.md’s Windows-first, single-user constraint; Immich/FileGator are comparative evidence, not an immediate target.
- Migration/upgrade: the active package/upgrade item and existing SQLite schema migrations should be extended to protocol versions, catalog snapshots, review artifacts, and dependency rollback.

## Rejected Ideas

- Multi-user accounts, server mode, and collaborative permissions — rejected for the current product boundary; CLAUDE.md explicitly defines a single-user local desktop, while [FileGator](https://github.com/filegator/filegator) demonstrates the separate server/security scope this would introduce.
- Mobile companion and cloud library sync — rejected for the current tier because it requires an always-available sync/API/auth model and conflicts with filesystem ownership; [Immich](https://immich.app/features) is evidence of the size of that product surface.
- Automatic AI deletion or unattended deduplication — rejected because community discussions emphasize review, keep decisions, reference folders, and dry-run safety; see [Hacker News duplicate discussion](https://news.ycombinator.com/item?id=32686357) and the [DataHoarder duplicate-tool discussion](https://www.reddit.com/r/DataHoarder/comments/1tnleod/latestmost_up_to_date_duplicate_file_finder/).
- A Rust rewrite or broad cross-platform parity before Windows release hardening — rejected because the existing WinUI/Python boundary already has active correctness and packaging debt; Czkawka’s Rust architecture is a useful performance reference, not a reason to change the core stack.
- GPL/AGPL code or server components in the MIT core — rejected for license and architectural reasons; Czkawka, TagSpaces, and AI File Sorter are useful product references but cannot be copied into the core without a deliberate license boundary.
- Immediate C2PA authoring, REST, MCP, or marketplace partnerships — deferred to existing UC/P items until the local plan/journal, metadata sidecar policy, provider consent, and release artifacts are stable. C2PA/IPTC remain valid interoperability research, not a reason to bypass safety work.

## Sources

### Direct OSS competitors

- https://github.com/QiuYannnn/Local-File-Organizer
- https://github.com/hyperfield/ai-file-sorter
- https://github.com/iyaja/llama-fs
- https://github.com/tfeldmann/organize
- https://github.com/tagspaces/tagspaces
- https://github.com/qarmin/czkawka
- https://github.com/pkolaczk/fclones
- https://rmlint.readthedocs.io/en/latest/
- https://github.com/paperless-ngx/paperless-ngx
- https://github.com/jjuliano/aifiles
- https://github.com/immich-app/immich

### Commercial and adjacent products

- https://www.filejuggler.com/documentation/
- https://en.eagle.cool/
- https://en.eagle.cool/support/desktop/organize
- https://www.dropitproject.com/index.php
- https://filearbor.com/
- https://dolfer.app/
- https://helpx.adobe.com/bridge/desktop/organize-and-find-files/tag-and-find-files/batch-rename-files.html
- https://helpx.adobe.com/bridge/desktop/organize-and-find-files/organize-files-and-folders/use-collections.html
- https://www.digikam.org/about/features/
- https://docs.immich.app/features/searching/
- https://docs.immich.app/features/duplicates-utility/
- https://docs.kde.org/trunk_kf6/en/plasma-desktop/kcontrol/baloo/baloo.pdf
- https://docs.tagspaces.org/

### Awesome lists and community signal

- https://awesome-selfhosted.net/tags/document-management.html
- https://github.com/sunlei/awesome-tools/blob/master/README.md
- https://www.reddit.com/r/DataHoarder/comments/1tnleod/latestmost_up_to_date_duplicate_file_finder/
- https://www.reddit.com/r/DataHoarder/comments/1rwv9nr/finding_duplicates_of_files_in_source_folder/
- https://www.reddit.com/r/DataHoarder/comments/1usgq5b/what_do_you_use_to_find_duplicates/
- https://news.ycombinator.com/item?id=32686357
- https://news.ycombinator.com/item?id=45879946

### Standards and platform APIs

- https://docs.python.org/3.14/library/zipfile.html
- https://docs.python.org/3.14/library/tarfile.html
- https://owasp.org/www-community/attacks/Path_Traversal
- https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- https://learn.microsoft.com/en-us/windows/win32/fileio/change-journal-records
- https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/self-contained-deploy/deploy-self-contained-apps
- https://spec.c2pa.org/specifications/specifications/2.2/index.html
- https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html
- https://exiftool.org/metafiles.html

### Accessibility and localization

- https://learn.microsoft.com/en-us/windows/apps/design/accessibility/accessibility-overview
- https://learn.microsoft.com/en-us/windows/apps/design/input/keyboard-interactions
- https://learn.microsoft.com/en-us/windows/apps/develop/testing/
- https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- https://doc.qt.io/qt-6/localization.html
- https://learn.microsoft.com/en-us/windows/apps/develop/platform/xaml/x-uid-directive
- https://unicode.org/reports/tr35/

### Dependencies, security, and engineering guidance

- https://pillow.readthedocs.io/en/stable/releasenotes/
- https://py7zr.readthedocs.io/en/stable/Changelog.html
- https://github.com/pypa/pip-audit
- https://packaging.python.org/en/latest/specifications/pylock-toml/
- https://github.com/fonttools/fonttools/blob/main/NEWS.rst
- https://nvd.nist.gov/vuln/detail/CVE-2025-66034
- https://nvd.nist.gov/vuln/detail/CVE-2026-42248
- https://ollama.readthedocs.io/en/windows/
- https://packaging.python.org/en/latest/specifications/entry-points/
- https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/
- https://pluggy.readthedocs.io/en/stable/
- https://docs.ollama.com/capabilities/structured-outputs
- https://arxiv.org/abs/2212.09422

## Open Questions

- Which signed distribution channel is authoritative for the next release: GitHub ZIP, MSIX/Store, or both? This changes installer, update, and signing work.
- Which initial display languages and taxonomy locales should be supported? This is a product/translation decision, not inferable from the repository.
- Should community catalog authenticity use a repository-published checksum/signature or a separately managed signing key? The implementation can support either, but the trust anchor needs an owner.
