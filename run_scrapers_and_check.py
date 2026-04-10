#!/usr/bin/env python3
"""
Run Pokémon TCG scrapers and check for just_landed items.
"""

import os
import subprocess
import json
import glob
import time
from datetime import datetime

def run_scrapers():
    """Run the existing run_all.py script."""
    print(f"Running scrapers at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    run_all_path = "/users/sguerra/pokemon/jb-hifi/run_all.py"
    
    if not os.path.exists(run_all_path):
        print(f"Error: run_all.py not found at {run_all_path}")
        return False
    
    try:
        # Change to the directory and run the script
        original_dir = os.getcwd()
        os.chdir(os.path.dirname(run_all_path))
        
        result = subprocess.run(
            ["python3", run_all_path],
            capture_output=True,
            text=True
        )
        
        os.chdir(original_dir)
        
        print(f"Scrapers exit code: {result.returncode}")
        print(f"Scrapers output:\n{result.stdout}")
        
        if result.stderr:
            print(f"Scrapers errors:\n{result.stderr}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"Error running scrapers: {e}")
        return False

def check_just_landed():
    """Check all JSON files in data directory for items in just_landed section."""
    data_dir = "/users/sguerra/pokemon/jb-hifi/data"
    
    # Check if data directory exists
    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        return []
    
    # Find all JSON files
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    
    if not json_files:
        print("No JSON files found in data directory")
        return []
    
    just_landed_items = []
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Check for just_landed section
            if "just_landed" in data and data["just_landed"]:
                items = data["just_landed"]
                if isinstance(items, list) and len(items) > 0:
                    just_landed_items.extend(items)
                    print(f"Found {len(items)} items in just_landed section of {os.path.basename(json_file)}")
                elif items:  # If it's not empty but not a list
                    just_landed_items.append(items)
                    print(f"Found item in just_landed section of {os.path.basename(json_file)}")
                    
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading {json_file}: {e}")
    
    return just_landed_items

def main():
    """Main function."""
    print(f"Starting Pokémon TCG check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run scrapers
    print("\n--- Running scrapers ---")
    scrapers_success = run_scrapers()
    
    if not scrapers_success:
        print("Scrapers failed, but will still check existing JSON files")
    
    # Wait a moment for files to be written
    time.sleep(2)
    
    # Check for just_landed items
    print("\n--- Checking for just_landed items ---")
    items = check_just_landed()
    
    # If items found, prepare Discord message
    if items:
        print("\n" + "="*60)
        print("🚨 POKÉMON TCG ITEMS JUST LANDED! 🚨")
        print("="*60)
        
        # Group items by store
        stores = {}
        for item in items:
            if isinstance(item, dict):
                store = item.get("_source_name", "Unknown Store")
            else:
                store = "Unknown Store"
            
            if store not in stores:
                stores[store] = []
            stores[store].append(item)
        
        # Build Discord message
        discord_message = f"@here 🚨 **New Pokémon TCG items just landed!** 🚨\nFound {len(items)} item(s):\n\n"
        
        for store, store_items in stores.items():
            discord_message += f"**{store}** ({len(store_items)} items):\n"
            for i, item in enumerate(store_items[:3], 1):  # Show first 3 per store
                if isinstance(item, dict):
                    title = item.get("title", "Unknown item")
                    price = item.get("price_aud")
                    price_str = f"${price:.2f}" if price else "Price N/A"
                    url = item.get("url", "")
                    
                    if url:
                        discord_message += f"  {i}. [{title}]({url}) - {price_str}\n"
                    else:
                        discord_message += f"  {i}. {title} - {price_str}\n"
                else:
                    discord_message += f"  {i}. {str(item)[:100]}...\n"
            
            if len(store_items) > 3:
                discord_message += f"  ... and {len(store_items) - 3} more\n"
            
            discord_message += "\n"
        
        if len(items) > 10:
            discord_message += f"\n*Showing first 10 of {len(items)} total items*"
        
        print(f"\nDiscord message to send:\n{discord_message}")
        
        # Write message to file for OpenClaw to pick up
        with open("discord_message.txt", "w") as f:
            f.write(discord_message)
        
        # Exit with code 1 to indicate items found
        return 1
    else:
        print("No items found in just_landed sections")
        return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)