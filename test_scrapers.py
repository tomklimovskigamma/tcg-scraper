#!/usr/bin/env python3
"""
Test suite for Pokémon TCG scrapers.
Tests for:
1. Network connectivity and rate limiting
2. HTML parsing and data extraction
3. Website blocking detection
4. Script functionality
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable

# Test URLs for each retailer
TEST_URLS = {
    "jbhifi": "https://www.jbhifi.com.au/collections/pokemon",
    "target": "https://www.target.com.au/c/pokemon-trading-cards",
    "kmart": "https://www.kmart.com.au/search/?q=pokemon%20cards",
    "bigw": "https://www.bigw.com.au/search/?q=pokemon%20cards"
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

def log_test(test_name: str, status: str, message: str = "", details: str = ""):
    """Log test results with timestamp."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    status_symbol = "✓" if status == "PASS" else "✗" if status == "FAIL" else "⚠"
    print(f"[{ts}] {status_symbol} {test_name}: {message}")
    if details:
        print(f"      Details: {details}")

def test_network_connectivity() -> Dict[str, bool]:
    """Test if we can reach each retailer's website."""
    results = {}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    
    for retailer, url in TEST_URLS.items():
        try:
            start = time.time()
            response = session.get(url, timeout=10)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                results[retailer] = True
                log_test(f"Network/{retailer}", "PASS", 
                        f"Connected in {elapsed:.2f}s", 
                        f"Status: {response.status_code}, Size: {len(response.text)} chars")
            elif response.status_code == 403 or response.status_code == 429:
                results[retailer] = False
                log_test(f"Network/{retailer}", "FAIL", 
                        f"Blocked (HTTP {response.status_code})", 
                        f"Likely rate limiting or bot detection")
            else:
                results[retailer] = False
                log_test(f"Network/{retailer}", "FAIL", 
                        f"HTTP {response.status_code}", 
                        f"Response: {response.text[:100]}...")
                
        except requests.exceptions.Timeout:
            results[retailer] = False
            log_test(f"Network/{retailer}", "FAIL", "Timeout", "Site not responding within 10s")
        except requests.exceptions.RequestException as e:
            results[retailer] = False
            log_test(f"Network/{retailer}", "FAIL", f"Connection error: {str(e)}", "")
    
    return results

def test_html_parsing() -> Dict[str, bool]:
    """Test if we can parse HTML from each retailer."""
    results = {}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    
    for retailer, url in TEST_URLS.items():
        try:
            response = session.get(url, timeout=10)
            if response.status_code != 200:
                results[retailer] = False
                log_test(f"Parsing/{retailer}", "FAIL", f"HTTP {response.status_code}", "Cannot parse non-200 response")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check for common anti-bot measures
            page_text = soup.get_text().lower()
            anti_bot_indicators = [
                "access denied", "you are being rate limited", "cloudflare",
                "distil security", "imperva", "incapsula", "bot detected"
            ]
            
            found_indicators = [indicator for indicator in anti_bot_indicators 
                              if indicator in page_text]
            
            if found_indicators:
                results[retailer] = False
                log_test(f"Parsing/{retailer}", "FAIL", "Anti-bot detected", 
                        f"Found: {', '.join(found_indicators)}")
                continue
            
            # Check for actual product content
            product_indicators = ["pokemon", "card", "price", "product", "item"]
            text_lower = page_text[:5000]  # Check first 5k chars
            
            found_products = [indicator for indicator in product_indicators 
                            if indicator in text_lower]
            
            if len(found_products) >= 2:
                results[retailer] = True
                log_test(f"Parsing/{retailer}", "PASS", "HTML parsed successfully",
                        f"Found product indicators: {', '.join(found_products[:3])}")
            else:
                results[retailer] = False
                log_test(f"Parsing/{retailer}", "FAIL", "No product content found",
                        "Page may be empty or require JavaScript")
                
        except Exception as e:
            results[retailer] = False
            log_test(f"Parsing/{retailer}", "FAIL", f"Parsing error: {str(e)}", "")

    return results

def test_individual_scrapers() -> Dict[str, bool]:
    """Test each scraper script individually."""
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
            log_test(f"Scraper/{name}", "FAIL", "Script not found", f"Path: {path}")
            continue
            
        try:
            start = time.time()
            # Run with --test flag if supported, otherwise just run
            cmd = [PYTHON, str(path)]
            if name == "jbhifi":
                cmd.extend(["--test", "--limit", "2"])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            elapsed = time.time() - start
            
            if result.returncode == 0:
                # Check if output contains data
                output = result.stdout.lower()
                if "error" in output or "traceback" in output:
                    results[name] = False
                    log_test(f"Scraper/{name}", "FAIL", f"Script error in {elapsed:.1f}s",
                            f"Output: {output[:200]}...")
                elif "product" in output or "item" in output or "found" in output:
                    results[name] = True
                    log_test(f"Scraper/{name}", "PASS", f"Ran successfully in {elapsed:.1f}s",
                            f"Output length: {len(output)} chars")
                else:
                    results[name] = False
                    log_test(f"Scraper/{name}", "FAIL", f"No product data in {elapsed:.1f}s",
                            "Script may be returning empty results")
            else:
                results[name] = False
                log_test(f"Scraper/{name}", "FAIL", f"Exit code {result.returncode} in {elapsed:.1f}s",
                        f"Stderr: {result.stderr[:200]}...")
                
        except subprocess.TimeoutExpired:
            results[name] = False
            log_test(f"Scraper/{name}", "FAIL", "Timeout after 30s", "Script may be stuck or blocked")
        except Exception as e:
            results[name] = False
            log_test(f"Scraper/{name}", "FAIL", f"Execution error: {str(e)}", "")

    return results

def test_data_files() -> Dict[str, bool]:
    """Check if data files are being created/updated."""
    data_dir = HERE / "data"
    results = {}
    
    if not data_dir.exists():
        log_test("Data/files", "FAIL", "Data directory missing", f"Path: {data_dir}")
        return {retailer: False for retailer in TEST_URLS.keys()}
    
    retailers = ["jbhifi", "target", "kmart", "bigw"]
    for retailer in retailers:
        json_file = data_dir / f"{retailer}.json"
        
        if json_file.exists():
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                if isinstance(data, list) and len(data) > 0:
                    results[retailer] = True
                    log_test(f"Data/{retailer}", "PASS", f"File exists with {len(data)} items",
                            f"Path: {json_file}")
                else:
                    results[retailer] = False
                    log_test(f"Data/{retailer}", "FAIL", "File exists but empty or invalid",
                            f"Content: {json.dumps(data)[:100]}...")
            except json.JSONDecodeError:
                results[retailer] = False
                log_test(f"Data/{retailer}", "FAIL", "Invalid JSON", f"File: {json_file}")
            except Exception as e:
                results[retailer] = False
                log_test(f"Data/{retailer}", "FAIL", f"Read error: {str(e)}", "")
        else:
            results[retailer] = False
            log_test(f"Data/{retailer}", "FAIL", "File not found", f"Expected: {json_file}")
    
    return results

def test_rate_limiting() -> Dict[str, bool]:
    """Test if we're being rate limited by making multiple quick requests."""
    results = {}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    
    for retailer, url in TEST_URLS.items():
        try:
            # Make 3 quick requests to test rate limiting
            status_codes = []
            for i in range(3):
                response = session.get(url, timeout=5)
                status_codes.append(response.status_code)
                time.sleep(0.5)  # Small delay between requests
            
            # Check if we got blocked on subsequent requests
            blocked = any(code in [403, 429] for code in status_codes)
            
            if blocked:
                results[retailer] = False
                log_test(f"RateLimit/{retailer}", "FAIL", "Rate limited detected",
                        f"Status codes: {status_codes}")
            else:
                results[retailer] = True
                log_test(f"RateLimit/{retailer}", "PASS", "No rate limiting",
                        f"Status codes: {status_codes}")
                
        except Exception as e:
            results[retailer] = False
            log_test(f"RateLimit/{retailer}", "FAIL", f"Test error: {str(e)}", "")
    
    return results

def run_comprehensive_test() -> bool:
    """Run all tests and provide summary."""
    print("\n" + "="*60)
    print("Pokémon TCG Scraper Diagnostic Tests")
    print("="*60 + "\n")
    
    print("Testing network connectivity...")
    network_results = test_network_connectivity()
    
    print("\nTesting HTML parsing...")
    parsing_results = test_html_parsing()
    
    print("\nTesting rate limiting...")
    rate_results = test_rate_limiting()
    
    print("\nTesting individual scrapers...")
    scraper_results = test_individual_scrapers()
    
    print("\nChecking data files...")
    data_results = test_data_files()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_retailers = set(TEST_URLS.keys())
    for retailer in sorted(all_retailers):
        tests = [
            ("Network", network_results.get(retailer)),
            ("Parsing", parsing_results.get(retailer)),
            ("RateLimit", rate_results.get(retailer)),
            ("Scraper", scraper_results.get(retailer)),
            ("Data", data_results.get(retailer))
        ]
        
        passed = sum(1 for _, result in tests if result is True)
        total = sum(1 for _, result in tests if result is not None)
        
        status = "✅" if passed == total else "⚠️" if passed > 0 else "❌"
        print(f"{status} {retailer.upper():10} {passed}/{total} tests passed")
        
        # Show details for failed tests
        for test_name, result in tests:
            if result is False:
                print(f"      ✗ {test_name} failed")
    
    # Overall assessment
    total_passed = sum(1 for results in [network_results, parsing_results, rate_results, scraper_results, data_results]
                      for result in results.values() if result is True)
    total_tests = sum(len(results) for results in [network_results, parsing_results, rate_results, scraper_results, data_results])
    
    print(f"\nOverall: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("🎉 All tests passed! Scrapers should be working correctly.")
        return True
    elif total_passed >= total_tests * 0.7:
        print("⚠️  Some tests failed. Scrapers may have partial issues.")
        print("   Common issues: rate limiting, website changes, or network problems.")
        return False
    else:
        print("❌ Multiple tests failed. Scrapers likely not working.")
        print("   Check: Network connectivity, website blocking, or script errors.")
        return False

def quick_test() -> bool:
    """Run a quick test to check basic functionality."""
    print("\nRunning quick diagnostic...")
    
    # Test one scraper
    test_scraper = HERE / "scrape_jbhifi.py"
    if not test_scraper.exists():
        print("❌ Scraper script not found")
        return False
    
    try:
        result = subprocess.run([PYTHON, str(test_scraper), "--test", "--limit", "1"], 
                              capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0 and "product" in result.stdout.lower():
            print("✅ Basic scraper test passed")
            return True
        else:
            print(f"❌ Scraper test failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        success = quick_test()
        sys.exit(0 if success else 1)
    else:
        success = run_comprehensive_test()
        sys.exit(0 if success else 1)