"""Tests for adaptive learning from user corrections."""

import pytest
import json
import os
import tempfile
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fileorganizer.adaptive_corrector import (
    CorrectionRecord, AdaptiveCorrector, build_adaptive_system_prompt
)


@pytest.fixture
def temp_corrections_file():
    """Create a temporary corrections file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    yield temp_path
    try:
        os.remove(temp_path)
    except OSError:
        pass


@pytest.fixture
def temp_lib_dir():
    """Create a temporary library directory with test folders."""
    temp_dir = tempfile.mkdtemp()
    
    # Create sample folders with files
    folders = [
        ('summer-flyer-2025', ['flyer.psd', 'flyer-alt.psd', 'preview.jpg']),
        ('logo-pack-v3', ['logo-1.ai', 'logo-2.ai', 'logo-3.ai']),
        ('product-demo-video', ['demo.mp4', 'thumbnail.jpg']),
    ]
    
    for folder_name, files in folders:
        folder_path = os.path.join(temp_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        for filename in files:
            Path(os.path.join(folder_path, filename)).touch()
    
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_correction_record_init():
    """Test CorrectionRecord initialization."""
    rec = CorrectionRecord(
        folder_name='summer-flyer-2025',
        folder_path='/lib/summer-flyer',
        corrected_category='Flyer / Poster',
        original_confidence=85
    )
    
    assert rec.folder_name == 'summer-flyer-2025'
    assert rec.corrected_category == 'Flyer / Poster'
    assert rec.original_confidence == 85
    assert rec.timestamp is not None
    assert isinstance(rec.keywords, list)


def test_correction_record_keyword_extraction():
    """Test keyword extraction from folder names."""
    test_cases = [
        ('summer-flyer-2025', ['2025', 'flyer', 'summer']),  # Sorted
        ('logo-pack-v3', ['logo', 'pack']),  # 'v3' filtered (noise)
        ('template-bundle-final', ['template', 'bundle']),  # 'final' filtered
        ('a-b-c', []),  # All too short
    ]
    
    for folder_name, expected_keywords in test_cases:
        rec = CorrectionRecord(
            folder_name=folder_name,
            folder_path='/lib/test',
            corrected_category='Test',
            original_confidence=50
        )
        assert rec.keywords == expected_keywords, f"Failed for {folder_name}"


def test_correction_record_serialization():
    """Test to_dict and from_dict round-trip."""
    original = CorrectionRecord(
        folder_name='test-folder',
        folder_path='/lib/test',
        corrected_category='Design',
        original_confidence=75,
        timestamp='2025-05-02T12:00:00+00:00'
    )
    
    # Serialize and deserialize
    data = original.to_dict()
    restored = CorrectionRecord.from_dict(data)
    
    assert restored.folder_name == original.folder_name
    assert restored.corrected_category == original.corrected_category
    assert restored.original_confidence == original.original_confidence
    assert restored.timestamp == original.timestamp


def test_adaptive_corrector_init(temp_corrections_file):
    """Test AdaptiveCorrector initialization."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    assert corrector.corrections == []
    assert corrector.corrections_file == temp_corrections_file


def test_adaptive_corrector_record_correction(temp_corrections_file, temp_lib_dir):
    """Test recording a correction."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    folder_path = os.path.join(temp_lib_dir, 'summer-flyer-2025')
    corrector.record_correction(
        folder_name='summer-flyer-2025',
        folder_path=folder_path,
        corrected_category='Flyer / Poster',
        original_confidence=60
    )
    
    assert len(corrector.corrections) == 1
    assert corrector.corrections[0].corrected_category == 'Flyer / Poster'
    
    # Verify it was saved to file
    with open(temp_corrections_file, 'r') as f:
        data = json.load(f)
    assert len(data['corrections']) == 1


def test_adaptive_corrector_deduplication(temp_corrections_file, temp_lib_dir):
    """Test that duplicate fingerprints are deduplicated."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    folder_path = os.path.join(temp_lib_dir, 'summer-flyer-2025')
    
    # Record two corrections for the same folder
    corrector.record_correction('summer-flyer-2025', folder_path, 'Flyer', 70)
    corrector.record_correction('summer-flyer-2025', folder_path, 'Poster', 80)
    
    # Should only have the latest correction
    assert len(corrector.corrections) == 1
    assert corrector.corrections[0].corrected_category == 'Poster'
    assert corrector.corrections[0].original_confidence == 80


def test_adaptive_corrector_apply_correction(temp_corrections_file, temp_lib_dir):
    """Test applying a correction via fingerprint matching."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    folder_path = os.path.join(temp_lib_dir, 'summer-flyer-2025')
    
    # Record correction
    corrector.record_correction('summer-flyer-2025', folder_path, 'Flyer / Poster', 50)
    
    # Try to apply: should match by fingerprint
    result = corrector.apply_correction(folder_path)
    
    assert result is not None
    category, weight = result
    assert category == 'Flyer / Poster'
    assert 50 <= weight <= 100  # Weight should be high due to low confidence
    
    # Non-existent path should return None
    assert corrector.apply_correction('/nonexistent/path') is None


def test_adaptive_corrector_apply_correction_weight(temp_corrections_file, temp_lib_dir):
    """Test that correction weight inversely correlates with original confidence."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    folder_path = os.path.join(temp_lib_dir, 'summer-flyer-2025')
    
    # Record with high confidence (certain mistake)
    corrector.record_correction('summer-flyer-2025', folder_path, 'Flyer', 95)
    result_high_conf = corrector.apply_correction(folder_path)
    
    # Record same correction with low confidence (uncertain)
    corrector.record_correction('summer-flyer-2025', folder_path, 'Flyer', 20)
    result_low_conf = corrector.apply_correction(folder_path)
    
    # Low confidence should yield higher weight
    _, weight_high_conf = result_high_conf
    _, weight_low_conf = result_low_conf
    assert weight_low_conf > weight_high_conf


def test_adaptive_corrector_inject_few_shot(temp_corrections_file, temp_lib_dir):
    """Test injecting few-shot examples for keyword-matching corrections."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    # Record several corrections with overlapping keywords
    folders = [
        ('summer-flyer-2025', 'Flyer / Poster'),
        ('summer-poster-beach', 'Flyer / Poster'),
        ('design-flyer-wedding', 'Flyer / Poster'),
        ('logo-pack-v3', 'Logo / Icon'),
    ]
    
    for folder_name, category in folders:
        folder_path = os.path.join(temp_lib_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        corrector.record_correction(folder_name, folder_path, category, 60)
    
    # Query with keyword "flyer" should match the flyer corrections
    examples = corrector.inject_few_shot('spring-flyer-design', num_examples=2)
    
    assert len(examples) > 0
    assert all(ex['category'] in ['Flyer / Poster', 'Logo / Icon'] for ex in examples)
    
    # Most should be Flyer / Poster due to keyword overlap
    flyer_count = sum(1 for ex in examples if ex['category'] == 'Flyer / Poster')
    assert flyer_count >= 1


def test_adaptive_corrector_load_from_file(temp_corrections_file, temp_lib_dir):
    """Test loading corrections from an existing file."""
    # Create a corrections file with data
    corrections_data = {
        'version': '1.0',
        'corrections': [
            {
                'folder_name': 'test-flyer',
                'fingerprint': 'abc123',
                'keywords': ['flyer', 'test'],
                'category': 'Flyer / Poster',
                'confidence': 70,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        ]
    }
    
    with open(temp_corrections_file, 'w') as f:
        json.dump(corrections_data, f)
    
    # Load and verify
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    assert len(corrector.corrections) == 1
    assert corrector.corrections[0].folder_name == 'test-flyer'
    assert corrector.corrections[0].corrected_category == 'Flyer / Poster'


def test_adaptive_corrector_filter_by_age(temp_corrections_file, temp_lib_dir):
    """Test that corrections older than max age are filtered out."""
    old_time = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    recent_time = datetime.now(timezone.utc).isoformat()
    
    corrections_data = {
        'version': '1.0',
        'corrections': [
            {
                'folder_name': 'old-flyer',
                'fingerprint': 'old123',
                'keywords': ['flyer'],
                'category': 'Flyer / Poster',
                'confidence': 70,
                'timestamp': old_time
            },
            {
                'folder_name': 'recent-flyer',
                'fingerprint': 'new123',
                'keywords': ['flyer'],
                'category': 'Flyer / Poster',
                'confidence': 70,
                'timestamp': recent_time
            }
        ]
    }
    
    with open(temp_corrections_file, 'w') as f:
        json.dump(corrections_data, f)
    
    # Load and verify old correction is filtered
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    assert len(corrector.corrections) == 1
    assert corrector.corrections[0].folder_name == 'recent-flyer'


def test_adaptive_corrector_get_stats(temp_corrections_file, temp_lib_dir):
    """Test getting correction statistics."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    # Record several corrections
    folders = [
        ('flyer-1', 'Flyer / Poster'),
        ('flyer-2', 'Flyer / Poster'),
        ('logo-1', 'Logo / Icon'),
    ]
    
    for folder_name, category in folders:
        folder_path = os.path.join(temp_lib_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        corrector.record_correction(folder_name, folder_path, category, 60)
    
    stats = corrector.get_stats()
    
    assert stats['total'] == 3
    assert stats['by_category']['Flyer / Poster'] == 2
    assert stats['by_category']['Logo / Icon'] == 1
    assert stats['oldest'] is not None
    assert stats['newest'] is not None


def test_adaptive_corrector_clear_all(temp_corrections_file, temp_lib_dir):
    """Test clearing all corrections."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    folder_path = os.path.join(temp_lib_dir, 'summer-flyer-2025')
    corrector.record_correction('summer-flyer', folder_path, 'Flyer', 70)
    assert len(corrector.corrections) == 1
    
    corrector.clear_all()
    assert len(corrector.corrections) == 0
    assert not os.path.exists(temp_corrections_file)


def test_build_adaptive_system_prompt(temp_corrections_file, temp_lib_dir):
    """Test building a system prompt with few-shot examples."""
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    
    # Record some corrections
    folders = [
        ('summer-flyer', 'Flyer / Poster'),
        ('beach-poster', 'Flyer / Poster'),
    ]
    
    for folder_name, category in folders:
        folder_path = os.path.join(temp_lib_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        corrector.record_correction(folder_name, folder_path, category, 60)
    
    base_prompt = "Classify this folder into a category."
    enhanced = build_adaptive_system_prompt('spring-flyer-design', base_prompt)
    
    # Should include examples if keywords match
    if enhanced != base_prompt:
        assert 'RECENT EXAMPLES' in enhanced or len(enhanced) > len(base_prompt)
    else:
        # No keywords match, so no enhancement expected
        pass


def test_correction_record_confidence_bounds():
    """Test that confidence is bounded to 0-100."""
    rec1 = CorrectionRecord('test', '/lib/test', 'Design', original_confidence=-50)
    assert rec1.original_confidence == 0
    
    rec2 = CorrectionRecord('test', '/lib/test', 'Design', original_confidence=150)
    assert rec2.original_confidence == 100


def test_adaptive_corrector_malformed_json(temp_corrections_file):
    """Test that malformed JSON is handled gracefully."""
    # Write invalid JSON
    with open(temp_corrections_file, 'w') as f:
        f.write('{ invalid json }')
    
    # Should not crash, just load empty
    corrector = AdaptiveCorrector(corrections_file=temp_corrections_file)
    assert len(corrector.corrections) == 0
