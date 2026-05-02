"""Shared dataclass for metadata extractor return values."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetadataHint:
    """High-confidence category hint produced by a metadata extractor.

    Items resolved at confidence >= 90 skip downstream classification stages.
    Lower confidence is informational only and is ignored by the caller.
    """
    category: str
    confidence: int
    extractor: str
    reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_result(self, name: str) -> dict[str, Any]:
        """Convert to the dict shape classify_design expects from a stage."""
        return {
            "name": name,
            "category": self.category,
            "clean_name": name,
            "confidence": int(self.confidence),
            "notes": f"metadata_extractor:{self.extractor} ({self.reason})" if self.reason
                     else f"metadata_extractor:{self.extractor}",
            "_source_name": name,
            "_classifier": f"metadata_{self.extractor}",
        }
