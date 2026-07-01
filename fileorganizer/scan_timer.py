"""Scan phase timing for performance measurement (NEXT-31).

Records wall-clock time for each pipeline phase (index build,
classification, enrichment, pre-flight, apply) and stores per-run
timings in organize_moves.db for display in the GUI status bar
and post-apply reports.
"""
import time
from typing import Dict, Optional


class ScanTimer:
    """Track wall-clock time for pipeline phases."""

    def __init__(self):
        self._phases: Dict[str, float] = {}
        self._active: Optional[str] = None
        self._start: float = 0.0
        self._run_start: float = time.monotonic()

    def start(self, phase: str):
        """Start timing a phase. Stops any previously active phase."""
        self.stop()
        self._active = phase
        self._start = time.monotonic()

    def stop(self):
        """Stop the currently active phase and record its duration."""
        if self._active:
            elapsed = time.monotonic() - self._start
            self._phases[self._active] = self._phases.get(self._active, 0.0) + elapsed
            self._active = None

    def elapsed_ms(self, phase: str) -> int:
        """Return elapsed milliseconds for a phase."""
        return int(self._phases.get(phase, 0.0) * 1000)

    def total_ms(self) -> int:
        """Return total elapsed milliseconds across all phases."""
        self.stop()
        return int(sum(self._phases.values()) * 1000)

    def run_elapsed_ms(self) -> int:
        """Return wall-clock ms since this timer was created."""
        return int((time.monotonic() - self._run_start) * 1000)

    def summary(self) -> Dict[str, int]:
        """Return {phase_name: elapsed_ms} for all recorded phases."""
        self.stop()
        return {k: int(v * 1000) for k, v in self._phases.items()}

    def format_summary(self) -> str:
        """Return a human-readable summary of all phase timings."""
        self.stop()
        parts = []
        for phase, ms in sorted(self.summary().items()):
            if ms < 1000:
                parts.append(f"{phase}: {ms}ms")
            else:
                parts.append(f"{phase}: {ms / 1000:.1f}s")
        total = self.total_ms()
        if total < 1000:
            parts.append(f"Total: {total}ms")
        else:
            parts.append(f"Total: {total / 1000:.1f}s")
        return " | ".join(parts)

    def reset(self):
        """Reset all timings."""
        self._phases.clear()
        self._active = None
        self._run_start = time.monotonic()
