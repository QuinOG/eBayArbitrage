# Plan 010: Retry eBay calls sensibly and cache scans for 90 seconds

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run right after the Git workflow merge; your worktree starts at an older commit)**: `git diff --stat 86f71de..HEAD -- ebay_api.py static/main.js templates/index.html config.py`
> If any changed, STOP. In `app.py`, plan 008 adds `read_amount` and type checks, which is expected.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (caching changes when you see new listings)
- **Depends on**: plans/009-evaluate-page-fixes.md (branch chain)
- **Category**: perf
- **Planned at**: commit `86f71de` (branch `advisor/005-title-exclusions`), 2026-11-27

## Why this matters

Every load of the scanner page runs all three eBay searches, one after another. eBay allows 5,000 calls a day, and the owner's TO-DO already asks for a short cache. When eBay is slow, `request_with_retry` makes it worse. It sleeps again after its last failed attempt (3 + 6 + 12 = 21 seconds per call), and it doesn't retry 429 "too many requests" or other 5xx errors. A 401 from an expired token is never retried with a fresh token.

## Current state

- `ebay_api.py`:
  ```python
  def request_with_retry(method, url, max_attempts=3, delay=3, **kwargs):
      """Make an HTTP request, retrying on errors and 503 responses."""
      response = None
      for attempt in range(max_attempts):
          try:
              response = requests.request(method, url, timeout=20, **kwargs)
              if response.status_code != 503:
                  return response
              if DEBUG:
                  print(f"Attempt {attempt + 1}: got 503 from {url}, retrying in {delay}s")
          except requests.RequestException as e:
              if DEBUG:
                  print(f"Attempt {attempt + 1}: {e}, retrying in {delay}s")
          time.sleep(delay)
          delay *= 2
      if response is None:
          raise Exception(f"No response from {url} after {max_attempts} attempts")
      return response
  ```
  `TOKEN_CACHE = {"token": None, "expires_at": None}`. `api_headers()` calls `get_ebay_oauth_token()`. `search_listings` and `get_item` call `request_with_retry("GET", ..., headers=api_headers(), params=...)`.
- `app.py` `/api/deals`:
  ```python
  @app.route("/api/deals")
  def api_deals():
      listings, errors = scan_all()
      return jsonify({"listings": listings, "errors": errors, "min_profit": config.MIN_PROFIT,
                      "searches": [s["name"] for s in config.SEARCHES]})
  ```
- `static/main.js:332-334`:
  ```js
  const response = await fetch("/api/deals");
  const data = await response.json();
  scannedAt = new Date();
  ```
  `scannedAt` feeds the "Scanned at 3:05 pm" line (`#summary`, main.js:137-139).
- `templates/index.html:74` has `<p id="summary" class="eyebrow"></p>`.
- `config.py` holds settings with an aligned trailing comment each, e.g. `MAX_LISTING_AGE_HOURS = 4      # ignore listings older than this`.
- Tests: stdlib `unittest` in `tests/`. Use `unittest.mock.patch` for `requests.request`, `time.sleep` and `app.scan_all`. No test may hit the network.

## Scope

**In scope**: `ebay_api.py` (`request_with_retry`, plus a 401 retry in `search_listings` and `get_item`), `app.py` (`api_deals` plus the cache), `config.py` (one setting), `static/main.js` (the load fetch and `scannedAt`), `templates/index.html` (one Refresh button), `tests/test_ebay_api.py` (create), `tests/test_api.py`.
**Out of scope**: `scanner.py`, parallel searches (the cache makes them unnecessary for now), the evaluate page.

## Git workflow

- `git switch -c advisor/010-retry-and-scan-cache` then `git merge --no-edit advisor/009-evaluate-page-fixes`. If it's missing, STOP.
- One commit, e.g. `Cache scans for 90 seconds and retry eBay rate limits`. Do NOT push.

## Steps

### Step 1: Retry tests in `tests/test_ebay_api.py`

Patch `ebay_api.requests.request` with a side-effect list of fake responses (objects with `status_code`, `headers`). Patch `ebay_api.time.sleep` and record the calls.
1. `[503, 503, 503]` → returns the last response, `requests.request` called 3 times, sleep called **2** times (no sleep after the last attempt).
2. `[429 with headers {"Retry-After": "2"}, 200]` → returns the 200, sleep called once with `2`.
3. `[429 with {"Retry-After": "600"}, 200]` → sleep called with `10` (capped).
4. `[500, 200]`, `[502, 200]`, `[504, 200]` → each returns the 200.
5. `[404]` → returned at once, no sleep.
6. Three `requests.ConnectionError` → raises `Exception`, sleep called 2 times.

**Verify**: cases 1-4 FAIL.

### Step 2: Rewrite `request_with_retry`

- Retry on status in `RETRY_STATUSES = {429, 500, 502, 503, 504}` and on `requests.RequestException`.
- Wait: for 429 with a numeric `Retry-After` header, `min(int(value), 10)`. Otherwise the current `delay`, doubling each time.
- Don't sleep after the last attempt.
- Keep the `DEBUG` prints, the 20-second timeout, and the final `Exception` when there was never a response.

**Verify**: `tests/test_ebay_api.py` passes.

### Step 3: Retry once with a new token on 401

In `search_listings` and `get_item`: if the response is 401, set `TOKEN_CACHE["token"] = None` and repeat the request once with fresh `api_headers()`. Add a test: `requests.request` returns `[401, 200]` for a search. Patch `get_ebay_oauth_token` to return `"t1"` then `"t2"`, and `config.LISTINGS_PER_SEARCH`/`MAX_LISTING_AGE_HOURS` as needed. Give the 200 a `.json()` returning `{"itemSummaries": []}` → `search_listings("164") == []`, and the second call's Authorization header is `Bearer t2`.

**Verify**: suite `OK`.

### Step 4: Cache in `app.py`

- `config.py`, under the search settings: `SCAN_CACHE_SECONDS = 90   # reuse a scan this long; the Refresh button skips it`
- `app.py`:
  ```python
  import threading
  import time

  SCAN_CACHE = {"at": 0.0, "result": None}
  SCAN_LOCK = threading.Lock()  # two tabs at once share one scan instead of running two


  def cached_scan(refresh=False):
      with SCAN_LOCK:
          fresh = time.time() - SCAN_CACHE["at"] < config.SCAN_CACHE_SECONDS
          if refresh or not fresh or SCAN_CACHE["result"] is None:
              SCAN_CACHE["result"] = scan_all()
              SCAN_CACHE["at"] = time.time()
          return SCAN_CACHE["result"], SCAN_CACHE["at"]
  ```
- `api_deals`: `refresh = request.args.get("refresh") == "1"`. Use `cached_scan(refresh)`. Add `"scanned_at": at` (epoch seconds) to the JSON. Don't cache a scan where every search failed: if `errors` and not `listings`, set `SCAN_CACHE["result"] = None` before returning.

Tests in `tests/test_api.py` (patch `app.scan_all` to return `([], [])` and count calls; reset `app.SCAN_CACHE` in `setUp`):
1. Two GETs to `/api/deals` → `scan_all` called once, and both responses have the same `scanned_at`.
2. Then `/api/deals?refresh=1` → called again.
3. `scan_all` returning `([], ["CPU search failed: x"])` → the next GET scans again.

**Verify**: suite `OK`.

### Step 5: Page uses the scan time and gets a Refresh button

- `templates/index.html`: right after `<p id="summary" class="eyebrow"></p>`, add `<button type="button" id="refresh" class="link-button">Refresh</button>`. If `link-button` doesn't exist in `static/styles.css`, use no class. Don't add CSS.
- `static/main.js`:
  - The fetch becomes `fetch(location.search.includes("refresh=1") ? "/api/deals?refresh=1" : "/api/deals")`.
  - `scannedAt = new Date(data.scanned_at * 1000);`
  - After the load, if the URL has `refresh=1`: `history.replaceState(null, "", location.pathname)`.
  - Add `$("refresh").addEventListener("click", () => { location.href = "/?refresh=1"; });`

**Verify**: `node --check static/main.js` exits 0. `python -B -c "import app"` exits 0.

## Done criteria

- [ ] Suite `OK`, including the new retry, token and cache tests
- [ ] `node --check static/main.js` and `node tests/test_parts.js` succeed
- [ ] `grep -n "SCAN_CACHE_SECONDS" config.py app.py` → matches in both
- [ ] `git diff advisor/009-evaluate-page-fixes --stat` lists only in-scope files

## STOP conditions

- Any test would need a real network call.
- `scan_all` is imported in `app.py` in a way that `mock.patch("app.scan_all")` doesn't affect (report it instead of restructuring).

## Maintenance notes

- New listings can show up to 90 seconds late. The Refresh button gets fresh results.
- The cache lives in memory, so restarting `python app.py` clears it.
- Manual check after merging: load `/`, note the "Scanned at" time, reload. The time should stay the same. Click Refresh and the time should change.
