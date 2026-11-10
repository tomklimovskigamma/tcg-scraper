"""Read-only questions against the stock and market history.

    python3 -m pipeline.ask summary
    python3 -m pipeline.ask stock [text] [--store "Big W"]
    python3 -m pipeline.ask product <text>
    python3 -m pipeline.ask set <name>
    python3 -m pipeline.ask market
    python3 -m pipeline.ask events [--days 7]
    python3 -m pipeline.ask quests [--days 30]
    python3 -m pipeline.ask schema
    python3 -m pipeline.ask sql "SELECT ..."

Opens the database read-only; nothing here can change it. Add --json for raw rows.
All market figures are US TCGplayer prices converted to AUD: a guide, not
Australian resale value.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import messages
from .classify import TYPE_LABELS, normalize
from .history import History

DB = Path(__file__).resolve().parent.parent / "data" / "history.db"
STOCK_ROWS = 60  # specialist shops list hundreds of products
MARKET_TYPES = ["booster_box", "etb", "booster_bundle", "booster", "sleeved_booster"]


def _market_text(value: Optional[dict], shelf: Optional[float] = None) -> str:
    return messages.market_line(shelf, value) or "no US market match"


def _local(ts: str) -> str:
    dt = datetime.fromisoformat(ts)
    dt = dt.astimezone(messages.LOCAL_TZ) if messages.LOCAL_TZ else dt.astimezone()
    return dt.strftime("%a %d %b %H:%M")


def summary(h: History, now: datetime) -> dict:
    last = h.db.execute("SELECT MAX(ts) FROM runs WHERE ok = 1").fetchone()[0]
    day = h.run_stats(now - timedelta(hours=24), now + timedelta(seconds=1))
    stock = h.in_stock_now()
    by_store = {}
    for p in stock:
        by_store[p["store"]] = by_store.get(p["store"], 0) + 1
    return {
        "last_successful_scan": _local(last) if last else None,
        "in_stock_by_store": by_store,
        "scrapes_last_24h": day,
        "best_value": h.opportunities(),
        "hot_sets": h.hot_sets(),
        "set_calendar": h.set_calendar(now),
        "fx_usd_aud": h.latest_fx(),
    }


def stock(h: History, text: Optional[str], store: Optional[str]) -> list:
    rows = []
    for p in h.in_stock_now():
        if store and normalize(store) != normalize(p["store"]):
            continue
        if text and normalize(text) not in normalize(p["title"]):
            continue
        rows.append(dict(p, market=h.market_value(p.get("set_name"), p.get("ptype"))))
    return rows


def product(h: History, text: str) -> list:
    out = []
    for p in h._query("SELECT * FROM products ORDER BY store, title"):
        if normalize(text) not in normalize(p["title"]):
            continue
        events = h._query(
            "SELECT ts, kind, label, price, old_price, duration_min FROM events WHERE store = ? AND sku = ? "
            "AND baseline = 0 ORDER BY id DESC LIMIT 20", (p["store"], p["sku"]))
        out.append(dict(p, market=h.market_value(p.get("set_name"), p.get("ptype")), events=events))
    return out


def set_info(h: History, name: str) -> list:
    out = []
    for s in h._query("SELECT set_name, published_on FROM market_sets ORDER BY published_on"):
        if normalize(name) not in normalize(s["set_name"]):
            continue
        prices = {t: h.market_value(s["set_name"], t) for t in MARKET_TYPES}
        shelves = [p for p in h.in_stock_now() if p.get("set_name") and normalize(p["set_name"]) == normalize(s["set_name"])]
        out.append({"set_name": s["set_name"], "released": (s["published_on"] or "")[:10], "hot": h.is_hot_set(s["set_name"]),
                    "market": {t: v for t, v in prices.items() if v}, "on_shelves": shelves})
    return out


def market(h: History) -> list:
    rows = []
    for s in h._query("SELECT set_name, published_on FROM market_sets ORDER BY published_on DESC"):
        for t in MARKET_TYPES:
            v = h.market_value(s["set_name"], t)
            if v:
                rows.append({"set_name": s["set_name"], "released": (s["published_on"] or "")[:10], "ptype": t, **v})
    return rows


def run_sql(h: History, query: str) -> list:
    if not query.lstrip().lower().startswith(("select", "with")):
        raise ValueError("only SELECT queries are allowed")
    return [dict(r) for r in h.db.execute(query).fetchmany(200)]


def render(command: str, data, args) -> str:
    if command == "summary":
        d = data
        lines = [f"Last successful scan: {d['last_successful_scan'] or 'never'}",
                 "In stock now: " + (", ".join(f"{s} {n}" for s, n in d["in_stock_by_store"].items()) or "nothing"),
                 "Scrapes in the last 24h: " + (", ".join(
                     f"{s} {v['ok']} ok / {v['failed']} failed" for s, v in d["scrapes_last_24h"].items()) or "none")]
        if d["fx_usd_aud"]:
            lines.append(f"Exchange rate: US$1 = A${d['fx_usd_aud']:.4f}")
        lines.append("Hot sets (US market up 10%+ in 30 days): " + (", ".join(d["hot_sets"]) or "none"))
        for c in d["set_calendar"]:
            verb = "released" if c["status"] == "released" else "releases"
            lines.append(f"Set: {c['set_name']} {verb} {c['date']}")
        lines.append("Best value on shelves:" if d["best_value"] else "Best value on shelves: nothing is 5%+ under market")
        for o in d["best_value"]:
            also = f" (also {', '.join(o['also'])})" if o.get("also") else ""
            lines.append(f"  - {o['title']} | {o['store']} A${o['price']:.2f}{also} | "
                         f"{_market_text({'usd': o['usd'], 'aud': o['aud'], 'change_30d': o['change_30d']}, o['price'])}")
        return "\n".join(lines)
    if command == "stock":
        if not data:
            return "Nothing matching is in stock."
        shown = data[:STOCK_ROWS]
        more = (f"\n... and {len(data) - len(shown)} more. Narrow it with a search text or --store."
                if len(data) > len(shown) else "")
        return "\n".join(
            f"- {p['store']} | {TYPE_LABELS.get(p['ptype'], p['ptype'])} | {p['title']} | "
            f"A${p['price']:.2f} | {_market_text(p['market'], p['price'])} | {p['url'] or ''}"
            if p["price"] is not None else f"- {p['store']} | {p['title']} | {p['url'] or ''}" for p in shown) + more
    if command == "product":
        if not data:
            return "No product matches."
        lines = []
        for p in data:
            state = "IN STOCK" if p["in_stock"] else "not in stock"
            price = f"A${p['price']:.2f}" if p["price"] is not None else "no price"
            lines.append(f"{p['store']} | {p['title']} | {state} | {price} | first seen {_local(p['first_seen'])} | "
                         f"last seen {_local(p['last_seen'])} | {_market_text(p['market'], p['price'])}")
            for e in p["events"]:
                extra = (f"lasted {messages.duration(e['duration_min'])}" if e["kind"] == "disappeared" else
                         f"A${e['old_price']:.2f} -> A${e['price']:.2f}" if e["kind"] == "price" else (e["label"] or ""))
                lines.append(f"    {_local(e['ts'])}  {e['kind']}  {extra}")
            if not p["events"]:
                lines.append("    (no events since the baseline scan)")
        return "\n".join(lines)
    if command == "set":
        if not data:
            return "No set matches. Run `market` to list the sets the feed knows."
        lines = []
        for s in data:
            lines.append(f"{s['set_name']} | released {s['released']} | {'HOT' if s['hot'] else 'not hot'}")
            for t, v in s["market"].items():
                lines.append(f"    {TYPE_LABELS[t]}: {_market_text(v)} (as of {v['date']})")
            for p in s["on_shelves"]:
                lines.append(f"    on shelf: {p['store']} | {p['title']} | A${p['price']:.2f} | {p['url'] or ''}")
            if not s["on_shelves"]:
                lines.append("    on shelf: nothing at the tracked stores right now")
        return "\n".join(lines)
    if command == "market":
        return "\n".join(f"- {r['set_name']} ({r['released']}) | {TYPE_LABELS[r['ptype']]} | {_market_text(r)} | as of {r['date']}"
                         for r in data) or "No market data yet."
    if command == "events":
        return "\n".join(
            f"- {_local(e['ts'])} | {e['store']} | {e['kind']}{' ' + e['label'] if e['label'] else ''} | {e['title']} | "
            + (f"A${e['price']:.2f}" if e["price"] is not None else "") for e in data) or "No events in that period."
    if command == "quests":
        return "\n\n".join(f"#{q['id']} {_local(q['ts'])} | {q['asker'] or 'unknown'} | {q['status']}\nQ: {q['question']}\n"
                           f"A: {(q['answer'] or '').strip()[:1500]}" for q in data) or "No quests in that period."
    return json.dumps(data, indent=1, default=str)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.ask", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["summary", "stock", "product", "set", "market", "events", "quests", "schema", "sql"])
    ap.add_argument("text", nargs="?")
    ap.add_argument("--store")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not DB.exists():
        print("No history database yet.", file=sys.stderr)
        return 1
    h = History(DB, readonly=True)
    now = datetime.now(timezone.utc)
    try:
        if args.command in ("product", "set", "sql") and not args.text:
            print(f"`{args.command}` needs an argument.", file=sys.stderr)
            return 2
        if args.command == "summary":
            data = summary(h, now)
        elif args.command == "stock":
            data = stock(h, args.text, args.store)
        elif args.command == "product":
            data = product(h, args.text)
        elif args.command == "set":
            data = set_info(h, args.text)
        elif args.command == "market":
            data = market(h)
        elif args.command == "events":
            data = h.events_between(now - timedelta(days=args.days), now + timedelta(seconds=1))
        elif args.command == "quests":
            data = h._query("SELECT * FROM quests WHERE ts >= ? ORDER BY id DESC",
                            ((now - timedelta(days=max(args.days, 30))).isoformat(timespec="seconds"),))
        elif args.command == "schema":
            data = [r[0] for r in h.db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")]
            print("\n\n".join(data))
            return 0
        else:
            try:
                data = run_sql(h, args.text)
            except Exception as e:  # noqa: BLE001
                print(f"Query failed: {e}", file=sys.stderr)
                return 2
        print(json.dumps(data, indent=1, default=str) if args.json else render(args.command, data, args))
        return 0
    finally:
        h.close()


if __name__ == "__main__":
    raise SystemExit(main())
