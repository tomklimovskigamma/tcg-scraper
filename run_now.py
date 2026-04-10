#!/usr/bin/env python3
"""
Run the scraper now and send Discord notification.
"""

import os
import subprocess
import sys
from pathlib import Path

def main():
    print("🚀 Running Pokémon TCG scraper now...")
    print("="*60)
    
    # Change to scraper directory
    scraper_dir = Path(__file__).parent
    os.chdir(scraper_dir)
    
    # Check for Discord webhook
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    webhook_file = scraper_dir / "discord_webhook.txt"
    
    if not webhook_url and webhook_file.exists():
        with open(webhook_file, "r") as f:
            webhook_url = f.read().strip()
    
    if not webhook_url:
        print("❌ ERROR: Discord webhook not configured")
        print("")
        print("To set up Discord notifications:")
        print("1. Create a webhook in your Discord server:")
        print("   Server Settings → Integrations → Webhooks → New Webhook")
        print("")
        print("2. Set the webhook URL:")
        print("   Option A: Set environment variable:")
        print("     export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'")
        print("")
        print("   Option B: Create discord_webhook.txt file:")
        print("     echo 'https://discord.com/api/webhooks/...' > discord_webhook.txt")
        print("")
        print("Without a webhook, I can run the scraper but can't send notifications.")
        response = input("Continue without Discord notifications? (y/n): ")
        if response.lower() != 'y':
            print("Aborting.")
            return 1
    
    # Run the scraper
    print("\n📊 Running scrapers...")
    try:
        result = subprocess.run(
            [sys.executable, "run_all.py"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print("Scraper output:")
        print("-"*40)
        print(result.stdout)
        
        if result.stderr:
            print("\nErrors:")
            print("-"*40)
            print(result.stderr)
        
        print(f"\nExit code: {result.returncode}")
        
    except subprocess.TimeoutExpired:
        print("❌ Scraper timed out after 5 minutes")
        return 1
    except Exception as e:
        print(f"❌ Error running scraper: {e}")
        return 1
    
    # Send Discord notification if webhook is available
    if webhook_url:
        print("\n🔔 Sending Discord notification...")
        try:
            # First try with --include-in-stock to show current inventory
            notify_cmd = [
                sys.executable, "notify_discord.py",
                "--include-in-stock"
            ]
            
            result = subprocess.run(
                notify_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            print("Notification output:")
            print("-"*40)
            print(result.stdout)
            
            if result.stderr:
                print("\nNotification errors:")
                print("-"*40)
                print(result.stderr)
            
            if result.returncode != 0:
                print(f"\n⚠️  Notification failed with exit code {result.returncode}")
                print("Trying with --force flag for test notification...")
                
                # Try force notification
                force_cmd = [
                    sys.executable, "notify_discord.py",
                    "--force"
                ]
                
                result = subprocess.run(
                    force_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                print("Force notification output:")
                print("-"*40)
                print(result.stdout)
                
        except Exception as e:
            print(f"❌ Error sending notification: {e}")
    else:
        print("\n⚠️  No Discord webhook configured - skipping notification")
        print("To enable notifications, set DISCORD_WEBHOOK_URL environment variable")
        print("or create discord_webhook.txt file with your webhook URL.")
    
    # Show data summary
    print("\n" + "="*60)
    print("DATA SUMMARY")
    print("="*60)
    
    data_dir = scraper_dir / "data"
    if data_dir.exists():
        json_files = list(data_dir.glob("*.json"))
        if json_files:
            print(f"Found {len(json_files)} data file(s):")
            for json_file in sorted(json_files):
                size = json_file.stat().st_size
                print(f"  {json_file.name} ({size} bytes)")
        else:
            print("No JSON data files found")
    else:
        print("Data directory not found")
    
    print("\n" + "="*60)
    print("✅ Run completed!")
    print("="*60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())