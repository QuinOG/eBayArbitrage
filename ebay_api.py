import os
import base64
import requests
import re
from datetime import datetime, timezone, timedelta
import time
import statistics
import concurrent.futures
import urllib.parse
from bs4 import BeautifulSoup

# --- Playwright Imports ---
from playwright.sync_api import sync_playwright

DEBUG = True

# OAuth token cache for eBay API
TOKEN_CACHE = {
    "token": None,
    "expires_at": None  # datetime when the token expires
}

# Directory for persistent Playwright profile
USER_DATA_DIR = "C:/temp/playwright-profile"
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)

# Cache for scraped prices by CPU model
SCRAPED_PRICE_CACHE = {}

# Precompiled regex patterns for CPU model extraction
RE_INTEL_CORE = re.compile(r'(intel\s+(?:core\s+)?i\d[- ]*\d{3,5}[a-z0-9]*)\b', re.IGNORECASE)
RE_AMD_RYZEN = re.compile(r'((?:amd\s+)?ryzen\s+\d+\s+\d{3,5}[a-z0-9]*)\b', re.IGNORECASE)
RE_AMD_ATHLON = re.compile(r'(amd\s+(?:athlon\s+(?:64\s+)?)?[a-z0-9-]*\d+[a-z0-9-]*)\b', re.IGNORECASE)
RE_INTEL_XEON_ALT = re.compile(r'(intel\s+xeon\s+e\d{1,4}[-\s]*\d{1,4}(?:\s*v\d+)?(?:\s*\d+M\s*cache)?)', re.IGNORECASE)
RE_INTEL_XEON_FALLBACK = re.compile(r'(intel\s+xeon\s+w[-\s]?\d{3,5}[a-z0-9-]*(?:\s+\d+-core)?)\b', re.IGNORECASE)
RE_INTEL_CORE2 = re.compile(r'(intel\s+core\s+2\s+duo\s+[a-z]\d{4,5})\b', re.IGNORECASE)
RE_AMD_RYZEN_PRO = re.compile(r'((?:amd\s+)?ryzen\s+(?:pro\s+)?\d+\s+\d{3,5}[a-z0-9]*)\b', re.IGNORECASE)
RE_LOT = re.compile(r'(?:lot\s+of\s+\d+\s+assorted\s+)?(?:intel\s+(?:pentium|celeron|core\s+2)|amd\s+(?:athlon))\b', re.IGNORECASE)
RE_REFRESH_RATE = re.compile(r'(\d+\.\d+)\s*ghz', re.IGNORECASE)

# ---------------------------
# Helper Functions
# ---------------------------

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

def get_seller_hub_metric_value(query="Intel Core I5-7500T 2.7GHz", headless=False, day_range=30, category_id=164, limit=50, tz="America/New_York"):
    """
    Uses Playwright with a persistent profile to load the Seller Hub research page
    and scrape the average sold price from an element with class 'metric-value'.
    For the first run, set headless=False to log in manually.
    Retries up to 3 times if the context or page crashes.
    """
    base_url = "https://www.ebay.com/sh/research"
    url = (
        f"{base_url}?marketplace=EBAY-US"
        f"&keywords={query.replace(' ', '+')}"
        f"&dayRange={day_range}"
        f"&categoryId={category_id}"
        f"&limit={limit}"
        f"&tabName=SOLD"
        f"&tz={urllib.parse.quote(tz)}"
    )
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(USER_DATA_DIR, headless=headless)
                page = context.new_page()
                page.goto(url)
                page.wait_for_selector("div.metric-value", timeout=40000)
                text_val = page.inner_text("div.metric-value").strip()
                text_val = re.sub(r"[^\d.]+", "", text_val)
                if text_val:
                    metric_value = float(text_val)
                    if DEBUG:
                        print(f"Scraped metric value from Seller Hub: {metric_value}")
                else:
                    print("No numeric value found in metric-value element.")
                    metric_value = None
                try:
                    context.close()
                except Exception as close_error:
                    if DEBUG:
                        print(f"Error closing context (ignored): {close_error}")
                return metric_value
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                print(f"Attempt {attempt+1} failed due to context closed error: {e}")
                time.sleep(2)
                continue
            else:
                print(f"Error in Playwright scraping: {e}")
                return None
    return None

def is_consumer_cpu(model_str):
    pattern = r'^(?:intel\s+core\s+i[3579]|amd\s+ryzen\s+[3579])'
    return bool(re.search(pattern, model_str.lower()))

def extract_cpu_model(title):
    title_clean = re.sub(r'[®™]', '', title)
    title_lower = re.sub(r'\s+', ' ', title_clean.lower()).strip()
    extracted = None

    intel_match = RE_INTEL_CORE.search(title_lower)
    if intel_match:
        extracted = intel_match.group(0).strip()
    if not extracted:
        amd_ryzen_match = RE_AMD_RYZEN.search(title_lower)
        if amd_ryzen_match:
            extracted = amd_ryzen_match.group(0).strip()
    if not extracted:
        amd_athlon_match = RE_AMD_ATHLON.search(title_lower)
        if amd_athlon_match:
            extracted = amd_athlon_match.group(0).strip()
    if not extracted:
        intel_xeon_alt_match = RE_INTEL_XEON_ALT.search(title_lower)
        if intel_xeon_alt_match:
            extracted = intel_xeon_alt_match.group(1).strip()
    if not extracted:
        intel_xeon_match = RE_INTEL_XEON_FALLBACK.search(title_lower)
        if intel_xeon_match:
            extracted = intel_xeon_match.group(1).strip()
    if not extracted:
        intel_core2_match = RE_INTEL_CORE2.search(title_lower)
        if intel_core2_match:
            extracted = intel_core2_match.group(1).strip()
    if not extracted:
        amd_ryzen_pro_match = RE_AMD_RYZEN_PRO.search(title_lower)
        if amd_ryzen_pro_match:
            extracted = amd_ryzen_pro_match.group(0).strip()
    if not extracted:
        lot_match = RE_LOT.search(title_lower)
        if lot_match:
            extracted = lot_match.group(0).strip()
    
    if extracted:
        refresh_rate_match = RE_REFRESH_RATE.search(title_lower)
        if refresh_rate_match:
            rr = refresh_rate_match.group(1).strip()
            rr_clean = str(float(rr))
            if rr_clean.lower() not in extracted.lower():
                extracted += " " + rr_clean + "GHz"
        if DEBUG:
            print(f"Original title: '{title}'")
            print(f"Extracted model: '{extracted}'")
        extracted_title = extracted.title().replace("Ghz", "GHz")
        # Skip non-consumer keywords
        non_consumer_keywords = ["epyc", "core duo", "power mac"]
        if any(keyword in extracted_title.lower() for keyword in non_consumer_keywords):
            if DEBUG:
                print(f"Skipping non-consumer CPU model: '{extracted_title}'")
                print("-------")
            return None
        # Completely skip Xeon processors
        if "xeon" in extracted_title.lower():
            if DEBUG:
                print(f"Skipping Xeon processor: '{extracted_title}'")
                print("-------")
            return None
        # Also skip if not consumer (though Xeon is already skipped)
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
    now = datetime.now(timezone.utc)
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expires_at"] and now < TOKEN_CACHE["expires_at"]:
        if DEBUG:
            print("Using cached OAuth token")
        return TOKEN_CACHE["token"]
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
        token = response.json()["access_token"]
        expires_in = int(response.json().get("expires_in", 7200))
        TOKEN_CACHE["token"] = token
        TOKEN_CACHE["expires_at"] = now + timedelta(seconds=expires_in)
        if DEBUG:
            print("Successfully retrieved OAuth token")
        return token
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

def scrape_terapeak_recent_median(query, num_sales=5):
    """
    Scrapes the Terapeak (Seller Hub) results table for the num_sales most recent sales
    of query, returning the median price. Falls back to the aggregated metric-value
    if not enough rows are found.
    """
    encoded_query = requests.utils.quote(query)
    url = (
        "https://www.ebay.com/sh/research"
        f"?marketplace=EBAY-US&keywords={encoded_query}&dayRange=30"
        "&categoryId=164&limit=50&tabName=SOLD&tz=America%2FNew_York"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        if DEBUG:
            print(f"Scrape failed: HTTP {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Find the main table
    table = soup.find("table", class_="terapeak-table content static-table table-content-default")
    if not table:
        if DEBUG:
            print("Could not locate the Terapeak table. Falling back to aggregated metric.")
        return fallback_metric_value(soup)

    tbody = table.find("tbody")
    if not tbody:
        if DEBUG:
            print("No <tbody> found in Terapeak table. Falling back to aggregated metric.")
        return fallback_metric_value(soup)

    # Each sold listing is a <tr> with class "research-table-row_item research-table-row_item-subtitle"
    rows = tbody.find_all("tr", class_="research-table-row_item research-table-row_item-subtitle")
    if not rows:
        if DEBUG:
            print("No matching <tr> rows found. Falling back to aggregated metric.")
        return fallback_metric_value(soup)

    listings = []
    for row in rows:
        cells = row.find_all("td")
        # Typically, we expect columns like:
        # 0: Price (e.g. "$57.65/fixed price")
        # 1: Shipping
        # 2: ...
        # 3: ...
        # 4: Date last sold
        if len(cells) < 5:
            continue

        # 1) Parse price from the first cell
        price_str = cells[0].get_text(strip=True)
        # e.g. "$57.65/fixed price" => split by '/' to drop "fixed price"
        price_str = price_str.split("/")[0].strip()
        price_str = price_str.replace("$", "").replace(",", "")
        try:
            price_val = float(price_str)
        except ValueError:
            if DEBUG:
                print(f"Skipping row with invalid price: {price_str}")
            continue

        # 2) Parse date from the 5th cell
        date_str = cells[4].get_text(strip=True)
        date_obj = parse_terapeak_date(date_str)  # We'll define parse_terapeak_date below
        if not date_obj:
            if DEBUG:
                print(f"Skipping row with unparseable date: {date_str}")
            continue

        listings.append((date_obj, price_val))

    if not listings:
        if DEBUG:
            print("No valid listings after parsing. Falling back to aggregated metric.")
        return fallback_metric_value(soup)

    # Sort by date descending (newest first)
    listings.sort(key=lambda x: x[0], reverse=True)
    # Take the top num_sales (e.g. 5)
    top_n = listings[:num_sales]
    prices = [p for (_, p) in top_n]

    # If you end up with fewer than 2 data points, you can decide how to handle that
    if len(prices) < 2:
        if DEBUG:
            print("Not enough recent listings for a median. Falling back to aggregated metric.")
        return fallback_metric_value(soup)

    # Compute median of these top N
    median_price = statistics.median(prices)
    if DEBUG:
        print(f"Median of the {len(top_n)} most recent sales for '{query}': {median_price}")
    return median_price

def parse_terapeak_date(date_str):
    """
    Example date parser. Adjust to the exact format used by your table's date cell.
    For instance, if it's '3/1/2025' or '03/01/2025', we can do this:
    """
    # Remove any text like "Sold on" or "Fixed Price" etc.
    # Just keep digits and slashes:
    cleaned = re.sub(r"[^0-9/]", "", date_str)
    try:
        # Attempt MM/DD/YYYY
        return datetime.strptime(cleaned, "%m/%d/%Y")
    except ValueError:
        return None

def fallback_metric_value(soup):
    """
    Attempts to parse the aggregated metric-value on the page
    if the row-level approach fails.
    """
    metric_div = soup.find("div", class_="metric-value")
    if metric_div:
        raw = metric_div.get_text(strip=True).replace("$", "").replace(",", "")
        try:
            val = float(raw)
            if DEBUG:
                print(f"Using fallback aggregated metric: {val}")
            return val
        except ValueError:
            if DEBUG:
                print(f"Error parsing fallback metric-value: {raw}")
            return None
    else:
        if DEBUG:
            print("No aggregated metric-value found.")
        return None

def get_fair_market_value(cpu_model, condition="Used"):
    """
    Determines the fair market value for a CPU model.
    Returns a tuple: (price, low_sales_flag, pricing_source)
    """
    # Remove the GHz portion from the query for better search results.
    query_for_scrape = re.sub(r'\s*\d+\.\d+\s*GHz', '', cpu_model, flags=re.IGNORECASE).strip()

    # Check cache (now storing a tuple: (price, low_sales_flag, pricing_source))
    if cpu_model in SCRAPED_PRICE_CACHE:
        cached_value, cached_flag, cached_source = SCRAPED_PRICE_CACHE[cpu_model]
        if DEBUG:
            print(f"Using cached scraped price for {cpu_model}: {cached_value}")
        return cached_value, cached_flag, cached_source

    # First, try the Seller Hub scraping (Terapeak / Sold Listings)
    seller_hub_value = get_seller_hub_metric_value(query=query_for_scrape, headless=False)
    if seller_hub_value is not None:
        SCRAPED_PRICE_CACHE[cpu_model] = (seller_hub_value, False, "(Sold Listings)")
        if DEBUG:
            print(f"Using Playwright scraped value for {cpu_model}: {seller_hub_value}")
        return seller_hub_value, False, "(Sold Listings)"

    # Fallback to eBay API method (Active Listings)
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
            prices = [float(it["price"]["value"]) for it in items if "price" in it and float(it["price"]["value"]) > 0]
            if DEBUG:
                print(f"Active listing prices for '{cpu_model}' (condition: {condition}): {prices}")
            if prices:
                fair_value = statistics.median(prices)
                low_sales_flag = len(prices) < 5
                if DEBUG:
                    print(f"Median fair market value for '{cpu_model}' (condition: {condition}): ${fair_value:.2f}{' (low sales data)' if low_sales_flag else ''}")
                    print("-------")
                return fair_value, low_sales_flag, "(Active Listings)"
            else:
                if DEBUG:
                    print(f"No active listing data for '{cpu_model}' (condition: {condition})")
                return None, False, None
        else:
            if DEBUG:
                print(f"Error fetching listings for '{short_model}': {response.status_code} {response.text}")
            return None, False, None
    except Exception as e:
        if DEBUG:
            print(f"Exception fetching prices for '{short_model}': {e}")
        return None, False, None

def process_listing(item, cache_expiry, now):
    creation_date_str = item.get("itemCreationDate", "")
    if creation_date_str:
        try:
            creation_date = datetime.fromisoformat(creation_date_str.replace("Z", "+00:00"))
            if (now - creation_date).total_seconds() > cache_expiry:
                return None
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
        "condition": item.get("condition", "Not Specified"),
        "category": item.get("categoryPath", "Misc"),
        "listing_url": item.get("itemWebUrl", ""),
        "post_date": post_date,
        "cpu_model": None,
        "estimated_sale_price": None,
        "estimated_sale_source": None,  # New field for pricing source
        "itemCreationDate": creation_date_str
    }
    if "cpu" in listing_data["category"].lower() or "processor" in listing_data["title"].lower():
        lot_match = re.search(r'(?i)^lot\s+of\s+(\d+)', listing_data["title"])
        multiplier = int(lot_match.group(1)) if lot_match else 1
        extracted_model = extract_cpu_model(listing_data["title"])
        if extracted_model:
            listing_data["cpu_model"] = extracted_model
            # Unpack the new tuple with pricing source
            cpu_value, low_sales_flag, pricing_source = get_fair_market_value(extracted_model, condition=listing_data["condition"])
            if cpu_value is not None:
                final_value = cpu_value * multiplier
                price_str = f"{final_value:.2f}"
                if low_sales_flag:
                    price_str += " (low sales data)"
                listing_data["estimated_sale_price"] = price_str
                listing_data["estimated_sale_source"] = pricing_source
                listing_data["net_profit"] = round(final_value - (listing_data["price"] + listing_data["shipping_cost"]), 2)
                if listing_data["net_profit"] < 10:
                    listing_data["deal_type"] = "fair"
                elif listing_data["net_profit"] < 30:
                    listing_data["deal_type"] = "good"
                else:
                    listing_data["deal_type"] = "great"
                return listing_data
    return None

def get_ebay_listings(keyword="computer parts", limit=20, cache_expiry=14400):
    """
    Fetches fresh listings from the eBay Browse API.
    Processes listings concurrently and returns them sorted by deal type.
    """
    start_time = time.perf_counter()
    now = datetime.now(timezone.utc)
    token = get_ebay_oauth_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"category_ids": "164", "limit": limit, "sort": "newlyListed"}
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    response = request_with_retry("GET", url, headers=headers, params=params)
    listings = []
    if response.status_code == 200:
        data = response.json()
        items = data.get("itemSummaries", [])
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(executor.map(lambda item: process_listing(item, cache_expiry, now), items))
        listings = [r for r in results if r is not None]
    else:
        if DEBUG:
            print(f"Error from Browse API: {response.status_code} {response.text}")
    elapsed = time.perf_counter() - start_time
    if DEBUG:
        print(f"get_ebay_listings completed in {elapsed:.2f} seconds")
    sort_order = {"great": 0, "good": 1, "fair": 2}
    return sorted(listings, key=lambda l: sort_order.get(l.get("deal_type", "fair"), 2))

# ----------------------------------------------------------
# New helper function to scrape multiple queries concurrently
# ----------------------------------------------------------
def get_seller_hub_metric_values(queries, headless=False, day_range=30, category_id=164, limit=50, tz="America/New_York"):
    """
    Takes a list of queries and scrapes the Seller Hub metric value for each one
    in parallel using ThreadPoolExecutor. Returns a dict of {query: metric_value}.
    """
    results = {}

    def scrape_one(q):
        return (q, get_seller_hub_metric_value(query=q, headless=headless, day_range=day_range, category_id=category_id, limit=limit, tz=tz))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_query = {executor.submit(scrape_one, q): q for q in queries}
        for future in concurrent.futures.as_completed(future_to_query):
            query_str = future_to_query[future]
            try:
                q, metric = future.result()
                results[q] = metric
            except Exception as e:
                if DEBUG:
                    print(f"Error scraping query '{query_str}': {e}")
                results[query_str] = None

    return results

# ----------------------------------------------------------
# Main execution
# ----------------------------------------------------------
if __name__ == "__main__":
    try:
        # Example: scrape 3 queries concurrently via Seller Hub
        queries_to_scrape = [
            "Intel Core i5-7500T 2.7GHz",
            "AMD Ryzen 5 3600",
            "Intel Core i7-8700K"
        ]

        # IMPORTANT: For your very first run, use headless=False so you can log in manually.
        metrics = get_seller_hub_metric_values(queries_to_scrape, headless=False)
        print("Scraped Seller Hub metric values:")
        for query_str, value in metrics.items():
            print(f"  {query_str} => {value}")

        # Additionally, you can continue with your eBay listings scraping:
        listings = get_ebay_listings(keyword="computer parts", limit=20)
        for listing in listings:
            print(listing)
    except Exception as e:
        if DEBUG:
            print(f"Error: {e}")