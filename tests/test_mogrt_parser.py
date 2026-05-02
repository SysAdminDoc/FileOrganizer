"""Tests for MOGRT (Motion Graphics Template) metadata parser."""

import pytest
import json
import os
import tempfile
import zipfile
from pathlib import Path

from fileorganizer.mogrt_parser import (
    parse_mogrt, batch_parse_mogrt, is_mogrt_file, extract_mogrt_fonts,
    mogrt_to_category_hints
)


@pytest.fixture
def sample_mogrt_file():
    """Create a sample MOGRT file for testing."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'test_template.mogrt')
    
    manifest = {
        'templateName': 'Cool Title Template',
        'parameters': [
            {'name': 'Title'},
            {'name': 'Subtitle'},
            {'name': 'Duration'},
        ],
        'requiredFonts': ['Montserrat', 'Roboto'],
        'minPremierePro': '2024.0',
        'duration': 3.0,
        'version': '1.0',
        'author': 'Adobe',
        'description': 'A cool title template',
    }
    
    # Create ZIP with manifest
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('Manifest.json', json.dumps(manifest))
        # Add a fake preview
        zf.writestr('preview.jpg', b'fake_image_data')
    
    yield mogrt_path
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_mogrt_minimal():
    """Create a minimal MOGRT file (only manifest, no parameters)."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'minimal.mogrt')
    
    manifest = {
        'templateName': 'Simple Title',
        'parameters': [],
        'requiredFonts': [],
    }
    
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('Manifest.json', json.dumps(manifest))
    
    yield mogrt_path
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def invalid_mogrt_file():
    """Create an invalid MOGRT (no manifest)."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'invalid.mogrt')
    
    # Create ZIP with no manifest
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('SomeFile.txt', 'not a manifest')
    
    yield mogrt_path
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_parse_mogrt_valid(sample_mogrt_file):
    """Test parsing a valid MOGRT file."""
    metadata = parse_mogrt(sample_mogrt_file)
    
    assert metadata is not None
    assert metadata['name'] == 'Cool Title Template'
    assert 'Title' in metadata['parameters']
    assert 'Montserrat' in metadata['required_fonts']
    assert metadata['min_premiere_version'] == '2024.0'
    assert metadata['duration'] == 3.0
    assert metadata['has_preview'] is True


def test_parse_mogrt_minimal(sample_mogrt_minimal):
    """Test parsing a minimal MOGRT file."""
    metadata = parse_mogrt(sample_mogrt_minimal)
    
    assert metadata is not None
    assert metadata['name'] == 'Simple Title'
    assert metadata['parameters'] == []
    assert metadata['required_fonts'] == []


def test_parse_mogrt_invalid(invalid_mogrt_file):
    """Test parsing an invalid MOGRT (no manifest)."""
    metadata = parse_mogrt(invalid_mogrt_file)
    
    assert metadata is None


def test_parse_mogrt_nonexistent():
    """Test parsing a non-existent file."""
    metadata = parse_mogrt('/nonexistent/file.mogrt')
    
    assert metadata is None


def test_parse_mogrt_not_zip():
    """Test parsing a non-ZIP file with .mogrt extension."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'fake.mogrt')
    
    # Write text data (not a valid ZIP)
    with open(mogrt_path, 'w') as f:
        f.write('This is not a ZIP file')
    
    metadata = parse_mogrt(mogrt_path)
    
    assert metadata is None
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_parse_mogrt_corrupted_manifest():
    """Test parsing MOGRT with invalid JSON manifest."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'corrupted.mogrt')
    
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('Manifest.json', 'invalid json {]')
    
    metadata = parse_mogrt(mogrt_path)
    
    assert metadata is None
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_is_mogrt_file_valid(sample_mogrt_file):
    """Test is_mogrt_file with valid MOGRT."""
    assert is_mogrt_file(sample_mogrt_file) is True


def test_is_mogrt_file_invalid(invalid_mogrt_file):
    """Test is_mogrt_file with invalid MOGRT."""
    assert is_mogrt_file(invalid_mogrt_file) is False


def test_is_mogrt_file_wrong_extension():
    """Test is_mogrt_file with wrong extension."""
    assert is_mogrt_file('/path/to/file.zip') is False
    assert is_mogrt_file('/path/to/file.txt') is False


def test_extract_mogrt_fonts(sample_mogrt_file):
    """Test extracting fonts from MOGRT."""
    fonts = extract_mogrt_fonts(sample_mogrt_file)
    
    assert 'Montserrat' in fonts
    assert 'Roboto' in fonts
    assert len(fonts) == 2


def test_extract_mogrt_fonts_empty(sample_mogrt_minimal):
    """Test extracting fonts from MOGRT with no fonts."""
    fonts = extract_mogrt_fonts(sample_mogrt_minimal)
    
    assert fonts == []


def test_extract_mogrt_fonts_invalid():
    """Test extracting fonts from invalid file."""
    fonts = extract_mogrt_fonts('/nonexistent/file.mogrt')
    
    assert fonts == []


def test_batch_parse_mogrt(sample_mogrt_file, sample_mogrt_minimal):
    """Test batch parsing multiple MOGRT files."""
    results = batch_parse_mogrt([sample_mogrt_file, sample_mogrt_minimal])
    
    assert len(results) == 2
    assert results[sample_mogrt_file] is not None
    assert results[sample_mogrt_minimal] is not None


def test_mogrt_to_category_hints(sample_mogrt_file):
    """Test converting MOGRT metadata to category hints."""
    metadata = parse_mogrt(sample_mogrt_file)
    hints = mogrt_to_category_hints(metadata)
    
    assert 'category_signals' in hints
    assert 'confidence' in hints
    assert 'reasoning' in hints
    assert isinstance(hints['category_signals'], list)


def test_mogrt_to_category_hints_title_pattern():
    """Test category hints for title-related template."""
    metadata = {
        'name': 'Cool Lower Third Title Template',
        'parameters': [],
        'required_fonts': [],
    }
    
    hints = mogrt_to_category_hints(metadata)
    
    assert 'Title / Lower Third' in hints['category_signals']
    assert hints['confidence'] > 0


def test_mogrt_to_category_hints_motion_pattern():
    """Test category hints for motion graphics template."""
    metadata = {
        'name': 'Animation Motion Graphic Effect',
        'parameters': [],
        'required_fonts': [],
    }
    
    hints = mogrt_to_category_hints(metadata)
    
    # Should match multiple patterns (motion, animation, graphic)
    assert len(hints['category_signals']) > 0
    assert hints['confidence'] >= 50


def test_mogrt_to_category_hints_empty():
    """Test category hints with no metadata."""
    hints = mogrt_to_category_hints({})
    
    assert hints['category_signals'] == []
    assert hints['confidence'] == 0


def test_mogrt_to_category_hints_no_name():
    """Test category hints with metadata but no name."""
    metadata = {'parameters': ['Param1'], 'required_fonts': []}
    hints = mogrt_to_category_hints(metadata)
    
    assert hints['category_signals'] == []
    assert hints['confidence'] == 0


def test_parse_mogrt_parameters_as_dict():
    """Test parsing MOGRT with parameters as dict instead of list."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'dict_params.mogrt')
    
    manifest = {
        'templateName': 'Dict Parameters Template',
        'parameters': {
            'Title': {'type': 'text'},
            'Color': {'type': 'color'},
        },
    }
    
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('Manifest.json', json.dumps(manifest))
    
    metadata = parse_mogrt(mogrt_path)
    
    assert metadata is not None
    assert 'Title' in metadata['parameters']
    assert 'Color' in metadata['parameters']
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_parse_mogrt_fonts_as_dict():
    """Test parsing MOGRT with fonts as dict instead of list."""
    temp_dir = tempfile.mkdtemp()
    mogrt_path = os.path.join(temp_dir, 'dict_fonts.mogrt')
    
    manifest = {
        'templateName': 'Dict Fonts Template',
        'requiredFonts': {
            'Montserrat': '400',
            'Roboto': '700',
        },
    }
    
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('Manifest.json', json.dumps(manifest))
    
    metadata = parse_mogrt(mogrt_path)
    
    assert metadata is not None
    assert 'Montserrat' in metadata['required_fonts']
    assert 'Roboto' in metadata['required_fonts']
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_parse_mogrt_all_optional_fields(sample_mogrt_file):
    """Test that all optional fields are extracted."""
    metadata = parse_mogrt(sample_mogrt_file)
    
    assert 'version' in metadata
    assert metadata['version'] == '1.0'
    assert 'author' in metadata
    assert metadata['author'] == 'Adobe'
    assert 'description' in metadata
    assert metadata['description'] == 'A cool title template'


def test_parse_mogrt_with_alternative_manifest_names():
    """Test parsing MOGRT with alternative manifest filenames."""
    temp_dir = tempfile.mkdtemp()
    
    # Test with lowercase manifest.json
    mogrt_path = os.path.join(temp_dir, 'lowercase.mogrt')
    manifest = {'templateName': 'Test', 'parameters': []}
    
    with zipfile.ZipFile(mogrt_path, 'w') as zf:
        zf.writestr('manifest.json', json.dumps(manifest))
    
    metadata = parse_mogrt(mogrt_path)
    assert metadata is not None
    assert metadata['name'] == 'Test'
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
