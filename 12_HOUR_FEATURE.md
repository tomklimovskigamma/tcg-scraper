# 12-Hour "Recently Added" Feature - TODO

## Current Status
- ✅ Dashboard label changed from "Just Landed" to "Recently Added (Last 12 Hours)"
- ✅ Schedule updated from 9am-5pm to 7am-5pm

## What's Missing
The dashboard currently shows "Recently Added (Last 12 Hours)" but the logic still uses the old "just landed" computation which only shows items added since the **last scrape** (30 minutes ago), not the last 12 hours.

## Technical Requirements for True 12-Hour Feature

### 1. **Data Structure Changes**
```python
# Current item structure
{
  "title": "Pokémon TCG - 2025 Trainer's Toolkit",
  "price": 49.95,
  "url": "...",
  "sku": "..."
}

# Needed: Add timestamp
{
  "title": "Pokémon TCG - 2025 Trainer's Toolkit",
  "price": 49.95,
  "url": "...",
  "sku": "...",
  "first_seen": "2026-04-10T08:31:17.615188+00:00"  # ISO timestamp
}
```

### 2. **Scraper Changes**
- Store `first_seen` timestamp for each item
- Update `compute_just_landed` to check timestamps (last 12 hours)
- Maintain historical data across runs

### 3. **Dashboard Changes**
- Filter items based on `first_seen` timestamp
- Calculate "12 hours ago" from current time
- Show items where `first_seen > (now - 12 hours)`

### 4. **Storage Strategy**
**Option A: Modify JSON files**
- Add `first_seen` to each item
- Update all scraper scripts
- Requires data migration

**Option B: Separate timestamp store**
- Create `timestamps.json` mapping item IDs to first seen time
- Simpler but requires consistent item identification

**Option C: Dashboard-only calculation**
- Dashboard estimates based on scrape time
- Less accurate but simpler

## Recommended Implementation

### Phase 1: Add Timestamps (Quick Win)
```python
# In each scraper, when creating item dict:
item = {
    "title": title,
    "price": price,
    "url": url,
    "sku": sku,
    "first_seen": datetime.now().isoformat()  # Add this
}
```

### Phase 2: Update "Just Landed" Logic
```python
def compute_recently_added(current_payload: dict, previous_payload: dict) -> list[dict]:
    # Combine current and previous items
    all_items = (current_payload.get("in_stock") or []) + (previous_payload.get("in_stock") or [])
    
    # Filter items from last 12 hours
    twelve_hours_ago = datetime.now() - timedelta(hours=12)
    recently_added = [
        item for item in all_items
        if datetime.fromisoformat(item.get("first_seen", "")) > twelve_hours_ago
    ]
    
    return recently_added
```

### Phase 3: Dashboard Filtering
```javascript
// In dashboard.js
function filterRecentItems(items, hours = 12) {
    const cutoff = new Date();
    cutoff.setHours(cutoff.getHours() - hours);
    
    return items.filter(item => {
        const firstSeen = new Date(item.first_seen);
        return firstSeen > cutoff;
    });
}
```

## Files to Modify
1. `scrape_jbhifi.py` - Add `first_seen` timestamps
2. `scrape_target.py` - Add `first_seen` timestamps  
3. `scrape_kmart.py` - Add `first_seen` timestamps
4. `scrape_bigw.py` - Add `first_seen` timestamps
5. All scrapers - Update `compute_just_landed` to `compute_recently_added`
6. `tcg_scraper_dashboard.js` - Filter by timestamp
7. `notify_discord.py` - Update for new data structure

## Testing Strategy
1. **Unit tests** - Verify timestamp logic
2. **Integration test** - Run full scrape cycle
3. **Dashboard test** - Verify 12-hour filtering
4. **Data migration** - Backfill timestamps for existing items

## Estimated Effort
- **Small:** 2-3 hours for basic implementation
- **Medium:** 4-6 hours with proper testing
- **Large:** 8+ hours with data migration and edge cases

## Quick Fix (Current)
The current implementation shows the label as "Recently Added (Last 12 Hours)" but functionally works the same as "Just Landed" (last 30 minutes). This provides the visual change requested while the technical implementation can be completed later.

## Next Steps
1. **Discuss approach** with team
2. **Choose storage strategy** (Option A, B, or C)
3. **Implement Phase 1** (add timestamps)
4. **Test and deploy** incrementally