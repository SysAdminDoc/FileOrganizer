#!/usr/bin/env python3
r"""
exiftool_extractor.py — ExifTool integration for metadata extraction (NEXT-43).

ExifTool supports 800+ file formats and can extract comprehensive metadata from:
- Images (JPG, PNG, RAW, HEIC, AVIF, etc.)
- Video (MP4, MOV, MKV, AVI, etc.)
- Audio (MP3, FLAC, OGG, WAV, M4A, etc.)
- Documents (PDF, Office, etc.)

Used as a fallback when primary extractors return low confidence (<50%).
Falls back gracefully if ExifTool is not installed (Windows: bundle binary, Linux: `exiftool` package).
"""
import subprocess
import json
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any

_HAS_PIEXIF = importlib.util.find_spec("piexif") is not None


def _get_exiftool_path() -> Optional[str]:
    """Find exiftool binary on PATH or return bundled Windows path."""
    try:
        # Check if exiftool is on PATH
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            timeout=2,
            text=True
        )
        if result.returncode == 0:
            return "exiftool"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Windows bundled path (if included in future releases)
    # For now, assume system exiftool or user-installed exiftool
    return None


def extract_metadata(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from file using ExifTool.
    
    Returns dict of extracted metadata or None if ExifTool is unavailable.
    Common keys: Make, Model, DateTime, ISO, FNumber, FocalLength, etc.
    """
    exiftool = _get_exiftool_path()
    if not exiftool:
        return None
    
    try:
        result = subprocess.run(
            [exiftool, "-json", str(file_path)],
            capture_output=True,
            timeout=10,
            text=True
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            # exiftool -json returns list; take first element
            return data[0] if isinstance(data, list) else data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    
    return None


def is_available() -> bool:
    """Check if ExifTool is available on this system."""
    return _get_exiftool_path() is not None


def get_creation_date(file_path: Path) -> Optional[str]:
    """Extract creation/modification date from file using ExifTool."""
    metadata = extract_metadata(file_path)
    if not metadata:
        return None
    
    # Priority: DateTimeOriginal > CreateDate > ModifyDate
    for key in ["DateTimeOriginal", "CreateDate", "ModifyDate"]:
        if key in metadata:
            return str(metadata[key])
    
    return None


def get_image_dimensions(file_path: Path) -> Optional[tuple]:
    """Extract image dimensions (width, height) from file."""
    metadata = extract_metadata(file_path)
    if not metadata:
        return None
    
    # Try common dimension keys
    for w_key, h_key in [
        ("ImageWidth", "ImageHeight"),
        ("ExifImageWidth", "ExifImageHeight"),
        ("SourceImageWidth", "SourceImageHeight"),
    ]:
        if w_key in metadata and h_key in metadata:
            try:
                return (int(metadata[w_key]), int(metadata[h_key]))
            except (ValueError, TypeError):
                pass
    
    return None


def get_camera_info(file_path: Path) -> Optional[Dict[str, str]]:
    """Extract camera make/model from file."""
    metadata = extract_metadata(file_path)
    if not metadata:
        return None
    
    info = {}
    if "Make" in metadata:
        info["make"] = str(metadata["Make"])
    if "Model" in metadata:
        info["model"] = str(metadata["Model"])
    if "LensModel" in metadata:
        info["lens"] = str(metadata["LensModel"])
    
    return info if info else None


def get_audio_info(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract audio metadata (duration, bitrate, sample rate, etc.)."""
    metadata = extract_metadata(file_path)
    if not metadata:
        return None
    
    info = {}
    # Duration (usually in seconds or HH:MM:SS)
    for key in ["Duration", "DurationTimebase"]:
        if key in metadata:
            info["duration"] = str(metadata[key])
            break
    
    # Bitrate
    if "BitRate" in metadata:
        info["bitrate"] = str(metadata["BitRate"])
    
    # Sample rate
    if "SampleRate" in metadata:
        info["sample_rate"] = str(metadata["SampleRate"])
    
    # Channels
    if "Channels" in metadata:
        info["channels"] = str(metadata["Channels"])
    
    return info if info else None


def get_video_info(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract video metadata (duration, codec, frame rate, dimensions, etc.)."""
    metadata = extract_metadata(file_path)
    if not metadata:
        return None
    
    info = {}
    
    # Duration
    for key in ["Duration", "DurationTimebase"]:
        if key in metadata:
            info["duration"] = str(metadata[key])
            break
    
    # Video codec
    for key in ["VideoCodecID", "CodecID", "Codec"]:
        if key in metadata:
            info["codec"] = str(metadata[key])
            break
    
    # Frame rate
    for key in ["FrameRate", "VideoFrameRate", "AvgFrameRate"]:
        if key in metadata:
            info["frame_rate"] = str(metadata[key])
            break
    
    # Resolution
    for w_key, h_key in [
        ("ImageWidth", "ImageHeight"),
        ("SourceImageWidth", "SourceImageHeight"),
    ]:
        if w_key in metadata and h_key in metadata:
            info["width"] = int(metadata[w_key])
            info["height"] = int(metadata[h_key])
            break
    
    return info if info else None
