"""
sold_parser.py - turn pasted eBay "Sold" search pages into a CPU price table.

How to use:
  1. Open an eBay sold search (Sold + Completed filters on), Ctrl+A, Ctrl+C,
     paste into a .txt file. Do as many pages as you like; one big file is fine.
  2. Put the .txt files in data/raw/
  3. Run:  python sold_parser.py data/raw/cpu*.txt
           python sold_parser.py --mobo data/raw/mobo*.txt
           python sold_parser.py --ram data/raw/ram*.txt
           python sold_parser.py --gpu data/raw/gpu*.txt
           python sold_parser.py --combine     (merges everything into prices.csv)
  4. Each run writes <part>_price_table.csv and <part>_sales_clean.csv (every sale + why it was kept/skipped).
     Run from any folder; output always goes to data/.

Rules it applies:
  - Only "Pre-Owned" sales count (no "Brand New", no "For parts").
  - Skips lots, CPU+motherboard combos, multi-model titles, and junk
    (for parts, bent pins, untested, box only, etc.).
  - Only sales from the last DAYS days count toward the price table.
  - "Value" = median of (item price + shipping) - what buyers actually paid.
  - "or Best Offer" sales may show the asking price, not the accepted offer,
    so those are left out of the value when there are 3+ other sales.
"""

import csv
import os
import re
import statistics
import sys
from datetime import datetime, timedelta

DAYS = 90
MIN_SALES = 3  # fewer sales than this gets flagged "low data"

# Every file this script writes goes next to this script (the data/ folder), wherever you run it from.
DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def data_path(name):
    return os.path.join(DATA_DIR, name)

JUNK = re.compile(
    r"for parts|not working|broken|bent pin|missing pin|damaged|as[- ]is|untested|"
    r"read desc|box only|empty box|cooler only|fan only|heatsink only|no cpu|"
    r"\bcombo\b|motherboard|mobo|\bboard\b|bundle|\bkit\b|laptop|desktop pc|"
    r"engineering sample|\bES\b|\bQS\b|\b(?:msi|asus|gigabyte|asrock|evga|biostar)\b",
    re.IGNORECASE,
)
LOT = re.compile(r"\blot\s*(?:of\s*)?(\d+)|\b(\d+)\s*(?:pcs|pieces)\b|\b(\d{1,2})\s?x\b|\bx\s?(\d{1,2})\b|^\((\d+)\)", re.IGNORECASE)

MODEL_PATTERNS = [
    # Intel Core Ultra 7 265K
    ("Intel", re.compile(r"ultra\s*([579])\s*(\d{3})([a-z]{0,2})\b", re.I),
     lambda m: f"Core Ultra {m[1]} {m[2]}{m[3].upper()}"),
    # Intel Core i7-10700K
    ("Intel", re.compile(r"\bi([3579])[\s-]?(\d{4,5})([a-z]{0,3})\b", re.I),
     lambda m: f"Core i{m[1]}-{m[2]}{m[3].upper()}"),
    # AMD Ryzen 7 5800X3D / Ryzen 5 PRO 4650G
    ("AMD", re.compile(r"ryzen\s*([3579])\s*(?:pro\s*)?(\d{4})\s?(x3d|xt|x|ge|g|f|e)?\b", re.I),
     lambda m: f"Ryzen {m[1]} {m[2]}{(m[3] or '').upper()}"),
    ("AMD", re.compile(r"\b(\d{4})(x3d|xt|x|g)\b.{0,20}ryzen\s*([3579])\b", re.I),
     lambda m: f"Ryzen {m[3]} {m[1]}{m[2].upper()}"),
    # AMD Threadripper 3970X
    ("AMD", re.compile(r"threadripper\s*(?:pro\s*)?(\d{4})([a-z]{0,3})\b", re.I),
     lambda m: f"Threadripper {m[1]}{m[2].upper()}"),
    # AMD EPYC 7742
    ("AMD", re.compile(r"epyc\s*(\d{4}[a-z0-9]{0,3})\b", re.I),
     lambda m: f"EPYC {m[1].upper()}"),
    # Intel Xeon E5-2690 v4 / Xeon Gold 6148 / Xeon W-2135
    ("Intel", re.compile(r"xeon\s*(?:e\d\s*)?(?:(platinum|gold|silver|bronze)\s*)?((?:e[357]|e|w)?-?\s?\d{4,5}[a-z]?)(?:\s*(v\d))?", re.I),
     lambda m: "Xeon " + " ".join(x for x in [(m[1] or "").title(), m[2].upper().replace(" ", ""), (m[3] or "").lower()] if x)),
    # Pentium G4560 / Celeron G3900
    ("Intel", re.compile(r"(pentium|celeron)\s*(?:gold\s*)?([gjn]\d{3,4}[a-z]?)\b", re.I),
     lambda m: f"{m[1].title()} {m[2].upper()}"),
    # Core 2 Quad Q6600
    ("Intel", re.compile(r"\b([qe]\d{4})\b", re.I),
     lambda m: f"Core 2 {m[1].upper()}"),
]


def extract_models(title):
    found = []
    for brand, pat, fmt in MODEL_PATTERNS:
        for m in pat.finditer(title):
            found.append((brand, fmt(m)))
        if found:
            break  # first family that matches wins
    return list(dict.fromkeys(found))  # dedupe, keep order


CHIPSET = re.compile(
    r"^(?:GA-)?(?:A|AB|AX)?((?:A3[02]0|A[56]20|B[3-6]50|B8[45]0|X[3-6]70|X670E?|X870E?|B650E|"
    r"[HBZQ](?:1[0-7]0|2[0-7]0|3[0-9]0|4[0-9]0|5[0-9]0|6[0-9]0|7[0-9]0|8[0-9]0)|"
    r"X99|X299|X399|TRX40|Z97|H97|H81|B85|Z87|H87|Q87|Z77|H77|B75|H61|P67|Z68|X79|"
    r"970A?|990FXA?|990X)(?:[A-Z]{1,2})?)(?:[-/][A-Z0-9+]+)*$")
MOBO_BRANDS = [("ASUS", r"asus|\brog\b"), ("MSI", r"\bmsi\b"), ("Gigabyte", r"gigabyte|aorus|\bga-"),
               ("ASRock", r"asrock"), ("EVGA", r"\bevga\b"), ("Biostar", r"biostar"), ("NZXT", r"\bnzxt\b")]
STOP = {"MOTHERBOARD", "MOBO", "ATX", "MATX", "MICROATX", "MICRO", "MINI", "ITX", "MINI-ITX", "E-ATX",
        "EATX", "AM4", "AM5", "AM3", "AM3+", "SOCKET", "INTEL", "AMD", "DDR3", "DDR4", "DDR5", "W/",
        "WITH", "+", "&", "-", "|", "/", "RYZEN", "CORE", "MAINBOARD", "BOARD", "DESKTOP", "PC", "USED",
        "TESTED", "HDMI", "M.2", "USB", "AND", "FOR", "CPU", "RGB", "4-DIMM", "2-DIMM"}
OEM_OR_LAPTOP = re.compile(r"laptop|notebook|xps|pavilion|thinkpad|latitude|inspiron|optiplex|"
                           r"elitedesk|prodesk|thinkcentre|vostro|precision|macbook|chromebook|oem|"
                           r"supermicro|server|\bdell\b|\bhp\b|lenovo|acer", re.I)
MOBO_JUNK = re.compile(r"for parts|not working|broken|bent pin|missing pin|damaged|as[- ]is|untested|"
                       r"read desc|shield only|backplate only|no post|won'?t post|parts only|repair", re.I)
COMBO = re.compile(r"\bcombo\b|w/\s*cpu|with\s*cpu|\+\s*cpu|&\s*cpu|\bcpu\b.*\bram\b|\bbundle\b", re.I)


def extract_mobo(title):
    brand = next((b for b, pat in MOBO_BRANDS if re.search(pat, title, re.I)), None)
    if not brand:
        return None
    t = title.upper().replace("WI-FI", "WIFI").replace("(", " ").replace(")", " ")
    toks = [x.strip(",.;:[]\"'") for x in t.split()]
    for i, tok in enumerate(toks):
        if CHIPSET.match(tok):
            key = [tok.replace("GA-", "")]
            for nxt in toks[i + 1:]:
                if not nxt or nxt in STOP or nxt.startswith("LGA") or re.match(r"^\d{3,4}$", nxt) or len(key) >= 4:
                    break
                key.append(nxt)
            if len(key) == 1 and not re.search(r"[-/]", tok):  # name comes before the chipset, e.g. "ROG CROSSHAIR VIII HERO X570"
                skip = {"ASUS", "ROG", "MSI", "GIGABYTE", "AORUS", "ASROCK", "EVGA", "BIOSTAR", "NZXT"} | STOP
                before = [x for x in toks[max(0, i - 4):i] if x and x not in skip]
                key = before + key
            return brand, f"{brand} " + " ".join(key)
    return None


SPEEDS = [1066, 1333, 1600, 1866, 2133, 2400, 2666, 2933, 3000, 3200, 3466, 3600, 4000, 4400,
          4800, 5200, 5600, 6000, 6400, 6800, 7200, 8000]
RAM_JUNK = re.compile(r"for parts|not working|broken|damaged|as[- ]is|untested|read desc|mixed|assorted|"
                      r"\blot\b|bulk|heat ?sink only|no ram", re.I)


def extract_ram(title):
    t = title.lower().replace("so-dimm", "sodimm")
    gen = re.search(r"ddr\s?([345])|\bpc([345])[l]?-", t)
    if not gen:
        return None
    gen = f"DDR{gen[1] or gen[2]}"
    if re.search(r"(?<!non-)(?<!non )\becc\b|registered|\brdimm|lrdimm|server|\breg\b", t):
        form = "Server"
    elif re.search(r"sodimm|laptop|notebook|260-?pin|262-?pin|204-?pin|imac|mac mini", t):
        form = "Laptop"
    else:
        form = "Desktop"
    m = (re.search(r"(\d+)\s*gb\s*\(\s*(\d+)\s*x\s*(\d+)\s*gb", t)
         or re.search(r"\(\s*(\d+)\s*x\s*(\d+)\s*gb", t)
         or re.search(r"\b(\d+)\s*x\s*(\d+)\s*gb", t))
    if m and len(m.groups()) == 3:
        n, each = int(m[2]), int(m[3])
    elif m:
        n, each = int(m[1]), int(m[2])
    else:
        m2 = re.search(r"\b(\d+)\s*gb\s*x\s*(\d)\b", t)
        caps = re.findall(r"\b(\d+)\s*gb\b", t)
        if m2:
            n, each = int(m2[2]), int(m2[1])
        elif caps:
            nx = re.match(r"^\(?(\d)\)?\s*x\s", t)
            n, each = (int(nx[1]) if nx else 1), int(caps[0])
        else:
            return None
    if each not in (1, 2, 4, 8, 16, 24, 32, 48, 64, 128) or not 1 <= n <= 8:
        return None
    sp = None
    for pat in (r"ddr[345]l?[- ]?(\d{4})\b", r"\b(\d{4})\s*mhz", r"\bpc[345]l?-(\d{4,5})"):
        x = re.search(pat, t)
        if x:
            v = int(x[1])
            v = v / 8 if v > 9000 else v
            sp = min(SPEEDS, key=lambda s_: abs(s_ - v))
            break
    kit = f"{n * each}GB ({n}x{each}GB)"
    return gen, f"{gen} {form} {kit}" + (f" {sp}" if sp else "")


GPU_JUNK = re.compile(r"for parts|not working|broken|damaged|as[- ]is|untested|read desc|artifact|"
                      r"repair|no display|no signal|bracket only|fan only|shroud|backplate|cooler only|"
                      r"heatsink only|box only|empty box|water ?block|\blot\b|\bbundle\b|\bcombo\b|"
                      r"mining rig|laptop|mxm", re.I)
MULTI_VRAM = {"RTX 3060": (8, 12), "RTX 3050": (6, 8), "RTX 2060": (6, 12), "GTX 1060": (3, 6),
              "RTX 4060 Ti": (8, 16), "RTX 5060 Ti": (8, 16), "GT 1030": (2, 4), "RX 580": (4, 8),
              "RX 570": (4, 8), "RX 480": (4, 8), "RX 470": (4, 8), "RX 5500 XT": (4, 8),
              "RX 6500 XT": (4, 8), "Arc A770": (8, 16), "GTX 1050": (2, 3)}


def extract_gpu(title):
    t = title.lower().replace("geforce", " ")
    chip = None
    m = re.search(r"\b(rtx|gtx|gt)\s*-?\s*(\d{3,4})\s*(ti|super)?\s*(super)?\b", t)
    if m and not re.search(r"\bquadro\b", t):
        chip = "NVIDIA", f"{m[1].upper()} {m[2]}" + "".join(f" {x.title() if x == 'ti' else x.upper()}" for x in (m[3], m[4]) if x)
    if not chip:
        m = re.search(r"\brtx\s*a(\d{3,4})\b", t) or re.search(r"quadro\s*(?:rtx\s*)?([kmptab]?\d{3,4})\b", t)
        if m:
            chip = "NVIDIA", ("RTX A" + m[1] if "rtx a" in m[0] else "Quadro " + m[1].upper())
    if not chip:
        m = re.search(r"\b(t400|t600|t1000)\b", t) or re.search(r"tesla\s*([a-z]\d{1,3}[a-z]?)\b", t)
        if m:
            chip = "NVIDIA", ("Tesla " if "tesla" in m[0] else "") + m[1].upper()
    if not chip:
        m = re.search(r"\brx\s*-?\s*(\d{3,4})\s*(xtx|xt|gre)?\b", t)
        if m:
            chip = "AMD", f"RX {m[1]}" + (f" {m[2].upper()}" if m[2] else "")
    if not chip:
        m = re.search(r"\bvega\s*(56|64)\b", t) or re.search(r"\barc\s*([ab]\d{3})\b", t)
        if m:
            chip = ("AMD", f"RX Vega {m[1]}") if "vega" in m[0] else ("Intel", f"Arc {m[1].upper()}")
    if not chip:
        return None
    brand, model = chip
    if model in MULTI_VRAM:
        v = re.search(r"\b(\d{1,2})\s*gb?\b", t)
        vram = int(v[1]) if v and int(v[1]) in MULTI_VRAM[model] else None
        model += f" {vram}GB" if vram else " (VRAM unknown)"
    return brand, model


def money(s):
    return float(s.replace("$", "").replace(",", ""))


def parse_file(path):
    lines = [l.strip() for l in open(path, encoding="utf-8", errors="ignore")]
    sales = []
    for i, line in enumerate(lines):
        m = re.match(r"^Sold ([A-Z][a-z]{2} \d{1,2}, \d{4})$", line)
        if not m:
            continue
        date = datetime.strptime(m[1], "%b %d, %Y")
        title = lines[i + 1].replace("Opens in a new window or tab", "").strip()
        title = re.sub(r"[\u2010-\u2015]", "-", title)
        # GPU pages add a spec line ("Dell · 4 GB") before the condition
        specs = lines[i + 2] if "·" in lines[i + 2] else ""
        condition = lines[i + 3] if specs else lines[i + 2]
        if specs:
            title = title + " [" + specs + "]"
        price = shipping = None
        fmt = "unknown"
        for j in range(i + 3, min(i + 15, len(lines))):
            l = lines[j]
            if l.startswith("Sold "):
                break
            if price is None and re.match(r"^\$[\d,]+\.\d{2}$", l):
                price = money(l)
            elif price is None and re.match(r"^\$[\d,]+\.\d{2} to ", l):
                break  # multi-variation listing, skip
            elif re.match(r"^\d+ bids?$", l):
                fmt = "auction"
            elif l == "or Best Offer":
                fmt = "best_offer"
            elif l == "Buy It Now":
                fmt = "buy_it_now"
            elif l.startswith("Free delivery"):
                shipping = 0.0
            elif re.match(r"^\+\$[\d,.]+ delivery", l):
                shipping = money(re.match(r"^\+(\$[\d,.]+)", l)[1])
            if l.startswith("Located in"):
                break
        if price is None:
            continue
        sales.append(dict(date=date, title=title, condition=condition,
                          price=price, shipping=shipping, format=fmt))
    return sales


def classify_mobo(sale):
    t = sale["title"]
    if sale["condition"] != "Pre-Owned":
        return None, "not pre-owned"
    if MOBO_JUNK.search(t):
        return None, "junk"
    if OEM_OR_LAPTOP.search(t):
        return None, "OEM/laptop/server board"
    if COMBO.search(t) or extract_models(t):
        return None, "combo (has CPU)"
    if LOT.search(t) and int(next(g for g in LOT.search(t).groups() if g)) > 1:
        return None, "lot"
    bm = extract_mobo(t)
    if not bm:
        return None, "no model found"
    return bm, "ok"


def classify_ram(sale):
    t = sale["title"]
    if sale["condition"] != "Pre-Owned":
        return None, "not pre-owned"
    if RAM_JUNK.search(t):
        return None, "junk/lot/mixed"
    bm = extract_ram(t)
    if not bm:
        return None, "no model found"
    return bm, "ok"


def classify_gpu(sale):
    t = sale["title"]
    if sale["condition"] != "Pre-Owned":
        return None, "not pre-owned"
    if GPU_JUNK.search(t):
        return None, "junk/lot"
    lead = re.match(r"^\(?(\d)\)?\s*x?\s", t)
    if (lead and int(lead[1]) > 1) or re.search(r"\b(?:two|three|four|pair)\b", t, re.I):
        return None, "multiple cards"
    bm = extract_gpu(t)
    if not bm:
        return None, "no model found"
    return bm, "ok"


def classify(sale):
    t = sale["title"]
    if sale["condition"] != "Pre-Owned":
        return None, "not pre-owned"
    if JUNK.search(t):
        return None, "junk/combo"
    lot = LOT.search(t)
    if lot and int(next(g for g in lot.groups() if g)) > 1:
        return None, "lot"
    models = extract_models(t)
    if not models:
        return None, "no model found"
    if len(models) > 1:
        return None, "multiple models"
    return models[0], "ok"


def main(paths, kind="cpu"):
    classify_fn = {"mobo": classify_mobo, "ram": classify_ram, "gpu": classify_gpu}.get(kind, classify)
    sales = []
    for p in paths:
        sales += parse_file(p)
    seen, unique = set(), []
    for s in sales:
        key = (s["title"], s["date"], s["price"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    if not unique:
        sys.exit("No sales found in the input files. Check you pasted a sold-search page.")
    cutoff = max(s["date"] for s in unique) - timedelta(days=DAYS)
    groups, reasons = {}, {}
    out = kind + "_"
    with open(data_path(out + "sales_clean.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sold_date", "brand", "model", "price", "shipping", "total", "format", "status", "title"])
        for s in unique:
            bm, why = classify_fn(s)
            if why == "ok" and s["date"] < cutoff:
                why = f"older than {DAYS} days"
            reasons[why] = reasons.get(why, 0) + 1
            total = round(s["price"] + s["shipping"], 2) if s["shipping"] is not None else None
            w.writerow([s["date"].date(), bm[0] if bm else "", bm[1] if bm else "", s["price"],
                        s["shipping"], total, s["format"], why, s["title"]])
            if why == "ok" and total is not None:
                groups.setdefault(bm, []).append((s, total))

    rows = []
    for (brand, model), items in groups.items():
        clean = [t for s, t in items if s["format"] != "best_offer"]
        use = clean if len(clean) >= MIN_SALES else [t for _, t in items]
        rows.append(dict(
            brand=brand, model=model,
            value=round(statistics.median(use), 2),
            sales=len(items),
            used_for_value=len(use),
            low=round(min(t for _, t in items), 2),
            high=round(max(t for _, t in items), 2),
            last_sold=max(s["date"] for s, _ in items).date(),
            flag="" if len(use) >= MIN_SALES else "low data",
        ))
    rows.sort(key=lambda r: (-r["sales"], r["model"]))
    if not rows:
        sys.exit(f"No {kind} sales passed the filters. Nothing written.")
    with open(data_path(out + "price_table.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    if kind == "mobo":
        chips = {}
        for (brand, model), items in groups.items():
            core = CHIPSET.match(model.split(" ", 1)[1].split()[0] if " " in model else model)
            if not core:
                core = next((CHIPSET.match(w) for w in model.split() if CHIPSET.match(w)), None)
            if core:
                chips.setdefault(core.group(1), []).extend(t for _, t in items)
        with open(data_path("mobo_chipset_table.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["chipset", "value", "sales", "low", "high"])
            for c, ts in sorted(chips.items(), key=lambda x: -len(x[1])):
                w.writerow([c, round(statistics.median(ts), 2), len(ts), min(ts), max(ts)])
        print("Wrote mobo_chipset_table.csv (fallback value by chipset when a model has low data).")

    if kind == "ram":
        caps = {}
        for (gen, model), items in groups.items():
            parts = model.split()  # DDR4 Desktop 16GB (2x8GB) 3200
            caps.setdefault(" ".join(parts[:3]), []).extend(t for _, t in items)
        with open(data_path("ram_capacity_table.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["type_and_total", "value", "sales", "low", "high"])
            for c, ts in sorted(caps.items(), key=lambda x: -len(x[1])):
                w.writerow([c, round(statistics.median(ts), 2), len(ts), min(ts), max(ts)])
        print("Wrote ram_capacity_table.csv (fallback value by DDR type + form + total GB).")

    print(f"Read {len(sales)} sales ({len(unique)} unique) from {len(paths)} file(s).")
    for why, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {n:5}  {why}")
    print(f"Wrote {out}price_table.csv ({len(rows)} models) and {out}sales_clean.csv.")


PRICE_FIELDS = ["part", "model", "value", "sales", "confidence", "kind"]
PARTS = ["cpu", "mobo", "ram", "gpu"]
FALLBACK_TABLES = {"mobo": ("mobo_chipset_table.csv", "chipset"),
                   "ram": ("ram_capacity_table.csv", "type_and_total")}


def combine():
    """Merge refreshed part tables into prices.csv. Parts without a new table keep their old rows."""
    old = []
    if os.path.exists(data_path("prices.csv")):
        with open(data_path("prices.csv"), newline="", encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    refreshed = [p for p in PARTS if os.path.exists(data_path(f"{p}_price_table.csv"))]
    if not refreshed:
        sys.exit("No *_price_table.csv files found in data/. Run a --cpu/--mobo/--ram/--gpu refresh first.")

    rows = []
    for part in PARTS:
        if part not in refreshed:
            rows += [r for r in old if r["part"] == part]
            continue
        with open(data_path(f"{part}_price_table.csv"), newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(dict(part=part, model=r["model"], value=r["value"], sales=r["sales"],
                                 confidence="low" if r["flag"] else "high", kind="exact"))
        if part in FALLBACK_TABLES and os.path.exists(data_path(FALLBACK_TABLES[part][0])):
            fname, key = FALLBACK_TABLES[part]
            with open(data_path(fname), newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    rows.append(dict(part=part, model=r[key], value=r["value"], sales=r["sales"],
                                     confidence="high" if int(r["sales"]) >= MIN_SALES else "low",
                                     kind="fallback"))
        else:
            rows += [r for r in old if r["part"] == part and r["kind"] == "fallback"]

    tmp = data_path("prices.csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_FIELDS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, data_path("prices.csv"))
    kept = [p for p in PARTS if p not in refreshed]
    print(f"Wrote prices.csv ({len(rows)} rows). Refreshed: {', '.join(refreshed)}. "
          f"Kept: {', '.join(kept) or 'none'}.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--combine"]:
        combine()
        sys.exit()
    kind = "cpu"
    if args and args[0] in ("--cpu", "--mobo", "--ram", "--gpu"):
        kind = args.pop(0)[2:]
    if not args:
        sys.exit("usage: python sold_parser.py [--cpu|--mobo|--ram|--gpu] file1.txt [file2.txt ...]")
    main(args, kind)
