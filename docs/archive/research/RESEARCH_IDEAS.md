# FileOrganizer — Research & Improvement Ideas

> Research-driven proposals for the next phase of the FileOrganizer effort.
> Sources: my training knowledge of similar projects, industry standards,
> and reflections on the v8.2.0 audit findings. No DeepSeek round-trip.

---

## 1. Deeper metadata extraction (the single highest-leverage improvement)

The pipeline currently classifies by **folder name** + **shallow extension peek**.
Every design-asset format has rich machine-readable metadata that's never read.

### After Effects projects (`.aep`)
- **Format**: Adobe AE project files are a binary format wrapping an XML/RIFF
  structure. Tools to parse:
  - [`pyaep`](https://github.com/yaowei/pyaep) (Python, reads composition tree)
  - [`aep-parser`](https://github.com/Goyofi/aep-parser) (Node, more mature)
  - The Envato CLI `videohive-parser` extracts VH item ID directly from
    project metadata embedded by the marketplace template.
- **What we'd get**: composition names, marker comments (often the human
  title), expression strings (reveal which AE plugins are required), source
  footage paths, project comments.
- **Win**: an AE folder named `VH-3536887` becomes "Liquid Logo Reveal"
  because the master composition is named "Liquid Logo Reveal Comp 1".

### Photoshop documents (`.psd`/`.psb`)
- **psd-tools** (Python) reads layer hierarchy + layer names + smart-object
  references + XMP metadata.
- **Why it matters**: a folder named `mockup-pack-2` with PSDs containing
  layers like `Logo`, `Place Your Design Here`, `Background` is *unmistakably*
  a mockup. Layer-name keyword extraction is a strong classifier signal that
  bypasses the AI entirely.

### Illustrator (`.ai`)
- New `.ai` files are PDF-compatible — `pypdf` or `pdfplumber` can read text
  layers, which often contain template comments.

### Premiere `.prproj`
- XML format; `lxml` parsing gets composition + bin names.

### Fonts (`.otf`/`.ttf`/`.woff`)
- **fonttools** reads the name table: family name, designer, foundry,
  copyright. Routing fonts to `Fonts & Typography` becomes 100% confident.

### LUTs (`.cube`/`.3dl`/`.look`)
- Plain text headers; first 5 lines often include `TITLE`, `DESCRIPTION`.

### Audio
- **mutagen** (Python) reads ID3/Vorbis/MP4 tags — title, artist, album,
  duration. Critical for separating tutorial-narration audio from stock music.

### Video
- **ffprobe** JSON output reveals: duration, resolution, codec, bitrate,
  audio language. Tutorial videos are typically 720p–1080p, <10 min,
  English/voiceover audio. Stock footage is typically ProRes/DNxHR,
  short (5–30s), no audio. This is a structural fingerprint.

### Images
- **Pillow** + **piexif** reads EXIF (camera, lens, timestamps), XMP
  (Adobe keywords), IPTC. Photos vs design renders separable by EXIF
  presence alone.

### Archive contents (`.zip`/`.rar`/`.7z`)
- Already partly done in `peek_inside_zip`. Could extend:
  - Read `manifest.json` / `package.json` if present (Adobe extension)
  - Read first PDF text layer (`pypdf`) for asset titles
  - Read `Readme.txt` / `Description.txt` for product description

### Recommendation
Add a `metadata_extractors/` package with one file per format. Each returns a
`MetadataRecord(title, kind, plugins_required, layer_names, exif, …)`.
Pipeline order: **metadata first, name-fallback, AI last**.

---

## 2. Marketplace API integration for ground truth

The current `marketplace_enrich.py` already detects marketplace IDs by
filename prefix. Take it further by hitting the actual APIs.

### Envato API (free, covers ~70% of items observed)
- **Endpoint**: `https://api.envato.com/v3/market/catalog/item?id={ID}`
- **Auth**: free personal token (rate-limited 60/min, plenty for our use)
- **Returns**: title, description, category tree, tags, preview URLs,
  author. Direct mapping to our taxonomy possible via `categories`.
- Covers: **Videohive**, **GraphicRiver**, **AudioJungle**, **3DOcean**,
  **CodeCanyon**, **PhotoDune**, **ThemeForest**.

### CreativeMarket
- No public API, but product URL pattern `creativemarket.com/{seller}/{id}-{slug}`
  is scrapable. The og:title, og:description meta tags + structured-data
  JSON-LD on product pages give title + category + author.

### DesignBundles
- Same pattern: scrape product page; parse JSON-LD for title + category.

### MotionElements
- Has an XML API at `https://www.motionelements.com/feed/` — paginated
  product feed.

### Adobe Stock
- Paid API. Free tier limited to 50 lookups/day.

### Implementation pattern
```python
class MarketplaceLookup:
    cache = SQLiteCache('marketplace_cache.db')
    backoff = ExponentialBackoff(base=2, max_retries=5)

    def lookup(self, marketplace_id: MarketplaceId) -> Result | None:
        if (hit := self.cache.get(marketplace_id)):
            return hit
        result = self._fetch(marketplace_id)
        self.cache.put(marketplace_id, result, ttl_days=180)
        return result
```

### Win
For any item with a recognisable marketplace ID prefix, we get
**ground truth title + canonical category** in milliseconds, with no AI cost.

---

## 3. Content-addressed dedup (hash-based, beyond name collisions)

Current dedup is name-collision-based (`Name (1)`, `Name (2)`). Content-level
dedup is the next frontier.

### Strategies
- **Whole-file SHA-256** for files <100 MB. Reuses `asset_db.py` fingerprint DB.
- **Block-level rolling hash** (rsync-style) for large video/zip files —
  identifies templates that share 95%+ content.
- **Perceptual hashes**:
  - `imagehash` (pHash, dHash, wHash) for image dedup. Detects same photo
    in different formats / resolutions.
  - **VideoHash** (Python, FFmpeg-based) for video dedup. Catches tutorial
    duplicates encoded differently.
  - **AcoustID/Chromaprint** for audio. Stock music dedup.

### Best-in-class reference projects
- **Czkawka** (Rust) — fast multi-hash dedup with GUI.
- **fclones** (Rust) — distributed dedup, tested on 100M-file libraries.
- **rmlint** (C) — deduplicates with reflinks (Btrfs / XFS).
- **dupeguru** (Python/Qt) — fuzzy dedup including image perceptual.
- **AllDup** (Windows commercial) — all-in-one dedup with similarity scoring.

### Recommendation
1. Build whole-file hashes during `build_source_index.py` (one-time cost).
2. After organize, run a `content_dedup.py` that flags items where
   different *folder* names point at identical *content*.
3. Use perceptual hash for the long tail (mockup PSDs that differ only
   in saved compression settings).

---

## 4. Rule-based classifier (declarative YAML, not hard-coded Python)

The current `AE_KEYWORD_RULES` and `CATEGORY_ALIASES` are hard-coded
Python dicts that grew organically through the audit. The future app
should externalise them.

```yaml
# rules/ae_keywords.yaml
- match: "lower third|lower-third"
  category: "After Effects - Lower Thirds"
  confidence: 90

- match: "wedding|romance|love story|invitation"
  category: "After Effects - Wedding & Romance"
  confidence: 85
  exclude: "wedding cake recipe"   # avoid food false positive

- match_layers:
    contains_any: ["Place Your Design Here", "Smart Object", "Drop Image Here"]
  category: "Photoshop - Mockups"
  confidence: 95
  source: "psd_layers"
```

### Benefits
- Non-Python users can edit rules.
- Version-controlled rules track classification taxonomy evolution.
- Rules can be unit-tested against a corpus of known-good classifications.
- Reusable across projects.

### Reference: similar engines
- **organize-cli** (Python) by tfeldmann — declarative YAML actions.
- **Hazel** (macOS) — rules with conditions and actions.
- **Maid** (Ruby) — DSL for organize rules.

---

## 5. Web UI dashboard for review/curation

The current `_Review` queue is a directory the user spelunks manually.
A purpose-built dashboard would make hand-curation much faster.

### Stack
- **Flask** + **HTMX** + **Tailwind** — lightweight, no build step.
- **Pillow thumbnails** for images.
- **ffmpeg-static** for video thumbnails.
- **psd-tools.compose** for PSD previews.

### Features
- Review queue with thumbnail grid.
- Click → category dropdown (canonical taxonomy preloaded).
- Bulk-select + assign category.
- "Compare" view for collision pairs (file lists side-by-side).
- Undo button → reverses via `organize_run.py --undo-last`.

### Reference: similar UIs
- **Eagle App** — visual asset library, gold standard for UX.
- **Inboard / Pixave / Pure Ref** — moodboard-style asset organizers.
- **digiKam** — photo cataloguer with rich metadata UI.
- **Hydrus Network** — content-addressed image library with tagging.

---

## 6. Provenance tracking ("where did this come from?")

The library has clear piracy artifacts (`aidownload.net`, `freegfx.com`,
`graphicux.com`, `softarchive`, `cgpersia`, `motionarray.com`). The future
app should track provenance per item:

- Source domain extracted from folder name.
- Marketplace ID (if any).
- Hash signature.
- First-seen timestamp.

### Use cases
- Strip piracy domains from clean names automatically.
- Detect re-downloads of the same item from different sources.
- Generate a "what's missing from my library" report by comparing against
  marketplace inventory (e.g., Envato bundle SKUs).

---

## 7. Embeddings-based clustering (the AI win that doesn't cost per-call)

Instead of asking DeepSeek/Claude to classify each item one at a time,
embed every folder name + first 1KB of contents into a vector space:

- **Sentence-transformers** `all-MiniLM-L6-v2` runs locally, ~80M params,
  fast on CPU.
- Hand-label one item per category (the "anchor" item).
- For new items, compute cosine similarity to every anchor — pick max.
- **Cost**: zero (local model). **Speed**: ~1000 items/sec.
- **Accuracy**: usually 85-92% for well-defined categories like ours.

This is exactly the approach that **TVRenamer**, **Sonarr/Radarr**,
**MusicBrainz Picard**, and **Plex's matching engine** use under the hood:
candidate retrieval via embedding + reranking via metadata.

### Recommendation
Build an `embeddings_classifier.py` that:
1. On first run, computes embeddings for every canonical category name + a
   description sentence.
2. For each item, computes its embedding from `name + extension_set + first_zip_filename`.
3. Returns top-3 candidates with similarity scores; defer to AI only for
   ties (similarity < 0.3 margin).

---

## 8. Idempotency by design (every script is safe to re-run)

The audit revealed several scripts that fail badly when interrupted:

- `fix_duplicates.py` — log written only at end. Killed mid-run lost the audit trail.
- `fix_phantom_categories.py` — was fine because re-running rebuilds the
  collision list from disk (correct pattern).

### Implementation rules
- **No in-memory state**: every step that mutates the disk also commits
  the journal row.
- **Resumable**: each script can be killed and re-run; the journal tells
  it what's already done.
- **`--dry-run` is mandatory**: every move-class CLI gets one.

This is the same discipline as **Ansible playbooks** (idempotent by
default), **Terraform** (state file is the source of truth),
**dbt** (incremental models).

---

## 9. Confidence calibration

The current pipeline treats DeepSeek's `confidence: N` field as gospel.
The audit found DeepSeek confidence is overly optimistic — items rated
80% were often wrong, and some confidence-30 items were trivially correct.

### Calibration pattern
1. Hold out a labelled set of 200 items.
2. Run the classifier; record reported confidence vs actual correctness.
3. Build a calibration curve: model says 80% → real accuracy is 65%.
4. Apply a calibration function before threshold checks.

### Reference
- **Platt scaling** (logistic regression on the score-vs-correctness pairs).
- **Isotonic regression** (non-parametric, robust to small N).
- **scikit-learn** has both: `sklearn.calibration.CalibratedClassifierCV`.

---

## 10. Industry-standard tools we should learn from

- **Eagle App** — visual asset organizer; commercial; strongest UX for
  designers; has an API for bulk import.
- **Adobe Bridge** — XMP metadata-aware browser; the de-facto standard for
  designers; reads everything.
- **digiKam** — open-source photo organizer with face recognition,
  geotag, AI tagging plugin.
- **Hydrus Network** — content-addressed image library; tag namespace
  system worth studying.
- **MusicBrainz Picard** — fingerprint-based audio tagger; reference
  implementation of "lookup → match → rename" pipeline.
- **Sonarr/Radarr/Lidarr** — *arr ecosystem; rule-based downloaders +
  metadata-driven organizers; their parsing of release filenames is
  battle-tested.
- **organize-cli** (Python) — `pip install organize-tool`; declarative
  YAML rules.
- **rclone** — cross-cloud sync with checksums; the dedup/sync engine to
  emulate.
- **Czkawka / fclones / rmlint** — content dedup; benchmark before
  building our own.
- **PhotoStructure** — paid commercial photo organizer; its
  duplicate-detection is best-in-class.
- **Tropy** — research-focused asset organizer; tagging UX worth borrowing.

---

## 11. Concrete next-quarter roadmap

In priority order:

1. **`metadata_extractors/`** — psd-tools, fonttools, mutagen, ffprobe,
   piexif, pypdf. Extract first; classify second; AI third.
2. **Envato API integration** — batch lookup of all VH/CR/AJ IDs in our
   marketplace_cache.json. Estimated coverage: 39% of AE, 8% of design_org,
   0.7% of loose_files = ~1,500 items get ground truth for free.
3. **Embeddings classifier** — local sentence-transformers; replace
   DeepSeek for the bulk of high-confidence classifications.
4. **YAML rule engine** — externalise `AE_KEYWORD_RULES` +
   `CATEGORY_ALIASES` to versioned YAML.
5. **Web UI** — Flask + HTMX dashboard for `_Review` curation, collision
   inspection, undo browser.
6. **Content dedup** — whole-file SHA-256 + perceptual hash for media.
7. **Calibration** — labelled holdout set + Platt/isotonic adjustment.
8. **Provenance tracking** — domain + marketplace + hash columns in journal.

---

## 12. Stretch ideas (if time permits)

- **Federated library**: multi-machine library sync via rclone bisync.
- **Cloud cold storage**: move "rarely accessed" items to S3 Glacier
  Deep Archive ($1/TB/month), keep local stubs.
- **Differential backups**: ZFS snapshots of the organize_moves.db every
  hour; recovery from accidental rmtree is one rollback.
- **Automated import pipeline**: watch a "drop zone" folder; new items
  flow through classify → dedup → file automatically.
- **Author/foundry/series detection**: cluster items by their stylistic
  fingerprint to auto-build mini-bundles.
- **Exhibit mode**: thumbnail wall for the whole library (similar to
  Eagle's "All Files" grid view).

---

## Appendix — relevant standards & specifications

- **XMP** (Adobe Extensible Metadata Platform) — ISO 16684-1; embedded
  in JPEG, PSD, AI, MOV, MP4, PDF.
- **IPTC IIM** (legacy) and **IPTC Photo Metadata** (current) for images.
- **EXIF 2.32** for camera images.
- **ID3v2.4** for audio.
- **Matroska XML** for MKV chapters/tags.
- **DASH manifest** for streaming video bundles.
- **OpenType `name` table** for font metadata (RFC 3066 + spec).
- **JSON-LD** schema.org/Product, schema.org/CreativeWork — most
  marketplaces embed these in product pages, often the cleanest source
  for title + category.
