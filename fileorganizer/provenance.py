"""
Provenance — source-domain parsing for asset folders/files.

Each asset on disk usually carries naming clues about which marketplace it
came from (Videohive ID prefix, MotionElements suffix, Creative Market 'cm_'
shortcode, etc.). Parsing those clues at index time lets the asset_fingerprints
database carry a stable `source_domain` field that downstream features can
weight on (embeddings prior, dedup heuristics, UI grouping).

A separate piracy-domain blocklist marks known re-host / cracked-asset domains
(intro-hd.net, gfxdrug, freegfx, etc.) so their names can be stripped from
CSV exports and review-panel display without losing the underlying record.
"""
from __future__ import annotations

import re
from typing import Optional


# ── Canonical source domains ──────────────────────────────────────────────────
#
# Patterns are checked in declaration order (most specific first). The first
# pattern to match a folder/file name wins.
#
# Each entry is (pattern, canonical_domain). The `canonical_domain` is the
# stable name we store in the DB and surface in the UI.

_DOMAIN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # MotionElements — explicit mid-name marker, very high specificity.
    (re.compile(r"_MotionElements_", re.IGNORECASE), "motionelements.com"),

    # Envato Elements — distinctive 'elements-...-CODE-CODE-DATE' pattern.
    (re.compile(r"^elements[-_][A-Za-z0-9_-]+-[A-Z0-9]{6,}-", re.IGNORECASE),
     "elements.envato.com"),

    # AEriver
    (re.compile(r"\baeriver\b|aeriver\.com", re.IGNORECASE), "aeriver.com"),

    # Creative Market shortcode (cm_NNNNNN).
    (re.compile(r"^cm[_-]\d{5,}", re.IGNORECASE), "creativemarket.com"),
    (re.compile(r"\bcreativemarket\b", re.IGNORECASE), "creativemarket.com"),

    # DesignBundles shortcode (db_NNNNNN).
    (re.compile(r"^db[_-]\d{5,}", re.IGNORECASE), "designbundles.net"),
    (re.compile(r"\bdesignbundles\b", re.IGNORECASE), "designbundles.net"),

    # Motion Array (MA-prefix or motionarray substring).
    (re.compile(r"\bmotionarray\b", re.IGNORECASE), "motionarray.com"),
    (re.compile(r"^MA[-_]\d{4,}", re.IGNORECASE), "motionarray.com"),

    # Freepik
    (re.compile(r"\bfreepik\b", re.IGNORECASE), "freepik.com"),

    # Dribbble / Behance (rare for design-asset bundles but seen).
    (re.compile(r"\bdribbble\b", re.IGNORECASE), "dribbble.com"),
    (re.compile(r"\bbehance\b", re.IGNORECASE), "behance.net"),

    # Videohive (Envato's video marketplace) — three explicit forms.
    (re.compile(r"^Videohive[_-]", re.IGNORECASE), "videohive.net"),
    (re.compile(r"^VH[_-]\d{4,}", re.IGNORECASE), "videohive.net"),
    # 8-9 digit numeric prefix followed by a real separator. Without the
    # separator requirement the pattern tags arbitrary numeric folders
    # like "12345678" or "12345678abc" as Videohive — keep the gate strict.
    (re.compile(r"^\d{8,9}[-_ ]"), "videohive.net"),
    (re.compile(r"\bvideohive\b", re.IGNORECASE), "videohive.net"),

    # Adobe Stock
    (re.compile(r"\badobe[-_]?stock\b", re.IGNORECASE), "stock.adobe.com"),
    (re.compile(r"^AS[_-]\d{6,}", re.IGNORECASE), "stock.adobe.com"),
)


# ── Piracy blocklist ──────────────────────────────────────────────────────────
#
# Domains known for re-hosting / cracking commercial design assets. The
# parser still recognises them so the underlying record can be tagged, but
# display_domain() returns an empty string so they never surface in UI
# captions or CSV exports. Detection patterns mostly key off junk-name
# stems already used by classify_design._JUNK_STEM_RE.

# Use letter-only lookarounds rather than \b — folder names are full of `_`,
# `-`, `.` separators, and Python's \b treats `_` as a word char (so
# "freegfx_pack_2026" would NOT trip a \bfreegfx\b match).
_PIRACY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"INTRO-HD\.NET", re.IGNORECASE), "intro-hd.net"),
    (re.compile(r"AIDOWNLOAD\.NET|(?<![A-Za-z])aidownload(?![A-Za-z])", re.IGNORECASE),
     "aidownload.net"),
    (re.compile(r"GFXDRUG\.COM|(?<![A-Za-z])gfxdrug(?![A-Za-z])", re.IGNORECASE),
     "gfxdrug.com"),
    (re.compile(r"(?<![A-Za-z])sharea?e(?![A-Za-z])|ShareAE\.com|share\.ae",
                re.IGNORECASE),
     "shareae.com"),
    (re.compile(r"(?<![A-Za-z])freegfx(?![A-Za-z])", re.IGNORECASE), "freegfx.net"),
    (re.compile(r"(?<![A-Za-z])graphicux(?![A-Za-z])", re.IGNORECASE), "graphicux.com"),
    (re.compile(r"(?<![A-Za-z])gfxlooks(?![A-Za-z])", re.IGNORECASE), "gfxlooks.com"),
)

_PIRACY_DOMAINS: frozenset[str] = frozenset(d for _, d in _PIRACY_PATTERNS)


def parse_source_domain(name: str) -> Optional[str]:
    """Resolve a source domain from a folder/file name.

    Tries piracy patterns first (so a `123456-INTRO-HD.NET` Videohive bundle
    re-hosted by intro-hd.net resolves to the piracy domain rather than the
    upstream Envato marketplace — the IP origin matters more than the
    underlying asset's vendor for UI/legal purposes).

    Returns the canonical domain string or None if no rule matches.
    """
    if not name:
        return None
    text = name.strip()
    if not text:
        return None

    for pattern, domain in _PIRACY_PATTERNS:
        if pattern.search(text):
            return domain

    for pattern, domain in _DOMAIN_PATTERNS:
        if pattern.search(text):
            return domain

    return None


def is_piracy_domain(domain: Optional[str]) -> bool:
    """True if the domain is on the known re-host / piracy blocklist."""
    return bool(domain) and domain in _PIRACY_DOMAINS


def display_domain(domain: Optional[str]) -> str:
    """UI-safe display string for a source domain.

    Returns an empty string for piracy domains (so they don't surface in
    review-panel captions or CSV exports) and otherwise echoes the input.
    """
    if not domain:
        return ""
    if is_piracy_domain(domain):
        return ""
    return domain


def all_known_domains() -> list[str]:
    """All canonical (non-piracy) domains the parser can emit. Stable ordering."""
    seen: list[str] = []
    for _, dom in _DOMAIN_PATTERNS:
        if dom not in seen:
            seen.append(dom)
    return seen


def all_piracy_domains() -> list[str]:
    """All piracy-blocklist domains. Stable ordering."""
    return sorted(_PIRACY_DOMAINS)
