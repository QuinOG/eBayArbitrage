"""
Talks to eBay's official APIs. No scraping.

- get_ebay_oauth_token(): app token from EBAY_CLIENT_ID / EBAY_CLIENT_SECRET (set in .env)
- search_listings(category_id): newest listings in a category, from the Browse API
- get_details(item_id): one listing's item specifics and description, cached in data/details_cache.json
"""

import base64
import html
import json
import os
import re
import threading
import time
from datetime import datetime, timezone, timedelta

import requests

import config

DEBUG = True
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

# eBay condition IDs: new, open box, refurbished grades, used. Leaves out 7000 "For parts or not working".
CONDITION_IDS = "1000|1500|2000|2010|2020|2030|2500|3000"

TOKEN_CACHE = {"token": None, "expires_at": None}


def request_with_retry(method, url, max_attempts=3, delay=3, **kwargs):
    """Make an HTTP request, retrying on errors and 503 responses."""
    response = None
    for attempt in range(max_attempts):
        try:
            response = requests.request(method, url, timeout=20, **kwargs)
            if response.status_code != 503:
                return response
            if DEBUG:
                print(f"Attempt {attempt + 1}: got 503 from {url}, retrying in {delay}s")
        except requests.RequestException as e:
            if DEBUG:
                print(f"Attempt {attempt + 1}: {e}, retrying in {delay}s")
        time.sleep(delay)
        delay *= 2
    if response is None:
        raise Exception(f"No response from {url} after {max_attempts} attempts")
    return response


def get_ebay_oauth_token():
    now = datetime.now(timezone.utc)
    if TOKEN_CACHE["token"] and now < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["token"]
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Exception("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are missing. Add them to your .env file.")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = request_with_retry(
        "POST", TOKEN_URL,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
    )
    if response.status_code == 401:
        raise Exception(
            "eBay rejected the keys (401). In .env, EBAY_CLIENT_ID must be the Production App ID "
            "(looks like Name-AppName-PRD-xxxxxxxx-xxxxxxxx), not the Dev ID, and EBAY_CLIENT_SECRET "
            "must be the Cert ID (starts with PRD-). If both are right, check that your Production "
            "keyset is enabled at https://developer.ebay.com/my/keys.")
    if response.status_code != 200:
        raise Exception(f"Error getting eBay token: {response.status_code} {response.text}")
    body = response.json()
    TOKEN_CACHE["token"] = body["access_token"]
    # Refresh a minute early so a token never expires mid-request.
    TOKEN_CACHE["expires_at"] = now + timedelta(seconds=int(body.get("expires_in", 7200)) - 60)
    return TOKEN_CACHE["token"]


def api_headers():
    headers = {
        "Authorization": f"Bearer {get_ebay_oauth_token()}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    if config.BUYER_ZIP:
        # Lets eBay calculate real shipping costs to you.
        headers["X-EBAY-C-ENDUSERCTX"] = f"contextualLocation=country%3DUS%2Czip%3D{config.BUYER_ZIP}"
    return headers


def format_time_ago(created):
    seconds = (datetime.now(timezone.utc) - created).total_seconds()
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hr ago"
    return f"{int(seconds // 86400)} days ago"


def get_shipping(item):
    """Cheapest shipping option, or None if eBay didn't give a cost."""
    costs = []
    for option in item.get("shippingOptions", []):
        cost = option.get("shippingCost", {}).get("value")
        if cost is not None:
            costs.append(float(cost))
    return min(costs) if costs else None


def parse_item(item):
    created_str = item.get("itemCreationDate", "")
    created = datetime.fromisoformat(created_str.replace("Z", "+00:00")) if created_str else None
    item_id = item.get("legacyItemId") or (item.get("itemId", "").split("|") + ["", ""])[1]
    return {
        "item_id": item_id,
        "title": item.get("title", ""),
        "price": float(item.get("price", {}).get("value", 0)),
        "shipping": get_shipping(item),
        "condition": item.get("condition", "Not specified"),
        "listing_url": item.get("itemWebUrl", ""),
        "created": created_str,
        "created_dt": created,
        "post_date": format_time_ago(created) if created else "N/A",
    }


def get_item(link_or_number):
    """
    One listing, from an eBay link (https://www.ebay.com/itm/123456789012) or a bare item number.
    Uses the Browse API getItemByLegacyId call.
    """
    m = re.search(r"/itm/(?:[^/?#]+/)?(\d{9,15})", link_or_number) or re.fullmatch(r"\s*(\d{9,15})\s*", link_or_number)
    if not m:
        raise ValueError("That doesn't look like an eBay listing link or item number.")
    response = request_with_retry("GET", ITEM_URL, headers=api_headers(), params={"legacy_item_id": m[1]})
    if response.status_code == 404:
        raise ValueError("eBay couldn't find that listing. It may have ended.")
    if response.status_code != 200:
        errors = response.json().get("errors", []) if response.text.startswith("{") else []
        if any(e.get("errorId") == 11006 for e in errors):
            raise ValueError("That listing has several variations (options). Enter its title and price by hand instead.")
        raise Exception(f"Browse API error {response.status_code}: {response.text[:300]}")
    item = response.json()
    listing = parse_item(item)
    listing.pop("created_dt")
    listing["specifics"] = specifics_lines(item.get("localizedAspects", []))
    listing["description"] = html_to_lines(item.get("description") or item.get("shortDescription") or "")
    return listing


# Item specifics and descriptions fetched during scans, by item number. A listing's description rarely
# changes, so each one costs 1 API call the first time it's scanned and nothing on later refreshes.
# The cache is saved to data/details_cache.json, so restarting app.py doesn't fetch everything again.
DETAILS_CACHE_HOURS = 12
DETAILS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "details_cache.json")


def fresh(entries):
    """Only the cache entries younger than DETAILS_CACHE_HOURS."""
    cutoff = time.time() - DETAILS_CACHE_HOURS * 3600
    return {k: v for k, v in entries.items() if v[0] > cutoff}


def load_details_cache():
    try:
        with open(DETAILS_CACHE_FILE, encoding="utf-8") as f:
            return fresh(json.load(f))
    except (OSError, ValueError):  # no file yet, or a broken one
        return {}


DETAILS_CACHE = load_details_cache()
DETAILS_LOCK = threading.Lock()  # scans fetch details from several threads at once


def save_details_cache():
    """Write the cache to disk. scan_all() calls this after each scan."""
    with DETAILS_LOCK:
        entries = fresh(DETAILS_CACHE)
    try:
        with open(DETAILS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f)
    except OSError as e:
        if DEBUG:
            print(f"Couldn't save {DETAILS_CACHE_FILE}: {e}")


def get_details(item_id):
    """{"specifics": [...], "description": [...]} for one listing, cached. Empty lists if it can't be loaded."""
    cached = DETAILS_CACHE.get(item_id)
    if cached and time.time() - cached[0] < DETAILS_CACHE_HOURS * 3600:
        return cached[1]
    try:
        item = get_item(item_id)
        details = {"specifics": item["specifics"], "description": item["description"]}
    except Exception as e:
        if DEBUG:
            print(f"Couldn't load details for {item_id}: {e}")
        return {"specifics": [], "description": []}  # not cached, so the next scan tries again
    with DETAILS_LOCK:
        DETAILS_CACHE[item_id] = (time.time(), details)
    return details


def specifics_lines(aspects):
    """Item specifics as "Name: value" lines, plus a few combined lines the part finders can read."""
    values = {a.get("name", ""): a.get("value", "") for a in aspects}
    lines = [f"{name}: {value}" for name, value in values.items()]
    # "Motherboard Brand: MSI" + "Model: H410M-A PRO" -> "MSI H410M-A PRO"
    brand, model = values.get("Motherboard Brand", ""), values.get("Model", "")
    if brand and model:
        lines.insert(0, model if brand.lower() in model.lower() else f"{brand} {model}")
    # Desktops: "RAM Size: 16 GB" + "Memory Type: DDR4" -> "16 GB DDR4"
    if values.get("RAM Size") and values.get("Memory Type"):
        lines.insert(0, f"{values['RAM Size']} {values['Memory Type']}")
    return lines


def html_to_lines(html_text):
    """The listing description as plain text lines."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|td)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return [line for line in lines if line][:300]


# Search results, by category, for SEARCH_CACHE_SECONDS. Refreshing the page a few times in a row
# reuses them instead of spending 1 API call per search each time.
SEARCH_CACHE = {}
SEARCH_CACHE_SECONDS = 90


def search_listings(category_id):
    """Newest fixed-price listings in one category, no older than config.MAX_LISTING_AGE_HOURS."""
    cached = SEARCH_CACHE.get(category_id)
    if cached and time.time() - cached[0] < SEARCH_CACHE_SECONDS:
        return [dict(l) for l in cached[1]]
    filters = [
        "buyingOptions:{FIXED_PRICE}",   # auctions show the current bid, not the final price
        f"conditionIds:{{{CONDITION_IDS}}}",
        f"itemLocationCountry:{config.ITEM_LOCATION_COUNTRY}",
    ]
    params = {
        "category_ids": category_id,
        "filter": ",".join(filters),
        "sort": "newlyListed",
        "limit": config.LISTINGS_PER_SEARCH,
    }
    response = request_with_retry("GET", BROWSE_URL, headers=api_headers(), params=params)
    if response.status_code != 200:
        raise Exception(f"Browse API error {response.status_code}: {response.text[:300]}")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_LISTING_AGE_HOURS)
    listings = []
    for item in response.json().get("itemSummaries", []):
        listing = parse_item(item)
        created = listing.pop("created_dt")
        if created and created < cutoff:
            continue
        listings.append(listing)
    if DEBUG:
        print(f"Category {category_id}: {len(listings)} listings from the last {config.MAX_LISTING_AGE_HOURS} hours")
    SEARCH_CACHE[category_id] = (time.time(), listings)
    return [dict(l) for l in listings]
