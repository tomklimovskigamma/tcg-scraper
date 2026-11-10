"""Classify a product title: product type, set name, and base tier.

Pure functions, no I/O apart from `load_watchlist`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PING_TYPES = {"booster_box", "etb", "booster_bundle", "collection", "tin"}
IGNORE_TYPES = {"not_tcg", "accessory"}

TYPE_LABELS = {
    "booster_box": "Booster Box",
    "etb": "Elite Trainer Box",
    "booster_bundle": "Booster Bundle",
    "collection": "Collection",
    "tin": "Tin",
    "deck": "Deck",
    "blister": "Blister",
    "sleeved_booster": "Sleeved Booster",
    "booster": "Booster Pack",
    "other_tcg": "TCG",
    "accessory": "Accessory",
    "not_tcg": "Not TCG",
}

# Things that carry the Pokémon brand but are not the card game.
_NOT_TCG = (
    "socks", "trunks", "rash", "swim", "pyjama", "pajama", "t-shirt", "tee ", "hoodie",
    "brief", "underwear", "plush", "figure", "pokemon select", "christmas", "costume",
    "backpack", "lunch", "bottle", "puzzle", "lego", "mega construx", "bedding", "quilt",
    "towel", "slipper", "cap ", "beanie",
)
_TCG_MARKERS = (
    "tcg", "trading card", "booster", "elite trainer", "blister", "battle deck",
    "premium collection", "collection box", "display box",
)
_ACCESSORY = (
    "protector", "sleeves", "portfolio", "binder", "playmat", "play mat", "deck box",
    "toolkit", "album", "card holder", "holder case", "storage", "acrylic", "dice",
)
# Ordered: first match wins.
_TYPE_RULES = (
    ("booster_box", ("booster box", "display box", "booster display")),
    ("etb", ("elite trainer box", " etb")),
    ("booster_bundle", ("booster bundle",)),
    ("collection", ("collection",)),
    ("tin", (" tin", "tin ")),
    ("deck", (" deck",)),
    ("blister", ("blister",)),
    ("sleeved_booster", ("sleeved booster",)),
    ("booster", ("booster",)),
)

_SERIES = r"(mega evolutions?|scarlet (?:&|and) violet|sword (?:&|and) shield|sun (?:&|and) moon)"
# Words that end a set name: where the product description starts.
_SET_STOP = {
    "booster", "blister", "blisters", "sleeved", "checklane", "display", "elite", "premium",
    "collection", "tin", "mini", "bundle", "deck", "three", "two", "pack", "box", "assorted",
    "etb", "league", "battle", "ex", "single", "triple",
}


@dataclass(frozen=True)
class Classified:
    ptype: str
    set_name: Optional[str]


def normalize(title: str) -> str:
    """Lower-case, strip accents, turn dashes and punctuation into spaces."""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[‒-―\-:*,()]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _ptype(norm: str) -> str:
    padded = f" {norm} "
    if any(k in padded for k in _NOT_TCG):
        return "not_tcg"
    if any(k in padded for k in _ACCESSORY):
        return "accessory"
    if not any(k in padded for k in _TCG_MARKERS):
        return "not_tcg"
    for ptype, keys in _TYPE_RULES:
        if any(k in padded for k in keys):
            return ptype
    return "other_tcg"


def _set_name(norm: str) -> Optional[str]:
    m = re.search(_SERIES + r"(?:\s+\d+)?\b", norm)
    if not m:
        return None
    words = []
    for w in norm[m.end():].split():
        if w in _SET_STOP or w.isdigit():
            break
        words.append(w)
    name = " ".join(words) if words else m.group(1).rstrip("s")
    return name.title()


def classify(title: str) -> Classified:
    norm = normalize(title)
    ptype = _ptype(norm)
    return Classified(ptype, None if ptype in IGNORE_TYPES else _set_name(norm))


def base_tier(ptype: str) -> str:
    if ptype in IGNORE_TYPES:
        return "ignore"
    return "ping" if ptype in PING_TYPES else "digest"


@dataclass
class Watchlist:
    always: list = field(default_factory=list)
    never: list = field(default_factory=list)
    ignore: list = field(default_factory=list)

    def override(self, title: str) -> Optional[str]:
        """Tier forced by the watchlist, or None. ignore beats never beats always."""
        norm = normalize(title)
        if any(k in norm for k in self.ignore):
            return "ignore"
        if any(k in norm for k in self.never):
            return "digest"
        if any(k in norm for k in self.always):
            return "ping"
        return None


def parse_watchlist(text: str) -> Watchlist:
    wl = Watchlist()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        kind, _, keyword = line.partition(":")
        keyword = normalize(keyword)
        bucket = {"always": wl.always, "never": wl.never, "ignore": wl.ignore}.get(kind.strip().lower())
        if bucket is not None and keyword:
            bucket.append(keyword)
    return wl


def load_watchlist(path: Path) -> Watchlist:
    try:
        return parse_watchlist(path.read_text(encoding="utf-8"))
    except OSError:
        return Watchlist()


# ── personal watches ────────────────────────────────────────────────────────
# Words that describe the product type or are filler; the rest of a watch must appear in the title.
_WATCH_FILLER = {
    "pokemon", "tcg", "trading", "card", "cards", "game", "the", "a", "an", "any", "for", "of", "and",
    "elite", "trainer", "etb", "etbs", "box", "boxes", "booster", "boosters", "bundle", "bundles", "pack",
    "packs", "tin", "tins", "collection", "collections", "blister", "blisters", "deck", "decks", "sleeved",
    "display", "premium",
}


def parse_watch(text: str) -> tuple:
    """A watch request -> (terms, ptype). `terms` are the words a title must contain;
    `ptype` is the product type the request names, or None for any type."""
    norm = normalize(text)
    padded = f" {norm} "
    for plural, singular in ((" etbs ", " etb "), (" boxes ", " box "), (" bundles ", " bundle "), (" tins ", " tin "),
                             (" decks ", " deck "), (" blisters ", " blister "), (" boosters ", " booster "),
                             (" packs ", " pack "), (" collections ", " collection ")):
        padded = padded.replace(plural, singular)
    ptype = None
    for name, keys in _TYPE_RULES:
        if any(k in padded for k in keys):
            ptype = name
            break
    terms = [w for w in norm.split() if w not in _WATCH_FILLER]
    return " ".join(terms), ptype


def watch_matches(watch: dict, product: dict) -> bool:
    """Does a product (or an event carrying product fields) satisfy a watch?"""
    if watch.get("ptype") and product.get("ptype") != watch["ptype"]:
        return False
    if watch.get("store") and normalize(watch["store"]) not in normalize(product.get("store") or ""):
        return False
    price = product.get("price")
    if watch.get("max_price") is not None and price is not None and price > watch["max_price"] + 0.005:
        return False
    padded = f" {normalize(product.get('title') or '')} "
    return all(f" {t} " in padded for t in (watch.get("terms") or "").split())
