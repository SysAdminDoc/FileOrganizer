#!/usr/bin/env python3
"""fix_cats.py — Fix non-canonical category names in batch result files."""
import json, sys, glob
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

try:
    from classify_design import CATEGORIES
except ImportError:
    CATEGORIES = []

# Canonical mapping for known aliases
ALIASES = {
    'After Effects - Typography Opener':  'After Effects - Intro & Opener',
    'Photoshop - Print & Stationery':     'Print - Invitations & Events',
    'After Effects - Mockup & Device':    'Photoshop - Mockups',
    'After Effects - Typography':         'After Effects - Title & Typography',
    'After Effects - Openers':            'After Effects - Intro & Opener',
    'Stock Footage & Photos':             'Stock Footage - General',
    'Premiere Pro - Motion Graphics':     'Premiere Pro - Motion Graphics (.mogrt)',
    'Photoshop - Templates':              'Photoshop - Smart Objects & Templates',
    'After Effects - Film Grain & Overlays': 'Cinematic FX & Overlays',
    'After Effects - Overlays':           'Cinematic FX & Overlays',
    'Premiere Pro - Transition':          'Premiere Pro - Transitions & FX',
    'After Effects - Transitions':        'After Effects - Transition Pack',
}

cat_set = set(CATEGORIES)
fixed = 0

for f in sorted(glob.glob('classification_results/design_batch_*.json')):
    data = json.load(open(f, encoding='utf-8'))
    items = data if isinstance(data, list) else data.get('results', data)
    changed = False
    for item in items:
        cat = item.get('category', '')
        if cat and cat not in cat_set and cat in ALIASES:
            new_cat = ALIASES[cat]
            if new_cat in cat_set:
                print(f'{Path(f).name}: {item.get("name","")} [{cat}] -> [{new_cat}]')
                item['category'] = new_cat
                changed = True
                fixed += 1
    if changed:
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)

print(f'\nFixed {fixed} items')

# Report remaining non-canonical
still_bad = {}
for f in sorted(glob.glob('classification_results/design_batch_*.json')):
    data = json.load(open(f, encoding='utf-8'))
    items = data if isinstance(data, list) else data.get('results', data)
    for item in items:
        cat = item.get('category', '')
        if cat and cat not in cat_set:
            still_bad[cat] = still_bad.get(cat, 0) + 1

if still_bad:
    print('\nStill non-canonical:')
    for cat, count in sorted(still_bad.items(), key=lambda x: -x[1]):
        print(f'  ({count}x): {cat}')
else:
    print('All categories now canonical.')
