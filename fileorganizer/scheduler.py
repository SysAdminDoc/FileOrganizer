"""FileOrganizer — Scheduled scans for automation profiles.

Cross-platform scheduler:
- Windows: Task Scheduler (taskschd.com via pywin32 or direct XML)
- macOS: launchd plist + ~/Library/LaunchAgents/
- Linux: systemd user timer or cron

Design:
- ScheduledProfile: Profile name, folder path, schedule (daily/weekly/monthly/cron), enabled state
- SchedulerManager: Create/delete/enable/disable scheduled tasks
- Platform detection + fallback to cron if systemd unavailable

Example:
  scheduler = SchedulerManager()
  scheduler.create_schedule(
    profile='Photos',
    folder='/path/to/photos',
    frequency='daily',
    time='18:00',  # 6 PM
  )
"""

import os
import sys
import json
import subprocess
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, time
import platform


@dataclass
class ScheduledProfile:
    """A scheduled file organization task."""
    name: str
    folder_path: str
    frequency: str  # 'daily', 'weekly', 'monthly', or cron expression
    time: str  # HH:MM (24-hour format)
    day_of_week: Optional[int] = None  # 0-6 (Mon-Sun), for weekly
    day_of_month: Optional[int] = None  # 1-31, for monthly
    enabled: bool = True
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class SchedulerManager:
    """Manage scheduled file organization tasks across platforms."""
    
    def __init__(self, config_dir: Optional[str] = None):
        """Initialize scheduler manager.
        
        Args:
            config_dir: Directory to store schedule configs. Defaults to ~/.fileorganizer/schedules/
        """
        if config_dir is None:
            home = Path.home()
            config_dir = str(home / '.fileorganizer' / 'schedules')
        
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.schedules_file = self.config_dir / 'schedules.json'
        self.platform = platform.system()
        self.schedules: Dict[str, ScheduledProfile] = self._load_schedules()
    
    def _load_schedules(self) -> Dict[str, ScheduledProfile]:
        """Load schedules from disk."""
        if not self.schedules_file.exists():
            return {}
        
        try:
            with open(self.schedules_file, 'r') as f:
                data = json.load(f)
            
            schedules = {}
            for name, profile_data in data.items():
                schedules[name] = ScheduledProfile(**profile_data)
            return schedules
        except (json.JSONDecodeError, Exception):
            return {}
    
    def _save_schedules(self):
        """Save schedules to disk."""
        data = {name: asdict(profile) for name, profile in self.schedules.items()}
        
        with open(self.schedules_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_schedule(self,
                       name: str,
                       folder_path: str,
                       frequency: str,
                       time: str,
                       day_of_week: Optional[int] = None,
                       day_of_month: Optional[int] = None) -> bool:
        """Create a new scheduled task.
        
        Args:
            name: Profile name (must be unique)
            folder_path: Directory to organize
            frequency: 'daily', 'weekly', 'monthly', or cron expression
            time: Time as HH:MM (24-hour format)
            day_of_week: 0-6 (Monday-Sunday) for weekly schedules
            day_of_month: 1-31 for monthly schedules
        
        Returns:
            True if successful, False otherwise
        """
        if name in self.schedules:
            return False
        
        profile = ScheduledProfile(
            name=name,
            folder_path=folder_path,
            frequency=frequency,
            time=time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
        )
        
        # Register with OS scheduler
        if not self._register_os_task(profile):
            return False
        
        self.schedules[name] = profile
        self._save_schedules()
        return True
    
    def delete_schedule(self, name: str) -> bool:
        """Delete a scheduled task.
        
        Args:
            name: Profile name
        
        Returns:
            True if successful, False otherwise
        """
        if name not in self.schedules:
            return False
        
        profile = self.schedules[name]
        
        # Unregister from OS scheduler
        if not self._unregister_os_task(profile):
            return False
        
        del self.schedules[name]
        self._save_schedules()
        return True
    
    def enable_schedule(self, name: str) -> bool:
        """Enable a scheduled task."""
        if name not in self.schedules:
            return False
        
        profile = self.schedules[name]
        profile.enabled = True
        self._save_schedules()
        
        # Enable in OS scheduler
        return self._set_os_task_enabled(profile, True)
    
    def disable_schedule(self, name: str) -> bool:
        """Disable a scheduled task."""
        if name not in self.schedules:
            return False
        
        profile = self.schedules[name]
        profile.enabled = False
        self._save_schedules()
        
        # Disable in OS scheduler
        return self._set_os_task_enabled(profile, False)
    
    def list_schedules(self) -> List[ScheduledProfile]:
        """List all scheduled tasks."""
        return list(self.schedules.values())
    
    def get_schedule(self, name: str) -> Optional[ScheduledProfile]:
        """Get a specific scheduled task."""
        return self.schedules.get(name)
    
    def _register_os_task(self, profile: ScheduledProfile) -> bool:
        """Register task with the OS scheduler."""
        if self.platform == 'Windows':
            return self._register_windows_task(profile)
        elif self.platform == 'Darwin':
            return self._register_macos_task(profile)
        else:
            return self._register_linux_task(profile)
    
    def _unregister_os_task(self, profile: ScheduledProfile) -> bool:
        """Unregister task from the OS scheduler."""
        if self.platform == 'Windows':
            return self._unregister_windows_task(profile)
        elif self.platform == 'Darwin':
            return self._unregister_macos_task(profile)
        else:
            return self._unregister_linux_task(profile)
    
    def _set_os_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        """Enable or disable task in OS scheduler."""
        if self.platform == 'Windows':
            return self._set_windows_task_enabled(profile, enabled)
        elif self.platform == 'Darwin':
            return self._set_macos_task_enabled(profile, enabled)
        else:
            return self._set_linux_task_enabled(profile, enabled)
    
    # Windows Task Scheduler implementation
    
    def _register_windows_task(self, profile: ScheduledProfile) -> bool:
        """Register a Windows Task Scheduler task."""
        try:
            import win32com.client
        except ImportError:
            # Fallback to schtasks.exe
            return self._register_windows_task_schtasks(profile)
        
        try:
            scheduler = win32com.client.Dispatch('Schedule.Service')
            scheduler.Connect()
            
            root_folder = scheduler.GetFolder('\\')
            
            # Create task definition
            task_def = scheduler.NewTask(0)
            task_def.RegistrationInfo.Description = f'FileOrganizer: {profile.name}'
            
            # Set trigger
            trigger = task_def.Triggers.Create(1)  # 1 = daily trigger
            trigger.StartBoundary = f'2000-01-01T{profile.time}:00'
            trigger.Enabled = profile.enabled
            
            if profile.frequency == 'weekly' and profile.day_of_week is not None:
                trigger.DaysOfWeek = 1 << profile.day_of_week
            elif profile.frequency == 'monthly' and profile.day_of_month is not None:
                trigger.DayOfMonth = profile.day_of_month
            
            # Set action (command to run)
            action = task_def.Actions.Create(0)  # 0 = exec action
            action.Path = sys.executable
            action.Arguments = f'-m fileorganizer.cli organize --folder "{profile.folder_path}"'
            
            # Register task
            root_folder.RegisterTaskDefinition(
                f'FileOrganizer\\{profile.name}',
                task_def,
                6,  # TASK_CREATE_OR_UPDATE
                None,
                None,
                3,  # TASK_LOGON_SERVICE_ACCOUNT
            )
            
            return True
        except Exception:
            return False
    
    def _register_windows_task_schtasks(self, profile: ScheduledProfile) -> bool:
        """Register Windows Task Scheduler task using schtasks.exe."""
        try:
            # Schedule types
            schedule_type = '/SC'
            if profile.frequency == 'daily':
                sched_str = 'DAILY'
            elif profile.frequency == 'weekly':
                sched_str = 'WEEKLY'
            elif profile.frequency == 'monthly':
                sched_str = 'MONTHLY'
            else:
                return False
            
            cmd = [
                'schtasks', '/create',
                '/TN', f'FileOrganizer\\{profile.name}',
                '/SC', sched_str,
                '/ST', profile.time,
                '/TR', f'python -m fileorganizer.cli organize --folder "{profile.folder_path}"',
                '/F'  # Force overwrite
            ]
            
            if profile.frequency == 'weekly' and profile.day_of_week is not None:
                days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
                cmd.extend(['/D', days[profile.day_of_week]])
            elif profile.frequency == 'monthly' and profile.day_of_month is not None:
                cmd.extend(['/D', str(profile.day_of_month)])
            
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except Exception:
            return False
    
    def _unregister_windows_task(self, profile: ScheduledProfile) -> bool:
        """Unregister a Windows Task Scheduler task."""
        try:
            subprocess.run(
                ['schtasks', '/delete', '/TN', f'FileOrganizer\\{profile.name}', '/F'],
                check=True,
                capture_output=True
            )
            return True
        except Exception:
            return False
    
    def _set_windows_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        """Enable or disable a Windows task."""
        try:
            action = '/enable' if enabled else '/disable'
            subprocess.run(
                ['schtasks', action, '/TN', f'FileOrganizer\\{profile.name}'],
                check=True,
                capture_output=True
            )
            return True
        except Exception:
            return False
    
    # macOS launchd implementation
    
    def _register_macos_task(self, profile: ScheduledProfile) -> bool:
        """Register a launchd task on macOS."""
        try:
            import plistlib
        except ImportError:
            return False
        
        try:
            agents_dir = Path.home() / 'Library' / 'LaunchAgents'
            agents_dir.mkdir(parents=True, exist_ok=True)
            
            plist_path = agents_dir / f'com.fileorganizer.{profile.name}.plist'
            
            # Parse time
            hour, minute = map(int, profile.time.split(':'))
            
            plist_dict = {
                'Label': f'com.fileorganizer.{profile.name}',
                'ProgramArguments': [
                    sys.executable,
                    '-m', 'fileorganizer.cli',
                    'organize',
                    '--folder', profile.folder_path
                ],
                'StartCalendarInterval': self._get_launchd_interval(profile, hour, minute),
                'RunAtLoad': profile.enabled,
            }
            
            with open(plist_path, 'wb') as f:
                plistlib.dump(plist_dict, f)
            
            # Load the agent
            subprocess.run(['launchctl', 'load', str(plist_path)], capture_output=True)
            
            return True
        except Exception:
            return False
    
    def _get_launchd_interval(self, profile: ScheduledProfile, hour: int, minute: int) -> List[Dict]:
        """Get StartCalendarInterval dict for launchd."""
        base = {'Hour': hour, 'Minute': minute}
        
        if profile.frequency == 'daily':
            return [base]
        elif profile.frequency == 'weekly' and profile.day_of_week is not None:
            return [{**base, 'Weekday': profile.day_of_week if profile.day_of_week > 0 else 7}]
        elif profile.frequency == 'monthly' and profile.day_of_month is not None:
            return [{**base, 'Day': profile.day_of_month}]
        else:
            return [base]
    
    def _unregister_macos_task(self, profile: ScheduledProfile) -> bool:
        """Unregister a launchd task."""
        try:
            agents_dir = Path.home() / 'Library' / 'LaunchAgents'
            plist_path = agents_dir / f'com.fileorganizer.{profile.name}.plist'
            
            # Unload the agent
            subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)
            
            # Remove the plist file
            if plist_path.exists():
                plist_path.unlink()
            
            return True
        except Exception:
            return False
    
    def _set_macos_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        """Enable or disable a launchd task."""
        try:
            agents_dir = Path.home() / 'Library' / 'LaunchAgents'
            plist_path = agents_dir / f'com.fileorganizer.{profile.name}.plist'
            
            if enabled:
                subprocess.run(['launchctl', 'load', str(plist_path)], capture_output=True)
            else:
                subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)
            
            return True
        except Exception:
            return False
    
    # Linux systemd/cron implementation
    
    def _register_linux_task(self, profile: ScheduledProfile) -> bool:
        """Register a systemd user timer on Linux."""
        # Try systemd first, fall back to cron
        if self._register_linux_systemd_timer(profile):
            return True
        return self._register_linux_cron(profile)
    
    def _register_linux_systemd_timer(self, profile: ScheduledProfile) -> bool:
        """Register a systemd user timer."""
        try:
            config_dir = Path.home() / '.config' / 'systemd' / 'user'
            config_dir.mkdir(parents=True, exist_ok=True)
            
            timer_file = config_dir / f'fileorganizer-{profile.name}.timer'
            service_file = config_dir / f'fileorganizer-{profile.name}.service'
            
            # Create service file
            service_content = f"""[Unit]
Description=FileOrganizer {profile.name}

[Service]
Type=oneshot
ExecStart={sys.executable} -m fileorganizer.cli organize --folder {profile.folder_path}
"""
            with open(service_file, 'w') as f:
                f.write(service_content)
            
            # Create timer file
            timer_content = self._get_systemd_timer_content(profile)
            with open(timer_file, 'w') as f:
                f.write(timer_content)
            
            # Reload and enable timer
            subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
            subprocess.run(['systemctl', '--user', 'enable', f'fileorganizer-{profile.name}.timer'], capture_output=True)
            subprocess.run(['systemctl', '--user', 'start', f'fileorganizer-{profile.name}.timer'], capture_output=True)
            
            return True
        except Exception:
            return False
    
    def _get_systemd_timer_content(self, profile: ScheduledProfile) -> str:
        """Generate systemd timer content."""
        content = f"""[Unit]
Description=FileOrganizer {profile.name} Timer

[Timer]
"""
        
        hour, minute = profile.time.split(':')
        
        if profile.frequency == 'daily':
            content += f'OnCalendar=daily\nOnCalendar=*-*-* {hour}:{minute}:00\n'
        elif profile.frequency == 'weekly' and profile.day_of_week is not None:
            days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            content += f'OnCalendar={days[profile.day_of_week]} {hour}:{minute}:00\n'
        elif profile.frequency == 'monthly' and profile.day_of_month is not None:
            content += f'OnCalendar=*-*-{profile.day_of_month:02d} {hour}:{minute}:00\n'
        
        content += f"""
Persistent=true

[Install]
WantedBy=timers.target
"""
        return content
    
    def _register_linux_cron(self, profile: ScheduledProfile) -> bool:
        """Register a cron job (fallback for systems without systemd)."""
        try:
            cron_entry = self._get_cron_entry(profile)
            
            # Get existing crontab
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            existing_cron = result.stdout if result.returncode == 0 else ''
            
            # Add new entry (avoid duplicates)
            if cron_entry not in existing_cron:
                new_cron = existing_cron + '\n' + cron_entry + '\n'
                subprocess.run(['crontab', '-'], input=new_cron, text=True, capture_output=True)
            
            return True
        except Exception:
            return False
    
    def _get_cron_entry(self, profile: ScheduledProfile) -> str:
        """Generate a cron entry."""
        minute, hour = profile.time.split(':')
        
        if profile.frequency == 'daily':
            return f'{minute} {hour} * * * {sys.executable} -m fileorganizer.cli organize --folder {profile.folder_path}'
        elif profile.frequency == 'weekly' and profile.day_of_week is not None:
            return f'{minute} {hour} * * {profile.day_of_week} {sys.executable} -m fileorganizer.cli organize --folder {profile.folder_path}'
        elif profile.frequency == 'monthly' and profile.day_of_month is not None:
            return f'{minute} {hour} {profile.day_of_month} * * {sys.executable} -m fileorganizer.cli organize --folder {profile.folder_path}'
        else:
            return f'{minute} {hour} * * * {sys.executable} -m fileorganizer.cli organize --folder {profile.folder_path}'
    
    def _unregister_linux_task(self, profile: ScheduledProfile) -> bool:
        """Unregister a Linux task (systemd or cron)."""
        # Try systemd first
        try:
            subprocess.run(['systemctl', '--user', 'stop', f'fileorganizer-{profile.name}.timer'], capture_output=True)
            subprocess.run(['systemctl', '--user', 'disable', f'fileorganizer-{profile.name}.timer'], capture_output=True)
            
            config_dir = Path.home() / '.config' / 'systemd' / 'user'
            timer_file = config_dir / f'fileorganizer-{profile.name}.timer'
            service_file = config_dir / f'fileorganizer-{profile.name}.service'
            
            if timer_file.exists():
                timer_file.unlink()
            if service_file.exists():
                service_file.unlink()
            
            subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
            return True
        except Exception:
            pass
        
        # Fall back to cron
        try:
            cron_entry = self._get_cron_entry(profile)
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            
            if result.returncode == 0:
                existing_cron = result.stdout
                new_cron = '\n'.join(line for line in existing_cron.split('\n') if line.strip() != cron_entry.strip())
                subprocess.run(['crontab', '-'], input=new_cron, text=True, capture_output=True)
            
            return True
        except Exception:
            return False
    
    def _set_linux_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        """Enable or disable a Linux task."""
        try:
            action = 'start' if enabled else 'stop'
            subprocess.run(
                ['systemctl', '--user', action, f'fileorganizer-{profile.name}.timer'],
                capture_output=True
            )
            return True
        except Exception:
            return False
