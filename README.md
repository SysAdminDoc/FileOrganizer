# FileOrganizer

![Version](https://img.shields.io/badge/version-7.5.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Status](https://img.shields.io/badge/status-active-success)
![AI Powered](https://img.shields.io/badge/AI-Ollama%20LLM-e879f9)

> AI-powered desktop tool that automatically classifies, renames, and organizes files and folders using a local LLM, a 7-level rule engine, cleanup tools, duplicate detection, and a premium dark-themed GUI.

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

## Configuration

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
| `mistral:7b` | 4.1 GB | Medium | Good | `ollama pull mistral:7b` |

### Themes

Click **Settings > Color Theme** to choose from 6 dark themes with live preview:
- **Steam Dark** (default) — Deep blue-black with cyan accents
- **Catppuccin Mocha** — Warm purple-blue palette
- **OLED Black** — True black for OLED displays
- **GitHub Dark** — GitHub's dark mode colors
- **Nord** — Arctic blue-gray palette
- **Dracula** — Classic purple-accented dark theme

### Protected Paths

Click **Settings > Protected Paths** to manage system folder protection. Platform-aware defaults include Windows system directories, AppData, and common dotfiles. Custom paths can be added.

## Prerequisites

- **Python 3.10+**
- **8 GB RAM** minimum (for Ollama LLM models)
- **~5 GB disk space** for the default `qwen2.5:7b` model
- **Internet connection** for first launch only (Ollama install + model download)
- Works without Ollama — falls back to rule-based engine automatically

Auto-installed dependencies: PyQt6, rapidfuzz, psd-tools, Pillow, and more.

## CLI Usage

```bash
python run.py                                    # Launch GUI
python run.py --source "C:/Users/You/Downloads"  # Auto-scan a folder
python run.py --profile MyProfile --auto-apply   # Automated profile scan
python run.py --dry-run --profile MyProfile --auto-apply  # Simulate without moving
python -m fileorganizer                           # Alternative launch
```

## FAQ

**Ollama won't install automatically** — Download from [ollama.com/download](https://ollama.com/download), then restart FileOrganizer.

**LLM shows "unavailable"** — Start the server manually: `ollama serve`, then restart.

**Classification is slow** — Each item takes 2-5s with LLM. Use rule-based mode (uncheck LLM) for bulk scans. A GPU (RTX 3060+) processes items in under 1s.

**How do I add categories?** — Settings > Edit Categories. Add categories with keywords. Saved to JSON and available immediately.

## Related Tools

| Tool | Best For |
|------|----------|
| **FileOrganizer** (this repo) | Focused file organization — AI classification, cleanup, duplicates, photo management |
| [UniFile](https://github.com/SysAdminDoc/UniFile) | Everything in FileOrganizer plus a tag-based file library (TagStudio-style), movie/TV metadata lookup (TMDb/TVMaze), and Nexa vision AI backend |

If you want tag-based organization with hierarchical tags, TMDb/TVMaze metadata, or LLaVA vision classification, see [UniFile](https://github.com/SysAdminDoc/UniFile) — the all-in-one successor built on this project's foundation.

## Contributing

Issues and PRs welcome. The codebase is modular — categories in `categories.py`, classification in `classifier.py`, UI in `main_window.py` and `dialogs.py`.

## License

MIT License — see [LICENSE](LICENSE) for details.
