"""Command line entry: `python3 -m pipeline.run scan|digest [--dry-run] [--no-scrape]`.

scan             run the scrapers, record history, post pings for high-demand arrivals
digest           post the daily summary
market-sync      fetch today's US market prices, release dates and exchange rate
market-backfill  load ~90 days of weekly market prices from the archive (run once)
market-chart     post the weekly market chart (needs matplotlib)

--dry-run   work on a throwaway copy of the history and print instead of posting
--no-scrape (scan only) read the existing data files instead of running scrapers
--quiet     (scan only) post only personal-watch alerts; other arrivals wait for the digest
--days N    (digest only) cover the last N days instead of today
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

# store label -> (scraper command, inventory file it writes)
STORES = {
    "JB Hi-Fi": (["scrape_jbhifi.py", "--no-js"], "inventory.json"),
    "Target": (["scrape_target.py", "--no-js"], "target_inventory.json"),
    "Kmart": (["scrape_kmart.py", "--no-js"], "kmart_inventory.json"),
    "Big W": (["scrape_bigw.py", "--no-js"], "bigw_inventory.json"),
    "Gameology": (["scrape_shopify.py", "--store", "gameology"], "gameology_inventory.json"),
    "Good Games": (["scrape_shopify.py", "--store", "goodgames"], "goodgames_inventory.json"),
    "Cherry Collectables": (["scrape_shopify.py", "--store", "cherry"], "cherry_inventory.json"),
}
# Specialist shops: deep back-catalogue, so only new and hot sets ping, and we check less often.
SPECIALIST = {"Gameology", "Good Games", "Cherry Collectables"}
SPECIALIST_INTERVAL_MIN = 14  # with a 5-minute scan this means every 15 minutes


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
    command, filename = STORES[store]
    path = DATA / filename
    before = path.stat().st_mtime_ns if path.exists() else 0
    try:
        proc = subprocess.run([sys.executable, str(ROOT / command[0])] + command[1:], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=SCRAPER_TIMEOUT)
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
         post: Optional[Callable[[str], None]], now: datetime, watchlist: Optional[Watchlist] = None,
         specialist: Iterable[str] = (), quiet: bool = False) -> int:
    """One scan cycle. `post=None` records events but sends nothing. `quiet` sends only
    personal-watch alerts; other arrivals wait for the digest. Returns an exit code."""
    stores = list(stores)
    specialist = set(specialist)
    ok = tried = 0
    for store in stores:
        if store in specialist:
            age = history.minutes_since_run(store, now)
            if age is not None and age < SPECIALIST_INTERVAL_MIN:
                continue
        tried += 1
        items = scrape(store)
        # A store that had stock and now lists nothing was almost certainly refused, not emptied.
        if items is None or (not items and history.stock_count(store)):
            if items is not None:
                log(f"scan {store}: listed nothing while stock is on record; counted as a failed run")
            history.record_failure(store, now)
            continue
        ok += 1
        events = history.apply_scan(store, items, now, watchlist, specialist=store in specialist)
        history.match_watches(events)
        kinds = ", ".join(f"{e['kind']}:{e['sku']}" for e in events[:40]) or "no change"
        log(f"scan {store}: {len(items)} listed; {len(events)} event(s): {kinds}")
    if tried and ok == 0:
        print("All scrapers failed this run; see pipeline.log", file=sys.stderr)
        return 1
    if post is None:
        return 0

    # One alert per event: a ping-tier arrival, a watched item, or both at once.
    pending = history.unposted_pings()
    if quiet:
        history.mark_posted([e["id"] for e in pending])
        pending = []
    hits = history.unposted_hits()
    watchers = {}
    for h in hits:
        watchers.setdefault(h["event"]["id"], []).append(h)
    entries = []
    for e in pending + [h["event"] for h in hits]:
        if any(e["id"] == done[0]["id"] for done in entries):
            continue
        context = history.ping_context(e)
        context["market"] = history.market_value(e.get("set_name"), e.get("ptype"))
        mine = watchers.get(e["id"], [])
        context["watchers"] = [h["watch"] for h in mine]
        token = ([e["id"]] if e["tier"] == "ping" and e["kind"] == "appeared" else [], [h["hit_id"] for h in mine])
        entries.append((e, context, token))
    batches = messages.build_alerts(entries)
    pending = entries
    sent = 0
    for text, tokens in batches:
        try:
            post(text)
        except Exception as e:  # noqa: BLE001 - any failure means "retry next scan"
            code = f" {e.code}" if hasattr(e, "code") else ""
            print(f"Discord post failed ({type(e).__name__}{code}); {len(pending) - sent} ping(s) "
                  "will be retried next scan", file=sys.stderr)
            log(f"post failed: {type(e).__name__}{code}")
            return 1
        history.mark_posted([i for event_ids, _ in tokens for i in event_ids])
        history.mark_hits_posted([i for _, hit_ids in tokens for i in hit_ids])
        sent += len(tokens)
    if sent:
        print(f"Pinged {sent} item(s) in {len(batches)} message(s).")
        log(f"pinged {sent} item(s)")
    return 0


def digest(history: History, post: Callable[[str], None], now: datetime, days: int = 1) -> int:
    """Post the summary of the last `days` local days, ending with the one `now` falls in."""
    local = now.astimezone(messages.LOCAL_TZ) if messages.LOCAL_TZ else now.astimezone()
    first = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max(days, 1) - 1)
    start = first.astimezone(timezone.utc)
    end = now.astimezone(timezone.utc) + timedelta(seconds=1)
    day_label = f"{local.strftime('%a')} {local.day} {local.strftime('%b')}"
    if days > 1:
        day_label = f"{first.strftime('%a')} {first.day} {first.strftime('%b')} to {day_label}"
    texts = messages.build_digest(day_label, history.events_between(start, end), history.in_stock_now(),
                                  history.run_stats(start, end), opportunities=history.opportunities(),
                                  sets=history.set_calendar(now), hot_sets=history.hot_sets(),
                                  specialist=SPECIALIST, watch_count=len(history.watches(everyone=True)),
                                  days=days)
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
    ap.add_argument("--quiet", action="store_true",
                    help="(scan) post only personal-watch alerts; everything else waits for the digest")
    ap.add_argument("--days", type=int, default=1, help="(digest) how many days to cover")
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
            return scan(history, STORES, scrape, post, now, load_watchlist(ROOT / "watchlist.txt"),
                        specialist=SPECIALIST, quiet=args.quiet)
        if args.command == "digest":
            return digest(history, post, now, days=args.days)
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
