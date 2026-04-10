#!/usr/bin/env python3
# Simple test of token tracking

import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN_LOG_FILE = HERE / "data" / "token_log.json"

# Create test data
test_job = {
    "job_id": "test-job-001",
    "job_type": "test_notification",
    "start_time": datetime.now(timezone.utc).isoformat(),
    "end_time": datetime.now(timezone.utc).isoformat(),
    "status": "completed",
    "tokens_used": 250,
    "estimated_cost": 0.000375,
    "items_processed": 15,
    "message_length": 1200,
    "model": "default",
    "notes": "Test notification"
}

# Ensure data directory exists
data_dir = HERE / "data"
data_dir.mkdir(exist_ok=True)

# Save test data
log = {}
if TOKEN_LOG_FILE.exists():
    try:
        with open(TOKEN_LOG_FILE, "r") as f:
            log = json.load(f)
    except:
        pass

log[test_job["job_id"]] = test_job

with open(TOKEN_LOG_FILE, "w") as f:
    json.dump(log, f, indent=2)

print("✅ Test token data created")
print(f"📁 File: {TOKEN_LOG_FILE}")
print(f"📊 Jobs in log: {len(log)}")

# Show the data
print("\n📋 Test Job Data:")
print(json.dumps(test_job, indent=2))

# Create summary file
TOKEN_SUMMARY_FILE = HERE / "data" / "token_summary.json"
summary = {
    "total_jobs": 1,
    "total_tokens": 250,
    "total_cost": 0.000375,
    "jobs_by_type": {
        "test_notification": {
            "count": 1,
            "tokens": 250,
            "cost": 0.000375
        }
    },
    "daily_usage": {
        datetime.now(timezone.utc).strftime("%Y-%m-%d"): {
            "jobs": 1,
            "tokens": 250,
            "cost": 0.000375
        }
    }
}

with open(TOKEN_SUMMARY_FILE, "w") as f:
    json.dump(summary, f, indent=2)

print(f"\n✅ Summary file created: {TOKEN_SUMMARY_FILE}")

# Show estimated costs
print("\n💰 Cost Estimates (per 1K tokens):")
print("  Default model: $0.0015")
print("  GPT-4: $0.03")
print("  Claude-3: $0.015")
print("\n📈 Next scheduled run will track tokens automatically!")