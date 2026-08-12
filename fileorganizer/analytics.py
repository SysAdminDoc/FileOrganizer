"""Local-only analytics aggregates for the legacy desktop dashboard.

The dashboard reads existing SQLite stores and returns counts only. It never
returns source paths, prompts, model responses, or other file-level evidence.
Missing or partially initialized stores simply contribute zeroes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fileorganizer.config import _APP_DATA_DIR


DEFAULT_JOURNAL_DB = Path(_APP_DATA_DIR) / "organize_moves.db"
DEFAULT_PROVENANCE_DB = Path(_APP_DATA_DIR) / "classification-provenance.sqlite3"
DEFAULT_REVIEW_DB = (
    Path(os.environ.get("APPDATA") or os.path.expanduser("~"))
    / "FileOrganizer" / "review-results.sqlite3"
)
MAX_CONFUSION_ROWS = 100


def _read_rows(path: os.PathLike[str] | str, query: str) -> list[sqlite3.Row]:
    """Read a bounded query from an existing database without creating it."""
    db_path = Path(path)
    if not db_path.is_file():
        return []
    try:
        with sqlite3.connect(str(db_path), timeout=5) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(query).fetchall()
    except (OSError, sqlite3.Error):
        return []


def _move_metrics(path: os.PathLike[str] | str) -> dict[str, Any]:
    rows = _read_rows(
        path,
        """
        SELECT category, dst, status, source_signature
        FROM moves
        WHERE status='done'
        ORDER BY ts_done ASC, id ASC
        LIMIT 100000
        """,
    )
    categories: Counter[str] = Counter()
    file_types: Counter[str] = Counter()
    reclaimed = 0
    for row in rows:
        category = str(row["category"] or "Uncategorized")
        destination = str(row["dst"] or "")
        categories[category] += 1
        extension = os.path.splitext(destination)[1].casefold() or "[folders]"
        file_types[extension] += 1
        if "archive" in category.casefold() or "archive" in destination.casefold():
            try:
                signature = json.loads(row["source_signature"] or "{}")
                if isinstance(signature, dict):
                    reclaimed += max(0, int(signature.get("size", 0) or 0))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

    return {
        "total": len(rows),
        "by_category": [
            {"category": category, "count": count}
            for category, count in categories.most_common()
        ],
        "top_file_types": [
            {"extension": extension, "count": count}
            for extension, count in file_types.most_common(10)
        ],
        "storage_reclaimed_bytes": reclaimed,
    }


def _provenance_metrics(path: os.PathLike[str] | str) -> dict[str, Any]:
    rows = _read_rows(
        path,
        """
        SELECT classified_at, provider, model, suggested_decision,
               final_decision, user_correction
        FROM classification_provenance
        ORDER BY classified_at ASC, record_id ASC
        LIMIT 100000
        """,
    )
    monthly: defaultdict[str, Counter[str]] = defaultdict(Counter)
    confusion: Counter[tuple[str, str]] = Counter()
    models: set[str] = set()
    corrected = 0
    for row in rows:
        month = str(row["classified_at"] or "Unknown")[:7] or "Unknown"
        monthly[month]["total"] += 1
        provider = str(row["provider"] or "").strip()
        model = str(row["model"] or "").strip()
        if provider or model:
            models.add(f"{provider}:{model}".strip(":"))
        if str(row["user_correction"] or "").strip():
            corrected += 1
            monthly[month]["corrected"] += 1
        suggested = str(row["suggested_decision"] or "").strip()
        final = str(row["final_decision"] or suggested).strip()
        if suggested and final:
            confusion[(suggested, final)] += 1

    total = len(rows)
    accuracy = (total - corrected) / total if total else 0.0
    by_month = []
    for month in sorted(monthly):
        month_total = monthly[month]["total"]
        month_corrected = monthly[month]["corrected"]
        by_month.append({
            "month": month,
            "total": month_total,
            "corrected": month_corrected,
            "accuracy": (
                (month_total - month_corrected) / month_total
                if month_total else 0.0
            ),
        })
    confusion_rows = [
        {"suggested": suggested, "final": final, "count": count}
        for (suggested, final), count in confusion.most_common(MAX_CONFUSION_ROWS)
    ]
    return {
        "total": total,
        "corrected": corrected,
        "accuracy": accuracy,
        "models": len(models),
        "by_month": by_month,
        "confusion_matrix": confusion_rows,
    }


def _duplicate_metrics(path: os.PathLike[str] | str) -> dict[str, Any]:
    rows = _read_rows(
        path,
        """
        SELECT COUNT(DISTINCT entries.path) AS total,
               COUNT(DISTINCT CASE WHEN entries.is_reference=0 THEN entries.path END) AS duplicates,
               COALESCE(SUM(CASE WHEN entries.is_reference=0 THEN entries.size ELSE 0 END), 0) AS bytes
        FROM entries
        JOIN scans ON scans.id=entries.scan_id
        WHERE scans.kind='duplicates'
        """,
    )
    if not rows:
        return {"total": 0, "duplicates": 0, "rate": 0.0, "bytes": 0}
    total = int(rows[0]["total"] or 0)
    duplicates = int(rows[0]["duplicates"] or 0)
    return {
        "total": total,
        "duplicates": duplicates,
        "rate": duplicates / total if total else 0.0,
        "bytes": int(rows[0]["bytes"] or 0),
    }


def load_analytics_snapshot(
    *,
    journal_db: os.PathLike[str] | str = DEFAULT_JOURNAL_DB,
    provenance_db: os.PathLike[str] | str = DEFAULT_PROVENANCE_DB,
    review_db: os.PathLike[str] | str = DEFAULT_REVIEW_DB,
) -> dict[str, Any]:
    """Return the local dashboard snapshot from existing app databases."""
    moves = _move_metrics(journal_db)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "organized": moves,
        "model": _provenance_metrics(provenance_db),
        "duplicates": _duplicate_metrics(review_db),
        "storage_reclaimed_bytes": moves["storage_reclaimed_bytes"],
    }


__all__ = [
    "DEFAULT_JOURNAL_DB",
    "DEFAULT_PROVENANCE_DB",
    "DEFAULT_REVIEW_DB",
    "load_analytics_snapshot",
]
