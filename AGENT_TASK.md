# Task: switch the scanner to local price data and score deals by profit

You're working on my repo QuinOG/eBayArbitrage, a Flask app that scans eBay for PC part deals I can flip. I'm newer to programming, so keep changes simple, explain what you changed and why in plain terms, and don't add frameworks I don't need.

## Goal
Replace the live sold-price scraping with local price data, then score listings by profit.

## What's in data/ (read data/README.md)
- **prices.csv**: every part's sold value in one file. Columns: part (cpu/mobo/ram/gpu), model, value (median sold price incl. shipping, last 90 days), sales, confidence (high = 3+ sales, low = fewer), kind (exact, or fallback = backup price by chipset for boards or by type + size for RAM).
- **sold_parser.py**: its extract functions (`extract_models` for CPUs, `extract_mobo`, `extract_ram`, `extract_gpu`) turn listing titles into the exact model names used in prices.csv.

## Tasks
1. Remove the Playwright / Seller Hub scraping from ebay_api.py (`get_seller_hub_metric_value`, `scrape_terapeak_recent_median`, the persistent Chrome profile). It breaks eBay's terms and causes the bug where only ~3 listings get sold prices before everything falls back to active prices. Also drop the active-listing price fallback in `get_fair_market_value`.
2. Add a prices module that loads data/prices.csv once at startup into a dictionary keyed by (part, model). Lookup order: exact model, then fallback, then "no data". Return value, sales and confidence.
3. Import the extract functions from data/sold_parser.py to pull parts out of ACTIVE listing titles, so names match prices.csv exactly. Don't rewrite them.
4. Score each listing: parts_value = sum of every part found (CPU, board, RAM, GPU). profit = parts_value - (price + shipping) - selling fees. Put the fee rate and a minimum-profit threshold in a config file, not hardcoded. Ask me for my actual eBay fee rate; don't guess it.
5. Searches: besides the CPU category (164), add motherboard/CPU combos and whole desktop PCs. Confirm the right category IDs with eBay's Taxonomy API instead of guessing.
6. Show each deal with its part breakdown, total value, profit and confidence, sorted by profit. Mark low-confidence deals visibly.
7. Security cleanup: move the MySQL credentials in app.py and the eBay keys into a .env file, add .env to .gitignore, and check that no secrets are committed in git history.

## Rules
- Use only eBay's official Browse API for live listings (5,000 calls/day). No scraping.
- Keep the TO-DO file updated: remove what's done, add anything new you find.
- Test with a few real listing titles before wiring up the UI, and show me the extracted parts and scores so I can sanity-check them.
- If a part can't be identified, count it as $0 and flag it. Never invent a price.

When you're done, give me a short summary: what changed, how to run it, and anything I should check.
