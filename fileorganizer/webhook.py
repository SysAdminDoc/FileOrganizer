"""Webhook notifications on organize completion (NEXT-28).

POSTs a JSON summary to user-configured URLs after each apply run.
Enables n8n, Zapier, Home Assistant, and custom downstream automations.
"""
import json
import logging
import os
import threading
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from fileorganizer.config import _APP_DATA_DIR

log = logging.getLogger(__name__)
_SETTINGS_FILE = os.path.join(_APP_DATA_DIR, "webhook_settings.json")
_TIMEOUT = 10


def load_webhook_urls() -> List[str]:
    """Load configured webhook URLs from settings."""
    if not os.path.isfile(_SETTINGS_FILE):
        return []
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("urls", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_webhook_urls(urls: List[str]):
    """Save webhook URLs to settings."""
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"urls": urls}, f, indent=2)


def build_payload(
    run_id: str,
    ok_count: int,
    err_count: int,
    categories: Dict[str, int],
    source: Optional[str] = None,
) -> Dict:
    """Build the webhook JSON payload."""
    return {
        "event": "organize_complete",
        "run_id": run_id,
        "source": source,
        "ok": ok_count,
        "errors": err_count,
        "total": ok_count + err_count,
        "categories": categories,
        "category_count": len(categories),
    }


def send_webhook(url: str, payload: Dict) -> bool:
    """POST payload to a single URL. Returns True on success."""
    try:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "FileOrganizer-Webhook/1.0")
        with urlopen(req, timeout=_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (URLError, OSError, Exception) as e:
        log.warning("Webhook POST failed for %s: %s", url, e)
        return False


def notify_all(
    run_id: str,
    ok_count: int,
    err_count: int,
    categories: Dict[str, int],
    source: Optional[str] = None,
):
    """Fire webhooks to all configured URLs in background threads."""
    urls = load_webhook_urls()
    if not urls:
        return

    payload = build_payload(run_id, ok_count, err_count, categories, source)

    for url in urls:
        t = threading.Thread(target=send_webhook, args=(url, payload), daemon=True)
        t.start()
