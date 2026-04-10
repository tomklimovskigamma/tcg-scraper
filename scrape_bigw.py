#!/usr/bin/env python3
"""Scrape Big W for Pokémon TCG products.

Rules:
  - Only BigW-sold stock (productChannel == "BIGW") — no marketplace/IMP resellers.
  - Only available items: can be added to cart (stock==True) or pre-order.
  - Sold-out items are excluded.
  - Non-Pokemon TCG items are filtered out.
"""

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

BIGW_BASE = "https://www.bigw.com.au"
API_URL   = "https://api.bigw.com.au/search/v1/search"

SEARCH_TERMS = (
    "pokemon cards",
    "pokemon tcg",
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Origin": BIGW_BASE,
    "Referer": f"{BIGW_BASE}/",
}

CARD_KEYWORDS = (
    "booster",
    "blister",
    "elite trainer",
    " tin",
    "collection",
    " pack",
    "trainer toolkit",
    "trainer's toolkit",
    "trading card",
    "tcg",
    " deck",
    "premium",
    "bundle",
    "sleeve",
    "checklane",
    "battle academy",
)

EXCLUDE_TITLE_SUBSTRINGS = (
    "nintendo switch",
    "switch 2",
    "figure",
    "backpack",
    "squish",
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
    "pop!",
    "funko",
    " book",
    "guidebook",
    "handbook",
    "random",
    "graded",
    "psa",
    "binder",
    " album",
    "holder case",
    "playmat",
    "portfo",
)


def slugify(name: str) -> str:
    slug = normalize(name)  # strips accents (Pokémon → pokemon)
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def normalize(s: str) -> str:
    """Normalize unicode to ASCII-equivalent lowercase (e.g. Pokémon → pokemon)."""
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def is_card_related(name: str) -> bool:
    t = normalize(name)
    if "pokemon" not in t:
        return False
    if not any(k in t for k in CARD_KEYWORDS):
        return False
    if any(bad in t for bad in EXCLUDE_TITLE_SUBSTRINGS):
        return False
    return True


def build_row(item: dict) -> dict | None:
    info = item.get("information", {})
    name = info.get("name", "").strip()
    if not name:
        return None

    fulfilment = item.get("fulfilment", {})

    # Only BigW-direct stock — not marketplace/IMP resellers
    if fulfilment.get("productChannel") != "BIGW":
        return None

    # Must be available: in stock or pre-order (not sold out)
    stock = item.get("stock")
    preorder_data = fulfilment.get("preorder", {})
    is_preorder = bool(preorder_data and preorder_data.get("start"))
    if stock is not True:
        return None

    if not is_card_related(name):
        return None

    idents = item.get("identifiers", {})
    article_id = idents.get("articleId", "")
    slug = slugify(name)
    url = f"{BIGW_BASE}/product/{slug}/p/{article_id}"

    # Prefer VIC pricing, fall back to NAT
    price_region = item.get("prices", {}).get("VIC") or item.get("prices", {}).get("NAT") or {}
    price_cents = price_region.get("price", {}).get("cents")
    price_aud = price_cents / 100 if price_cents is not None else None

    # Release label (e.g. "RELEASES 22.05.26") for pre-orders
    label_text = price_region.get("label", {}).get("text", "")
    release_label = label_text if is_preorder else ""

    status = "pre-order" if is_preorder else "in_stock"

    return {
        "handle": article_id,
        "title": name,
        "url": url,
        "vendor": "Big W",
        "product_type": "TCG",
        "available": True,
        "status": status,
        "release_label": release_label,
        "price_aud": price_aud,
        "sku": article_id,
        "variant_available": [True],
    }


def fetch_all() -> tuple[list[dict], int]:
    seen: set[str] = set()
    rows: list[dict] = []
    total_seen = 0

    for term in SEARCH_TERMS:
        for page in range(10):
            payload = {
                "text": term,
                "perPage": 50,
                "page": page,
                "format": "1",
                "clientId": "web",
            }
            resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("organic", {}).get("results", [])
            if not results:
                break

            total_seen += len(results)
            for item in results:
                article_id = item.get("identifiers", {}).get("articleId", "")
                if article_id in seen:
                    continue
                row = build_row(item)
                if row:
                    seen.add(article_id)
                    rows.append(row)

    rows.sort(key=lambda x: (x.get("title") or "").lower())
    return rows, total_seen


def load_previous(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def row_key(row: dict) -> str:
    return str(row.get("handle") or row.get("sku") or row.get("url") or row.get("title") or "")


def compute_just_landed(current_payload: dict, previous_payload: dict) -> list[dict]:
    previous_keys = {row_key(p) for p in (previous_payload.get("in_stock") or [])}
    just_landed = [p for p in (current_payload.get("in_stock") or []) if row_key(p) not in previous_keys]
    just_landed.sort(key=lambda x: (x.get("title") or "").lower())
    return just_landed


def main() -> int:
    ap = argparse.ArgumentParser(description="Big W Pokémon TCG scraper")
    ap.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    ap.add_argument("--no-js", action="store_true")
    args = ap.parse_args()

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bigw_inventory.json"
    js_path   = out_dir / "bigw_inventory.js"

    previous_payload = load_previous(json_path)

    in_stock, total_seen = fetch_all()

    # Separate pre-orders from regular in-stock for totals reporting
    regular = [r for r in in_stock if r.get("status") != "pre-order"]
    preorders = [r for r in in_stock if r.get("status") == "pre-order"]

    payload: dict = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": BIGW_BASE,
        "in_stock": in_stock,
        "out_of_stock": [],
        "excluded": [],
        "errors": [],
        "totals": {
            "handles_discovered": total_seen,
            "in_stock": len(regular),
            "pre_orders": len(preorders),
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
        f"{payload['totals']['pre_orders']} pre-orders, "
        f"{total_seen} raw results seen, "
        f"{payload['totals']['just_landed']} just landed"
    )

    if not args.no_js:
        js_path.write_text(
            "window.BIGW_INVENTORY = " + json.dumps(payload, separators=(",", ":")) + ";",
            encoding="utf-8",
        )
        print(f"Wrote {js_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
