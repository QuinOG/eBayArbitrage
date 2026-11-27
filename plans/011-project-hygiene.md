# Plan 011: Turn off the debugger by default, pin dependencies, add a README

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run right after the Git workflow merge; your worktree starts at an older commit)**: `git diff --stat 86f71de..HEAD -- requirements.txt`
> If it changed, STOP. `app.py` and `static/evaluate.js` change in plans 008-010, which is expected. Re-read them before editing.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/010-retry-and-scan-cache.md (branch chain; the README documents its Refresh button)
- **Category**: dx
- **Planned at**: commit `86f71de` (branch `advisor/005-title-exclusions`), 2026-11-27

## Why this matters

- `app.run(debug=True)` is hardcoded. The Werkzeug debugger runs Python from the browser, which is fine on your own machine and dangerous if the app is ever started on a shared network.
- `requirements.txt` has no versions, so a fresh install can pull a different Flask than the one this was tested on.
- The repo has no README. Setup, running and testing live only in docstrings and `data/README.md`.
- `static/evaluate.js` has its own `money()` that formats without thousands commas, unlike the scanner page.

## Current state

- `app.py` last lines:
  ```python
  if __name__ == "__main__":
      app.run(debug=True)
  ```
- `requirements.txt`:
  ```
  flask
  requests
  python-dotenv
  ```
  Installed and tested versions: Flask 3.1.3, requests 2.34.2, python-dotenv 1.2.4, Python 3.14.
- `static/evaluate.js` has a local `money` near the top of the `DOMContentLoaded` handler:
  ```js
  function money(n) {
    return (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(2);
  }
  ```
  and already destructures `const { esc, safeUrl } = window.Parts;`. `window.Parts.money` formats with commas.
- Facts for the README:
  - Setup: `pip install -r requirements.txt`, then copy `.env.example` to `.env` and fill in the eBay Production keys (`EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`).
  - Run the web app with `python app.py` and open http://127.0.0.1:5000. `/evaluate` scores one listing. Scans are cached 90 seconds, and the Refresh button gets fresh results.
  - Command-line scan: `python scanner.py`. Category check: `python check_categories.py`.
  - Tests: `python -B -m unittest discover -s tests -t . -v` and `node tests/test_parts.js`.
  - Settings live in `config.py`. Price data and refreshing it are in `data/README.md`. Known gaps are in `TO-DO`.
  - Uses only eBay's official Browse API, about 5,000 calls a day.
- Owner's writing style for docs: plain words, short sentences, sentence-case headings, no marketing.

## Scope

**In scope**: `app.py` (the `__main__` block), `requirements.txt`, `README.md` (create), `static/evaluate.js` (remove the local `money`).
**Out of scope**: everything else. Don't add a linter, formatter or CI.

## Git workflow

- `git switch -c advisor/011-project-hygiene` then `git merge --no-edit advisor/010-retry-and-scan-cache`. If it's missing, STOP.
- One commit, e.g. `Make debug opt-in, pin dependencies and add a README`. Do NOT push.

## Steps

### Step 1: Debug is opt-in

```python
if __name__ == "__main__":
    # FLASK_DEBUG=1 turns on auto-reload and the in-browser debugger. Keep it off on shared networks.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
```
Add `import os` at the top if it's missing.

**Verify**: `grep -n "debug=True" app.py` → no output. `python -B -c "import app"` → exit 0.

### Step 2: Pin requirements

```
flask==3.1.3
requests==2.34.2
python-dotenv==1.2.4
```

**Verify**: `python -m pip install --dry-run -r requirements.txt` → exit 0 and reports the requirements as already satisfied. If `--dry-run` isn't supported, skip it and say so.

### Step 3: Shared `money` on the evaluate page

Delete the local `money` function and change the destructure to `const { esc, safeUrl, money } = window.Parts;`.

**Verify**: `node --check static/evaluate.js` → exit 0. `grep -n "function money" static/evaluate.js` → no output.

### Step 4: README.md

Write a root `README.md` of about 40-60 lines covering, in order: what it does (one paragraph), setup, run, the evaluate page, settings, tests, price data (link to `data/README.md`), and limits (link to `TO-DO`). Use only the facts listed in "Current state". Don't invent features.

**Verify**: `test -f README.md && grep -c "unittest discover" README.md` → `1` or more.

### Step 5: Everything still passes

**Verify**: `python -B -m unittest discover -s tests -t . -v` → `OK`. `node tests/test_parts.js` → `ok`.

## Done criteria

- [ ] All Step verifications pass
- [ ] `git diff advisor/010-retry-and-scan-cache --stat` lists only the four in-scope files

## STOP conditions

- The installed versions differ from those listed. Report what `python -m pip show flask requests python-dotenv` prints instead of picking versions.

## Maintenance notes

- Update the pins together when you upgrade, then rerun the tests.
- The owner now needs `FLASK_DEBUG=1` (PowerShell: `$env:FLASK_DEBUG="1"`) to get auto-reload while developing.
