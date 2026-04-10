# Pokémon TCG Scraper

A Python-based scraper for monitoring Pokémon Trading Card Game (TCG) inventory across major Australian retailers.

## Features

- **Multi-retailer support**: JB Hi-Fi, Target, Kmart, Big W
- **Real-time inventory tracking**: Monitor stock levels and prices
- **Just-landed detection**: Get alerts when new items arrive
- **Automated runs**: Scheduled checks with logging
- **Discord integration**: Notifications for new stock
- **Web dashboard**: Real-time inventory visualization

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

### View dashboard:
Open `dashboard.html` in your browser to see real-time inventory.

### Schedule automated runs:
Add to crontab for hourly checks:
```bash
0 * * * * cd /path/to/tcg-scraper && python run_all.py >> run_log.txt 2>&1
```

## Output

The scraper generates:
- `data/` directory with retailer-specific JSON files
- `dashboard.html` with real-time inventory visualization
- Discord notifications for new stock

## Project Structure

```
tcg-scraper/
├── scrape_jbhifi.py      # JB Hi-Fi scraper
├── scrape_target.py      # Target scraper
├── scrape_kmart.py       # Kmart scraper
├── scrape_bigw.py        # Big W scraper
├── run_all.py            # Orchestrator to run all scrapers
├── notify_discord.py     # Discord notification handler
├── dashboard.html        # Web dashboard
├── dashboard.css         # Dashboard styles
├── dashboard.js          # Dashboard JavaScript
├── README.md             # This file
├── requirements.txt      # Python dependencies
└── .gitignore           # Git ignore rules
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