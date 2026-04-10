#!/bin/bash
# Install cron job for Pokémon TCG scraper

echo "Installing Pokémon TCG Scraper cron job..."
echo ""

# Create the crontab entry
CRON_ENTRY="*/30 * * * * cd /Users/tomklimovski/clawd/tcg-scraper && ./schedule_check.sh >> /Users/tomklimovski/clawd/tcg-scraper/cron.log 2>&1"

echo "Cron entry to be installed:"
echo "$CRON_ENTRY"
echo ""

# Check if crontab exists
if crontab -l 2>/dev/null; then
    echo "Existing crontab found. Adding new entry..."
    (crontab -l 2>/dev/null; echo "# Pokémon TCG Scraper - Runs every 30 minutes, 9am-5pm only") | crontab -
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
else
    echo "No existing crontab. Creating new one..."
    echo "# Pokémon TCG Scraper - Runs every 30 minutes, 9am-5pm only" | crontab -
    echo "$CRON_ENTRY" | crontab -
fi

echo ""
echo "✅ Cron job installed!"
echo ""
echo "To verify:"
echo "  crontab -l"
echo ""
echo "To remove:"
echo "  crontab -r"
echo ""
echo "The scraper will run every 30 minutes between 9am-5pm."
echo "Outside these hours, it will skip gracefully."
echo ""
echo "Logs will be saved to:"
echo "  /Users/tomklimovski/clawd/tcg-scraper/cron.log"
echo "  /Users/tomklimovski/clawd/run_log.txt"