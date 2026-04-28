#!/usr/bin/env python3
"""
build_source_index.py — Build index files for new classification sources.

Usage:
    python build_source_index.py --source design_org
    python build_source_index.py --source loose_files
"""
import os, sys, json, argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

DESIGN_ORG_ROOT  = r'G:\Design Organized'
LOOSE_FILES_ROOT = r'G:\Design Unorganized'

LOOSE_EXTS = frozenset([
    '.psd', '.psb', '.ai', '.eps', '.aep', '.prproj', '.mogrt',
    '.rar', '.zip', '.7z', '.otf', '.ttf', '.woff',
    '.lut', '.cube', '.atn', '.abr', '.pat', '.jsx', '.jsxbin',
    '.aex', '.c4d', '.blend',
])

# Top-level branches and their depth rules for G:\Design Organized
# depth=1 means immediate subdirs are asset dirs
# depth=2 means subdirs-of-subdirs are asset dirs (subcats sit at depth 1)
BRANCHES = {
    'After Effects Organized': {'depth': 1, 'legacy': 'After Effects Organized'},
    'Design Elements':         {'depth': 2, 'legacy': None},   # subcat name used
    'Flyers':                  {'depth': 1, 'legacy': 'Flyers'},
}


def build_design_org_index() -> list[dict]:
    root = Path(DESIGN_ORG_ROOT)
    if not root.exists():
        print(f"ERROR: {DESIGN_ORG_ROOT!r} not found.")
        sys.exit(1)

    items = []
    for branch_name, cfg in BRANCHES.items():
        branch_dir = root / branch_name
        if not branch_dir.is_dir():
            print(f"  WARNING: branch not found: {branch_dir}")
            continue

        depth = cfg['depth']
        static_legacy = cfg['legacy']

        if depth == 1:
            for asset_dir in sorted(branch_dir.iterdir()):
                if not asset_dir.is_dir():
                    continue
                items.append({
                    'name':            asset_dir.name,
                    'path':            str(asset_dir),
                    'legacy_category': static_legacy,
                })
        elif depth == 2:
            for subcat_dir in sorted(branch_dir.iterdir()):
                if not subcat_dir.is_dir():
                    continue
                legacy_cat = subcat_dir.name
                for asset_dir in sorted(subcat_dir.iterdir()):
                    if not asset_dir.is_dir():
                        continue
                    items.append({
                        'name':            asset_dir.name,
                        'path':            str(asset_dir),
                        'legacy_category': legacy_cat,
                    })

    return items


def build_loose_files_index() -> list[dict]:
    root = Path(LOOSE_FILES_ROOT)
    if not root.exists():
        print(f"ERROR: {LOOSE_FILES_ROOT!r} not found.")
        sys.exit(1)

    items = []
    for entry in sorted(root.iterdir()):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext not in LOOSE_EXTS:
            continue
        items.append({
            'name':     entry.stem,
            'path':     str(entry),
            'file_ext': ext,
            'is_file':  True,
        })
    return items


def main():
    ap = argparse.ArgumentParser(description='Build index files for classification sources')
    ap.add_argument('--source', required=True, choices=['design_org', 'loose_files'],
                    help='Which source to index')
    args = ap.parse_args()

    if args.source == 'design_org':
        print(f"Walking {DESIGN_ORG_ROOT} ...")
        items = build_design_org_index()
        out_path = SCRIPT_DIR / 'design_org_index.json'
        out_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"design_org_index.json: {len(items)} items saved to {out_path}")

    elif args.source == 'loose_files':
        print(f"Scanning {LOOSE_FILES_ROOT} root files ...")
        items = build_loose_files_index()
        out_path = SCRIPT_DIR / 'loose_files_index.json'
        out_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"loose_files_index.json: {len(items)} items saved to {out_path}")


if __name__ == '__main__':
    main()
