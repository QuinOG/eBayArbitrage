import os
import base64
import requests
import re
from datetime import datetime, timezone, timedelta
import time
import statistics
import concurrent.futures
from bs4 import BeautifulSoup
import urllib.parse

DEBUG = True

# OAuth token cache (for eBay API)
TOKEN_CACHE = {
    "token": None,
    "expires_at": None  # datetime when the token expires
}

# Example cookies for Terapeak (replace these values with your actual session cookies)
TERAPEAK_COOKIES = {
    "ebaysid":"BAQAAAZRXz2gmAAaAA/oDQWuKJfxleUpyWlhraU9pSnphWFJsTG1saFppNXphV2R1WVhSMWNtVXVhMlY1Y0dGcGNpSXNJblpsY2lJNk1UTXNJbUZzWnlJNklsSlROVEV5SW4wLmV5SnBjM01pT2lKSlFVWlRUMEZKUkVWT1ZDSXNJbk4xWWlJNkltODBlRU5FU1V0QlVYQlRJaXdpWlhod0lqb3hOelF4TVRRME56QTBMQ0p1WW1ZaU9qRTNOREV4TkRNNE1EUXNJbWxoZENJNk1UYzBNVEUwTXpnd05Dd2lhblJwSWpvaVpqWXdZMlJsWlRrdE9XTmxaaTAwWVRNekxUZzRObU10TVRFMU5HTmpOV1JsT0dZNElpd2ljMlZ6YzJsdmJsUnZhMlZ1VW1WbVpYSmxibU5sSWpvaWRsNHhMakVqYVY0eEkyWmVNQ053WGpNalNWNHpJM0plTVNOMFhsVnNOSGhOUmpoM1QydFZNazVFUVRCTmFtc3hVbFJCTTA5VVVrZE9hMUpHVGtWWk1FNTZWa05TYWxGNFRsUldSMDR3V2tOWWVrWm1UVk5PUmxocVNUSk5RVDA5SWl3aWMyVnpjMmx2Ymtsa0lqb2lZV0UyWm1KbU56Y3hPVFF3WVRZeVlqRTJZVEpsTkdRMVptWm1aamcxT1RVaWZRLnBGaF9ER3RudXFlZllTWDdhNlg3RzVFUU1jbWRXb0daejhpS204TXV2VlhTWFotV3FjZUdJbGZ2R3NoUFNXTVhFUnBaWUhyY3NBMHVqMGh1dU9Sc3J5NUVOMVc1SktOODViaVhHYV85d3hYc2pNMkFrdHBiQzlKd0toUFA4UGlJbW9nMzNlRFBBYkV0OVdBZmYyeGJIR1ZVNVhoRFRTeEJNTzVNNG5DMVZRbFlhSk1sQjRTaWVZbEFWNEhnSHZfZlJ1SW9jVzI0RHpiY3ZMLWJCWkdwa1YycUFsbkZYUGVscnBnSTNYUlE1U0s5SVBJQlBNaEtQd2ZER0lqS01nUlhxc005SmJXbUJGaDktVndKTzJWTE5RMEp4VlUtOWFKcTA2Zmk3TENCRWlDeVFWeGx3U3BYMTRfY2YtUDNKQ0w5Qms2b243SF95OUhLOXpCZzhKd0xhdwttLPtpr49oF7pkFrFwrMgwDs8l",
    "ebay": "%5Ejs%3D1%5EsfLMD%3D0%5Esin%3Din%5Esbf%3D%2300000004%5E",
    "nonsession": "BAQAAAZRXz2gmAAaAAAQADGmg0Z9xdWlubGFkYXZpLTAAEAAMaajyuXF1aW5sYWRhdmktMAAzAA5pqPK5MzI2MDUtMTc2NSxVU0EAQAAMaajyuXF1aW5sYWRhdmktMACcADhpqPK5blkrc0haMlByQm1kajZ3Vm5ZK3NFWjJQckEyZGo2QUFsWU9pQUphQXBBcWRqNng5blkrc2VRPT0AnQAIaajyuTAwMDAwMDAxAMoAIGuKJjlhYTZmYmY3NzE5NDBhNjJiMTZhMmU0ZDVmZmZmODU5NQDLAAJnx8ZBNjkBZAAHa4omOSMwMTAwOGGijwcMRrex2TcP4l+8oWZzONKYpg**", 
    "ns1": "BAQAAAZRXz2gmAAaAAKUADWmo8rkxNDUxMzg2MjU2LzA7ANgAU2mo8rljNjl8NjAxXjE3MzgwMjYyODk2NjBeXjFeM3wyfDV8NHw3fDEwfDQyfDQzfDExXl5eNF4zXjEyXjEyXjJeMV4xXjBeMV4wXjFeNjQ0MjQ1OTA3NTC33ZRZ0IqN8S5jlIDEY2GUyjwZ", 
    "s": "BAQAAAZRXz2gmAAWAAPgAIGfJB2xhYTZmYmY3NzE5NDBhNjJiMTZhMmU0ZDVmZmZmODU5NQFFAAhpqPK5NjFhYjg2MTCD2VJVRlugI+HZhGPCuRYKkUAQNw**", 
    "shs": "BAQAAAZRXz2gmAAaAAVUAD2mg0Z8yMjQxMTAwMjA0MDA4LDLZGH5LLafa1nObzCkey+/hiv4Aqg**", 
    "totp": "1741144178350.mUYnQ8huxvJt9xAqFnnCMiOEluQVQtulIbksEt75jCQGw4KeHEjyyXAuRZVBQpMJ7bnnLSr6eORw9/EzDkZEdg==.kLqPiCS1qjMqrh3Znw1tFAVbxYJB2mI0aSk1pYrn46I", 
    # plus anything else you see from the same domain
}

# Precompile regular expressions for performance
RE_INTEL_CORE = re.compile(r'(intel\s+(?:core\s+)?i\d[- ]*\d{3,5}[a-z0-9]*)\b', re.IGNORECASE)
RE_AMD_RYZEN = re.compile(r'((?:amd\s+)?ryzen\s+\d+\s+\d{3,5}[a-z0-9]*)\b', re.IGNORECASE)
RE_AMD_ATHLON = re.compile(r'(amd\s+(?:athlon\s+(?:64\s+)?)?[a-z0-9-]*\d+[a-z0-9-]*)\b', re.IGNORECASE)
RE_INTEL_XEON_ALT = re.compile(r'(intel\s+xeon\s+e\d{1,4}[-\s]*\d{1,4}(?:\s*v\d+)?(?:\s*\d+M\s*cache)?)', re.IGNORECASE)
RE_INTEL_XEON_FALLBACK = re.compile(r'(intel\s+xeon\s+w[-\s]?\d{3,5}[a-z0-9-]*(?:\s+\d+-core)?)\b', re.IGNORECASE)
RE_INTEL_CORE2 = re.compile(r'(intel\s+core\s+2\s+duo\s+[a-z]\d{4,5})\b', re.IGNORECASE)
RE_AMD_RYZEN_PRO = re.compile(r'((?:amd\s+)?ryzen\s+(?:pro\s+)?\d+\s+\d{3,5}[a-z0-9]*)\b', re.IGNORECASE)
RE_LOT = re.compile(r'(?:lot\s+of\s+\d+\s+assorted\s+)?(?:intel\s+(?:pentium|celeron|core\s+2)|amd\s+(?:athlon))\b', re.IGNORECASE)
RE_REFRESH_RATE = re.compile(r'(\d+\.\d+)\s*ghz', re.IGNORECASE)


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


def scrape_terapeak_avg_price(query, cookies=TERAPEAK_COOKIES):
    """
    Scrapes Terapeak for the average sold price for the given query.
    Note: Adjust the URL and parsing based on the actual Terapeak page structure.
    
    :param query: The CPU model query string.
    :param cookies: A dictionary of session cookies for Terapeak.
    :return: A float representing the average sold price, or None if not found.
    """
    encoded_query = urllib.parse.quote(query)
    # Example URL – adjust parameters as needed.
    url = f"https://www.ebay.com/sh/research?marketplace=EBAY-US&keywords={encoded_query}&dayRange=30&categoryId=164&limit=50&tabName=SOLD&tz=America%2FNew_York"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        )
    }
    
    response = requests.get(url, headers=headers, cookies=cookies)
    
    if response.status_code != 200:
        if DEBUG:
            print(f"Scrape failed: HTTP {response.status_code}")
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Adjust the selector based on the actual HTML snippet. For example:
    price_div = soup.find("div", class_="metric-value")
    if price_div:
        avg_price_str = price_div.get_text(strip=True)
        # Remove currency symbols and commas
        avg_price_str = avg_price_str.replace("$", "").replace(",", "")
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
    Attempts to determine the fair market value for the given CPU model.
    First, it tries to scrape Terapeak for the average sold price.
    If that fails, it falls back to the eBay API method.
    """
    # First attempt: scrape Terapeak
    scraped_value = scrape_terapeak_avg_price(cpu_model)
    if scraped_value is not None:
        # Assume sufficient sales data if scraping works
        return scraped_value, False
    
    # Fallback: use eBay API
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
    Always fetches fresh listings from eBay.
    Uses parallel processing for listings and prints the time taken to reload.
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
        listings = get_ebay_listings(keyword="computer parts", limit=20)
    except Exception as e:
        if DEBUG:
            print(f"Error: {e}")
