#!/usr/bin/env python3
"""Run all Pokémon TCG scrapers then send Discord notifications for new stock.

Cron example (every 30 minutes):
  */30 * * * * cd /path/to/pokemon/jb-hifi && python3 run_all.py >> /tmp/pokemon_scraper.log 2>&1

If using a discord_webhook.txt file, no extra env vars needed.
If using environment variable:
  */30 * * * * cd /path/to/pokemon/jb-hifi && DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... python3 run_all.py >> /tmp/pokemon_scraper.log 2>&1
"""

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable

SCRAPERS = [
    HERE / "scrape_jbhifi.py",
    HERE / "scrape_target.py",
    HERE / "scrape_kmart.py",
    HERE / "scrape_bigw.py",
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def run_scraper(path: Path) -> bool:
    log(f"Running {path.name}...")
    t0 = time.perf_counter()
    result = subprocess.run([PYTHON, str(path)], capture_output=False)
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        log(f"  ✗ {path.name} failed (exit {result.returncode}) in {elapsed:.1f}s")
        return False
    log(f"  ✓ {path.name} done in {elapsed:.1f}s")
    return True


def main() -> int:
    log("=== Pokémon TCG scraper run started ===")
    t_total = time.perf_counter()

    failed = []
    for scraper in SCRAPERS:
        ok = run_scraper(scraper)
        if not ok:
            failed.append(scraper.name)

    if failed:
        log(f"WARNING: {len(failed)} scraper(s) failed: {', '.join(failed)}")

    elapsed_total = time.perf_counter() - t_total
    log(f"=== Done in {elapsed_total:.1f}s ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
