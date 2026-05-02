#!/usr/bin/env python3
r"""
bad_names.py — Bad filename detection for NEXT-42 pre-flight scanner.

Detects naming issues that cause silent failures or taxonomy drift:
- Non-ASCII characters (NTFS ASCII codepage)
- Uppercase-only file extensions (.JPG → .jpg)
- Reserved Windows characters (< > : " / \ | ? *)
- Filename length > 200 chars
- Leading/trailing spaces (already checked in pre-flight but reported here)
"""
import os
import re
from pathlib import Path
from typing import List, Tuple

# Windows reserved characters
RESERVED_CHARS = set('<>:"|?*')

# Extensions that are commonly uppercase
COMMON_UPPERCASE_EXTS = {'.JPG', '.PNG', '.MP4', '.MOV', '.AVI', '.DOCX', '.PDF', '.XLSX', '.ZIP'}


def check_bad_names(folder_path: str) -> List[Tuple[str, str]]:
    """
    Scan folder (shallow, one level deep) for bad filenames.
    
    Returns list of (full_path, issue_description) tuples.
    """
    issues = []
    
    if not os.path.isdir(folder_path):
        return issues
    
    try:
        children = os.listdir(folder_path)
    except (PermissionError, OSError):
        return issues
    
    for child in children:
        full_path = os.path.join(folder_path, child)
        issues.extend(_check_filename(child, full_path))
    
    return issues


def _check_filename(filename: str, full_path: str) -> List[Tuple[str, str]]:
    """Check a single filename for issues."""
    issues = []
    
    # Check for non-ASCII characters
    try:
        filename.encode('ascii')
    except UnicodeEncodeError:
        issues.append((full_path, "Non-ASCII characters in filename"))
    
    # Check for reserved Windows characters
    if any(c in filename for c in RESERVED_CHARS):
        reserved_found = ''.join(c for c in filename if c in RESERVED_CHARS)
        issues.append((full_path, f"Reserved Windows characters: {reserved_found}"))
    
    # Check for leading/trailing spaces
    if filename != filename.strip():
        issues.append((full_path, "Leading or trailing space in filename"))
    
    # Check filename length (leave headroom below 260-char path limit)
    if len(filename) > 200:
        issues.append((full_path, f"Filename length {len(filename)} chars (>200)"))
    
    # Check for uppercase-only extensions
    if '.' in filename:
        ext = os.path.splitext(filename)[1].upper()
        if ext in COMMON_UPPERCASE_EXTS:
            # This is an uppercase extension that should be lowercase
            issues.append((full_path, f"Uppercase extension {ext} (should be {ext.lower()})"))
    
    return issues


def fix_bad_names(folder_path: str, dry_run: bool = True) -> List[Tuple[str, str, str]]:
    """
    Fix bad filenames in a folder.
    
    Returns list of (original_path, new_path, action) tuples for reporting.
    Respects dry_run flag (if False, actually renames files).
    """
    results = []
    
    if not os.path.isdir(folder_path):
        return results
    
    try:
        children = os.listdir(folder_path)
    except (PermissionError, OSError):
        return results
    
    for child in children:
        full_path = os.path.join(folder_path, child)
        issues = _check_filename(child, full_path)
        
        if not issues:
            continue
        
        # Build a fixed filename
        fixed = child
        
        # Strip leading/trailing spaces
        fixed = fixed.strip()
        
        # Replace reserved characters with underscore
        for c in RESERVED_CHARS:
            fixed = fixed.replace(c, '_')
        
        # Normalize uppercase extensions to lowercase
        if '.' in fixed:
            name, ext = os.path.splitext(fixed)
            if ext.upper() in COMMON_UPPERCASE_EXTS:
                fixed = name + ext.lower()
        
        if fixed != child:
            new_path = os.path.join(folder_path, fixed)
            if not dry_run:
                try:
                    os.rename(full_path, new_path)
                    results.append((full_path, new_path, 'renamed'))
                except OSError as e:
                    results.append((full_path, full_path, f'rename failed: {e}'))
            else:
                results.append((full_path, new_path, 'would rename'))
    
    return results
