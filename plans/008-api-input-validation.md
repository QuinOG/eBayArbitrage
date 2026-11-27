# Plan 008: Reject bad numbers and wrong JSON types in the API with clear 400 errors

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run right after the Git workflow merge; your worktree starts at an older commit)**: `git diff --stat 86f71de..HEAD -- app.py`
> If it changed, compare the "Current state" excerpt with the live code. A mismatch is a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/007-cpu-ambiguity.md (branch chain)
- **Category**: bug
- **Planned at**: commit `86f71de` (branch `advisor/005-title-exclusions`), 2026-11-27

## Why this matters

`/api/evaluate` turns `price` and `shipping` into numbers with bare `float()`. `"NaN"` and `"Infinity"` pass and produce JSON the browser can't parse, so the page breaks with a generic error. Negative prices are accepted. A JSON array body crashes on `.get` and comes back as 502 "Couldn't load the listing". In `/api/price`, a number in `text` crashes with a 500.

## Current state

- `app.py` (the full handlers):
  ```python
  @app.route("/api/evaluate", methods=["POST"])
  def api_evaluate():
      body = request.get_json(silent=True) or {}
      try:
          if body.get("link"):
              listing = get_item(body["link"])
          else:
              title = (body.get("title") or "").strip()
              if not title:
                  return jsonify({"error": "Enter an eBay link, or a title and price."}), 400
              shipping = body.get("shipping")
              listing = {
                  "title": title,
                  "price": float(body.get("price") or 0),
                  "shipping": float(shipping) if shipping not in (None, "") else 0.0,
                  "condition": "", "listing_url": "", "post_date": "",
                  "description": [l.strip() for l in (body.get("description") or "").splitlines() if l.strip()],
              }
      except ValueError as e:
          return jsonify({"error": str(e)}), 400
      except Exception as e:
          return jsonify({"error": f"Couldn't load the listing: {e}"}), 502
      ...

  @app.route("/api/price", methods=["POST"])
  def api_price():
      body = request.get_json(silent=True) or {}
      part, text = body.get("part"), (body.get("text") or "").strip()
      if part not in PART_NAMES or not text:
          return jsonify({"error": "Pick a part type and type its model."}), 400
  ```
- `ebay_api.get_item` raises `ValueError` with a user-facing message for bad links. Keep that path.
- Error style: `jsonify({"error": "<plain sentence>"}), 400`. Match it.
- Tests: `tests/test_api.py` (`ApiTest`, `self.client = app.app.test_client()`, fixture prices). Follow it.

## Scope

**In scope**: `app.py` (these two handlers plus a small helper), `tests/test_api.py`.
**Out of scope**: `ebay_api.py`, `scanner.py`, JS. Don't test `"link"` with a real number, since it calls eBay.

## Git workflow

- `git switch -c advisor/008-api-input-validation` then `git merge --no-edit advisor/007-cpu-ambiguity`. If it's missing, STOP.
- One commit, e.g. `Validate API input types and amounts`. Do NOT push.

## Steps

### Step 1: Failing tests in `tests/test_api.py`

Each expects status 400 and an `error` key:
1. `/api/evaluate` `{"title": "Intel Core i7-8700", "price": "NaN"}`
2. `/api/evaluate` `{"title": "Intel Core i7-8700", "price": "Infinity"}`
3. `/api/evaluate` `{"title": "Intel Core i7-8700", "price": -5}`
4. `/api/evaluate` `{"title": "Intel Core i7-8700", "price": 40, "shipping": "abc"}` (error text mentions shipping)
5. `/api/evaluate` with body `[1, 2]`
6. `/api/evaluate` `{"title": 123}`
7. `/api/evaluate` `{"link": 123456789012}` (a number, not a string). Must return 400 without calling eBay. Patch `app.get_item` with a mock and assert it was not called.
8. `/api/price` `{"part": "cpu", "text": 8700}`
9. `/api/price` with body `["cpu"]`

Controls with status 200: `{"title": "Intel Core i7-8700", "price": "40", "shipping": ""}` (string numbers and blank shipping still work), and `{"title": "Intel Core i7-8700"}` (price defaults to 0).

**Verify**: the new error cases FAIL. The controls pass.

### Step 2: Add a helper and type checks

In `app.py`, above the routes:

```python
import math


def read_amount(body, key, label):
    """A price or shipping amount from the request: blank means 0. Raises ValueError with a message for the page."""
    value = body.get(key)
    if value in (None, ""):
        return 0.0
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(amount) or amount < 0:
        raise ValueError(f"{label} must be a number of 0 or more.")
    return amount
```

In `api_evaluate`, after reading the body: `if not isinstance(body, dict): return jsonify({"error": "Send a JSON object."}), 400`. Inside the `try`:
- if `"link"` is present and not a string → raise `ValueError("The link must be text.")`
- `title = body.get("title") or ""`; if it is not a string → raise `ValueError("The title must be text.")`
- `"price": read_amount(body, "price", "Price")`, `"shipping": read_amount(body, "shipping", "Shipping")`
- `description = body.get("description") or ""`; if it is not a string → raise `ValueError("The description must be text.")`

In `api_price`: the same dict check, and treat a non-string `text` as missing (the existing 400 message).

**Verify**: suite `OK`.

## Done criteria

- [ ] Suite `OK`, 11 new tests
- [ ] `python -B -c "import app"` exits 0
- [ ] `git diff advisor/007-cpu-ambiguity --stat` lists only `app.py` and `tests/test_api.py`

## STOP conditions

- A control fails after the change.
- Test 7 calls eBay (the mock reports a call).

## Maintenance notes

- New numeric fields should go through `read_amount`.
- The evaluate page already shows `data.error` from 400 responses, so no JS change is needed.
