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
from prices import PRICES, lookup
from data.sold_parser import (CHIPSET, MODEL_PATTERNS, MOBO_JUNK, OEM_OR_LAPTOP, extract_gpu, extract_mobo,
                              extract_ram)

PART_NAMES = {"cpu": "CPU", "mobo": "Motherboard", "ram": "RAM", "gpu": "GPU"}

# Used by the "Evaluate a listing" page: look for every part, expect a CPU, board and RAM.
MANUAL_SEARCH = {"name": "Manual", "parts": ["cpu", "mobo", "ram", "gpu"], "required": ["cpu", "mobo", "ram"]}


# --- What kind of listing it is ---

# "Lot of 3", "(LOT OF 3)", "5 pcs": several of the same item
LOT = re.compile(r"\blot\s*(?:of\s*)?(\d+)\b|\b(\d+)\s*(?:pcs|pieces)\b|\bx\s?([2-9])\b(?!\s*(?:fans?|gb|tb|mb|monitors?|displays?)\b)",
                 re.IGNORECASE)
# An empty box, a cooler or a bracket listed under a part's name. These are valued at $0, or
# "EMPTY BOX - RTX 5080" would be scored as a $1,800 card.
ACCESSORY = re.compile(
    r"\bempty\s+box\b|\b(?:retail\s+)?box\s+only\b|"
    r"\b(?:fans?|coolers?|heat\s*sinks?|shroud|backplate|bracket|shield|manual|cables?|box)\s+only\b|"
    # "GPU Fans for EVGA RTX 2060", "Water block for RTX 3080": an accessory for the part
    r"\b(?:fans?|heat\s*sinks?|shroud|backplate|water\s*block|waterblock|bracket|riser|thermal\s*pads?)\s+"
    r"(?:for|fits|compatible)\b|\breplacement\s+(?:fans?|coolers?|shroud)\b|"
    # "Wraith Prism Cooler for Ryzen 7", but not "Ryzen 7 5800X with cooler for sale"
    r"^\D{0,50}?\bcoolers?\s+(?:for|fits|compatible)\b|"
    # "i9-13900K Contact Frame for LGA1700", but "i9-9900K delidded" or "with contact frame" is still a CPU
    r"\b(?:contact\s*frame|socket\s*(?:cover|protector)s?|mount(?:ing)?\s*kit)\s+(?:for|fits|compatible)\b|"
    r"\bdelid\s*(?:tool|kit)s?\b|"
    r"\b(?:support|sag|anti[- ]sag)\s+(?:bracket|brace|stand)\b|\bdummy\b|\bdisplay\s+model\b", re.IGNORECASE)
# A combo or bundle listed in a single-part category, like a CPU with a board in the CPU category.
BUNDLE = re.compile(r"\b(?:combo|bundle)\b|(?:w/|with|\+|&|\band\b)\s*(?:an?\s+)?(?:\w+\s+){0,2}(?:motherboard|mobo)\b",
                    re.IGNORECASE)
# "NO RAM", "w/o GPU", "without CPU": parts the title says aren't included
TITLE_NO = re.compile(r"\b(?:no|w/o|without|minus)\s+(?:the\s+)?(cpu|processor|ram|memory|gpu|graphics\s*card|"
                      r"video\s*card|motherboard|mobo)\b(?!\s*(?:cooler|fan|heatsink|heat sink))",
                      re.IGNORECASE)  # "no CPU cooler" is about the cooler
TITLE_NO_PART = {"cpu": "cpu", "processor": "cpu", "ram": "ram", "memory": "ram", "gpu": "gpu", "graphics": "gpu",
                 "video": "gpu", "motherboard": "mobo", "mobo": "mobo"}
# Prebuilt PCs from big brands use their own boards, which aren't sold or priced on their own.
PREBUILT = re.compile(OEM_OR_LAPTOP.pattern + r"|apple|imac|mac\s*mini|alienware|raspberry|mini\s*pc|\btiny\b|"
                      r"\bnuc\b|thin\s*client|all[- ]in[- ]one|beelink|minisforum|gmktec|geekom|zbox", re.IGNORECASE)
# Small PCs and laptops take laptop-size RAM (SODIMM).
SMALL_PC = re.compile(r"\bmini\b(?![\s-]*(?:itx|tower|atx))|\btiny\b|\bmicro\b(?![\s-]*atx)|\busff\b|\bmff\b|\bnuc\b|"
                      r"all[- ]in[- ]one|\bimac\b|mac\s*mini|laptop|notebook|chromebox|thin\s*client", re.IGNORECASE)
MOBILE_CPU = re.compile(r"\d(?:U|H|HQ|HS|HX|Y)$")  # "Core i5-8265U", "Ryzen 5 5600H"


# --- Cleaning text before the sold_parser.py extractors read it ---

# Desktop titles mix many parts, which confuses the RAM and board extractors.
# These remove text that belongs to other parts before we look for RAM or a board.
GPU_MEMORY = re.compile(r"(\b(?:rtx|gtx|gt|rx|arc)\s*-?\s*[a-z]?\d{3,4}(?:\s*(?:ti|super|xtx|xt|gre))*)"
                        r"\s*(?:\d|1[0-2]|16|20|24|32(?=\s*gb\s*gddr))\s*gb\b", re.IGNORECASE)
# "8GB nVIDIA RTX 3070": the GPU's memory written before its name
GPU_MEMORY_BEFORE = re.compile(r"\b\d{1,2}\s*gb\s+(?=(?:(?:nvidia|amd|geforce|radeon)\s+)*(?:rtx|gtx|gt|rx|arc)\b)",
                               re.IGNORECASE)
LISTING_WORDS = re.compile(r"\b(?:combo|bundle|kit|set|package|deal)\b", re.IGNORECASE)
STORAGE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:tb|gb)(?:\s*(?:nvme|ssd|hdd|m\.2|sata))+\b|\b\d+(?:\.\d+)?\s*tb\b",
                     re.IGNORECASE)
# "8GB GPU", "12GB GDDR6", "1TB of storage": sizes that belong to another part.
OTHER_SIZES = re.compile(r"\b\d+(?:\.\d+)?\s*(?:gb|tb)\s+(?:of\s+)?(?:gpu|graphics|video|vram|gddr\d\w*|"
                         r"storage|ssd|hdd|nvme|m\.2|hard drive|drive)\b", re.IGNORECASE)
GPU_NAME = re.compile(r"\b(?:rtx|gtx|gt|rx)\s*-?\s*\d{3,4}(?:\s*(?:ti|super|xtx|xt|gre))*\b", re.IGNORECASE)
PART_WORDS = re.compile(r"\b(?:cpu|gpu|ram|mb|memory|processor|parts?|graphics|\d+\s*gb)\b", re.IGNORECASE)
CPU_NAME = re.compile(r"\bryzen\s*[3579]?\s*(?:pro\s*)?\d{4}\w*|\bi[3579][\s-]?\d{3,5}[a-z]{0,3}\b|"
                      r"\bcore\s*ultra\s*[579]\s*\d{3}\w*", re.IGNORECASE)

# "Ryzen 2700X": the tier (3, 5, 7, 9) follows from the model number's second digit.
# "Ryzen 7000" (a series, second digit 0) is left alone.
RYZEN_NO_TIER = re.compile(r"\bryzen\s*(?=(\d)([1-9])\d{2}(?:x3d|xt|x|g|ge|f)?\b)", re.IGNORECASE)
RYZEN_TIER = {"1": "3", "2": "3", "3": "3", "4": "5", "5": "5", "6": "5", "7": "7", "8": "7", "9": "9"}
# "Ryzen 9 5000 Series": a CPU family, not a model
CPU_SERIES = re.compile(r"\d000$")
# "1070 Ti 8gb", "2060 graphics": an NVIDIA card named without RTX/GTX
BARE_GPU = re.compile(r"(?<![\w-])(?<!i[3579]\s)(?<!tx\s)((?:10[5-8]0|16[56]0|20[6-8]0|30[5-9]0|40[6-9]0|50[6-9]0)"
                      r"(?:\s*(?:ti|super))*)(?=\s*(?:\d{1,2}\s*gb|gpu|graphics|video))", re.IGNORECASE)
# Older Radeon cards extract_gpu doesn't know. There's no price data for them, but naming them
# shows "no price data, type a value" instead of "not identified".
OLD_RADEON = re.compile(r"\b(?:(r[579])\s*-?\s*(\d{3})(x?)|hd\s*-?\s*(\d{4}))\b", re.IGNORECASE)

# RAM kit layouts, rewritten the way extract_ram reads them ("2x8GB").
NUMBER_WORDS = re.compile(r"\b(two|three|four|six|eight)\b(?=\s*(?:\(?\d+\s*gb|x\b|sticks?|modules?|dimms?))", re.I)
NUMBERS = {"two": "2", "three": "3", "four": "4", "six": "6", "eight": "8"}
# "6 identical modules of 2GB", "2 sticks 8gb", "4 x DIMMs @ 8GB"
STICKS_OF = re.compile(r"\b([1-8])\s*(?:x\s*)?(?:(?:identical|matching|ram|memory)\s+)?(?:modules?|sticks?|dimms?|pieces|pcs)\s*(?:of\s*|x\s*|@\s*)?(\d{1,3})\s*gb\b",
                       re.IGNORECASE)
# "(2) 8GB", "2 8GB sticks"
COUNT_SIZE = re.compile(r"(?:\(([1-8])\)\s*x?\s*(\d{1,3})\s*gb\b|\b([1-8])\s+(\d{1,3})\s*gb(?=\s*(?:ddr\d\s*)?(?:sticks?|modules?|dimms?)\b))",
                        re.IGNORECASE)
# "16GB (2 sticks)", "32GB 4 dimms"
SIZE_IN = re.compile(r"\b(\d{1,3})\s*gb\s*(ddr\d\s*)?\(?\s*([1-8])\s*(?:x\s*)?(?:sticks?|modules?|dimms?)\)?", re.IGNORECASE)
# The kit layout is written as one stick: "1x16GB", "16GB x1", "single stick"
ONE_STICK = re.compile(r"\b1\s*x\s*\d+\s*gb|\d+\s*gb\s*x\s*1\b|single\s*(?:stick|module|dimm|channel)", re.IGNORECASE)
LAPTOP_RAM = re.compile(r"so-?dimm|laptop|notebook", re.IGNORECASE)


def split_size(m):
    total, ddr, n = int(m[1]), m[2] or "", int(m[3])
    return f"{total}GB {ddr}({n}x{total // n}GB)" if total % n == 0 and n > 1 else m[0]


def normalize_ram_layout(text):
    """ "6 modules of 2GB" -> "6x2GB", "16GB (2 sticks)" -> "16GB (2x8GB)" """
    text = NUMBER_WORDS.sub(lambda m: NUMBERS[m[1].lower()], text)
    text = re.sub(r"(?<=[\dbB])\s*\*\s*(?=\d)", "x", text)  # "8GB*2" -> "8GBx2"
    text = STICKS_OF.sub(lambda m: f"{m[1]}x{m[2]}GB", text)
    text = COUNT_SIZE.sub(lambda m: f"{m[1] or m[3]}x{m[2] or m[4]}GB", text)
    return SIZE_IN.sub(split_size, text)


def name_bare_gpu(m):
    return ("RTX " if int(m[1][:4]) >= 2000 else "GTX ") + m[1]


def clean_title(part, title):
    if part == "cpu":
        title = RYZEN_NO_TIER.sub(lambda m: f"Ryzen {RYZEN_TIER[m[2]]} ", title)  # "Ryzen 2700X" -> "Ryzen 7 2700X"
        title = re.sub(r"(\d{4})\s*[vV](\d)\b", r"\1 v\2", title)  # "E5-2660V2" -> "E5-2660 v2"
    if part in ("gpu", "ram", "mobo"):
        title = BARE_GPU.sub(name_bare_gpu, title)  # "1070 Ti 8gb" -> "GTX 1070 Ti 8gb"
    if part in ("ram", "mobo"):
        title = GPU_MEMORY.sub(r"\1", title)   # "RTX 3070 8GB" -> "RTX 3070"
        title = GPU_MEMORY_BEFORE.sub(" ", title)  # "8GB RTX 3070" -> "RTX 3070"
        title = STORAGE.sub(" ", title)        # "1TB", "512GB SSD" -> removed
        title = OTHER_SIZES.sub(" ", title)    # "8GB GPU", "12GB GDDR6" -> removed
    if part == "ram":
        title = re.sub(r"\blpddr\d\w*", " ", title, flags=re.IGNORECASE)  # soldered to the board, can't be resold
        title = re.sub(r"\b(pc[345]l?)\s+-\s*(?=\d)", r"\1-", title, flags=re.IGNORECASE)  # "PC3 - 10600" -> "PC3-10600"
        title = normalize_ram_layout(title)
    if part == "mobo":
        title = LISTING_WORDS.sub(" ", title)  # "B450M-A Combo" -> "B450M-A"
        # Other parts' names confuse the board name: "Ryzen 3 3100, Gigabyte B450M" was read as
        # "Gigabyte 3 3100 B450M", and "MSI GTX 970" as an MSI 970 board.
        # "Motherboard,Ryzen 9" and "Gaming+CPU" -> separate words
        title = re.sub(r"\+(?=[A-Za-z]{2})", " + ", title).replace(",", " , ")
        title = CPU_NAME.sub(" | ", GPU_NAME.sub(" | ", title))
        title = PART_WORDS.sub(" | ", title)  # "RAM 16GB, GPU. Gigabyte B450M" was read as "Gigabyte GPU B450M"
    return title


# --- RAM listed without its DDR type ---

# "16GB G.Skill Ripjaws" gets the type from its product line, its speed, or the rest of the
# listing (item specifics, board, CPU).
RAM_HINT = re.compile(r"\bram\b|memory|\bdimms?\b|\bsticks?\b|g\.?\s?skill|ripjaws?|trident|corsair|vengeance|"
                      r"dominator|kingston|hyperx|fury|crucial|ballistix|patriot|viper|t-?force|teamgroup|"
                      r"\badata\b|\bxpg\b|\bpny\b|\bxms\d?\b|sniper|aegis|\bflare\b", re.IGNORECASE)
NOT_RAM = re.compile(r"\bgddr|\bvram\b|\bgpu\b|graphics|video card|\bssd\b|\bnvme\b|\bhdd\b|storage|cache|lpddr",
                     re.IGNORECASE)
RAM_LINES = [
    ("DDR5", re.compile(r"ripjaws\s*[sm]5|trident\s*z5|flare\s*x5|fury\s*beast\s*ddr5|vengeance\s*(?:rgb\s*)?ddr5", re.I)),
    ("DDR4", re.compile(r"ripjaws\s*v\b|ripjaws\s*4|trident\s*z\b(?!5)|trident\s*z\s*(?:neo|rgb|royal)|"
                        r"vengeance\s*lpx|ballistix|flare\s*x\b|aegis|sniper\s*x|xpg\s*spectrix\s*d[456]0\b", re.I)),
    ("DDR3", re.compile(r"\bxms\s*3\b|ripjaws\s*x\b", re.I)),
]
DDR = re.compile(r"\bddr\s?[2345]|\bpc[2345]l?-", re.IGNORECASE)
EITHER = "DDR4|DDR5"  # boards and CPUs that came in both versions


def board_generation(model):
    """DDR type a board takes, from its chipset. EITHER for Intel 600 and 700 series, None if unknown."""
    upper = model.upper()
    if re.search(r"\bDDR4\b|\bD4\b", upper):
        return "DDR4"
    if re.search(r"\bDDR5\b|\bD5\b", upper):
        return "DDR5"
    for word in upper.replace("(", " ").replace("-", " ").split():
        m = CHIPSET.match(word.strip(",.;:"))
        if not m:
            continue
        chip = m.group(1)
        if re.match(r"A620|B650|X670|X870|B850|B840|Z890|B860|H810", chip):
            return "DDR5"
        if re.match(r"[HBZQ][67]\d0", chip):
            return EITHER  # Intel 600 and 700 series boards came in DDR4 and DDR5 versions
        if re.match(r"H61|H67|P67|Z68|B75|H77|Z77|Q77|H81|B85|H87|Z87|Q87|H97|Z97|X79|970|990", chip):
            return "DDR3"
        return "DDR4"  # Intel 100-500 series, X99, X299, AM4
    return None


def cpu_generation(model):
    """DDR type a CPU takes. EITHER for Intel 12th to 14th gen, None if unknown."""
    m = re.match(r"Ryzen \d (\d)\d{3}", model)
    if m:
        return "DDR5" if m[1] in "6789" else "DDR4"
    m = re.match(r"Core i\d-(\d+)\d{3}", model)
    if m:
        gen = int(m[1])
        return "DDR3" if 2 <= gen <= 4 else "DDR4" if 6 <= gen <= 11 else EITHER if 12 <= gen <= 14 else None
    if model.startswith("Core Ultra"):
        return "DDR5"
    return None


def ram_generation(listing, cpu=None, mobo=None):
    """(DDR type, where it came from) to assume for RAM listed without one, or (None, None)."""
    for line in listing.get("specifics") or []:
        m = re.match(r"memory type:\s*(ddr[345])", line, re.IGNORECASE)
        if m:
            return m[1].upper(), "the item specifics"
    board_gen = board_generation(mobo) if mobo else None
    cpu_gen = cpu_generation(cpu) if cpu else None
    if board_gen and not (board_gen == EITHER and cpu_gen and cpu_gen != EITHER):
        return board_gen, f"the board ({mobo})"
    if cpu_gen:
        return cpu_gen, f"the CPU ({cpu})"
    return None, None


def add_ram_generation(text, gen, loose=False):
    """
    Adds a DDR type to RAM text that has none: "16GB G.Skill Ripjaws" -> "16GB G.Skill Ripjaws DDR4".
    loose: the text is a PC's title, where a bare "16GB" is the RAM even without the word "RAM".
    """
    if DDR.search(text) or not re.search(r"\d\s*gb\b", text, re.IGNORECASE):
        return text
    if NOT_RAM.search(text) and not loose:
        return text
    if not (loose or RAM_HINT.search(text)):
        return text
    line_gen = next((g for g, pat in RAM_LINES if pat.search(text)), None)
    if line_gen or gen:
        return f"{text} {line_gen or gen}"
    speed = re.search(r"\b(\d{4})\s*(?:mhz|mt/?s)\b", text, re.IGNORECASE)
    if speed and 4800 <= int(speed[1]) <= 8400:
        return f"{text} DDR5"
    if speed and 2400 <= int(speed[1]) <= 4400:
        return f"{text} DDR4"
    return text


# --- Reading the item specifics and description ---

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

# Descriptions often come as one long paragraph. Each sentence is checked on its own, so one
# "not included" or "supports" doesn't throw away the rest of the paragraph.
SENTENCE_END = re.compile(r"(?<=[A-Za-z0-9)\]])[.!?]+\s+(?=[A-Z0-9*(])|\s*[;•|]\s*|\s+-\s+(?=[A-Z])")


def split_sentences(lines):
    return [s.strip() for line in lines for s in SENTENCE_END.split(line) if s and s.strip()]


def detail_lines(listing, key):
    """The lines of the item specifics or description that can describe what's for sale."""
    lines = []
    source = listing.get(key) or []
    for line in (split_sentences(source) if key == "description" else source):
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
    ("Storage", re.compile(r"\b\d+(?:\.\d+)?\s?(?:tb|gb)\b(?:\s+(?!\d+\s?(?:gb|tb)\b|ddr\d|ram\b)[\w-]+){0,4}?\s*(?:nvme|ssd|hdd|m\.2|sata|hard drive)"
                           r"(?:\s*(?:ssd|nvme))?\b|^\s*(?:storage|ssd|hdd|hard drive)\s*:", re.I)),
    ("Case", re.compile(r"\b(?:pc|computer|atx|matx|itx|mid[- ]?tower|full[- ]?tower)\s*case\b|\bmid[- ]?tower\b|\b(?:w/|with)\s*case\b", re.I)),
]

DETAIL_SOURCES = (("specifics", "item specifics"), ("description", "description"))
PRICE_RANK = {"exact": 2, "fallback": 1}


def rank(price):
    return PRICE_RANK.get(price["kind"], 0) if price else 0


# --- Finding one part ---

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


def find_ram(text, hints):
    """The prices.csv name for the RAM in text, or None. See find_part for hints."""
    gens = (hints.get("gen") or "").split("|")
    best = None
    for gen in gens:  # "DDR4|DDR5": try both and keep the cheaper, so the value is never overstated
        t = add_ram_generation(text, gen or None, hints.get("loose"))
        if hints.get("sodimm") and not LAPTOP_RAM.search(t):
            t += " SODIMM"
        found = extract_ram(t)
        if not found:
            continue
        model = found[1]
        # "16GB DDR4" doesn't say if it's one stick or two. extract_ram reads it as 1x16GB, which sells
        # for less than 2x8GB. Price it as the average 16GB DDR4 kit instead, when there's data for that.
        if "(1x" in model and not ONE_STICK.search(t):
            average = " ".join(model.split()[:3])
            if ("ram", average) in PRICES:
                model = average
        price = lookup("ram", model)
        if best is None or (price and (best[1] is None or price["value"] < best[1]["value"])):
            best = (model, price)
    return best[0] if best else None


def find_part(part, text, allow_chipset=True, ram=None):
    """
    Return (model, problem). model is the prices.csv name, or None if it couldn't be identified.
    ram: hints for reading RAM.
        gen     the DDR type to assume when none is written ("DDR4", or "DDR4|DDR5" when either fits)
        sodimm  True when the RAM is laptop size (mini PCs, laptops)
        loose   True for a PC's title, where a bare "16GB" is the RAM
    """
    text = clean_title(part, text)
    if part == "cpu":
        models = [m for m in cpu_models(text) if not CPU_SERIES.search(m)]
        if len(models) > 1:
            return None, f"several CPU models ({', '.join(models)})"
        return (models[0], None) if models else (None, None)
    if part == "ram":
        return find_ram(text, ram or {}), None
    extract = {"mobo": extract_mobo, "gpu": extract_gpu}[part]
    found = extract(text)
    if found:
        return found[1], None
    if part == "mobo" and allow_chipset:
        return mobo_by_chipset(text), None
    if part == "gpu":
        old = OLD_RADEON.search(text)
        if old and re.search(r"radeon|\bamd\b|\bati\b|graphics|video", text, re.IGNORECASE):
            name = f"{old[1].upper()} {old[2]}{old[3].upper()}" if old[1] else f"HD {old[4]}"
            return f"Radeon {name}", None
    return None, None


def same_part(part, a, b):
    """True when two names found for a part are the same item described with more or less detail."""
    if a.startswith(b) or b.startswith(a):
        return True
    if part == "ram":  # "DDR4 Desktop 16GB (1x16GB)" and "DDR4 Desktop 16GB (2x8GB) 3200": same type and size
        return a.split()[:3] == b.split()[:3]
    if part == "gpu":  # "RTX 3060 (VRAM unknown)" and "RTX 3060 12GB"
        return a.replace(" (VRAM unknown)", "") in b or b.replace(" (VRAM unknown)", "") in a
    return False


def best_model(part, models):
    """The most precise of several names for one part, or None if they name different parts."""
    if any(not same_part(part, a, b) for a in models for b in models):
        return None
    return max(models, key=lambda m: (rank(lookup(part, m)), "unknown" not in m, len(m)))


def find_in_details(part, listing, ram=None):
    """
    Look for a part in the item specifics, then the description, line by line.
    Returns (model, problem, source). If a source names several different models, none is picked.
    """
    sources = [(label, detail_lines(listing, key)) for key, label in DETAIL_SOURCES]
    for allow_chipset in (False, True):  # a full board name anywhere beats a bare chipset
        found = {}  # model -> where it was first seen
        for label, lines in sources:
            for line in lines:
                model, line_problem = find_part(part, line, allow_chipset, ram)
                if line_problem:
                    return None, f"the {label} has {line_problem}", label
                if model:
                    found.setdefault(model, label)
        if not found:
            continue
        # The specifics and description agree: take the most precise name from either.
        model = best_model(part, list(found))
        if model:
            return model, None, found[model]
        # They disagree: the first source that agrees with itself wins.
        for label, _ in sources:
            models = [m for m, src in found.items() if src == label]
            if models:
                model = best_model(part, models)
                if model:
                    return model, None, label
                return None, f"the {label} names several ({', '.join(models[:4])})", label
    return None, None, None


def find_extras(listing):
    """Coolers, PSUs, storage and cases. First match per kind, title first."""
    sources = [("title", [listing["title"]])] + [
        (label, detail_lines(listing, key)) for key, label in DETAIL_SOURCES]
    extras = []
    for name, pattern in EXTRAS:
        for label, lines in sources:
            model = None
            for line in lines:
                m = pattern.search(line)
                if not m:
                    continue
                # "Cooler: Noctua NH-D15" -> use the part after the colon as the name
                label_part, colon, value = line.partition(":")
                if colon and m.start() < len(label_part):
                    if not value.strip():
                        continue  # a "Storage:" heading with the details on the next line
                    model = value.strip()
                else:
                    model = m[0].strip()
                break
            if model:
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


# --- Scoring a listing ---

def listing_kind(title, search):
    """What to look for in this listing: (parts, required, quantity, excluded, flags)."""
    flags = []
    parts, required = list(search["parts"]), list(search["required"])
    if len(parts) == 1 and BUNDLE.search(title):
        parts = list(PART_NAMES)
        flags.append(f"Bundle in the {search['name']} search: every part in it was priced.")
    lot = LOT.search(title)
    quantity = int(next(g for g in lot.groups() if g)) if lot else 1
    # "Lot of 2 i5-8500 + MSI B450" doesn't say what the 2 applies to, so only a lot of one kind of part counts.
    if quantity > 1 and sum(1 for p in parts if find_part(p, title)[0]) > 1:
        flags.append(f"Title says {quantity} pieces but names several parts. Values not multiplied, check the count.")
        quantity = 1
    if quantity > 1:
        flags.append(f"Lot of {quantity}: each part's value multiplied by {quantity}. Check every unit matches the title.")
    else:
        quantity = 1
    named = [TITLE_NO_PART[m[1].split()[0].lower()] for m in TITLE_NO.finditer(title)]
    named += [part for part in parts if TITLE_EXCLUDES[part].search(title)]  # "RAM not included"
    excluded = []
    for part in dict.fromkeys(named):
        if part in parts:
            parts.remove(part)
            required = [p for p in required if p != part]
            excluded.append({"part": part, "name": PART_NAMES[part]})
            flags.append(f"Title says the {PART_NAMES[part]} isn't included. Counted as $0.")
    return parts, required, quantity, excluded, flags


def score_listing(listing, search):
    """
    listing: dict with title, price, shipping (None if unknown) and anything else to pass through.
             Optional: specifics and description (lists of text lines), searched for parts the title doesn't name.
    search:  one entry from config.SEARCHES.
    Returns the listing with parts, extras, parts_value, tax, profit, confidence and flags added.
    """
    title = listing["title"]
    if ACCESSORY.search(title):
        flags = ["Looks like an accessory or an empty box, not the part itself. Not valued."]
        return with_totals(listing, search, [], [], [], flags)

    has_details = bool(listing.get("specifics") or listing.get("description"))
    wanted, required, quantity, missing, flags = listing_kind(title, search)  # missing starts with excluded parts
    risky = quantity > 1  # True when a flag means the profit is a guess
    prebuilt = bool(PREBUILT.search(title))
    small = bool(SMALL_PC.search(title))
    parts = []
    from_details = []  # parts found in the item specifics or description, not the title

    found = {}  # part -> model, so RAM can take its DDR type from the CPU and board
    for part in wanted:
        name = PART_NAMES[part]
        ram_gen, gen_source, hints = None, None, None
        if part == "ram":
            ram_gen, gen_source = ram_generation(listing, found.get("cpu"), found.get("mobo"))
            mobile = bool(found.get("cpu") and MOBILE_CPU.search(found["cpu"]))
            hints = {"gen": ram_gen, "sodimm": small or mobile}
        title_hints = {**hints, "loose": "cpu" in found} if hints else None
        model, problem = find_part(part, title, ram=title_hints)
        price = lookup(part, model) if model else None
        source = "title"
        # Title first. Use the item specifics or description when the title doesn't name the part,
        # or when they name it precisely enough to get a better price (exact instead of a chipset average).
        vague = model is not None and "unknown" in model  # "RTX 2060 (VRAM unknown)"
        if has_details and not problem and (rank(price) < 2 or vague):
            d_model, d_problem, d_source = find_in_details(part, listing, hints)
            d_price = lookup(part, d_model) if d_model else None
            if model is None and d_problem:
                problem = d_problem
            elif d_model and (model is None or rank(d_price) > rank(price)
                              or (vague and "unknown" not in d_model and rank(d_price) == rank(price))):
                model, price, source = d_model, d_price, d_source

        if problem:
            flags.append(f"{name}: {problem}. Counted as $0.")
        if model is None:
            if part in required or problem:
                missing.append({"part": part, "name": name})
            if part in required and not problem:
                if part == "mobo" and prebuilt:
                    flags.append("Prebuilt PC: its board can't be priced on its own. Counted as $0.")
                else:
                    where = "the listing" if has_details else "title"
                    flags.append(f"{name} not identified in {where}. Counted as $0.")
            continue

        found[part] = model
        row = make_part(part, model, price, quantity, source)
        parts.append(row)
        if part == "ram" and ram_gen:
            plain_hints = {**hints, "gen": None}
            plain = (find_part(part, title, ram={**plain_hints, "loose": "cpu" in found})[0] if source == "title"
                     else find_in_details(part, listing, plain_hints)[0])
            if plain != model:
                gen = model.split()[0]
                if ram_gen == EITHER:
                    row["confidence"] = "low"
                    flags.append(f"RAM type not stated, and {gen_source} takes DDR4 or DDR5. "
                                 f"Priced as the cheaper, {gen}.")
                else:
                    flags.append(f"RAM type not stated with the RAM. {gen} taken from {gen_source}.")
        if price is None:
            flags.append(f"No price data for {name} '{model}'. Counted as $0.")
        elif part == "mobo" and price["kind"] == "fallback":
            risky = True
            if model == price["priced_as"]:
                flags.append(f"Board brand and model unknown, priced as an average {model} board.")
            else:
                flags.append(f"No sold data for '{model}', priced as an average {price['priced_as']} board.")
        if source != "title":
            from_details.append(name)
        if "VRAM unknown" in model:
            flags.append("GPU memory size not in the listing. Check it.")

    if from_details:
        flags.append(f"Found outside the title: {', '.join(from_details)}. Check they're included.")

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
    return with_totals(listing, search, parts, missing, extras, flags, risky)


def with_totals(listing, search, parts, missing, extras, flags, risky=False):
    """Adds the tax, parts value and profit to a scored listing. risky: a flag means the profit is a guess."""
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
    from concurrent.futures import ThreadPoolExecutor
    from ebay_api import get_details, save_details_cache, search_listings  # here so tests run without API keys

    scored, errors = [], []
    for search in config.SEARCHES:
        try:
            listings = search_listings(search["category_id"])
        except Exception as e:
            errors.append(f"{search['name']} search failed: {e}")
            continue
        if search.get("details"):
            # Read the description too, 8 listings at a time. Titles often leave out the RAM or GPU.
            with ThreadPoolExecutor(max_workers=8) as pool:
                details = pool.map(lambda l: get_details(l["item_id"]) if l.get("item_id") else {}, listings)
                listings = [{**l, **d} for l, d in zip(listings, details)]
        scored += [score_listing(l, search) for l in listings]
    save_details_cache()
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
