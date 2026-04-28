#!/usr/bin/env python3
r"""
post_apply_sequence.py — Automated post-apply cleanup orchestrator.

Runs the cleanup pipeline in the correct order after AE apply (PID 22500) exits.
Safe to run: each step checks for its own prerequisites and skips gracefully if not ready.

Steps (run in order):
  0. Merge variant category directories (e.g., "Titles & Typography" → "Title & Typography")
  1. organize_run.py --retry-errors --source ae     (stale errors auto-skipped, real ones retried)
  2. reclassify_unorg.py --analyze                  (re-classify I:\Unorganized items)
  3. reclassify_unorg.py --apply                    (move to correct categories)
  4. organize_run.py --apply --source loose_files   (run ONLY when classify reaches 326/326)
  5. fix_duplicates.py --apply                      (merge all (N) suffix collision pairs)
  6. fix_stock_ae_items.py --scan --analyze --apply  (ONLY if merge_stock has exited)

Usage:
    python post_apply_sequence.py              # run all steps
    python post_apply_sequence.py --dry-run    # preview without moving
    python post_apply_sequence.py --step 1     # run just step N
    python post_apply_sequence.py --step 0     # run only the category-merge step
    python post_apply_sequence.py --skip 4     # skip step N
    python post_apply_sequence.py --wait-pid 12345  # wait for a specific AE apply PID first

Blocking: auto-detects a live AE apply PID before starting when possible.
Does NOT wait for merge_stock.
"""

import os, sys, subprocess, argparse, time, shutil
from pathlib import Path

REPO = Path(__file__).parent

DEFAULT_AE_APPLY_PID = 22500  # Historical hint from an earlier AE apply run; auto-detection is preferred.
PYTHON          = sys.executable
ORGANIZED          = Path(r'G:\Organized')
ORGANIZED_OVERFLOW = Path(r'I:\Organized')   # overflow destination when G:\ is low
LOOSE_INDEX     = REPO / 'loose_files_index.json'
LOOSE_RESULTS   = REPO / 'classification_results'
TOTAL_LOOSE_BATCHES = 326

# Category directories that should be merged into canonical names.
# Applied to BOTH organized roots if they exist.
CATEGORY_MERGES = [
    ('After Effects - Titles & Typography', 'After Effects - Title & Typography'),
]

def all_org_roots() -> list[Path]:
    return [r for r in (ORGANIZED, ORGANIZED_OVERFLOW) if r.exists()]

def is_pid_running(pid: int) -> bool:
    try:
        import ctypes
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            return False
        import ctypes.wintypes
        exit_code = ctypes.wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        STILL_ACTIVE = 259
        return exit_code.value == STILL_ACTIVE
    except Exception:
        return False


def iter_wmic_processes(process_name: str) -> list[dict[str, str]]:
    r"""Return process records from WMIC /format:list as a list of dicts."""
    try:
        out = subprocess.check_output(
            ['wmic', 'process', 'where', f'name="{process_name}"', 'get', 'ProcessId,CommandLine', '/format:list'],
            text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return []

    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        current[key] = value
    if current:
        records.append(current)
    return records


def looks_like_ae_apply_command(cmdline: str) -> bool:
    lowered = cmdline.lower()
    if 'organize_run.py' not in lowered or '--apply' not in lowered:
        return False
    if '--retry-errors' in lowered:
        return False
    for other_source in ('design', 'design_org', 'loose_files', 'design_elements'):
        if f'--source {other_source}' in lowered:
            return False
    return True


def detect_ae_apply_pid(explicit_pid: int | None = None) -> tuple[int | None, str]:
    r"""Return `(pid, reason)` for the AE apply process to wait on, if one is live."""
    if explicit_pid is not None:
        return explicit_pid, 'explicit'

    candidates: list[int] = []
    for proc in iter_wmic_processes('python.exe'):
        cmdline = proc.get('CommandLine', '')
        pid_str = proc.get('ProcessId', '')
        if not pid_str.isdigit() or not looks_like_ae_apply_command(cmdline):
            continue
        candidates.append(int(pid_str))

    live_candidates = [pid for pid in candidates if is_pid_running(pid)]
    if len(live_candidates) == 1:
        return live_candidates[0], 'auto-detected'
    if len(live_candidates) > 1:
        return None, f'ambiguous ({", ".join(str(pid) for pid in live_candidates)})'
    if is_pid_running(DEFAULT_AE_APPLY_PID):
        return DEFAULT_AE_APPLY_PID, 'historical-default'
    return None, 'not-found'

def run(label: str, cmd: list[str], dry_run: bool = False) -> bool:
    print(f'\n{"="*62}')
    print(f'  [{label}]')
    if dry_run:
        print(f'  [DRY RUN] Would run: {" ".join(cmd)}')
        return True
    print(f'  Running: {" ".join(cmd)}')
    print(f'{"="*62}')
    result = subprocess.run(cmd, cwd=str(REPO))
    if result.returncode not in (0, 1):
        print(f'\n  [WARN] Command exited with code {result.returncode}')
        return False
    return True


def is_merge_stock_done() -> bool:
    r"""Check if merge_stock has finished (no robocopy process copying from G:\Stock)."""
    try:
        for proc in iter_wmic_processes('robocopy.exe'):
            cmdline = proc.get('CommandLine', '')
            if r'G:\Stock' in cmdline or 'Stock' in cmdline:
                return False
        return True
    except Exception:
        return True  # assume done if can't check


def main():
    ap = argparse.ArgumentParser(description='Post-apply cleanup orchestrator')
    ap.add_argument('--dry-run', action='store_true', help='Preview steps without executing')
    ap.add_argument('--step',    type=int, help='Run only step N (0-6)')
    ap.add_argument('--skip',    type=int, help='Skip step N')
    ap.add_argument('--no-wait', action='store_true', help='Skip waiting for AE apply to exit')
    ap.add_argument('--wait-pid', type=int, help='Explicit AE apply PID to wait for before starting')
    args = ap.parse_args()

    # --- Wait for AE apply if still running ---
    if not args.no_wait:
        wait_pid, wait_reason = detect_ae_apply_pid(args.wait_pid)
        if wait_pid is not None and is_pid_running(wait_pid):
            print(f'Waiting for AE apply (PID {wait_pid}, {wait_reason}) to exit...')
            while is_pid_running(wait_pid):
                time.sleep(15)
                print('.', end='', flush=True)
            print('\nAE apply exited. Starting cleanup sequence.')
        elif args.wait_pid is not None:
            print(f'AE apply PID {args.wait_pid} already exited.')
        elif wait_reason.startswith('ambiguous'):
            print(f'No unique AE apply process detected ({wait_reason}). Starting immediately.')
        else:
            print('No live AE apply process detected. Starting cleanup sequence immediately.')
    else:
        print('[no-wait] Skipping AE apply check.')

    # --- Step 0: Merge mis-named category directories into canonical names ---
    run_step0 = (args.step is None or args.step == 0) and args.skip != 0
    if run_step0:
        print('\n' + '='*62)
        print('  [Step 0] Merging variant category directories')
        print('='*62)
        for root in all_org_roots():
            for src_name, dst_name in CATEGORY_MERGES:
                src_dir = root / src_name
                dst_dir = root / dst_name
                if not src_dir.exists():
                    print(f'  [SKIP] {root.drive} {src_name} — not found')
                    continue
                src_count = sum(1 for _ in src_dir.rglob('*') if _.is_file())
                print(f'  Merging [{root.drive}] {src_name} ({src_count} files) -> {dst_name}')
                if not args.dry_run:
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    rc = subprocess.run([
                        'robocopy', str(src_dir), str(dst_dir),
                        '/E', '/MOVE', '/COPY:DAT', '/R:1', '/W:1', '/NP', '/NS', '/NC', '/NFL', '/NDL'
                    ]).returncode
                    if rc > 7:
                        print(f'  [WARN] robocopy rc={rc} for {src_name}')
                    else:
                        try:
                            shutil.rmtree(str(src_dir))
                            print(f'  -> merged and removed {root.drive} {src_name}')
                        except FileNotFoundError:
                            print(f'  -> merged and source already removed {root.drive} {src_name}')
                        except Exception as e:
                            print(f'  [WARN] Could not remove {src_name}: {e}')
                else:
                    print(f'  [DRY] Would robocopy /MOVE [{root.drive}] {src_name} -> {dst_name}')

    # Define all steps
    steps = {
        1: ('Retry AE errors',         [PYTHON, 'organize_run.py', '--retry-errors', '--source', 'ae']),
        2: ('Reclassify Unorg analyze', [PYTHON, 'reclassify_unorg.py', '--analyze']),
        3: ('Reclassify Unorg apply',   [PYTHON, 'reclassify_unorg.py', '--apply']),
        4: ('Loose files apply',        None),  # conditional — waits for 326/326 classify batches
        5: ('Fix duplicates',           [PYTHON, 'fix_duplicates.py', '--apply']),
        6: ('Fix stock AE items',       None),  # conditional — requires merge_stock done
    }

    if args.step is None:
        selected = sorted(steps.keys())
    elif args.step == 0:
        selected = []
    else:
        selected = [args.step]
    if args.skip:
        selected = [s for s in selected if s != args.skip]

    for step_n in selected:
        label, cmd = steps[step_n]

        if step_n == 4:
            # Wait until loose_files classify is fully complete (326/326 batches)
            done = sum(1 for p in LOOSE_RESULTS.glob('loose_batch_*.json')
                       if p.is_file())
            if done < TOTAL_LOOSE_BATCHES:
                print(f'\n  [Step 4] Loose files classify: {done}/{TOTAL_LOOSE_BATCHES} batches done.')
                print(f'  Waiting for classify to finish before applying...')
                while True:
                    done = sum(1 for p in LOOSE_RESULTS.glob('loose_batch_*.json')
                               if p.is_file())
                    if done >= TOTAL_LOOSE_BATCHES:
                        break
                    print(f'  [{done}/{TOTAL_LOOSE_BATCHES}] classify still running... (sleeping 60s)')
                    time.sleep(60)
                print(f'  Classify complete. Starting loose_files apply.')
            else:
                print(f'\n  [Step 4] Loose files classify already complete ({done}/{TOTAL_LOOSE_BATCHES}).')
            ok = run(label, [PYTHON, 'organize_run.py', '--apply', '--quiet', '--source', 'loose_files'],
                     dry_run=args.dry_run)
            if not ok:
                print(f'  Loose files apply returned non-zero; continuing anyway.')
            continue

        if step_n == 6:
            if not is_merge_stock_done():
                print('\n  [SKIP] Step 6: merge_stock still running. Run manually after it exits:')
                print('    python fix_stock_ae_items.py --scan')
                print('    python fix_stock_ae_items.py --analyze')
                print('    python fix_stock_ae_items.py --apply')
                continue
            # Run scan → analyze → apply as sub-sequence
            for sub_label, sub_cmd in [
                ('Fix stock AE scan',    [PYTHON, 'fix_stock_ae_items.py', '--scan']),
                ('Fix stock AE analyze', [PYTHON, 'fix_stock_ae_items.py', '--analyze']),
                ('Fix stock AE apply',   [PYTHON, 'fix_stock_ae_items.py', '--apply']),
            ]:
                if not run(sub_label, sub_cmd, dry_run=args.dry_run):
                    print(f'  Step 6 sub-step {sub_label} failed, stopping.')
                    break
            continue

        if cmd is None:
            continue

        ok = run(label, cmd, dry_run=args.dry_run)
        if not ok and step_n in (1, 5):
            # Non-critical steps can fail without stopping sequence
            print(f'  Continuing despite step {step_n} non-zero exit.')
        elif not ok:
            print(f'  Step {step_n} failed, stopping sequence.')
            sys.exit(1)

    print('\n' + '='*62)
    print('  Post-apply sequence complete.')
    print('  Next: python verify_organized.py --summary')
    print('        python verify_organized.py --collisions')
    print('        python verify_organized.py --review')
    print('='*62)


if __name__ == '__main__':
    main()
