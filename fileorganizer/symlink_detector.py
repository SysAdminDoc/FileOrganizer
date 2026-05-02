#!/usr/bin/env python3
r"""
symlink_detector.py — Symlink/junction detection for NEXT-35 pre-flight scanner.

Detects and optionally blocks:
- File symlinks (potentially malicious or out-of-scope)
- Directory junctions (potential path traversal to protected system dirs)
- Reparse points (broken/orphaned)

Windows-specific using FILE_ATTRIBUTE_REPARSE_POINT flag.
"""
import os
import stat
from pathlib import Path
from typing import List, Tuple, Optional


def is_symlink_or_junction(path: str) -> Tuple[bool, Optional[str]]:
    """
    Check if path is a symlink or junction.
    
    Returns (is_reparse, reparse_type) where reparse_type is one of:
    - 'symlink' (file or directory symlink)
    - 'junction' (directory junction, !NTFS 5.0+)
    - 'reparse' (unclassified reparse point — mounted volume, dedup, etc.)
    - None (not a reparse point)
    """
    try:
        path_stat = os.stat(path)
        # FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        is_reparse = bool(path_stat.st_file_attributes & 0x400)
        if not is_reparse:
            return False, None
    except (OSError, AttributeError):
        # st_file_attributes not available on non-Windows
        # Fall back to checking if it's a symlink via os.path.islink
        if os.path.islink(path):
            return True, 'symlink'
        return False, None
    
    # It's a reparse point. Classify it.
    try:
        if os.path.islink(path):
            return True, 'symlink'
    except OSError:
        pass
    
    # Junctions are directories that redirect to another path.
    # On Windows, you can detect a junction by trying to readlink
    # and checking if it's a directory.
    try:
        if os.path.isdir(path) and hasattr(os, 'readlink'):
            # It's a directory reparse point; likely a junction
            return True, 'junction'
    except (OSError, NotImplementedError):
        pass
    
    return True, 'reparse'


def scan_for_reparse_points(folder_path: str) -> List[Tuple[str, str]]:
    """
    Scan folder (shallow, one level deep) for symlinks/junctions.
    
    Returns list of (full_path, issue_type) tuples.
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
        is_reparse, reparse_type = is_symlink_or_junction(full_path)
        if is_reparse and reparse_type:
            issues.append((full_path, reparse_type))
    
    return issues


def is_path_traversal_risk(target: str) -> bool:
    """
    Check if a junction target escapes to protected system directories.
    
    Returns True if target resolves to:
    - C:\\Windows
    - C:\\Program Files
    - C:\\Program Files (x86)
    - C:\\Users\\*\\AppData\\
    - C:\\ProgramData\\
    - C:\\$Recycle.Bin
    """
    protected_roots = {
        'windows',
        'program files',
        'program files (x86)',
        'programdata',
        '$recycle.bin',
    }
    
    try:
        resolved = os.path.realpath(target).lower()
        # Extract drive + top-level folder
        _, tail = os.path.splitdrive(resolved)
        first_folder = tail.split(os.sep)[1] if len(tail.split(os.sep)) > 1 else ''
        
        if first_folder in protected_roots:
            return True
        
        # Check for AppData anywhere in the path
        if 'appdata' in resolved:
            return True
    except Exception:
        pass
    
    return False


def validate_junction_target(junction_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a junction target for safety.
    
    Returns (is_safe, reason) where is_safe=False means the junction
    should be blocked or reviewed.
    """
    try:
        if not os.path.isdir(junction_path):
            return False, "Junction target does not exist"
        
        target = os.path.realpath(junction_path)
        if not os.path.exists(target):
            return False, "Target path unreachable (orphaned junction)"
        
        if is_path_traversal_risk(target):
            return False, f"Target points to protected system directory: {target}"
        
        return True, None
    except Exception as e:
        return False, f"Validation failed: {e}"
