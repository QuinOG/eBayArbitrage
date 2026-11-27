# Plan 004: Make the price refresh keep parts it didn't refresh, and write to data/

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat 548bb91..HEAD -- data/sold_parser.py`
> If it changed, compare the "Current state" excerpts with the live code. A mismatch is a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/002-test-baseline.md (uses its `tests/` package)
- **Category**: bug
- **Planned at**: commit `548bb91`, 2026-11-27

## Why this matters

`data/prices.csv` (1,242 rows: CPU, motherboard, RAM, GPU) is the app's only price source. `python sold_parser.py --combine` rebuilds it from per-part tables (`cpu_price_table.csv` etc.). Those tables are gitignored and none exist right now. So refreshing only CPUs and then running `--combine` replaces the whole file with CPU rows. Boards, RAM and GPUs disappear and every one of them counts as $0. Running with no tables at all writes a header-only file. The script also writes to whatever folder you run it from, so running it from the repo root creates a second `prices.csv` the app never reads.

## Current state

- `data/sold_parser.py` — two jobs: title extractors (imported by `scanner.py` and `prices.py`, do not change them) and the refresh CLI (`main()`, `combine()`, the `__main__` block).
- `prices.py:9` reads `os.path.join(os.path.dirname(__file__), "data", "prices.csv")`.
- `.gitignore` expects outputs in `data/`: `data/*_price_table.csv`, `data/*_sales_clean.csv`, `data/mobo_chipset_table.csv`, `data/ram_capacity_table.csv`, `data/raw/`.
- Output writes in `main()` use bare names relative to the current folder, and no encoding:
  ```python
  # data/sold_parser.py:337-339
  out = kind + "_"
  with open(out + "sales_clean.csv", "w", newline="") as f:
  # :368   with open(out + "price_table.csv", "w", newline="") as f:
  # :381   with open("mobo_chipset_table.csv", "w", newline="") as f:
  # :393   with open("ram_capacity_table.csv", "w", newline="") as f:
  ```
- `main()` crashes on empty input: `cutoff = max(s["date"] for s in unique) - ...` (line 335) raises `ValueError` when no sales parse, and `rows[0]` (line 369) raises `IndexError` when no rows pass.
- `combine()`:
  ```python
  # data/sold_parser.py:406-425
  def combine():
      import os
      rows = []
      for part in ["cpu", "mobo", "ram", "gpu"]:
          if os.path.exists(f"{part}_price_table.csv"):
              for r in csv.DictReader(open(f"{part}_price_table.csv")):
                  rows.append(dict(part=part, model=r["model"], value=r["value"], sales=r["sales"],
                                   confidence="low" if r["flag"] else "high", kind="exact"))
      for fname, part, key in [("mobo_chipset_table.csv", "mobo", "chipset"),
                               ("ram_capacity_table.csv", "ram", "type_and_total")]:
          if os.path.exists(fname):
              for r in csv.DictReader(open(fname)):
                  rows.append(dict(part=part, model=r[key], value=r["value"], sales=r["sales"],
                                   confidence="high" if int(r["sales"]) >= MIN_SALES else "low", kind="fallback"))
      with open("prices.csv", "w", newline="") as f:
          w = csv.DictWriter(f, fieldnames=["part", "model", "value", "sales", "confidence", "kind"])
          w.writeheader()
          w.writerows(rows)
      print(f"Wrote prices.csv ({len(rows)} rows).")
  ```
- The module docstring (lines 7-12) says to put files in `sold_data/raw/`. The gitignored folder is `data/raw/`.
- `data/README.md` documents the refresh steps.
- Tests use stdlib `unittest` in `tests/` (created by plan 002). Run with `python -B -m unittest discover -s tests -t . -v`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `python -B -m unittest discover -s tests -t . -v` | `OK` |
| Real data untouched | `git diff --stat -- data/prices.csv` | no output |

## Scope

**In scope**: `data/sold_parser.py` (only `main()`, `combine()`, module docstring, and a new `DATA_DIR` constant), `data/README.md` (refresh section only), `tests/test_sold_parser.py` (create).

**Out of scope**: every `extract_*`, `classify*`, regex constant, and `parse_file`. They feed live scoring. `data/prices.csv` itself must not change. Tests must use a temporary folder, never the real `data/`.

## Git workflow

- `git switch -c advisor/004-safe-price-refresh` then `git merge --no-edit advisor/003-confidence-reflects-listing-risk` (if missing, merge `advisor/002-test-baseline`; if that is missing too, STOP).
- One commit, e.g. `Keep unrefreshed parts when combining price tables`. Do NOT push.

## Steps

### Step 1: Add `DATA_DIR` and route every output path through it

- Add `import os` to the top imports, and below `MIN_SALES`:
  ```python
  # Every file this script writes goes next to this script (the data/ folder), wherever you run it from.
  DATA_DIR = os.path.dirname(os.path.abspath(__file__))

  def data_path(name):
      return os.path.join(DATA_DIR, name)
  ```
- In `main()`, change the four `open(...)` writes to `open(data_path(...), "w", newline="", encoding="utf-8")`.
- In `main()`, after the dedupe loop: `if not unique: sys.exit("No sales found in the input files. Check you pasted a sold-search page.")`.
- Before writing the price table: `if not rows: sys.exit(f"No {kind} sales passed the filters. Nothing written.")`.
- Remove the local `import os` inside `combine()`.

**Verify**: `python -B -c "import data.sold_parser as s; print(s.DATA_DIR)"` → ends in `eBayArbitrage\data` (or `/data`).

### Step 2: Rewrite `combine()` to merge instead of replace

Behavior:
1. Read the existing `data_path("prices.csv")` if it exists, into a list of row dicts.
2. For each part in `["cpu", "mobo", "ram", "gpu"]`: if `data_path(f"{part}_price_table.csv")` exists, that part is **refreshed**. Take its exact rows from that table, and its fallback rows from its fallback table (`mobo_chipset_table.csv` for mobo, `ram_capacity_table.csv` for ram) when that file exists. Otherwise keep the part's old fallback rows. If the part was not refreshed, keep all its old rows unchanged.
3. If no part was refreshed, `sys.exit("No *_price_table.csv files found in data/. Run a --cpu/--mobo/--ram/--gpu refresh first.")` without writing.
4. Write to `data_path("prices.csv.tmp")` with `encoding="utf-8"`, then `os.replace(tmp, data_path("prices.csv"))`.
5. Print which parts were refreshed and which were kept, e.g. `Wrote prices.csv (1250 rows). Refreshed: cpu. Kept: mobo, ram, gpu.`

Open every file with `with open(..., newline="", encoding="utf-8")`. Keep the column order `part, model, value, sales, confidence, kind`, and the same confidence rules as today.

**Verify**: `python -B -c "import data.sold_parser"` → exit 0.

### Step 3: Fix the docstring and README

- Docstring lines 7-12: `sold_data/raw/` → `data/raw/`, and add one line: `Run from any folder; output always goes to data/.`
- `data/README.md` refresh step: add `--combine keeps the rows of any part you didn't refresh.`

**Verify**: `grep -n "sold_data" data/sold_parser.py` → no output.

### Step 4: Tests in `tests/test_sold_parser.py`

Use `tempfile.TemporaryDirectory()` and `unittest.mock.patch.object(sold_parser, "DATA_DIR", tmp)`. Write small CSVs by hand with the same headers the real tables use (`model,value,sales,flag` is enough for price tables because `combine()` reads only those keys; `chipset,value,sales` and `type_and_total,value,sales` for fallback tables). Cases:

1. Existing prices.csv with one row per part + only `cpu_price_table.csv` present → result has the new CPU rows and the old mobo, ram and gpu rows unchanged.
2. Refreshing mobo with `mobo_price_table.csv` and no chipset table → old mobo fallback rows are kept, old mobo exact rows are replaced.
3. No tables → `SystemExit` raised and prices.csv byte-for-byte unchanged.
4. No prices.csv yet + all four tables → file created with rows from all four.
5. A `flag` of `"low data"` → `confidence == "low"`. A fallback with `sales` below `MIN_SALES` → `"low"`.
6. No `prices.csv.tmp` left behind after a successful run.

**Verify**: `python -B -m unittest discover -s tests -t . -v` → `OK`. `git diff --stat -- data/prices.csv` → no output.

## Done criteria

- [ ] All tests pass, including 6 new ones
- [ ] `git diff --stat -- data/prices.csv` → empty
- [ ] `git diff advisor/003-confidence-reflects-listing-risk --stat` lists only `data/sold_parser.py`, `data/README.md`, `tests/test_sold_parser.py`
- [ ] `grep -nE 'open\("(prices|mobo_chipset|ram_capacity)' data/sold_parser.py` → no output

## STOP conditions

- A change seems to need edits to an `extract_*` or `classify*` function.
- Any step would write to the real `data/` folder during tests.
- Excerpts don't match the live file.

## Maintenance notes

- If a new part type (e.g. PSU) is added, add it to the part list in `combine()` and its fallback table mapping.
- Plan deferred: carrying `last_sold` into prices.csv to show price age. It changes the CSV format that `prices.py` reads.
