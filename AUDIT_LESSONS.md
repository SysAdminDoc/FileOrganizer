# FileOrganizer — Audit Lessons (2026-04-28)

A record of every architectural failure mode and design decision uncovered
during the v8.2.0 audit + cleanup session. Intended as a checklist of
"things the future Python app must get right from day one."

---

## 1. Phantom-category problem: any classifier output that isn't in the canonical taxonomy creates a real folder on disk

The library taxonomy is a closed set (~85 categories in `classify_design.CATEGORIES`).
Every script that **writes** a category folder must validate against that set.

### What we saw

- `fix_stock_ae_items.py` had a keyword rule that produced
  `After Effects - Promo & Advertising` — not in the taxonomy.
- `merge_stock.py` had a fallback `f"After Effects - {sub.name}"` — invented
  a fresh category name from any subdirectory it didn't recognise.
- `review_resolver.py`'s SYSTEM_PROMPT had ~11 ground-truth rules pointing
  at non-existent categories (`Photoshop - Print & Stationery`,
  `After Effects - Backgrounds`, etc.). DeepSeek faithfully reproduced them.

### Implementation rules for the future app

1. **Single source of truth**: one `CATEGORIES` constant, one `set(CATEGORIES)`
   used as a runtime guard.
2. **Validate at write time**: every code path that creates `dest_root /
   category` must call `assert category in _CATEGORY_SET` (or route to
   `_Review` if the model returned junk).
3. **Phantom→canonical alias map**: a public, expandable dict keyed by
   observed-typo category names → canonical. Apply it before validation.
4. **System prompts must enumerate the canonical list**: never write
   "use category X" in a prompt unless X is in the live taxonomy.
5. **Reject unknown categories from any AI provider** instead of writing
   them through. Audit log every rejection.

---

## 2. `robocopy /MOVE` is not a metadata-only rename, even on the same drive

Robocopy's `/MOVE` flag is "copy then delete" — it always reads + writes
file bytes, even when source and destination are on the same volume. This
turned a 97 GB folder migration that should have been milliseconds into
14+ minutes per item, and a 15,633-item I:\Organized phantom-category
migration into an estimated 8+ hours.

### Implementation rules for the future app

1. **Always check `os.path.splitdrive(src) == os.path.splitdrive(dst)` first.**
2. **Same drive → `os.rename`** (instant; the underlying NTFS operation is
   metadata-only).
3. **Cross drive → robocopy with `/256 /COPY:DAT`** (long-path support;
   no Manage Auditing right needed).
4. **Per-child merge for collisions**: when the destination directory
   already exists, walk the source tree bottom-up and rename each entry
   individually rather than calling whole-folder robocopy.
5. **Never use `/COPYALL`** — it requires the SeManageAudit privilege.

In this audit, switching from whole-folder robocopy to per-child
`os.rename` reduced a 250-folder / 15,633-item migration from ~8 hours to
24 seconds — a 1,000x speedup.

---

## 3. Long-running cleanup scripts must write their audit log incrementally

`fix_duplicates.py` originally accumulated `results` in memory and called
`LOG_FILE.write_text` only at the end of `cmd_apply`. When the prior
session was killed mid-run, all the merges it had completed were on disk
but invisible to the next run's audit trail. We had to rebuild the
collision list from scratch (a 7-minute filesystem walk).

### Implementation rules for the future app

1. **Flush the log every N items (50 is fine).**
2. **SQLite journal** (the existing `organize_moves.db` pattern) is even
   better: each move is a separate row, durable on commit.
3. **Idempotent re-runs**: any script that walks the disk and acts on
   `Name (N)` collisions or phantom dirs should be safe to interrupt and
   re-run; rebuilding the work list every invocation costs nothing
   compared to a corrupted/partial state.

---

## 4. `robocopy /MOVE` does not delete the source directory after emptying it

Robocopy `/MOVE` removes files individually after each successful copy and
empties the source tree, but it does not `rmdir` the source root. A naive
`shutil.rmtree(src)` in a `try` block is fine and Pythonic, but be ready
for `WinError 3` (path already gone) and treat it as success.

---

## 5. `shutil.move` on cross-drive paths leaves partial copies on failure

`shutil.move` cross-drive is `copytree → unlink_source`. If `copytree`
raises mid-walk, the source is intact (good) but the destination has a
partial copy (bad). The next run with `safe_dest_path` will create a
`(1)` suffix collision dir, so you end up with two partial copies if you
don't clean up first.

### Implementation rules

1. **Always log `partial_dest_exists` on the error record.**
2. **In `--retry-errors` flow**: if `partial_dest_exists`, `shutil.rmtree(dest)`
   before re-running the move.

---

## 6. Trailing-space file/folder names cause `WinError 2` on `shutil.move`

Windows strips trailing spaces in normal API calls but accepts them via
the extended-length prefix `\\?\`. Files created on macOS / ext4 / a
download that preserved them will round-trip fine until Python tries to
move them.

### Implementation rules

1. **Pre-sanitize**: walk the source tree bottom-up and `os.rename` any
   name where `name != name.rstrip()`.
2. **Use `\\?\` extended-length paths** in the rename call — the normal
   API normalises trailing spaces away before the syscall, so a naive
   `os.rename(old, new)` silently fails.
3. **Move via robocopy with `/256`** for long-path safety as a separate
   robustness layer.

---

## 7. Robocopy exit codes 0–7 are all success; only 8+ is failure

Robocopy uses a bitfield exit code: 1 = files copied, 2 = extras present,
4 = mismatched, etc. `subprocess.check_call` would raise on any non-zero
exit — wrong for robocopy. Always check `if result.returncode >= 8`.

---

## 8. Position-based batch-to-disk mapping beats name-based mapping

When DeepSeek returns classification batches, the AI may:
- Strip marketplace ID prefixes (`13357739_MotionElements_…` → `…`).
- Truncate long folder names to fit token budgets.
- Return only the "clean" display title.

Trying to match the AI's `name` field back to the disk via dict lookup
fails for ~30% of items. Instead, embed the actual `org_index[(N-1)*60 :
N*60]` slice into the prompt and rely on **positional alignment**: batch
result `i` corresponds to `org_index[offset + i]`, regardless of name.

### Implementation rule

The classifier and the apply step both use position-based offset; never
let either side rely on the AI-returned name as the disk key.

---

## 9. Phase ordering matters: classify before merge, merge before dedup, dedup before final cleanup

The pipeline shape that worked:

```
build_source_index → classify_design → organize_run --apply
                  → fix_phantom_categories (any phantom dirs from prior runs)
                  → fix_duplicates (now collisions are concentrated in canonical bins)
                  → fix_stock_ae_items (catch any AE that landed in stock)
                  → reclassify_unorg / review_resolver (refine _Review backlog)
                  → verify_organized
```

### Implementation rules

1. **Phantom cleanup must run before dedup**, otherwise dedup tries to
   merge into phantom names that the next pipeline step would have
   relocated anyway.
2. **fix_stock_ae_items must scan EVERY non-AE category**, not just five
   of them. The audit found 16 categories were missing from the original
   scan list.
3. **Each step is idempotent**: running it twice on a clean state must be
   a no-op.

---

## 10. Tutorial videos shipped with AE templates look like stock footage by extension

`.mp4` files inside an AE template folder (typically named
`tutorial.mp4`, `Help/Tutorial.mp4`, `*-tutorial.mp4`) get picked up by a
naive extension-based stock-footage classifier. The fix is two-layer:

1. **`has_ae_files()` walk**: if any `.aep / .aet / .ffx / .mogrt /
   .aex` exists anywhere in the folder tree, the parent is an AE
   template, not stock. Move the parent folder, not the video.
2. **Tutorial-signal token scan**: `tutorial`, `walkthrough`, `demo`,
   `how-to`, `preview`, `lesson`, `instruction`, `readme`. Any of these
   in a video filename inside a stock dir is suspicious.

`find_misclassified_tutorials.py` now performs this scan, and
`fix_stock_ae_items.py` got an expanded scan-dir list (every stock /
print / FX / colour category, not just five).

---

## 11. `_Review` is a holding pen, not a destination

Items with `confidence < 50` land in `_Review/<category>/<item>`. The
mistake the prior session made was treating `_Review` as the final answer
and never running a second pass. The right shape:

1. **`review_resolver.py`** runs after every classify pass and
   re-classifies any `_Review` item using extra hints (folder peek, zip
   peek, legacy_category).
2. **Hand-curation scripts** (`resolve_review_manual.py`,
   `resolve_unknown_vh.py`) handle the long tail. The author of the
   curator script signs off on each decision.
3. **Documentation/help-only folders should be deleted**, not organized.
   The audit deleted 4 such items (`Help File - Avelina Studio`, `Main
   Print`, `Read Me (GraphixTree)`, `readme`).

---

## 12. The classifier prompt needs **explicit anti-hallucination rules**

Items that are not design assets show up regularly and the prior prompt
had no rule for them:

- `.exe` installers, `setup.zip`, "Portable" / "Multilingual" apps →
  `Software & Utilities`.
- macOS artifacts (`.DS_Store`, `__MACOSX`, `fseventsd`) → ignore as junk.
- Chinese-language piracy sites (`aidownload.net`, `freegfx.com`,
  `graphicux.com`, `softarchive`) → strip from clean names; don't let
  them influence category.
- Empty folders, `.part2.rar` / `.part3.rar` fragments → `_Skip`.
- Documentation-only folders → delete, don't organize.

These rules are now in `classify_design.py` and `review_resolver.py`'s
SYSTEM_PROMPT.

---

## 13. Cross-drive moves must respect free-space on the destination

`fix_stock_ae_items.py` originally hard-coded `dest_root = G:\Organized`,
which filled G:\ to 0 GB free during the orchestrator step 6 pass. The
fix: route to the same drive as the source unless explicitly overridden.

```python
src_drive = os.path.splitdrive(str(src))[0].upper()
cat_root = ORGANIZED_OVERFLOW if src_drive == 'I:' else ORGANIZED
```

### Implementation rules

1. **Per-item destination decision**: every move chooses its dest root
   based on (a) source drive, (b) free-space check on the primary, (c)
   explicit `--overflow-now` override.
2. **Free-space monitor**: before each move, sample
   `shutil.disk_usage(dest_root).free`; if below `MIN_FREE_GB`, fail-fast
   with a clear error and switch to overflow.

---

## 14. The journal (`organize_moves.db`) is the system of record

Every move flows through `organize_run.py` → `journal_record(...)`.
This is the single source of truth for:

- **Undo**: `--undo-last N` and `--undo-all` reverse moves in reverse order.
- **Audit**: `--report <plan_id>` regenerates a Markdown report.
- **Verify**: `--missing` cross-checks DB vs disk; `--orphans` cross-checks
  disk vs DB.

### Implementation rules

1. **Every script that moves a file must journal**: phantom migration,
   dedup, fix_stock_ae_items, manual hand-curators all insert rows.
2. **Journal schema is append-only**: never UPDATE the original move
   record when a follow-up corrects it; insert a new row pointing back at
   the previous one (or use a `correction_of` column).
3. **Schema migrations are forward-compatible**: new columns added via
   `ALTER TABLE … ADD COLUMN`, defaulting to NULL.

---

## 15. Provider abstraction: classification should be replaceable

The current pipeline mixes DeepSeek, GitHub Models, Ollama, and direct
hand-curation. The future app should expose a single `Classifier` ABC:

```python
class Classifier(Protocol):
    def classify_batch(self, items: list[Item]) -> list[Result]: ...
    def confidence_floor(self) -> int: ...
    def supports_legacy_hint(self) -> bool: ...
```

Concrete implementations: `DeepSeekClassifier`, `AnthropicClassifier`,
`OllamaClassifier`, `KeywordRuleClassifier`, `ManualCuratorClassifier`.
A `ChainClassifier` runs them in priority order: keyword rule first
(zero cost, high confidence), then AI for residue, then human review.

In the audit, switching from "DeepSeek for everything" to "keyword first
+ manual curation for residue" produced 367 correct classifications with
zero AI calls.

---

## Appendix — files touched in this audit

Source-code fixes:
- `fix_stock_ae_items.py` — phantom keyword removed; expanded scan-dir
  list (5 → 21 categories); `--no-ai` mode; same-drive routing.
- `merge_stock.py` — strict `AE_ORGANIZED_REMAP` allowlist + fallback.
- `review_resolver.py` — 11 phantom rules rewritten; `canonicalize()`
  validator added.
- `organize_run.py` — `CATEGORY_ALIASES` expanded by ~250 entries;
  `_web_template_collapse()` helper.
- `fix_duplicates.py` — same-drive `os.rename` merge path; incremental
  log save.

New scripts:
- `fix_phantom_categories.py` — non-canonical category migration.
- `fix_flagged_misclassifications.py` — 4 known mis-routings.
- `resolve_review_manual.py` — _Review hand-curation (8 items).
- `resolve_unknown_vh.py` — detached AE-subfolder identification (5 items).
- `find_misclassified_tutorials.py` — tutorial-video detector for stock dirs.
- `manual_ae_classifications.py` — 106-item curated category map.

Disk operations executed:
- 13 G:\ phantom dirs cleared (57 items).
- 253 I:\ phantom dirs cleared (15,633 items).
- 3,796 collision dirs deduplicated.
- 4 flagged misclassifications corrected.
- 13 _Review backlog items resolved (4 deleted as junk).
- 5 unknown-VH detached subfolders identified and re-categorized.
- 367 misplaced AE templates queued for relocation.
- ~620 GB Stock Footage Abstract & VFX migration G:\ → I:\ (in flight).
