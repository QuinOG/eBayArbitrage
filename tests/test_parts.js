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
