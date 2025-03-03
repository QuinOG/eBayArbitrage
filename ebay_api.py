import os
import base64
import requests
import re
from datetime import datetime, timezone
import time
import statistics

DEBUG = True

# In-memory cache for listings
listing_cache = {
    "listings": [],
    "timestamp": None
}

def request_with_retry(method, url, headers=None, params=None, data=None, max_attempts=3, delay=3):
    attempt = 0
    current_delay = delay
    while attempt < max_attempts:
        try:
            response = requests.request(method, url, headers=headers, params=params, data=data)
            if response.status_code == 503:
                if DEBUG:
                    print(f"Attempt {attempt+1}: Received 503 for {url}. Retrying in {current_delay} seconds...")
                time.sleep(current_delay)
                attempt += 1
                current_delay *= 2
                continue
            return response
        except Exception as e:
            if DEBUG:
                print(f"Attempt {attempt+1}: Exception {e} for {url}. Retrying in {current_delay} seconds...")
            time.sleep(current_delay)
            attempt += 1
            current_delay *= 2
    if DEBUG:
        print(f"Max retries reached for {url}, returning last response with status {response.status_code}")
    return response

def is_consumer_cpu(model_str):
    """
    Returns True if 'model_str' is a typical consumer CPU:
    Intel Core i3/i5/i7/i9 or AMD Ryzen 3/5/7/9.
    Otherwise returns False.
    """
    pattern = r'^(?:intel\s+core\s+i[3579]|amd\s+ryzen\s+[3579])'
    return bool(re.search(pattern, model_str.lower()))

def extract_cpu_model(title):
    # Remove special characters like ®, ™, etc., and normalize spaces
    title_clean = re.sub(r'[®™]', '', title)
    title_lower = re.sub(r'\s+', ' ', title_clean.lower()).strip()
    extracted = None

    # 1) Intel Core (with optional "core", handles variations)
    intel_match = re.search(r'(intel\s+(?:core\s+)?i\d[- ]*\d{3,5}[a-z0-9]*)\b', title_lower)
    if intel_match:
        extracted = intel_match.group(0).strip()

    # 2) AMD Ryzen (flexible for optional "AMD")
    if not extracted:
        amd_ryzen_match = re.search(r'(?:amd\s+)?ryzen\s+\d+\s+\d{3,5}[a-z0-9]*\b', title_lower)
        if amd_ryzen_match:
            extracted = amd_ryzen_match.group(0).strip()

    # 3) AMD Athlon (excluded as non-consumer, but check for clarity)
    if not extracted:
        amd_athlon_match = re.search(r'(amd\s+(?:athlon\s+(?:64\s+)?)?[a-z0-9-]*\d+[a-z0-9-]*)\b', title_lower)
        if amd_athlon_match:
            extracted = amd_athlon_match.group(1).strip()

    # 4) Intel Xeon (explicitly skip as non-consumer)
    if not extracted:
        intel_xeon_match = re.search(r'(intel\s+xeon\s+w[-\s]?\d{3,5}[a-z0-9-]*(?:\s+\d+-core)?)\b', title_lower)
        if intel_xeon_match:
            extracted = intel_xeon_match.group(1).strip()

    # 5) Intel Core 2 Duo (explicitly skip as non-consumer)
    if not extracted:
        intel_core2_match = re.search(r'(intel\s+core\s+2\s+duo\s+[a-z]\d{4,5})\b', title_lower)
        if intel_core2_match:
            extracted = intel_core2_match.group(1).strip()

    # 6) AMD Ryzen Pro (explicitly skip as non-consumer)
    if not extracted:
        amd_ryzen_pro_match = re.search(r'(?:amd\s+)?ryzen\s+(?:pro\s+)?\d+\s+\d{3,5}[a-z0-9]*\b', title_lower)
        if amd_ryzen_pro_match:
            extracted = amd_ryzen_pro_match.group(0).strip()

    # 7) Mixed lots or vintage processors (e.g., Pentium Pro, lots)
    if not extracted:
        lot_match = re.search(r'(?:lot\s+of\s+\d+\s+assorted\s+)?(?:intel\s+(?:pentium|celeron|core\s+2)|amd\s+(?:athlon))\b', title_lower)
        if lot_match:
            extracted = lot_match.group(0).strip()

    if extracted:
        # Attempt to extract a refresh rate (e.g., "3.6GHz")
        refresh_rate_match = re.search(r'(\d+\.\d+)\s*ghz', title_lower)
        if refresh_rate_match:
            rr = refresh_rate_match.group(1).strip()
            # Remove trailing zeros and format (e.g., "3.00" -> "3", "3.40" -> "3.4")
            rr_clean = str(float(rr))
            if rr_clean.lower() not in extracted.lower():
                extracted += " " + rr_clean + "GHz"

        if DEBUG:
            print(f"Original title: '{title}'")
            print(f"Extracted model: '{extracted}'")

        # Convert to Title Case, ensure "GHz" consistency
        extracted_title = extracted.title().replace("Ghz", "GHz")

        # If it's not a typical consumer CPU (i3/i5/i7/i9 or Ryzen 3/5/7/9), skip it
        if not is_consumer_cpu(extracted_title):
            if DEBUG:
                print(f"Skipping non-consumer CPU model: '{extracted_title}'")
                print("-------")
            return None
        return extracted_title
    else:
        if DEBUG:
            print(f"No CPU model extracted from '{title}'")
            print("-------")
        return None

def get_ebay_oauth_token():
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Exception("Please set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET environment variables.")
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    response = request_with_retry("POST", url, headers=headers, data=data)
    if response.status_code == 200:
        if DEBUG:
            print("Successfully retrieved OAuth token")
        return response.json()["access_token"]
    else:
        if DEBUG:
            print(f"Error retrieving token: {response.status_code} {response.text}")
        raise Exception(f"Error retrieving token: {response.status_code} {response.text}")

def format_time_ago(post_date_str):
    try:
        post_date = datetime.fromisoformat(post_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - post_date
        seconds = diff.total_seconds()
        if seconds < 60:
            return f"{int(seconds)} second(s) ago"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            return f"{minutes} minute(s) ago"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"{hours} hour(s) ago"
        else:
            days = int(seconds // 86400)
            return f"{days} day(s) ago"
    except Exception as e:
        if DEBUG:
            print(f"Error formatting time ago: {e}")
        return "N/A"

def get_fair_market_value(cpu_model, condition="Used"):
    """
    Uses 'limit': '5'. If fewer than 5 results come back, we append "(low sales data)".
    """
    token = get_ebay_oauth_token()
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    short_model = re.sub(
        r'^(amd\s+ryzen\s+|intel\s+core\s+|amd\s+|intel\s+pentium\s+|intel\s+celeron\s+)',
        '',
        cpu_model,
        flags=re.IGNORECASE
    ).strip()

    condition_map = {
        "New": "1000",
        "Open box": "1500",
        "Used": "3000",
        "For parts or not working": "7000"
    }
    condition_id = condition_map.get(condition, "3000")

    params = {
        "q": short_model,
        "category_ids": "164",
        "filter": f"conditionIds:{{{condition_id}}}",
        "limit": "5",
        "sort": "price"
    }
    try:
        response = request_with_retry("GET", url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            items = data.get("itemSummaries", [])
            prices = [
                float(it["price"]["value"])
                for it in items
                if "price" in it and float(it["price"]["value"]) > 0
            ]
            if DEBUG:
                print(f"Active listing prices for '{cpu_model}' (condition: {condition}): {prices}")
            if prices:
                fair_value = statistics.median(prices)
                low_sales_flag = len(prices) < 5
                if DEBUG:
                    print(
                        f"Median fair market value for '{cpu_model}' (condition: {condition}): "
                        f"${fair_value:.2f}{' (low sales data)' if low_sales_flag else ''}"
                    )
                    print("-------")
                return fair_value, low_sales_flag
            else:
                if DEBUG:
                    print(f"No active listing data for '{cpu_model}' (condition: {condition})")
                return None, False
        else:
            if DEBUG:
                print(f"Error fetching listings for '{short_model}': {response.status_code} {response.text}")
            return None, False
    except Exception as e:
        if DEBUG:
            print(f"Exception fetching prices for '{short_model}': {e}")
        return None, False

def get_ebay_listings(keyword="computer parts", limit=50, cache_expiry=14400):  # 4 hours in seconds
    global listing_cache
    now = datetime.now(timezone.utc)

    # Check if cache is valid and no new listings are expected
    if (listing_cache["listings"] and 
        listing_cache["timestamp"] and 
        (now - listing_cache["timestamp"]).total_seconds() < cache_expiry):
        # Check if any cached listing's itemCreationDate is within cache_expiry
        has_new_listings = False
        for listing in listing_cache["listings"]:
            try:
                creation_date_str = listing.get("itemCreationDate", "")
                if creation_date_str:
                    creation_date = datetime.fromisoformat(creation_date_str.replace("Z", "+00:00"))
                    if (now - creation_date).total_seconds() < cache_expiry:
                        has_new_listings = True
                        if DEBUG:
                            print(f"Found new listing in cache: {listing['title']} (created: {creation_date})")
                        break
            except Exception:
                continue
        if not has_new_listings:
            if DEBUG:
                print(f"Returning cached listings (last updated: {listing_cache['timestamp']})")
            sort_order = {"great": 0, "good": 1, "fair": 2}
            return sorted(listing_cache["listings"], key=lambda l: sort_order.get(l.get("deal_type", "fair"), 2))

    # Fetch new listings if cache is invalid, expired, or has new listings
    if DEBUG:
        print(f"Fetching new listings from eBay at {now}")
    token = get_ebay_oauth_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"category_ids": "164", "limit": limit, "sort": "newlyListed"}
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    response = request_with_retry("GET", url, headers=headers, params=params)

    listings = []
    if response.status_code == 200:
        data = response.json()
        items = data.get("itemSummaries", [])
        now = datetime.now(timezone.utc)

        for item in items:
            creation_date_str = item.get("itemCreationDate", "")
            if creation_date_str:
                try:
                    creation_date = datetime.fromisoformat(creation_date_str.replace("Z", "+00:00"))
                    if (now - creation_date).total_seconds() > cache_expiry:
                        continue
                    post_date = format_time_ago(creation_date_str)
                except Exception:
                    post_date = "N/A"
            else:
                post_date = "N/A"

            price_info = item.get("price", {})
            try:
                price = float(price_info.get("value", 0))
            except (ValueError, TypeError):
                price = 0.0

            listing_data = {
                "title": item.get("title", ""),
                "price": price,
                "shipping_cost": 0.00,
                "tax_estimate": 0.00,
                "net_profit": None,
                "condition": item.get("condition", "Not Specified"),  # Included for display
                "category": item.get("categoryPath", "Misc"),
                "listing_url": item.get("itemWebUrl", ""),
                "post_date": post_date,
                "cpu_model": None,
                "estimated_sale_price": None,
                "itemCreationDate": creation_date_str  # Store for cache checking
            }

            # If "cpu" or "processor" is in the listing, try extracting
            if "cpu" in listing_data["category"].lower() or "processor" in listing_data["title"].lower():
                lot_match = re.search(r'(?i)^lot\s+of\s+(\d+)', listing_data["title"])
                multiplier = int(lot_match.group(1)) if lot_match else 1

                extracted_model = extract_cpu_model(listing_data["title"])
                if extracted_model:
                    listing_data["cpu_model"] = extracted_model
                    cpu_value, low_sales_flag = get_fair_market_value(extracted_model, condition=listing_data["condition"])
                    if cpu_value is not None:
                        final_value = cpu_value * multiplier
                        if low_sales_flag:
                            listing_data["estimated_sale_price"] = f"{final_value:.2f} (low sales data)"
                        else:
                            listing_data["estimated_sale_price"] = f"{final_value:.2f}"
                        listing_data["net_profit"] = round(final_value - (listing_data["price"] + listing_data["shipping_cost"]), 2)
                        # Classify the deal type
                        if listing_data["net_profit"] < 10:
                            listing_data["deal_type"] = "fair"
                        elif listing_data["net_profit"] < 30:
                            listing_data["deal_type"] = "good"
                        else:
                            listing_data["deal_type"] = "great"
                        listings.append(listing_data)

        # Update cache with new listings if there are changes or cache is expired
        if listings or (listing_cache["timestamp"] is None or (now - listing_cache["timestamp"]).total_seconds() >= cache_expiry):
            listing_cache["listings"] = listings
            listing_cache["timestamp"] = now
            if DEBUG:
                print(f"Cache updated with {len(listings)} listings at {now}")
        else:
            if DEBUG:
                print("No new listings or cache not expired, retaining existing cache")
    else:
        if DEBUG:
            print(f"Error from Browse API: {response.status_code} {response.text}")
    
    # Instead of filtering out fair deals, return all cached listings sorted by deal type.
    sort_order = {"great": 0, "good": 1, "fair": 2}
    return sorted(listing_cache["listings"], key=lambda l: sort_order.get(l.get("deal_type", "fair"), 2))

if __name__ == "__main__":
    try:
        # No console output for listings here, as per your request
        listings = get_ebay_listings(keyword="computer parts", limit=5)
    except Exception as e:
        if DEBUG:
            print(f"Error: {e}")
