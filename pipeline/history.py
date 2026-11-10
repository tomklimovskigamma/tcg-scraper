"""SQLite history: what was in stock, when it appeared, when it went, at what price.

`apply_scan` is the only writer of stock state. It turns one store's current
in-stock list into events and returns them.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Union

from .classify import Watchlist, base_tier, classify

NEW_SET_DAYS = 90
MISSES_UNTIL_GONE = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    store TEXT NOT NULL, sku TEXT NOT NULL,
    title TEXT, url TEXT, cart_url TEXT, release_label TEXT,
    ptype TEXT, set_name TEXT, tier TEXT, price REAL,
    in_stock INTEGER NOT NULL DEFAULT 1, misses INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT, since TEXT, last_seen TEXT,
    PRIMARY KEY (store, sku)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, store TEXT NOT NULL, sku TEXT NOT NULL,
    kind TEXT NOT NULL, label TEXT, tier TEXT,
    price REAL, old_price REAL, duration_min INTEGER,
    baseline INTEGER NOT NULL DEFAULT 0, posted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS events_product ON events (store, sku, ts);
CREATE TABLE IF NOT EXISTS sets (name TEXT PRIMARY KEY, first_seen TEXT, baseline INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS runs (ts TEXT NOT NULL, store TEXT NOT NULL, ok INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS runs_store ON runs (store, ts);
"""

_EVENT_COLS = (
    "e.id, e.ts, e.store, e.sku, e.kind, e.label, e.tier, e.price, e.old_price, e.duration_min, "
    "e.baseline, e.posted, p.title, p.url, p.cart_url, p.release_label, p.ptype, p.set_name, p.in_stock"
)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _key(item: dict) -> str:
    return str(item.get("sku") or item.get("handle") or item.get("url") or item.get("title"))


def _price(item: dict) -> Optional[float]:
    for k in ("price_aud", "price"):
        v = item.get(k)
        if v not in (None, ""):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return None
    return None


class History:
    def __init__(self, path: Union[str, Path]):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    def close(self) -> None:
        self.db.close()

    # ── writes ──────────────────────────────────────────────────────────────
    def record_failure(self, store: str, now: datetime) -> None:
        """A scraper failed: note it and touch nothing else."""
        with self.db:
            self.db.execute("INSERT INTO runs (ts, store, ok) VALUES (?, ?, 0)", (_iso(now), store))

    def apply_scan(self, store: str, items: Iterable[dict], now: datetime,
                   watchlist: Optional[Watchlist] = None) -> list:
        """Record one successful scrape of `store`; return the events it produced."""
        wl = watchlist or Watchlist()
        ts = _iso(now)
        new_ids = []
        with self.db:
            baseline = 0 if self.db.execute(
                "SELECT 1 FROM runs WHERE store = ? AND ok = 1 LIMIT 1", (store,)).fetchone() else 1
            self.db.execute("INSERT INTO runs (ts, store, ok) VALUES (?, ?, 1)", (ts, store))

            seen = set()
            for item in items:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                c = classify(title)
                override = wl.override(title)
                if override == "ignore" or base_tier(c.ptype) == "ignore":
                    continue
                sku = _key(item)
                if sku in seen:
                    continue
                seen.add(sku)
                tier = override or self._tier(c.ptype, c.set_name, now, baseline)
                price = _price(item)
                preorder = str(item.get("status") or "").lower().startswith("pre")
                row = self.db.execute(
                    "SELECT * FROM products WHERE store = ? AND sku = ?", (store, sku)).fetchone()
                details = (title, item.get("url"), item.get("cart_url"), item.get("release_label") or None,
                           c.ptype, c.set_name, tier)
                if row is None:
                    self.db.execute(
                        "INSERT INTO products (title, url, cart_url, release_label, ptype, set_name, tier, "
                        "price, in_stock, misses, first_seen, since, last_seen, store, sku) "
                        "VALUES (?,?,?,?,?,?,?,?,1,0,?,?,?,?,?)",
                        details + (price, ts, ts, ts, store, sku))
                    new_ids.append(self._event(ts, store, sku, "appeared", "preorder" if preorder else "new",
                                               tier, price, baseline=baseline))
                    continue
                self.db.execute(
                    "UPDATE products SET title=?, url=?, cart_url=?, release_label=?, ptype=?, set_name=?, tier=?, "
                    "misses=0, last_seen=? WHERE store=? AND sku=?", details + (ts, store, sku))
                if not row["in_stock"]:
                    self.db.execute("UPDATE products SET in_stock=1, since=?, price=? WHERE store=? AND sku=?",
                                    (ts, price, store, sku))
                    new_ids.append(self._event(ts, store, sku, "appeared", "preorder" if preorder else "restock",
                                               tier, price))
                elif price is not None and row["price"] is not None and abs(price - row["price"]) >= 0.01:
                    self.db.execute("UPDATE products SET price=? WHERE store=? AND sku=?", (price, store, sku))
                    new_ids.append(self._event(ts, store, sku, "price", None, tier, price, old_price=row["price"]))
                elif price is not None and row["price"] is None:
                    self.db.execute("UPDATE products SET price=? WHERE store=? AND sku=?", (price, store, sku))

            for row in self.db.execute(
                    "SELECT sku, misses, since, tier, price FROM products WHERE store = ? AND in_stock = 1",
                    (store,)).fetchall():
                if row["sku"] in seen:
                    continue
                misses = row["misses"] + 1
                if misses < MISSES_UNTIL_GONE:
                    self.db.execute("UPDATE products SET misses=? WHERE store=? AND sku=?",
                                    (misses, store, row["sku"]))
                    continue
                duration = None
                if row["since"]:
                    duration = int((now - datetime.fromisoformat(row["since"])).total_seconds() // 60)
                self.db.execute("UPDATE products SET in_stock=0, misses=0 WHERE store=? AND sku=?",
                                (store, row["sku"]))
                new_ids.append(self._event(ts, store, row["sku"], "disappeared", None, row["tier"], row["price"],
                                           duration_min=duration))
        return self._events_by_id(new_ids)

    def mark_posted(self, ids: Iterable[int]) -> None:
        with self.db:
            self.db.executemany("UPDATE events SET posted = 1 WHERE id = ?", [(i,) for i in ids])

    # ── reads ───────────────────────────────────────────────────────────────
    def unposted_pings(self) -> list:
        return self._query(
            f"SELECT {_EVENT_COLS} FROM events e JOIN products p ON p.store = e.store AND p.sku = e.sku "
            "WHERE e.kind = 'appeared' AND e.tier = 'ping' AND e.posted = 0 AND e.baseline = 0 ORDER BY e.id")

    def ping_context(self, event: dict) -> dict:
        """How often this product has come into stock lately, and how long the last stint lasted."""
        ts = datetime.fromisoformat(event["ts"])
        since = _iso(ts - timedelta(days=30))
        times = self.db.execute(
            "SELECT COUNT(*) FROM events WHERE store=? AND sku=? AND kind='appeared' AND baseline=0 "
            "AND ts > ? AND ts <= ?", (event["store"], event["sku"], since, event["ts"])).fetchone()[0]
        last = self.db.execute(
            "SELECT duration_min FROM events WHERE store=? AND sku=? AND kind='disappeared' AND ts <= ? "
            "ORDER BY id DESC LIMIT 1", (event["store"], event["sku"], event["ts"])).fetchone()
        return {"times_30d": times, "last_duration_min": last[0] if last else None}

    def events_between(self, start: datetime, end: datetime) -> list:
        return self._query(
            f"SELECT {_EVENT_COLS} FROM events e JOIN products p ON p.store = e.store AND p.sku = e.sku "
            "WHERE e.baseline = 0 AND e.ts >= ? AND e.ts < ? ORDER BY e.id", (_iso(start), _iso(end)))

    def in_stock_now(self) -> list:
        return self._query(
            "SELECT store, sku, title, url, cart_url, ptype, set_name, tier, price, since FROM products "
            "WHERE in_stock = 1 ORDER BY store, ptype, title")

    def run_stats(self, start: datetime, end: datetime) -> dict:
        out = {}
        for r in self.db.execute(
                "SELECT store, SUM(ok) AS ok, SUM(1 - ok) AS failed FROM runs WHERE ts >= ? AND ts < ? "
                "GROUP BY store ORDER BY store", (_iso(start), _iso(end))):
            out[r["store"]] = {"ok": r["ok"], "failed": r["failed"]}
        return out

    # ── internals ───────────────────────────────────────────────────────────
    def _tier(self, ptype: str, set_name: Optional[str], now: datetime, baseline: int) -> str:
        new_set = False
        if set_name:
            row = self.db.execute("SELECT first_seen, baseline FROM sets WHERE name = ?", (set_name,)).fetchone()
            if row is None:
                self.db.execute("INSERT INTO sets (name, first_seen, baseline) VALUES (?, ?, ?)",
                                (set_name, _iso(now), baseline))
                new_set = not baseline
            elif not row["baseline"]:
                new_set = now - datetime.fromisoformat(row["first_seen"]) <= timedelta(days=NEW_SET_DAYS)
        return "ping" if new_set else base_tier(ptype)

    def _event(self, ts, store, sku, kind, label, tier, price, old_price=None, duration_min=None, baseline=0) -> int:
        cur = self.db.execute(
            "INSERT INTO events (ts, store, sku, kind, label, tier, price, old_price, duration_min, baseline, posted) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts, store, sku, kind, label, tier, price, old_price, duration_min, baseline, 1 if baseline else 0))
        return cur.lastrowid

    def _events_by_id(self, ids: list) -> list:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self._query(
            f"SELECT {_EVENT_COLS} FROM events e JOIN products p ON p.store = e.store AND p.sku = e.sku "
            f"WHERE e.id IN ({marks}) ORDER BY e.id", ids)

    def _query(self, sql: str, params: Iterable = ()) -> list:
        return [dict(r) for r in self.db.execute(sql, tuple(params)).fetchall()]
