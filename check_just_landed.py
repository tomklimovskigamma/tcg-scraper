#!/usr/bin/env python3
import json
import os
import glob
from datetime import datetime

def check_just_landed():
    data_dir = "/Users/tomklimovski/clawd/tcg-scraper/data"
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    
    all_items = []
    store_items = {}
    
    for json_file in json_files:
        # Skip token files
        if "token" in json_file:
            continue
            
        store_name = os.path.basename(json_file).replace("_inventory.json", "").replace("inventory.json", "combined")
        if store_name == "combined":
            store_name = "combined"
        elif store_name == "":
            store_name = "unknown"
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Check for just_landed array
            if isinstance(data, dict) and 'just_landed' in data:
                just_landed = data['just_landed']
                if isinstance(just_landed, list) and len(just_landed) > 0:
                    for item in just_landed:
                        if isinstance(item, dict):
                            title = item.get('title', 'Unknown Title')
                            url = item.get('url', '')
                            all_items.append({
                                'store': store_name,
                                'title': title,
                                'url': url
                            })
                    
                    store_items[store_name] = len(just_landed)
                    
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error reading {json_file}: {e}")
            continue
    
    return all_items, store_items

if __name__ == "__main__":
    items, store_counts = check_just_landed()
    total_items = len(items)
    
    print(f"Total just_landed items found: {total_items}")
    for store, count in store_counts.items():
        print(f"  {store}: {count} items")
    
    # Log to run_log.txt
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - Run completed - Found {total_items} items"
    if total_items == 0:
        log_entry = f"{timestamp} - Run completed - No items found"
    
    with open("/Users/tomklimovski/clawd/run_log.txt", "a") as log_file:
        log_file.write(log_entry + "\n")
    
    print(f"\nLogged: {log_entry}")
    
    # Print items for Discord message
    if total_items > 0:
        print("\nItems found:")
        for item in items:
            print(f"• [{item['store']}] {item['title']}: {item['url']}")