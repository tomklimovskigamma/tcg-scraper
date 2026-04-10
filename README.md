# Pokémon TCG Scraper

A Python-based scraper for monitoring Pokémon Trading Card Game (TCG) inventory across major Australian retailers.

## Features

- **Multi-retailer support**: JB Hi-Fi, Target, Kmart, Big W
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

## Usage

### Run all scrapers:
```bash
python run_scrapers_and_check.py
```

### Run individual scrapers:
```bash
python jb_pokemon_scraper.py
```

### Schedule automated runs:
Add to crontab for hourly checks:
```bash
0 * * * * cd /path/to/tcg-scraper && python run_scrapers_and_check.py >> run_log.txt 2>&1
```

## Output

The scraper generates:
- `inventory.json`: JSON data for all retailers
- `inventory.js`: JavaScript version for web display
- `run_log.txt`: Log of all runs and findings

## Project Structure

```
tcg-scraper/
├── jb_pokemon_scraper.py      # Main scraper script
├── run_scrapers_and_check.py  # Orchestrator with just-landed detection
├── README.md                  # This file
├── requirements.txt           # Python dependencies
└── run_log.txt               # Execution log (generated)
```

## Dependencies

- Python 3.7+
- requests
- beautifulsoup4
- lxml

## License

MIT License - see LICENSE file for details.

## Contributing

Feel free to submit issues and pull requests for additional retailers or improvements.

## Support

For questions or support, open an issue on GitHub.