# Plan 007: Flag listings that name CPUs from different families

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run right after the Git workflow merge; your worktree starts at an older commit)**: `git diff --stat 86f71de..HEAD -- scanner.py`
> If it changed outside what plan 006 did (006 does not touch scanner.py), STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED (false ambiguity would zero out real CPUs)
- **Depends on**: plans/006-gpu-vram-and-ram-kits.md (branch chain)
- **Category**: bug
- **Planned at**: commit `86f71de` (branch `advisor/005-title-exclusions`), 2026-11-27

## Why this matters

When a listing names two different CPUs, the scanner is supposed to refuse to pick one ("several CPU models") and count $0. That only works when both CPUs come from the same pattern family. `"Intel i7-8700 or Ryzen 5 5600X"` prices the i7-8700 with high confidence. The reason is that `extract_models` stops at the first family that matches. Also, `find_in_details` throws away a "several models" problem found on a single detail line, so it can pick a CPU from another line instead.

## Current state

- `data/sold_parser.py:73-80` (shared with the price refresh, do NOT change it):
  ```python
  def extract_models(title):
      found = []
      for brand, pat, fmt in MODEL_PATTERNS:
          for m in pat.finditer(title):
              found.append((brand, fmt(m)))
          if found:
              break  # first family that matches wins
      return list(dict.fromkeys(found))
  ```
  `MODEL_PATTERNS` is a list of `(brand, compiled_regex, formatter)`. Order: Core Ultra, Core iN, Ryzen (two patterns), Threadripper, EPYC, Xeon, Pentium/Celeron, Core 2 (`\b([qe]\d{4})\b`). Families overlap on purpose. `"Xeon E5645"` matches both Xeon and Core 2 (`E5645`), and the first match is the right one.
- `scanner.py` `find_part` CPU branch:
  ```python
  if part == "cpu":
      models = extract_models(text)
      if len(models) > 1:
          return None, f"several CPU models ({', '.join(m for _, m in models)})"
      return (models[0][1], None) if models else (None, None)
  ```
- `scanner.py` `find_in_details`:
  ```python
  for allow_chipset in (False, True):
      for line in lines:
          model, _ = find_part(part, line, allow_chipset)
          if model and model not in found:
              found.append(model)
  ```
- Baseline: every one of the 349 CPU models in `data/prices.csv` passed through `scanner.find_part("cpu", model)` returns itself with no problem. This must stay 349 of 349.
- Tests: `tests/test_scoring.py` (`ScoringTest` with fixture prices; `self.score(search, title, price, shipping, **extra)`).

## Scope

**In scope**: `scanner.py` (`find_part` CPU branch, a new helper, `find_in_details`), `tests/test_scoring.py`.
**Out of scope**: `data/sold_parser.py`.

## Git workflow

- `git switch -c advisor/007-cpu-ambiguity` then `git merge --no-edit advisor/006-gpu-vram-and-ram-kits`. If it's missing, STOP.
- One commit, e.g. `Flag CPU titles that name models from different families`. Do NOT push.

## Steps

### Step 1: Failing tests

Add to `tests/test_scoring.py` (fixture already has `Core i7-8700`, `Ryzen 5 5600X` and others):
1. `scanner.find_part("cpu", "Intel i7-8700 or Ryzen 5 5600X")` → model `None`, problem contains `"several CPU models"`, `"Core i7-8700"` and `"Ryzen 5 5600X"`.
2. `scanner.find_part("cpu", "Intel Xeon E5645 2.4GHz")` → `("Xeon E5645", None)` (overlap control).
3. `scanner.find_part("cpu", "AMD 5800X Ryzen 7 CPU")` → `("Ryzen 7 5800X", None)` (control; run it on current code first and use its output).
4. CPU search, title `"Intel Core CPU"`, `specifics=["Processor: i7-8700 or i5-8500"]`, `description=["Ryzen 5 5600X"]` → no cpu in `parts` and a flag contains `"several CPU models"`.

**Verify**: cases 1 and 4 FAIL. Cases 2 and 3 pass.

### Step 2: Look across all families in `scanner.py`

Import `MODEL_PATTERNS` alongside the existing `data.sold_parser` imports. Add:

```python
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
```

In the `find_part` CPU branch, use `models = cpu_models(text)` and adapt to plain strings: `', '.join(models)` and `models[0]`.

**Verify**: cases 1-3 pass.

### Step 3: Keep line-level problems in `find_in_details`

```python
            for line in lines:
                model, line_problem = find_part(part, line, allow_chipset)
                if line_problem:
                    return None, f"the {label} has {line_problem}", label
                if model and model not in found:
                    found.append(model)
```

**Verify**: case 4 passes. Whole suite `OK`.

### Step 4: Regression baseline

**Verify**: `python -B -c "import csv, scanner; rows=[r for r in csv.DictReader(open('data/prices.csv', encoding='utf-8')) if r['part']=='cpu']; bad=[r['model'] for r in rows if scanner.find_part('cpu', r['model']) != (r['model'], None)]; print(len(rows), len(bad), bad[:5])"` → `349 0 []`.

Also `python -B test_titles.py` output matches the output from before your change (save it to a temp folder outside the repo first, then diff) → empty diff.

## Done criteria

- [ ] Suite `OK`, 4 new tests
- [ ] Step 4 prints `349 0 []` and the sample diff is empty
- [ ] `git diff advisor/006-gpu-vram-and-ram-kits --stat` lists only `scanner.py` and `tests/test_scoring.py`

## STOP conditions

- Step 4 reports any bad model. Report the list instead of adding special cases.
- You need to edit `data/sold_parser.py`.

## Maintenance notes

- A new CPU family in `MODEL_PATTERNS` that overlaps another needs a test like case 2.
- The price refresh still uses the first-family rule, which is fine there because it skips multi-model titles separately.
