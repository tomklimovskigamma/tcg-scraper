"""Command line entry: `python3 -m pipeline.run scan|digest [--dry-run] [--no-scrape]`.

scan    run the scrapers, record history, post pings for high-demand arrivals
digest  post the daily summary

--dry-run   work on a throwaway copy of the history and print instead of posting
--no-scrape (scan only) read the existing data files instead of running scrapers
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import discord, messages
from .classify import Watchlist, load_watchlist
from .history import History

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOG = ROOT / "pipeline.log"
SCRAPER_TIMEOUT = 120

# store label -> (scraper script, inventory file it writes)
STORES = {
    "JB Hi-Fi": ("scrape_jbhifi.py", "inventory.json"),
    "Target": ("scrape_target.py", "target_inventory.json"),
    "Kmart": ("scrape_kmart.py", "kmart_inventory.json"),
    "Big W": ("scrape_bigw.py", "bigw_inventory.json"),
}


def log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def read_inventory(store: str) -> Optional[list]:
    """Items currently purchasable at `store` per its data file, or None if unreadable."""
    try:
        data = json.loads((DATA / STORES[store][1]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return list(data.get("in_stock") or []) + list(data.get("pre_orders") or [])


def scrape_store(store: str) -> Optional[list]:
    """Run one scraper. Returns its in-stock items, or None if it failed."""
    script, filename = STORES[store]
    path = DATA / filename
    before = path.stat().st_mtime_ns if path.exists() else 0
    try:
        proc = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=SCRAPER_TIMEOUT)
    except subprocess.TimeoutExpired:
        log(f"scrape {store}: timed out after {SCRAPER_TIMEOUT}s")
        return None
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
        log(f"scrape {store}: exit {proc.returncode}: {tail[0][:200]}")
        return None
    # A scraper that exits 0 without rewriting its file gave us nothing new to trust.
    if not path.exists() or path.stat().st_mtime_ns == before:
        log(f"scrape {store}: exit 0 but {filename} was not rewritten")
        return None
    return read_inventory(store)


def scan(history: History, stores: Iterable[str], scrape: Callable[[str], Optional[list]],
         post: Optional[Callable[[str], None]], now: datetime, watchlist: Optional[Watchlist] = None) -> int:
    """One scan cycle. `post=None` records events but sends nothing. Returns an exit code."""
    stores = list(stores)
    ok = 0
    for store in stores:
        items = scrape(store)
        if items is None:
            history.record_failure(store, now)
            continue
        ok += 1
        events = history.apply_scan(store, items, now, watchlist)
        kinds = ", ".join(f"{e['kind']}:{e['sku']}" for e in events) or "no change"
        log(f"scan {store}: {len(items)} listed; {kinds}")
    if stores and ok == 0:
        print("All scrapers failed this run; see pipeline.log", file=sys.stderr)
        return 1
    if post is None:
        return 0

    pending = history.unposted_pings()
    batches = messages.build_pings([(e, history.ping_context(e)) for e in pending])
    sent = 0
    for text, ids in batches:
        try:
            post(text)
        except Exception as e:  # noqa: BLE001 - any failure means "retry next scan"
            code = f" {e.code}" if hasattr(e, "code") else ""
            print(f"Discord post failed ({type(e).__name__}{code}); {len(pending) - sent} ping(s) "
                  "will be retried next scan", file=sys.stderr)
            log(f"post failed: {type(e).__name__}{code}")
            return 1
        history.mark_posted(ids)
        sent += len(ids)
    if sent:
        print(f"Pinged {sent} item(s) in {len(batches)} message(s).")
        log(f"pinged {sent} item(s)")
    return 0


def digest(history: History, post: Callable[[str], None], now: datetime) -> int:
    """Post the summary of the local day that `now` falls in. Returns an exit code."""
    local = now.astimezone(messages.LOCAL_TZ) if messages.LOCAL_TZ else now.astimezone()
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = now.astimezone(timezone.utc) + timedelta(seconds=1)
    day_label = f"{local.strftime('%a')} {local.day} {local.strftime('%b')}"
    texts = messages.build_digest(day_label, history.events_between(start, end), history.in_stock_now(),
                                  history.run_stats(start, end))
    for text in texts:
        try:
            post(text)
        except Exception as e:  # noqa: BLE001
            code = f" {e.code}" if hasattr(e, "code") else ""
            print(f"Discord post failed ({type(e).__name__}{code}); digest not fully sent", file=sys.stderr)
            log(f"digest post failed: {type(e).__name__}{code}")
            return 1
    print(f"Digest posted in {len(texts)} message(s).")
    log(f"digest posted ({len(texts)} message(s))")
    return 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["scan", "digest"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-scrape", action="store_true")
    args = ap.parse_args(argv)

    DATA.mkdir(exist_ok=True)
    db_path = DATA / "history.db"
    tmp = None
    if args.dry_run:
        tmp = tempfile.TemporaryDirectory()
        scratch = Path(tmp.name) / "history.db"
        if db_path.exists():
            shutil.copy2(db_path, scratch)
        db_path = scratch

        def post(text: str) -> None:
            print(text + "\n" + "-" * 40)
    else:
        url = discord.webhook_url(ROOT)
        if not url:
            print("No Discord webhook URL (DISCORD_WEBHOOK_URL or discord_webhook.txt)", file=sys.stderr)
            return 1

        def post(text: str) -> None:
            discord.post(url, text)

    history = History(db_path)
    now = datetime.now(timezone.utc)
    try:
        if args.command == "scan":
            scrape = read_inventory if args.no_scrape else scrape_store
            return scan(history, STORES, scrape, post, now, load_watchlist(ROOT / "watchlist.txt"))
        return digest(history, post, now)
    finally:
        history.close()
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
