# Plan 001: Escape quotes in HTML output so seller titles can't inject markup

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat 548bb91..HEAD -- static/parts.js static/evaluate.js static/main.js`
> If any file changed, compare the "Current state" excerpts with the live code. A mismatch is a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `548bb91`, 2026-11-27

## Why this matters

The deal scanner page builds HTML strings from eBay listing data and assigns them with `innerHTML`. The escape helper `esc()` uses `textContent` then reads `innerHTML`, which escapes `&`, `<` and `>` but NOT `"` or `'`. Seller-controlled titles are placed inside quoted attributes (`aria-label="..."`), so a title containing `" onfocus="...` adds an event handler that runs JavaScript in the user's browser. Listing URLs are also placed in `href` without a scheme check.

## Current state

- `static/parts.js` — shared drawing helpers, exposed as `window.Parts`. Loaded before `main.js` and `evaluate.js` (see `templates/index.html:106-107`, `templates/evaluate.html:71-72`).
  ```js
  // static/parts.js:5-10
  window.Parts = (function () {
    function esc(text) {
      const div = document.createElement("div");
      div.textContent = text == null ? "" : String(text);
      return div.innerHTML;
    }
  // static/parts.js:179
    return { items, money, esc };
  ```
- `static/evaluate.js:20-24` has its own copy of the same `esc` function inside the `DOMContentLoaded` handler.
- `static/main.js:3` gets it with `const { esc, money } = window.Parts;`
- Attribute sinks that receive escaped seller data:
  - `static/main.js:109` `<a href="${esc(d.listing_url)}" ...>`
  - `static/main.js:218` `aria-label="${esc(d.title)}, profit ${money(d.profit)}">`
  - `static/main.js:344` `<input type="checkbox" value="${esc(s)}" checked>`
  - `static/evaluate.js:135` `<a href="${esc(d.listing_url)}" ...>`
- Conventions: plain browser JavaScript, no build step, no framework. Functions are small and commented in plain English. Match that style.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax check | `node --check static/parts.js && node --check static/main.js && node --check static/evaluate.js` | exit 0, no output |
| New check | `node tests/test_parts.js` | prints `ok`, exit 0 |

## Scope

**In scope**:
- `static/parts.js`
- `static/main.js` (only lines that use `esc` in an `href`)
- `static/evaluate.js` (remove the local `esc`, use the shared one, and the `href` line)
- `tests/test_parts.js` (create)

**Out of scope**: Python files, templates, CSS, the duplicated `money()` helper in `evaluate.js` (it formats differently on purpose; leave it).

## Git workflow

- Create a branch: `git switch -c advisor/001-escape-html-attributes`
- One commit. Message style matches the repo (sentence case, imperative, no prefix), e.g. `Escape quotes in HTML output and check listing URL schemes`
- Do NOT push.

## Steps

### Step 1: Replace `esc` in `static/parts.js` with a string-based escape

Replace the body so it no longer uses the DOM and escapes all five characters:

```js
  // Text made safe to put inside HTML, including inside quoted attributes.
  function esc(text) {
    return (text == null ? "" : String(text))
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
```

Add a `safeUrl` helper next to it, and export both:

```js
  // A link that can only be http or https. Anything else (javascript:, data:) becomes "#".
  function safeUrl(url) {
    const s = url == null ? "" : String(url).trim();
    return /^https?:\/\//i.test(s) ? esc(s) : "#";
  }
```

Change the return line to `return { items, money, esc, safeUrl };`

**Verify**: `node --check static/parts.js` → exit 0.

### Step 2: Create `tests/test_parts.js`

```js
// Checks the HTML escape helpers in static/parts.js. Run: node tests/test_parts.js
const assert = require("assert");
global.window = {};
require("../static/parts.js");
const { esc, safeUrl } = window.Parts;

assert.strictEqual(esc(`" onfocus="alert(1)`), "&quot; onfocus=&quot;alert(1)");
assert.strictEqual(esc("<b>it's & more</b>"), "&lt;b&gt;it&#39;s &amp; more&lt;/b&gt;");
assert.strictEqual(esc(null), "");
assert.strictEqual(esc(42), "42");
assert.strictEqual(safeUrl("https://www.ebay.com/itm/123"), "https://www.ebay.com/itm/123");
assert.strictEqual(safeUrl("javascript:alert(1)"), "#");
assert.strictEqual(safeUrl(""), "#");
console.log("ok");
```

**Verify**: `node tests/test_parts.js` → prints `ok`. If it throws `document is not defined`, Step 1 still uses the DOM. Fix Step 1.

### Step 3: Use `safeUrl` for links

- `static/main.js:3`: change to `const { esc, money, safeUrl } = window.Parts;`
- `static/main.js:109`: `href="${esc(d.listing_url)}"` → `href="${safeUrl(d.listing_url)}"`

**Verify**: `grep -n 'href="${esc' static/main.js` → no output.

### Step 4: Make `evaluate.js` use the shared helpers

- Delete the local `function esc(text) { ... }` at `static/evaluate.js:20-24`.
- Add `const { esc, safeUrl } = window.Parts;` as the first line inside the `DOMContentLoaded` handler (before `const linkForm`).
- `static/evaluate.js:135`: `href="${esc(d.listing_url)}"` → `href="${safeUrl(d.listing_url)}"`

**Verify**: `grep -n "createElement(\"div\")" static/evaluate.js static/parts.js` → no output. `grep -n 'href="${esc' static/evaluate.js` → no output.

### Step 5: Final syntax check

**Verify**: `node --check static/parts.js && node --check static/main.js && node --check static/evaluate.js && node tests/test_parts.js` → prints `ok`, exit 0.

## Test plan

`tests/test_parts.js` (Step 2) covers: attribute breakout with `"`, all five escaped characters, `null`, numbers, a valid https URL, a `javascript:` URL, and an empty URL.

## Done criteria

- [ ] `node tests/test_parts.js` prints `ok`
- [ ] `node --check` passes for all three JS files
- [ ] `grep -rn 'href="${esc' static/` returns nothing
- [ ] `grep -n "function esc" static/evaluate.js` returns nothing
- [ ] `git status` shows changes only to the four in-scope files

## STOP conditions

- `templates/evaluate.html` does not load `parts.js` before `evaluate.js` (then the shared helper is undefined on that page).
- The excerpts above don't match the live files.
- Any check fails twice after a fix attempt.

## Maintenance notes

- Any new `innerHTML` template that puts listing data in an attribute must use `esc()`; any new link from listing data must use `safeUrl()`.
- A reviewer should open both pages in a browser once and confirm titles with `&` and quotes display normally (escaped entities render as the original characters).
