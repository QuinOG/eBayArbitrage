"""
Looks up what a part sells for, using data/prices.csv.

The CSV is read once, when this file is first imported, into PRICES:
    PRICES[("cpu", "Core i7-8700")] = {"value": 61.0, "sales": 26, "confidence": "high", "kind": "exact"}

Lookup order (see data/README.md):
    1. exact model
    2. fallback (motherboards: by chipset, RAM: by type + size)
    3. no data -> returns None, and the caller counts the part as $0
"""

import csv
import os

from data.sold_parser import CHIPSET

PRICES_FILE = os.path.join(os.path.dirname(__file__), "data", "prices.csv")


def load_prices(path=PRICES_FILE):
    prices = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["part"], row["model"])
            prices[key] = {
                "value": float(row["value"]),
                "sales": int(row["sales"]),
                "confidence": row["confidence"],
                "kind": row["kind"],
            }
    return prices


PRICES = load_prices()


def fallback_model(part, model):
    """The name of the backup price row for a model, or None if that part has no backup."""
    if part == "mobo":
        # "MSI B450 TOMAHAWK MAX" -> "B450". Same steps sold_parser.py uses to build the chipset rows.
        for word in model.split()[1:]:
            m = CHIPSET.match(word)
            if m:
                return m.group(1)
        return None
    if part == "ram":
        # "DDR4 Desktop 16GB (2x8GB) 3200" -> "DDR4 Desktop 16GB"
        return " ".join(model.split()[:3])
    return None


def lookup(part, model):
    """Return {"value", "sales", "confidence", "kind", "priced_as"} or None if there's no data."""
    row = PRICES.get((part, model))
    if row:
        return {**row, "priced_as": model}
    backup = fallback_model(part, model)
    if backup:
        row = PRICES.get((part, backup))
        if row:
            return {**row, "priced_as": backup}
    return None
