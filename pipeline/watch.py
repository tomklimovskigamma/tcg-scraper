"""Personal watches: tell one person when a product they named arrives or drops under a price.

    python3 -m pipeline.watch add "delta reign etb" --under 80 --asker tom
    python3 -m pipeline.watch add "pitch black booster box" --store "Big W" --asker tom
    python3 -m pipeline.watch list --asker tom
    python3 -m pipeline.watch list --all
    python3 -m pipeline.watch remove 3 --asker tom

The scan (pipeline.run) does the matching and the telling. A watch stays active
until it is removed. Each person can hold MAX_WATCHES at a time.

Who is asking: the Discord user id is taken from the chat gateway's own record
of the latest message, never from the command line, so a watch can only
mention the person who actually asked for it. When no record matches the
`--asker` name, the watch is stored by name and alerts name the person in
plain text without notifying them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import messages
from .classify import TYPE_LABELS, parse_watch, watch_matches
from .history import MAX_WATCHES, History

DB = Path(__file__).resolve().parent.parent / "data" / "history.db"
SESSIONS = Path(os.environ.get("TCG_CHAT_SESSIONS") or Path.home() / ".openclaw/agents/main/sessions")
RECENT_SECONDS = 15 * 60
TAIL_BYTES = 400_000


def discord_sender(asker: str, sessions_dir: Path = SESSIONS, now: Optional[float] = None) -> Optional[dict]:
    """The Discord user who most recently wrote to the bot under the name `asker`, from the
    gateway's session records: {"id", "name"} or None. Read-only."""
    wanted = (asker or "").strip().casefold().lstrip("@")
    if not wanted:
        return None
    now = time.time() if now is None else now
    try:
        index = json.loads((sessions_dir / "sessions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    best = None
    for key, entry in index.items():
        if ":discord:" not in key or not isinstance(entry, dict):
            continue
        path = entry.get("sessionFile")
        if not path or now - (entry.get("updatedAt") or 0) / 1000 > RECENT_SECONDS:
            continue
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - TAIL_BYTES))
                lines = f.read().decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                message = json.loads(line).get("message") or {}
            except ValueError:
                continue
            meta = message.get("__openclaw") or {}
            if message.get("role") != "user" or not meta.get("senderId"):
                continue
            stamp = (message.get("timestamp") or 0) / 1000
            if now - stamp > RECENT_SECONDS:
                break
            names = {str(meta.get(k) or "").casefold() for k in ("senderName", "senderUsername")}
            if wanted in names and str(meta["senderId"]).isdigit() and (best is None or stamp > best[0]):
                best = (stamp, {"id": str(meta["senderId"]), "name": meta.get("senderName") or asker})
            break  # only the latest user message of each conversation counts
    return best[1] if best else None


def describe(w: dict) -> str:
    parts = [f"#{w['id']}", f"\"{w['text']}\""]
    if w.get("ptype"):
        parts.append(TYPE_LABELS.get(w["ptype"], w["ptype"]))
    if w.get("max_price") is not None:
        parts.append(f"under {messages.money(w['max_price'])}")
    if w.get("store"):
        parts.append(f"at {w['store']}")
    return " · ".join(parts)


def add(h: History, text: str, asker: str, user_id: Optional[str], max_price: Optional[float],
        store: Optional[str], now: datetime) -> tuple:
    """Returns (exit code, message)."""
    text = " ".join(text.split())[:120]
    terms, ptype = parse_watch(text)
    if not terms and not ptype:
        return 2, "That watch would match everything. Name a set or product, e.g. \"delta reign etb\"."
    if max_price is not None and max_price <= 0:
        return 2, "The price limit must be above zero."
    mine = h.watches(asker=asker, user_id=user_id)
    for w in mine:
        if (w["terms"], w["ptype"], w["max_price"], w["store"]) == (terms, ptype, max_price, store):
            return 0, f"Already watching: {describe(w)}"
    if len(mine) >= MAX_WATCHES:
        return 1, f"{asker} already has {MAX_WATCHES} watches, the limit. Remove one first (`list` shows them)."
    wid = h.add_watch(now, asker, user_id, text, terms, ptype, max_price, store)
    watch = {"id": wid, "text": text, "terms": terms, "ptype": ptype, "max_price": max_price, "store": store}
    lines = [f"Watch saved for {asker}: {describe(watch)}",
             "They will be mentioned in the channel when a match arrives" +
             (" or drops under the price." if max_price is not None else ".")]
    if not user_id:
        lines.append("(No Discord id found for that name, so alerts will name them without a notification.)")
    now_matching = [p for p in h.in_stock_now() if watch_matches(watch, p)]
    if now_matching:
        lines.append(f"In stock right now ({len(now_matching)}):")
        for p in sorted(now_matching, key=lambda p: (p["price"] is None, p["price"]))[:8]:
            lines.append(f"  - {p['store']} | {p['title']} | {messages.money(p['price']) or 'no price'} | {p['url'] or ''}")
    else:
        lines.append("Nothing matching is in stock right now.")
    return 0, "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.watch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["add", "list", "remove"])
    ap.add_argument("text", nargs="?", help="what to watch (add) or the watch number (remove)")
    ap.add_argument("--asker", help="display name of the person asking")
    ap.add_argument("--under", type=float, help="only when the shelf price is at or under this (AUD)")
    ap.add_argument("--store", help="only at this store")
    ap.add_argument("--all", action="store_true", help="list everyone's watches")
    args = ap.parse_args(argv)

    if args.command == "list" and args.all:
        asker, sender = "", None
    else:
        asker = (args.asker or "").strip().lstrip("@")[:40]
        if not asker:
            print("Say who is asking with --asker.", file=sys.stderr)
            return 2
        sender = discord_sender(asker)
    user_id = sender["id"] if sender else None

    DB.parent.mkdir(exist_ok=True)
    h = History(DB)
    try:
        if args.command == "add":
            if not args.text:
                print("Say what to watch.", file=sys.stderr)
                return 2
            code, text = add(h, args.text, asker, user_id, args.under, args.store, datetime.now(timezone.utc))
            print(text, file=sys.stderr if code else sys.stdout)
            return code
        if args.command == "list":
            rows = h.watches(everyone=True) if args.all else h.watches(asker=asker, user_id=user_id)
            if not rows:
                print("No active watches.")
            for w in rows:
                print(describe(w) + (f" · {w['asker']}" if args.all else ""))
            return 0
        mine = h.watches(asker=asker, user_id=user_id)
        wanted = (args.text or "").strip().lstrip("#")
        target = [w for w in mine if str(w["id"]) == wanted] or \
                 [w for w in mine if wanted and wanted.casefold() in w["text"].casefold()]
        if len(target) != 1:
            print("No single watch of theirs matches that. Their watches:" if mine else f"{asker} has no watches.",
                  file=sys.stderr)
            for w in mine:
                print("  " + describe(w), file=sys.stderr)
            return 1
        h.remove_watch(target[0]["id"])
        print(f"Removed: {describe(target[0])}")
        return 0
    finally:
        h.close()


if __name__ == "__main__":
    raise SystemExit(main())
