# eBay Arbitrage

This app scans eBay listings for PC parts and compares each price with eBay sold prices. It shows the listings that look like deals. It also scores one listing you paste in, so you can check a specific offer.

It uses only eBay's official Browse API, about 5,000 calls a day.

## Setup

1. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`.
3. Fill in your eBay Production keys: `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`.

## Run

Start the web app:

```
python app.py
```

Then open http://127.0.0.1:5000.

Scans are cached for 90 seconds. To get fresh results, click **Refresh** on the home page.

Command-line scan: `python scanner.py`. Category check: `python check_categories.py`.

Debug mode (auto-reload and the in-browser debugger) is off by default. To turn it on in PowerShell, run `$env:FLASK_DEBUG="1"` before `python app.py`. Keep it off on any shared network.

## The evaluate page

Open http://127.0.0.1:5000/evaluate to score one listing. Enter a listing link, or enter the details by hand. The server finds the parts and their values. You can then edit the values, add or remove parts, and change the price. The page recalculates in your browser as you edit.

## Settings

Settings live in `config.py`.

## Tests

```
python -B -m unittest discover -s tests -t . -v
node tests/test_parts.js
```

## Price data

The price data and how to refresh it are in [data/README.md](data/README.md).

## Limits

Known gaps are listed in [TO-DO](TO-DO).
