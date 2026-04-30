# FileOrganizer

![Shell](https://img.shields.io/badge/shell-FileOrganizer.UI%20v0.2.0-22d3ee)
![Core](https://img.shields.io/badge/core-Python%20v8.2.0-3776AB)
![License](https://img.shields.io/badge/license-MIT-green)
![.NET](https://img.shields.io/badge/.NET-8.0-512BD4?logo=dotnet&logoColor=white)
![WinUI](https://img.shields.io/badge/WinUI-3-0078D6)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![AI](https://img.shields.io/badge/AI-DeepSeek%20%7C%20GitHub%20Models%20%7C%20Ollama-e879f9)

> Hybrid file organizer for Windows. A C# / .NET 8 / WinUI 3 desktop shell
> drives a Python core that handles AI classification (DeepSeek, GitHub
> Models, Ollama), six cleanup scanners, progressive hash + perceptual
> dedup, and EXIF-aware photo workflows.

![Screenshot](screenshot.png)

## What's in this repo

```
src/FileOrganizer.UI/   ← C# / WinUI 3 desktop shell (new — v0.2.0)
fileorganizer/          ← Python core (legacy PyQt6 GUI + library code)
*.py at repo root       ← CLI runners + NDJSON sidecars (organize_run, cleanup_run, asset_db, ...)
```

The shell exists to replace the legacy PyQt6 GUI with a UCX-style
side-tab `NavigationView` and tile dashboard, while keeping every line of
the AI / dedup / photo logic in Python where the ecosystem lives. The
two halves talk over `stdout` (text or NDJSON). The legacy PyQt6 GUI
keeps working in parallel until the shell reaches feature parity.

| Page in shell | Status (v0.2.0) | Wraps |
|---|---|---|
| Home | Live | — |
| Organize | Live | `organize_run.py` |
| Cleanup | Live | `cleanup_run.py` |
| Files / Duplicates / Photos / Watch / Toolbox | Placeholder | TBD |

## Get FileOrganizer

Two install paths, pick the one that fits.

### Path A — WinUI 3 shell preview (recommended for new users)

Grab the latest release zip from
[Releases](https://github.com/SysAdminDoc/FileOrganizer/releases) (look
for `ui-v*` tags) and extract it anywhere.

```
shell\FileOrganizer.exe   ← double-click to launch
organize_run.py · cleanup_run.py · fileorganizer\ · requirements.txt
```

The shell is self-contained for .NET 8, but the live pages still call
into Python — install Python 3.10+ on PATH (or drop a
`.venv\Scripts\python.exe` next to the scripts at the extract root, or
set `%FILEORGANIZER_PYTHON%`), then once:

```pwsh
python -m pip install -r requirements.txt
```

### Path B — Python core only (legacy PyQt6 GUI + CLI)

```bash
git clone https://github.com/SysAdminDoc/FileOrganizer.git
cd FileOrganizer
python run.py        # auto-installs deps + Ollama, opens the PyQt6 GUI
```

On first launch this path will:
1. Install PyQt6, rapidfuzz, psd-tools, and other dependencies if missing.
2. Download and install [Ollama](https://ollama.com) if not found.
3. Pull the `qwen2.5:7b` model if not already downloaded.

## Build the WinUI 3 shell from source

```pwsh
pwsh src/build.ps1                         # Debug build
pwsh src/build.ps1 -Configuration Release  # Release build
```

The script wraps **VS 2026 MSBuild** because bare `dotnet build` against
the .NET 10 SDK fails on the WindowsAppSDK 1.5 AppX/PRI task path. It
also cleans `obj/` + `bin/` first and runs `Restore` and `Build` as
separate invocations to avoid a known MarkupCompilePass2 cascade.

Output: `src/FileOrganizer.UI/bin/x64/Debug/net8.0-windows10.0.19041.0/FileOrganizer.exe`.

## Major workflows

### Design Asset Organization (the original use case)

Sort thousands of marketplace downloads (Envato, Creative Market, Freepik)
into a clean category tree. The LLM reads folder + filenames, strips
marketplace junk, and picks from 384+ built-in categories.

**Before:**
```
Downloads/
├── GraphicRiver - Neon Night Club Party Flyer Template 28394756/
├── CM_elegant-wedding-invitation-set_4829173/
├── christmas-slideshow-after-effects-21098345/
└── ... 2,000 more like this
```

**After:**
```
Organized/
├── After Effects - Slideshows/
│   └── Christmas Slideshow/
├── Print - Flyers & Posters/
│   └── Neon Night Club Party Flyer/
├── Print - Invitations & Events/
│   └── Elegant Wedding Invitation Set/
└── ...
```

Drive it from the **Organize** page in the shell, or directly from the
CLI runner — see [CLI Batch Runner](#cli-batch-runner) below.

### Cleanup

Six progressive scanners, all wired into the **Cleanup** page in the shell
(or callable as `python cleanup_run.py --scanner <name> --root <path>`):

| Scanner | What it finds |
|---|---|
| Empty folders | Recursively-empty directory trees, deepest-first |
| Empty files | Zero-byte files |
| Temp / junk | `.tmp`, `.bak`, `Thumbs.db`, `~$*`, `.DS_Store`, partial downloads |
| Broken / corrupt | Magic-byte mismatches + optional ZIP/TAR integrity check |
| Big files | Files above a configurable MB threshold |
| Old downloads | Files not accessed in N days at the top of a folder |

Results stream live as items are discovered. Cancellation kills the child
Python process tree.

### Duplicates, Photos, Watch (Python-side, shell pages still placeholders)

- **Progressive hash dedup** — Size > prefix hash > suffix hash > full
  SHA-256, plus perceptual image hashing for near-duplicate photos.
- **Photos** — EXIF metadata, Leaflet geotag map, AI event clustering,
  optional face detection, thumbnail grid.
- **Watch mode** — monitor folders, auto-organize new files, system tray.

These all work today through `python -m fileorganizer` (Path B). Shell
pages will land in subsequent `ui-v0.X.Y` releases.

## CLI Batch Runner

```bash
# AE pipeline (I:\After Effects → G:\Organized)
python organize_run.py --stats                    # Show all classified batches
python organize_run.py --preview --quiet          # Dry run
python organize_run.py --apply --quiet            # Apply all moves
python organize_run.py --retry-errors             # Retry failed items

# Design pipeline (G:\Design Unorganized → G:\Organized)
python organize_run.py --source design --preview --quiet
python organize_run.py --source design --apply --quiet

# Plan-first apply
python organize_run.py --source design --preview --plan-out plan.json
python organize_run.py --apply-plan plan.json
python organize_run.py --report <RUN_ID> --output report.md

# Undo
python organize_run.py --undo-last 10
python organize_run.py --undo-all

# Validate sources
python organize_run.py --validate
```

## Community Fingerprint Database

```bash
python asset_db.py --build G:\Organized          # Hash every file → SQLite DB
python asset_db.py --stats                       # DB summary
python asset_db.py --export                      # asset_fingerprints.json
python asset_db.py --lookup "path/to/folder"     # Look up a folder
```

Match locally-downloaded templates against a community-curated catalog of
already-classified assets by SHA-256 — get clean names and categories
instantly without an AI API call.

## Configuration

### AI Providers

| Provider | Use | Model |
|---|---|---|
| DeepSeek | Heavy classification batches | `deepseek-chat` |
| GitHub Models | Fast lightweight checks | `claude-3-5-haiku` |
| Ollama | Local / offline fallback | Any local model |

Set `DEEPSEEK_API_KEY` to enable DeepSeek routing.

### Ollama models

| Model | Size | Speed | Accuracy | Install |
|---|---|---|---|---|
| `qwen2.5:7b` | 4.7 GB | Medium | Best | `ollama pull qwen2.5:7b` |
| `llama3.2:3b` | 2.0 GB | Fastest | Good | `ollama pull llama3.2:3b` |
| `gemma3:4b` | 3.3 GB | Fast | Good | `ollama pull gemma3:4b` |

### Themes (legacy PyQt6 GUI)

Six dark themes with live preview: **Steam Dark** (default), Catppuccin
Mocha, OLED Black, GitHub Dark, Nord, Dracula. The WinUI 3 shell uses the
Steam Dark palette with a cyan accent and currently does not expose a
theme picker.

## Architecture

### WinUI 3 shell

```
src/FileOrganizer.UI/
├── App.xaml(.cs)             ← brand tokens, DI, crash handler
├── Views/
│   ├── MainWindow.xaml(.cs)  ← side-tab NavigationView shell
│   └── Pages/
│       ├── HomePage          ← hero + tile grid + cluster cards
│       ├── OrganizePage      ← live, runs organize_run.py
│       ├── CleanupPage       ← live, runs cleanup_run.py over NDJSON
│       └── PlaceholderPage   ← parameterized stub for unwired routes
├── Services/
│   ├── PythonRunner.cs       ← text + NDJSON Python invocation
│   └── SidecarRunner.cs      ← NDJSON for future tools/<name>/<name>.exe
└── FileOrganizer.UI.csproj
```

### Python core

```
fileorganizer/
├── classifier.py             ← 7-level classification engine
├── categories.py             ← 384+ canonical category definitions
├── providers.py              ← multi-provider AI router (DeepSeek + GH + Ollama)
├── catalog.py                ← marketplace lookup + fingerprint DB pre-check
├── cleanup.py                ← six cleanup scanners
├── duplicates.py             ← progressive hash + perceptual image hash
├── photos.py                 ← EXIF / faces / events / map markers
├── files.py                  ← PC file organizer
├── workers.py                ← QThread workers (legacy GUI)
├── main_window.py            ← legacy PyQt6 main window
└── ...

repo root:
├── organize_run.py           ← CLI batch runner (text-stdout sidecar)
├── cleanup_run.py            ← NDJSON sidecar for the Cleanup page
├── asset_db.py               ← community SHA-256 fingerprint DB
├── classify_design.py        ← DeepSeek batch classifier for design assets
└── deepseek_research.py      ← _Review-folder ID resolver
```

## FAQ

**Should I install Path A (shell) or Path B (Python)?** — If you want the
new UI and you're on Windows, Path A. If you're on Linux/macOS, or you
need the photo / duplicates / watch features today, Path B. Both share
the same `fileorganizer/` package so you can switch later.

**Ollama won't install automatically** — Download from
[ollama.com/download](https://ollama.com/download), then restart.

**Classification is slow** — Use DeepSeek for bulk batches (60 items/call,
~1–2s). Ollama is per-item; use it only for small jobs.

**Why position-based batch mapping?** — AI agents may clean or reformat
folder names in their response. The only reliable mapping is by position:
`batch_NNN.json[i]` always corresponds to `org_index[(N-1)*60 + i]`
regardless of name changes.

**Why two release tag schemes (`v8.x` vs `ui-v0.x`)?** — The Python core
and the WinUI 3 shell version independently. Python uses `vX.Y.Z`, the
shell uses `ui-vX.Y.Z`, and they release on their own cadences.

## Related Tools

| Tool | Best for |
|---|---|
| **FileOrganizer** (this repo) | Focused file organization — AI classification, cleanup, dedup, photo |
| [UniFile](https://github.com/SysAdminDoc/UniFile) | Everything here plus tag-based library, TMDb/TVMaze lookup, LLaVA vision |

## Contributing

Issues and PRs welcome. The codebase is modular — categories in
`fileorganizer/categories.py`, classification in
`fileorganizer/catalog.py`, legacy GUI in `fileorganizer/main_window.py`,
shell in `src/FileOrganizer.UI/`.

## License

MIT — see [LICENSE](LICENSE).
