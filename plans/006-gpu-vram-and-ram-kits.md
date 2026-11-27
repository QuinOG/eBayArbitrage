# Plan 006: Read GPU memory and RAM kit layout from the right numbers in multi-part titles

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat 86f71de..HEAD -- data/sold_parser.py`
> If it changed, compare the "Current state" excerpts with the live code. A mismatch is a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED (`data/sold_parser.py` extractors also build the price tables on the next refresh)
- **Depends on**: plans/005-title-exclusions.md (branch chain and tests)
- **Category**: bug
- **Planned at**: commit `86f71de` (branch `advisor/005-title-exclusions`), 2026-11-27

## Why this matters

Desktop titles name several parts, and two extractors read the wrong numbers.
- `extract_gpu` takes the FIRST "NN GB" anywhere in the title as GPU memory. `"Gaming PC i5-9600K 8GB DDR4 RTX 3060 12GB"` is priced as an RTX 3060 **8GB** (about $100 less than 12GB). `"... 16GB DDR4 RTX 3060 12GB"` becomes `RTX 3060 (VRAM unknown)` at $0.
- `extract_ram` reads `"5600X 16GB"` as a kit of **5600** sticks of 16GB, rejects it, and finds no RAM. `"Gaming PC Ryzen 5 5600X 16GB DDR4 RTX 3060 12GB"` loses $55 of RAM.

## Current state

- `data/sold_parser.py` — title extractors shared by live scoring (`scanner.py`) and the price refresh (`main()`).
- GPU memory lookup, at the end of `extract_gpu` (around lines 217-223):
  ```python
  if not chip:
      return None
  brand, model = chip
  if model in MULTI_VRAM:
      v = re.search(r"\b(\d{1,2})\s*gb?\b", t)
      vram = int(v[1]) if v and int(v[1]) in MULTI_VRAM[model] else None
      model += f" {vram}GB" if vram else " (VRAM unknown)"
  return brand, model
  ```
  `chip` is set in one of five `if not chip:` branches, each from its own `m = re.search(...)`. Only models in `MULTI_VRAM` (e.g. `"RTX 3060": (8, 12)`) get a memory suffix.
- RAM kit lookup in `extract_ram` (around lines 152-156):
  ```python
  m = (re.search(r"(\d+)\s*gb\s*\(\s*(\d+)\s*x\s*(\d+)\s*gb", t)
       or re.search(r"\(\s*(\d+)\s*x\s*(\d+)\s*gb", t)
       or re.search(r"\b(\d+)\s*x\s*(\d+)\s*gb", t))
  ```
  The third pattern matches `"5600x 16gb"` with a stick count of 5600. Later `if each not in (...) or not 1 <= n <= 8: return None` rejects it, so the code never tries the plain `caps` path.
- Current results (run from the repo root):
  | Title | `extract_gpu` | `extract_ram(scanner.clean_title("ram", t))` |
  |---|---|---|
  | `Gaming PC Ryzen 5 5600X 16GB DDR4 RTX 3060 12GB` | `RTX 3060 (VRAM unknown)` | `None` |
  | `Gaming PC i5-9600K 8GB DDR4 RTX 3060 12GB` | `RTX 3060 8GB` | `DDR4 Desktop 8GB (1x8GB)` |
  | `MSI RTX 3060 Ventus 2X 12G OC` | `RTX 3060 12GB` | n/a |
  | `RTX 3060 12GB` | `RTX 3060 12GB` | n/a |
- Regression baseline: each exact `prices.csv` model run back through its extractor returns itself 156 of 156 times for GPU and 31 of 242 for RAM. (RAM model names aren't title-shaped, so 31 is normal.) Neither number may drop.
- Tests: stdlib `unittest` in `tests/`. Run `python -B -m unittest discover -s tests -t . -v`. Extractor tests need no price fixture.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `python -B -m unittest discover -s tests -t . -v` | `OK` |
| Baseline | see Step 4 | `gpu 156 156` and `ram 242 >=31` |

## Scope

**In scope**: `data/sold_parser.py` (`extract_gpu` memory lookup, `extract_ram` kit regex only), `tests/test_extractors.py` (create).

**Out of scope**: the other extractors, `MULTI_VRAM` values, `scanner.clean_title` (it strips GPU memory before the RAM search and stays as is), `data/prices.csv`.

## Git workflow

- `git switch -c advisor/006-gpu-vram-and-ram-kits` then `git merge --no-edit advisor/005-title-exclusions`. If that branch is missing, STOP.
- One commit, e.g. `Read GPU memory next to the GPU model and ignore CPU names in RAM kits`. Do NOT push.

## Steps

### Step 1: Failing tests in `tests/test_extractors.py`

```python
import unittest
import scanner
from data.sold_parser import extract_gpu, extract_ram

def ram(title):
    found = extract_ram(scanner.clean_title("ram", title))
    return found[1] if found else None
```

Cases:
1. `extract_gpu("Gaming PC Ryzen 5 5600X 16GB DDR4 RTX 3060 12GB")[1] == "RTX 3060 12GB"`
2. `extract_gpu("Gaming PC i5-9600K 8GB DDR4 RTX 3060 12GB")[1] == "RTX 3060 12GB"`
3. `extract_gpu("MSI RTX 3060 Ventus 2X 12G OC")[1] == "RTX 3060 12GB"` (control)
4. `extract_gpu("12GB RTX 3060 Gaming OC")[1] == "RTX 3060 12GB"` (memory written before the model; control, already passes and must keep passing)
5. `extract_gpu("RTX 3060 graphics card")[1] == "RTX 3060 (VRAM unknown)"` (control)
6. `extract_gpu("Gaming PC 16GB RAM RTX 3060")[1] == "RTX 3060 (VRAM unknown)"` (16 isn't a 3060 size, so nothing is guessed)
7. `ram("Gaming PC Ryzen 5 5600X 16GB DDR4 RTX 3060 12GB") == "DDR4 Desktop 16GB (1x16GB)"`
8. `ram("Corsair Vengeance 16GB (2x8GB) DDR4 3200") == "DDR4 Desktop 16GB (2x8GB) 3200"` (control)
9. `ram("Kingston 2x8GB DDR4 2666") == "DDR4 Desktop 16GB (2x8GB) 2666"` (control)

Run the control cases against current code first and use the exact output strings it gives if they differ in format from the ones above. Report any difference.

**Verify**: run the tests. Cases 1, 2 and 7 FAIL. The controls (3, 4, 5, 6, 8, 9) pass.

### Step 2: Find GPU memory next to the model

Record where the chip match ends. In each `if not chip:` branch that sets `chip`, also set `chip_end = m.end()`. Initialize `chip_end = 0` next to `chip = None`. Replace the `MULTI_VRAM` block with:

```python
    if model in MULTI_VRAM:
        sizes = MULTI_VRAM[model]
        # Memory right after the model ("RTX 3060 12GB", "RTX 3060 Ventus 2X 12G") wins.
        # Otherwise take a size that fits this model and isn't system RAM ("16GB DDR4").
        near = re.search(r"\b(\d{1,2})\s*gb?\b", t[chip_end:chip_end + 25])
        vram = int(near[1]) if near and int(near[1]) in sizes else None
        if vram is None:
            for v in re.finditer(r"\b(\d{1,2})\s*gb?\b(?!\s*(?:ddr|ram|memory|sodimm))", t):
                if int(v[1]) in sizes:
                    vram = int(v[1])
                    break
        model += f" {vram}GB" if vram else " (VRAM unknown)"
```

**Verify**: GPU cases 1-6 pass.

### Step 3: A stick count is 1 to 8

In `extract_ram`, change only the third kit pattern from `r"\b(\d+)\s*x\s*(\d+)\s*gb"` to `r"\b([1-8])\s*x\s*(\d+)\s*gb"`.

**Verify**: RAM cases 7-9 pass. Whole suite `OK`.

### Step 4: Regression baseline

**Verify**:
```
python -B -c "import csv; from data.sold_parser import extract_ram, extract_gpu; rows=list(csv.DictReader(open('data/prices.csv', encoding='utf-8'))); [print(p, len(rs), sum(1 for r in rs if (f(r['model']) or (0, None))[1] == r['model'])) for p, f in [('ram', extract_ram), ('gpu', extract_gpu)] for rs in [[r for r in rows if r['part'] == p and r['kind'] == 'exact']]]"
```
→ `ram 242 N` with N ≥ 31, and `gpu 156 156`.

Also run `python -B test_titles.py` and compare it with the output from before your change (save it to a temp folder first). Only the GPU or RAM lines of Desktop samples may differ. Report each changed line.

## Done criteria

- [ ] Suite `OK` with 9 new tests
- [ ] Step 4 prints `gpu 156 156` and ram ≥ 31
- [ ] `git diff advisor/005-title-exclusions --stat` lists only `data/sold_parser.py` and `tests/test_extractors.py`

## STOP conditions

- GPU self-match drops below 156, or RAM below 31.
- A `test_titles.py` change touches a CPU or board line.
- Excerpts don't match the live file.

## Maintenance notes

- The next price refresh uses these extractors, so sold desktop titles will also be read correctly. Tables built before this change may hold a few wrong 8GB/12GB rows until then.
- Reviewers: check that `chip_end` is set in every branch that sets `chip`.
