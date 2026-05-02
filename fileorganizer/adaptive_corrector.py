"""FileOrganizer — Adaptive learning from user corrections.

When a user corrects a misclassification, record the correction with:
- Folder fingerprint (file count, size, mtime) for exact matching on re-run
- Extracted keywords from folder name for pattern-based injection into future prompts
- Original LLM confidence to weight the injection (low confidence → higher priority)
- Timestamp for recency filtering

Design:
- corrections.json: Array of {fingerprint, keywords, category, confidence, timestamp}
- load_corrections(): Parse JSON, filter by age
- record_correction(): Add new correction (dedup by fingerprint)
- apply_correction(): Check if folder matches known fingerprint → return correction
- inject_few_shot(): Find keyword matches, build few-shot examples for system prompt
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from fileorganizer.config import _APP_DATA_DIR
from fileorganizer.folder_cache import compute_folder_fingerprint
from fileorganizer.naming import _normalize, _extract_name_hints


_CORRECTIONS_FILE = os.path.join(_APP_DATA_DIR, 'corrections.json')
_CORRECTIONS_VERSION = '1.0'
_CORRECTION_MAX_AGE_DAYS = 365  # Keep corrections for 1 year
_CORRECTION_HISTORY_LIMIT = 5000  # Hard cap to prevent unbounded growth


class CorrectionRecord:
    """Single correction: fingerprint, keywords, category, confidence, timestamp."""
    
    def __init__(self, folder_name: str, folder_path: str, corrected_category: str,
                 original_confidence: int = 0, timestamp: Optional[str] = None):
        """
        Args:
            folder_name: Original folder name
            folder_path: Original folder path (for fingerprint computation)
            corrected_category: The user-supplied correct category
            original_confidence: LLM confidence (0-100) — lower confidence → higher weight
            timestamp: ISO 8601 timestamp (defaults to now)
        """
        self.folder_name = folder_name
        self.folder_path = folder_path
        self.corrected_category = corrected_category
        self.original_confidence = max(0, min(original_confidence, 100))
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        
        # Compute fingerprint for exact matching
        self.fingerprint = compute_folder_fingerprint(folder_path) if os.path.isdir(folder_path) else None
        
        # Extract keywords from folder name for pattern injection
        self.keywords = self._extract_keywords(folder_name)
    
    def _extract_keywords(self, folder_name: str) -> List[str]:
        """Extract significant keywords from folder name.
        
        Returns:
            List of normalized keywords (lowercased, deduplicated, sorted)
        """
        # Split by common separators, normalize
        parts = re.split(r'[-_\s\.]+', folder_name.lower())
        
        # Filter: keep words 3+ chars, ignore common noise
        noise = {'the', 'a', 'an', 'for', 'and', 'or', 'of', 'in', 'on', 'at', 'by', 'to',
                 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'v1', 'v2', 'v3',
                 'final', 'template', 'pack', 'bundle', 'collection', 'set', 'design',
                 'file', 'folder', 'archive', 'zip', 'rar', 'tar', 'project'}
        
        keywords = []
        for part in parts:
            if len(part) >= 3 and part not in noise:
                keywords.append(part)
        
        return sorted(list(set(keywords)))  # Deduplicate and sort
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            'folder_name': self.folder_name,
            'fingerprint': self.fingerprint,
            'keywords': self.keywords,
            'category': self.corrected_category,
            'confidence': self.original_confidence,
            'timestamp': self.timestamp
        }
    
    @staticmethod
    def from_dict(d: dict) -> 'CorrectionRecord':
        """Deserialize from JSON dict."""
        rec = CorrectionRecord.__new__(CorrectionRecord)
        rec.folder_name = d.get('folder_name', '')
        rec.fingerprint = d.get('fingerprint')
        rec.keywords = d.get('keywords', [])
        rec.corrected_category = d.get('category', '')
        rec.original_confidence = d.get('confidence', 50)
        rec.timestamp = d.get('timestamp', datetime.now(timezone.utc).isoformat())
        return rec


class AdaptiveCorrector:
    """Manage user corrections and apply them to future runs."""
    
    def __init__(self, corrections_file: str = None):
        """
        Args:
            corrections_file: Path to corrections.json (defaults to app data dir)
        """
        self.corrections_file = corrections_file or _CORRECTIONS_FILE
        self.corrections: List[CorrectionRecord] = []
        self._load_corrections()
    
    def _load_corrections(self):
        """Load corrections from JSON file, filtering by age."""
        if not os.path.exists(self.corrections_file):
            self.corrections = []
            return
        
        try:
            with open(self.corrections_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Expect: {version: "1.0", corrections: [...]}
            corrections_list = data.get('corrections', []) if isinstance(data, dict) else data
            
            # Filter by age
            cutoff = datetime.now(timezone.utc) - timedelta(days=_CORRECTION_MAX_AGE_DAYS)
            kept = []
            for rec_dict in corrections_list:
                try:
                    rec = CorrectionRecord.from_dict(rec_dict)
                    if rec.timestamp:
                        try:
                            ts = datetime.fromisoformat(rec.timestamp.replace('Z', '+00:00'))
                            if ts >= cutoff:
                                kept.append(rec)
                        except (ValueError, AttributeError):
                            kept.append(rec)  # Keep if timestamp unparseable
                    else:
                        kept.append(rec)
                except Exception:
                    pass  # Skip malformed records
            
            self.corrections = kept
        except (OSError, json.JSONDecodeError):
            self.corrections = []
    
    def _save_corrections(self):
        """Write corrections to JSON file."""
        # Trim to hard limit
        to_save = self.corrections[-_CORRECTION_HISTORY_LIMIT:]
        
        data = {
            'version': _CORRECTIONS_VERSION,
            'corrections': [rec.to_dict() for rec in to_save]
        }
        
        try:
            os.makedirs(os.path.dirname(self.corrections_file), exist_ok=True)
            with open(self.corrections_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Fail silently; corrections are optional
    
    def record_correction(self, folder_name: str, folder_path: str,
                         corrected_category: str, original_confidence: int = 0):
        """Record a user correction.
        
        Args:
            folder_name: Original folder name
            folder_path: Original folder path
            corrected_category: User-supplied correct category
            original_confidence: LLM confidence (0-100)
        """
        # Deduplicate: if we already have a correction for this fingerprint, update it
        new_rec = CorrectionRecord(folder_name, folder_path, corrected_category, original_confidence)
        
        # Remove any existing correction with same fingerprint
        if new_rec.fingerprint:
            self.corrections = [r for r in self.corrections if r.fingerprint != new_rec.fingerprint]
        
        self.corrections.append(new_rec)
        self._save_corrections()
    
    def apply_correction(self, folder_path: str) -> Optional[Tuple[str, int]]:
        """Check if folder matches a known correction by fingerprint.
        
        Returns:
            (category, weight) where weight is 1–100 based on recency and confidence.
            Returns None if no match found.
        """
        if not os.path.isdir(folder_path):
            return None
        
        fingerprint = compute_folder_fingerprint(folder_path)
        if not fingerprint:
            return None
        
        # Find exact fingerprint match
        for rec in self.corrections:
            if rec.fingerprint == fingerprint:
                # Weight: inverse of original confidence + recency bonus
                # Low confidence (30) → high weight (70)
                # High confidence (95) → low weight (5)
                confidence_weight = 100 - rec.original_confidence
                
                # Recency bonus (up to +20): corrections from last 30 days get bonus
                recency_bonus = 0
                if rec.timestamp:
                    try:
                        ts = datetime.fromisoformat(rec.timestamp.replace('Z', '+00:00'))
                        age_days = (datetime.now(timezone.utc) - ts).days
                        if age_days <= 30:
                            recency_bonus = int(20 * (1 - age_days / 30))
                    except (ValueError, AttributeError):
                        pass
                
                weight = min(100, confidence_weight + recency_bonus)
                return (rec.corrected_category, weight)
        
        return None
    
    def inject_few_shot(self, folder_name: str, num_examples: int = 3) -> List[Dict]:
        """Find corrections matching keywords in folder name, return as few-shot examples.
        
        Returns:
            List of {name, category} dicts to inject into LLM prompt
        """
        # Extract keywords from the query folder
        query_keywords = self._extract_keywords_from_name(folder_name)
        if not query_keywords:
            return []
        
        # Find corrections with matching keywords
        matches = []
        for rec in self.corrections:
            if not rec.keywords:
                continue
            
            # Jaccard similarity: common keywords / total unique keywords
            common = set(query_keywords) & set(rec.keywords)
            if common:
                total = len(set(query_keywords) | set(rec.keywords))
                similarity = len(common) / total if total > 0 else 0
                
                # Weight by original confidence (uncertain → more useful)
                weight = (1 - rec.original_confidence / 100) * similarity
                
                matches.append((weight, rec))
        
        # Sort by weight (descending) and take top N
        matches.sort(key=lambda x: -x[0])
        
        # Build few-shot examples
        examples = []
        for _, rec in matches[:num_examples]:
            examples.append({
                'name': rec.folder_name,
                'category': rec.corrected_category
            })
        
        return examples
    
    def _extract_keywords_from_name(self, folder_name: str) -> List[str]:
        """Extract keywords from folder name (same logic as CorrectionRecord)."""
        parts = re.split(r'[-_\s\.]+', folder_name.lower())
        noise = {'the', 'a', 'an', 'for', 'and', 'or', 'of', 'in', 'on', 'at', 'by', 'to',
                 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'v1', 'v2', 'v3',
                 'final', 'template', 'pack', 'bundle', 'collection', 'set', 'design',
                 'file', 'folder', 'archive', 'zip', 'rar', 'tar', 'project'}
        keywords = [part for part in parts if len(part) >= 3 and part not in noise]
        return sorted(list(set(keywords)))
    
    def get_stats(self) -> dict:
        """Return stats on stored corrections."""
        if not self.corrections:
            return {'total': 0, 'by_category': {}}
        
        by_cat = {}
        for rec in self.corrections:
            by_cat[rec.corrected_category] = by_cat.get(rec.corrected_category, 0) + 1
        
        return {
            'total': len(self.corrections),
            'by_category': by_cat,
            'oldest': self.corrections[0].timestamp if self.corrections else None,
            'newest': self.corrections[-1].timestamp if self.corrections else None
        }
    
    def clear_all(self):
        """Clear all corrections (for testing or reset)."""
        self.corrections = []
        try:
            os.remove(self.corrections_file)
        except OSError:
            pass


def build_adaptive_system_prompt(folder_name: str, base_prompt: str) -> str:
    """Enhance system prompt with few-shot examples from prior corrections.
    
    Args:
        folder_name: Current folder being classified
        base_prompt: The base system prompt (from ollama._build_llm_system_prompt)
    
    Returns:
        Enhanced system prompt with few-shot examples appended
    """
    corrector = AdaptiveCorrector()
    examples = corrector.inject_few_shot(folder_name, num_examples=3)
    
    if not examples:
        return base_prompt
    
    # Append few-shot examples to prompt
    examples_text = "RECENT EXAMPLES (similar folders from your library):\n"
    for ex in examples:
        examples_text += f"  • {ex['name']} → {ex['category']}\n"
    
    return base_prompt + "\n\n" + examples_text
