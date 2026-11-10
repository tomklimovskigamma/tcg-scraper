#!/usr/bin/env python3
"""
Scrape a Shopify-based specialist store for Pokemon products, using the store's
public collection feed (`/collections/<handle>/products.json`).

    python3 scrape_shopify.py --store gameology

Writes data/<store>_inventory.json in the same shape as the other scrapers.
Standard library only. For personal checks: it identifies itself honestly,
pauses between pages, and stops on the first refusal rather than retrying.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "tcg-stock-check/1.0 (personal stock checker)"
PAGE_SIZE = 250
MAX_PAGES = 8
PAUSE_SECONDS = 1.0

# key -> (display name, base URL, collection handle)
STORES = {
    "gameology": ("Gameology", "https://www.gameology.com.au", "pokemon"),
    "goodgames": ("Good Games", "https://www.goodgames.com.au", "pokemon"),
    "cherry": ("Cherry Collectables", "https://www.cherrycollectables.com.au", "pokemon"),
    "toyworld": ("Toyworld", "https://www.toyworld.com.au", "pokemon"),
}


def fetch_page(base: str, handle: str, page: int) -> list:
    url = f"{base}/collections/{handle}/products.json?limit={PAGE_SIZE}&page={page}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8")).get("products") or []


def to_item(base: str, product: dict):
    """One in-stock item from a Shopify product, or None when no variant can be bought."""
    prices = []
    for v in product.get("variants") or []:
        if not v.get("available"):
            continue
        try:
            prices.append(float(v.get("price")))
        except (TypeError, ValueError):
            pass
    if not prices:
        return None
    title = str(product.get("title") or "").strip()
    if not title:
        return None
    # Specialist shops often leave "TCG" out of the title; the category carries it.
    category = str(product.get("product_type") or "")
    if "trading card" in category.lower() or "tcg" in category.lower():
        if "tcg" not in title.lower() and "trading card" not in title.lower():
            title = f"{title} (TCG)"
    return {
        "sku": str(product.get("id")),
        "handle": product.get("handle"),
        "title": title,
        "url": f"{base}/products/{product.get('handle')}",
        "vendor": product.get("vendor"),
        "product_type": category,
        "available": True,
        "price_aud": min(prices),
    }


def scrape(key: str, fetch=fetch_page, pause: float = PAUSE_SECONDS) -> dict:
    name, base, handle = STORES[key]
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        products = fetch(base, handle, page)
        for p in products:
            item = to_item(base, p)
            if item and item["sku"] not in seen:
                seen.add(item["sku"])
                items.append(item)
        if len(products) < PAGE_SIZE:
            break
        time.sleep(pause)
    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": base,
        "store": name,
        "in_stock": items,
        "totals": {"in_stock": len(items)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True, choices=sorted(STORES))
    ap.add_argument("--no-js", action="store_true", help="accepted for compatibility; has no effect")
    args = ap.parse_args(argv)
    try:
        result = scrape(args.store)
    except urllib.error.HTTPError as e:
        print(f"{STORES[args.store][0]}: HTTP {e.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"{STORES[args.store][0]}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    out = Path(__file__).resolve().parent / "data" / f"{args.store}_inventory.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"{result['store']}: {len(result['in_stock'])} in stock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
