"""
Confirms the eBay category IDs in config.SEARCHES using eBay's Taxonomy API.
Run: python check_categories.py

For each configured search it prints the category's real name and path, and
whether it is a leaf (a leaf has no subcategories). It also asks eBay which
categories it suggests for each kind of listing, so you can compare.
"""

from dotenv import load_dotenv

load_dotenv()

import config
from ebay_api import api_headers, request_with_retry

TAXONOMY = "https://api.ebay.com/commerce/taxonomy/v1"
SUGGESTION_QUERIES = {
    "CPU": "intel core i7 cpu processor",
    "Combo": "motherboard cpu combo",
    "Desktop": "gaming desktop pc computer",
}


def path_of(node):
    ancestors = [a["categoryName"] for a in reversed(node.get("categoryTreeNodeAncestors", []))]
    return " > ".join(ancestors + [node["category"]["categoryName"]])


def main():
    headers = api_headers()
    r = request_with_retry("GET", f"{TAXONOMY}/get_default_category_tree_id",
                           headers=headers, params={"marketplace_id": "EBAY_US"})
    r.raise_for_status()
    tree = r.json()["categoryTreeId"]

    print("Configured categories:")
    for search in config.SEARCHES:
        r = request_with_retry("GET", f"{TAXONOMY}/category_tree/{tree}/get_category_subtree",
                               headers=headers, params={"category_id": search["category_id"]})
        if r.status_code != 200:
            print(f"  {search['name']:<8} {search['category_id']:>7}  NOT FOUND ({r.status_code})")
            continue
        node = r.json()["categorySubtreeNode"]
        leaf = "leaf" if node.get("leafCategoryTreeNode") else f"{len(node.get('childCategoryTreeNodes', []))} subcategories"
        print(f"  {search['name']:<8} {search['category_id']:>7}  {path_of(node)}  ({leaf})")

    print("\neBay's suggested categories:")
    for name, query in SUGGESTION_QUERIES.items():
        r = request_with_retry("GET", f"{TAXONOMY}/category_tree/{tree}/get_category_suggestions",
                               headers=headers, params={"q": query})
        r.raise_for_status()
        print(f"  {name} ('{query}'):")
        for s in r.json().get("categorySuggestions", [])[:4]:
            print(f"    {s['category']['categoryId']:>7}  {path_of(s)}")


if __name__ == "__main__":
    main()
