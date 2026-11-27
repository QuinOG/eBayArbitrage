# Price data

## prices.csv
Sold value for every part, built from eBay sold-search pages (used items, last 90 days).

| Column | Meaning |
| --- | --- |
| part | cpu, mobo, ram or gpu |
| model | Model name, e.g. `Core i7-8700`, `MSI Z390 GAMING PLUS`, `DDR4 Desktop 16GB (2x8GB) 3200`, `RTX 3060 12GB` |
| value | Median sold price including shipping (USD) |
| sales | Number of sales behind the value |
| confidence | `high` = 3+ sales, `low` = fewer |
| kind | `exact` = this exact model; `fallback` = backup price by chipset (boards, e.g. `B550`) or by type + size (RAM, e.g. `DDR4 Desktop 16GB`) |

Lookup order: exact model, then fallback, then "no data" (count as $0 and flag it).

## sold_parser.py
Two jobs:
1. **Refreshing prices.** Copy an eBay sold-search page (Ctrl+A, Ctrl+C), paste into a .txt, then run
   `python sold_parser.py --cpu|--mobo|--ram|--gpu file.txt`. It writes per-part tables; then `python sold_parser.py --combine` merges them into prices.csv.
2. **Reading listing titles.** `extract_models` (CPU), `extract_mobo`, `extract_ram` and `extract_gpu` turn a title into
   the exact model names used in prices.csv. The scanner should import these, not rewrite them, so names always match.

Refresh every 1–2 weeks.

## Faster refresh: collect_sold.py
From the repo root, run `python collect_sold.py` (or `python collect_sold.py gpu ram` for some parts).
It opens each sold-search page in your browser (used, newest first, 240 per page). Press Ctrl+A, then Ctrl+C,
and it saves the page to `data/raw/<part>/`, opens the next one, and moves on once it reaches sales older than
30 days (`--days` changes that). Then it runs this parser on every saved page and rebuilds prices.csv, keeping a backup.
A part with no saved pages keeps its old rows. `python collect_sold.py --build-only` rebuilds without collecting.
