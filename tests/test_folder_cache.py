"""Tests for FileOrganizer folder_cache module."""
import os
import time
import sqlite3
import tempfile
import pytest
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fileorganizer import folder_cache as fc


class TestComputeFolderFingerprint:
    """Tests for fingerprint computation."""

    def test_fingerprint_same_folder_same_hash(self, tmp_path):
        """Same folder contents should produce same fingerprint."""
        # Create test files
        (tmp_path / 'file1.txt').write_text('content1')
        (tmp_path / 'file2.txt').write_text('content2')

        # Compute fingerprint twice
        fp1 = fc.compute_folder_fingerprint(str(tmp_path))
        time.sleep(0.1)
        fp2 = fc.compute_folder_fingerprint(str(tmp_path))

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA256 hex digest

    def test_fingerprint_different_files_different_hash(self, tmp_path):
        """Different files should produce different fingerprints."""
        # Create first set
        (tmp_path / 'file1.txt').write_text('content1')
        fp1 = fc.compute_folder_fingerprint(str(tmp_path))

        # Add another file
        (tmp_path / 'file2.txt').write_text('content2')
        fp2 = fc.compute_folder_fingerprint(str(tmp_path))

        assert fp1 != fp2

    def test_fingerprint_file_deletion_changes_hash(self, tmp_path):
        """Deleting a file should change fingerprint."""
        file1 = tmp_path / 'file1.txt'
        file2 = tmp_path / 'file2.txt'
        file1.write_text('content1')
        file2.write_text('content2')

        fp1 = fc.compute_folder_fingerprint(str(tmp_path))

        file1.unlink()
        fp2 = fc.compute_folder_fingerprint(str(tmp_path))

        assert fp1 != fp2

    def test_fingerprint_file_rename_changes_hash(self, tmp_path):
        """Renaming a file should change fingerprint."""
        file1 = tmp_path / 'old_name.txt'
        file1.write_text('content')

        fp1 = fc.compute_folder_fingerprint(str(tmp_path))

        file1.rename(tmp_path / 'new_name.txt')
        fp2 = fc.compute_folder_fingerprint(str(tmp_path))

        assert fp1 != fp2

    def test_fingerprint_empty_folder(self, tmp_path):
        """Empty folder should have valid fingerprint."""
        fp = fc.compute_folder_fingerprint(str(tmp_path))

        assert len(fp) == 64
        assert fp == fc.compute_folder_fingerprint(str(tmp_path))

    def test_fingerprint_nonexistent_folder(self):
        """Nonexistent folder should return empty string."""
        fp = fc.compute_folder_fingerprint('/nonexistent/folder')

        assert fp == ""


class TestFolderCache:
    """Tests for FolderCache class."""

    def test_cache_initialization(self, tmp_path):
        """FolderCache should create schema on init."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))

        # Check table exists
        db = sqlite3.connect(str(db_path))
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='folder_cache'"
        )
        assert cursor.fetchone() is not None
        db.close()

    def test_cache_set_and_get(self, tmp_path):
        """Cache should store and retrieve fingerprints."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        cache.set(folder, 'abc123def456')

        result = cache.get(folder)

        assert result is not None
        assert result['fingerprint'] == 'abc123def456'

    def test_cache_expiration(self, tmp_path):
        """Cache entries should expire after TTL."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        # Set with short TTL
        cache.set(folder, 'abc123', ttl_seconds=1)
        time.sleep(1.1)

        # Should be expired
        result = cache.get(folder)

        assert result is None

    def test_is_cached_and_valid_match(self, tmp_path):
        """is_cached_and_valid should return True for matching fingerprint."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        cache.set(folder, 'abc123')

        is_valid = cache.is_cached_and_valid(folder, 'abc123')

        assert is_valid

    def test_is_cached_and_valid_mismatch(self, tmp_path):
        """is_cached_and_valid should return False for different fingerprint."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        cache.set(folder, 'abc123')

        is_valid = cache.is_cached_and_valid(folder, 'xyz789')

        assert not is_valid

    def test_cache_invalidate(self, tmp_path):
        """Invalidate should remove cache entry."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        cache.set(folder, 'abc123')
        cache.invalidate(folder)

        result = cache.get(folder)

        assert result is None

    def test_cache_invalidate_all(self, tmp_path):
        """Invalidate_all should clear entire cache."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))

        # Create multiple cache entries
        for i in range(5):
            folder = str(tmp_path / f'folder_{i}')
            os.makedirs(folder, exist_ok=True)
            cache.set(folder, f'fp_{i}')

        cache.invalidate_all()

        # All should be gone
        for i in range(5):
            folder = str(tmp_path / f'folder_{i}')
            assert cache.get(folder) is None

    def test_cache_cleanup_expired(self, tmp_path):
        """Cleanup should remove expired entries."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))

        # Create entry with short TTL
        folder1 = str(tmp_path / 'folder1')
        os.makedirs(folder1)
        cache.set(folder1, 'fp1', ttl_seconds=1)

        # Create entry with long TTL
        folder2 = str(tmp_path / 'folder2')
        os.makedirs(folder2)
        cache.set(folder2, 'fp2', ttl_seconds=3600)

        time.sleep(1.1)
        cache.cleanup_expired()

        # First should be gone, second should remain
        assert cache.get(folder1) is None
        assert cache.get(folder2) is not None

    def test_cache_get_stats(self, tmp_path):
        """Get_stats should return cache statistics."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))

        # Create entries
        for i in range(3):
            folder = str(tmp_path / f'folder_{i}')
            os.makedirs(folder, exist_ok=True)
            cache.set(folder, f'fp_{i}')

        stats = cache.get_stats()

        assert stats['total_entries'] == 3
        assert stats['valid_entries'] == 3
        assert stats['expired_entries'] == 0


class TestShouldSkipFolder:
    """Tests for should_skip_folder function."""

    def test_skip_folder_on_cache_hit(self, tmp_path):
        """Folder should be skipped if fingerprint cached and valid."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        # Create test file
        (tmp_path / 'test_folder' / 'file.txt').write_text('content')

        # First call: computes and caches fingerprint
        should_skip1, reason1 = fc.should_skip_folder(folder, cache)
        assert not should_skip1
        assert 'not cached' in reason1.lower()

        # Second call: should skip (fingerprint unchanged)
        should_skip2, reason2 = fc.should_skip_folder(folder, cache)
        assert should_skip2
        assert 'unchanged' in reason2.lower()

    def test_dont_skip_folder_on_content_change(self, tmp_path):
        """Folder should not be skipped if content changes."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))
        folder = str(tmp_path / 'test_folder')
        os.makedirs(folder)

        # Create test file
        (tmp_path / 'test_folder' / 'file.txt').write_text('content')

        # First call
        should_skip1, _ = fc.should_skip_folder(folder, cache)
        assert not should_skip1

        # Add another file
        (tmp_path / 'test_folder' / 'file2.txt').write_text('content2')

        # Second call: should not skip (fingerprint changed)
        should_skip2, reason2 = fc.should_skip_folder(folder, cache)
        assert not should_skip2
        assert 'changed' in reason2.lower()


class TestIntegration:
    """Integration tests."""

    def test_typical_workflow(self, tmp_path):
        """Typical usage: cache hits reduce re-scan cost."""
        db_path = tmp_path / 'test.db'
        cache = fc.FolderCache(str(db_path))

        # Simulate scanning multiple folders
        folders = []
        for i in range(5):
            folder = str(tmp_path / f'folder_{i}')
            os.makedirs(folder)
            (Path(folder) / 'file.txt').write_text('content')
            folders.append(folder)

        # First pass: all folders are new (not cached)
        skip_count_1 = sum(
            1 for folder in folders
            if fc.should_skip_folder(folder, cache)[0]
        )
        assert skip_count_1 == 0

        # Second pass: all folders should be skipped
        skip_count_2 = sum(
            1 for folder in folders
            if fc.should_skip_folder(folder, cache)[0]
        )
        assert skip_count_2 == 5

        # Modify one folder
        (Path(folders[0]) / 'new_file.txt').write_text('new')

        # Modified folder should not be skipped
        should_skip, _ = fc.should_skip_folder(folders[0], cache)
        assert not should_skip

        # Others should still be skipped
        for folder in folders[1:]:
            should_skip, _ = fc.should_skip_folder(folder, cache)
            assert should_skip


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
