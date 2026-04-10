#!/usr/bin/env python3
"""
Monitor scraper health and detect common issues.
Run this periodically to check if scrapers are working.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable

def get_timestamp() -> str:
    """Get current timestamp for logging."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def check_data_freshness() -> Dict[str, bool]:
    """Check if data files are fresh (updated in last 2 hours)."""
    data_dir = HERE / "data"
    results = {}
    
    if not data_dir.exists():
        print(f"[{get_timestamp()}] ❌ Data directory not found: {data_dir}")
        return {}
    
    retailers = ["jbhifi", "target", "kmart", "bigw"]
    cutoff_time = datetime.now() - timedelta(hours=2)
    
    for retailer in retailers:
        json_file = data_dir / f"{retailer}.json"
        
        if json_file.exists():
            mtime = datetime.fromtimestamp(json_file.stat().st_mtime)
            is_fresh = mtime > cutoff_time
            
            results[retailer] = is_fresh
            
            if is_fresh:
                age = datetime.now() - mtime
                print(f"[{get_timestamp()}] ✅ {retailer}: Data fresh ({age.seconds//60} minutes ago)")
            else:
                age = datetime.now() - mtime
                print(f"[{get_timestamp()}] ⚠️  {retailer}: Data stale ({age.days}d {age.seconds//3600}h ago)")
        else:
            results[retailer] = False
            print(f"[{get_timestamp()}] ❌ {retailer}: No data file found")
    
    return results

def check_scraper_output() -> Dict[str, bool]:
    """Run each scraper briefly to check for errors."""
    scrapers = {
        "jbhifi": HERE / "scrape_jbhifi.py",
        "target": HERE / "scrape_target.py", 
        "kmart": HERE / "scrape_kmart.py",
        "bigw": HERE / "scrape_bigw.py"
    }
    
    results = {}
    
    for name, path in scrapers.items():
        if not path.exists():
            results[name] = False
            print(f"[{get_timestamp()}] ❌ {name}: Script not found")
            continue
        
        try:
            # Run with minimal output/limit
            cmd = [PYTHON, str(path)]
            if name == "jbhifi":
                cmd.extend(["--limit", "1", "--quiet"])
            
            start = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            elapsed = time.time() - start
            
            if result.returncode == 0:
                # Check for common error patterns
                output = result.stdout.lower() + result.stderr.lower()
                error_indicators = [
                    "error", "exception", "traceback", "timeout",
                    "blocked", "403", "429", "cloudflare", "captcha"
                ]
                
                has_error = any(indicator in output for indicator in error_indicators)
                
                if has_error:
                    results[name] = False
                    error_msg = result.stderr[:200] if result.stderr else result.stdout[:200]
                    print(f"[{get_timestamp()}] ❌ {name}: Error detected in {elapsed:.1f}s")
                    print(f"      Error: {error_msg}...")
                else:
                    results[name] = True
                    print(f"[{get_timestamp()}] ✅ {name}: Ran successfully in {elapsed:.1f}s")
            else:
                results[name] = False
                print(f"[{get_timestamp()}] ❌ {name}: Failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"      Stderr: {result.stderr[:200]}...")
                    
        except subprocess.TimeoutExpired:
            results[name] = False
            print(f"[{get_timestamp()}] ❌ {name}: Timeout after 30s (may be blocked)")
        except Exception as e:
            results[name] = False
            print(f"[{get_timestamp()}] ❌ {name}: Unexpected error: {str(e)}")
    
    return results

def check_website_access() -> Dict[str, bool]:
    """Quick check if websites are accessible."""
    import requests
    
    websites = {
        "jbhifi": "https://www.jbhifi.com.au/collections/pokemon",
        "target": "https://www.target.com.au/c/pokemon-trading-cards",
        "kmart": "https://www.kmart.com.au/search/?q=pokemon%20cards",
        "bigw": "https://www.bigw.com.au/search/?q=pokemon%20cards"
    }
    
    results = {}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    
    for name, url in websites.items():
        try:
            response = session.get(url, timeout=10)
            
            if response.status_code == 200:
                results[name] = True
                print(f"[{get_timestamp()}] ✅ {name}: Website accessible")
            elif response.status_code in [403, 429]:
                results[name] = False
                print(f"[{get_timestamp()}] ❌ {name}: Blocked (HTTP {response.status_code})")
            else:
                results[name] = False
                print(f"[{get_timestamp()}] ❌ {name}: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            results[name] = False
            print(f"[{get_timestamp()}] ❌ {name}: Timeout")
        except Exception as e:
            results[name] = False
            print(f"[{get_timestamp()}] ❌ {name}: Connection error: {str(e)}")
    
    return results

def generate_report() -> Dict[str, Dict[str, bool]]:
    """Generate comprehensive health report."""
    print("\n" + "="*60)
    print("Pokémon TCG Scraper Health Check")
    print("="*60 + "\n")
    
    print("1. Checking website access...")
    website_results = check_website_access()
    
    print("\n2. Checking scraper functionality...")
    scraper_results = check_scraper_output()
    
    print("\n3. Checking data freshness...")
    data_results = check_data_freshness()
    
    # Summary
    print("\n" + "="*60)
    print("HEALTH SUMMARY")
    print("="*60)
    
    all_retailers = set(website_results.keys()) | set(scraper_results.keys()) | set(data_results.keys())
    
    for retailer in sorted(all_retailers):
        website_ok = website_results.get(retailer, False)
        scraper_ok = scraper_results.get(retailer, False)
        data_ok = data_results.get(retailer, False)
        
        status = []
        if website_ok:
            status.append("🌐")
        else:
            status.append("❌")
        
        if scraper_ok:
            status.append("🐍")
        else:
            status.append("❌")
        
        if data_ok:
            status.append("💾")
        else:
            status.append("❌")
        
        print(f"{' '.join(status)} {retailer.upper():10} "
              f"[Site: {'OK' if website_ok else 'FAIL'}, "
              f"Scraper: {'OK' if scraper_ok else 'FAIL'}, "
              f"Data: {'OK' if data_ok else 'STALE'}]")
    
    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    issues_found = False
    
    for retailer in sorted(all_retailers):
        website_ok = website_results.get(retailer, False)
        scraper_ok = scraper_results.get(retailer, False)
        data_ok = data_results.get(retailer, False)
        
        if not website_ok:
            print(f"• {retailer.upper()}: Website inaccessible - check network or IP blocking")
            issues_found = True
        
        if website_ok and not scraper_ok:
            print(f"• {retailer.upper()}: Website OK but scraper failing - script may need update")
            issues_found = True
        
        if scraper_ok and not data_ok:
            print(f"• {retailer.upper()}: Scraper runs but no fresh data - check output/parsing")
            issues_found = True
    
    if not issues_found:
        print("✅ All systems operational!")
    
    return {
        "websites": website_results,
        "scrapers": scraper_results,
        "data": data_results
    }

def main() -> int:
    """Main entry point."""
    try:
        report = generate_report()
        
        # Determine overall status
        all_website_ok = all(report["websites"].values())
        all_scraper_ok = all(report["scrapers"].values())
        all_data_ok = all(report["data"].values())
        
        if all_website_ok and all_scraper_ok and all_data_ok:
            return 0  # Success
        elif all_website_ok and all_scraper_ok:
            return 1  # Warning (data stale)
        else:
            return 2  # Error (website or scraper issues)
            
    except Exception as e:
        print(f"[{get_timestamp()}] ❌ Health check failed: {str(e)}")
        return 3

if __name__ == "__main__":
    sys.exit(main())