#!/usr/bin/env python3
"""
Scrape Target Australia for Pokemon TCG/card products using the public Constructor search API.
Use for personal checks and avoid aggressive polling.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

BASE = "https://www.target.com.au"
API_BASE = "https://ac.cnstrc.com"
API_KEY = "key_kWcXakjuyHSxpu75"
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
    "pokemon trainer toolkit",
    "pokemon premium collection",
]

EXCLUDE_TITLE_SUBSTRINGS = (
    "nintendo switch",
    "switch 2",
    "pokopia",
    "playmat",
    "portfolio",
    "album",
    "binder",
    "figure",        # battle figures, action figures
    "backpack",      # bags
    "squish",        # squish toys / plush
    "plush",
    "t-shirt",
    "shirt",
    "costume",
    "hat",
    "cap",
    "mug",
    "puzzle",
    "activity",
    "sticker",
    "pop!",          # Funko Pop
    "funko",
    " book",         # books (e.g. "Battle Collection - Book")
    "guidebook",
    "handbook",
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"})
    return s


def to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def is_card_related(title: str, brand: str) -> bool:
    t = (title or "").lower()
    b = (brand or "").lower()
    for bad in EXCLUDE_TITLE_SUBSTRINGS:
        if bad in t:
            return False
    if "pokemon" not in t:
        return False
    if "tcg" in t or "trading card" in t:
        return True
    if b == "pokemon":
        return any(
            k in t
            for k in (
                "booster",
                "blister",
                "elite trainer",
                " tin",
                "collection",
                "trainer toolkit",
                "trainer's toolkit",
                "trading card",
                "tcg",
                " deck",
                "premium",
                "bundle",
                " pack",    # space prefix avoids matching "backpack"
                "sleeve",
            )
        )
    return False


def fetch_search_page(
    sess: requests.Session, query: str, page: int, num_results_per_page: int
) -> list[dict]:
    endpoint = f"{API_BASE}/search/{quote(query)}"
    params = {
        "key": API_KEY,
        "i": str(uuid.uuid4()),
        "page": page,
        "num_results_per_page": num_results_per_page,
    }
    r = sess.get(endpoint, params=params, timeout=45)
    r.raise_for_status()
    data = r.json()
    return list((data.get("response") or {}).get("results") or [])


def extract_row(result: dict) -> dict:
    data = result.get("data") or {}
    title = result.get("value") or data.get("name") or data.get("description") or "Unknown product"
    url = data.get("url") or ""
    instock = data.get("instock")
    sku = data.get("id")
    return {
        "handle": sku or url.rsplit("/", 1)[-1],
        "title": title,
        "url": url if url.startswith("http") else f"{BASE}{url}",
        "vendor": data.get("brand"),
        "product_type": "TCG",
        "available": bool(instock),
        "price_aud": to_float(data.get("price")),
        "sku": sku,
        "variant_available": [bool(instock)],
    }


def run(
    queries: list[str],
    tcg_focus: bool,
    sess: requests.Session,
    max_pages: int,
    per_page: int,
) -> dict:
    seen_ids: set[str] = set()
    in_stock: list[dict] = []
    out_of_stock: list[dict] = []
    excluded: list[dict] = []
    errors: list[dict] = []
    discovered = 0

    for q in queries:
        for page in range(1, max_pages + 1):
            try:
                results = fetch_search_page(sess, q, page, per_page)
            except (requests.RequestException, ValueError) as e:
                errors.append({"query": q, "page": page, "error": str(e)})
                break

            if not results:
                break

            for result in results:
                data = result.get("data") or {}
                item_id = data.get("id") or data.get("url")
                if not item_id:
                    continue
                discovered += 1
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                title = result.get("value") or ""
                brand = data.get("brand") or ""
                if tcg_focus and not is_card_related(title, brand):
                    excluded.append(
                        {
                            "handle": item_id,
                            "title": title or str(item_id),
                            "reason": "not classified as Pokemon TCG / cards",
                        }
                    )
                    continue

                row = extract_row(result)
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
            "handles_discovered": discovered,
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
    ap = argparse.ArgumentParser(description="Target Australia Pokemon cards stock scraper")
    ap.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help="Extra search phrases (in addition to built-in list)",
    )
    ap.add_argument("--queries-only", nargs="+", help="Use only these queries (replace defaults)")
    ap.add_argument(
        "--no-tcg-filter",
        action="store_true",
        help="Include all discovered products (games, toys, etc.)",
    )
    ap.add_argument("--max-pages", type=int, default=5, help="Pages per query to scan")
    ap.add_argument("--per-page", type=int, default=50, help="Results per API page")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data",
        help="Directory for target_inventory.json / target_inventory.js",
    )
    ap.add_argument("--no-js", action="store_true", help="Do not write target_inventory.js")
    args = ap.parse_args()

    if args.queries_only:
        queries = list(args.queries_only)
    else:
        queries = list(DEFAULT_QUERIES)
        if args.queries:
            queries.extend(args.queries)

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "target_inventory.json"
    js_path = out_dir / "target_inventory.js"

    previous_payload = load_previous(json_path)

    try:
        sess = session()
        payload = run(
            queries=queries,
            tcg_focus=not args.no_tcg_filter,
            sess=sess,
            max_pages=max(1, args.max_pages),
            per_page=max(1, args.per_page),
        )
    except requests.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    payload["just_landed"] = compute_just_landed(payload, previous_payload)
    payload["totals"]["just_landed"] = len(payload["just_landed"])

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {json_path} - "
        f"{payload['totals']['in_stock']} in stock, "
        f"{payload['totals']['out_of_stock']} out of stock, "
        f"{payload['totals']['handles_discovered']} products seen, "
        f"{payload['totals']['just_landed']} just landed"
    )

    if not args.no_js:
        js_path.write_text(
            "window.TARGET_INVENTORY = " + json.dumps(payload, separators=(",", ":")) + ";",
            encoding="utf-8",
        )
        print(f"Wrote {js_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
