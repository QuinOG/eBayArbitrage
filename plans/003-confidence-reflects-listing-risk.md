# Plan 003: Mark risky listings low confidence so they never get a "Buy" stamp

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat 548bb91..HEAD -- scanner.py`
> If it changed, compare the "Current state" excerpts with the live code. A mismatch is a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED (changes which listings show "Buy" and which "Hide low confidence" hides)
- **Depends on**: plans/002-test-baseline.md
- **Category**: bug
- **Planned at**: commit `548bb91`, 2026-11-27

## Why this matters

A listing's overall `confidence` decides the verdict stamp on the page: high confidence + profit above the minimum = green "Buy", low = amber "Check" (`static/main.js:83-88`). Today confidence only asks "did every found part have 3+ sales?". So an "Untested, For Parts" i9-9900K scores +$97 with "Buy". So does a combo whose board was never identified (counted $0), a listing with unknown shipping (counted $0), a "Lot of 5" whose chips are unchecked, and a board priced as an average for its chipset. Each already adds a warning flag, but the stamp ignores flags. After this plan, every one of these is low confidence.

## Current state

- `scanner.py` — finds parts, prices them, computes profit. `score_listing` at lines 167-259.
- Relevant excerpts:
  ```python
  # scanner.py:180-184
  quantity = 1
  lot = LOT.search(title)
  if search["parts"] == ["cpu"] and lot and int(lot[1]) > 1:
      quantity = int(lot[1])
      flags.append(f"Lot of {quantity}: CPU value multiplied by {quantity}. Check every chip is the same model.")

  # scanner.py:203-215
  if model is None:
      if part in search["required"] or problem:
          missing.append({"part": part, "name": name})
      ...
      continue
  parts.append(make_part(part, model, price, quantity if part == "cpu" else 1, source))
  if price is None:
      flags.append(f"No price data for {name} '{model}'. Counted as $0.")
  elif part == "mobo" and price["kind"] == "fallback" and model == price["priced_as"]:
      flags.append(f"Board brand and model unknown, priced as an average {model} board.")

  # scanner.py:226-235
  junk = next((m for m in map(MOBO_JUNK.search, listing.get("description") or []) if m), None)
  if junk:
      flags.append(f"Description mentions '{junk[0]}'. Values assume working parts.")
  if MOBO_JUNK.search(title):
      flags.append("Title suggests parts may be damaged or untested. Values assume working parts.")

  shipping = listing.get("shipping")
  if shipping is None:
      flags.append("Shipping cost unknown. Counted as $0.")
      shipping = 0.0

  # scanner.py:244
  low = any(p["confidence"] != "high" for p in parts) or not parts
  ```
- Board fallback has two cases. When the title names only a chipset ("B660M Motherboard"), `model == priced_as == "B660M"` and a flag exists. When the title names a full board that has no exact row ("MSI B550 GAMING PLUS"), `prices.lookup` returns the `B550` average with `priced_as = "B550"` and **no flag** today.
- RAM fallback (`"DDR4 Desktop 16GB"` from `"DDR4 Desktop 16GB (2x8GB) 3200"`) keeps the same size and type and is fine. Leave RAM fallback as high confidence.
- Tests: `tests/test_scoring.py` (from plan 002) with a `ScoringTest` base class that patches `prices.PRICES` with `FIXTURE` and sets tax 10%. Follow its style. Case 10 there asserts the old confidence for a damaged title with the comment `# current behavior, plan 003 changes this`.
- Style: plain functions, short English comments, f-string flags that end with a period. Match it.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `python -B -m unittest discover -s tests -t . -v` | `OK` |
| Sanity script | `python -B test_titles.py` | exit 0 |

## Scope

**In scope**: `scanner.py` (`score_listing` only), `tests/test_scoring.py`.

**Out of scope**: `data/sold_parser.py` (shared with the price refresh), `prices.py`, all JS (the page already reads `confidence`), the `MOBO_JUNK` regex itself.

## Git workflow

- `git switch -c advisor/003-confidence-reflects-listing-risk` then `git merge --no-edit advisor/002-test-baseline`. If that branch doesn't exist, STOP: this plan needs its tests.
- One commit, e.g. `Mark damaged, incomplete and estimated listings low confidence`. Do NOT push.

## Steps

### Step 1: Write failing tests first

Add these to `tests/test_scoring.py` (each asserts `confidence == "low"`):

1. CPU search, `"Intel Core i7-8700 - Untested, For Parts"`, price 20, shipping 0. Update existing case 10 to assert `"low"` and drop its "current behavior" comment.
2. Combo search, `"AMD Ryzen 5 3600 CPU and 16GB DDR4 RAM Combo"` (no board) → `missing` has `mobo`, confidence low.
3. CPU search, `"Intel Core i7-8700"`, shipping `None` → low.
4. CPU search, `"Lot of 5 Intel Core i5-8500 3.0GHz SR3XE LGA1151 CPU"` → low.
5. Combo search, `"Intel i5-12400F + B660M Motherboard + 16GB DDR4 Bundle"` with the fixture's B660M row → low.
6. Full board name, fallback price: add `("mobo", "B550"): {"value": 80.0, "sales": 30, "confidence": "high", "kind": "fallback"}` and `("cpu", "Ryzen 5 5600X"): {"value": 120.0, "sales": 10, "confidence": "high", "kind": "exact"}` to the fixture. Combo search, `"MSI B550 GAMING PLUS Ryzen 5 5600X Combo"` → the mobo part has `priced_as == "B550"`, confidence low, and a flag contains `"priced as an average B550 board"`.
7. Description junk: CPU search, `"Intel Core i7-8700"` with `description=["Sold as-is"]` → low.
8. Control: CPU search, `"Intel Core i7-8700"`, shipping 5 → still `"high"`.

**Verify**: `python -B -m unittest discover -s tests -t . -v` → the new low-confidence tests FAIL, the control passes. (If any already passes, note it in your report.)

### Step 2: Track the risk conditions in `score_listing`

- Before the parts loop, add `risky = quantity > 1` right after the lot block.
- In the fallback branch (scanner.py:214), replace the single `elif` with:
  ```python
  elif part == "mobo" and price["kind"] == "fallback":
      risky = True
      if model == price["priced_as"]:
          flags.append(f"Board brand and model unknown, priced as an average {model} board.")
      else:
          flags.append(f"No sold data for '{model}', priced as an average {price['priced_as']} board.")
  ```
- After the junk checks: `if junk or MOBO_JUNK.search(title): risky = True`.
- In the shipping block: set `risky = True` inside `if shipping is None:`.
- Replace line 244 with:
  ```python
  # Low when any price is thin, a required part is missing, or a flag means the profit is a guess.
  low = not parts or bool(missing) or risky or any(p["confidence"] != "high" for p in parts)
  ```

**Verify**: `python -B -m unittest discover -s tests -t . -v` → `OK`, all tests pass.

### Step 3: Check the sample output

**Verify**: `python -B test_titles.py | grep -c "LOW CONFIDENCE"` → a number greater than before. Before this change it is 9 with the current `data/prices.csv`. Every sample with "Untested", "Lot of", unknown shipping, a missing board, or a board fallback now shows `[LOW CONFIDENCE]`. `"Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor SR3QS"` still does not.

## Done criteria

- [ ] `python -B -m unittest discover -s tests -t . -v` → `OK`, including the 8 new tests
- [ ] `git diff --stat advisor/002-test-baseline -- . ':!tests'` lists only `scanner.py`
- [ ] `grep -n "low = not parts or bool(missing) or risky" scanner.py` → one match

## STOP conditions

- Any existing test other than case 10 has to change to pass.
- The Combo title in Step 1 test 2 detects a board anyway. Report what it detects instead of rewriting the title more than once.
- Excerpts don't match the live file.

## Maintenance notes

- New flags that mean "the profit is a guess" should also set `risky = True`.
- The scanner page's "Hide low confidence" checkbox now hides more listings. This is intended. Mention it to the owner.
- Deferred: separate fields for "why low" (a `confidence_reasons` list). The flags already explain it.
