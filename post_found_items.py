#!/usr/bin/env python3
"""Post run_and_post.sh results to the Discord webhook. No LLM involved.

Reads run_and_post.sh stdout on stdin (FOUND_ITEMS= / ITEM=store|title|url /
DASHBOARD= lines), groups the new items by store, and posts one message per
store (split when a message would pass Discord's 2000-character limit).

The webhook URL comes from DISCORD_WEBHOOK_URL or discord_webhook.txt next to
this file. Set DRY_RUN=1 to print the messages instead of posting them.

Exit codes: 0 posted (or nothing to post), 1 a post failed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT = 1900  # Discord rejects content over 2000 characters
HEADER = "🚨 **New Pokémon TCG Stock!**"


def webhook_url() -> str:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        f = HERE / "discord_webhook.txt"
        if f.exists():
            url = f.read_text(encoding="utf-8").strip()
    return url


def parse(lines: list[str]) -> tuple[dict[str, list[tuple[str, str]]], str]:
    by_store: dict[str, list[tuple[str, str]]] = {}
    dashboard = ""
    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("DASHBOARD="):
            dashboard = line[len("DASHBOARD="):].strip()
        elif line.startswith("ITEM="):
            parts = line[len("ITEM="):].split("|")
            if len(parts) < 2:
                continue
            store, title = parts[0].strip(), parts[1].strip()
            url = parts[2].strip() if len(parts) > 2 else ""
            by_store.setdefault(store, []).append((title, url))
    return by_store, dashboard


def build_messages(by_store: dict[str, list[tuple[str, str]]], dashboard: str) -> list[tuple[str, str]]:
    """Return (store, message) pairs, one or more per store."""
    footer = f"\n📊 **Dashboard:** <{dashboard}>" if dashboard else ""
    messages: list[tuple[str, str]] = []
    for store, items in by_store.items():
        head = f"{HEADER}\n**🏪 {store}**"
        body = head
        for title, url in items:
            entry = f"\n• **{title}**" + (f"\n  <{url}>" if url else "")
            if len(body) + len(entry) + len(footer) > LIMIT and body != head:
                messages.append((store, body + footer))
                body = head
            body += entry
        messages.append((store, body + footer))
    return messages


def forget_seen(by_store: dict[str, list[tuple[str, str]]], stores: set[str]) -> None:
    """Un-mark items of `stores` in seen_items.txt so a failed post is retried next run.

    run_and_post.sh records items as seen before anything is posted; without this,
    an alert that fails to send would be lost for good.
    """
    seen = HERE / "seen_items.txt"
    if not seen.exists():
        return
    drop = set()
    for store in stores:
        key = store.lower().replace(" ", "").replace("-", "")
        for title, _ in by_store.get(store, []):
            drop.add(f"{key}|{title.rstrip('*') if title.endswith('*') else title}")
    kept = []
    for line in seen.read_text(encoding="utf-8").splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2 and not line.startswith("#") and parts[1] in drop:
            continue
        kept.append(line)
    seen.write_text("\n".join(kept) + "\n", encoding="utf-8")


def post(url: str, content: str) -> None:
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
            if e.code == 429 and attempt < 3:  # Discord's own rate limit: wait as told
                try:
                    wait = float(json.loads(e.read()).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                time.sleep(min(wait, 30) + 0.5)
                continue
            raise


def main() -> int:
    by_store, dashboard = parse(sys.stdin.readlines())
    count = sum(len(v) for v in by_store.values())
    if count == 0:
        return 0
    messages = build_messages(by_store, dashboard)
    if os.environ.get("DRY_RUN"):
        print("\n---\n".join(m for _, m in messages))
        return 0
    url = webhook_url()
    if not url:
        forget_seen(by_store, set(by_store))
        print("ERROR: no Discord webhook URL (DISCORD_WEBHOOK_URL or discord_webhook.txt)", file=sys.stderr)
        return 1
    for i, (_, msg) in enumerate(messages):
        try:
            post(url, msg)
        except Exception as e:  # noqa: BLE001
            unsent = {store for store, _ in messages[i:]}
            forget_seen(by_store, unsent)
            code = f" {e.code}" if isinstance(e, urllib.error.HTTPError) else ""
            print(f"ERROR: Discord post {i + 1}/{len(messages)} failed: {type(e).__name__}{code}; "
                  f"{len(unsent)} store(s) will be retried next run", file=sys.stderr)
            return 1
        time.sleep(1)
    with open(HERE / "cron_posted_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S %Z')} - Posted {count} item(s) in {len(messages)} message(s)\n")
    print(f"Posted {count} new item(s) across {len(by_store)} store(s) to Discord.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
