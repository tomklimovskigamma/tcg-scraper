#!/bin/bash
# Schedule check - only runs between 9am-5pm

echo "=========================================="
echo "Pokémon TCG Scraper Schedule Check"
echo "=========================================="
echo "Time: $(date)"
echo ""

# Get current hour in 24-hour format
CURRENT_HOUR=$(date +%H)
CURRENT_MINUTE=$(date +%M)

echo "Current time: ${CURRENT_HOUR}:${CURRENT_MINUTE}"

# Check if within business hours (9am-5pm)
if [ "$CURRENT_HOUR" -ge 9 ] && [ "$CURRENT_HOUR" -le 16 ]; then
    echo "✅ Within business hours (9am-5pm)"
    echo "Running notification script..."
    echo ""
    
    # Run the notification script
    ./quick_notify.sh
    EXIT_CODE=$?
    
    echo ""
    echo "=========================================="
    echo "Schedule check completed with exit code: $EXIT_CODE"
    echo "=========================================="
    
    exit $EXIT_CODE
else
    echo "⏸️  Outside business hours (9am-5pm)"
    echo "Skipping notification until business hours."
    echo ""
    
    # Log the skip
    LOG_ENTRY="$(date -u +"%Y-%m-%d %H:%M:%S UTC") - Schedule skip - Outside business hours (${CURRENT_HOUR}:${CURRENT_MINUTE})"
    echo "$LOG_ENTRY" >> /Users/tomklimovski/clawd/run_log.txt
    
    echo "=========================================="
    echo "Schedule check completed - Skipped"
    echo "=========================================="
    
    exit 0
fi