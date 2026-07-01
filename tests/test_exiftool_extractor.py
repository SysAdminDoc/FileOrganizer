"""Tests for fileorganizer.exiftool_extractor — NEXT-43 ExifTool integration."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fileorganizer.exiftool_extractor import (
    extract_metadata,
    is_available,
    get_creation_date,
    get_image_dimensions,
    get_camera_info,
    get_audio_info,
    get_video_info,
)


SAMPLE_IMAGE_METADATA = [{
    "FileName": "test.jpg",
    "Make": "Canon",
    "Model": "EOS R5",
    "LensModel": "RF 24-70mm F2.8L IS USM",
    "DateTimeOriginal": "2026:01:15 14:30:00",
    "CreateDate": "2026:01:15 14:30:00",
    "ImageWidth": 8192,
    "ImageHeight": 5464,
    "ISO": 400,
    "FNumber": 2.8,
}]

SAMPLE_VIDEO_METADATA = [{
    "FileName": "clip.mp4",
    "Duration": "00:02:30",
    "VideoCodecID": "avc1",
    "FrameRate": "29.97",
    "ImageWidth": 3840,
    "ImageHeight": 2160,
}]

SAMPLE_AUDIO_METADATA = [{
    "FileName": "track.mp3",
    "Duration": "3:45",
    "BitRate": "320000",
    "SampleRate": "44100",
    "Channels": "2",
}]


def _mock_run_success(metadata_list):
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps(metadata_list)
    return result


class TestExifToolAvailability(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor.subprocess.run")
    def test_available_when_on_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(is_available())

    @patch("fileorganizer.exiftool_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_unavailable_when_not_found(self, mock_run):
        self.assertFalse(is_available())


class TestExtractMetadata(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor._get_exiftool_path", return_value=None)
    def test_returns_none_when_unavailable(self, _):
        self.assertIsNone(extract_metadata(Path("test.jpg")))

    @patch("fileorganizer.exiftool_extractor.subprocess.run")
    @patch("fileorganizer.exiftool_extractor._get_exiftool_path",
           return_value="exiftool")
    def test_extracts_metadata(self, _, mock_run):
        mock_run.return_value = _mock_run_success(SAMPLE_IMAGE_METADATA)
        result = extract_metadata(Path("test.jpg"))
        self.assertIsNotNone(result)
        self.assertEqual(result["Make"], "Canon")

    @patch("fileorganizer.exiftool_extractor.subprocess.run",
           side_effect=Exception("timeout"))
    @patch("fileorganizer.exiftool_extractor._get_exiftool_path",
           return_value="exiftool")
    def test_handles_subprocess_error(self, _, __):
        self.assertIsNone(extract_metadata(Path("test.jpg")))


class TestGetCreationDate(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor.extract_metadata")
    def test_prefers_datetime_original(self, mock_extract):
        mock_extract.return_value = SAMPLE_IMAGE_METADATA[0]
        date = get_creation_date(Path("test.jpg"))
        self.assertEqual(date, "2026:01:15 14:30:00")

    @patch("fileorganizer.exiftool_extractor.extract_metadata",
           return_value={"ModifyDate": "2026:02:01 10:00:00"})
    def test_falls_back_to_modify_date(self, _):
        date = get_creation_date(Path("test.jpg"))
        self.assertEqual(date, "2026:02:01 10:00:00")

    @patch("fileorganizer.exiftool_extractor.extract_metadata", return_value=None)
    def test_returns_none_when_unavailable(self, _):
        self.assertIsNone(get_creation_date(Path("test.jpg")))


class TestGetImageDimensions(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor.extract_metadata")
    def test_extracts_dimensions(self, mock_extract):
        mock_extract.return_value = SAMPLE_IMAGE_METADATA[0]
        dims = get_image_dimensions(Path("test.jpg"))
        self.assertEqual(dims, (8192, 5464))

    @patch("fileorganizer.exiftool_extractor.extract_metadata", return_value={})
    def test_returns_none_for_missing_keys(self, _):
        self.assertIsNone(get_image_dimensions(Path("test.jpg")))


class TestGetCameraInfo(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor.extract_metadata")
    def test_extracts_camera_info(self, mock_extract):
        mock_extract.return_value = SAMPLE_IMAGE_METADATA[0]
        info = get_camera_info(Path("test.jpg"))
        self.assertEqual(info["make"], "Canon")
        self.assertEqual(info["model"], "EOS R5")
        self.assertEqual(info["lens"], "RF 24-70mm F2.8L IS USM")

    @patch("fileorganizer.exiftool_extractor.extract_metadata", return_value={})
    def test_returns_none_for_no_camera(self, _):
        self.assertIsNone(get_camera_info(Path("test.jpg")))


class TestGetAudioInfo(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor.extract_metadata")
    def test_extracts_audio_info(self, mock_extract):
        mock_extract.return_value = SAMPLE_AUDIO_METADATA[0]
        info = get_audio_info(Path("test.mp3"))
        self.assertEqual(info["duration"], "3:45")
        self.assertEqual(info["bitrate"], "320000")
        self.assertEqual(info["sample_rate"], "44100")
        self.assertEqual(info["channels"], "2")


class TestGetVideoInfo(unittest.TestCase):
    @patch("fileorganizer.exiftool_extractor.extract_metadata")
    def test_extracts_video_info(self, mock_extract):
        mock_extract.return_value = SAMPLE_VIDEO_METADATA[0]
        info = get_video_info(Path("clip.mp4"))
        self.assertEqual(info["duration"], "00:02:30")
        self.assertEqual(info["codec"], "avc1")
        self.assertEqual(info["frame_rate"], "29.97")
        self.assertEqual(info["width"], 3840)
        self.assertEqual(info["height"], 2160)


if __name__ == "__main__":
    unittest.main()
