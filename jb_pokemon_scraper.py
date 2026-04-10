import requests
from bs4 import BeautifulSoup

def check_jb_hifi_pokemon_stock(url):
    """
    Checks the JB Hi-Fi Pokémon cards page for stock indicators.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- Stock Indicator Logic ---
        # This part might need adjustment if JB Hi-Fi changes their website HTML.
        # We'll look for common elements that indicate product availability.
        
        # Example 1: Look for "Add to cart" buttons
        add_to_cart_buttons = soup.find_all('button', class_='add-to-cart-button')
        if add_to_cart_buttons:
            print(f"💋 Found {len(add_to_cart_buttons)} 'Add to Cart' buttons!")
            return True

        # Example 2: Look for product cards that are not marked as "sold out" or "unavailable"
        # This is a more general approach if specific buttons are hard to find.
        # You'll need to inspect the page to find the correct div/class for product listings
        product_cards = soup.find_all('div', class_='product-card') # Adjust this class as needed
        
        if product_cards:
            found_available = False
            for card in product_cards:
                # Check if the card explicitly says "Sold Out" or "Unavailable"
                sold_out_text = card.find(string=lambda text: "Sold Out" in text or "Unavailable" in text)
                if not sold_out_text:
                    found_available = True
                    break
            
            if found_available:
                print(f"💋 Found available Pokémon cards on the page!")
                return True

        # If we reach here, we didn't find clear indicators of stock
        print("🤷‍♀️ Couldn't find clear indicators of Pokémon cards in stock.")
        return False
        
    except requests.exceptions.RequestException as e:
        print(f"💔 Error fetching the page, honey: {e}")
        return False

# --- Main execution ---
if __name__ == "__main__":
    jb_hifi_url = "https://www.jbhifi.com.au/collections/collectibles-merchandise/pokemon-trading-cards"
    print(f"✨ Checking stock for Pokémon cards at JB Hi-Fi, babe! URL: {jb_hifi_url}")
    
    if check_jb_hifi_pokemon_stock(jb_hifi_url):
        print("🎉 Good news, hottie! It looks like Pokémon cards might be available at JB Hi-Fi! Go check it out! 😉")
    else:
        print("😔 No luck today, sweetie. Pokémon cards don't seem to be readily available online at JB Hi-Fi right now. Keep an eye out!")
