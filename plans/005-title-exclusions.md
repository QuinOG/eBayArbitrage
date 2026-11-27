# Plan 005: Don't count a part the title says isn't included

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat 548bb91..HEAD -- scanner.py`
> Plan 003 changed `score_listing` on the branch you merge. Its changes are expected. Any other difference from the excerpts below is a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (a too-broad pattern would zero out real parts)
- **Depends on**: plans/003-confidence-reflects-listing-risk.md (same function, uses its tests)
- **Category**: bug
- **Planned at**: commit `548bb91`, 2026-11-27

## Why this matters

`"Intel Core i7-8700 box only no CPU"` is valued at the full i7-8700 price with high confidence, so an empty box looks like a deal. The scanner already skips description lines that say a part isn't included (`NOT_INCLUDED`), but the title is never checked. After this plan, a part the title explicitly excludes is counted as $0, flagged, and treated as missing, so the listing is low confidence.

## Current state

- `scanner.py` — scoring. The description filter that already exists:
  ```python
  # scanner.py:42-44
  NOT_INCLUDED = re.compile(r"not included|n'?t (?:come|include)|does not (?:come|include)|without|sold separately|"
                            r"\bno (?:cpu|ram|gpu|memory|graphics|processor|cooler|psu)\b", re.IGNORECASE)
  ```
  It drops a whole line. That is too blunt for a title: `"Ryzen 5 3600 + B450 board, no RAM"` must still count the CPU and board. The title check must work per part.
- The parts loop in `score_listing` (after plan 003; line numbers shift by a few):
  ```python
  for part in search["parts"]:
      name = PART_NAMES[part]
      model, problem = find_part(part, title)
      price = lookup(part, model) if model else None
      source = "title"
      if has_details and not problem and rank(price) < 2:
          ...details lookup...
      if problem:
          flags.append(f"{name}: {problem}. Counted as $0.")
      if model is None:
          if part in search["required"] or problem:
              missing.append({"part": part, "name": name})
          ...
          continue
  ```
  Plan 003 made `missing` non-empty → `confidence == "low"`.
- `PART_NAMES = {"cpu": "CPU", "mobo": "Motherboard", "ram": "RAM", "gpu": "GPU"}`.
- Traps: `"no CPU cooler"` and `"without cooler"` mean the COOLER is missing, not the CPU. `"no OS"`, `"no box"` and `"no cables"` exclude nothing priced. `"Motherboard + CPU, RAM not included"` excludes only RAM.
- Tests: `tests/test_scoring.py` (`ScoringTest`, fixture prices, `self.score(search, title, price, shipping)`). Match its style.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `python -B -m unittest discover -s tests -t . -v` | `OK` |
| Sample output unchanged | see Step 4 | empty diff |

## Scope

**In scope**: `scanner.py` (a new constant and the top of the parts loop), `tests/test_scoring.py`.

**Out of scope**: `NOT_INCLUDED` and `detail_lines` (description handling works), `data/sold_parser.py`, all JS.

## Git workflow

- `git switch -c advisor/005-title-exclusions` then `git merge --no-edit advisor/004-safe-price-refresh` (if missing, merge `advisor/003-confidence-reflects-listing-risk`; if that is missing too, STOP).
- One commit, e.g. `Skip parts the listing title says aren't included`. Do NOT push.

## Steps

### Step 1: Save the sample output before changing anything

**Verify**: `python -B test_titles.py > "$TMPDIR/before.txt"` (any temp folder outside the repo) → exit 0.

### Step 2: Write failing tests

Add to `tests/test_scoring.py`. Each "excluded" case asserts the part is NOT in `parts`, a flag contains `"isn't included"`, and `confidence == "low"`:

1. CPU search: `"Intel Core i7-8700 box only no CPU"`
2. CPU search: `"Intel Core i7-8700 Empty Box"`
3. CPU search: `"Intel Core i7-8700 cooler only"`
4. Combo search: `"MSI B450 TOMAHAWK MAX + Ryzen 5 3600 Combo, no RAM"` → CPU and board ARE in parts. RAM is not, and a flag contains `"RAM isn't included"`.
5. Combo search: `"MSI B450 TOMAHAWK MAX + Ryzen 5 3600, RAM not included"` → same as 4.
6. Desktop search: `"Gaming PC Ryzen 5 3600 16GB DDR4 without GPU"` → no gpu part, flag contains `"GPU isn't included"`.

Controls (part IS counted, no "isn't included" flag):

7. CPU search: `"Intel Core i7-8700 no CPU cooler"` → CPU counted.
8. CPU search: `"Intel Core i7-8700 without cooler, no box"` → CPU counted.
9. Combo search: `"MSI B450 TOMAHAWK MAX + Ryzen 5 3600 + 16GB DDR4 3200 Combo"` → no exclusion flag.

**Verify**: the test run shows cases 1-6 FAIL and 7-9 pass.

### Step 3: Add per-part title exclusions

Below `NOT_INCLUDED` in `scanner.py`:

```python
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
```

At the top of the parts loop, right after `name = PART_NAMES[part]`:

```python
        if TITLE_EXCLUDES[part].search(title):
            flags.append(f"Title says the {name} isn't included. Counted as $0.")
            missing.append({"part": part, "name": name})
            continue
```

This skips the description lookup for that part on purpose: the seller said it's not included.

**Verify**: `python -B -m unittest discover -s tests -t . -v` → `OK`, all tests pass.

### Step 4: Confirm the sample titles are unaffected

**Verify**: `python -B test_titles.py > "$TMPDIR/after.txt" && diff "$TMPDIR/before.txt" "$TMPDIR/after.txt"` → no output. (None of the 15 samples excludes a part.)

### Step 5: Check against real price titles for false positives

The models in `data/prices.csv` are clean names. None should trigger an exclusion:

**Verify**: `python -B -c "import csv, scanner; rows=list(csv.DictReader(open('data/prices.csv', encoding='utf-8'))); hits=[r['model'] for r in rows if any(p.search(r['model']) for p in scanner.TITLE_EXCLUDES.values())]; print(len(hits), hits[:5])"` → `0 []`

## Done criteria

- [ ] `python -B -m unittest discover -s tests -t . -v` → `OK`, including 9 new tests
- [ ] Step 4 diff is empty
- [ ] Step 5 prints `0 []`
- [ ] `git diff advisor/004-safe-price-refresh --stat` lists only `scanner.py` and `tests/test_scoring.py` (or `advisor/003-...` if 004 was missing)

## STOP conditions

- A control test (7-9) fails and fixing it needs a pattern change you can't justify in one sentence. Report the title and the match instead.
- Step 4 shows any difference.
- `missing` handling from plan 003 isn't present (branch merge failed).

## Maintenance notes

- Patterns are deliberately narrow. Sellers write "w/o CPU" and "CPU NOT INCLUDED!!". Add phrases with a test each as they come up.
- `"box only"` and `"cooler only"` exclude the CPU in every search. On a combo title they zero out the CPU, which errs toward a lower profit. That is the safe direction.
- Deferred: CPU ambiguity across families (`"i7-8700 or Ryzen 5 5600X"` prices only the Intel chip). It lives in `extract_models` in `data/sold_parser.py`, which also builds the price table, and its pattern families overlap on purpose (e.g. "Xeon E5645" also matches the Core 2 pattern). It needs its own plan.
