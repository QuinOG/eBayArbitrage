# Plan 009: Fix lot pricing and part lookups on the evaluate page

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run right after the Git workflow merge; your worktree starts at an older commit)**: `git diff --stat 86f71de..HEAD -- static/evaluate.js`
> If it changed, STOP. In `scanner.py`, plan 007 changes `find_part` and `find_in_details`, which is expected. The lot block below must match.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/008-api-input-validation.md (branch chain)
- **Category**: bug
- **Planned at**: commit `86f71de` (branch `advisor/005-title-exclusions`), 2026-11-27

## Why this matters

The "Evaluate a listing" page disagrees with the scanner and can show stale numbers.
1. `"Lot of 5 Intel Core i5-8500"` shows about +$39 on the scanner (5 CPUs) and about -$85 on `/evaluate` (1 CPU). The lot rule only runs for the CPU-only search.
2. In an added part row, a failed lookup (unknown model, or a network error) leaves the previous model's value in the box. A network error leaves the row stuck on "looking up...".
3. Two quick edits to the same row can finish out of order, so the older answer wins.

## Current state

- `scanner.py` `score_listing` lot block (after plan 003):
  ```python
  quantity = 1
  lot = LOT.search(title)
  if search["parts"] == ["cpu"] and lot and int(lot[1]) > 1:
      quantity = int(lot[1])
      flags.append(f"Lot of {quantity}: CPU value multiplied by {quantity}. Check every chip is the same model.")
  risky = quantity > 1  # True when a flag means the profit is a guess
  ```
  `MANUAL_SEARCH = {"name": "Manual", "parts": ["cpu", "mobo", "ram", "gpu"], "required": ["cpu", "mobo", "ram"]}` is used by `/api/evaluate`. The CPU part is built with `make_part(part, model, price, quantity if part == "cpu" else 1, source)`.
- `static/evaluate.js` `lookupRow`:
  ```js
  async function lookupRow(row) {
    const part = row.querySelector(".part-type").value;
    const text = row.querySelector(".part-name").value.trim();
    const note = row.querySelector(".lookup");
    if (!part) {
      note.textContent = "no price data for this type, type a value";
      return;
    }
    if (!text) return;
    note.textContent = "looking up...";
    const response = await fetch("/api/price", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ part, text }),
    });
    const p = await response.json();
    const low = !response.ok || p.confidence !== "high";
    row.classList.toggle("low-row", low);
    row.querySelector(".dot").className = "dot " + (low ? "low" : "high");
    if (!response.ok) {
      note.textContent = p.error;
      return;
    }
    note.textContent = `${p.model} · ${partDetail(p)}`;
    row.querySelector(".value").value = p.value.toFixed(2);
    recalc();
  }
  ```
- Style: plain browser JS, short English comments. No JS test runner exists. Use `node --check`.
- Tests: `tests/test_scoring.py` (`ScoringTest`, fixture has `("cpu", "Core i5-8500")` at 30.0). Import `scanner.MANUAL_SEARCH` for the manual search.

## Scope

**In scope**: `scanner.py` (lot block only), `static/evaluate.js` (`lookupRow` only), `tests/test_scoring.py`.
**Out of scope**: `static/main.js`, `app.py`, the Buy/Check stamp logic in `recalc` (deferred, see Maintenance notes).

## Git workflow

- `git switch -c advisor/009-evaluate-page-fixes` then `git merge --no-edit advisor/008-api-input-validation`. If it's missing, STOP.
- One commit, e.g. `Price CPU lots on the evaluate page and clear failed lookups`. Do NOT push.

## Steps

### Step 1: Failing tests

1. `scanner.score_listing({"title": "Lot of 5 Intel Core i5-8500 3.0GHz SR3XE LGA1151 CPU", "price": 99, "shipping": 8.5}, scanner.MANUAL_SEARCH)` → CPU part value `150.0`, a flag contains `"Lot of 5"`, confidence `"low"`.
2. The same with `"Lot of 2 Intel Core i5-8500 + MSI B450 TOMAHAWK MAX"` on `MANUAL_SEARCH` → the CPU value stays `30.0` (a lot that also names a board is not a CPU lot), and no `"Lot of"` flag.
3. Control: the CPU search lot test from plan 002 still passes unchanged.

**Verify**: test 1 FAILS. Test 2 and the control pass.

### Step 2: Apply the lot rule when only CPUs are listed

Change the condition so it also covers the manual search when the title names no board, RAM or GPU:

```python
lot = LOT.search(title)
cpu_only = search["parts"] == ["cpu"] or not any(find_part(p, title)[0] for p in ("mobo", "ram", "gpu"))
if lot and int(lot[1]) > 1 and cpu_only:
```

Keep the rest of the block the same.

**Verify**: suite `OK`. `python -B test_titles.py` output is unchanged from before this step (save, then diff). The scanner's Combo and Desktop searches have other parts, so no sample changes.

### Step 3: Make `lookupRow` clear stale values and ignore old answers

Rewrite `lookupRow` to:
- Give each request a number: `const ticket = (row._ticket || 0) + 1; row._ticket = ticket;` and after every `await`, `if (row._ticket !== ticket) return;`.
- Wrap the fetch and `response.json()` in `try/catch`. On a network error, set the note to `"lookup failed, type a value"`, mark the row low, set the value to `"0.00"`, call `recalc()`, and return.
- When `!response.ok`, set the note to `p.error`, set the value to `"0.00"`, and call `recalc()`.
- When `text` is empty, set the value to `"0.00"` and call `recalc()`.

Keep the success path as it is.

**Verify**: `node --check static/evaluate.js` → exit 0. `grep -n "_ticket" static/evaluate.js` → at least 3 lines.

## Done criteria

- [ ] Suite `OK`, 2 new tests
- [ ] `node --check static/evaluate.js` exits 0, and `node tests/test_parts.js` prints `ok`
- [ ] `git diff advisor/008-api-input-validation --stat` lists only the three in-scope files

## STOP conditions

- Test 2 shows `find_part` for mobo/ram/gpu finds a part in a CPU-only lot title (would zero the lot rule). Report the title and the match.
- Excerpts don't match.

## Maintenance notes

- Manual check after merging: on `/evaluate`, add a part row, type `RTX 3060 12GB`, press Enter, then change it to `zzz`. The value should drop to 0.00.
- Deferred: the Buy/Check stamp uses the server's confidence and doesn't change as you edit rows. Deciding what a hand-typed value means for confidence is a product choice for the owner.
