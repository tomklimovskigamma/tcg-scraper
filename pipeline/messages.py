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


def format_ping(event: dict, context: dict) -> str:
    head = _join([
        _LABELS.get(event.get("label"), _LABELS["restock"]),
        TYPE_LABELS.get(event.get("ptype"), "TCG"),
        f"**{money(event.get('price'))}**" if event.get("price") is not None else None,
        event.get("release_label") if event.get("label") == "preorder" else None,
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
    return "\n".join(lines)


def build_pings(pings_with_context) -> list:
    """[(event, context)] -> [(message text, [event ids])], few messages as possible."""
    blocks = [format_ping(e, c) for e, c in pings_with_context]
    ids = [e["id"] for e, _ in pings_with_context]
    return [("\n\n".join(blocks[i] for i in g), [ids[i] for i in g]) for g in _pack(blocks, "\n\n")]


def build_digest(day_label: str, events: list, in_stock: list, run_stats: dict) -> list:
    lines = [f"📋 **Pokémon TCG daily digest · {day_label}**"]
    total_runs = sum(s["ok"] + s["failed"] for s in run_stats.values())

    arrived = [e for e in events if e["kind"] == "appeared"]
    gone = [e for e in events if e["kind"] == "disappeared"]
    prices = [e for e in events if e["kind"] == "price"]
    gone_by_product = {(e["store"], e["sku"]): e for e in gone}

    if total_runs == 0:
        lines += ["", "⚠️ No scrapes ran today, so there is nothing to report."]
    elif not (arrived or gone or prices):
        lines += ["", "Nothing arrived, sold out or changed price today."]

    if arrived:
        lines += ["", f"**Arrived today ({len(arrived)})**"]
        for e in arrived:
            left = gone_by_product.get((e["store"], e["sku"]))
            if left is not None and left["ts"] >= e["ts"]:
                fate = f"gone after {duration(left.get('duration_min'))}"
            else:
                fate = "still in stock" if e.get("in_stock") else "gone"
            lines.append("• " + _join([local_time(e["ts"]), e["store"], short_title(e["title"]), money(e.get("price")), fate]))
    if gone:
        lines += ["", f"**Sold out today ({len(gone)})**"]
        for e in gone:
            lines.append("• " + _join([local_time(e["ts"]), e["store"], short_title(e["title"]),
                                       f"lasted {duration(e.get('duration_min'))}"]))
    if prices:
        lines += ["", f"**Price changes ({len(prices)})**"]
        for e in prices:
            lines.append("• " + _join([e["store"], short_title(e["title"]),
                                       f"{money(e.get('old_price'))} → {money(e.get('price'))}"]))

    if in_stock:
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

    health = []
    for store, s in run_stats.items():
        total = s["ok"] + s["failed"]
        if s["failed"] and not s["ok"]:
            health.append(f"⚠️ {store}: every scrape failed today ({total})")
        elif s["failed"]:
            health.append(f"⚠️ {store}: {s['failed']} of {total} scrapes failed")
    if health:
        lines += [""] + health

    chunks = ("\n".join(lines[i] for i in g).strip("\n") for g in _pack(lines, "\n"))
    return [c for c in chunks if c.strip()]
