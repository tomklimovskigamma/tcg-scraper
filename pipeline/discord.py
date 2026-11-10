"""Post plain-text messages to a Discord webhook."""
from __future__ import annotations

import json
import os
import re
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


_MENTION = re.compile(r"<@(\d{5,25})>")


def post(url: str, content: str) -> None:
    """Send one message. Raises on failure. Waits out Discord's own rate limit.

    Only explicit `<@id>` user mentions notify anyone; @everyone, @here and roles never do.
    """
    users = sorted(set(_MENTION.findall(content)))[:100]
    data = json.dumps({"content": content, "allowed_mentions": {"parse": [], "users": users}}).encode()
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


def post_file(url: str, content: str, path: Path, filename: str = "chart.png") -> None:
    """Send one message with an image attached. Raises on failure."""
    boundary = "----tcgscraper" + os.urandom(8).hex()
    payload = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode()
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
        f"Content-Type: application/json\r\n\r\n".encode(), payload, b"\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{filename}\"\r\n"
        f"Content-Type: image/png\r\n\r\n".encode(), Path(path).read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "tcg-scraper/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60):
        return
