# Pings, daily digest and a history log

Date: 2026-11-10. Status: approved by Tom, built in the same change.

## Goal

The Discord alert serves two readers from one scrape:

- **Buyers who act fast** get an instant ping, only for products that sell out.
- **People keeping an eye on the market** get one digest a day.

Everything the scrape learns is kept in a history log, because it cannot be
backfilled later.

## Out of scope

Fixing JB Hi-Fi's HTTP 429, new retailers, market prices, a release calendar,
and any change to the web dashboard.

## Flow

```
scrape_<store>.py (unchanged)  ->  data/<store>_inventory.json
pipeline scan:   run scrapers -> classify -> compare with history -> record events -> post pings
pipeline digest: read history -> post one digest
```

Both commands are script-only scheduled jobs (Hermes `--no-agent`). No model.
The scan runs every 5 minutes 07:00-18:55; the digest runs at 19:00, after the last scan.

## Units

| File | Purpose | Depends on |
|---|---|---|
| `pipeline/classify.py` | Title -> product type, set name, base tier. Parses `watchlist.txt`. | nothing |
| `pipeline/history.py` | SQLite store: products, events, sets, runs. Turns a store's current stock into events. | classify |
| `pipeline/messages.py` | Events and stock -> Discord message text, split under 2000 characters. | nothing |
| `pipeline/discord.py` | Post text to the webhook. | nothing |
| `pipeline/run.py` | CLI (`scan`, `digest`, `--dry-run`): runs scrapers, wires the units together. | all |

Standard library only; must run on the system Python 3.9.

## Classification

The title is lower-cased and stripped of accents and dashes, then matched in
this order (first match wins):

1. **not_tcg**: clothing, swimwear, plush, figures ("Pokemon Select"), greeting
   cards ("Christmas"), or no TCG marker at all.
2. **accessory**: protectors, card sleeves, portfolios, binders, playmats, deck
   boxes, toolkits.
3. `booster_box` (booster box, display box), `etb`, `booster_bundle`,
   `collection` (premium collection, collection box, any "collection"), `tin`,
   `deck`, `blister`, `sleeved_booster`, `booster`, then `other_tcg`.

Tiers:

| Tier | Types |
|---|---|
| ping | booster_box, etb, booster_bundle, collection, tin; or any TCG item from a new set |
| digest | deck, blister, sleeved_booster, booster, other_tcg |
| ignore | not_tcg, accessory (never stored, never shown) |

**Set name**: the words between a series marker ("Mega Evolution", "Scarlet &
Violet", ...) and the first product-type word. No series marker means no set.

**New set**: a set name the history first saw within the last 90 days. Sets
seen in a store's baseline run are never "new".

**Overrides** (`watchlist.txt`, one per line, substring match on the title):
`always: <keyword>` forces ping, `never: <keyword>` forces digest,
`ignore: <keyword>` drops the item. `ignore` beats `never` beats `always`.

## History

SQLite at `data/history.db` (the `data/` folder is git-ignored).

- `products`: one row per store + sku with title, url, cart url, type, set,
  price, `in_stock`, `misses`, `since` (start of the current stint).
- `events`: `appeared` (label `new`, `restock` or `preorder`), `disappeared`
  (with `duration_min`), `price` (with `old_price`). Each has `tier`,
  `baseline` and `posted`.
- `sets`: name, first seen, baseline flag.
- `runs`: one row per store per scan with `ok`.

Rules:

- A store whose scraper failed records a failed run and nothing else, so an
  outage never looks like a sell-out.
- An item must be absent from two successful runs in a row before it counts as
  gone. Reappearing after one miss is not an event.
- A store's first successful run is its **baseline**: products and sets are
  recorded, events are marked `baseline` and never posted.
- An event is marked `posted` only after Discord accepts the message, so a
  failed post is retried on the next scan.

## Ping

Sent for unposted, non-baseline `appeared` events in the ping tier. All pings
from one scan share as few messages as fit.

```
🚨 **RESTOCK** · Elite Trainer Box · **$79.00**
**Pokémon TCG: Mega Evolution Chaos Rising ETB**
Big W · <url> · 🛒 <cart url>
3rd time in stock in 30 days · last time it sold out in 40 min
```

The label is RESTOCK, NEW LISTING or PRE-ORDER. The cart link appears when the
store provides one. The last line appears only when history has something to say.

## Digest

One post a day covering the local (Australia/Melbourne) day:

1. Arrivals, with time and whether each is still in stock or how long it lasted.
2. Sell-outs.
3. Price changes.
4. In stock now, grouped by store, with type and price.
5. Scraper health: any store that failed every run, or some runs, today.

If nothing was scraped all day the digest says so rather than staying silent.

## Failure handling

- Scan exits non-zero when every scraper failed or a Discord post failed, so
  the scheduler shows the job as failed.
- A scraper is given 120 seconds, then counted as failed.

## Testing

`python3 -m unittest discover tests` covers the classifier (real titles from
2026-11-10, including the socks and the box protector), the history
transitions (baseline, restock, two-miss rule, failed store, price change,
new set), and message formatting and splitting. `--dry-run` prints messages
and does not mark events as posted.

## Cutover

`run_and_post.sh`, `post_found_items.py` and `seen_items.txt` are replaced by
the pipeline. The first scan is a silent baseline. Scheduler wrappers are kept
in `hermes/` and copied to `~/.hermes/scripts/`.

## Addendum (same day): market prices, release dates, weekly chart

Approved by Tom after the first build. Source: TCGCSV (tcgcsv.com), a community
mirror of TCGplayer data refreshed once a day. It is a **US market in US
dollars**; every use is labelled as converted and as a guide only.

- `pipeline/market.py` fetches, once a day (07:40), the groups, products and
  prices for main-series sets released in the last 500 days, plus the USD to
  AUD rate (frankfurter.dev). Only the plain `<Set> Booster Box`, `Elite
  Trainer Box`, `Booster Bundle`, `Booster Pack` and `Sleeved Booster Pack`
  products are kept. Thirteen weekly points were backfilled once from the
  TCGCSV archive.
- **Ping line**: when a pinged item's set and type match a market product, the
  ping ends with `US market ≈ A$106 (US$70, converted) · shelf price is 25% below`.
- **New-set rule**: a set with a known release date is new for 90 days after
  release (unreleased sets count as new). The first-seen rule remains the
  fallback for sets the feed does not know.
- **Weekly chart** (`pipeline/chart.py`, Sundays 19:30): four small panels
  (booster box, ETB, bundle, pack), one line per set for the three newest
  sets, 90 days, dark theme, end labels, and the Australian shelf price as a
  reference line where the history has one. It needs matplotlib, so its
  wrapper runs the Homebrew Python; nothing else imports it.

## Addendum 2 (same day): tying stock to the market, and questions from Discord

Approved by Tom.

- **Trend**: `market_value` carries the 30-day change of the US market price.
  Ping and digest lines say "up 17% in 30 days", "down 6% in 30 days" or "flat
  over 30 days" (under 3%).
- **Hot sets**: a set whose product types have risen 10% or more (median) in
  30 days is hot; all its products ping, tagged "🔥 hot set". It drops back
  when the rise falls under 10%.
- **Digest**: a "Best value on shelves" section ranks in-stock items whose
  shelf price is 5% or more under the converted US market price (one line per
  set and product type, cheapest store first, other stores noted), and a
  "Sets to watch" section lists hot sets, sets released in the last 90 days
  and sets due in the next 60.
- **Questions** (`pipeline/ask.py`): a read-only command line over the history
  (`summary`, `stock`, `product`, `set`, `market`, `events`, `quests`,
  `schema`, `sql`). The database is opened read-only and `sql` accepts SELECT
  only.
- **Quests** (`pipeline/quest.py`): hands a question to qwen as a one-shot
  Hermes agent limited to the `web` toolset (no shell, no files), with our
  stock and market data as text in the prompt. Runs in the background, stores
  question and answer in the `quests` table, and posts the answer through the
  webhook. One at a time, ten per 24 hours, 15-minute limit, because the model
  server is shared.
- **Skill** (`skill/pokemon-stock/SKILL.md`, copied to
  `~/clawd/skills/pokemon-stock/`): teaches the OpenClaw `@gamma-ai` bot to
  answer from `pipeline.ask` and to start quests, with rules: label US prices,
  never predict restocks, no investment advice.
