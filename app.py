import math
import os
import threading
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()  # reads .env into environment variables before anything uses them

import config
from ebay_api import get_item
from scanner import MANUAL_SEARCH, PART_NAMES, price_text, scan_all, score_listing

app = Flask(__name__)
SCAN_CACHE = {"at": 0.0, "result": None}
SCAN_LOCK = threading.Lock()  # Concurrent requests can share a scan.


def cached_scan(refresh=False):
    with SCAN_LOCK:
        fresh = time.time() - SCAN_CACHE["at"] < config.SCAN_CACHE_SECONDS
        if refresh or not fresh or SCAN_CACHE["result"] is None:
            listings, errors = scan_all()
            scanned_at = time.time()
            SCAN_CACHE["at"] = scanned_at
            SCAN_CACHE["result"] = None if errors and not listings else (listings, errors)
            return (listings, errors), scanned_at
        return SCAN_CACHE["result"], SCAN_CACHE["at"]


def read_amount(body, key, label):
    """A price or shipping amount from the request: blank means 0. Raises ValueError with a message for the page."""
    value = body.get(key)
    if value in (None, ""):
        return 0.0
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(amount) or amount < 0:
        raise ValueError(f"{label} must be a number of 0 or more.")
    return amount


@app.route("/")
def index():
    # The page loads deals from /api/deals with JavaScript.
    return render_template("index.html")


@app.route("/api/deals")
def api_deals():
    refresh = request.args.get("refresh") == "1"
    (listings, errors), at = cached_scan(refresh)
    return jsonify({
        "listings": listings,  # every scanned listing, sorted by profit (highest first)
        "errors": errors,
        "scanned_at": at,
        "min_profit": config.MIN_PROFIT,
        "searches": [s["name"] for s in config.SEARCHES],
    })


@app.route("/evaluate")
def evaluate_page():
    return render_template("evaluate.html")


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    """
    Score one listing. Send JSON with either:
      {"link": "https://www.ebay.com/itm/..."}                      fetches it from eBay
      {"title": "...", "price": 150, "shipping": 10,
       "description": "..."}                                         any listing, typed by hand
    The typed version can also carry "specifics" (a list of lines), "listing_url" and
    "condition", which the page sends back after a listing was loaded by link.
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Send a JSON object."}), 400
    try:
        link = body.get("link")
        if link is not None and not isinstance(link, str):
            raise ValueError("The link must be text.")
        if link:
            listing = get_item(link)
        else:
            title = body.get("title") or ""
            if not isinstance(title, str):
                raise ValueError("The title must be text.")
            title = title.strip()
            if not title:
                return jsonify({"error": "Enter an eBay link, or a title and price."}), 400
            description = body.get("description") or ""
            if not isinstance(description, str):
                raise ValueError("The description must be text.")
            specifics = body.get("specifics") or []
            if not isinstance(specifics, list):
                raise ValueError("The specifics must be a list of lines.")
            listing = {
                "title": title,
                "price": read_amount(body, "price", "Price"),
                "shipping": read_amount(body, "shipping", "Shipping"),
                "condition": str(body.get("condition") or ""),
                "listing_url": str(body.get("listing_url") or ""),
                "post_date": "",
                "specifics": [str(l) for l in specifics][:200],
                "description": [l.strip() for l in description.splitlines() if l.strip()],
            }
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Couldn't load the listing: {e}"}), 502
    return jsonify({
        "listing": score_listing(listing, MANUAL_SEARCH),
        "sales_tax_rate": config.SALES_TAX_RATE,
        "tax_on_shipping": config.TAX_ON_SHIPPING,
        "min_profit": config.MIN_PROFIT,
    })


@app.route("/api/price", methods=["POST"])
def api_price():
    """Price one part typed by hand: {"part": "gpu", "text": "RTX 3060 12GB"}."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Send a JSON object."}), 400
    part, text = body.get("part"), body.get("text")
    text = text.strip() if isinstance(text, str) else ""
    if not isinstance(part, str) or part not in PART_NAMES or not text:
        return jsonify({"error": "Pick a part type and type its model."}), 400
    try:
        return jsonify(price_text(part, text))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    # FLASK_DEBUG=1 turns on auto-reload and the in-browser debugger. Keep it off on shared networks.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
