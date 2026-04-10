#!/usr/bin/env python3
"""Run all Pokémon TCG scrapers then send Discord notifications for new stock.

Cron example (every 30 minutes):
  */30 * * * * cd /path/to/pokemon/jb-hifi && python3 run_all.py >> /tmp/pokemon_scraper.log 2>&1

If using a discord_webhook.txt file, no extra env vars needed.
If using environment variable:
  */30 * * * * cd /path/to/pokemon/jb-hifi && DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... python3 run_all.py >> /tmp/pokemon_scraper.log 2>&1
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
DATA_DIR = HERE / "data"

SCRAPERS = [
    HERE / "scrape_jbhifi.py",
    HERE / "scrape_target.py",
    HERE / "scrape_kmart.py",
    HERE / "scrape_bigw.py",
]

# Inventory file mappings
INVENTORY_FILES = {
    "jbhifi": DATA_DIR / "inventory.json",
    "target": DATA_DIR / "target_inventory.json",
    "kmart": DATA_DIR / "kmart_inventory.json",
    "bigw": DATA_DIR / "bigw_inventory.json",
}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)
    
    # Also log to run_log.txt
    log_file = Path("/Users/tomklimovski/clawd/run_log.txt")
    with open(log_file, "a") as f:
        f.write(f"{ts} - {msg}\n")


def run_scraper(path: Path) -> bool:
    log(f"Running {path.name}...")
    t0 = time.perf_counter()
    result = subprocess.run([PYTHON, str(path)], capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    
    if result.returncode != 0:
        log(f"  ✗ {path.name} failed (exit {result.returncode}) in {elapsed:.1f}s")
        if result.stderr:
            log(f"    Error: {result.stderr[:200]}...")
        return False
    
    # Check if scraper actually found items
    scraper_name = path.stem.replace("scrape_", "")
    inventory_file = INVENTORY_FILES.get(scraper_name)
    items_found = 0
    
    if inventory_file and inventory_file.exists():
        try:
            with open(inventory_file, "r") as f:
                data = json.load(f)
            items_found = len(data.get("in_stock", []))
            just_landed = len(data.get("just_landed", []))
            log(f"  ✓ {path.name} found {items_found} in-stock, {just_landed} just-landed items in {elapsed:.1f}s")
        except (json.JSONDecodeError, KeyError) as e:
            log(f"  ⚠ {path.name} done but couldn't parse output in {elapsed:.1f}s: {e}")
    else:
        log(f"  ✓ {path.name} done in {elapsed:.1f}s (no data file yet)")
    
    return True


def count_total_items() -> tuple[int, int]:
    """Count total in-stock and just-landed items across all retailers."""
    total_in_stock = 0
    total_just_landed = 0
    
    for inventory_file in INVENTORY_FILES.values():
        if inventory_file.exists():
            try:
                with open(inventory_file, "r") as f:
                    data = json.load(f)
                total_in_stock += len(data.get("in_stock", []))
                total_just_landed += len(data.get("just_landed", []))
            except (json.JSONDecodeError, KeyError):
                continue
    
    return total_in_stock, total_just_landed

def main() -> int:
    log("=== Pokémon TCG scraper run started ===")
    t_total = time.perf_counter()

    failed = []
    for scraper in SCRAPERS:
        ok = run_scraper(scraper)
        if not ok:
            failed.append(scraper.name)

    # Count total items
    total_in_stock, total_just_landed = count_total_items()
    
    # Log summary
    if total_in_stock > 0:
        log(f"Found {total_in_stock} total in-stock item(s) across all retailers")
    else:
        log("No in-stock items found")
        
    if total_just_landed > 0:
        log(f"Found {total_just_landed} just-landed item(s)")
    
    if failed:
        log(f"WARNING: {len(failed)} scraper(s) failed: {', '.join(failed)}")

    elapsed_total = time.perf_counter() - t_total
    log(f"=== Done in {elapsed_total:.1f}s ===")
    
    # Return 0 for success, 1 for partial failure, 2 for complete failure
    if len(failed) == len(SCRAPERS):
        return 2  # All scrapers failed
    elif failed:
        return 1  # Some scrapers failed
    else:
        return 0  # All scrapers succeeded


if __name__ == "__main__":
    raise SystemExit(main())
