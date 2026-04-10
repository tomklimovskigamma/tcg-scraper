#!/bin/bash
# Setup token tracking for TCG Scraper

echo "=========================================="
echo "TCG Scraper Token Tracking Setup"
echo "=========================================="
echo ""

# Create data directory
mkdir -p data

# Create initial token log if it doesn't exist
TOKEN_LOG="data/token_log.json"
if [ ! -f "$TOKEN_LOG" ]; then
    echo "📝 Creating initial token log..."
    cat > "$TOKEN_LOG" << 'EOF'
{
  "test-job-001": {
    "job_id": "test-job-001",
    "job_type": "setup_test",
    "start_time": "2026-04-10T12:00:00+00:00",
    "end_time": "2026-04-10T12:00:05+00:00",
    "status": "completed",
    "tokens_used": 150,
    "estimated_cost": 0.000225,
    "items_processed": 10,
    "message_length": 800,
    "model": "default",
    "notes": "Token tracking setup test"
  }
}
EOF
    echo "✅ Created $TOKEN_LOG"
fi

# Create token summary if it doesn't exist
TOKEN_SUMMARY="data/token_summary.json"
if [ ! -f "$TOKEN_SUMMARY" ]; then
    echo "📊 Creating token summary..."
    cat > "$TOKEN_SUMMARY" << 'EOF'
{
  "total_jobs": 1,
  "total_tokens": 150,
  "total_cost": 0.000225,
  "jobs_by_type": {
    "setup_test": {
      "count": 1,
      "tokens": 150,
      "cost": 0.000225
    }
  },
  "daily_usage": {
    "2026-04-10": {
      "jobs": 1,
      "tokens": 150,
      "cost": 0.000225
    }
  }
}
EOF
    echo "✅ Created $TOKEN_SUMMARY"
fi

echo ""
echo "📁 Files created:"
echo "  • data/token_log.json"
echo "  • data/token_summary.json"
echo ""
echo "🔧 Token tracking is now ready!"
echo ""
echo "📈 How token tracking works:"
echo "  1. Each scraper run generates a unique job ID"
echo "  2. Token usage is estimated based on:"
echo "     • Discord webhook payload size"
echo "     • Number of items processed"
echo "     • Message length"
echo "  3. Costs are estimated based on model pricing"
echo ""
echo "💰 Cost estimates (per 1K tokens):"
echo "  • Default model: $0.0015"
echo "  • GPT-4: $0.03"
echo "  • Claude-3: $0.015"
echo ""
echo "🚀 Next scheduled run (tomorrow 7am) will track tokens automatically!"
echo ""
echo "📊 To check token usage:"
echo "  ./check_token_usage.sh"
echo "  python3 token_tracker.py --action report"
echo ""
echo "=========================================="
echo "✅ Token tracking setup complete!"
echo "=========================================="