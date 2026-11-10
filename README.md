# Pokémon TCG Scraper

A Python-based scraper for monitoring Pokémon Trading Card Game (TCG) inventory across major Australian retailers.

## Alerts: pings, daily digest and history

The scrapers feed a small pipeline (`pipeline/`) that needs no LLM:

- **Instant pings** for products that sell out (booster boxes, Elite Trainer
  Boxes, bundles, collections, tins, and anything from a set first seen in the
  last 90 days), with price, a RESTOCK / NEW LISTING / PRE-ORDER label and
  restock history.
- **A daily digest** at 19:00 with the day's arrivals, sell-outs, price changes,
  current stock and scraper health.
- **A history log** in `data/history.db` (SQLite) of every appearance,
  disappearance and price change.

```bash
python3 -m pipeline.run scan              # scrape, record, post pings
python3 -m pipeline.run digest            # post the daily digest
python3 -m pipeline.run scan --dry-run    # print instead of posting; history untouched
python3 -m unittest discover -s tests -p 'test_[chmr]*.py'
```

**Market prices.** `python3 -m pipeline.run market-sync` (daily) stores US
market prices and set release dates from tcgcsv.com; pings then carry a
"US market ≈ A$…" line, and `market-chart` (Sundays, needs matplotlib, so run
it with the Homebrew Python) posts a 90-day price chart. The prices are US
market prices converted to AUD: a guide, not Australian resale value.

**Specialist stores.** Gameology, Good Games and Cherry Collectables are read
through `scrape_shopify.py --store <key>` every 15 minutes. Only new and hot
sets ping there; the digest shows a count per shop.

**Personal watches.** `python3 -m pipeline.watch add "delta reign etb" --under 80
--asker <name>` (also `list`, `remove`). A matching arrival or price drop is
posted with that person's mention. Ten per person.

**Questions and quests.** `python3 -m pipeline.ask summary` (also `stock`,
`product`, `set`, `market`, `events`, `quests`, `sql`) answers from the history,
read-only. `python3 -m pipeline.quest "<question>" --asker <name>` sends qwen
(a local model, web research only) to find out more and post the answer to the
channel. `skill/pokemon-stock/SKILL.md` teaches the `@gamma-ai` Discord bot to
use both; copy it to `~/clawd/skills/pokemon-stock/` after changing it.

Edit `watchlist.txt` to force a product to always ping, never ping, or be
ignored. The webhook URL is read from `discord_webhook.txt` (git-ignored) or
`DISCORD_WEBHOOK_URL`. The scheduler wrappers are in `hermes/`; copy them to
`~/.hermes/scripts/` after changing them. Design:
`docs/superpowers/specs/2026-11-10-pings-digest-history-design.md`.

## Features

- **Multi-retailer support**: JB Hi-Fi, Target, Kmart, Big W, Gameology, Good Games, Cherry Collectables
- **Real-time inventory tracking**: Monitor stock levels and prices
- **Just-landed detection**: Get alerts when new items arrive
- **Automated runs**: Scheduled checks with logging
- **Discord integration**: Notifications for new stock

## Retailers Covered

| Retailer | URL | Status |
|----------|-----|--------|
| JB Hi-Fi | `https://www.jbhifi.com.au/collections/pokemon` | ✅ Active |
| Target | `https://www.target.com.au/c/pokemon-trading-cards` | ✅ Active |
| Kmart | `https://www.kmart.com.au/search/?q=pokemon%20cards` | ✅ Active |
| Big W | `https://www.bigw.com.au/search/?q=pokemon%20cards` | ✅ Active |

## Installation

1. Clone the repository:
```bash
git clone https://github.com/tomklimovskigamma/tcg-scraper.git
cd tcg-scraper
```

2. Set up a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Quick Health Check

Run the health check script to diagnose issues:
```bash
./health_check.sh
```

This will check:
- Python environment
- Script files
- Data directory
- Run logs
- System health

## Usage

### Run all scrapers:
```bash
python run_all.py
```

### Run individual scrapers:
```bash
python scrape_jbhifi.py
python scrape_target.py
python scrape_kmart.py
python scrape_bigw.py
```

### Send Discord notifications:
```bash
python notify_discord.py
```

### Schedule automated runs:
Add to crontab for hourly checks:
```bash
0 * * * * cd /path/to/tcg-scraper && python run_all.py
```

Note: The script now automatically logs to `/Users/tomklimovski/clawd/run_log.txt`

## Output

The scraper generates:
- `data/` directory with retailer-specific JSON files
- Discord notifications for new stock

## Project Structure

```
tcg-scraper/
├── scrape_jbhifi.py          # JB Hi-Fi scraper
├── scrape_jbhifi_improved.py # Improved version with retry logic
├── scrape_target.py          # Target scraper
├── scrape_kmart.py           # Kmart scraper
├── scrape_bigw.py            # Big W scraper
├── scrape_shopify.py         # Gameology, Good Games, Cherry Collectables
├── run_all.py                # Orchestrator to run all scrapers
├── notify_discord.py         # Discord notification handler
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── .gitignore               # Git ignore rules
├── health_check.sh          # System health check script
├── diagnose_issues.py       # Diagnostic tool
├── simple_test.py           # Basic test script
└── tests/                   # Test suite
    └── test_scrapers.py    # Comprehensive tests
```

## Dependencies

- Python 3.7+
- requests
- beautifulsoup4
- lxml

## Common Issues & Fixes

### Issue: "No items found" but scrapers are working
**Cause**: Notification logic checks `just_landed` instead of `in_stock`
**Fix**: Use `--include-in-stock` flag with `notify_discord.py`
```bash
python notify_discord.py --include-in-stock
```

### Issue: Rate limiting or blocking
**Cause**: Websites blocking frequent requests
**Fix**: Use improved scraper with retry logic
```bash
python scrape_jbhifi_improved.py --delay 1.0
```

### Issue: Price shows as "None"
**Cause**: HTML parsing issues
**Fix**: The improved scraper has better price extraction

### Issue: Inconsistent results
**Cause**: Network issues or website changes
**Fix**: Run health check and enable retry logic
```bash
./health_check.sh
```

## License

MIT License - see LICENSE file for details.

## Testing

Run the test suite:
```bash
cd tests && python -m pytest test_scrapers.py -v
```

Or run quick health check:
```bash
./health_check.sh
```

## Contributing

Feel free to submit issues and pull requests for additional retailers or improvements.

## Support

For questions or support, open an issue on GitHub.

## Recent Updates (April 2026)

1. **Dashboard retired (November 2026)** - The web dashboard and its tailnet link were removed; the Discord digest replaces it
2. **Schedule Update** - Changed from 9am-5pm to **7am-5pm** runs
3. **Recently Added Section** - Changed "Just Landed" to "Recently Added (Last 12 Hours)"
4. **Fixed notification logic** - Now supports `--include-in-stock` flag
5. **Added retry logic** - Exponential backoff for rate limiting
6. **Improved error handling** - Better parsing and validation
7. **Enhanced logging** - More detailed run logs
8. **Added health checks** - Diagnostic tools for troubleshooting
9. **Schedule automation** - Configured for 7am-5pm runs every 30 minutes
10. **Discord integration** - Real-time notifications to #tcg channel