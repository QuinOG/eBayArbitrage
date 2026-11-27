"""
collect_sold.py - collect eBay sold prices faster, then rebuild data/prices.csv.

eBay blocks scripts that download its search pages, and these API keys don't
have the official sold-data API (Marketplace Insights). So you still browse,
but the script does the rest:

  1. It opens a sold search in your browser: used items only, newest sales
     first, 240 results per page (the normal page shows 60).
  2. You press Ctrl+A, then Ctrl+C on that page.
  3. The script sees the copy, saves it to data/raw/<part>/, tells you how
     many sales it found, closes that tab, and opens the next page.
  4. It moves to the next part once most sales on a page are older than --days.
  5. At the end it runs sold_parser.py on every saved page and rebuilds
     data/prices.csv. The old file is kept as data/prices_backup_<date>.csv.

Usage:
  python collect_sold.py                  all four parts, last 30 days
  python collect_sold.py gpu ram          only these parts
  python collect_sold.py --days 14        stop at sales older than 14 days
  python collect_sold.py gpu --start-page 6   pick up where you left off
  python collect_sold.py --build-only     skip collecting, just rebuild prices.csv

Press Ctrl+C in this window to skip the rest of the current part.
Saved pages stay in data/raw/, so each run adds to the data you already have.
Older pastes can go in data/raw/<part>/ too; duplicate sales are dropped.
"""

import argparse
import csv
import ctypes
import os
import shutil
import sys
import time
import tkinter
import webbrowser
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from data import sold_parser

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")

# Category IDs: CPUs/Processors, Motherboards, Memory (RAM), Graphics/Video Cards.
# The keywords are eBay OR searches, so every listing found has a word the
# sold_parser.py extractors need (a CPU family, a board brand, a DDR type, a GPU line).
PARTS = {
    "cpu": {"category_id": "164", "keywords": "(intel,amd,ryzen,xeon,core)"},
    "mobo": {"category_id": "1244", "keywords": "(asus,msi,gigabyte,asrock,evga,biostar,nzxt)"},
    "ram": {"category_id": "170083", "keywords": "(ddr3,ddr4,ddr5)"},
    "gpu": {"category_id": "27386", "keywords": "(rtx,gtx,radeon,rx,geforce,quadro,arc)"},
}


def sold_search_url(part, page):
    p = PARTS[part]
    query = {
        "_nkw": p["keywords"],
        "LH_Sold": "1",
        "LH_Complete": "1",
        "LH_ItemCondition": "3000",  # Used. sold_parser.py only keeps "Pre-Owned" sales anyway.
        "_sop": "13",                # End date: recent first
        "_ipg": "240",               # results per page
        "_pgn": str(page),
    }
    return f"https://www.ebay.com/sch/{p['category_id']}/i.html?" + urlencode(query)


class Clipboard:
    """Reads the Windows clipboard with tkinter, which comes with Python."""

    def __init__(self):
        self.tk = tkinter.Tk()
        self.tk.withdraw()

    def text(self):
        try:
            self.tk.update()  # without this, tkinter misses copies made in other programs
            return self.tk.clipboard_get()
        except tkinter.TclError:  # empty, or not text (an image, say)
            return ""

    def clear(self):
        self.tk.clipboard_clear()
        self.tk.update()


def parse_text(text, path):
    """Save the copied page and read its sales with sold_parser.parse_file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return sold_parser.parse_file(path)


def wait_for_page(clip, part, page):
    """Wait until the clipboard holds a sold-results page. Returns its sales and the saved path."""
    folder = os.path.join(RAW_DIR, part)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{date.today()}_p{page:02}.txt")
    last = clip.text()
    while True:
        time.sleep(0.5)
        text = clip.text()
        if not text or text == last:
            continue
        last = text
        sales = parse_text(text, path)
        if sales:
            return sales, path
        os.remove(path)
        print("    That copy had no sold listings. Press Ctrl+A, then Ctrl+C on the eBay page.")


def close_ebay_tab():
    """Close the tab the page was copied from by pressing Ctrl+W in it. Returns True if it did."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(user32.GetForegroundWindow(), title, 512)
    # Only press Ctrl+W when an eBay tab is in front. In a terminal or editor it would close that instead.
    if "| ebay" not in title.value.lower():  # eBay pages are titled "... | eBay"
        return False
    ctrl, w, keyup = 0x11, 0x57, 0x0002
    user32.keybd_event(ctrl, 0, 0, 0)
    user32.keybd_event(w, 0, 0, 0)
    user32.keybd_event(w, 0, keyup, 0)
    user32.keybd_event(ctrl, 0, keyup, 0)
    time.sleep(0.3)  # let the tab close before the next one opens
    return True


def collect_part(clip, part, days, start_page, max_pages):
    cutoff = datetime.now() - timedelta(days=days)
    seen = set()
    total = 0
    print(f"\n== {part.upper()}: sold in the last {days} days")
    try:
        for page in range(start_page, start_page + max_pages):
            clip.clear()
            url = sold_search_url(part, page)
            webbrowser.open(url)
            print(f"  Page {page}: opened in your browser. Press Ctrl+A, then Ctrl+C there.")
            sales, path = wait_for_page(clip, part, page)
            if not close_ebay_tab():
                print("    Left that tab open, because the eBay tab wasn't the window in front.")
            new =[s for s in sales if (s["title"], s["date"], s["price"]) not in seen]
            seen.update((s["title"], s["date"], s["price"]) for s in sales)
            total += len(new)
            # A few odd old sales show up even on page 1, so go by the typical (median) date, not the oldest.
            dates = sorted(s["date"] for s in sales)
            typical = dates[len(dates) // 2]
            print(f"    Saved {len(sales)} sales ({len(new)} new), most around {typical:%b %d}. "
                  f"-> {os.path.relpath(path)}")
            if sales and not new:
                print("    Every sale on this page was already saved. Is the browser still on the last page?")
            if typical < cutoff:
                print(f"    Reached sales older than {days} days.")
                break
            if len(sales) < 30:
                print("    Short page, so this is probably the last one.")
                break
        else:
            print(f"    Stopped at --max-pages {max_pages}.")
    except KeyboardInterrupt:
        print("\n    Skipped the rest of this part.")
    print(f"  {part.upper()}: {total} sales collected this run.")


def build_prices(parts):
    """Run sold_parser.py on every saved page, then merge the tables into prices.csv."""
    os.chdir(DATA_DIR)  # sold_parser.py writes its tables to the current folder
    if os.path.exists("prices.csv"):
        backup = f"prices_backup_{date.today()}.csv"
        shutil.copy("prices.csv", backup)
        print(f"\nBacked up the old prices.csv to data/{backup}")
    old_rows = []
    if os.path.exists("prices.csv"):
        with open("prices.csv", newline="", encoding="utf-8") as f:
            old_rows = list(csv.DictReader(f))
    missing = []
    for part in parts:
        folder = os.path.join("raw", part)
        files = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                       if f.endswith(".txt")) if os.path.isdir(folder) else []
        print(f"\n== Building {part} prices from {len(files)} saved page(s)")
        if not files:
            print(f"  No saved pages in data/raw/{part}/. Keeping the {part} rows from the old prices.csv.")
            missing.append(part)
            if os.path.exists(f"{part}_price_table.csv"):
                os.remove(f"{part}_price_table.csv")  # so combine() doesn't also add a stale table
            if part == "mobo" and os.path.exists("mobo_chipset_table.csv"):
                os.remove("mobo_chipset_table.csv")
            if part == "ram" and os.path.exists("ram_capacity_table.csv"):
                os.remove("ram_capacity_table.csv")
            continue
        sold_parser.main(files, part)
    print()
    sold_parser.combine()
    kept = [r for r in old_rows if r["part"] in missing]
    if kept:
        with open("prices.csv", "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=["part", "model", "value", "sales", "confidence", "kind"]).writerows(kept)
        print(f"Kept {len(kept)} old rows for: {', '.join(missing)}.")


def main():
    ap = argparse.ArgumentParser(description="Collect eBay sold prices and rebuild data/prices.csv.")
    ap.add_argument("parts", nargs="*", help="cpu, mobo, ram and/or gpu (default: all four)")
    ap.add_argument("--days", type=int, default=30, help="stop at sales older than this (default 30)")
    ap.add_argument("--start-page", type=int, default=1, help="first page number (default 1)")
    ap.add_argument("--max-pages", type=int, default=40, help="most pages per part (default 40)")
    ap.add_argument("--build-only", action="store_true", help="skip collecting, just rebuild prices.csv")
    args = ap.parse_args()
    parts = args.parts or list(PARTS)
    unknown = [p for p in parts if p not in PARTS]
    if unknown:
        ap.error(f"unknown part {', '.join(unknown)}. Choose from: {', '.join(PARTS)}")

    if not args.build_only:
        clip = Clipboard()
        print("A browser tab opens for each page. Ctrl+A, then Ctrl+C on it, and the next page opens.")
        for part in parts:
            collect_part(clip, part, args.days, args.start_page, args.max_pages)

    # prices.csv is rebuilt from all four parts, so a run for one part keeps the others' rows.
    build_prices(list(PARTS))


if __name__ == "__main__":
    sys.exit(main())
