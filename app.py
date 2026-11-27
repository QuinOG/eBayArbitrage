from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()  # reads .env into environment variables before anything uses them

import config
from ebay_api import get_item
from scanner import MANUAL_SEARCH, PART_NAMES, price_text, scan_all, score_listing

app = Flask(__name__)


@app.route("/")
def index():
    # The page loads deals from /api/deals with JavaScript.
    return render_template("index.html")


@app.route("/api/deals")
def api_deals():
    listings, errors = scan_all()
    return jsonify({
        "listings": listings,  # every scanned listing, sorted by profit (highest first)
        "errors": errors,
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
    try:
        if body.get("link"):
            listing = get_item(body["link"])
        else:
            title = (body.get("title") or "").strip()
            if not title:
                return jsonify({"error": "Enter an eBay link, or a title and price."}), 400
            shipping = body.get("shipping")
            listing = {
                "title": title,
                "price": float(body.get("price") or 0),
                "shipping": float(shipping) if shipping not in (None, "") else 0.0,
                "condition": str(body.get("condition") or ""),
                "listing_url": str(body.get("listing_url") or ""),
                "post_date": "",
                "specifics": [str(l) for l in (body.get("specifics") or [])][:200],
                "description": [l.strip() for l in (body.get("description") or "").splitlines() if l.strip()],
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
    part, text = body.get("part"), (body.get("text") or "").strip()
    if part not in PART_NAMES or not text:
        return jsonify({"error": "Pick a part type and type its model."}), 400
    try:
        return jsonify(price_text(part, text))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True)
