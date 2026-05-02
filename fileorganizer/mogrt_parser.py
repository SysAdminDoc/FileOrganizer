"""FileOrganizer — Motion Graphics Template (.mogrt) metadata parser.

.mogrt files are ZIP archives containing:
1. Manifest.json: Template metadata (name, parameters, required fonts, minimum version)
2. Media files: Preview/thumbnail images
3. Plugin files: Template effects and graphics

Design:
- parse_mogrt(): Extract manifest and key metadata
- Store in asset_files.metadata or return as dict
- Graceful fallback if manifest missing
- Extract: name, parameters (count/list), required fonts, min Premiere version

Example:
  metadata = parse_mogrt('/path/to/template.mogrt')
  # Returns: {
  #   'name': 'Cool Title',
  #   'parameters': ['Title', 'Subtitle', 'Color'],
  #   'required_fonts': ['Montserrat', 'Roboto'],
  #   'min_premiere_version': '2025.0',
  # }
"""

import json
import zipfile
import os
from typing import Dict, Any, Optional, List
from pathlib import Path


def parse_mogrt(mogrt_path: str) -> Optional[Dict[str, Any]]:
    """Parse Motion Graphics Template file metadata.
    
    Args:
        mogrt_path: Path to .mogrt file
    
    Returns:
        Dict with keys: name, parameters, required_fonts, min_premiere_version, duration, etc.
        Returns None if file is not a valid MOGRT or parsing fails.
    """
    if not os.path.isfile(mogrt_path):
        return None
    
    metadata = {
        'type': 'mogrt',
        'name': None,
        'parameters': [],
        'required_fonts': [],
        'min_premiere_version': None,
        'duration': None,
        'has_preview': False,
    }
    
    try:
        with zipfile.ZipFile(mogrt_path, 'r') as zf:
            # Check for manifest
            manifest_names = ['Manifest.json', 'manifest.json', 'MANIFEST.json']
            manifest_path = None
            
            for name in manifest_names:
                if name in zf.namelist():
                    manifest_path = name
                    break
            
            if not manifest_path:
                # Not a valid MOGRT (no manifest)
                return None
            
            # Parse manifest
            try:
                manifest_data = zf.read(manifest_path).decode('utf-8')
                manifest = json.loads(manifest_data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            
            # Extract template name
            metadata['name'] = manifest.get('templateName') or manifest.get('name')
            
            # Extract parameters (editable fields)
            parameters = manifest.get('parameters', [])
            if isinstance(parameters, list):
                metadata['parameters'] = [p.get('name') or p for p in parameters if p]
            elif isinstance(parameters, dict):
                metadata['parameters'] = list(parameters.keys())
            
            # Extract required fonts
            required_fonts = manifest.get('requiredFonts', [])
            if isinstance(required_fonts, list):
                metadata['required_fonts'] = required_fonts
            elif isinstance(required_fonts, dict):
                metadata['required_fonts'] = list(required_fonts.keys())
            
            # Extract minimum Premiere version
            metadata['min_premiere_version'] = manifest.get('minPremierePro') or manifest.get('minVersion')
            
            # Extract duration if present
            duration = manifest.get('duration')
            if duration is not None:
                try:
                    metadata['duration'] = float(duration)
                except (ValueError, TypeError):
                    pass
            
            # Check for preview/thumbnail
            preview_names = ['preview.jpg', 'preview.png', 'thumbnail.jpg', 'thumbnail.png']
            for preview in preview_names:
                if preview in zf.namelist():
                    metadata['has_preview'] = True
                    break
            
            # Extract additional useful fields
            if 'category' in manifest:
                metadata['category'] = manifest['category']
            
            if 'description' in manifest:
                metadata['description'] = manifest['description']
            
            if 'version' in manifest:
                metadata['version'] = manifest['version']
            
            if 'author' in manifest:
                metadata['author'] = manifest['author']
        
        return metadata
    
    except zipfile.BadZipFile:
        # Not a valid ZIP file
        return None
    except Exception:
        # Any other error
        return None


def batch_parse_mogrt(mogrt_paths: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Parse multiple MOGRT files.
    
    Args:
        mogrt_paths: List of paths to .mogrt files
    
    Returns:
        Dict mapping path → metadata (or None if parsing failed)
    """
    results = {}
    for path in mogrt_paths:
        results[path] = parse_mogrt(path)
    return results


def is_mogrt_file(file_path: str) -> bool:
    """Check if file is a valid MOGRT."""
    if not file_path.lower().endswith('.mogrt'):
        return False
    
    metadata = parse_mogrt(file_path)
    return metadata is not None


def extract_mogrt_fonts(mogrt_path: str) -> List[str]:
    """Extract list of required fonts from MOGRT.
    
    Args:
        mogrt_path: Path to .mogrt file
    
    Returns:
        List of font names (empty list if none found or parsing failed)
    """
    metadata = parse_mogrt(mogrt_path)
    if not metadata:
        return []
    return metadata.get('required_fonts', [])


def mogrt_to_category_hints(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MOGRT metadata to category classification hints.
    
    Returns:
        Dict with keys: category_signals, confidence, reasoning
    """
    hints = {
        'category_signals': [],
        'confidence': 0,
        'reasoning': ''
    }
    
    if not metadata or not metadata.get('name'):
        return hints
    
    name = metadata['name'].lower()
    
    # Pattern-based categorization
    patterns = {
        'Title / Lower Third': ['title', 'lower third', 'lower-third', 'subtitle'],
        'Motion Graphic': ['motion', 'animation', 'animate', 'graphic', 'graphics'],
        'Transition': ['transition', 'wipe', 'dissolve', 'fade'],
        'Effect': ['effect', 'filter', 'distortion', 'glitch'],
        'Broadcast / Cinema Stock': ['broadcast', 'cinema', '4k', 'uhd', 'broadcast-quality'],
    }
    
    signal_count = 0
    for category, keywords in patterns.items():
        for kw in keywords:
            if kw in name:
                hints['category_signals'].append(category)
                signal_count += 1
                break
    
    # Confidence based on signals found
    if signal_count >= 2:
        hints['confidence'] = 75
    elif signal_count == 1:
        hints['confidence'] = 50
    
    # Reasoning
    if hints['category_signals']:
        hints['reasoning'] = f"Matched keywords: {', '.join(set(hints['category_signals']))}"
    else:
        hints['reasoning'] = "No pattern matches in MOGRT name"
    
    return hints
