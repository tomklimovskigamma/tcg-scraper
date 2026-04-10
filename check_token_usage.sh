#!/bin/bash
# Check token usage for TCG Scraper

echo "=========================================="
echo "TCG Scraper Token Usage Report"
echo "=========================================="
echo ""

# Check if token tracker is available
if [ ! -f "token_tracker.py" ]; then
    echo "❌ token_tracker.py not found"
    echo "Run: python3 token_tracker.py --action report"
    exit 1
fi

# Check if data directory exists
if [ ! -d "data" ]; then
    echo "❌ data directory not found"
    echo "No token tracking data available yet."
    exit 1
fi

# Check token log file
TOKEN_LOG="data/token_log.json"
if [ ! -f "$TOKEN_LOG" ]; then
    echo "ℹ️  No token log found yet"
    echo "Token tracking will start with the next scheduled run."
    echo ""
    echo "Next scheduled run: Tomorrow at 7:00 AM"
    exit 0
fi

# Get report
echo "📊 Generating token usage report..."
echo ""

python3 token_tracker.py --action report --days 7

echo ""
echo "=========================================="
echo "📈 Token Tracking Details:"
echo "=========================================="
echo ""

# Show raw data files
echo "📁 Data Files:"
echo "  • token_log.json: $(wc -l < data/token_log.json 2>/dev/null || echo 0) lines"
echo "  • token_summary.json: $(wc -l < data/token_summary.json 2>/dev/null || echo 0) lines"
echo ""

# Show last few jobs
echo "🔄 Recent Jobs:"
python3 -c "
import json
try:
    with open('data/token_log.json') as f:
        data = json.load(f)
    jobs = list(data.items())[-5:]  # Last 5 jobs
    for job_id, job_data in reversed(jobs):
        status = job_data.get('status', 'unknown')
        tokens = job_data.get('tokens_used', 0)
        cost = job_data.get('estimated_cost', 0.0)
        start = job_data.get('start_time', '')[:19]
        print(f'  {job_id[:20]}...')
        print(f'    Status: {status}')
        print(f'    Tokens: {tokens:,}')
        print(f'    Cost: \${cost:.6f}')
        print(f'    Started: {start}')
        print()
except Exception as e:
    print(f'  Error: {e}')
"
echo "=========================================="
echo "✅ Report generated"
echo ""
echo "🔧 Manual commands:"
echo "  python3 token_tracker.py --action report --days 30"
echo "  python3 token_tracker.py --action summary"
echo "  cat data/token_log.json | jq ."