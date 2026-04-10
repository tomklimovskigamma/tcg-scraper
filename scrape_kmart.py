#!/usr/bin/env python3
"""
Scrape Kmart Australia Pokemon TCG listings via the Constructor.io search API.
Only fetches purchasable products (what the Constructor API returns = orderable).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

API_KEY = "key_GZTqlLr41FS2p7AY"
API_BASE = "https://ac.cnstrc.com/search"
KMART_BASE = "https://www.kmart.com.au"

SEARCH_QUERIES = [
    "pokemon cards",
    "pokemon tcg",
    "pokemon booster",
]

EXCLUDE_TITLE_SUBSTRINGS = (
    "nanoblock",
    "switch",
    "plush",
    "figure",
    "model kit",
    "mug",
    "cup",
    "party",
    "costume",
    "umbrella",
    "lego",
    "funko",
    "vinyl",
    "sticker",
    "clip",
    "belt",
    "shirt",
    "sock",
    "hat",
    "cap",
    "pillow",
    "cushion",
    "backpack",
    "pencil",
    "eraser",
    "notebook",
    # Non-card Pokémon products
    " book",
    "activity",
    "trivia",
    "guessing",
    "guidebook",
    "handbook",
    "puzzle",
    "searchlight",
    "dot-to-dot",
    "trivia game",
    "trainer guess",
    "travel",
    "video game",
    "ultra pro",
    "portafolio",
    "portfolio"
)

# Title must contain at least one of these to be considered a TCG product
CARD_KEYWORDS = (
    "trading card",
    "tcg",
    "booster",
    " tin",
    "elite trainer",
    "trainer box",
    "binder",
    "sleeve",
    "portfolio",
    "collection",
    " deck",
    "blister",
    "bundle",
    "one touch",
    "card holder",
    "pocket page",
    "pocket portfolio",
    "card game",
)


def is_card_related(title: str, national_inventory: bool, price: float | None, fc: int | None) -> bool:
    """Only keep Pokémon TCG products purchasable online (not in-store only).

    FulfilmentChannel values:
      1 = in-store only (never has "+ Add" button)
      2 = standard Kmart stock — fluctuates between online / in-store dynamically
      3 = marketplace seller — always available for online delivery (has "+ Add")
      5 = marketplace seller — always available for online delivery (has "+ Add")

    We only include FC=3 and FC=5 because those are the only ones guaranteed to
    show the blue "+ Add" button for delivery. FC=2 items switch between
    "Online only" and "In store only" unpredictably.
    """
    if fc not in (3, 5):
        return False
    t = title.lower()
    # Must explicitly mention Pokémon — rules out One Piece, Dragon Ball, LoL, etc.
    if "pokemon" not in t:
        return False
    # Must be a TCG / card game product (not books, games, puzzles, etc.)
    if not any(k in t for k in CARD_KEYWORDS):
        return False
    # Drop excluded categories
    if any(bad in t for bad in EXCLUDE_TITLE_SUBSTRINGS):
        return False
    # Booster DISPLAY BOXES (wholesale cases ~36 packs) are almost always in-store only.
    # They appear at $150+ and contain "booster" but not "bundle", "blister", or "box" in title.
    if price and price >= 150 and "booster" in t and not any(k in t for k in ("bundle", " box", "blister", "collection", "elite")):
        return False
    return True


def fetch_page(query: str, page: int, num: int = 60) -> dict:
    # "Available in NSW=True" is the filter Kmart's own site uses for the recommendations
    # pod. It reliably excludes "In store only" items — only products orderable for
    # delivery in NSW are returned, matching the ones with the blue "+ Add" button.
    url = (
        f"{API_BASE}/{quote(query)}"
        f"?key={API_KEY}"
        f"&num_results_per_page={num}"
        f"&page={page}"
        f"&sort_by=relevance"
        f"&sort_order=descending"
        f"&filters%5BAvailable%20in%20VIC%5D=True"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def scrape_query(query: str) -> list[dict]:
    try:
        first = fetch_page(query, 1)
    except requests.RequestException as e:
        print(f"  [{query}] fetch error: {e}", file=sys.stderr)
        return []

    resp = first.get("response", {})
    total = resp.get("total_num_results", 0)
    raw_results = resp.get("results", [])

    # Fetch remaining pages if needed (60 per page)
    pages = (total + 59) // 60
    for p in range(2, min(pages + 1, 6)):  # cap at 5 pages = 300 results
        try:
            page_data = fetch_page(query, p)
            raw_results.extend(page_data.get("response", {}).get("results", []))
        except requests.RequestException:
            break

    return raw_results


def build_row(item: dict) -> dict | None:
    data = item.get("data", {})
    title: str = item.get("value", "").strip()
    national_inventory: bool = bool(data.get("nationalInventory", False))
    price_val = data.get("price")
    price_aud = float(price_val) if price_val is not None else None
    fc = data.get("FulfilmentChannel")
    if not title or not is_card_related(title, national_inventory, price_aud, fc):
        return None

    relative_url = data.get("url", "")
    full_url = KMART_BASE + relative_url if relative_url.startswith("/") else relative_url

    item_id = data.get("id", "")
    sku = item_id.replace("P_", "") if item_id else data.get("variation_id", "")

    slug = relative_url.rstrip("/").rsplit("/", 1)[-1] if relative_url else str(sku)

    return {
        "handle": slug,
        "title": title,
        "url": full_url,
        "vendor": "Kmart",
        "product_type": "TCG",
        "available": True,   # Constructor API only returns purchasable items
        "price_aud": price_aud,
        "sku": str(sku) if sku else None,
        "variant_available": [True],
        "badges": data.get("badges", []),
    }


def row_key(row: dict) -> str:
    return str(row.get("handle") or row.get("sku") or row.get("url") or row.get("title") or "")


def load_previous(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def compute_just_landed(current_payload: dict, previous_payload: dict) -> list[dict]:
    previous_keys = {row_key(p) for p in (previous_payload.get("in_stock") or [])}
    just_landed = [p for p in (current_payload.get("in_stock") or []) if row_key(p) not in previous_keys]
    just_landed.sort(key=lambda x: (x.get("title") or "").lower())
    return just_landed


def main() -> int:
    ap = argparse.ArgumentParser(description="Kmart Pokemon cards scraper via Constructor.io API")
    ap.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    ap.add_argument("--no-js", action="store_true")
    args = ap.parse_args()

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kmart_inventory.json"
    js_path = out_dir / "kmart_inventory.js"

    previous_payload = load_previous(json_path)

    in_stock: list[dict] = []
    seen_handles: set[str] = set()
    total_seen = 0

    for query in SEARCH_QUERIES:
        raw = scrape_query(query)
        total_seen += len(raw)
        for item in raw:
            row = build_row(item)
            if row is None:
                continue
            key = row_key(row)
            if key in seen_handles:
                continue
            seen_handles.add(key)
            in_stock.append(row)

    in_stock.sort(key=lambda x: (x.get("title") or "").lower())

    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": KMART_BASE,
        "in_stock": in_stock,
        "out_of_stock": [],
        "excluded": [],
        "errors": [],
        "totals": {
            "handles_discovered": total_seen,
            "in_stock": len(in_stock),
            "out_of_stock": 0,
            "excluded": 0,
            "errors": 0,
        },
    }
    payload["just_landed"] = compute_just_landed(payload, previous_payload)
    payload["totals"]["just_landed"] = len(payload["just_landed"])

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {json_path} - "
        f"{payload['totals']['in_stock']} in stock, "
        f"{total_seen} raw results seen, "
        f"{payload['totals']['just_landed']} just landed"
    )

    if not args.no_js:
        js_path.write_text(
            "window.KMART_INVENTORY = " + json.dumps(payload, separators=(",", ":")) + ";",
            encoding="utf-8",
        )
        print(f"Wrote {js_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
