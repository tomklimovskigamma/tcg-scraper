#!/bin/bash
# Schedule check - only runs between 7am-5pm

echo "=========================================="
echo "Pokémon TCG Scraper Schedule Check"
echo "=========================================="
echo "Time: $(date)"
echo ""

# Get current hour in 24-hour format
CURRENT_HOUR=$(date +%H)
CURRENT_MINUTE=$(date +%M)

echo "Current time: ${CURRENT_HOUR}:${CURRENT_MINUTE}"
echo "Business hours: 7am-5pm"

# Check if within business hours (7am-5pm)
if [ "$CURRENT_HOUR" -ge 7 ] && [ "$CURRENT_HOUR" -le 16 ]; then
    echo "✅ Within business hours (7am-5pm)"
    echo "Running notification script..."
    echo ""
    
    # Run the notification script with token tracking
    python3 notify_discord_with_tracking.py
    EXIT_CODE=$?
    
    echo ""
    echo "=========================================="
    echo "Schedule check completed with exit code: $EXIT_CODE"
    echo "=========================================="
    
    exit $EXIT_CODE
else
    echo "⏸️  Outside business hours (7am-5pm)"
    echo "Skipping notification until business hours."
    echo ""
    
    # Log the skip
    LOG_ENTRY="$(date -u +"%Y-%m-%d %H:%M:%S UTC") - Schedule skip - Outside business hours 7am-5pm (${CURRENT_HOUR}:${CURRENT_MINUTE})"
    echo "$LOG_ENTRY" >> /Users/tomklimovski/clawd/run_log.txt
    
    echo "=========================================="
    echo "Schedule check completed - Skipped"
    echo "=========================================="
    
    exit 0
fi