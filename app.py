from flask import Flask, render_template, request, redirect, url_for
from ebay_api import get_ebay_listings
from dummy_deals import dummy_deals
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)

# --- Database Functions (from your one-file model) ---

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host='127.0.0.1',
            port=3306,  # Update if using a different port (e.g., 8889 for MAMP on macOS)
            user='root',
            password='root',  # Replace with your actual password
            database='computer_parts_db'
        )
        return connection
    except Error as e:
        print("Error connecting to MySQL:", e)
    return None

def get_listings_from_db():
    connection = get_db_connection()
    if not connection:
        return []
    listings = []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM listings")
        listings = cursor.fetchall()
    except Error as e:
        print("Error fetching listings:", e)
    finally:
        cursor.close()
        connection.close()
    return listings

def calculate_net_profit(purchase_price, shipping_cost, tax_estimate=0.0, resale_price_assumption=0.0, platform_fee_rate=0.10):
    if resale_price_assumption == 0.0:
        resale_price_assumption = purchase_price + 50.0
    platform_fees = resale_price_assumption * platform_fee_rate
    net_profit = resale_price_assumption - (purchase_price + shipping_cost + tax_estimate + platform_fees)
    return net_profit

def find_good_deals():
    listings = get_listings_from_db()
    good_deals = []
    for item in listings:
        try:
            purchase_price = float(item["price"])
            shipping_cost = float(item["shipping_cost"])
            tax_estimate = float(item["tax_estimate"])
        except (ValueError, KeyError):
            continue
        net_profit = calculate_net_profit(purchase_price, shipping_cost, tax_estimate)
        if net_profit >= 30:  # Use your threshold
            item["net_profit"] = round(net_profit, 2)
            good_deals.append(item)
    return good_deals

# --- Flask Routes ---

@app.route('/', methods=['GET'])
def index():
    # Retrieve multi-select filters from query parameters
    selected_categories = [cat for cat in request.args.getlist('category') if cat]
    selected_deal_types = [dt for dt in request.args.getlist('deal_type') if dt]

    # Optionally retrieve a keyword from query parameters (default to "computer parts")
    keyword = request.args.get('keyword', 'computer parts')

    try:
        listings = get_ebay_listings(keyword=keyword, limit=50)
    except Exception as e:
        print(e)
        listings = []  # Fallback to empty list or dummy_deals

    # Apply server-side filtering by category
    if selected_categories:
        listings = [
            listing for listing in listings
            if listing.get("category", "").lower() in [cat.lower() for cat in selected_categories]
        ]

    # Apply filtering based on deal type
    if selected_deal_types:
        filtered_listings = []
        for listing in listings:
            net_profit = listing.get("net_profit", 0)
            if net_profit < 10:
                deal_type = "fair"
            elif net_profit < 30:
                deal_type = "good"
            else:
                deal_type = "great"
            if deal_type in [dt.lower() for dt in selected_deal_types]:
                filtered_listings.append(listing)
        listings = filtered_listings

    return render_template('index.html', deals=listings, selected_categories=selected_categories, selected_deal_types=selected_deal_types)

if __name__ == '__main__':
    app.run(debug=True)
