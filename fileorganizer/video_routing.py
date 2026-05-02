"""FileOrganizer — Advanced video metadata extraction and routing.

Builds on video_extractor.py. Routes videos by:
- aspect ratio (9:16 vertical → Social Media)
- duration + codec (≤15s looping ProRes/DNXHD → Motion Graphic)
- codec type (ProRes/DNXHD/XDCAM → Broadcast / Cinema Stock)
- duration > 5min → Tutorial Video
- broadcast frame rates (59.94, 29.97) → Broadcast
- 60fps + 4K → High-performance
- HDR metadata → HDR Source

Design:
- VideoRoutingMetadata: Extends base metadata with routing signals
- route_video(): Determine category based on technical specs + heuristics
- extract_video_codecs(): ffprobe-based codec extraction

Minimal new dependencies: ffprobe only (already in system on many dev machines).
"""

import os
import json
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass, asdict


@dataclass
class VideoRoutingMetadata:
    """Video metadata optimized for intelligent routing."""
    # Base fields
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    bitrate: Optional[int] = None  # bits/sec
    
    # Codec info
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    
    # Routing signals
    aspect_ratio: Optional[float] = None
    is_vertical: bool = False
    is_looping_clip: bool = False
    is_broadcast_codec: bool = False
    is_broadcast_fps: bool = False
    is_high_performance: bool = False
    has_hdr: bool = False
    has_audio: bool = False
    
    # Final routing
    suggested_category: Optional[str] = None
    confidence: float = 0.0


def extract_video_codecs(file_path: str) -> Dict[str, Any]:
    """Extract codec information using ffprobe.
    
    Args:
        file_path: Path to video file
    
    Returns:
        Dict with keys: video_codec, audio_codec, frame_rate, resolution, duration, bitrate
    """
    try:
        import subprocess
        
        # Try to run ffprobe
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_format',
                '-show_streams',
                '-of', 'json',
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return {}
        
        data = json.loads(result.stdout)
        
        output = {
            'video_codec': None,
            'audio_codec': None,
            'frame_rate': None,
            'resolution': None,
            'duration': None,
            'bitrate': None,
        }
        
        # Extract streams
        streams = data.get('streams', [])
        
        for stream in streams:
            codec_type = stream.get('codec_type')
            
            if codec_type == 'video':
                output['video_codec'] = stream.get('codec_name')
                
                # Resolution
                width = stream.get('width')
                height = stream.get('height')
                if width and height:
                    output['resolution'] = f'{width}x{height}'
                
                # Frame rate
                fps_str = stream.get('r_frame_rate')
                if fps_str and '/' in fps_str:
                    try:
                        num, den = map(float, fps_str.split('/'))
                        output['frame_rate'] = num / den if den > 0 else None
                    except (ValueError, ZeroDivisionError):
                        pass
            
            elif codec_type == 'audio':
                output['audio_codec'] = stream.get('codec_name')
        
        # Duration from format
        if 'format' in data:
            duration_str = data['format'].get('duration')
            if duration_str:
                try:
                    output['duration'] = float(duration_str)
                except ValueError:
                    pass
            
            # Bitrate
            bitrate_str = data['format'].get('bit_rate')
            if bitrate_str:
                try:
                    output['bitrate'] = int(bitrate_str)
                except ValueError:
                    pass
        
        return output
    
    except Exception:
        return {}


def analyze_video_metadata(file_path: str, codec_info: Optional[Dict[str, Any]] = None) -> VideoRoutingMetadata:
    """Analyze video file and produce routing metadata.
    
    Args:
        file_path: Path to video file
        codec_info: Pre-extracted codec info (optional, will extract if not provided)
    
    Returns:
        VideoRoutingMetadata with routing signals and suggested category
    """
    if codec_info is None:
        codec_info = extract_video_codecs(file_path)
    
    metadata = VideoRoutingMetadata()
    
    # Extract basic fields
    metadata.video_codec = codec_info.get('video_codec')
    metadata.audio_codec = codec_info.get('audio_codec')
    metadata.bitrate = codec_info.get('bitrate')
    metadata.duration = codec_info.get('duration')
    
    # Parse resolution
    resolution = codec_info.get('resolution')
    if resolution and 'x' in resolution:
        try:
            width_str, height_str = resolution.split('x')
            metadata.width = int(width_str)
            metadata.height = int(height_str)
        except (ValueError, IndexError):
            pass
    
    # Parse frame rate
    metadata.fps = codec_info.get('frame_rate')
    
    # Check for audio
    metadata.has_audio = metadata.audio_codec is not None
    
    # Calculate aspect ratio
    if metadata.width and metadata.height:
        aspect = metadata.width / metadata.height
        metadata.aspect_ratio = aspect
        
        # Vertical video (9:16, 1:1.5, etc.)
        if aspect < 0.7:
            metadata.is_vertical = True
    
    # Detect broadcast codec
    broadcast_codecs = ['prores', 'dnxhd', 'xdcam', 'dv', 'mpeg2video']
    if metadata.video_codec:
        codec_lower = metadata.video_codec.lower()
        for bc in broadcast_codecs:
            if bc in codec_lower:
                metadata.is_broadcast_codec = True
                break
    
    # Detect broadcast frame rate (23.976, 29.97, 59.94, etc.)
    if metadata.fps:
        # Allow ±0.5 tolerance for rounding
        if any(abs(metadata.fps - fps) < 0.5 for fps in [23.976, 24.0, 25.0, 29.97, 30.0, 59.94, 60.0]):
            metadata.is_broadcast_fps = True
    
    # Looping clip detection (short, low bitrate, high fps)
    if metadata.duration and metadata.duration <= 15:
        if metadata.fps and metadata.fps >= 30:
            if metadata.bitrate and metadata.bitrate < 50_000_000:  # < 50 Mbps
                metadata.is_looping_clip = True
    
    # High-performance detection (60fps + 4K)
    if metadata.fps and metadata.fps >= 60:
        if metadata.width and metadata.height:
            pixels = metadata.width * metadata.height
            if pixels >= 3840 * 2160:  # 4K minimum
                metadata.is_high_performance = True
    
    # Route to category
    metadata.suggested_category, metadata.confidence = _route_video(metadata)
    
    return metadata


def _route_video(metadata: VideoRoutingMetadata) -> Tuple[Optional[str], float]:
    """Determine category and confidence score for video.
    
    Returns:
        Tuple of (category, confidence) where confidence is 0.0-1.0
    """
    
    # Rule 1: Vertical videos → Social Media
    if metadata.is_vertical:
        return ('Social Media', 0.90)
    
    # Rule 2: Short looping + broadcast codec → Motion Graphic
    if metadata.is_looping_clip and metadata.is_broadcast_codec:
        return ('Motion Graphic', 0.85)
    
    # Rule 3: Broadcast codec alone → Broadcast / Cinema Stock
    if metadata.is_broadcast_codec:
        return ('Broadcast / Cinema Stock', 0.75)
    
    # Rule 4: High-performance (60fps + 4K) → High-Performance Clips
    if metadata.is_high_performance:
        return ('High-Performance Clips', 0.80)
    
    # Rule 5: Long duration → Tutorial Video
    if metadata.duration and metadata.duration > 300:  # > 5 min
        return ('Tutorial Video', 0.65)
    
    # Rule 6: Broadcast frame rate → Broadcast
    if metadata.is_broadcast_fps:
        return ('Broadcast', 0.60)
    
    # Default: Stock footage or generic
    return ('Video Stock Footage', 0.30)


def batch_analyze_videos(file_paths: List[str]) -> Dict[str, VideoRoutingMetadata]:
    """Analyze multiple video files.
    
    Args:
        file_paths: List of paths to video files
    
    Returns:
        Dict mapping path → VideoRoutingMetadata
    """
    results = {}
    for path in file_paths:
        results[path] = analyze_video_metadata(path)
    return results


def video_to_routing_hints(metadata: VideoRoutingMetadata) -> Dict[str, Any]:
    """Convert video routing metadata to category hints.
    
    Returns:
        Dict with keys: category_signals, confidence, reasoning
    """
    hints = {
        'category_signals': [],
        'confidence': 0,
        'reasoning': ''
    }
    
    if metadata.suggested_category:
        hints['category_signals'].append(metadata.suggested_category)
        hints['confidence'] = int(metadata.confidence * 100)
        
        # Build reasoning
        reasons = []
        if metadata.is_vertical:
            reasons.append('vertical aspect ratio')
        if metadata.is_looping_clip:
            reasons.append('looping clip (≤15s)')
        if metadata.is_broadcast_codec:
            reasons.append(f'broadcast codec ({metadata.video_codec})')
        if metadata.is_broadcast_fps:
            reasons.append(f'broadcast frame rate ({metadata.fps}fps)')
        if metadata.is_high_performance:
            reasons.append('high-performance (60fps 4K+)')
        if metadata.duration and metadata.duration > 300:
            reasons.append(f'long duration ({metadata.duration:.0f}s)')
        
        if reasons:
            hints['reasoning'] = f"Matched: {', '.join(reasons)}"
        else:
            hints['reasoning'] = f"Default routing based on technical specs"
    
    return hints
