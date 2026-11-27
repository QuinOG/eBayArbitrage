"""
Finds the parts in a listing (title first, then item specifics and description), prices them,
and works out the profit.

    parts_value = value of every part found (CPU, board, RAM, GPU)
    cost        = price + shipping + sales tax
    profit      = parts_value - cost

Run `python scanner.py` to scan eBay and print the deals in the terminal.
"""

import re

import config
from prices import lookup
from data.sold_parser import CHIPSET, MOBO_JUNK, MODEL_PATTERNS, extract_gpu, extract_mobo, extract_ram

PART_NAMES = {"cpu": "CPU", "mobo": "Motherboard", "ram": "RAM", "gpu": "GPU"}

# Used by the "Evaluate a listing" page: look for every part, expect a CPU, board and RAM.
MANUAL_SEARCH = {"name": "Manual", "parts": ["cpu", "mobo", "ram", "gpu"], "required": ["cpu", "mobo", "ram"]}
LOT = re.compile(r"\blot\s*(?:of\s*)?(\d+)\b", re.IGNORECASE)

# Desktop titles mix many parts, which confuses the RAM and board extractors.
# These remove text that belongs to other parts before we look for RAM or a board.
GPU_MEMORY = re.compile(r"(\b(?:rtx|gtx|gt|rx|arc)\s*-?\s*[a-z]?\d{3,4}(?:\s*(?:ti|super|xtx|xt|gre))*)\s*\d{1,2}\s*gb\b",
                        re.IGNORECASE)
LISTING_WORDS = re.compile(r"\b(?:combo|bundle|kit|set|package|deal)\b", re.IGNORECASE)
STORAGE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:tb|gb)(?:\s*(?:nvme|ssd|hdd|m\.2|sata))+\b|\b\d+(?:\.\d+)?\s*tb\b",
                     re.IGNORECASE)


def clean_title(part, title):
    if part in ("ram", "mobo"):
        title = GPU_MEMORY.sub(r"\1", title)   # "RTX 3070 8GB" -> "RTX 3070"
        title = STORAGE.sub(" ", title)        # "1TB", "512GB SSD" -> removed
    if part == "mobo":
        title = LISTING_WORDS.sub(" ", title)  # "B450M-A Combo" -> "B450M-A"
    return title


# A description line saying a part isn't included is skipped completely.
NOT_INCLUDED = re.compile(r"not included|n'?t (?:come|include)|does not (?:come|include)|without|sold separately|"
                          r"\bno (?:cpu|ram|gpu|memory|graphics|processor|cooler|psu)\b", re.IGNORECASE)

# Words in a TITLE that say one part isn't in the box. Checked per part, so "no RAM" still counts the CPU.
# "no CPU cooler" is about the cooler, so the CPU patterns refuse a following cooler/fan/heatsink.
NOT_A_COOLER = r"(?!\s*(?:cooler|fan|heatsink|heat sink))"
TITLE_EXCLUDES = {
    "cpu": re.compile(r"\bno (?:cpu|processor)\b" + NOT_A_COOLER + r"|\b(?:cpu|processor) not included\b|"
                      r"\bwithout (?:a |the )?(?:cpu|processor)\b" + NOT_A_COOLER + r"|"
                      r"\b(?:box|cooler|fan|heatsink) only\b|\bempty box\b", re.IGNORECASE),
    "mobo": re.compile(r"\bno (?:motherboard|mobo|board)\b|\b(?:motherboard|mobo|board) not included\b|"
                       r"\bwithout (?:a |the )?(?:motherboard|mobo|board)\b", re.IGNORECASE),
    "ram": re.compile(r"\bno (?:ram|memory)\b|\b(?:ram|memory) not included\b|\bwithout (?:ram|memory)\b",
                      re.IGNORECASE),
    "gpu": re.compile(r"\bno (?:gpu|graphics card|video card|graphics)\b|\b(?:gpu|graphics card) not included\b|"
                      r"\bwithout (?:a |the )?(?:gpu|graphics card|video card)\b", re.IGNORECASE),
}

# Talk about what a board supports or was tested with isn't in the box. Only the text before it is kept:
# "MSI B550 TOMAHAWK, supports Ryzen 5000 like the 5950X" -> "MSI B550 TOMAHAWK, "
SPEC_TALK = re.compile(r"support|compatib|up to|\bmax(?:imum)?\s+(?:of\b|\d|ram|memory|capacity)|upgrade|recommend|"
                       r"tested (?:with|on|in)|used with", re.IGNORECASE)


def detail_lines(listing, key):
    """The lines of the item specifics or description that can describe what's for sale."""
    lines = []
    for line in listing.get(key) or []:
        if NOT_INCLUDED.search(line):
            continue
        talk = SPEC_TALK.search(line)
        line = line[:talk.start()] if talk else line
        if line.strip():
            lines.append(line)
    return lines

# Parts with no price data. They're found so you can see them and type a value, and count as $0 until you do.
EXTRAS = [
    ("Cooler", re.compile(r"\b(?:aio|(?:liquid|water|air|cpu|stock)\s*cool(?:er|ing)|cooler|noctua\s*nh-\S+|hyper\s*212|wraith\s*\w+)\b", re.I)),
    ("PSU", re.compile(r"\b\d{3,4}\s?w(?:att)?\b(?:\s+\S+){0,3}?\s*(?:psu|power supply)|\bpsu\b|\bpower supply\b", re.I)),
    ("Storage", re.compile(r"\b\d+(?:\.\d+)?\s?(?:tb|gb)\s*(?:nvme|ssd|hdd|m\.2|sata)(?:\s*(?:ssd|nvme))?\b", re.I)),
    ("Case", re.compile(r"\b(?:pc|computer|atx|matx|itx|mid[- ]?tower|full[- ]?tower)\s*case\b|\bmid[- ]?tower\b|\b(?:w/|with)\s*case\b", re.I)),
]

DETAIL_SOURCES = (("specifics", "item specifics"), ("description", "description"))
PRICE_RANK = {"exact": 2, "fallback": 1}


def rank(price):
    return PRICE_RANK.get(price["kind"], 0) if price else 0


def mobo_by_chipset(text):
    """A board with no brand in the text, by chipset alone: "B660M Motherboard" -> "B660M"."""
    for word in text.upper().replace("(", " ").replace(")", " ").split():
        m = CHIPSET.match(word.strip(",.;:[]\"'"))
        if m and re.search(r"[A-Z]", m.group(1)):  # skip bare numbers like "970" (usually a GTX 970)
            return m.group(1)
    return None


def cpu_models(text):
    """Every CPU model in the text, across all families. A match inside an earlier family's match is the same chip."""
    taken, found = [], []
    for brand, pat, fmt in MODEL_PATTERNS:
        for m in pat.finditer(text):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue  # "Xeon E5645" already covers "E5645"
            taken.append(m.span())
            found.append(fmt(m))
    return list(dict.fromkeys(found))


def find_part(part, text, allow_chipset=True):
    """Return (model, problem). model is the prices.csv name, or None if it couldn't be identified."""
    text = clean_title(part, text)
    if part == "cpu":
        models = cpu_models(text)
        if len(models) > 1:
            return None, f"several CPU models ({', '.join(models)})"
        return (models[0], None) if models else (None, None)
    extract = {"mobo": extract_mobo, "ram": extract_ram, "gpu": extract_gpu}[part]
    found = extract(text)
    if found:
        return found[1], None
    if part == "mobo" and allow_chipset:
        return mobo_by_chipset(text), None
    return None, None


def find_in_details(part, listing):
    """
    Look for a part in the item specifics, then the description, line by line.
    Returns (model, problem, source). If a source names several different models, none is picked.
    """
    for key, label in DETAIL_SOURCES:
        lines = detail_lines(listing, key)
        found = []
        for allow_chipset in (False, True):  # a full board name beats a bare chipset
            for line in lines:
                model, line_problem = find_part(part, line, allow_chipset)
                if line_problem:
                    return None, f"the {label} has {line_problem}", label
                if model and model not in found:
                    found.append(model)
            if found:
                break
        if len(found) == 1:
            return found[0], None, label
        if len(found) > 1:
            return None, f"the {label} names several ({', '.join(found[:4])})", label
    return None, None, None


def find_extras(listing):
    """Coolers, PSUs, storage and cases. First match per kind, title first."""
    sources = [("title", [listing["title"]])] + [
        (label, detail_lines(listing, key)) for key, label in DETAIL_SOURCES]
    extras = []
    for name, pattern in EXTRAS:
        for label, lines in sources:
            for line in lines:
                m = pattern.search(line)
                if m:
                    break
            else:
                continue
            # "Cooler: Noctua NH-D15" -> use the part after the colon as the name
            label_part, colon, value = line.partition(":")
            model = value.strip() if colon and m.start() < len(label_part) and value.strip() else m[0].strip()
            extras.append({"name": name, "model": model[:60], "source": label})
            break
    return extras


def make_part(part, model, price, quantity=1, source="title"):
    """One row of the parts breakdown. price is a lookup() result, or None for no data."""
    row = {"part": part, "name": PART_NAMES[part], "model": model, "source": source}
    if price is None:
        return {**row, "value": 0.0, "sales": 0, "confidence": "none", "kind": "no data", "priced_as": None}
    return {**row, "value": round(price["value"] * quantity, 2), "sales": price["sales"],
            "confidence": price["confidence"], "kind": price["kind"], "priced_as": price["priced_as"]}


def price_text(part, text):
    """Price a part typed by hand on the evaluate page. Returns a parts row, or raises ValueError."""
    model, problem = find_part(part, text)
    if problem:
        raise ValueError(f"Found {problem}. Type just one.")
    if not model:
        raise ValueError(f"Couldn't identify a {PART_NAMES[part]} in '{text}'. Type a value instead.")
    return make_part(part, model, lookup(part, model), source=None)


def score_listing(listing, search):
    """
    listing: dict with title, price, shipping (None if unknown) and anything else to pass through.
             Optional: specifics and description (lists of text lines), searched for parts the title doesn't name.
    search:  one entry from config.SEARCHES.
    Returns the listing with parts, extras, parts_value, tax, profit, confidence and flags added.
    """
    title = listing["title"]
    has_details = bool(listing.get("specifics") or listing.get("description"))
    flags = []
    parts = []
    missing = []  # required parts that couldn't be identified

    quantity = 1
    lot = LOT.search(title)
    # The manual search lists every part, so it's a CPU lot only if the title names no board, RAM or GPU.
    cpu_only = search["parts"] == ["cpu"] or not any(find_part(p, title)[0] for p in ("mobo", "ram", "gpu"))
    if lot and int(lot[1]) > 1 and cpu_only:
        quantity = int(lot[1])
        flags.append(f"Lot of {quantity}: CPU value multiplied by {quantity}. Check every chip is the same model.")
    risky = quantity > 1  # True when a flag means the profit is a guess

    for part in search["parts"]:
        name = PART_NAMES[part]
        if TITLE_EXCLUDES[part].search(title):
            flags.append(f"Title says the {name} isn't included. Counted as $0.")
            missing.append({"part": part, "name": name})
            continue
        model, problem = find_part(part, title)
        price = lookup(part, model) if model else None
        source = "title"
        # Title first. Use the item specifics or description when the title doesn't name the part,
        # or when they name it precisely enough to get a better price (exact instead of a chipset average).
        if has_details and not problem and rank(price) < 2:
            d_model, d_problem, d_source = find_in_details(part, listing)
            d_price = lookup(part, d_model) if d_model else None
            if model is None and d_problem:
                problem = d_problem
            elif d_model and (model is None or rank(d_price) > rank(price)):
                model, price, source = d_model, d_price, d_source

        if problem:
            flags.append(f"{name}: {problem}. Counted as $0.")
        if model is None:
            if part in search["required"] or problem:
                missing.append({"part": part, "name": name})
            if part in search["required"] and not problem:
                where = "the listing" if has_details else "title"
                flags.append(f"{name} not identified in {where}. Counted as $0.")
            continue

        parts.append(make_part(part, model, price, quantity if part == "cpu" else 1, source))
        if price is None:
            flags.append(f"No price data for {name} '{model}'. Counted as $0.")
        elif part == "mobo" and price["kind"] == "fallback":
            risky = True
            if model == price["priced_as"]:
                flags.append(f"Board brand and model unknown, priced as an average {model} board.")
            else:
                flags.append(f"No sold data for '{model}', priced as an average {price['priced_as']} board.")
        if source != "title":
            flags.append(f"{name} '{model}' is from the {source}, not the title. Check it's included.")
        if "VRAM unknown" in model:
            flags.append("GPU memory size not in the listing. Check it.")

    extras = find_extras(listing)
    if extras:
        names = ", ".join(f"{e['name']} ({e['model']})" for e in extras)
        flags.append(f"No price data for: {names}. Counted as $0.")

    junk = next((m for m in map(MOBO_JUNK.search, listing.get("description") or []) if m), None)
    if junk:
        flags.append(f"Description mentions '{junk[0]}'. Values assume working parts.")
    if MOBO_JUNK.search(title):
        flags.append("Title suggests parts may be damaged or untested. Values assume working parts.")
    if junk or MOBO_JUNK.search(title):
        risky = True

    shipping = listing.get("shipping")
    if shipping is None:
        risky = True
        flags.append("Shipping cost unknown. Counted as $0.")
        shipping = 0.0

    price = listing["price"]
    taxable = price + shipping if config.TAX_ON_SHIPPING else price
    tax = round(taxable * config.SALES_TAX_RATE, 2)
    cost = round(price + shipping + tax, 2)
    parts_value = round(sum(p["value"] for p in parts), 2)
    profit = round(parts_value - cost, 2)

    # Low when any price is thin, a required part is missing, or a flag means the profit is a guess.
    low = not parts or bool(missing) or risky or any(p["confidence"] != "high" for p in parts)
    return {
        **listing,
        "search": search["name"],
        "shipping": shipping,
        "parts": parts,
        "missing": missing,
        "extras": extras,
        "parts_value": parts_value,
        "tax": tax,
        "profit": profit,
        "is_deal": profit >= config.MIN_PROFIT,
        "confidence": "low" if low else "high",
        "flags": flags,
    }


def scan_all():
    """Run every search in config.SEARCHES. Returns (scored listings sorted by profit, error messages)."""
    from ebay_api import search_listings  # imported here so tests can run without API keys

    scored, errors = [], []
    for search in config.SEARCHES:
        try:
            listings = search_listings(search["category_id"])
        except Exception as e:
            errors.append(f"{search['name']} search failed: {e}")
            continue
        scored += [score_listing(l, search) for l in listings]
    scored.sort(key=lambda d: d["profit"], reverse=True)
    return scored, errors


def print_deal(d):
    mark = "  [LOW CONFIDENCE]" if d["confidence"] == "low" else ""
    print(f"${d['profit']:>8.2f} profit  [{d['search']}]{mark}")
    print(f"    {d['title']}")
    for p in d["parts"]:
        how = p["kind"] if p["priced_as"] in (None, p["model"]) else f"fallback '{p['priced_as']}'"
        print(f"    {p['name']:<12} {p['model']:<36} ${p['value']:>8.2f}  "
              f"{p['sales']} sales, {p['confidence']}, {how}")
    print(f"    parts value ${d['parts_value']:.2f} - (price ${d['price']:.2f} + shipping ${d['shipping']:.2f}"
          f" + tax ${d['tax']:.2f}) = ${d['profit']:.2f}")
    for f in d["flags"]:
        print(f"    ! {f}")
    print()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    results, errs = scan_all()
    for e in errs:
        print("ERROR:", e)
    deals = [d for d in results if d["is_deal"]]
    print(f"{len(results)} listings scanned, {len(deals)} with ${config.MIN_PROFIT:.0f}+ profit\n")
    for d in deals:
        print_deal(d)
