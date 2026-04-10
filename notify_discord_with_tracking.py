#!/usr/bin/env python3
"""Post Discord webhook notification for newly landed Pokémon TCG stock with token tracking.

Configuration:
  Set the DISCORD_WEBHOOK_URL environment variable before running.

Run after the scrapers:
  python3 scrape_jbhifi.py && python3 scrape_target.py && \\
  python3 scrape_kmart.py  && python3 scrape_bigw.py   && \\
  python3 notify_discord_with_tracking.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import uuid

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


# ── Token Tracking ──────────────────────────────────────────────────────────
def start_token_tracking(job_id: str, job_type: str = "scraper_notification") -> bool:
    """Start token tracking for this job."""
    try:
        result = subprocess.run(
            [
                sys.executable, str(HERE / "token_tracker.py"),
                "--action", "start",
                "--job-id", job_id,
                "--job-type", job_type
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️ Failed to start token tracking: {e}")
        return False


def end_token_tracking(job_id: str, items_processed: int = 0, 
                      message_length: int = 0, notes: str = "") -> bool:
    """End token tracking for this job."""
    try:
        result = subprocess.run(
            [
                sys.executable, str(HERE / "token_tracker.py"),
                "--action", "end",
                "--job-id", job_id,
                "--items", str(items_processed),
                "--message-length", str(message_length),
                "--notes", notes
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️ Failed to end token tracking: {e}")
        return False


def generate_job_id() -> str:
    """Generate a unique job ID."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"scraper-{timestamp}-{unique_id}"


# ── Helpers ─────────────────────────────────────────────────────────────────
def get_webhook_url() -> str:
    return os.environ.get("DISCORD_WEBHOOK_URL", "").strip()


def load_items(include_in_stock: bool = False) -> list[dict]:
    items = []
    for source_key, path in INVENTORY_FILES.items():
        if not path.exists():
            print(f"⚠️  {path.name} not found — skipping {source_key}")
            continue

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️  Failed to load {path}: {e}")
            continue

        item_list = data.get("just_landed") or []
        if include_in_stock:
            item_list = data.get("in_stock") or []

        for item in item_list:
            item["_source_name"] = STORE_LABELS.get(source_key, source_key)
            item["_source_key"] = source_key
            items.append(item)

    return items


def fmt_time(iso_str: str) -> str:
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y %H:%M UTC")
    except Exception:
        return iso_str


def send_discord(webhook_url: str, items: list[dict], include_in_stock: bool = False) -> None:
    n = len(items)
    if n == 0:
        return

    # Calculate message length for token tracking
    total_message_length = 0
    
    # Build embeds
    embeds = []
    for source_key in STORE_LABELS:
        source_items = [i for i in items if i.get("_source_key") == source_key]
        if not source_items:
            continue

        source_name = STORE_LABELS[source_key]
        embed = {
            "title": f"{source_name} ({len(source_items)} item{'s' if len(source_items) != 1 else ''})",
            "color": STORE_COLORS[source_key],
            "fields": [],
            "footer": {"text": f"Scraped {fmt_time(items[0].get('scraped_at'))}"},
        }

        # Add up to 5 items per embed (Discord limit)
        for item in source_items[:5]:
            title = item.get("title", "Unknown")
            price = item.get("price")
            url = item.get("url", "")
            status = item.get("status", "in_stock")
            
            # Track message length
            total_message_length += len(title) + len(str(price)) + len(url) + 50  # Approx for formatting
            
            price_str = f"${price:.2f}" if price is not None else "—"
            status_emoji = "📦" if status == "pre-order" else "✅"
            embed["fields"].append({
                "name": f"{status_emoji} {title}",
                "value": f"**{price_str}** • [View product]({url})",
                "inline": False,
            })

        embeds.append(embed)

    # Build payload
    if include_in_stock:
        content = f"📦 **{n} Pokémon TCG item{'s' if n != 1 else ''} currently in stock**"
    else:
        content = f"🚨 **{n} new Pokémon TCG item{'s' if n != 1 else ''} just landed!**"
    
    total_message_length += len(content)
    
    payload = {
        "content": content,
        "embeds": embeds,
        "username": "TCG Scraper",
        "avatar_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/poke-ball.png",
    }

    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    
    # Return message length for token tracking
    return total_message_length, n


# ── Entry point ─────────────────────────────────────────────────────────────
def main() -> int:
    import argparse
    
    parser = argparse.ArgumentParser(description="Send Discord notifications for Pokémon TCG stock")
    parser.add_argument("--include-in-stock", action="store_true", 
                       help="Include all in-stock items, not just just_landed")
    parser.add_argument("--force", action="store_true",
                       help="Send notification even if no items found (for testing)")
    parser.add_argument("--no-tracking", action="store_true",
                       help="Skip token tracking")
    args = parser.parse_args()
    
    webhook_url = get_webhook_url()
    if not webhook_url:
        print(
            "ERROR: DISCORD_WEBHOOK_URL environment variable not set.",
            file=sys.stderr,
        )
        return 1

    # Generate job ID and start tracking
    job_id = generate_job_id()
    if not args.no_tracking:
        start_token_tracking(job_id, "scraper_notification")

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
            
            # Track test notification
            if not args.no_tracking:
                end_token_tracking(
                    job_id, 
                    items_processed=0,
                    message_length=len(test_payload["content"]),
                    notes="Test notification (force flag)"
                )
            return 0
        else:
            item_type = "in-stock" if args.include_in_stock else "just-landed"
            print(f"No {item_type} items — nothing to notify.")
            
            # Track empty run
            if not args.no_tracking:
                end_token_tracking(
                    job_id,
                    items_processed=0,
                    message_length=0,
                    notes=f"No {item_type} items found"
                )
            return 0

    item_type = "in-stock" if args.include_in_stock else "just-landed"
    print(f"Found {len(items)} {item_type} item(s):")
    for item in items:
        print(f"  [{item.get('_source_name')}] {item.get('title')}")

    try:
        message_length, items_processed = send_discord(webhook_url, items, include_in_stock=args.include_in_stock)
        print(f"Discord notification sent for {items_processed} item(s).")
        
        # Track successful notification
        if not args.no_tracking:
            end_token_tracking(
                job_id,
                items_processed=items_processed,
                message_length=message_length,
                notes=f"Sent {items_processed} {item_type} items to Discord"
            )
        
        return 0
    except Exception as e:
        print(f"❌ Failed to send Discord notification: {e}")
        
        # Track failed notification
        if not args.no_tracking:
            end_token_tracking(
                job_id,
                items_processed=len(items),
                message_length=0,
                notes=f"Failed: {str(e)[:100]}"
            )
        
        return 1


if __name__ == "__main__":
    sys.exit(main())