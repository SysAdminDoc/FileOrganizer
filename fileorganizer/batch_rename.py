"""Shared canonical batch-rename planning for GUI and CLI workflows."""

from __future__ import annotations

import os
import re
from typing import Any

from fileorganizer.path_safety import validate_storage_name


CANONICAL_TEMPLATE = "{CAT_CODE}_{ID}_{CLEAN_NAME}"
_TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]+))?\}")
_INVALID_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00]')
_MULTI_SPACE = re.compile(r"\s+")


def item_value(item: Any, name: str, default: Any = '') -> Any:
    """Read a field from either a model object or a CLI result dictionary."""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def item_source_path(item: Any) -> str:
    """Return the current filesystem path represented by an item."""
    for field_name in ('full_source_path', 'full_src', 'full_current_path', 'src'):
        value = item_value(item, field_name, '')
        if isinstance(value, str) and value.strip():
            return value
    return ''


def item_target_path(item: Any) -> str:
    """Return the pending destination path, falling back to the source path."""
    for field_name in ('full_dest_path', 'full_dst', 'full_new_path', 'dest'):
        value = item_value(item, field_name, '')
        if isinstance(value, str) and value.strip():
            return value
    return item_source_path(item)


def item_is_file(item: Any) -> bool:
    """Identify file items without treating a folder's suffix as an extension."""
    if item_value(item, 'is_file_item', None) is not None:
        return bool(item_value(item, 'is_file_item'))
    if item_value(item, 'is_folder', None) is not None:
        return not bool(item_value(item, 'is_folder'))
    return bool(item_value(item, 'full_src', ''))


def category_code(category: str) -> str:
    """Build a stable uppercase code from a taxonomy category name."""
    words = re.findall(r"[A-Za-z0-9]+", str(category or '').upper())
    code = ''.join(word[0] for word in words)
    return code[:12] or 'UNCAT'


def extract_identifier(item: Any, fallback_index: int = 1) -> str:
    """Extract a marketplace/asset identifier, or use a stable preview ordinal."""
    fields = (
        '_marketplace_id', 'marketplace_id', '_asset_id', 'asset_id',
        'product_id', 'item_id', 'id',
    )
    for field_name in fields:
        value = item_value(item, field_name, '')
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if ':' in text:
            text = text.rsplit(':', 1)[-1]
        text = re.sub(r'[^A-Za-z0-9_-]', '', text)
        if text:
            return text.upper()

    candidates = [
        item_value(item, 'folder_name', ''),
        item_value(item, 'name', ''),
        os.path.basename(item_source_path(item)),
    ]
    for candidate in candidates:
        match = re.search(r'(?<!\d)(\d{4,})(?!\d)', str(candidate or ''))
        if match:
            return match.group(1)
    return f'{max(1, int(fallback_index)):04d}'


def _clean_component(value: Any, fallback: str = 'UNTITLED') -> str:
    text = str(value or '').strip()
    if not text:
        text = fallback
    text = _INVALID_COMPONENT_CHARS.sub('-', text)
    text = _MULTI_SPACE.sub(' ', text).strip(' .')
    return text or fallback


def _clean_name(item: Any) -> str:
    for field_name in ('clean_name', 'cleaned_name', 'display_name', 'folder_name', 'name'):
        value = item_value(item, field_name, '')
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if item_is_file(item):
                text = os.path.splitext(text)[0]
            return _clean_component(text)
    source_name = os.path.basename(item_source_path(item))
    return _clean_component(os.path.splitext(source_name)[0])


def render_name(item: Any, index: int = 1, template: str = CANONICAL_TEMPLATE) -> str:
    """Render and validate a canonical name from a bounded template.

    Supported fields are ``CAT_CODE``, ``ID``, ``CLEAN_NAME``, ``CATEGORY``,
    ``NAME``, ``COUNTER`` and their lowercase spellings. Unknown fields resolve
    to an empty string, keeping user-edited templates deterministic and safe.
    """
    if not isinstance(template, str) or not template.strip():
        raise ValueError('rename template must not be empty')
    category = str(item_value(item, 'category', '') or '').strip()
    clean_name = _clean_name(item)
    identifier = extract_identifier(item, index)
    context = {
        'cat_code': category_code(category),
        'id': identifier,
        'clean_name': clean_name,
        'category': _clean_component(category, 'UNCATEGORIZED'),
        'name': clean_name,
        'counter': max(1, int(index)),
    }

    def replace(match: re.Match) -> str:
        key = match.group(1).lower()
        value = context.get(key, '')
        format_spec = match.group(2)
        if format_spec:
            try:
                return format(int(value), format_spec)
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    rendered = _TOKEN_RE.sub(replace, template)
    rendered = _INVALID_COMPONENT_CHARS.sub('-', rendered)
    rendered = _MULTI_SPACE.sub(' ', rendered).strip(' ._-')
    rendered = re.sub(r'[_-]{2,}', '_', rendered).strip(' ._-')
    if not rendered:
        raise ValueError('rename template produced an empty name')
    return validate_storage_name(rendered)


def proposed_filename(item: Any, index: int = 1, template: str = CANONICAL_TEMPLATE) -> str:
    """Render a name and preserve a file's original extension when applicable."""
    rendered = render_name(item, index, template)
    if not item_is_file(item):
        return rendered
    extension = os.path.splitext(os.path.basename(item_source_path(item)))[1]
    return validate_storage_name(rendered + extension) if extension else rendered


__all__ = [
    'CANONICAL_TEMPLATE',
    'category_code',
    'extract_identifier',
    'item_is_file',
    'item_source_path',
    'item_target_path',
    'item_value',
    'proposed_filename',
    'render_name',
]
