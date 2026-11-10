"""Command line entry: `python3 -m pipeline.run scan|digest [--dry-run] [--no-scrape]`.

scan             run the scrapers, record history, post pings for high-demand arrivals
digest           post the daily summary
market-sync      fetch today's US market prices, release dates and exchange rate
market-backfill  load ~90 days of weekly market prices from the archive (run once)
market-chart     post the weekly market chart (needs matplotlib)

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

from . import discord, market, messages
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
        proc = subprocess.run([sys.executable, str(ROOT / script), "--no-js"], cwd=str(ROOT), capture_output=True,
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
    contexts = []
    for e in pending:
        context = history.ping_context(e)
        context["market"] = history.market_value(e.get("set_name"), e.get("ptype"))
        contexts.append((e, context))
    batches = messages.build_pings(contexts)
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
                                  history.run_stats(start, end), opportunities=history.opportunities(),
                                  sets=history.set_calendar(now), hot_sets=history.hot_sets())
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
    ap.add_argument("command", choices=["scan", "digest", "market-sync", "market-backfill", "market-chart"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-scrape", action="store_true")
    args = ap.parse_args(argv)

    DATA.mkdir(exist_ok=True)
    db_path = DATA / "history.db"
    tmp = None
    url = ""
    if args.dry_run:
        tmp = tempfile.TemporaryDirectory()
        scratch = Path(tmp.name) / "history.db"
        if db_path.exists():
            shutil.copy2(db_path, scratch)
        db_path = scratch

        def post(text: str) -> None:
            print(text + "\n" + "-" * 40)
    elif args.command in ("scan", "digest", "market-chart"):
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
        if args.command == "digest":
            return digest(history, post, now)
        if args.command == "market-sync":
            try:
                stored = market.sync(history, now)
            except Exception as e:  # noqa: BLE001
                print(f"Market sync failed ({type(e).__name__}: {e})", file=sys.stderr)
                log(f"market sync failed: {type(e).__name__}: {e}")
                return 1
            log(f"market sync: {stored} prices")
            return 0 if stored else 1
        if args.command == "market-backfill":
            stored = market.backfill(history, market.weekly_dates(now, 13), log)
            print(f"Backfilled {stored} prices.")
            return 0
        return market_chart(history, url, now, args.dry_run)
    finally:
        history.close()
        if tmp is not None:
            tmp.cleanup()


def market_chart(history: History, url: str, now: datetime, dry_run: bool) -> int:
    from . import chart  # imported here: only this command needs matplotlib

    local = now.astimezone(messages.LOCAL_TZ) if messages.LOCAL_TZ else now.astimezone()
    out = chart.render(history, DATA / "market-chart.png", local.date())
    if out is None:
        print("No market price data to chart; run market-sync first", file=sys.stderr)
        return 1
    text = chart.caption(history, local.date())
    if dry_run:
        print(text + f"\n[chart written to {out}]")
        return 0
    try:
        discord.post_file(url, text, out, "pokemon-market.png")
    except Exception as e:  # noqa: BLE001
        code = f" {e.code}" if hasattr(e, "code") else ""
        print(f"Discord post failed ({type(e).__name__}{code}); chart not sent", file=sys.stderr)
        log(f"chart post failed: {type(e).__name__}{code}")
        return 1
    print("Market chart posted.")
    log("market chart posted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
