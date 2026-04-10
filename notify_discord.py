#!/usr/bin/env python3
"""Post Discord webhook notification for newly landed Pokémon TCG stock.

Configuration:
  Set the DISCORD_WEBHOOK_URL environment variable before running.

Run after the scrapers:
  python3 scrape_jbhifi.py && python3 scrape_target.py && \\
  python3 scrape_kmart.py  && python3 scrape_bigw.py   && \\
  python3 notify_discord.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent

INVENTORY_FILES: dict[str, Path] = {
    "jbhifi": HERE / "data" / "inventory.json",
    "target": HERE / "data" / "target_inventory.json",
    "kmart":  HERE / "data" / "kmart_inventory.json",
    "bigw":   HERE / "data" / "bigw_inventory.json",
}

STORE_LABELS: dict[str, str] = {
    "jbhifi": "JB Hi-Fi",
    "target": "Target",
    "kmart":  "Kmart",
    "bigw":   "Big W",
}

# Discord embed colours (decimal)
STORE_COLORS: dict[str, int] = {
    "jbhifi": 0xFACC15,  # Yellow
    "target": 0xF87171,  # Red/coral
    "kmart":  0x38BDF8,  # Sky blue
    "bigw":   0x4ADE80,  # Green
}


# ── Helpers ─────────────────────────────────────────────────────────────────
def get_webhook_url() -> str:
    return os.environ.get("DISCORD_WEBHOOK_URL", "").strip()


def load_items(include_in_stock: bool = False) -> list[dict]:
    """Collect items from all store JSON files.
    
    Args:
        include_in_stock: If True, include all in-stock items, not just just_landed
    """
    items: list[dict] = []
    for source_key, path in INVENTORY_FILES.items():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scraped_at = data.get("scraped_at", "")
        
        # Get items based on mode
        if include_in_stock:
            item_list = data.get("in_stock") or []
            item_type = "in_stock"
        else:
            item_list = data.get("just_landed") or []
            item_type = "just_landed"
        
        for item in item_list:
            items.append({
                **item,
                "_source_key": source_key,
                "_source_name": STORE_LABELS.get(source_key, source_key),
                "_scraped_at": scraped_at,
                "_item_type": item_type,
            })
    return items


def fmt_price(price_aud) -> str:
    if price_aud is None:
        return "N/A"
    return f"${float(price_aud):.2f}"


def fmt_time(iso_str: str) -> str:
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y %H:%M UTC")
    except Exception:
        return iso_str


def build_embeds(items: list[dict]) -> list[dict]:
    """Build up to 10 Discord embeds (API limit per message)."""
    embeds = []
    for item in items[:10]:
        source_key  = item.get("_source_key", "")
        store_name  = item.get("_source_name", source_key)
        scraped_at  = item.get("_scraped_at", "")
        title       = item.get("title", "Unknown item")
        url         = item.get("url", "")
        price_aud   = item.get("price_aud")
        status      = item.get("status", "in_stock")
        release_lbl = item.get("release_label", "")

        is_preorder = status == "pre-order"
        status_str  = f"🗓 Pre-order — {release_lbl}" if is_preorder and release_lbl else \
                      "🗓 Pre-order" if is_preorder else "✅ In Stock"
        color       = 0xA78BFA if is_preorder else STORE_COLORS.get(source_key, 0x4ADE80)

        embed: dict = {
            "title": title,
            "color": color,
            "fields": [
                {"name": "🏪 Store",  "value": store_name,       "inline": True},
                {"name": "💰 Price",  "value": fmt_price(price_aud), "inline": True},
                {"name": "📦 Status", "value": status_str,       "inline": True},
            ],
            "footer": {"text": f"Scraped {fmt_time(scraped_at)}"},
        }
        if url:
            embed["url"] = url
        embeds.append(embed)
    return embeds


def send_discord(webhook_url: str, items: list[dict], include_in_stock: bool = False) -> None:
    n = len(items)
    embeds = build_embeds(items)
    
    if include_in_stock:
        content = f"📦 **{n} Pokémon TCG item{'s' if n != 1 else ''} currently in stock!**"
    else:
        content = f"🚨 **{n} new Pokémon TCG item{'s' if n != 1 else ''} just landed!**"

    payload: dict = {
        "content": content,
        "embeds": embeds,
    }

    # If more than 10 items, send a plain-text overflow list
    overflow = items[10:]
    if overflow:
        extra_lines = "\n".join(
            f"• {i.get('title', '?')} ({STORE_LABELS.get(i.get('_source_key', ''), '?')}) — {i.get('url', '')}"
            for i in overflow
        )
        payload["content"] += f"\n\nAdditional items:\n{extra_lines}"

    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    print(f"Discord notification sent for {n} item(s).")


# ── Entry point ─────────────────────────────────────────────────────────────
def main() -> int:
    import argparse
    
    parser = argparse.ArgumentParser(description="Send Discord notifications for Pokémon TCG stock")
    parser.add_argument("--include-in-stock", action="store_true", 
                       help="Include all in-stock items, not just just_landed")
    parser.add_argument("--force", action="store_true",
                       help="Send notification even if no items found (for testing)")
    args = parser.parse_args()
    
    webhook_url = get_webhook_url()
    if not webhook_url:
        print(
            "ERROR: DISCORD_WEBHOOK_URL environment variable not set.",
            file=sys.stderr,
        )
        return 1

    items = load_items(include_in_stock=args.include_in_stock)
    
    if not items:
        if args.force:
            print("No items found, but sending test notification due to --force flag")
            # Send a test notification
            test_payload = {
                "content": "✅ Pokémon TCG scraper test notification - System is working!"
            }
            resp = requests.post(webhook_url, json=test_payload, timeout=15)
            resp.raise_for_status()
            print("Test notification sent.")
            return 0
        else:
            item_type = "in-stock" if args.include_in_stock else "just-landed"
            print(f"No {item_type} items — nothing to notify.")
            return 0

    item_type = "in-stock" if args.include_in_stock else "just-landed"
    print(f"Found {len(items)} {item_type} item(s):")
    for item in items:
        print(f"  [{item.get('_source_name')}] {item.get('title')}")

    send_discord(webhook_url, items, include_in_stock=args.include_in_stock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
