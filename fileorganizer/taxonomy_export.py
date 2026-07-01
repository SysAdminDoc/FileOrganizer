"""Export the 384-category taxonomy as reusable YAML/JSON (NEXT-93).

Ships the full category hierarchy with keywords and descriptions as a
template that users can fork, extend, and share. Makes FileOrganizer's
taxonomy the canonical reference for creative-asset classification.
"""
import json
import os
from typing import Dict, List, Optional

from fileorganizer.categories import CATEGORIES, BUILTIN_CATEGORIES, NEGATIVE_KEYWORDS


def export_taxonomy_json(output_path: Optional[str] = None) -> str:
    """Export the full taxonomy as a JSON file.

    Args:
        output_path: Path to write the JSON. If None, returns the JSON string.

    Returns:
        The JSON string (always), and writes to file if output_path given.
    """
    taxonomy = []
    for cat_name, keywords in BUILTIN_CATEGORIES:
        entry = {
            "category": cat_name,
            "keywords": keywords,
        }
        negatives = NEGATIVE_KEYWORDS.get(cat_name)
        if negatives:
            entry["negative_keywords"] = negatives
        taxonomy.append(entry)

    doc = {
        "schema_version": "1.0",
        "generator": "FileOrganizer",
        "category_count": len(taxonomy),
        "categories": taxonomy,
    }

    result = json.dumps(doc, indent=2, ensure_ascii=False)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    return result


def export_taxonomy_yaml(output_path: Optional[str] = None) -> str:
    """Export the taxonomy as YAML (hand-rolled, no PyYAML dep).

    Args:
        output_path: Path to write the YAML. If None, returns the YAML string.

    Returns:
        The YAML string.
    """
    lines = [
        "# FileOrganizer Taxonomy",
        f"# {len(BUILTIN_CATEGORIES)} categories for creative asset classification",
        "# https://github.com/SysAdminDoc/FileOrganizer",
        "",
        "schema_version: '1.0'",
        f"category_count: {len(BUILTIN_CATEGORIES)}",
        "",
        "categories:",
    ]

    for cat_name, keywords in BUILTIN_CATEGORIES:
        lines.append(f"  - category: {_yaml_str(cat_name)}")
        lines.append("    keywords:")
        for kw in keywords:
            lines.append(f"      - {_yaml_str(kw)}")
        negatives = NEGATIVE_KEYWORDS.get(cat_name)
        if negatives:
            lines.append("    negative_keywords:")
            for neg in negatives:
                lines.append(f"      - {_yaml_str(neg)}")
        lines.append("")

    result = "\n".join(lines) + "\n"

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    return result


def get_taxonomy_stats() -> Dict:
    """Return summary statistics about the taxonomy."""
    total_keywords = sum(len(kws) for _, kws in BUILTIN_CATEGORIES)
    sections: Dict[str, int] = {}
    for cat_name, _ in BUILTIN_CATEGORIES:
        prefix = cat_name.split(" - ")[0] if " - " in cat_name else cat_name
        sections[prefix] = sections.get(prefix, 0) + 1

    return {
        "total_categories": len(BUILTIN_CATEGORIES),
        "total_keywords": total_keywords,
        "avg_keywords_per_category": round(total_keywords / max(len(BUILTIN_CATEGORIES), 1), 1),
        "sections": sections,
        "negative_rules": len(NEGATIVE_KEYWORDS),
    }


def _yaml_str(s: str) -> str:
    """Escape a string for YAML output."""
    if any(c in s for c in ":#{}[]&*!|>'\","):
        return f'"{s}"'
    return s
