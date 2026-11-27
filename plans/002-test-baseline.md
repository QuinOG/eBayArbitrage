# Plan 002: Add an automated test suite for scoring, pricing and the API

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat 548bb91..HEAD -- scanner.py prices.py app.py config.py`
> If any file changed, compare the "Current state" excerpts with the live code. A mismatch is a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (it stacks on plan 001's branch so the final branch holds everything)
- **Category**: tests
- **Planned at**: commit `548bb91`, 2026-11-27

## Why this matters

The app decides "Buy" or "Pass" from profit math and part detection, and nothing checks either. `test_titles.py` only prints results, so a regression can't fail. Later plans (003, 004, 005) change scoring and the price refresh script. They need tests that fail when behavior changes. Tests must not depend on the real `data/prices.csv` numbers, because the owner refreshes that file every 1-2 weeks.

## Current state

- Python 3.14, Flask 3.1, `requests`, `python-dotenv` are installed. No pytest. Use the standard library `unittest` and `unittest.mock` only. Do not add dependencies.
- `prices.py` loads `data/prices.csv` at import into the module dict `PRICES`, keyed `(part, model)`:
  ```python
  # prices.py:22-30, 38, 56-63
  prices[key] = {"value": float(row["value"]), "sales": int(row["sales"]),
                 "confidence": row["confidence"], "kind": row["kind"]}
  PRICES = load_prices()
  def lookup(part, model):
      row = PRICES.get((part, model))
      if row:
          return {**row, "priced_as": model}
      backup = fallback_model(part, model)   # mobo -> chipset ("B450"), ram -> first 3 words
      ...
  ```
  `scanner.py` does `from prices import lookup`, and `lookup` reads the module global `PRICES`. So `unittest.mock.patch.dict(prices.PRICES, FIXTURE, clear=True)` controls every price.
- `config.py` holds `SALES_TAX_RATE = 0.075`, `TAX_ON_SHIPPING = True`, `MIN_PROFIT = 20.00`, and `SEARCHES` (names `CPU`, `Combo`, `Desktop`). `scanner.score_listing` reads them as `config.X` at call time, so `unittest.mock.patch.object(config, "SALES_TAX_RATE", 0.10)` works.
- `scanner.score_listing(listing, search)` (scanner.py:167-259) returns the listing plus `parts`, `missing`, `extras`, `parts_value`, `tax`, `total_cost`, `profit`, `is_deal`, `confidence` ("high"/"low"), `flags` (list of strings). Math (scanner.py:237-242):
  ```python
  taxable = price + shipping if config.TAX_ON_SHIPPING else price
  tax = round(taxable * config.SALES_TAX_RATE, 2)
  cost = round(price + shipping + tax, 2)
  parts_value = round(sum(p["value"] for p in parts), 2)
  profit = round(parts_value - cost, 2)
  ```
  Unknown shipping (`None`) becomes 0.0 and adds a flag. A CPU-only search with "Lot of N" in the title multiplies the CPU value by N.
- `scanner.find_part(part, text)` returns `(model, problem)`. Model names match `prices.csv`, e.g. `"Core i7-8700"`, `"Ryzen 5 5600X"`, `"MSI B450 TOMAHAWK MAX"`, `"DDR4 Desktop 16GB (1x16GB) 3200"`, `"RTX 3060 12GB"`.
- `app.py` Flask app object is `app.app`. Routes: `POST /api/price` (`{"part","text"}` → part row, 400 on bad input), `POST /api/evaluate` (`{"title","price","shipping","description"}` → `{"listing": ..., ...}`, 400 when title is empty). Do NOT test `/api/deals` or `/api/evaluate` with `"link"`: both call eBay over the network.
- Existing sample titles with known outputs are in `test_titles.py`. Use them as inputs.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `python -B -m unittest discover -s tests -t . -v` | `OK`, exit 0 |
| Old sanity script still runs | `python -B test_titles.py` | prints receipts, exit 0 |

## Scope

**In scope** (create only):
- `tests/__init__.py` (empty)
- `tests/test_scoring.py`
- `tests/test_api.py`

**Out of scope**: every existing file. This plan adds tests only and must not change behavior. If a test you write fails against current code, the test is wrong or you found a bug. Either way, do not change app code. Record the case in your report and assert the CURRENT behavior with a comment `# current behavior, see report`.

## Git workflow

- Start from plan 001's branch: `git switch -c advisor/002-test-baseline` then `git merge --no-edit advisor/001-escape-html-attributes` (skip the merge if that branch doesn't exist and say so in your report).
- One commit, e.g. `Add unittest suite for scoring, pricing and the API`. Do NOT push.

## Steps

### Step 1: Create the harness

Create empty `tests/__init__.py`. In `tests/test_scoring.py` define a fixture and a base class:

```python
import unittest
from unittest import mock

import config
import prices
import scanner

FIXTURE = {
    ("cpu", "Core i7-8700"): {"value": 60.0, "sales": 10, "confidence": "high", "kind": "exact"},
    ("cpu", "Core i5-8500"): {"value": 30.0, "sales": 10, "confidence": "high", "kind": "exact"},
    ("cpu", "Ryzen 5 3600"): {"value": 70.0, "sales": 10, "confidence": "high", "kind": "exact"},
    ("mobo", "MSI B450 TOMAHAWK MAX"): {"value": 80.0, "sales": 1, "confidence": "low", "kind": "exact"},
    ("mobo", "B660M"): {"value": 85.0, "sales": 5, "confidence": "high", "kind": "fallback"},
    ("ram", "DDR4 Desktop 16GB"): {"value": 50.0, "sales": 5, "confidence": "high", "kind": "fallback"},
    ("gpu", "RTX 3060 12GB"): {"value": 300.0, "sales": 20, "confidence": "high", "kind": "exact"},
}
SEARCH = {s["name"]: s for s in config.SEARCHES}


class ScoringTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.dict(prices.PRICES, FIXTURE, clear=True),
            mock.patch.object(config, "SALES_TAX_RATE", 0.10),
            mock.patch.object(config, "TAX_ON_SHIPPING", True),
            mock.patch.object(config, "MIN_PROFIT", 20.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def score(self, search, title, price, shipping, **extra):
        return scanner.score_listing({"title": title, "price": price, "shipping": shipping, **extra}, SEARCH[search])
```

**Verify**: `python -B -m unittest discover -s tests -t . -v` → `Ran 0 tests ... OK` (or `NO TESTS RAN`, exit code 5 is acceptable at this step only).

### Step 2: Scoring tests in `tests/test_scoring.py`

Write one test method per case. Run each title through the code first (`python -B -c "..."`) to confirm detection, then assert:

1. Profit math: CPU search, `"Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor"`, price 40, shipping 10 → `tax == 5.0`, `total_cost == 55.0`, `parts_value == 60.0`, `profit == 5.0`, `is_deal is False`, `confidence == "high"`.
2. Tax without shipping: same listing with `config.TAX_ON_SHIPPING` patched to False inside the test → `tax == 4.0`.
3. Deal threshold: same title, price 20, shipping 0 → `profit == 38.0`, `is_deal is True`.
4. Lot multiplier: CPU search, `"Lot of 5 Intel Core i5-8500 3.0GHz SR3XE LGA1151 CPU"` → `parts_value == 150.0`, and some flag contains `"Lot of 5"`.
5. Unknown shipping: price 40, shipping `None` → `shipping == 0.0` and a flag contains `"Shipping cost unknown"`.
6. Unidentified CPU: CPU search, `"Intel Core i5 10th Gen Processor Desktop CPU"` → `parts == []`, `parts_value == 0`, `confidence == "low"`, `missing[0]["part"] == "cpu"`.
7. Low-confidence part: Combo search, `"MSI B450 TOMAHAWK MAX + AMD Ryzen 5 3600 + 16GB DDR4 3200 Combo"` → board value 80.0 is in parts and `confidence == "low"` (the board has 1 sale).
8. Chipset fallback: Combo search, `"Intel i5-12400F + B660M Motherboard + 16GB DDR4 Bundle"` → the mobo part has `priced_as == "B660M"` and `kind == "fallback"`, and a flag contains `"average B660M board"`.
9. GPU: Desktop search, `"Custom Gaming PC Ryzen 5 3600 RTX 3060 12GB 32GB DDR4"` → a gpu part with model `"RTX 3060 12GB"` and value 300.0.
10. Damaged title: CPU search, `"Intel Core i7-8700 - Untested, For Parts"` → a flag contains `"damaged or untested"`. Assert the current `confidence` value with the comment `# current behavior, plan 003 changes this`.
11. `find_part("cpu", "i7-8700 and i5-8500")` returns `(None, <problem string containing "several CPU models">)`.
12. `prices.lookup("mobo", "MSI B660M MORTAR")` (not in fixture) returns the B660M fallback row with `priced_as == "B660M"`. `prices.lookup("cpu", "Core i9-99999")` returns `None`.

**Verify**: `python -B -m unittest discover -s tests -t . -v` → 12 tests, `OK`.

### Step 3: API tests in `tests/test_api.py`

Use `app.app.test_client()`, patching `prices.PRICES` the same way (import `FIXTURE` from `tests.test_scoring`).

1. `POST /api/price` `{"part": "cpu", "text": "i7-8700"}` → 200, JSON `model == "Core i7-8700"`, `value == 60.0`.
2. `POST /api/price` `{"part": "psu", "text": "x"}` → 400 with an `error` key.
3. `POST /api/price` `{"part": "cpu", "text": "nothing here"}` → 400.
4. `POST /api/evaluate` `{"title": ""}` → 400.
5. `POST /api/evaluate` `{"title": "Intel Core i7-8700", "price": 40, "shipping": 10}` → 200, `listing.profit` is a number, `listing.parts[0].model == "Core i7-8700"`.

**Verify**: `python -B -m unittest discover -s tests -t . -v` → 17 tests, `OK`.

### Step 4: Confirm nothing else changed

**Verify**: `git status --short` → only `tests/` files (plus plan 001's files if merged). `python -B test_titles.py` → exit 0.

## Done criteria

- [ ] `python -B -m unittest discover -s tests -t . -v` → at least 17 tests, `OK`
- [ ] Tests pass with no network access (none call `/api/deals` or use `"link"`)
- [ ] `git diff --stat 548bb91 -- '*.py' ':!tests'` shows no changes to app code
- [ ] Every test asserts concrete values, not just "no exception"

## STOP conditions

- A listed title is not detected the way the plan says (e.g. case 9 finds no GPU). Report the actual output. Do not change the title to force a pass without reporting it.
- Patching `prices.PRICES` does not affect `scanner` results (would mean `lookup` was copied, not imported).
- You find you need to edit any non-test file.

## Maintenance notes

- Add a test here with every scoring change. Plans 003 and 005 extend `tests/test_scoring.py`.
- If `prices.lookup` is ever rewritten to cache results, the fixture patch approach must be revisited.
