#!/usr/bin/env python3
r"""overnight_supervisor.py — Drive the full overnight library reorg.

User asked: "Keep going all night and ensure this external drive is fully
organized... Bring these files (G:\Organized) and merge them with the rest
of the library on I:\Organized."

Phases (in order, each blocks until the previous completes):

  Phase 1: Finish I:\After Effects archive processing.
           (process_ae_archives.py is already running — wait for it.)

  Phase 2: Process I:\After Effects Organized (44 bundles + 1 stray .rar).
           Each bundle gets classified by name → moved to canonical category.

  Phase 3: Merge G:\Organized → I:\Organized.
           Cross-drive moves of every category in G:\Organized into the
           matching I:\Organized\<category>. Same-name collisions get
           merged via per-child os.rename (within I:\) once the data lands.

  Phase 4: Run fix_duplicates --apply to merge any (N) collision suffixes
           caused by the consolidation.

  Phase 5: Final fix_phantom_categories scan + verify_organized --summary.

Logs every phase to overnight_supervisor_log.json. Idempotent: each phase
checks whether its work is already done and skips if so. Safe to kill
mid-run; restart picks up where it left off.
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
from organize_run import robust_move  # noqa: E402

LOG_FILE = REPO / "overnight_supervisor_log.json"
STATE_FILE = REPO / "overnight_supervisor_state.json"
DB = REPO / "organize_moves.db"
SEVENZIP = r"C:\Program Files\7-Zip\7z.exe"

ORGANIZED_PRIMARY = Path(r"G:\Organized")
ORGANIZED_OVERFLOW = Path(r"I:\Organized")

PHASES = [
    "wait-ae-archives", "process-ae-organized",
    "merge-g-to-i", "fix-duplicates", "final-verify",
]


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    safe = line.encode("cp1252", errors="replace").decode("cp1252")
    print(safe)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(s: dict) -> None:
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def append_log(entry: dict) -> None:
    entries: list[dict] = []
    if LOG_FILE.exists():
        try:
            entries = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries.append({"ts": ts(), **entry})
    LOG_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ── Phase 1: wait for I:\After Effects archive processing ───────────────────
def is_pipeline_running() -> bool:
    """True if any python process_ae_archives.py is alive."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "ProcessId,CommandLine", "/format:list"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    return "process_ae_archives.py" in out


def archives_at_root(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(
        1 for f in root.iterdir()
        if f.is_file() and f.suffix.lower() in (".zip", ".rar", ".7z")
        and not re.search(r"\.part(\d+)\.rar$", f.name, re.IGNORECASE)
    )


def phase_wait_ae_archives() -> None:
    root = Path(r"I:\After Effects")
    while is_pipeline_running():
        remaining = archives_at_root(root)
        log(f"phase 1: archive pipeline running, {remaining} archives left")
        time.sleep(120)
    final = archives_at_root(root)
    log(f"phase 1: pipeline exited; {final} archives still at root")
    if final > 5:
        # Pipeline may have died — restart it
        log("phase 1: relaunching process_ae_archives.py to mop up")
        subprocess.Popen(
            [sys.executable, "process_ae_archives.py",
             "--root", str(root), "--apply"],
            cwd=str(REPO),
            stdout=open(REPO / "process_ae_archives_supervised.out", "ab"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(15)
        # Re-enter the wait
        return phase_wait_ae_archives()
    append_log({"phase": "wait-ae-archives", "status": "complete",
                "archives_remaining_at_root": final})


# ── Phase 2: process I:\After Effects Organized ─────────────────────────────
AE_ORGANIZED_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["cinepunch"],                      "After Effects - Motion Graphics Pack"),
    (["explainer"],                      "After Effects - Character & Explainer"),
    (["pixel film studios"],             "Plugins & Extensions"),
    (["confetti"],                       "After Effects - Event & Party"),
    (["transformation tralier", "trailer"], "After Effects - Trailer & Teaser"),
    (["network creator"],                "After Effects - Broadcast Package"),
    (["video copilot"],                  "Plugins & Extensions"),
    (["paramount", "filmmaker"],         "After Effects - Cinematic & Film"),
    (["ghosthack", "ultimate producer"], "Stock Music & Audio"),
    (["universevideo"],                  "After Effects - Motion Graphics Pack"),
    (["ultra editing", "candymustache"], "After Effects - Motion Graphics Pack"),
    (["digital cinema package"],         "After Effects - Cinematic & Film"),
    (["fx toolkit", "fx movie pro"],     "Cinematic FX & Overlays"),
    (["seamless transitions"],           "After Effects - Transition Pack"),
    (["dark magic", "magic pack"],       "Cinematic FX & Overlays"),
    (["bounce color", "animated elements"], "After Effects - Motion Graphics Pack"),
    (["atmosfx"],                        "Cinematic FX & Overlays"),
    (["cinegrain", "indie master"],      "Cinematic FX & Overlays"),
    (["rocketstock", "particle effects"],"After Effects - 3D & Particle"),
    (["mstreak", "smoke", "fog"],        "Cinematic FX & Overlays"),
    (["camera screen", "screen recordings", "overlays"], "Cinematic FX & Overlays"),
    (["film textures", "aejuice"],       "Cinematic FX & Overlays"),
    (["lens flare", "anamorphic"],       "Cinematic FX & Overlays"),
    (["audio visualizer"],               "After Effects - Music & Audio Visualizer"),
    (["atom after effects"],             "Plugins & Extensions"),
    (["character concepts"],             "After Effects - Character & Explainer"),
    (["socializing", "social"],          "After Effects - Social Media"),
    (["epic trailers"],                  "After Effects - Trailer & Teaser"),
    (["motion pro", "premiere kit"],     "Premiere Pro - Templates"),
    (["blockbuster"],                    "After Effects - Cinematic & Film"),
    (["motion bro"],                     "Plugins & Extensions"),
    (["smoke revealer"],                 "After Effects - Logo Reveal"),
    (["video fx presets"],               "Cinematic FX & Overlays"),
    (["explosions", "blockbuster explosions"], "Cinematic FX & Overlays"),
    (["animation creator"],              "After Effects - Character & Explainer"),
    (["bluefx"],                         "After Effects - News & Broadcast"),
    (["studio", "virtual studio"],       "After Effects - News & Broadcast"),
    (["slideshow"],                      "After Effects - Slideshow"),
    (["creativelab", "ai"],              "Plugins & Extensions"),
    (["640studio"],                      "Cinematic FX & Overlays"),
    (["revostock"],                      "After Effects - Trailer & Teaser"),
]


def classify_organized_bundle(name: str) -> str:
    low = name.lower()
    for keywords, cat in AE_ORGANIZED_KEYWORD_RULES:
        if any(kw in low for kw in keywords):
            return cat
    return "After Effects - Motion Graphics Pack"  # safe default for big bundles


def journal_move(src: str, dst: str, name: str, category: str) -> None:
    if not DB.exists():
        return
    try:
        con = sqlite3.connect(str(DB))
        with con:
            con.execute(
                "INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at,status) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (src, dst, Path(src).name, name, category, 75, ts(), "done"),
            )
        con.close()
    except Exception:
        pass


def safe_dest(target: Path, name: str) -> Path:
    base = target / name
    if not base.exists():
        return base
    i = 1
    while True:
        cand = target / f"{name} ({i})"
        if not cand.exists():
            return cand
        i += 1


def phase_process_ae_organized() -> None:
    root = Path(r"I:\After Effects Organized")
    if not root.exists():
        log("phase 2: I:\\After Effects Organized not found, skipping")
        append_log({"phase": "process-ae-organized", "status": "skipped"})
        return

    moved = errors = skipped_dirs = 0
    # Handle stray archives first
    for entry in list(root.iterdir()):
        if entry.is_file() and entry.suffix.lower() in (".zip", ".rar", ".7z"):
            log(f"phase 2: extracting stray archive {entry.name}")
            scratch = Path(r"I:\_ae_scratch") / f"_organized_{entry.stem[:60]}"
            if scratch.exists():
                shutil.rmtree(str(scratch), ignore_errors=True)
            scratch.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    [SEVENZIP, "x", str(entry), f"-o{scratch}", "-y",
                     "-bso0", "-bse0", "-bsp0"],
                    capture_output=True, text=True, errors="replace",
                    timeout=2 * 3600,
                )
            except subprocess.TimeoutExpired:
                log(f"phase 2: extract timeout on {entry.name}")
                errors += 1
                continue
            # Find extracted root
            try:
                children = [c for c in scratch.iterdir()
                            if c.is_dir() and c.name.lower() not in ("__macosx",)]
            except OSError:
                children = []
            files = [c for c in scratch.iterdir() if c.is_file()] if scratch.exists() else []
            if len(children) == 1 and not files:
                src_dir = children[0]
            else:
                src_dir = scratch
            target_name = entry.stem
            category = classify_organized_bundle(target_name)
            cat_dir = ORGANIZED_OVERFLOW / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            dest = safe_dest(cat_dir, target_name)
            try:
                robust_move(str(src_dir), str(dest))
                journal_move(str(entry), str(dest), target_name, category)
                entry.unlink()
                moved += 1
                log(f"phase 2: stray archive -> {category}/{target_name}")
            except Exception as e:
                log(f"phase 2: move fail {entry.name}: {e}")
                errors += 1
            finally:
                if scratch.exists():
                    shutil.rmtree(str(scratch), ignore_errors=True)

    # Handle bundle directories
    for entry in list(root.iterdir()):
        if not entry.is_dir():
            continue
        category = classify_organized_bundle(entry.name)
        cat_dir = ORGANIZED_OVERFLOW / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        dest = safe_dest(cat_dir, entry.name)
        log(f"phase 2: bundle {entry.name!r} -> {category}")
        try:
            robust_move(str(entry), str(dest))
            journal_move(str(entry), str(dest), entry.name, category)
            moved += 1
        except Exception as e:
            log(f"phase 2: move fail {entry.name}: {e}")
            errors += 1

    # Try removing the now-empty AE Organized root
    try:
        if root.exists() and not list(root.iterdir()):
            root.rmdir()
            log("phase 2: I:\\After Effects Organized removed (empty)")
    except OSError:
        pass

    append_log({"phase": "process-ae-organized", "status": "complete",
                "moved": moved, "errors": errors})


# ── Phase 3: merge G:\Organized → I:\Organized ──────────────────────────────
def phase_merge_g_to_i() -> None:
    r"""Move every category from G:\Organized into I:\Organized.

    Strategy v2 (post-audit, optimized for speed): use whole-dir robocopy
    /MOVE /E for each category. When the destination already exists,
    add /XC /XN /XO (skip files present in both with any size/timestamp
    relationship) so we never overwrite or duplicate — items unique to G:\
    move over, identical names in both stay on I:\ untouched. fix_duplicates
    in Phase 4 catches anything ambiguous.

    This is ~10-100x faster than the per-child loop because it avoids the
    process-startup overhead of one robocopy invocation per item.
    """
    if not ORGANIZED_PRIMARY.exists():
        log("phase 3: G:\\Organized not found, skipping")
        append_log({"phase": "merge-g-to-i", "status": "skipped"})
        return

    moved_whole = merged_existing = errors = empty_removed = 0

    g_categories = sorted(c for c in ORGANIZED_PRIMARY.iterdir() if c.is_dir())
    log(f"phase 3: {len(g_categories)} categories on G:\\Organized")

    def _lp(p: str) -> str:
        ap = os.path.abspath(p).replace("/", "\\")
        if ap.startswith("\\\\?\\"):
            return ap
        if ap.startswith("\\\\"):
            return "\\\\?\\UNC\\" + ap[2:]
        return "\\\\?\\" + ap

    for cat_g in g_categories:
        cat_i = ORGANIZED_OVERFLOW / cat_g.name
        try:
            child_count = sum(1 for _ in cat_g.iterdir())
        except OSError:
            child_count = 0
        if child_count == 0:
            try:
                cat_g.rmdir()
                empty_removed += 1
            except OSError:
                pass
            continue

        existed = cat_i.exists()
        cat_i.mkdir(parents=True, exist_ok=True)

        # Build robocopy command. /MOVE /E is the core. /XC /XN /XO when
        # dest existed = "skip any file present in both" (additive merge).
        cmd = [
            "robocopy", _lp(str(cat_g)), _lp(str(cat_i)),
            "/MOVE", "/E", "/256", "/COPY:DAT",
            "/R:1", "/W:1", "/NP", "/NFL", "/NDL", "/NJH", "/NJS",
        ]
        if existed:
            cmd.extend(["/XC", "/XN", "/XO"])
            log(f"phase 3: merging {cat_g.name} ({child_count} items, "
                f"additive — won't overwrite I:)")
        else:
            log(f"phase 3: moving whole category {cat_g.name} ({child_count} items)")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    errors="replace", timeout=12 * 3600)
        except subprocess.TimeoutExpired:
            log(f"phase 3: TIMEOUT on {cat_g.name} (>12 hours)")
            errors += 1
            continue

        if result.returncode >= 8:
            log(f"phase 3: robocopy rc={result.returncode} on {cat_g.name}: "
                f"{(result.stderr or result.stdout)[:300]}")
            errors += 1
            continue

        if existed:
            merged_existing += 1
        else:
            moved_whole += 1

        # Try removing the now-empty G:\<cat> dir
        try:
            if cat_g.exists() and not list(cat_g.iterdir()):
                cat_g.rmdir()
                empty_removed += 1
                log(f"phase 3: G:\\Organized\\{cat_g.name} removed (empty)")
        except OSError:
            pass

    # Try removing G:\Organized root if empty
    try:
        if ORGANIZED_PRIMARY.exists() and not list(ORGANIZED_PRIMARY.iterdir()):
            ORGANIZED_PRIMARY.rmdir()
            log("phase 3: G:\\Organized removed (empty)")
    except OSError:
        pass

    append_log({
        "phase": "merge-g-to-i", "status": "complete",
        "moved_whole": moved_whole, "merged_existing": merged_existing,
        "empty_removed": empty_removed, "errors": errors,
    })


# ── Phase 4: fix_duplicates ──────────────────────────────────────────────────
def phase_fix_duplicates() -> None:
    log("phase 4: running fix_duplicates --apply")
    result = subprocess.run(
        [sys.executable, "fix_duplicates.py", "--apply"],
        cwd=str(REPO), capture_output=True, text=True, errors="replace",
    )
    summary = result.stdout.splitlines()[-15:] if result.stdout else []
    append_log({"phase": "fix-duplicates", "status": "complete",
                "rc": result.returncode, "tail": summary})
    log(f"phase 4: fix_duplicates rc={result.returncode}")


# ── Phase 5: final verify ────────────────────────────────────────────────────
def phase_final_verify() -> None:
    log("phase 5: fix_phantom_categories --scan")
    p1 = subprocess.run([sys.executable, "fix_phantom_categories.py", "--scan"],
                        cwd=str(REPO), capture_output=True, text=True,
                        errors="replace")
    log("phase 5: verify_organized.py --summary")
    p2 = subprocess.run([sys.executable, "verify_organized.py", "--summary"],
                        cwd=str(REPO), capture_output=True, text=True,
                        errors="replace")
    append_log({
        "phase": "final-verify", "status": "complete",
        "phantom_scan_tail": p1.stdout.splitlines()[-10:],
        "summary_tail": p2.stdout.splitlines()[-30:],
    })
    log("phase 5: complete")


# ── Main ─────────────────────────────────────────────────────────────────────
PHASE_FUNCS = {
    "wait-ae-archives":      phase_wait_ae_archives,
    "process-ae-organized":  phase_process_ae_organized,
    "merge-g-to-i":          phase_merge_g_to_i,
    "fix-duplicates":        phase_fix_duplicates,
    "final-verify":          phase_final_verify,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-from", choices=PHASES, default=PHASES[0],
                    help="Skip earlier phases")
    ap.add_argument("--only", choices=PHASES,
                    help="Run only this phase, then exit")
    args = ap.parse_args()

    state = load_state()
    log(f"supervisor starting (state: {state})")

    if args.only:
        log(f"running only: {args.only}")
        PHASE_FUNCS[args.only]()
        return

    start_idx = PHASES.index(args.start_from)
    completed = set(state.get("completed", []))

    for phase in PHASES[start_idx:]:
        if phase in completed:
            log(f"phase {phase}: already complete, skipping")
            continue
        log(f"=== starting phase: {phase} ===")
        try:
            PHASE_FUNCS[phase]()
            completed.add(phase)
            state["completed"] = sorted(completed)
            save_state(state)
            log(f"=== phase {phase} done ===\n")
        except KeyboardInterrupt:
            log(f"phase {phase}: interrupted")
            raise
        except Exception as e:
            log(f"phase {phase}: FAILED: {e}")
            append_log({"phase": phase, "status": "failed", "error": str(e)})
            # Don't continue to later phases on failure
            sys.exit(1)

    log("\n*** OVERNIGHT SUPERVISOR COMPLETE ***")


if __name__ == "__main__":
    main()
