#!/bin/bash
# Quick notification script for Pokémon TCG scraper

echo "=========================================="
echo "Pokémon TCG Scraper Notification"
echo "=========================================="

# Check webhook
WEBHOOK_FILE="/Users/tomklimovski/clawd/tcg-scraper/discord_webhook.txt"
if [ ! -f "$WEBHOOK_FILE" ]; then
    echo "❌ Error: discord_webhook.txt not found"
    echo "Create it with: echo 'WEBHOOK_URL' > $WEBHOOK_FILE"
    exit 1
fi

WEBHOOK=$(head -1 "$WEBHOOK_FILE")
if [[ ! "$WEBHOOK" =~ ^https://discord.com/api/webhooks/ ]]; then
    echo "❌ Error: Invalid webhook URL"
    exit 1
fi

echo "✅ Webhook loaded: ${WEBHOOK:0:50}..."

# Count items from data files
echo ""
echo "📊 Counting items from data files..."

JB_COUNT=$(grep -c '"title"' /Users/tomklimovski/clawd/tcg-scraper/data/inventory.json 2>/dev/null || echo "0")
TARGET_COUNT=$(grep -c '"title"' /Users/tomklimovski/clawd/tcg-scraper/data/target_inventory.json 2>/dev/null || echo "0")
KMART_COUNT=$(grep -c '"title"' /Users/tomklimovski/clawd/tcg-scraper/data/kmart_inventory.json 2>/dev/null || echo "0")
BIGW_COUNT=$(grep -c '"title"' /Users/tomklimovski/clawd/tcg-scraper/data/bigw_inventory.json 2>/dev/null || echo "0")

TOTAL=$((JB_COUNT + TARGET_COUNT + KMART_COUNT + BIGW_COUNT))

echo "   JB Hi-Fi: $JB_COUNT items"
echo "   Target: $TARGET_COUNT items"
echo "   Kmart: $KMART_COUNT items"
echo "   Big W: $BIGW_COUNT items"
echo "   Total: $TOTAL items"

# Get sample items
echo ""
echo "📋 Sample items:"
SAMPLE_ITEMS=$(grep '"title"' /Users/tomklimovski/clawd/tcg-scraper/data/inventory.json 2>/dev/null | head -3 | sed 's/.*"title": "//;s/",.*//' | sed 's/^/• /')
echo "$SAMPLE_ITEMS"

# Create notification
echo ""
echo "📨 Creating notification JSON..."

cat > /tmp/tcg_notification.json << EOF
{
  "content": "📦 **Pokémon TCG Inventory Update**",
  "embeds": [
    {
      "title": "✅ Scraper System Online",
      "description": "Current inventory across Australian retailers",
      "color": 5763719,
      "fields": [
        {"name": "JB Hi-Fi", "value": "$JB_COUNT items", "inline": true},
        {"name": "Target", "value": "$TARGET_COUNT items", "inline": true},
        {"name": "Kmart", "value": "$KMART_COUNT items", "inline": true},
        {"name": "Big W", "value": "$BIGW_COUNT items", "inline": true},
        {"name": "Total", "value": "$TOTAL items", "inline": true},
        {"name": "Last Check", "value": "$(date '+%H:%M %Z')", "inline": true}
      ],
      "footer": {"text": "Pokémon TCG Scraper • Live Dashboard: https://toms-mac-mini.tailb83730.ts.net/"}
    }
  ]
}
EOF

# Send notification
echo "🚀 Sending notification to Discord..."
curl -X POST -H "Content-Type: application/json" -d @/tmp/tcg_notification.json "$WEBHOOK"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Notification sent successfully!"
    
    # Update run log
    LOG_ENTRY="$(date -u +"%Y-%m-%d %H:%M:%S UTC") - Notification sent - Found $TOTAL items across retailers"
    echo "$LOG_ENTRY" >> /Users/tomklimovski/clawd/run_log.txt
    echo "📝 Log updated: $LOG_ENTRY"
else
    echo ""
    echo "❌ Failed to send notification"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Done! Check Discord for the notification."
echo "=========================================="