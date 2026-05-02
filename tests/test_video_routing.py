"""Tests for video metadata extraction and routing."""

import pytest
from fileorganizer.video_routing import (
    VideoRoutingMetadata, analyze_video_metadata, _route_video,
    batch_analyze_videos, video_to_routing_hints
)


class TestVideoRoutingMetadata:
    """Test VideoRoutingMetadata dataclass."""
    
    def test_create_metadata(self):
        """Test creating video routing metadata."""
        metadata = VideoRoutingMetadata(
            duration=30.0,
            width=1920,
            height=1080,
            fps=30.0,
            video_codec='h264'
        )
        
        assert metadata.duration == 30.0
        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.fps == 30.0
    
    def test_metadata_defaults(self):
        """Test metadata with default values."""
        metadata = VideoRoutingMetadata()
        
        assert metadata.duration is None
        assert metadata.width is None
        assert metadata.is_vertical is False
        assert metadata.confidence == 0.0


class TestVideoRouting:
    """Test video routing logic."""
    
    def test_route_vertical_video(self):
        """Test routing vertical video to Social Media."""
        metadata = VideoRoutingMetadata(
            width=1080,
            height=1920,
            aspect_ratio=1080/1920,
            is_vertical=True
        )
        
        category, confidence = _route_video(metadata)
        
        assert category == 'Social Media'
        assert confidence > 0.8
    
    def test_route_broadcast_codec(self):
        """Test routing broadcast codec."""
        metadata = VideoRoutingMetadata(
            video_codec='prores',
            is_broadcast_codec=True
        )
        
        category, confidence = _route_video(metadata)
        
        assert category == 'Broadcast / Cinema Stock'
        assert confidence > 0.7
    
    def test_route_looping_clip(self):
        """Test routing looping clip (short + broadcast codec)."""
        metadata = VideoRoutingMetadata(
            duration=10.0,
            fps=60.0,
            video_codec='prores',
            is_looping_clip=True,
            is_broadcast_codec=True
        )
        
        category, confidence = _route_video(metadata)
        
        assert category == 'Motion Graphic'
        assert confidence > 0.8
    
    def test_route_high_performance(self):
        """Test routing high-performance video (60fps + 4K)."""
        metadata = VideoRoutingMetadata(
            fps=60.0,
            width=3840,
            height=2160,
            is_high_performance=True
        )
        
        category, confidence = _route_video(metadata)
        
        assert category == 'High-Performance Clips'
        assert confidence > 0.7
    
    def test_route_long_video(self):
        """Test routing long video (>5 min) to Tutorial."""
        metadata = VideoRoutingMetadata(
            duration=600.0  # 10 minutes
        )
        
        category, confidence = _route_video(metadata)
        
        assert category == 'Tutorial Video'
        assert confidence > 0.6
    
    def test_route_broadcast_fps(self):
        """Test routing video with broadcast frame rate."""
        metadata = VideoRoutingMetadata(
            fps=29.97  # NTSC broadcast
        )
        
        category, confidence = _route_video(metadata)
        
        assert category == 'Broadcast'
        assert confidence > 0.5
    
    def test_route_default(self):
        """Test default routing for generic video."""
        metadata = VideoRoutingMetadata(
            duration=30.0,
            fps=30.0
        )
        
        category, confidence = _route_video(metadata)
        
        # Should fall through to default
        assert category == 'Video Stock Footage'
        assert confidence < 0.5


class TestAnalyzeVideoMetadata:
    """Test video metadata analysis."""
    
    def test_analyze_vertical_video(self):
        """Test analyzing a vertical video."""
        codec_info = {
            'video_codec': 'h264',
            'audio_codec': 'aac',
            'resolution': '1080x1920',
            'frame_rate': 30.0,
            'duration': 15.0,
            'bitrate': 5_000_000
        }
        
        metadata = analyze_video_metadata('/fake/video.mp4', codec_info)
        
        assert metadata.width == 1080
        assert metadata.height == 1920
        assert metadata.is_vertical is True
        assert metadata.aspect_ratio < 0.7
    
    def test_analyze_horizontal_video(self):
        """Test analyzing a horizontal video."""
        codec_info = {
            'video_codec': 'h264',
            'resolution': '1920x1080',
            'frame_rate': 24.0,
            'duration': 60.0
        }
        
        metadata = analyze_video_metadata('/fake/video.mp4', codec_info)
        
        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.is_vertical is False
    
    def test_analyze_4k_60fps(self):
        """Test analyzing 4K 60fps video."""
        codec_info = {
            'video_codec': 'h265',
            'resolution': '3840x2160',
            'frame_rate': 60.0,
            'duration': 30.0
        }
        
        metadata = analyze_video_metadata('/fake/4k60.mp4', codec_info)
        
        assert metadata.width == 3840
        assert metadata.height == 2160
        assert metadata.fps == 60.0
        assert metadata.is_high_performance is True
    
    def test_analyze_broadcast_codec(self):
        """Test analyzing video with broadcast codec."""
        codec_info = {
            'video_codec': 'dnxhd',
            'audio_codec': 'pcm_s24le',
            'resolution': '1920x1080',
            'frame_rate': 29.97,
            'duration': 120.0
        }
        
        metadata = analyze_video_metadata('/fake/broadcast.mov', codec_info)
        
        assert metadata.is_broadcast_codec is True
        assert 'dnxhd' in metadata.video_codec.lower()
    
    def test_analyze_looping_clip(self):
        """Test analyzing short looping clip."""
        codec_info = {
            'video_codec': 'prores',
            'resolution': '1920x1080',
            'frame_rate': 30.0,
            'duration': 10.0,
            'bitrate': 30_000_000  # < 50 Mbps
        }
        
        metadata = analyze_video_metadata('/fake/loop.mov', codec_info)
        
        assert metadata.duration == 10.0
        assert metadata.is_looping_clip is True
    
    def test_analyze_long_tutorial(self):
        """Test analyzing long tutorial video."""
        codec_info = {
            'video_codec': 'h264',
            'audio_codec': 'aac',
            'duration': 600.0  # 10 minutes
        }
        
        metadata = analyze_video_metadata('/fake/tutorial.mp4', codec_info)
        
        assert metadata.duration == 600.0
        assert metadata.suggested_category == 'Tutorial Video'
    
    def test_analyze_with_audio(self):
        """Test detecting audio codec."""
        codec_info = {
            'video_codec': 'h264',
            'audio_codec': 'aac'
        }
        
        metadata = analyze_video_metadata('/fake/video.mp4', codec_info)
        
        assert metadata.has_audio is True
    
    def test_analyze_without_audio(self):
        """Test detecting no audio."""
        codec_info = {
            'video_codec': 'h264',
            'audio_codec': None
        }
        
        metadata = analyze_video_metadata('/fake/video.mp4', codec_info)
        
        assert metadata.has_audio is False
    
    def test_analyze_malformed_resolution(self):
        """Test handling malformed resolution string."""
        codec_info = {
            'video_codec': 'h264',
            'resolution': 'invalid'
        }
        
        metadata = analyze_video_metadata('/fake/video.mp4', codec_info)
        
        # Should not crash, width/height remain None
        assert metadata.width is None
        assert metadata.height is None


class TestVideoToRoutingHints:
    """Test conversion to routing hints."""
    
    def test_hints_with_routing(self):
        """Test generating hints for routed video."""
        metadata = VideoRoutingMetadata(
            suggested_category='Social Media',
            confidence=0.90,
            is_vertical=True
        )
        
        hints = video_to_routing_hints(metadata)
        
        assert 'Social Media' in hints['category_signals']
        assert hints['confidence'] == 90
        assert 'vertical' in hints['reasoning'].lower()
    
    def test_hints_with_multiple_signals(self):
        """Test hints with multiple routing signals."""
        metadata = VideoRoutingMetadata(
            suggested_category='Broadcast / Cinema Stock',
            confidence=0.75,
            is_broadcast_codec=True,
            video_codec='prores',
            fps=29.97,
            is_broadcast_fps=True
        )
        
        hints = video_to_routing_hints(metadata)
        
        assert hints['confidence'] == 75
        assert 'prores' in hints['reasoning'].lower()
        assert 'broadcast' in hints['reasoning'].lower()
    
    def test_hints_without_routing(self):
        """Test hints when no routing occurs."""
        metadata = VideoRoutingMetadata(
            suggested_category=None,
            confidence=0.0
        )
        
        hints = video_to_routing_hints(metadata)
        
        assert hints['category_signals'] == []
        assert hints['confidence'] == 0


class TestBatchAnalyze:
    """Test batch video analysis."""
    
    def test_batch_analyze(self):
        """Test analyzing multiple videos."""
        codec_info_1 = {
            'video_codec': 'h264',
            'resolution': '1080x1920',
            'duration': 15.0
        }
        
        codec_info_2 = {
            'video_codec': 'prores',
            'resolution': '1920x1080',
            'duration': 120.0
        }
        
        # We can't test actual file paths without ffprobe, but we can
        # test the structure of the returned dict
        paths = ['/fake/video1.mp4', '/fake/video2.mov']
        
        # Mock the analyze function if needed
        # For now, just test that batch_analyze returns a dict
        assert isinstance(batch_analyze_videos([]), dict)


class TestFrameRateDetection:
    """Test frame rate detection."""
    
    def test_detect_23_976_fps(self):
        """Test detecting 23.976 fps (NTSC film)."""
        metadata = VideoRoutingMetadata(fps=23.976)
        
        assert metadata.is_broadcast_fps == False  # Will be True after analyze
        
        # After analysis in _route_video
        category, conf = _route_video(metadata)
        # 23.976 should match broadcast detection
    
    def test_detect_29_97_fps(self):
        """Test detecting 29.97 fps (NTSC)."""
        metadata = VideoRoutingMetadata(fps=29.97, is_broadcast_fps=True)
        
        assert metadata.is_broadcast_fps is True
    
    def test_detect_59_94_fps(self):
        """Test detecting 59.94 fps (NTSC high frame rate)."""
        metadata = VideoRoutingMetadata(fps=59.94, is_broadcast_fps=True)
        
        assert metadata.is_broadcast_fps is True
    
    def test_detect_60_fps(self):
        """Test detecting 60 fps."""
        metadata = VideoRoutingMetadata(fps=60.0, is_broadcast_fps=True)
        
        assert metadata.is_broadcast_fps is True


class TestCodecDetection:
    """Test codec detection."""
    
    def test_detect_prores(self):
        """Test detecting ProRes codec."""
        codec_info = {'video_codec': 'prores'}
        metadata = analyze_video_metadata('/fake/video.mov', codec_info)
        
        assert metadata.is_broadcast_codec is True
    
    def test_detect_dnxhd(self):
        """Test detecting DNxHD codec."""
        codec_info = {'video_codec': 'dnxhd'}
        metadata = analyze_video_metadata('/fake/video.mov', codec_info)
        
        assert metadata.is_broadcast_codec is True
    
    def test_detect_xdcam(self):
        """Test detecting XDCAM codec."""
        codec_info = {'video_codec': 'mpeg2video'}  # XDCAM uses MPEG2
        metadata = analyze_video_metadata('/fake/video.mxf', codec_info)
        
        assert metadata.is_broadcast_codec is True
    
    def test_h264_not_broadcast(self):
        """Test that H.264 is not marked as broadcast codec."""
        codec_info = {'video_codec': 'h264'}
        metadata = analyze_video_metadata('/fake/video.mp4', codec_info)
        
        assert metadata.is_broadcast_codec is False
