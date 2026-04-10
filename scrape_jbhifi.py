#!/usr/bin/env python3
"""
Scrape JB Hi-Fi (Shopify) for Pokémon card–related products and live stock via product .js endpoints.

JB search pages only embed ~10 products in `var meta`; we union handles from several search queries.
Respect JB Hi-Fi's terms of service; use for personal checks and avoid aggressive polling.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests

BASE = "https://www.jbhifi.com.au"
SEARCH_URL = f"{BASE}/search"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_QUERIES = [
    "pokemon cards",
    "pokemon tcg",
    "pokemon booster",
    "pokemon blister",
    "pokemon elite trainer",
    "pokemon tin",
    "pokemon collection",
    "pokemon mega evolution",
    "pokemon trainer toolkit",
    "pokemon premium collection",
    "pokemon playmat",
    "pokemon album",
    "pokemon portfolio",
]

EXCLUDE_TITLE_SUBSTRINGS = (
    "nanoblock",
    "model kit",
    "microsd",
    "micro sd",
    "nintendo switch",
    "switch 2",
    "pokopia",
    "playmat",
    "potafolio",
    "portfolio",
    "ultra pro",
    "figure",
    " book",
    "backpack",
    "protector",
    "pop!",         # Funko Pop figures
    "funko",
    "plush",
    "squish",
    "t-shirt",
    "shirt",
    "costume",
    "hat",
    "cap",
    "mug",
    "puzzle",
    "activity",
    "sticker",
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"})
    return s


def parse_search_meta_products(html: str) -> list[dict]:
    needle = "var meta = "
    i = html.find(needle)
    if i == -1:
        return []
    start = i + len(needle)
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return []
    return list(obj.get("products") or [])


def fetch_product_js(sess: requests.Session, handle: str) -> dict | None:
    url = f"{BASE}/products/{handle}.js"
    try:
        r = sess.get(url, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def price_cents_to_aud(cents: int | float | None) -> float | None:
    if cents is None:
        return None
    try:
        return round(float(cents) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def is_card_related(title: str, vendor: str, product_type: str) -> bool:
    t = title.lower()
    v = (vendor or "").upper()
    for bad in EXCLUDE_TITLE_SUBSTRINGS:
        if bad in t:
            return False
    if v == "POKEMON TCG":
        return True
    if "tcg" in t or "trading card" in t:
        return True
    if "pokemon" in t and any(
        k in t
        for k in (
            "booster",
            "blister",
            "elite trainer",
            "tin",
            "collection",
            "trainer's toolkit",
            "trainer toolkit",
            "playmat",
            "portfolio",
            "album",
            "deck",
            "premium",
        )
    ):
        return True
    return False


def product_row(handle: str, js: dict) -> dict:
    price = price_cents_to_aud(js.get("price"))
    variants = js.get("variants") or []
    any_avail = bool(js.get("available"))
    return {
        "handle": handle,
        "title": js.get("title") or handle,
        "url": f"{BASE}{js.get('url') or '/products/' + handle}",
        "vendor": js.get("vendor"),
        "product_type": js.get("type"),
        "available": any_avail,
        "price_aud": price,
        "sku": variants[0].get("sku") if variants else None,
        "variant_available": [v.get("available", False) for v in variants],
    }


def run(
    queries: list[str],
    delay: float,
    tcg_focus: bool,
    sess: requests.Session,
) -> dict:
    handles: set[str] = set()
    for q in queries:
        url = f"{SEARCH_URL}?q={quote_plus(q)}"
        r = sess.get(url, timeout=45)
        r.raise_for_status()
        for p in parse_search_meta_products(r.text):
            h = p.get("handle")
            if h:
                handles.add(h)
        if delay > 0:
            time.sleep(delay)

    in_stock: list[dict] = []
    out_of_stock: list[dict] = []
    excluded: list[dict] = []
    errors: list[dict] = []

    for handle in sorted(handles):
        if delay > 0:
            time.sleep(delay)
        js = fetch_product_js(sess, handle)
        if not js:
            errors.append({"handle": handle, "error": "failed to load product .js"})
            continue
        title = js.get("title") or handle
        vendor = js.get("vendor") or ""
        ptype = js.get("type") or ""
        if tcg_focus and not is_card_related(title, vendor, ptype):
            excluded.append({"handle": handle, "title": title, "reason": "not classified as Pokémon TCG / cards"})
            continue
        row = product_row(handle, js)
        if row["available"]:
            in_stock.append(row)
        else:
            out_of_stock.append(row)

    in_stock.sort(key=lambda x: (x["title"] or "").lower())
    out_of_stock.sort(key=lambda x: (x["title"] or "").lower())

    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE,
        "queries_used": queries,
        "in_stock": in_stock,
        "out_of_stock": out_of_stock,
        "excluded": excluded,
        "errors": errors,
        "totals": {
            "handles_discovered": len(handles),
            "in_stock": len(in_stock),
            "out_of_stock": len(out_of_stock),
            "excluded": len(excluded),
            "errors": len(errors),
        },
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
    previous_in_stock = previous_payload.get("in_stock") or []
    previous_keys = {row_key(p) for p in previous_in_stock}
    just_landed = []
    for product in current_payload.get("in_stock") or []:
        if row_key(product) not in previous_keys:
            just_landed.append(product)
    just_landed.sort(key=lambda x: (x.get("title") or "").lower())
    return just_landed


def main() -> int:
    ap = argparse.ArgumentParser(description="JB Hi-Fi Pokémon cards stock scraper")
    ap.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help="Extra search phrases (in addition to built-in list)",
    )
    ap.add_argument("--queries-only", nargs="+", help="Use only these queries (replace defaults)")
    ap.add_argument("--delay", type=float, default=0.35, help="Seconds between HTTP requests")
    ap.add_argument(
        "--no-tcg-filter",
        action="store_true",
        help="Include all discovered products (games, toys, etc.)",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data",
        help="Directory for inventory.json / inventory.js",
    )
    ap.add_argument("--no-js", action="store_true", help="Do not write inventory.js")
    args = ap.parse_args()

    if args.queries_only:
        queries = list(args.queries_only)
    else:
        queries = list(DEFAULT_QUERIES)
        if args.queries:
            queries.extend(args.queries)

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "inventory.json"
    js_path = out_dir / "inventory.js"

    previous_payload = load_previous(json_path)

    try:
        sess = session()
        payload = run(
            queries=queries,
            delay=max(0.0, args.delay),
            tcg_focus=not args.no_tcg_filter,
            sess=sess,
        )
    except requests.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    payload["just_landed"] = compute_just_landed(payload, previous_payload)
    payload["totals"]["just_landed"] = len(payload["just_landed"])

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {json_path} — "
        f"{payload['totals']['in_stock']} in stock, "
        f"{payload['totals']['out_of_stock']} out of stock, "
        f"{payload['totals']['handles_discovered']} handles from search, "
        f"{payload['totals']['just_landed']} just landed"
    )

    if not args.no_js:
        js_path.write_text(
            "window.JBHIFI_INVENTORY = " + json.dumps(payload, separators=(",", ":")) + ";",
            encoding="utf-8",
        )
        print(f"Wrote {js_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
