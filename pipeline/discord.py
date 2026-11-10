"""Post plain-text messages to a Discord webhook."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def webhook_url(root: Path) -> str:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        try:
            url = (root / "discord_webhook.txt").read_text(encoding="utf-8").strip()
        except OSError:
            url = ""
    return url


def post(url: str, content: str) -> None:
    """Send one message. Raises on failure. Waits out Discord's own rate limit."""
    data = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode()
    for attempt in range(4):
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "tcg-scraper/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20):
                return
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                try:
                    wait = float(json.loads(e.read()).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                time.sleep(min(wait, 30) + 0.5)
                continue
            raise
