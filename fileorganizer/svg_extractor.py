"""SVG 2.0 metadata extraction and classification (NEXT-78).

Parses <metadata>, <title>, <desc>, <rdf:RDF> tags using stdlib
xml.etree.ElementTree. Classifies SVGs into: design system icons,
illustrations, diagrams, animations (via <animate> detection).
"""
import os
from typing import Dict, Any, Optional

try:
    from defusedxml.ElementTree import parse as _safe_parse
except ImportError:
    import xml.etree.ElementTree as _ET
    _safe_parse = _ET.parse
import xml.etree.ElementTree as ET

_SVG_NS = "http://www.w3.org/2000/svg"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_CC_NS = "http://creativecommons.org/ns#"
_XMP_NS = "http://ns.adobe.com/xap/1.0/"

_NS = {
    "svg": _SVG_NS,
    "dc": _DC_NS,
    "rdf": _RDF_NS,
    "cc": _CC_NS,
    "xmp": _XMP_NS,
}


def extract_svg_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """Extract metadata from an SVG file.

    Returns dict with keys: title, description, author, license,
    creation_date, keywords, width, height, has_animation,
    svg_type (icon/illustration/diagram/animation).
    Returns None on parse error.
    """
    if not os.path.isfile(file_path):
        return None

    try:
        tree = _safe_parse(file_path)
    except (ET.ParseError, Exception):
        return None

    root = tree.getroot()
    tag = root.tag
    if not tag.endswith("svg") and tag != "svg":
        return None

    meta: Dict[str, Any] = {
        "title": None,
        "description": None,
        "author": None,
        "license": None,
        "creation_date": None,
        "keywords": [],
        "width": None,
        "height": None,
        "has_animation": False,
        "svg_type": "illustration",
    }

    _extract_dimensions(root, meta)
    _extract_title_desc(root, meta)
    _extract_rdf_metadata(root, meta)
    _detect_animation(root, meta)
    _classify_svg_type(root, meta)

    return meta


def _extract_dimensions(root: ET.Element, meta: Dict[str, Any]):
    w = root.get("width")
    h = root.get("height")
    if w:
        meta["width"] = _parse_dimension(w)
    if h:
        meta["height"] = _parse_dimension(h)
    if not meta["width"] or not meta["height"]:
        vb = root.get("viewBox")
        if vb:
            parts = vb.replace(",", " ").split()
            if len(parts) >= 4:
                try:
                    meta["width"] = meta["width"] or float(parts[2])
                    meta["height"] = meta["height"] or float(parts[3])
                except ValueError:
                    pass


def _parse_dimension(val: str) -> Optional[float]:
    val = val.strip().lower()
    for unit in ("px", "pt", "mm", "cm", "in", "em", "%"):
        val = val.replace(unit, "")
    try:
        return float(val)
    except ValueError:
        return None


def _extract_title_desc(root: ET.Element, meta: Dict[str, Any]):
    for tag_local in ("title", "desc"):
        for ns_prefix in (f"{{{_SVG_NS}}}", ""):
            el = root.find(f"{ns_prefix}{tag_local}")
            if el is not None and el.text:
                key = "title" if tag_local == "title" else "description"
                meta[key] = el.text.strip()
                break


def _extract_rdf_metadata(root: ET.Element, meta: Dict[str, Any]):
    metadata = root.find(f"{{{_SVG_NS}}}metadata")
    if metadata is None:
        metadata = root.find("metadata")
    if metadata is None:
        return

    for el in metadata.iter():
        tag = el.tag
        text = (el.text or "").strip()
        if not text:
            continue
        if tag.endswith("}title") or tag == "title":
            meta["title"] = meta["title"] or text
        elif tag.endswith("}description") or tag == "description":
            meta["description"] = meta["description"] or text
        elif tag.endswith("}creator") or tag == "creator":
            meta["author"] = meta["author"] or text
        elif tag.endswith("}date") or tag == "date":
            meta["creation_date"] = meta["creation_date"] or text
        elif tag.endswith("}rights") or tag == "rights":
            meta["license"] = meta["license"] or text
        elif tag.endswith("}subject") or tag == "subject":
            meta["keywords"].append(text)
        elif tag.endswith("}license") or tag.endswith("}License"):
            href = el.get(f"{{{_RDF_NS}}}resource") or el.get("rdf:resource")
            if href:
                meta["license"] = meta["license"] or href


def _detect_animation(root: ET.Element, meta: Dict[str, Any]):
    anim_tags = {"animate", "animateTransform", "animateMotion", "set"}
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local in anim_tags:
            meta["has_animation"] = True
            return


def _classify_svg_type(root: ET.Element, meta: Dict[str, Any]):
    if meta["has_animation"]:
        meta["svg_type"] = "animation"
        return

    w = meta.get("width")
    h = meta.get("height")

    if w and h and w <= 64 and h <= 64:
        meta["svg_type"] = "icon"
        return

    element_count = sum(1 for _ in root.iter())
    text_count = sum(
        1 for el in root.iter()
        if (el.tag.split("}")[-1] if "}" in el.tag else el.tag) == "text"
    )

    if text_count > 5 and text_count / max(element_count, 1) > 0.15:
        meta["svg_type"] = "diagram"
        return

    meta["svg_type"] = "illustration"
