#!/usr/bin/env python3
"""
Diagnose scraper issues by analyzing data files and logs.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def analyze_data_file(filepath):
    """Analyze a JSON data file to understand its structure and contents."""
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return None
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        print(f"\n📊 Analyzing: {filepath.name}")
        print("-" * 40)
        
        # Show all keys
        print(f"Keys: {list(data.keys())}")
        
        # Count items in different sections
        for key in ['in_stock', 'out_of_stock', 'just_landed', 'products', 'items']:
            if key in data:
                items = data[key]
                if isinstance(items, list):
                    print(f"{key}: {len(items)} items")
                    if items and len(items) > 0:
                        # Show first item structure
                        first = items[0]
                        print(f"  First item keys: {list(first.keys())}")
                        if 'title' in first:
                            print(f"  Title: {first['title'][:80]}...")
                        if 'price' in first:
                            print(f"  Price: {first['price']}")
        
        # Check for errors
        if 'errors' in data and data['errors']:
            print(f"Errors: {len(data['errors'])}")
            for error in data['errors'][:3]:
                print(f"  - {error[:100]}...")
        
        # Check totals if present
        if 'totals' in data:
            print(f"Totals: {data['totals']}")
        
        return data
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return None

def check_run_log(log_path):
    """Analyze the run log to identify patterns."""
    if not os.path.exists(log_path):
        print(f"❌ Log file not found: {log_path}")
        return
    
    print(f"\n📝 Analyzing run log: {log_path}")
    print("-" * 40)
    
    with open(log_path, 'r') as f:
        lines = f.readlines()
    
    print(f"Total runs logged: {len(lines)}")
    
    # Count results
    found_counts = {'found': 0, 'none': 0}
    for line in lines:
        if 'Found' in line and 'items' in line:
            found_counts['found'] += 1
        elif 'No items found' in line:
            found_counts['none'] += 1
    
    print(f"Runs with items found: {found_counts['found']}")
    print(f"Runs with no items: {found_counts['none']}")
    
    # Show recent runs
    print("\nRecent runs (last 10):")
    for line in lines[-10:]:
        print(f"  {line.strip()}")

def check_scraper_health():
    """Check overall scraper health."""
    print("="*60)
    print("SCRAPER DIAGNOSTIC REPORT")
    print("="*60)
    
    # Check original data directory
    original_data_dir = Path("/Users/sguerra/pokemon/jb-hifi/data")
    if original_data_dir.exists():
        print(f"\n✅ Original data directory exists: {original_data_dir}")
        
        # Analyze each JSON file
        json_files = list(original_data_dir.glob("*.json"))
        print(f"Found {len(json_files)} JSON files")
        
        for json_file in sorted(json_files):
            analyze_data_file(json_file)
    
    # Check run log
    run_log = Path("/Users/tomklimovski/clawd/run_log.txt")
    check_run_log(run_log)
    
    # Check repository files
    repo_dir = Path(__file__).parent
    print(f"\n📁 Repository directory: {repo_dir}")
    
    # List scraper files
    scraper_files = list(repo_dir.glob("scrape_*.py"))
    print(f"Scraper scripts: {len(scraper_files)}")
    for f in scraper_files:
        size = f.stat().st_size
        print(f"  {f.name} ({size} bytes)")
    
    # Check requirements
    req_file = repo_dir / "requirements.txt"
    if req_file.exists():
        with open(req_file, 'r') as f:
            reqs = f.read().strip()
        print(f"\n📦 Requirements: {reqs}")
    
    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    print("1. **Issue identified**: 'just_landed' array is empty in inventory.json")
    print("   → The scraper finds items but the 'new item' detection isn't working")
    print("   → Check the logic in scrape_jbhifi.py for just_landed detection")
    
    print("\n2. **Possible fixes**:")
    print("   a) Update the notification logic to check 'in_stock' instead of 'just_landed'")
    print("   b) Fix the just_landed detection algorithm")
    print("   c) Check if price parsing is working (some prices are None)")
    
    print("\n3. **Testing needed**:")
    print("   a) Run scrapers manually to see raw output")
    print("   b) Check if websites are blocking requests")
    print("   c) Verify network connectivity to retailer sites")
    
    print("\n4. **Immediate action**:")
    print("   Update run_all.py or notification logic to use 'in_stock' count > 0")
    print("   instead of relying on 'just_landed' for notifications")

def main():
    check_scraper_health()
    return 0

if __name__ == "__main__":
    sys.exit(main())