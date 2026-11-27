"""
Settings for the deal scanner. Change numbers here, not in the code.
Secrets (API keys, passwords) do NOT go here. They go in .env.
"""

# --- Money ---
# You resell locally, so there are no eBay selling fees.
# The only extra cost is the sales tax you pay when you buy.
SALES_TAX_RATE = 0.075     # 7.5%
TAX_ON_SHIPPING = True     # True: tax = rate x (price + shipping). False: tax = rate x price.
MIN_PROFIT = 20.00         # a listing needs at least this much profit to count as a deal

# --- What to search on eBay ---
# Each search is one Browse API call.
#   parts:    which parts to look for in the listing title
#   required: parts every listing of this type should have. If one can't be
#             identified it counts as $0 and the deal gets a warning flag.
#   details:  also read each listing's item specifics and description, like the
#             evaluate page does. Costs 1 extra API call per new listing (cached
#             for 12 hours in data/details_cache.json, so refreshes are nearly free).
# A search with one part (CPU, GPU) still prices every part of a bundle listed in it.
#
# Run `python check_categories.py` to confirm these category IDs with eBay's
# Taxonomy API. See the TO-DO file.
SEARCHES = [
    {"name": "CPU", "category_id": "164",
     "parts": ["cpu"], "required": ["cpu"]},
    {"name": "Combo", "category_id": "131511",
     "parts": ["cpu", "mobo", "ram", "gpu"], "required": ["cpu", "mobo"], "details": True},
    {"name": "Desktop", "category_id": "179",
     "parts": ["cpu", "mobo", "ram", "gpu"], "required": ["cpu", "mobo", "ram"], "details": True},
    {"name": "GPU", "category_id": "27386",
     "parts": ["gpu"], "required": ["gpu"]},
]

LISTINGS_PER_SEARCH = 50       # newest N listings per search (Browse API max is 200)
MAX_LISTING_AGE_HOURS = 4      # ignore listings older than this
ITEM_LOCATION_COUNTRY = "US"   # only listings shipping from this country
BUYER_ZIP = "32607"            # your ZIP code, so eBay returns real shipping costs ("" to turn off)
SCAN_CACHE_SECONDS = 90        # reuse a scan this long; the Refresh button skips it
