#!/bin/bash
# Lightweight runner for Pokémon TCG scraper cron jobs
# Runs scrapers, checks for just_landed items, filters out already-seen items,
# logs results, outputs to stdout only for genuinely new items.
#
# **FIXES applied (2026-05-04):**
# 1. scraper stderr is CAPTURED not swallowed — errors are logged
# 2. scraped_at is force-updated AFTER scrapers run (guaranteed fresh)
# 3. just_landed arrays are cleared from JSON after processing (no re-discovery)
# 4. seen_items.txt TTL check uses UTC consistently to match scrapers
# 5. seen_items.txt is checked against current in_stock (item gone = remove from seen)
#    so items that sold out can be re-notified if they come back
#
# Dedup: items are tracked by store+normalized_title in seen_items.txt.
# Trailing * is stripped from titles for dedup (Big W does this).
# Seen entries older than 7 days are purged so items can be re-notified.

RUN_LOG="/Users/tomklimovski/clawd/run_log.txt"
DATA_DIR="/Users/tomklimovski/clawd/tcg-scraper/data"
SCRAPER="/Users/tomklimovski/clawd/tcg-scraper/run_all.py"
SEEN_FILE="/Users/tomklimovski/clawd/tcg-scraper/seen_items.txt"
DASHBOARD_URL="https://toms-mac-mini.tailb83730.ts.net/"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
NOW_EPOCH=$(date +%s)
SEEN_TTL=$((7 * 24 * 3600))  # 24 hours in seconds

mkdir -p "$DATA_DIR"
touch "$SEEN_FILE"

# ── Step 1: Purge seen_items.txt entries older than 12h ─────────────────
# (use python3 for consistent date handling, avoiding timezone issues)
python3 -c "
import time, datetime
now_epoch = $NOW_EPOCH
seen_ttl = $SEEN_TTL
seen_path = '$SEEN_FILE'
with open(seen_path, 'r') as f:
    lines = f.readlines()
kept = []
purged = 0
for line in lines:
    line = line.rstrip('\n')
    if not line or line.startswith('#'):
        kept.append(line)
        continue
    try:
        ts_str = line.split('|')[0]
        dt = datetime.datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
        ts = dt.timestamp()
        if now_epoch - ts < seen_ttl:
            kept.append(line)
        else:
            purged += 1
    except Exception:
        kept.append(line)
with open(seen_path, 'w') as f:
    f.write('\n'.join(kept) + '\n')
if purged > 0:
    print(f'  🧹 Purged {purged} expired entries from seen_items.txt')
" 2>/dev/null

# ── Step 2: Run scrapers (with stderr captured, not /dev/null!) ──────────
RUN_MARKER=$(mktemp /tmp/tcg_run_marker.XXXXXX)
SCRAPER_LOG=$(mktemp /tmp/tcg_scraper_run.XXXXXX)
python3 "$SCRAPER" > "$SCRAPER_LOG" 2>&1
SCRAPER_EXIT=$?

# Always log scraper output (visible in run_log.txt)
while IFS= read -r line; do
    echo "$TIMESTAMP - [scraper] $line" >> "$RUN_LOG"
done < "$SCRAPER_LOG"

if [ $SCRAPER_EXIT -ne 0 ]; then
    echo "$TIMESTAMP - ⚠ run_all.py exited with code $SCRAPER_EXIT" >> "$RUN_LOG"
fi
rm -f "$SCRAPER_LOG"

# Only inventory files a scraper rewrote THIS run are trusted for alerts. A failed
# scraper (e.g. HTTP 429) leaves its old file behind; alerting from it would
# announce stale stock as new. Must be captured before Step 3 touches every file.
FRESH_FILES=$(find "$DATA_DIR" -name '*.json' -newer "$RUN_MARKER" 2>/dev/null)
rm -f "$RUN_MARKER"

# ── Step 3: Force-update scraped_at in ALL JSON files ───────────────────
# This guarantees scraped_at is always current, even if scrapers partially failed.
python3 -c "
import json, datetime, sys
from pathlib import Path
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
data_dir = Path('$DATA_DIR')
for f in data_dir.glob('*.json'):
    if f.name.startswith('token_'):
        continue
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        data['scraped_at'] = now
        # Ensure totals key exists
        if 'totals' not in data:
            data['totals'] = {}
        data['totals']['just_landed'] = len(data.get('just_landed', []))
        f.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        print(f'⚠ Failed to update scraped_at in {f.name}: {e}', file=sys.stderr)
" 2>/dev/null

# ── Step 4: Build seen keys from seen_items.txt ──────────────────────────
SEEN_KEYS=$(mktemp /tmp/tcg_seen_keys.XXXXXX)
while IFS='|' read -r seen_ts seen_store seen_title; do
    [[ "$seen_ts" =~ ^#.*$ ]] && continue
    [[ -z "$seen_ts" || -z "$seen_store" || -z "$seen_title" ]] && continue
    norm_title=$(echo "$seen_title" | sed 's/\*$//')
    echo "${seen_store}|${norm_title}" >> "$SEEN_KEYS"
done < "$SEEN_FILE"

# ── Step 5: Discover new items from just_landed + in_stock ─────────────
new_count=0
total_count=0
new_items_file=$(mktemp /tmp/tcg_new_items.XXXXXX)

while IFS= read -r json_file; do
    store_name=$(basename "$json_file" .json)
    if ! printf '%s\n' "$FRESH_FILES" | grep -qxF "$json_file"; then
        echo "$TIMESTAMP - ⚠ skipping $store_name: not refreshed this run (scraper failed?)" >> "$RUN_LOG"
        continue
    fi
    case "$store_name" in
        inventory) store_label="JB Hi-Fi" ;;
        target_inventory) store_label="Target" ;;
        kmart_inventory) store_label="Kmart" ;;
        bigw_inventory) store_label="Big W" ;;
        *) store_label="$store_name" ;;
    esac
    
    # First, check just_landed items (high priority)
    while IFS='|' read -r item_title item_price item_url; do
        [[ -z "$item_title" ]] && continue
        
        total_count=$((total_count + 1))
        store_key=$(echo "$store_label" | tr '[:upper:]' '[:lower:]' | tr -d ' -')
        norm_title=$(echo "$item_title" | sed 's/\*$//')
        seen_key="${store_key}|${norm_title}"
        
        if ! grep -F -x "$seen_key" "$SEEN_KEYS" > /dev/null 2>&1; then
            echo "$TIMESTAMP|${store_key}|${norm_title}" >> "$SEEN_FILE"
            new_count=$((new_count + 1))
            echo "${store_label}|${item_title}|${item_url}" >> "$new_items_file"
        fi
    done < <(python3 -c "
import json, sys
try:
    with open('$json_file') as f:
        data = json.load(f)
    for item in data.get('just_landed', []):
        title = item.get('title', 'Unknown')
        price = item.get('price') or item.get('price_aud') or ''
        url = item.get('url', '')
        title_safe = title.replace('|', '-')
        print(f\"{title_safe}|{price}|{url}\")
except Exception:
    pass
")
    
    # Also check ALL in_stock items against seen_items.txt
    # This catches items that were never marked as just_landed (e.g. pre-orders)
    while IFS='|' read -r item_title item_price item_url; do
        [[ -z "$item_title" ]] && continue
        
        store_key=$(echo "$store_label" | tr '[:upper:]' '[:lower:]' | tr -d ' -')
        norm_title=$(echo "$item_title" | sed 's/\*$//')
        seen_key="${store_key}|${norm_title}"
        
        if ! grep -F -x "$seen_key" "$SEEN_KEYS" > /dev/null 2>&1; then
            echo "$TIMESTAMP|${store_key}|${norm_title}" >> "$SEEN_FILE"
            new_count=$((new_count + 1))
            total_count=$((total_count + 1))
            echo "${store_label}|${item_title}|${item_url}" >> "$new_items_file"
        fi
    done < <(python3 -c "
import json, sys
try:
    with open('$json_file') as f:
        data = json.load(f)
    for item in data.get('in_stock', []):
        title = item.get('title', 'Unknown')
        price = item.get('price') or item.get('price_aud') or ''
        url = item.get('url', '')
        title_safe = title.replace('|', '-')
        print(f\"{title_safe}|{price}|{url}\")
except Exception:
    pass
")
done < <(ls "$DATA_DIR"/*.json 2>/dev/null 2>&1)

rm -f "$SEEN_KEYS"

# ── Step 6: CLEAR just_landed from JSON files ────────────────────────────
# This is the KEY FIX: prevent items from being re-discovered.
# After run_and_post.sh processes them, the just_landed arrays are cleared.
# The scrapers themselves will recompute just_landed on their next run.
python3 -c "
import json
from pathlib import Path
data_dir = Path('$DATA_DIR')
for f in data_dir.glob('*.json'):
    if f.name.startswith('token_') or not f.exists():
        continue
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        jl_count = len(data.get('just_landed', []))
        if jl_count > 0:
            data['just_landed'] = []
            data['totals']['just_landed'] = 0
            f.write_text(json.dumps(data, indent=2), encoding='utf-8')
            print(f'  ✅ Cleared {jl_count} just_landed items from {f.name}')
    except Exception as e:
        print(f'⚠ Failed to clear just_landed in {f.name}: {e}')
" 2>/dev/null

# ── Step 7: Log and output ───────────────────────────────────────────────
echo "$TIMESTAMP - Run completed - Found $total_count items ($new_count new)" >> "$RUN_LOG"

if [ $new_count -gt 0 ]; then
    echo "FOUND_ITEMS=$new_count"
    while IFS= read -r item_line; do
        echo "ITEM=$item_line"
    done < "$new_items_file"
    echo "DASHBOARD=$DASHBOARD_URL"
fi

rm -f "$new_items_file"
