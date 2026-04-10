#!/usr/bin/env python3
"""Token consumption tracker for TCG Scraper notifications.

Tracks:
1. Discord webhook payload size (approximate tokens)
2. Notification message length
3. Total items processed
4. Cost estimation (if using paid AI models)

Usage:
    python3 token_tracker.py --action start --job-id scraper-run-001
    python3 token_tracker.py --action end --job-id scraper-run-001 --tokens 150 --cost 0.0003
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import argparse
from typing import Optional, Dict, Any

HERE = Path(__file__).resolve().parent
TOKEN_LOG_FILE = HERE / "data" / "token_log.json"
TOKEN_SUMMARY_FILE = HERE / "data" / "token_summary.json"

# Token estimation constants
DISCORD_WEBHOOK_OVERHEAD = 50  # Approx tokens for Discord embed structure
PER_ITEM_TOKENS = 10           # Approx tokens per inventory item in notification
PER_CHARACTER_TOKENS = 0.25    # Rough estimate: 1 token ≈ 4 characters

# Cost constants (per 1K tokens)
# Update these based on your actual model costs
MODEL_COSTS = {
    "default": 0.0015,  # $0.0015 per 1K tokens (example: GPT-3.5)
    "gpt-4": 0.03,      # $0.03 per 1K tokens
    "claude-3": 0.015,  # $0.015 per 1K tokens
}


class TokenTracker:
    def __init__(self):
        self.ensure_data_dir()
    
    def ensure_data_dir(self):
        """Ensure data directory exists."""
        data_dir = HERE / "data"
        data_dir.mkdir(exist_ok=True)
    
    def start_job(self, job_id: str, job_type: str = "scraper_notification") -> Dict[str, Any]:
        """Start tracking a job."""
        job_data = {
            "job_id": job_id,
            "job_type": job_type,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "tokens_used": 0,
            "estimated_cost": 0.0,
            "items_processed": 0,
            "message_length": 0,
            "model": "default",
            "notes": ""
        }
        
        # Load existing log
        log = self.load_log()
        log[job_id] = job_data
        
        # Save log
        self.save_log(log)
        
        print(f"✅ Started tracking job: {job_id}")
        return job_data
    
    def end_job(self, job_id: str, tokens_used: Optional[int] = None, 
                items_processed: int = 0, message_length: int = 0,
                model: str = "default", notes: str = "") -> Dict[str, Any]:
        """End tracking a job and calculate tokens/cost."""
        log = self.load_log()
        
        if job_id not in log:
            print(f"⚠️ Job {job_id} not found in log")
            return {}
        
        job_data = log[job_id]
        job_data["end_time"] = datetime.now(timezone.utc).isoformat()
        job_data["status"] = "completed"
        job_data["items_processed"] = items_processed
        job_data["message_length"] = message_length
        job_data["model"] = model
        job_data["notes"] = notes
        
        # Calculate tokens if not provided
        if tokens_used is None:
            tokens_used = self.estimate_tokens(items_processed, message_length)
        
        job_data["tokens_used"] = tokens_used
        
        # Calculate cost
        cost_per_1k = MODEL_COSTS.get(model, MODEL_COSTS["default"])
        job_data["estimated_cost"] = (tokens_used / 1000) * cost_per_1k
        
        # Update summary
        self.update_summary(job_data)
        
        # Save log
        self.save_log(log)
        
        print(f"✅ Completed job: {job_id}")
        print(f"   Tokens used: {tokens_used}")
        print(f"   Estimated cost: ${job_data['estimated_cost']:.6f}")
        print(f"   Items processed: {items_processed}")
        
        return job_data
    
    def estimate_tokens(self, items_processed: int, message_length: int) -> int:
        """Estimate token usage based on job parameters."""
        # Base overhead
        tokens = DISCORD_WEBHOOK_OVERHEAD
        
        # Add tokens for items
        tokens += items_processed * PER_ITEM_TOKENS
        
        # Add tokens for message content
        tokens += int(message_length * PER_CHARACTER_TOKENS)
        
        return max(tokens, 0)
    
    def update_summary(self, job_data: Dict[str, Any]):
        """Update token usage summary."""
        summary = self.load_summary()
        
        # Initialize if needed
        if "total_jobs" not in summary:
            summary["total_jobs"] = 0
            summary["total_tokens"] = 0
            summary["total_cost"] = 0.0
            summary["jobs_by_type"] = {}
            summary["daily_usage"] = {}
        
        # Update totals
        summary["total_jobs"] += 1
        summary["total_tokens"] += job_data["tokens_used"]
        summary["total_cost"] += job_data["estimated_cost"]
        
        # Update by job type
        job_type = job_data["job_type"]
        if job_type not in summary["jobs_by_type"]:
            summary["jobs_by_type"][job_type] = {
                "count": 0,
                "tokens": 0,
                "cost": 0.0
            }
        
        summary["jobs_by_type"][job_type]["count"] += 1
        summary["jobs_by_type"][job_type]["tokens"] += job_data["tokens_used"]
        summary["jobs_by_type"][job_type]["cost"] += job_data["estimated_cost"]
        
        # Update daily usage
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if date_str not in summary["daily_usage"]:
            summary["daily_usage"][date_str] = {
                "jobs": 0,
                "tokens": 0,
                "cost": 0.0
            }
        
        summary["daily_usage"][date_str]["jobs"] += 1
        summary["daily_usage"][date_str]["tokens"] += job_data["tokens_used"]
        summary["daily_usage"][date_str]["cost"] += job_data["estimated_cost"]
        
        # Save summary
        self.save_summary(summary)
    
    def load_log(self) -> Dict[str, Any]:
        """Load token log from file."""
        if not TOKEN_LOG_FILE.exists():
            return {}
        
        try:
            with open(TOKEN_LOG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def save_log(self, log: Dict[str, Any]):
        """Save token log to file."""
        with open(TOKEN_LOG_FILE, "w") as f:
            json.dump(log, f, indent=2)
    
    def load_summary(self) -> Dict[str, Any]:
        """Load token summary from file."""
        if not TOKEN_SUMMARY_FILE.exists():
            return {}
        
        try:
            with open(TOKEN_SUMMARY_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def save_summary(self, summary: Dict[str, Any]):
        """Save token summary to file."""
        with open(TOKEN_SUMMARY_FILE, "w") as f:
            json.dump(summary, f, indent=2)
    
    def get_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate a token usage report."""
        summary = self.load_summary()
        log = self.load_log()
        
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_jobs": summary.get("total_jobs", 0),
                "total_tokens": summary.get("total_tokens", 0),
                "total_cost": summary.get("total_cost", 0.0),
                "jobs_by_type": summary.get("jobs_by_type", {}),
            },
            "recent_jobs": {},
            "daily_breakdown": {}
        }
        
        # Get recent jobs (last 10)
        recent_jobs = dict(sorted(
            log.items(),
            key=lambda x: x[1].get("start_time", ""),
            reverse=True
        )[:10])
        report["recent_jobs"] = recent_jobs
        
        # Get daily breakdown for specified days
        daily_usage = summary.get("daily_usage", {})
        sorted_dates = sorted(daily_usage.keys(), reverse=True)[:days]
        report["daily_breakdown"] = {date: daily_usage[date] for date in sorted_dates}
        
        return report
    
    def print_report(self, days: int = 7):
        """Print a formatted token usage report."""
        report = self.get_report(days)
        
        print("\n" + "="*60)
        print("TOKEN USAGE REPORT")
        print("="*60)
        print(f"Generated: {report['generated_at']}")
        print(f"Total Jobs: {report['summary']['total_jobs']}")
        print(f"Total Tokens: {report['summary']['total_tokens']:,}")
        print(f"Total Cost: ${report['summary']['total_cost']:.6f}")
        print()
        
        print("📊 By Job Type:")
        print("-"*40)
        for job_type, stats in report['summary']['jobs_by_type'].items():
            print(f"  {job_type}:")
            print(f"    Jobs: {stats['count']}")
            print(f"    Tokens: {stats['tokens']:,}")
            print(f"    Cost: ${stats['cost']:.6f}")
            print(f"    Avg per job: {stats['tokens']//max(stats['count'],1):,} tokens")
        print()
        
        print("📅 Daily Breakdown (last 7 days):")
        print("-"*40)
        for date, stats in report['daily_breakdown'].items():
            print(f"  {date}: {stats['jobs']} jobs, {stats['tokens']:,} tokens, ${stats['cost']:.6f}")
        print()
        
        print("🔄 Recent Jobs:")
        print("-"*40)
        for job_id, job_data in report['recent_jobs'].items():
            status = job_data.get('status', 'unknown')
            tokens = job_data.get('tokens_used', 0)
            cost = job_data.get('estimated_cost', 0.0)
            print(f"  {job_id}: {status}, {tokens:,} tokens, ${cost:.6f}")
        
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Track token consumption for scraper jobs")
    parser.add_argument("--action", choices=["start", "end", "report", "summary"], 
                       required=True, help="Action to perform")
    parser.add_argument("--job-id", help="Job ID for start/end actions")
    parser.add_argument("--job-type", default="scraper_notification", help="Type of job")
    parser.add_argument("--tokens", type=int, help="Tokens used (for end action)")
    parser.add_argument("--items", type=int, default=0, help="Items processed")
    parser.add_argument("--message-length", type=int, default=0, help="Message length in characters")
    parser.add_argument("--model", default="default", help="Model used")
    parser.add_argument("--notes", default="", help="Notes about the job")
    parser.add_argument("--days", type=int, default=7, help="Days for report")
    
    args = parser.parse_args()
    tracker = TokenTracker()
    
    if args.action == "start":
        if not args.job_id:
            print("❌ Error: --job-id required for start action")
            sys.exit(1)
        tracker.start_job(args.job_id, args.job_type)
    
    elif args.action == "end":
        if not args.job_id:
            print("❌ Error: --job-id required for end action")
            sys.exit(1)
        tracker.end_job(
            args.job_id, 
            tokens_used=args.tokens,
            items_processed=args.items,
            message_length=args.message_length,
            model=args.model,
            notes=args.notes
        )
    
    elif args.action == "report":
        tracker.print_report(args.days)
    
    elif args.action == "summary":
        report = tracker.get_report(args.days)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()