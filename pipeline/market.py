"""US market prices and release dates for sealed product, from TCGCSV.

TCGCSV (https://tcgcsv.com) is a community mirror of TCGplayer's data, refreshed
once a day around 20:00 UTC. We fetch it once a day, for current sets only, with
an identifiable User-Agent as its usage guidelines ask.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from .classify import normalize
from .history import History

BASE = "https://tcgcsv.com/tcgplayer/3"  # category 3 = Pokémon
ARCHIVE = "https://tcgcsv.com/archive/tcgplayer/prices-{date}.ppmd.7z"
FX_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=AUD"
USER_AGENT = "tcg-scraper/1.0 (personal stock alert; daily fetch)"
MAX_SET_AGE_DAYS = 500

_GROUP = re.compile(r"^(?:ME|SV)\w*:\s*(.+)$")
_SKIP_GROUP = ("promo", "energies")
_MARKET_TYPES = {
    "booster box": "booster_box",
    "elite trainer box": "etb",
    "booster bundle": "booster_bundle",
    "booster pack": "booster",
    "sleeved booster pack": "sleeved_booster",
}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def select_groups(groups: list, now: datetime) -> list:
    """Main-series sets released recently enough to matter, oldest first."""
    picked = []
    for g in groups:
        m = _GROUP.match(g.get("name") or "")
        if not m or any(k in g["name"].lower() for k in _SKIP_GROUP):
            continue
        published = (g.get("publishedOn") or "")[:10]
        if not published:
            continue
        age = now.date() - datetime.fromisoformat(published).date()
        if age > timedelta(days=MAX_SET_AGE_DAYS):
            continue
        picked.append({"groupId": g["groupId"], "set_name": m.group(1).strip(), "published_on": published})
    return sorted(picked, key=lambda g: g["published_on"])


def market_ptype(name: str, set_name: str) -> Optional[str]:
    """Product type for a market listing, only for the plain '<Set> <Type>' products."""
    n = normalize(re.sub(r"\s*\[[^\]]*\]\s*$", "", name))
    s = normalize(set_name)
    if not n.startswith(s + " "):
        return None
    return _MARKET_TYPES.get(n[len(s):].strip())


def _prices(payload) -> dict:
    out = {}
    for row in payload.get("results") or []:
        price = row.get("marketPrice")
        if price is not None and row.get("productId") not in out:
            out[row["productId"]] = price
    return out


def sync(history: History, now: datetime, fetch: Callable = fetch_json) -> int:
    """Store today's market prices, release dates and exchange rate. Returns prices stored."""
    date = now.date().isoformat()
    stored = 0
    for g in select_groups(fetch(f"{BASE}/groups").get("results") or [], now):
        history.upsert_market_set(g["set_name"], g["groupId"], g["published_on"])
        products = fetch(f"{BASE}/{g['groupId']}/products").get("results") or []
        prices = _prices(fetch(f"{BASE}/{g['groupId']}/prices"))
        for p in products:
            ptype = market_ptype(p.get("name") or "", g["set_name"])
            if not ptype:
                continue
            history.upsert_market_product(p["productId"], g["groupId"], g["set_name"], p["name"], ptype, p.get("url"))
            if p["productId"] in prices:
                history.add_market_price(date, p["productId"], prices[p["productId"]])
                stored += 1
    try:
        rate = fetch(FX_URL)["rates"]["AUD"]
        history.set_fx(date, rate)
    except Exception:  # noqa: BLE001 - keep yesterday's rate
        pass
    return stored


def weekly_dates(now: datetime, weeks: int) -> list:
    return [(now.date() - timedelta(days=7 * k)).isoformat() for k in range(weeks, 0, -1)]


def backfill(history: History, dates: list, log: Callable = print) -> int:
    """Load past prices from TCGCSV's daily archive (one ~4 MB download per date). Run sync first."""
    groups = [r[0] for r in history.db.execute("SELECT group_id FROM market_sets")]
    stored = 0
    with tempfile.TemporaryDirectory() as tmp:
        for date in dates:
            archive = Path(tmp) / f"{date}.7z"
            try:
                req = urllib.request.Request(ARCHIVE.format(date=date), headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=120) as r:
                    archive.write_bytes(r.read())
            except Exception as e:  # noqa: BLE001
                log(f"backfill {date}: download failed ({type(e).__name__})")
                continue
            day = 0
            for gid in groups:
                wanted = set(history.market_product_ids(gid))
                proc = subprocess.run(["bsdtar", "-xOf", str(archive), f"{date}/3/{gid}/prices"],
                                      capture_output=True)
                if proc.returncode != 0 or not proc.stdout:
                    continue  # set not released yet on that date
                try:
                    prices = _prices(json.loads(proc.stdout))
                except ValueError:
                    continue
                for pid, usd in prices.items():
                    if pid in wanted:
                        history.add_market_price(date, pid, usd)
                        day += 1
            archive.unlink()
            log(f"backfill {date}: {day} prices")
            stored += day
    return stored
