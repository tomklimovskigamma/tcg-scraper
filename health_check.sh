#!/bin/bash
# Health check script for Pokémon TCG scrapers

echo "============================================================"
echo "Pokémon TCG Scraper Health Check"
echo "============================================================"
echo ""

# Check Python availability
echo "1. Checking Python environment..."
python3 --version
if [ $? -eq 0 ]; then
    echo "   ✅ Python is available"
else
    echo "   ❌ Python not found"
    exit 1
fi

# Check directory structure
echo ""
echo "2. Checking directory structure..."
SCRIPTS=("scrape_jbhifi.py" "scrape_target.py" "scrape_kmart.py" "scrape_bigw.py" "run_all.py" "notify_discord.py")
MISSING=0

for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        echo "   ✅ $script exists"
    else
        echo "   ❌ $script missing"
        MISSING=$((MISSING + 1))
    fi
done

if [ $MISSING -eq 0 ]; then
    echo "   ✅ All scripts present"
else
    echo "   ⚠️  $MISSING script(s) missing"
fi

# Check data directory
echo ""
echo "3. Checking data directory..."
if [ -d "data" ]; then
    echo "   ✅ data/ directory exists"
    
    # Count JSON files
    JSON_COUNT=$(find data -name "*.json" -type f 2>/dev/null | wc -l)
    if [ $JSON_COUNT -gt 0 ]; then
        echo "   ✅ Found $JSON_COUNT JSON file(s) in data/"
        
        # Check file ages
        echo "   Checking file ages..."
        find data -name "*.json" -type f -exec ls -lh {} \; 2>/dev/null | head -5
    else
        echo "   ⚠️  No JSON files found in data/"
    fi
else
    echo "   ⚠️  data/ directory doesn't exist (will be created on first run)"
fi

# Check requirements
echo ""
echo "4. Checking Python requirements..."
if [ -f "requirements.txt" ]; then
    echo "   ✅ requirements.txt exists"
    echo "   Contents:"
    cat requirements.txt
else
    echo "   ⚠️  requirements.txt missing"
fi

# Check run log
echo ""
echo "5. Checking run log..."
RUN_LOG="/Users/tomklimovski/clawd/run_log.txt"
if [ -f "$RUN_LOG" ]; then
    echo "   ✅ Run log exists at $RUN_LOG"
    
    # Show last 5 runs
    echo "   Last 5 runs:"
    tail -5 "$RUN_LOG" 2>/dev/null || echo "   (Could not read log)"
    
    # Count successes/failures
    TOTAL_RUNS=$(grep -c "Run completed" "$RUN_LOG" 2>/dev/null || echo "0")
    SUCCESS_RUNS=$(grep -c "Found [0-9]* items" "$RUN_LOG" 2>/dev/null || echo "0")
    FAILED_RUNS=$(grep -c "No items found" "$RUN_LOG" 2>/dev/null || echo "0")
    
    echo "   Statistics:"
    echo "     Total runs: $TOTAL_RUNS"
    echo "     Successful: $SUCCESS_RUNS"
    echo "     Failed: $FAILED_RUNS"
else
    echo "   ⚠️  Run log not found at $RUN_LOG"
fi

# Check original data directory
echo ""
echo "6. Checking original data directory..."
ORIGINAL_DATA="/Users/sguerra/pokemon/jb-hifi/data"
if [ -d "$ORIGINAL_DATA" ]; then
    echo "   ✅ Original data directory exists"
    
    # Count files
    FILE_COUNT=$(find "$ORIGINAL_DATA" -name "*.json" -type f 2>/dev/null | wc -l)
    echo "   Found $FILE_COUNT JSON file(s)"
    
    # Show most recent file
    RECENT_FILE=$(find "$ORIGINAL_DATA" -name "*.json" -type f -exec ls -lt {} \; 2>/dev/null | head -1)
    if [ -n "$RECENT_FILE" ]; then
        echo "   Most recent: $RECENT_FILE"
    fi
else
    echo "   ⚠️  Original data directory not found"
fi

# Summary
echo ""
echo "============================================================"
echo "HEALTH CHECK SUMMARY"
echo "============================================================"

# Determine overall health
HEALTH_SCORE=0
MAX_SCORE=6

if python3 --version >/dev/null 2>&1; then HEALTH_SCORE=$((HEALTH_SCORE + 1)); fi
if [ $MISSING -eq 0 ]; then HEALTH_SCORE=$((HEALTH_SCORE + 1)); fi
if [ -d "data" ]; then HEALTH_SCORE=$((HEALTH_SCORE + 1)); fi
if [ -f "requirements.txt" ]; then HEALTH_SCORE=$((HEALTH_SCORE + 1)); fi
if [ -f "$RUN_LOG" ]; then HEALTH_SCORE=$((HEALTH_SCORE + 1)); fi
if [ -d "$ORIGINAL_DATA" ]; then HEALTH_SCORE=$((HEALTH_SCORE + 1)); fi

HEALTH_PERCENT=$((HEALTH_SCORE * 100 / MAX_SCORE))

echo "Overall Health: $HEALTH_SCORE/$MAX_SCORE ($HEALTH_PERCENT%)"

if [ $HEALTH_PERCENT -ge 80 ]; then
    echo "✅ System is healthy"
    echo ""
    echo "RECOMMENDATIONS:"
    echo "1. The scrapers are fundamentally working"
    echo "2. Fix notification logic to check 'in_stock' instead of 'just_landed'"
    echo "3. Consider adding retry logic for rate limiting"
elif [ $HEALTH_PERCENT -ge 50 ]; then
    echo "⚠️  System has issues"
    echo ""
    echo "RECOMMENDATIONS:"
    echo "1. Check missing scripts or directories"
    echo "2. Run scrapers manually to test"
    echo "3. Fix the 'just_landed' detection bug"
else
    echo "❌ System is unhealthy"
    echo ""
    echo "RECOMMENDATIONS:"
    echo "1. Check Python installation"
    echo "2. Verify all script files exist"
    echo "3. Run initial setup"
fi

echo ""
echo "============================================================"
echo "Quick Test Commands:"
echo "============================================================"
echo "1. Test JB Hi-Fi scraper:"
echo "   python3 scrape_jbhifi.py --test --limit 1"
echo ""
echo "2. Run all scrapers:"
echo "   python3 run_all.py"
echo ""
echo "3. Test notification (requires DISCORD_WEBHOOK_URL):"
echo "   python3 notify_discord.py --force"
echo ""
echo "4. Check data files:"
echo "   ls -la data/*.json 2>/dev/null || echo 'No data files'"
echo "============================================================"