# ROADMAP -- FileOrganizer

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

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
