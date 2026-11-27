"""
Sanity check: score some sample listing titles without calling eBay.
Run: python test_titles.py
"""

import config
from scanner import score_listing, print_deal

SEARCH = {s["name"]: s for s in config.SEARCHES}

# (search, title, price, shipping). shipping None = unknown.
SAMPLES = [
    ("CPU", "Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor SR3QS", 38.00, 5.00),
    ("CPU", "AMD Ryzen 5 5600X 6-Core 3.7GHz AM4 Processor CPU - Tested Working", 85.00, 0.00),
    ("CPU", "AMD Ryzen 7 7800X3D 8-Core 4.2GHz AM5 CPU Processor", 245.00, 0.00),
    ("CPU", "Lot of 5 Intel Core i5-8500 3.0GHz SR3XE LGA1151 CPU", 99.00, 8.50),
    ("CPU", "Intel Core i5 10th Gen Processor Desktop CPU", 40.00, 4.99),
    ("CPU", "Intel Core i9-9900K 3.6GHz 8-Core LGA1151 - Untested, For Parts", 60.00, 5.00),
    ("Combo", "MSI B450 TOMAHAWK MAX + AMD Ryzen 5 3600 + 16GB DDR4 3200 Combo", 110.00, 15.00),
    ("Combo", "ASUS ROG STRIX B550-F GAMING WIFI w/ Ryzen 7 5800X CPU AM4 Combo", 180.00, None),
    ("Combo", "Gigabyte Z390 AORUS PRO Motherboard i7-9700K CPU 32GB (2x16GB) DDR4 3200", 190.00, 20.00),
    ("Combo", "Intel i5-12400F + B660M Motherboard + 16GB DDR4 Bundle", 120.00, 12.00),
    ("Desktop", "Custom Gaming PC Ryzen 5 5600X RTX 3060 12GB 16GB DDR4 MSI B550 GAMING PLUS 1TB NVMe", 450.00, 40.00),
    ("Desktop", "Gaming PC Intel i7-9700K GTX 1080 Ti 16GB (2x8GB) DDR4 500GB SSD Windows 11", 300.00, 35.00),
    ("Desktop", "Gaming PC RTX 3070 8GB i7-10700K 32GB DDR4 3600 ASUS TUF GAMING Z490-PLUS 1TB SSD", 520.00, 50.00),
    ("Desktop", "Gaming Desktop Ryzen 7 5800X3D RX 6800 XT 16GB 32GB (2x16GB) DDR4 3200 2TB NVMe", 700.00, 0.00),
    ("Desktop", "Dell OptiPlex 7070 SFF i7-9700 16GB DDR4 512GB SSD Win 11 Pro", 160.00, 15.00),
]

if __name__ == "__main__":
    for search, title, price, shipping in SAMPLES:
        d = score_listing({"title": title, "price": price, "shipping": shipping}, SEARCH[search])
        print_deal(d)
