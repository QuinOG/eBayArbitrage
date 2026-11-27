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
import re

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


def fallback_models(part, model):
    """The names of the backup price rows for a model, best first. Empty if that part has no backup."""
    if part == "mobo":
        # "MSI B450 TOMAHAWK MAX" -> "B450". Same steps sold_parser.py uses to build the chipset rows.
        # "Gigabyte Z270MX" -> "Z270MX", then "Z270M", then "Z270" (not every suffix has its own row).
        words = model.split()
        for word in words[1:] or words:
            m = CHIPSET.match(word)
            if m:
                chip = m.group(1)
                base = re.match(r"[A-Z]*\d+", chip)[0]
                return list(dict.fromkeys([chip, chip[:len(base) + 1], base]))
        return []
    if part == "ram":
        # "DDR4 Desktop 16GB (2x8GB) 3200" -> "DDR4 Desktop 16GB"
        return [" ".join(model.split()[:3])]
    return []


def lookup(part, model):
    """Return {"value", "sales", "confidence", "kind", "priced_as"} or None if there's no data."""
    if part == "gpu" and model.endswith(" (VRAM unknown)"):
        # "RTX 3060 (VRAM unknown)": price it as the cheapest memory size that card came in.
        # This comes before the "(VRAM unknown)" row itself, which mixes sales of every size.
        base = model.replace(" (VRAM unknown)", "")
        rows = [(r["value"], name, r) for (p, name), r in PRICES.items()
                if p == "gpu" and re.fullmatch(re.escape(base) + r" \d+GB", name)]
        if rows:
            _, name, row = min(rows, key=lambda x: x[0])
            return {**row, "kind": "fallback", "confidence": "low", "priced_as": name}
    row = PRICES.get((part, model))
    if row:
        return {**row, "priced_as": model}
    for backup in fallback_models(part, model):
        row = PRICES.get((part, backup))
        if row:
            return {**row, "priced_as": backup}
    return None
