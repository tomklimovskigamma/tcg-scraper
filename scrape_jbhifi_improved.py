#!/usr/bin/env python3
"""
Improved JB Hi-Fi scraper with retry logic, better error handling, and rate limiting.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
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
    "game voucher",
    "eshop",
    "digital code",
    "digital download",
    "gift card",
    "poster",
    "sticker",
    "keychain",
    "plush",
    "figure",
    "statue",
    "backpack",
    "lunch box",
    "water bottle",
    "clothing",
    "hat",
    "shirt",
    "socks",
    "pin",
    "patch",
    "postcard",
    "art print",
    "coloring book",
    "puzzle",
    "board game",
    "dice",
    "playmat",
    "sleeves",
    "binder",
    "deck box",
    "card case",
    "portfolio",
    "album",
)

def session() -> requests.Session:
    """Create a session with proper headers and retry logic."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    return sess

def make_request_with_retry(
    sess: requests.Session,
    url: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 30
) -> Optional[requests.Response]:
    """Make HTTP request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = sess.get(url, timeout=timeout)
            
            # Check for rate limiting or blocking
            if response.status_code == 429:  # Too Many Requests
                retry_after = response.headers.get('Retry-After')
                if retry_after and retry_after.isdigit():
                    wait_time = int(retry_after)
                else:
                    wait_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                
                print(f"Rate limited. Waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                continue
            
            # Check for other error status codes
            if response.status_code >= 400:
                print(f"HTTP {response.status_code} for {url}")
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait_time)
                    continue
                else:
                    return None
            
            return response
            
        except requests.exceptions.Timeout:
            print(f"Timeout for {url} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                time.sleep(wait_time)
                continue
            else:
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Request error for {url}: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                time.sleep(wait_time)
                continue
            else:
                return None
    
    return None

def extract_products_from_search(sess: requests.Session, query: str, delay: float) -> tuple[list[str], list[str]]:
    """Extract product handles from search page with improved parsing."""
    url = f"{SEARCH_URL}?q={quote_plus(query)}"
    print(f"  Searching: {query}")
    
    response = make_request_with_retry(sess, url)
    if not response:
        return [], [f"Failed to fetch search results for query: {query}"]
    
    text = response.text
    
    # Look for product handles in the page
    handles = []
    
    # Method 1: Look for data-product-handle attributes
    import re
    handle_pattern = r'data-product-handle="([^"]+)"'
    handles.extend(re.findall(handle_pattern, text))
    
    # Method 2: Look for product URLs
    url_pattern = r'/products/([^"/?#]+)'
    product_urls = re.findall(url_pattern, text)
    handles.extend(product_urls)
    
    # Method 3: Look for Shopify product data
    shopify_pattern = r'Shopify\.routes\.root\s*=\s*"([^"]+)"'
    shopify_matches = re.findall(shopify_pattern, text)
    
    # Deduplicate and clean handles
    unique_handles = list(set(h.strip() for h in handles if h.strip()))
    
    # Add small random delay between requests
    time.sleep(delay + random.uniform(0, 0.5))
    
    return unique_handles, []

def fetch_product_details(sess: requests.Session, handle: str, delay: float) -> Optional[dict]:
    """Fetch product details from product page with improved parsing."""
    url = f"{BASE}/products/{handle}"
    
    response = make_request_with_retry(sess, url)
    if not response:
        return None
    
    text = response.text
    
    # Extract product data using multiple methods
    import re
    import json as json_module
    
    product_data = {
        "handle": handle,
        "url": url,
        "title": None,
        "price_aud": None,
        "available": False,
        "description": None,
        "image_url": None,
    }
    
    # Method 1: Look for JSON-LD data
    json_ld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
    json_ld_matches = re.findall(json_ld_pattern, text, re.DOTALL)
    
    for json_ld in json_ld_matches:
        try:
            data = json_module.loads(json_ld.strip())
            if isinstance(data, dict):
                if "name" in data and not product_data["title"]:
                    product_data["title"] = data["name"]
                if "offers" in data:
                    offers = data["offers"]
                    if isinstance(offers, dict):
                        if "price" in offers:
                            try:
                                product_data["price_aud"] = float(offers["price"])
                            except (ValueError, TypeError):
                                pass
                        if "availability" in offers:
                            availability = offers["availability"].lower()
                            product_data["available"] = "instock" in availability or "preorder" in availability
                    elif isinstance(offers, list) and offers:
                        offer = offers[0]
                        if "price" in offer:
                            try:
                                product_data["price_aud"] = float(offer["price"])
                            except (ValueError, TypeError):
                                pass
                        if "availability" in offer:
                            availability = offer["availability"].lower()
                            product_data["available"] = "instock" in availability or "preorder" in availability
        except json_module.JSONDecodeError:
            continue
    
    # Method 2: Look for meta tags
    title_pattern = r'<meta property="og:title" content="([^"]+)"'
    title_match = re.search(title_pattern, text)
    if title_match and not product_data["title"]:
        product_data["title"] = title_match.group(1)
    
    price_pattern = r'<meta property="product:price:amount" content="([^"]+)"'
    price_match = re.search(price_pattern, text)
    if price_match and not product_data["price_aud"]:
        try:
            product_data["price_aud"] = float(price_match.group(1))
        except (ValueError, TypeError):
            pass
    
    availability_pattern = r'<meta property="product:availability" content="([^"]+)"'
    availability_match = re.search(availability_pattern, text)
    if availability_match:
        availability = availability_match.group(1).lower()
        product_data["available"] = "instock" in availability or "preorder" in availability
    
    # Method 3: Look for product-form data
    product_form_pattern = r'data-product="({[^}]+})"'
    product_form_match = re.search(product_form_pattern, text)
    if product_form_match:
        try:
            product_json = product_form_match.group(1).replace('&quot;', '"')
            data = json_module.loads(product_json)
            if "title" in data and not product_data["title"]:
                product_data["title"] = data["title"]
            if "variants" in data and data["variants"]:
                variant = data["variants"][0]
                if "price" in variant and not product_data["price_aud"]:
                    try:
                        # Price might be in cents
                        price = variant["price"]
                        if isinstance(price, int) and price > 1000:
                            product_data["price_aud"] = price / 100.0
                        else:
                            product_data["price_aud"] = float(price)
                    except (ValueError, TypeError):
                        pass
                if "available" in variant:
                    product_data["available"] = variant["available"]
        except (json_module.JSONDecodeError, KeyError):
            pass
    
    # Clean up title
    if product_data["title"]:
        product_data["title"] = product_data["title"].strip()
    
    # Add delay with jitter
    time.sleep(delay + random.uniform(0, 0.3))
    
    return product_data

def should_exclude_product(title: Optional[str], tcg_focus: bool) -> bool:
    """Determine if a product should be excluded based on title."""
    if not title:
        return False
    
    title_lower = title.lower()
    
    if tcg_focus:
        # Must contain Pokémon TCG keywords
        pokemon_keywords = ["pokemon", "pokémon"]
        tcg_keywords = ["card", "tcg", "booster", "blister", "elite trainer", "tin", "collection"]
        
        has_pokemon = any(keyword in title_lower for keyword in pokemon_keywords)
        has_tcg = any(keyword in title_lower for keyword in tcg_keywords)
        
        if not (has_pokemon and has_tcg):
            return True
    
    # Exclude based on excluded substrings
    for substring in EXCLUDE_TITLE_SUBSTRINGS:
        if substring in title_lower:
            return True
    
    return False

def run(
    queries: list[str],
    delay: float = 0.5,
    tcg_focus: bool = True,
    sess: Optional[requests.Session] = None,
) -> dict:
    """Run the scraper with improved error handling."""
    if sess is None:
        sess = session()
    
    all_handles = set()
    errors = []
    
    # Collect handles from all queries
    for query in queries:
        handles, query_errors = extract_products_from_search(sess, query, delay)
        all_handles.update(handles)
        errors.extend(query_errors)
        
        # Progress indicator
        print(f"    Found {len(handles)} products for '{query}'")
    
    print(f"Total unique products found: {len(all_handles)}")
    
    # Fetch details for each product
    in_stock = []
    out_of_stock = []
    excluded = []
    
    for i, handle in enumerate(sorted(all_handles)):
        print(f"  [{i+1}/{len(all_handles)}] Fetching {handle}...")
        
        product = fetch_product_details(sess, handle, delay)
        if not product:
            errors.append(f"Failed to fetch details for handle: {handle}")
            continue
        
        # Check if should be excluded
        if should_exclude_product(product["title"], tcg_focus):
            excluded.append(product)
            continue
        
        # Categorize by availability
        if product["available"]:
            in_stock.append(product)
        else:
            out_of_stock.append(product)
    
    # Sort results
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
            "handles_discovered": len(all_handles),
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
    ap = argparse.ArgumentParser(description="Improved JB Hi-Fi Pokémon cards stock scraper")
    ap.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help="Extra search phrases (in addition to built-in list)",
    )
    ap.add_argument("--queries-only", nargs="+", help="Use only these queries (replace defaults)")
    ap.add_argument("--delay", type=float, default=0.5, help="Seconds between HTTP requests")
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
    ap.add_argument("--test", action="store_true", help="Test mode - limit to 2 products")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of products to process")
    args = ap.parse_args()

    if args.queries_only:
        queries = list(args.queries_only)
    else:
        queries = list(DEFAULT_QUERIES)
        if args.queries:
            queries.extend(args.queries)
    
    # Apply test/limit
    if args.test:
        queries = queries[:2]
        print(f"Test mode: Using first 2 queries: {queries}")

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "inventory.json"
    js_path = out_dir / "inventory.js"

    previous_payload = load_previous(json_path)

    try:
        sess = session()
        payload = run(
            queries=queries,
            delay=max(0.1, args.delay),
            tcg_focus=not args.no_tcg_filter,
            sess=sess,
        )
    except requests.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    # Compute just_landed
    payload["just_landed"] = compute_just_landed(payload, previous_payload)

    # Write JSON
    json_path.write_text(json.d