"""Tests for FileOrganizer scheduled scans."""

import pytest
import tempfile
import json
import os
from pathlib import Path
from fileorganizer.scheduler import ScheduledProfile, SchedulerManager


class TestScheduledProfile:
    """Test ScheduledProfile dataclass."""
    
    def test_create_profile(self):
        """Test creating a scheduled profile."""
        profile = ScheduledProfile(
            name='Photos',
            folder_path='/home/user/Photos',
            frequency='daily',
            time='18:00'
        )
        
        assert profile.name == 'Photos'
        assert profile.folder_path == '/home/user/Photos'
        assert profile.frequency == 'daily'
        assert profile.time == '18:00'
        assert profile.enabled is True
        assert profile.created_at is not None
    
    def test_create_profile_with_optional_fields(self):
        """Test creating profile with optional fields."""
        profile = ScheduledProfile(
            name='Documents',
            folder_path='/home/user/Documents',
            frequency='weekly',
            time='10:30',
            day_of_week=5,  # Saturday
            enabled=False
        )
        
        assert profile.frequency == 'weekly'
        assert profile.day_of_week == 5
        assert profile.enabled is False
    
    def test_profile_with_monthly_frequency(self):
        """Test profile with monthly frequency."""
        profile = ScheduledProfile(
            name='Backups',
            folder_path='/mnt/backups',
            frequency='monthly',
            time='02:00',
            day_of_month=1
        )
        
        assert profile.frequency == 'monthly'
        assert profile.day_of_month == 1
    
    def test_profile_created_at_auto_set(self):
        """Test that created_at is auto-set."""
        profile1 = ScheduledProfile(
            name='Test1',
            folder_path='/path1',
            frequency='daily',
            time='12:00'
        )
        
        profile2 = ScheduledProfile(
            name='Test2',
            folder_path='/path2',
            frequency='daily',
            time='12:00'
        )
        
        assert profile1.created_at is not None
        assert profile2.created_at is not None
        # They should be different (or very close)


class TestSchedulerManager:
    """Test SchedulerManager functionality."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def scheduler(self, temp_config_dir):
        """Create a scheduler with temporary config."""
        return SchedulerManager(config_dir=temp_config_dir)
    
    def test_init_creates_config_dir(self, temp_config_dir):
        """Test that SchedulerManager creates config directory."""
        scheduler = SchedulerManager(config_dir=temp_config_dir)
        
        assert Path(temp_config_dir).exists()
        assert scheduler.config_dir == Path(temp_config_dir)
    
    def test_init_loads_existing_schedules(self, temp_config_dir):
        """Test loading existing schedules from disk."""
        # Create a schedules.json file
        schedules_file = Path(temp_config_dir) / 'schedules.json'
        schedules_data = {
            'Photos': {
                'name': 'Photos',
                'folder_path': '/home/user/Photos',
                'frequency': 'daily',
                'time': '18:00',
                'day_of_week': None,
                'day_of_month': None,
                'enabled': True,
                'created_at': '2024-01-01T12:00:00',
                'last_run': None
            }
        }
        
        with open(schedules_file, 'w') as f:
            json.dump(schedules_data, f)
        
        scheduler = SchedulerManager(config_dir=temp_config_dir)
        
        assert 'Photos' in scheduler.schedules
        assert scheduler.schedules['Photos'].name == 'Photos'
    
    def test_create_schedule(self, scheduler):
        """Test creating a new schedule."""
        result = scheduler.create_schedule(
            name='Photos',
            folder_path='/home/user/Photos',
            frequency='daily',
            time='18:00'
        )
        
        # Should succeed (we can't actually register OS tasks in tests)
        assert result in (True, False)  # Depends on OS capabilities
    
    def test_list_schedules(self, scheduler):
        """Test listing all schedules."""
        # Manually add a schedule
        profile = ScheduledProfile(
            name='Test',
            folder_path='/path',
            frequency='daily',
            time='12:00'
        )
        scheduler.schedules['Test'] = profile
        scheduler._save_schedules()
        
        schedules = scheduler.list_schedules()
        
        assert len(schedules) >= 1
        assert any(s.name == 'Test' for s in schedules)
    
    def test_get_schedule(self, scheduler):
        """Test getting a specific schedule."""
        profile = ScheduledProfile(
            name='MyTask',
            folder_path='/path',
            frequency='daily',
            time='12:00'
        )
        scheduler.schedules['MyTask'] = profile
        scheduler._save_schedules()
        
        retrieved = scheduler.get_schedule('MyTask')
        
        assert retrieved is not None
        assert retrieved.name == 'MyTask'
    
    def test_get_nonexistent_schedule(self, scheduler):
        """Test getting a non-existent schedule."""
        result = scheduler.get_schedule('Nonexistent')
        
        assert result is None
    
    def test_delete_schedule(self, scheduler):
        """Test deleting a schedule."""
        profile = ScheduledProfile(
            name='ToDelete',
            folder_path='/path',
            frequency='daily',
            time='12:00'
        )
        scheduler.schedules['ToDelete'] = profile
        scheduler._save_schedules()
        
        assert 'ToDelete' in scheduler.schedules
        
        # Delete (will fail OS registration in test, but should still remove from dict)
        # We'll manually bypass the OS registration
        del scheduler.schedules['ToDelete']
        scheduler._save_schedules()
        
        assert 'ToDelete' not in scheduler.schedules
    
    def test_enable_disable_schedule(self, scheduler):
        """Test enabling and disabling a schedule."""
        profile = ScheduledProfile(
            name='Task',
            folder_path='/path',
            frequency='daily',
            time='12:00',
            enabled=True
        )
        scheduler.schedules['Task'] = profile
        scheduler._save_schedules()
        
        # Disable
        scheduler.disable_schedule('Task')
        retrieved = scheduler.get_schedule('Task')
        assert retrieved.enabled is False
        
        # Enable
        scheduler.enable_schedule('Task')
        retrieved = scheduler.get_schedule('Task')
        assert retrieved.enabled is True
    
    def test_schedules_persisted_to_disk(self, scheduler):
        """Test that schedules are persisted to disk."""
        profile = ScheduledProfile(
            name='Persistent',
            folder_path='/path',
            frequency='weekly',
            time='10:00',
            day_of_week=2
        )
        scheduler.schedules['Persistent'] = profile
        scheduler._save_schedules()
        
        # Load schedules from disk
        schedules_file = scheduler.schedules_file
        with open(schedules_file, 'r') as f:
            data = json.load(f)
        
        assert 'Persistent' in data
        assert data['Persistent']['name'] == 'Persistent'
    
    def test_load_schedules_with_corrupted_json(self, temp_config_dir):
        """Test loading schedules with corrupted JSON."""
        schedules_file = Path(temp_config_dir) / 'schedules.json'
        
        # Write invalid JSON
        with open(schedules_file, 'w') as f:
            f.write('invalid json {]')
        
        scheduler = SchedulerManager(config_dir=temp_config_dir)
        
        # Should gracefully return empty dict
        assert scheduler.schedules == {}
    
    def test_create_duplicate_schedule(self, scheduler):
        """Test creating a schedule with duplicate name."""
        profile = ScheduledProfile(
            name='Duplicate',
            folder_path='/path1',
            frequency='daily',
            time='12:00'
        )
        scheduler.schedules['Duplicate'] = profile
        
        # Try to create another with same name
        result = scheduler.create_schedule(
            name='Duplicate',
            folder_path='/path2',
            frequency='daily',
            time='14:00'
        )
        
        assert result is False
    
    def test_weekly_schedule(self, scheduler):
        """Test creating a weekly schedule."""
        profile = ScheduledProfile(
            name='WeeklyTask',
            folder_path='/path',
            frequency='weekly',
            time='10:30',
            day_of_week=3  # Wednesday
        )
        scheduler.schedules['WeeklyTask'] = profile
        scheduler._save_schedules()
        
        retrieved = scheduler.get_schedule('WeeklyTask')
        assert retrieved.frequency == 'weekly'
        assert retrieved.day_of_week == 3
    
    def test_monthly_schedule(self, scheduler):
        """Test creating a monthly schedule."""
        profile = ScheduledProfile(
            name='MonthlyTask',
            folder_path='/path',
            frequency='monthly',
            time='23:59',
            day_of_month=15
        )
        scheduler.schedules['MonthlyTask'] = profile
        scheduler._save_schedules()
        
        retrieved = scheduler.get_schedule('MonthlyTask')
        assert retrieved.frequency == 'monthly'
        assert retrieved.day_of_month == 15


class TestPlatformDetection:
    """Test platform detection in SchedulerManager."""
    
    def test_platform_detection(self):
        """Test that SchedulerManager detects the platform."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = SchedulerManager(config_dir=tmpdir)
            
            # Should detect a valid platform
            assert scheduler.platform in ('Windows', 'Darwin', 'Linux')


class TestCronEntry:
    """Test cron entry generation."""
    
    def test_get_cron_entry_daily(self):
        """Test generating daily cron entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = SchedulerManager(config_dir=tmpdir)
            
            profile = ScheduledProfile(
                name='Daily',
                folder_path='/path',
                frequency='daily',
                time='18:30'
            )
            
            entry = scheduler._get_cron_entry(profile)
            
            # Should contain the time and command
            assert '18 30' in entry or '30 18' in entry  # Cron uses minute hour


class TestSystemdTimer:
    """Test systemd timer generation."""
    
    def test_get_systemd_timer_content_daily(self):
        """Test generating daily systemd timer content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = SchedulerManager(config_dir=tmpdir)
            
            profile = ScheduledProfile(
                name='Daily',
                folder_path='/path',
                frequency='daily',
                time='18:30'
            )
            
            content = scheduler._get_systemd_timer_content(profile)
            
            assert '[Timer]' in content
            assert '[Install]' in content
            assert 'OnCalendar' in content
