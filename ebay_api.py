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
        non_consumer_keywords = ["epyc", "core duo", "power mac"]
        if any(keyword in extracted_title.lower() for keyword in non_consumer_keywords):
            if DEBUG:
                print(f"Skipping non-consumer CPU model: '{extracted_title}'")
                print("-------")
            return None
        if not is_consumer_cpu(extracted_title) and "xeon" not in extracted_title.lower():
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

def scrape_terapeak_avg_price(query):
    """
    Attempts to scrape Terapeak (or Seller Hub) for the average sold price using requests.
    This is a fallback method.
    """
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.ebay.com/sh/research?marketplace=EBAY-US&keywords={encoded_query}&dayRange=30&categoryId=164&limit=50&tabName=SOLD&tz=America%2FNew_York"
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
    price_div = soup.find("div", class_="metric-value")
    if price_div:
        avg_price_str = price_div.get_text(strip=True).replace("$", "").replace(",", "")
        try:
            avg_price = float(avg_price_str)
            if DEBUG:
                print(f"Scraped Terapeak average price for '{query}': {avg_price}")
            return avg_price
        except Exception as e:
            if DEBUG:
                print(f"Error parsing scraped price: {e}")
            return None
    else:
        if DEBUG:
            print("Could not find average price element on Terapeak page")
        return None

def get_fair_market_value(cpu_model, condition="Used"):
    """
    Determines the fair market value for a CPU model.
    First, it removes the GHz portion from the CPU model to form a search query.
    It then attempts to scrape the Seller Hub research page via Playwright.
    If successful, the scraped value is cached and returned.
    Otherwise, it falls back to using the eBay API median price.
    """
    # Remove the GHz portion from the query for better search results.
    query_for_scrape = re.sub(r'\s*\d+\.\d+\s*GHz', '', cpu_model, flags=re.IGNORECASE).strip()

    if cpu_model in SCRAPED_PRICE_CACHE:
        if DEBUG:
            print(f"Using cached scraped price for {cpu_model}: {SCRAPED_PRICE_CACHE[cpu_model]}")
        return SCRAPED_PRICE_CACHE[cpu_model], False

    seller_hub_value = get_seller_hub_metric_value(query=query_for_scrape, headless=False)
    if seller_hub_value is not None:
        SCRAPED_PRICE_CACHE[cpu_model] = seller_hub_value
        if DEBUG:
            print(f"Using Playwright scraped value for {cpu_model}: {seller_hub_value}")
        return seller_hub_value, False

    # Fallback to eBay API method
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
        "itemCreationDate": creation_date_str
    }
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

if __name__ == "__main__":
    try:
        # For initial login, run with headless=False once:
        # metric = get_seller_hub_metric_value(query="Intel Core I5-7500T 2.7GHz", headless=False)
        # print(f"Metric value (manual login required): {metric}")
        
        listings = get_ebay_listings(keyword="computer parts", limit=20)
        for listing in listings:
            print(listing)
    except Exception as e:
        if DEBUG:
            print(f"Error: {e}")
