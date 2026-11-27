// Checks the HTML escape helpers in static/parts.js. Run: node tests/test_parts.js
const assert = require("assert");
global.window = {};
require("../static/parts.js");
const { esc, safeUrl, spread, stamp } = window.Parts;

assert.strictEqual(esc(`" onfocus="alert(1)`), "&quot; onfocus=&quot;alert(1)");
assert.strictEqual(esc("<b>it's & more</b>"), "&lt;b&gt;it&#39;s &amp; more&lt;/b&gt;");
assert.strictEqual(esc(null), "");
assert.strictEqual(esc(42), "42");
assert.strictEqual(safeUrl("https://www.ebay.com/itm/123"), "https://www.ebay.com/itm/123");
assert.strictEqual(safeUrl("javascript:alert(1)"), "#");
assert.strictEqual(safeUrl(""), "#");

assert.strictEqual(stamp(-5, 20, false), '<div class="stamp pass"><b>Pass</b><span>-$5.00</span></div>');
assert.strictEqual(stamp(25, 20, false), '<div class="stamp buy"><b>Buy</b><span>+$25.00</span></div>');
assert.strictEqual(stamp(20, 20, true), '<div class="stamp check"><b>Check</b><span>+$20.00</span></div>');
assert.strictEqual(stamp(10, 20, false), '<div class="r-verdict">+$10.00<span>under $20</span></div>');

assert.ok(spread(80, 100, 10, 8, -38).includes("spread-mark"));
assert.ok(!spread(80, 100, 10, 8, -38).includes("seg-profit"));
assert.ok(spread(200, 100, 10, 8, 82).includes("seg-profit"));
assert.ok(!spread(200, 100, 10, 8, 82).includes("spread-mark"));
assert.ok(spread(-5, 100, 10, 8, -123).includes("left:0%"));
console.log("ok");
