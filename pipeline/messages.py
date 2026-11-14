"""Turn events and stock into Discord message text. Pure functions."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Australia/Melbourne")
except Exception:  # pragma: no cover - zoneinfo data missing
    LOCAL_TZ = None

from .classify import TYPE_LABELS

LIMIT = 1900  # Discord rejects content over 2000 characters

_LABELS = {
    "restock": "🚨 **RESTOCK**",
    "new": "🆕 **NEW LISTING**",
    "preorder": "📅 **PRE-ORDER**",
    "drop": "💸 **PRICE DROP**",
}


def money(price: Optional[float]) -> Optional[str]:
    return None if price is None else f"${price:,.2f}"


def duration(minutes: Optional[int]) -> str:
    if minutes is None:
        return "an unknown time"
    if minutes < 5:
        return "under 5 min"
    if minutes < 60:
        return f"{minutes} min"
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {mins} min" if mins else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h" if hours else f"{days} d"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def local_time(ts: str) -> str:
    dt = datetime.fromisoformat(ts)
    return (dt.astimezone(LOCAL_TZ) if LOCAL_TZ else dt.astimezone()).strftime("%H:%M")


def local_date(ts: str) -> str:
    dt = datetime.fromisoformat(ts)
    return (dt.astimezone(LOCAL_TZ) if LOCAL_TZ else dt.astimezone()).strftime("%Y-%m-%d")


_PREFIX = re.compile(r"^pok[eé]mon\s+(?:tcg|trading card game)\s*[:\-\u2013\u2014]\s*", re.IGNORECASE)
_SUFFIX = re.compile(r"\s*(?:-\s*assorted)?\s*\*?\s*$", re.IGNORECASE)


def short_title(title: str) -> str:
    """Drop the 'Pokémon TCG:' prefix and '- Assorted*' suffix for compact digest lines."""
    short = _SUFFIX.sub("", _PREFIX.sub("", title.strip())).strip()
    return short[:150] if short else title.strip()[:150]


def _join(parts) -> str:
    return " · ".join(p for p in parts if p)


def _pack(blocks, sep: str) -> list:
    """Pack text blocks into as few messages as fit under LIMIT. Returns lists of block indexes."""
    groups, current, size = [], [], 0
    for i, block in enumerate(blocks):
        extra = len(block) + (len(sep) if current else 0)
        if current and size + extra > LIMIT:
            groups.append(current)
            current, size, extra = [], 0, len(block)
        current.append(i)
        size += extra
    if current:
        groups.append(current)
    return groups


def _amount(v: float) -> str:
    return f"{v:,.0f}" if v >= 20 else f"{v:,.2f}"


def trend_phrase(change: Optional[float]) -> Optional[str]:
    if change is None:
        return None
    if abs(change) < 0.03:
        return "flat over 30 days"
    return f"{'up' if change > 0 else 'down'} {abs(change):.0%} in 30 days"


def market_line(shelf: Optional[float], market: Optional[dict]) -> Optional[str]:
    """Compare an Australian shelf price with the US market price. The US figure is only a guide."""
    if not market or market.get("usd") is None:
        return None
    usd, aud = market["usd"], market.get("aud")
    trend = trend_phrase(market.get("change_30d"))
    tail = f", {trend}" if trend else ""
    if aud is None:
        return f"US market ≈ US${_amount(usd)}{tail}"
    head = f"US market ≈ A${_amount(aud)} (US${_amount(usd)}, converted){tail}"
    if shelf is None or aud <= 0:
        return head
    diff = (shelf - aud) / aud
    if abs(diff) < 0.05:
        return f"{head} · shelf price is about the same"
    return f"{head} · shelf price is {abs(diff):.0%} {'below' if diff < 0 else 'above'}"


def watcher_tag(watch: dict) -> str:
    """Who to tell, and which of their watches matched."""
    who = f"<@{watch['user_id']}>" if watch.get("user_id") else f"**{(watch.get('asker') or 'someone')[:40]}**"
    limit = f" under {money(watch['max_price'])}" if watch.get("max_price") is not None else ""
    return f"{who} (watching \"{watch['text'][:80]}\"{limit})"


def format_ping(event: dict, context: dict) -> str:
    drop = event.get("kind") == "price"
    price = f"**{money(event.get('price'))}**" if event.get("price") is not None else None
    if drop and price and event.get("old_price") is not None:
        price = f"{money(event['old_price'])} → {price}"
    head = _join([
        _LABELS["drop"] if drop else _LABELS.get(event.get("label"), _LABELS["restock"]),
        TYPE_LABELS.get(event.get("ptype"), "TCG"),
        price,
        event.get("release_label") if event.get("label") == "preorder" else None,
        "🔥 hot set" if context.get("hot") else None,
    ])
    where = _join([
        event["store"],
        f"<{event['url']}>" if event.get("url") else None,
        f"🛒 <{event['cart_url']}>" if event.get("cart_url") else None,
    ])
    lines = [head, f"**{event['title'][:400]}**", where]
    times = context.get("times_30d") or 0
    last = context.get("last_duration_min")
    history = _join([
        f"{ordinal(times)} time in stock in 30 days" if times > 1 else None,
        f"last time it sold out in {duration(last)}" if last is not None else None,
    ])
    if history:
        lines.append(history)
    market = market_line(event.get("price"), context.get("market"))
    if market:
        lines.append(market)
    if context.get("watchers"):
        lines.append("👀 " + ", ".join(watcher_tag(w) for w in context["watchers"]))
    return "\n".join(lines)


def build_alerts(entries) -> list:
    """[(event, context, token)] -> [(message text, [tokens])]; `token` is whatever the caller
    needs back to mark the entry as sent."""
    blocks = [format_ping(e, c) for e, c, _ in entries]
    return [("\n\n".join(blocks[i] for i in g), [entries[i][2] for i in g]) for g in _pack(blocks, "\n\n")]


def build_pings(pings_with_context) -> list:
    """[(event, context)] -> [(message text, [event ids])], few messages as possible."""
    blocks = [format_ping(e, c) for e, c in pings_with_context]
    ids = [e["id"] for e, _ in pings_with_context]
    return [("\n\n".join(blocks[i] for i in g), [ids[i] for i in g]) for g in _pack(blocks, "\n\n")]


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso[:10])
    return f"{d.day} {d.strftime('%b')}"


COMPACT_ROWS = 8


def _compact_changes(arrived: list, gone: list, prices: list) -> list:
    """Multi-day digest: one line per product, only what is still true at the end of the period."""
    lines = []
    latest = {}
    for e in arrived:
        latest[(e["store"], e["sku"])] = e
    here = [e for e in latest.values() if e.get("in_stock")]
    kept = [e for e in here if e.get("label") != "restock"]
    kept.sort(key=lambda e: e["ts"], reverse=True)
    if kept:
        lines += ["", f"**New listings still in stock ({len(kept)})**"]
        for e in kept[:COMPACT_ROWS]:
            lines.append("• " + _join([_day(local_date(e["ts"])), e["store"], short_title(e["title"]),
                                       money(e.get("price"))]))
        if len(kept) > COMPACT_ROWS:
            lines.append(f"…and {len(kept) - COMPACT_ROWS} more")
    back = len(here) - len(kept)
    passed = len(latest) - len(here)
    if back or passed:
        lines += ["", _join([f"{back} restocked and still in stock" if back else None,
                             f"{passed} came and went" if passed else None])]
    net = {}
    for e in prices:
        key = (e["store"], e["sku"])
        first = net[key]["old_price"] if key in net else e.get("old_price")
        net[key] = dict(e, old_price=first)
    moved = [e for e in net.values() if e.get("in_stock") and e.get("old_price") and e.get("price")
             and e["price"] < e["old_price"]]
    moved.sort(key=lambda e: e["price"] / e["old_price"])
    if moved:
        lines += ["", f"**Price drops ({len(moved)})**"]
        for e in moved[:COMPACT_ROWS]:
            lines.append("• " + _join([e["store"], short_title(e["title"]),
                                       f"{money(e['old_price'])} → {money(e['price'])}"]))
        if len(moved) > COMPACT_ROWS:
            lines.append(f"…and {len(moved) - COMPACT_ROWS} more")
    return lines


def build_digest(day_label: str, events: list, in_stock: list, run_stats: dict,
                 opportunities: Optional[list] = None, sets: Optional[list] = None,
                 hot_sets: Optional[list] = None, specialist: Optional[set] = None,
                 watch_count: int = 0, days: int = 1) -> list:
    lines = [f"📋 **Pokémon TCG {'daily digest' if days <= 1 else f'{days}-day digest'} · {day_label}**"]
    total_runs = sum(s["ok"] + s["failed"] for s in run_stats.values())

    arrived = [e for e in events if e["kind"] == "appeared"]
    gone = [e for e in events if e["kind"] == "disappeared"]
    prices = [e for e in events if e["kind"] == "price"]
    gone_by_product = {(e["store"], e["sku"]): e for e in gone}

    compact = days > 1
    when = "in this period" if compact else "today"
    if total_runs == 0:
        lines += ["", f"⚠️ No scrapes ran {when}, so there is nothing to report."]
    elif not (arrived or gone or prices):
        lines += ["", f"Nothing arrived, sold out or changed price {when}."]

    if compact:
        lines += _compact_changes(arrived, gone, prices)
    elif arrived:
        lines += ["", f"**Arrived today ({len(arrived)})**"]
        for e in arrived:
            left = gone_by_product.get((e["store"], e["sku"]))
            if left is not None and left["ts"] >= e["ts"]:
                fate = f"gone after {duration(left.get('duration_min'))}"
            else:
                fate = "still in stock" if e.get("in_stock") else "gone"
            lines.append("• " + _join([local_time(e["ts"]), e["store"], short_title(e["title"]), money(e.get("price")), fate]))
    if gone and not compact:
        lines += ["", f"**Sold out today ({len(gone)})**"]
        for e in gone:
            lines.append("• " + _join([local_time(e["ts"]), e["store"], short_title(e["title"]),
                                       f"lasted {duration(e.get('duration_min'))}"]))
    if prices and not compact:
        lines += ["", f"**Price changes ({len(prices)})**"]
        for e in prices:
            lines.append("• " + _join([e["store"], short_title(e["title"]),
                                       f"{money(e.get('old_price'))} → {money(e.get('price'))}"]))

    if opportunities:
        lines += ["", f"**Best value on shelves ({len(opportunities)})**"]
        for o in opportunities:
            title = short_title(o["title"])
            name = f"[{title}](<{o['url']}>)" if o.get("url") else title
            market = f"{o['discount']:.0%} under US market (A${_amount(o['aud'])})"
            trend = trend_phrase(o.get("change_30d"))
            lines.append("• " + _join([name, f"{o['store']} {money(o['price'])}",
                                       f"{market}, {trend}" if trend else market,
                                       "also at " + ", ".join(o["also"]) if o.get("also") else None]))

    # Specialist shops hold hundreds of lines: count them rather than list them.
    specialist = specialist or set()
    special_counts = {}
    for p in in_stock:
        if p["store"] in specialist:
            special_counts[p["store"]] = special_counts.get(p["store"], 0) + 1
    in_stock = [p for p in in_stock if p["store"] not in specialist]

    if compact and in_stock:
        counts = {}
        for p in in_stock:
            counts[p["store"]] = counts.get(p["store"], 0) + 1
        lines += ["", f"**In stock now ({len(in_stock)})**",
                  " · ".join(f"{store} {n}" for store, n in sorted(counts.items()))]
    elif in_stock:
        lines += ["", f"**In stock now ({len(in_stock)})**"]
        store = None
        for p in in_stock:
            if p["store"] != store:
                store = p["store"]
                lines.append(f"__{store}__")
            title = short_title(p["title"])
            name = f"[{title}](<{p['url']}>)" if p.get("url") else title
            lines.append("• " + _join([TYPE_LABELS.get(p.get("ptype"), "TCG"), name, money(p.get("price"))]))
    elif total_runs:
        lines += ["", "**In stock now (0)**"]
    if special_counts:
        lines += ["", "**Specialist stores**"]
        lines += [f"• {store}: {n} products in stock" for store, n in sorted(special_counts.items())]
        lines.append("Ask @gamma-ai what they have, or set a watch: \"@gamma-ai watch <product> under $<price>\"")
    if watch_count:
        lines += ["", f"👀 {watch_count} personal watch{'es' if watch_count != 1 else ''} active"]

    pings = "" if compact else ", so every product pings"
    watch = [f"• 🔥 {name}: US market up 10% or more in 30 days{pings}" for name in hot_sets or []]
    for c in sets or []:
        if c["status"] == "released":
            watch.append(f"• 🆕 {c['set_name']}: released {_day(c['date'])}" +
                         ("" if compact else f", every product pings until {_day(c['pings_until'])}"))
        else:
            watch.append(f"• 📅 {c['set_name']}: releases {_day(c['date'])}")
    if watch:
        lines += ["", "**Sets to watch**"] + watch

    health = []
    for store, s in run_stats.items():
        total = s["ok"] + s["failed"]
        if s["failed"] and not s["ok"]:
            health.append(f"⚠️ {store}: every scrape failed {when} ({total})")
        elif s["failed"] and (not compact or s["failed"] * 10 >= total):
            health.append(f"⚠️ {store}: {s['failed']} of {total} scrapes failed")
    if health:
        lines += [""] + health

    chunks = ("\n".join(lines[i] for i in g).strip("\n") for g in _pack(lines, "\n"))
    return [c for c in chunks if c.strip()]
