<!-- codex-branding:start -->
<p align="center"><img src="icon.ico" width="128" alt="File Organizer"></p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-8.1.0-58A6FF?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-4ade80?style=for-the-badge">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Python%20GUI-58A6FF?style=for-the-badge">
</p>
<!-- codex-branding:end -->

# FileOrganizer

![Version](https://img.shields.io/badge/version-8.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Status](https://img.shields.io/badge/status-active-success)
![AI Powered](https://img.shields.io/badge/AI-DeepSeek%20%7C%20GitHub%20Models%20%7C%20Ollama-e879f9)

> AI-powered desktop tool that automatically classifies, renames, and organizes design asset folders at scale using multi-provider AI (DeepSeek, GitHub Models, Ollama), a community fingerprint database, and a robust CLI batch runner with undo support.

![Screenshot](screenshot.png)

## Quick Start

```bash
git clone https://github.com/SysAdminDoc/FileOrganizer.git
cd FileOrganizer
python run.py  # Auto-installs all dependencies + Ollama on first run
```

That's it. On launch, FileOrganizer will:
1. Install PyQt6, rapidfuzz, psd-tools, and other dependencies if missing
2. Download and install [Ollama](https://ollama.com) if not found
3. Start the Ollama server if not running
4. Pull the `qwen2.5:7b` model if not already downloaded
5. Open the GUI with LLM mode enabled and ready

No manual setup required.

## What It Does

FileOrganizer handles two major workflows:

### 1. Design Asset Organization
Sort hundreds of messy marketplace downloads (Envato, Creative Market, Freepik) into a clean category tree. The LLM reads folder names and filenames, strips marketplace junk, and picks the best category from 384+ built-in categories.

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
├── Flyers & Print/
│   └── Neon Night Club Party Flyer/
├── Invitations & Save the Date/
│   └── Elegant Wedding Invitation Set/
└── ...
```

### 2. PC File Organizer
Scan any folder (Downloads, Desktop, etc.) and auto-sort files by type into organized category folders with configurable output mapping per category.

## Features

### Core
| Feature | Description |
|---------|-------------|
| Ollama LLM Classification | Local AI-powered category + name inference via Ollama |
| Auto Ollama Setup | Installs Ollama, starts server, pulls model on first launch |
| 384+ Built-in Categories | Covers design, video, audio, print, web, 3D, photography |
| 7-Level Classification Pipeline | Extension > Keyword > Fuzzy > Metadata > Envato API > Composition > Context |
| PC File Organizer | Sort any folder's files by type with configurable output mapping |
| Multiple Scan Profiles | Design Assets, PC Files, Photo Library, and custom profiles |
| Classification Rules Editor | Create custom if/then rules with condition builder UI |
| Rename Template Engine | Token-based rename templates with live preview |

### Organization Modes
| Mode | Description |
|------|-------------|
| Rename .aep Folders | Renames After Effects project folders by their largest `.aep` filename |
| Categorize Folders | Sorts folders into category groups using AI + rules |
| Categorize + Smart Rename | Full AI rename + categorization in one pass |
| PC File Organizer | Sorts individual files by extension/type with per-category output paths |

### Cleanup Tools (v7.0+)
| Tool | Description |
|------|-------------|
| Empty Folders | Find and delete empty directories |
| Empty Files | Find zero-byte files |
| Temp / Junk Files | Find `.tmp`, `.bak`, `Thumbs.db`, etc. |
| Broken Files | Detect corrupt/truncated files |
| Big Files | Find files above a configurable size threshold |
| Old Downloads | Find stale files in download folders |

All cleanup scanners show results **progressively** as items are discovered.

### Duplicate Finder (v7.0+)
- Progressive hash-based duplicate detection: Size > Prefix hash > Suffix hash > Full SHA-256
- Perceptual image hashing for near-duplicate photos
- Side-by-side duplicate comparison dialog
- Configurable similarity tolerance

### Photo Organization (v7.0+)
- EXIF metadata extraction (date, camera, GPS)
- Photo map view with geotagged photo markers (Leaflet)
- AI Event Grouping — cluster photos by event using vision descriptions
- Face detection and person-based organization (optional)
- Thumbnail grid view with flow layout

### Watch Mode
- Monitor folders for changes and auto-organize new files
- System tray integration with minimize-to-tray
- Configurable delay and folder list
- **Watch History** — log of all auto-organize events with timestamps

### UI & UX
| Feature | Description |
|---------|-------------|
| 6 Color Themes | Steam Dark, Catppuccin Mocha, OLED Black, GitHub Dark, Nord, Dracula |
| Live Theme Preview | See themes applied instantly before committing |
| Czkawka-Inspired Sidebar | Left navigation panel with section grouping |
| Before/After Preview | Visual directory tree comparison |
| File Relationship Graph | Interactive graph showing file connections |
| File Preview Panel | Split-view with image preview, text excerpt, metadata |
| Thumbnail Grid View | Visual grid with flow layout for image-heavy scans |
| Dashboard Bar Chart | Interactive category distribution chart with drag-reassign |
| Drag & Drop | Drop folders onto the window to set source |
| Protected Paths | System folder protection prevents accidental moves |
| Undo Timeline | Visual timeline of all operations with one-click rollback |
| Plugin System | Extensible plugin architecture for custom behavior |
| Scheduled Scans | Windows Task Scheduler integration for automated scans |
| Shell Extension | Right-click "Organize with FileOrganizer" in Windows Explorer |

### Safety
- **Preview before apply** — full destination tree preview before any files move
- **Protected paths** — system folders and important files are guarded at scan, apply, and delete layers
- **Safe merge-move** — merging into existing folders preserves all files
- **Progressive hash dedup** — SHA-256 + perceptual hash prevents overwrites
- **Full undo log** — every operation recorded with one-click rollback
- **CSV audit trail** — every classification logged with timestamp, method, confidence
- **Crash handler** — unhandled exceptions saved to crash log with MessageBox notification

## Architecture

```
fileorganizer/
├── __init__.py          # Package version
├── __main__.py          # Entry point with crash handler
├── bootstrap.py         # Auto-dependency installer
├── config.py            # Settings, themes, protected paths
├── categories.py        # 384+ category definitions
├── classifier.py        # 7-level classification engine
├── engine.py            # Rule engine, scheduler, templates
├── naming.py            # Smart rename logic
├── metadata.py          # File metadata extraction
├── ollama.py            # Ollama LLM integration
├── photos.py            # Photo/EXIF/face processing
├── files.py             # PC file organizer logic
├── cache.py             # Classification cache, undo log
├── models.py            # Data models (ScanItem, etc.)
├── workers.py           # QThread workers for scanning/applying
├── plugins.py           # Plugin system, profiles, presets
├── profiles.py          # Scan profile management
├── cleanup.py           # Cleanup scanners (6 types)
├── duplicates.py        # Duplicate detection engine
├── dialogs.py           # All dialog windows and panels
├── widgets.py           # Custom Qt widgets (charts, map, preview)
└── main_window.py       # Main application window
```

## CLI Batch Runner (v8+)

```bash
# AE pipeline (I:\After Effects → G:\Organized)
python organize_run.py --stats                    # Show all classified batches
python organize_run.py --preview --quiet          # Dry run: see what would move
python organize_run.py --apply --quiet            # Apply all moves
python organize_run.py --retry-errors             # Retry failed items

# Design pipeline (G:\Design Unorganized → G:\Organized)
python organize_run.py --source design --preview --quiet
python organize_run.py --source design --apply --quiet

# Plan-first apply flow
python organize_run.py --source design --preview --plan-out plan.json
python organize_run.py --apply-plan plan.json
python organize_run.py --report <RUN_ID> --output report.md

# Undo support
python organize_run.py --undo-last 10             # Reverse last 10 moves
python organize_run.py --undo-all                 # Reverse everything

# Validate sources before moving
python organize_run.py --validate                 # Report trailing-space/long-path issues
```

## Community Fingerprint Database (v8.1+)

```bash
python asset_db.py --build G:\Organized          # Hash every file, build SQLite DB
python asset_db.py --stats                       # Show DB summary
python asset_db.py --export                      # Export asset_fingerprints.json
python asset_db.py --lookup "path/to/folder"     # Look up a folder in the DB
```

The fingerprint DB enables any FileOrganizer user to match their locally-downloaded templates against a community-curated catalog of already-classified assets by SHA-256 hash — getting clean names and categories instantly without an AI API call.

## Configuration

### AI Providers (v8+)

Click **Settings > AI Providers** to configure:

| Provider | Use | Model |
|----------|-----|-------|
| DeepSeek | Heavy classification batches | `deepseek-chat` |
| GitHub Models | Fast lightweight checks | `claude-3-5-haiku` |
| Ollama | Local/offline fallback | Any local model |

Set `DEEPSEEK_API_KEY` in your environment to enable DeepSeek routing.

### Ollama Settings

Click **Settings > Ollama LLM** to configure:

| Setting | Default | Description |
|---------|---------|-------------|
| URL | `http://localhost:11434` | Ollama server address |
| Model | `qwen2.5:7b` | Model for classification |
| Timeout | 30s | Per-item LLM timeout |

**Recommended models:**

| Model | Size | Speed | Accuracy | Install |
|-------|------|-------|----------|---------|
| `qwen2.5:7b` | 4.7 GB | Medium | Best | `ollama pull qwen2.5:7b` |
| `llama3.2:3b` | 2.0 GB | Fastest | Good | `ollama pull llama3.2:3b` |
| `gemma3:4b` | 3.3 GB | Fast | Good | `ollama pull gemma3:4b` |

### Themes

Click **Settings > Color Theme** to choose from 6 dark themes with live preview:
- **Steam Dark** (default) — Deep blue-black with cyan accents
- **Catppuccin Mocha** — Warm purple-blue palette
- **OLED Black** — True black for OLED displays
- **GitHub Dark** — GitHub's dark mode colors
- **Nord** — Arctic blue-gray palette
- **Dracula** — Classic purple-accented dark theme

## Architecture (v8+)

```
FileOrganizer/
├── fileorganizer/           # GUI package
│   ├── providers.py         # Multi-provider AI router (DeepSeek, GitHub Models, Ollama)
│   ├── catalog.py           # Marketplace lookup + fingerprint DB pre-check
│   ├── archive_extractor.py # ZIP/RAR/7z inspection without full extraction
│   ├── categories.py        # 84+ canonical category definitions
│   ├── workers.py           # QThread workers
│   └── main_window.py       # Main GUI window
├── organize_run.py          # CLI batch runner (Phase 1+2 apply)
├── classify_design.py       # DeepSeek batch classifier for design assets
├── asset_db.py              # Community SHA-256 fingerprint DB
├── org_index.json           # Master index: I:\After Effects items
├── design_unorg_index.json  # Master index: G:\Design Unorganized items
└── classification_results/  # batch_NNN.json + design_batch_NNN.json outputs
```

## FAQ

**Ollama won't install automatically** — Download from [ollama.com/download](https://ollama.com/download), then restart FileOrganizer.

**LLM shows "unavailable"** — Start the server manually: `ollama serve`, then restart.

**Classification is slow** — Use DeepSeek for bulk batches (60 items/call, ~1-2s). Ollama is per-item; use it only for small jobs.

**How do I add categories?** — Settings > Edit Categories. Add categories with keywords. Saved to JSON and available immediately.

**Why position-based batch mapping?** — AI agents may clean or reformat folder names in their response. The only reliable mapping is by position: `batch_NNN.json[i]` always corresponds to `org_index[(N-1)*60 + i]` regardless of name changes.

## Related Tools

| Tool | Best For |
|------|----------|
| **FileOrganizer** (this repo) | Focused file organization — AI classification, cleanup, duplicates, photo management |
| [UniFile](https://github.com/SysAdminDoc/UniFile) | Everything in FileOrganizer plus a tag-based file library (TagStudio-style), movie/TV metadata lookup (TMDb/TVMaze), and Nexa vision AI backend |

If you want tag-based organization with hierarchical tags, TMDb/TVMaze metadata, or LLaVA vision classification, see [UniFile](https://github.com/SysAdminDoc/UniFile) — the all-in-one successor built on this project's foundation.

## Contributing

Issues and PRs welcome. The codebase is modular — categories in `categories.py`, classification in `catalog.py`, UI in `main_window.py`.

## License

MIT License — see [LICENSE](LICENSE) for details.
