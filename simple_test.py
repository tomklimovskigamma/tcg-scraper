#!/usr/bin/env python3
"""
Simple test to check scraper functionality.
"""

import subprocess
import sys
import os

def test_scraper(name, script_path, args=None):
    """Test a single scraper."""
    if not os.path.exists(script_path):
        print(f"❌ {name}: Script not found at {script_path}")
        return False
    
    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)
    
    try:
        print(f"Testing {name}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"✅ {name}: Ran successfully")
            print(f"   Output: {result.stdout[:200]}...")
            return True
        else:
            print(f"❌ {name}: Failed with exit code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}...")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ {name}: Timeout after 30s")
        return False
    except Exception as e:
        print(f"❌ {name}: Unexpected error: {str(e)}")
        return False

def main():
    print("="*60)
    print("Simple Scraper Test")
    print("="*60)
    
    scrapers = [
        ("JB Hi-Fi", "scrape_jbhifi.py", []),
        ("Target", "scrape_target.py", []),
        ("Kmart", "scrape_kmart.py", []),
        ("Big W", "scrape_bigw.py", []),
    ]
    
    results = []
    for name, script, args in scrapers:
        success = test_scraper(name, script, args)
        results.append((name, success))
        print()
    
    print("="*60)
    print("Summary:")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print(f"\n{passed}/{total} scrapers passed")
    
    if passed == total:
        print("🎉 All scrapers working!")
        return 0
    elif passed > 0:
        print("⚠️  Some scrapers failing")
        return 1
    else:
        print("❌ All scrapers failing")
        return 2

if __name__ == "__main__":
    sys.exit(main())