#!/usr/bin/env python3
r"""find_misclassified_tutorials.py — Identify AE tutorial videos that
were mis-classified as stock footage.

Tutorial videos that ship with template bundles often look like stock
footage by extension (.mp4/.mov/.mkv) but should live with their template,
not in a Stock Footage category. This scanner flags any video file in a
Stock Footage / Stock Photos / Stock Music dir that:

  - has a tutorial-signal token in its name (tutorial, how-to, demo,
    walkthrough, preview, guide, overview, lesson, instruction), OR
  - sits next to .aep / .mogrt / .aet / .ffx / .aex sibling files
    (strongest signal — it's literally inside an AE template folder).

Run --scan to see the suspect list. Run --report to write a JSON report
that you can hand-review and feed into a per-item move script.

Usage:
    python find_misclassified_tutorials.py --scan
    python find_misclassified_tutorials.py --scan --root G:|I:|all
    python find_misclassified_tutorials.py --report
"""
import argparse
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).parent
REPORT = REPO / "tutorial_video_suspects.json"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv"}
AE_EXTS = {".aep", ".aet", ".ffx", ".mogrt", ".aex"}

SIGNAL_WORDS = {
    "tutorial", "tutorials", "tut",
    "how-to", "how to", "howto",
    "guide", "walkthrough",
    "demo", "preview",
    "help-file", "help file",
    "overview", "introduction",
    "instruction", "instructions",
    "lesson",
    "readme", "read-me", "read me",
}

# Token-boundary regex per word (cached once)
_TOKEN_RE = {
    w: re.compile(rf"(^|[\s_\-\.\(\[]){re.escape(w)}([\s_\-\.\)\]]|$)", re.IGNORECASE)
    for w in SIGNAL_WORDS if " " not in w and "-" not in w
}
_SUBSTR_WORDS = [w for w in SIGNAL_WORDS if " " in w or "-" in w]


STOCK_CATEGORIES = [
    "Stock Footage - General",
    "Stock Footage - Abstract & VFX",
    "Stock Footage - Aerial & Drone",
    "Stock Footage - Green Screen",
    "Stock Footage - Nature & Landscape",
    "Stock Footage - People & Lifestyle",
    "Stock Footage - Timelapse",
    "Stock Photos - General",
    "Stock Photos - Food & Drink",
    "Stock Photos - Nature & Outdoors",
    "Stock Music & Audio",
    "Sound Effects & SFX",
]


def has_signal(name: str) -> str | None:
    low = name.lower()
    for w in _SUBSTR_WORDS:
        if w in low:
            return w
    for w, rx in _TOKEN_RE.items():
        if rx.search(low):
            return w
    return None


def scan(roots: list[Path], skip: set[str]) -> tuple[int, list[dict]]:
    suspects: list[dict] = []
    total = 0
    for root in roots:
        for cat in STOCK_CATEGORIES:
            cat_dir = root / cat
            if not cat_dir.exists() or str(cat_dir) in skip:
                continue
            for dirpath, dirnames, filenames in os.walk(str(cat_dir)):
                ae_siblings = [
                    f for f in filenames
                    if os.path.splitext(f)[1].lower() in AE_EXTS
                ]
                for f in filenames:
                    if os.path.splitext(f)[1].lower() not in VIDEO_EXTS:
                        continue
                    total += 1
                    full = os.path.join(dirpath, f)
                    sig = has_signal(f)
                    if not sig and not ae_siblings:
                        continue
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = -1
                    rel = os.path.relpath(full, str(root))
                    suspects.append({
                        "path": full,
                        "rel": rel,
                        "category": rel.split(os.sep, 1)[0],
                        "signal": sig or "ae-sibling",
                        "size_mb": round(size / 1024 / 1024, 2) if size >= 0 else -1,
                        "ae_siblings": ae_siblings,
                        "parent_dir": os.path.basename(dirpath),
                    })
    return total, suspects


def fmt_suspects(suspects: list[dict], limit: int = 60) -> None:
    print(f"\nSuspect tutorial videos: {len(suspects)}\n")
    for s in suspects[:limit]:
        sig = s["signal"]
        sz = s["size_mb"]
        cat = s["category"]
        parent = s["parent_dir"]
        name = os.path.basename(s["path"])
        ae_str = f" + {len(s['ae_siblings'])} AE file(s)" if s["ae_siblings"] else ""
        print(f"  [{sig:<11}] {sz:>7} MB  {cat}/.../{parent}/{name}{ae_str}")
    if len(suspects) > limit:
        print(f"\n  ... +{len(suspects) - limit} more")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="Write tutorial_video_suspects.json")
    ap.add_argument("--root", choices=["G:", "I:", "all"], default="all")
    ap.add_argument("--skip-migrating", action="store_true",
                    help="Skip Stock Footage - Abstract & VFX on I:\\")
    args = ap.parse_args()

    roots: list[Path] = []
    if args.root in ("G:", "all"):
        roots.append(Path(r"G:\Organized"))
    if args.root in ("I:", "all"):
        roots.append(Path(r"I:\Organized"))

    skip: set[str] = set()
    if args.skip_migrating:
        skip.add(r"I:\Organized\Stock Footage - Abstract & VFX")

    total, suspects = scan(roots, skip)

    if args.scan:
        print(f"Total video files scanned in stock dirs: {total}")
        fmt_suspects(suspects)

    if args.report:
        REPORT.write_text(
            json.dumps(suspects, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nReport written: {REPORT.name}  ({len(suspects)} suspects)")


if __name__ == "__main__":
    main()
