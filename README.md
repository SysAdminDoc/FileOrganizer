# FileOrganizer

![Version](https://img.shields.io/badge/version-4.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Status](https://img.shields.io/badge/status-active-success)
![AI Powered](https://img.shields.io/badge/AI-Ollama%20LLM-e879f9)

> AI-powered desktop tool that automatically classifies, renames, and organizes thousands of design asset folders into marketplace-ready category structures using a local LLM and a 7-level rule engine.

![Screenshot](screenshot.png)

## Quick Start

```bash
git clone https://github.com/SysAdminDoc/FileOrganizer.git
cd FileOrganizer
python FileOrganizer.py  # Auto-installs all dependencies + Ollama on first run
```

That's it. On launch, FileOrganizer will:
1. Install PyQt6, rapidfuzz, and psd-tools if missing
2. Download and install [Ollama](https://ollama.com) if not found
3. Start the Ollama server if not running
4. Pull the `qwen2.5:7b` model if not already downloaded
5. Open the GUI with LLM mode enabled and ready

No manual setup required.

## What It Does

FileOrganizer solves a specific problem: you have hundreds or thousands of design asset folders downloaded from marketplaces (Envato, Creative Market, Freepik, etc.) with messy names like `GraphicRiver - Neon Night Club Party Flyer Template 28394756 + Bonus` and you need them sorted into a clean category tree.

**Before:**
```
Downloads/
├── GraphicRiver - Neon Night Club Party Flyer Template 28394756/
├── CM_elegant-wedding-invitation-set_4829173/
├── christmas-slideshow-after-effects-21098345/
├── fitness-gym-brochure-trifold-psd/
├── 38291_business_card_mockup_v2/
└── ... 2,000 more like this
```

**After:**
```
Organized/
├── After Effects - Slideshows/
│   └── Christmas Slideshow/
├── Brochures & Bi-Fold & Tri-Fold/
│   └── Fitness Gym Brochure/
├── Business Cards/
│   └── Business Card Mockup/
├── Flyers & Print/
│   └── Neon Night Club Party Flyer/
├── Invitations & Save the Date/
│   └── Elegant Wedding Invitation Set/
└── ...
```

The LLM reads folder names and actual filenames inside each folder, strips marketplace junk (IDs, site prefixes, version numbers), produces a clean project title, and picks the best category from 384 built-in categories.

## Features

| Feature | Description | Default |
|---------|-------------|---------|
| Ollama LLM Classification | Every folder analyzed by local AI for category + clean name | Enabled |
| Auto Ollama Setup | Installs Ollama, starts server, pulls model on first launch | Automatic |
| Context-Aware Inference | Detects asset TYPE from filenames (flyer, brochure, card) even when folder name is just a topic | Enabled |
| 384 Built-in Categories | Covers After Effects, Premiere Pro, Photoshop, print design, social media, web, 3D, audio, and more | - |
| 7-Level Classification Pipeline | Extension → Keyword → Fuzzy → Metadata → Envato API → Composition → Context | Automatic |
| LLM Folder Renaming | Strips marketplace IDs, codes, site prefixes. Outputs clean Title Case names | With LLM |
| Fuzzy Matching | rapidfuzz-powered approximate matching for misspelled or truncated names | Enabled |
| PSD/PRPROJ Metadata | Extracts project names and keywords from Photoshop and Premiere Pro files | Enabled |
| Envato API Enrichment | Looks up item metadata via Envato Market API for precise classification | Optional |
| AEP Batch Rename | Renames After Effects project folders by their largest `.aep` filename | Mode 1 |
| Hash Deduplication | MD5-based skip for identical files during merge-move operations | Optional |
| Undo / Rollback | Full undo log for every move operation. One-click rollback | Enabled |
| Destination Tree Preview | Visual tree showing where every folder will land before you commit | Button |
| Custom Categories | Add your own categories via the built-in editor. Persisted to JSON | Available |
| CSV Audit Logging | Logs every classification decision with confidence, method, and detail | Automatic |
| Dark Theme GUI | Professional dark Fusion-style interface | Enabled |
| Drag & Drop | Drop a folder onto the window to set it as source | Enabled |
| Safe Merge-Move | Merges into existing destinations without data loss | Enabled |

## How It Works

```
┌──────────────┐     ┌──────────────────────────────────────────────────┐     ┌──────────────┐
│              │     │          CLASSIFICATION ENGINE                    │     │              │
│  Source Dir  │────>│                                                  │────>│  Organized   │
│              │     │  LLM Mode (Ollama):                             │     │  Output Dir  │
│  2,000       │     │    Folder name + filenames → qwen2.5:7b         │     │              │
│  messy       │     │    Returns: {name, category, confidence}        │     │  384         │
│  folders     │     │    Falls back to rules if LLM fails             │     │  category    │
│              │     │                                                  │     │  folders     │
│              │     │  Rule-Based Pipeline:                           │     │              │
│              │     │    L1  Extension Map (23 rules)                 │     │              │
│              │     │    L2  Keyword Match (384 categories)           │     │              │
│              │     │    L2.5 Fuzzy Match (rapidfuzz 75%)             │     │              │
│              │     │    L3  Metadata (.prproj XML, .psd layers)      │     │              │
│              │     │    L3.5 Envato API lookup                       │     │              │
│              │     │    L4  Folder Composition heuristics            │     │              │
│              │     │    L5  Context Inference (topic → asset type)   │     │              │
│              │     │                                                  │     │              │
└──────────────┘     └──────────────────────────────────────────────────┘     └──────────────┘
```

### Classification Pipeline Detail

**Level 1 — Extension Mapping:** 23 extension groups map directly to categories. A folder of `.ttf`/`.otf` files → `Fonts & Typography`. A folder of `.cube`/`.3dl` files → `Premiere Pro - LUTs & Color`. Fires at 80%+ confidence.

**Level 2 — Keyword Matching:** 384 categories with curated keyword lists. The folder name is cleaned (marketplace prefixes stripped, separators normalized), then matched against all category keywords. Fires at 65%+ confidence.

**Level 2.5 — Fuzzy Matching:** When exact keywords don't hit, rapidfuzz token-set matching finds approximate matches at 75%+ similarity. Catches misspellings, abbreviations, and creative naming.

**Level 3 — Metadata Extraction:** Opens `.prproj` files (XML) to extract project names and composition names. Reads `.psd` layer names via psd-tools. Feeds extracted text back through keyword matching.

**Level 3.5 — Envato API:** If a numeric Envato item ID is detected in the folder name, queries the Envato Market API for the item's official category and tags. Requires an API key (optional).

**Level 4 — Composition Heuristics:** Analyzes the mix of file extensions and subfolder structure. A folder with `.aep` + a `/footage/` subfolder → `After Effects - Templates`. Pure image folders → `Stock Images`.

**Level 5 — Context Inference (v4.0):** The key innovation. When the pipeline returns a *topic* category (like `Club & DJ`) but the folder contains design template files (`.psd`, `.ai`), the engine scans filenames for asset type clues (`flyer`, `brochure`, `business-card`, `menu`, `poster`, etc.) and overrides the topic with the actual asset type. Result: `Night Club` + PSD flyers → `Flyers & Print/Night Club/` instead of `Club & DJ/Night Club/`.

### LLM Mode

When enabled (default), every folder is sent to a local Ollama instance with a structured prompt containing the folder name, up to 40 filenames, and the full list of 384 valid categories. The LLM returns a JSON object with the cleaned name, best category, and confidence score. If the LLM produces an invalid category name, rapidfuzz corrects it against the valid list. If the LLM is unreachable or returns garbage, the folder falls back to the rule-based pipeline automatically.

## Configuration

### Ollama Settings

Click **Ollama LLM** in the toolbar to configure:

| Setting | Default | Description |
|---------|---------|-------------|
| URL | `http://localhost:11434` | Ollama server address |
| Model | `qwen2.5:7b` | Model for classification. See recommendations below |
| Timeout | 30s | Per-folder LLM timeout |

**Recommended models:**

| Model | Size | Speed | Accuracy | Install |
|-------|------|-------|----------|---------|
| `qwen2.5:7b` | 4.7 GB | Medium | Best | `ollama pull qwen2.5:7b` |
| `llama3.2:3b` | 2.0 GB | Fastest | Good | `ollama pull llama3.2:3b` |
| `gemma3:4b` | 3.3 GB | Fast | Good | `ollama pull gemma3:4b` |
| `mistral:7b` | 4.1 GB | Medium | Good | `ollama pull mistral:7b` |

### Envato API

Click **Envato API** in the toolbar and paste your personal token from [build.envato.com](https://build.envato.com/create-token/). Only needs the `View your Envato Account username` and `View your items' sales history` permissions.

### Custom Categories

Click **Edit Categories** to add your own categories. These are saved to `custom_categories.json` alongside the script and persist across sessions.

### Confidence Threshold

Use the **Min Confidence** slider to auto-deselect low-confidence matches. Folders below the threshold remain visible but unchecked, so you can review them manually.

## Usage

### Mode 1: Categorize Folders

1. Set **Operation** to `Categorize Folders into Groups`
2. Set **Source** to the folder containing your messy asset folders
3. Set **Output** to where you want the organized category tree
4. Check **Use LLM** (enabled by default) for AI-powered classification
5. Click **Scan** — each folder gets classified, renamed, and previewed in the table
6. Review results. Right-click any row to **Change Category** manually
7. Click **Preview** to see the destination tree before committing
8. Click **Apply** to move all selected folders

### Mode 2: AEP Batch Rename

1. Set **Operation** to `Rename Folders by Largest .aep File`
2. Set **Source** to the folder containing After Effects project folders
3. Click **Scan** — finds the largest `.aep` in each folder and proposes a rename
4. Click **Apply** to rename

### Table Color Coding

| Color | Meaning |
|-------|---------|
| Green text | Category assignment |
| Pink text (Detected As) | LLM renamed the folder |
| Purple text (Detected As) | Context engine overrode a topic → asset type |
| Blue text (Detected As) | Marketplace prefix was stripped |
| Method column colors | `llm` pink, `context` purple, `keyword` green, `fuzzy` yellow, `extension` violet, `metadata` blue, `envato_api` pink, `composition` lime |

### Right-Click Menu

Right-click any row for:
- **Open Folder in Explorer** — opens the source folder
- **Change Category** — manually reassign to any of 384+ categories

## Diagnostic Script

`FileOrganizerDiag.py` is a standalone CLI tool that runs the same classification engine and produces a text report. Useful for testing on a folder before running the GUI.

```bash
python FileOrganizerDiag.py /path/to/your/assets
```

Outputs a report with match counts, confidence distribution, method breakdown, category histogram, and a list of unmatched folders.

## Category Coverage

384 built-in categories across these domains:

| Domain | Examples |
|--------|----------|
| After Effects | Templates, Slideshows, Titles, Transitions, Intros, Lower Thirds, Infographics |
| Premiere Pro | Templates, Transitions, Title Templates, LUTs & Color, Sound Effects |
| Photoshop | Templates, Mockups, Brushes, Actions, Overlays, Text Effects, Layer Styles |
| Illustrator | Vectors, Patterns, Icons, Logo Templates |
| Print Design | Flyers, Posters, Brochures, Business Cards, Menus, Resumes, Certificates, Invitations, Letterhead, Postcards, Rollup Banners, Billboards, Calendars, Vouchers, Packaging, Book Covers |
| Social Media | Instagram, Facebook, YouTube, Thumbnails, Web Banners, LinkedIn |
| Web & UI | WordPress, HTML Templates, UI Kits, Wireframes, Dashboards |
| 3D & Motion | Cinema 4D, Blender, 3D Models, VJ Loops |
| Audio | Music, Sound Effects, Podcast |
| Fonts | Typography, Display, Script, Sans-Serif |
| Photography | Presets, Actions, Lightroom, Stock Images |
| Topics (190+) | Wedding, Christmas, Halloween, Sports, Food, Real Estate, Medical, Gaming, and many more |

## Prerequisites

- **Python 3.8+** (3.10+ recommended)
- **8 GB RAM** minimum (for Ollama LLM models)
- **~5 GB disk space** for the default `qwen2.5:7b` model
- **Internet connection** for first launch only (Ollama install + model download)
- Works without Ollama — falls back to rule-based engine automatically

Auto-installed Python dependencies:
- `PyQt6` — GUI framework
- `rapidfuzz` — fuzzy string matching (optional, improves accuracy)
- `psd-tools` — PSD metadata extraction (optional)

## Safety Features

- **Preview before apply** — full destination tree preview before any files move
- **Safe merge-move** — merging into existing folders preserves all unique files in both source and destination
- **Hash deduplication** — optional MD5 check skips identical files instead of overwriting
- **Full undo log** — every move operation is recorded. Click **Undo Last** to roll back
- **CSV audit trail** — every classification decision logged with timestamp, method, confidence, and detail
- **Non-destructive** — the tool moves folders, it never deletes content

## What It Does NOT Do

- Does not modify files inside folders (only moves/renames the folder itself)
- Does not send data to the cloud (Ollama runs 100% locally)
- Does not require an internet connection after initial setup
- Does not auto-apply — always requires user confirmation before moving files
- Does not overwrite without warning — safe merge handles conflicts

## FAQ / Troubleshooting

**Ollama won't install automatically on my system**

Run the install manually:
- Windows: Download from [ollama.com/download](https://ollama.com/download)
- Linux/macOS: `curl -fsSL https://ollama.com/install.sh | sh`

Then restart FileOrganizer.

**LLM status shows "unavailable" but Ollama is installed**

The server may not be running. Start it manually: `ollama serve`, then restart FileOrganizer.

**Classification is slow with LLM enabled**

Each folder takes 2-5 seconds depending on your hardware. For 1,000+ folders, consider using rule-based mode first (uncheck **Use LLM**), then re-scan problem folders with LLM. A GPU dramatically improves speed — an RTX 3060 processes folders in under 1 second each.

**Model download is stuck**

The default `qwen2.5:7b` model is ~4.7 GB. On slow connections, pull it manually: `ollama pull qwen2.5:7b`. Progress will show in your terminal.

**I want to use a different model**

Click **Ollama LLM** → change the model name → **Save**. Any model from the [Ollama library](https://ollama.com/library) works. Smaller models like `llama3.2:3b` are faster but less accurate.

**Folders are categorized but not renamed**

Rename-on-move only happens in LLM mode. The LLM produces a clean project name which becomes the folder name at the destination. Rule-based mode preserves original folder names.

**How do I add my own categories?**

Click **Edit Categories** in the toolbar. Add categories with comma-separated keywords. They're saved to `custom_categories.json` and available immediately.

**Can I run this headless / from CLI?**

Use `FileOrganizerDiag.py` for CLI-based classification reports. Full headless move operations are not yet supported.

## Contributing

Issues and PRs welcome. The classification engine lives entirely in `FileOrganizer.py` — all 384 categories, keyword mappings, and the LLM prompt are in a single file for easy modification.

To add a new category, find the `CATEGORIES` list and add a tuple: `("Category Name", {"keyword1", "keyword2"})`.

## License

MIT License — see [LICENSE](LICENSE) for details.
