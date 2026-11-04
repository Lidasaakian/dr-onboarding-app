// Checks static/assets/format.js against the step-formatting spec. Run by tests/test_format.py (needs Node).
const assert = require("assert");
const F = require("../static/assets/format.js");
const flat = (n) => n.map((x) => (x.t === "text" ? x.v : x.t === "code" ? `<code>${x.v}</code>` : `<${x.t}${x.href ? " " + x.href : ""}>${flat(x.c)}</${x.t}>`)).join("");

let b = F.parse("Intro line\n- one\n- two\n- three");
assert.deepStrictEqual(b.map((x) => x.type), ["p", "ul"]);
assert.strictEqual(b[1].items.length, 3);

b = F.parse("1. Open Console\n2. Pick a deployment");
assert.strictEqual(b[0].type, "ol");
assert.deepStrictEqual(b[0].items.map(flat), ["Open Console", "Pick a deployment"]);

b = F.parse("- [ ] Install\n- [x] Sign in\nAfter\n- [ ] Lab");
assert.deepStrictEqual(b.map((x) => x.type), ["check", "p", "check"]);
assert.deepStrictEqual(b[0].items.map((i) => [i.checked, i.index]), [[false, 0], [true, 1]]);
assert.strictEqual(b[2].items[0].index, 2);

assert.strictEqual(flat(F.inline("see [the docs](https://docs.datarobot.com/)")), "see <a https://docs.datarobot.com/>the docs</a>");
assert.strictEqual(flat(F.inline("**Required:** read *all* of it")), "<b>Required:</b> read <i>all</i> of it");
assert.strictEqual(flat(F.inline("5 * 3 * 2")), "5 * 3 * 2");
assert.strictEqual(flat(F.inline("run `dr start` now")), "run <code>dr start</code> now");
assert.strictEqual(flat(F.inline("open https://app.datarobot.com/x.")), "open <a https://app.datarobot.com/x>https://app.datarobot.com/x</a>.");

// nothing runs as code
assert.strictEqual(flat(F.inline('<img src=x onerror=alert(1)>')), '<img src=x onerror=alert(1)>');
assert.ok(F.inline('<img src=x onerror=alert(1)>').every((n) => n.t === "text"));
assert.ok(F.inline("[click](javascript:alert(1))").every((n) => n.t !== "a"));
assert.strictEqual(flat(F.inline("[click](javascript:alert(1))")), "[click](javascript:alert(1))");

assert.strictEqual(F.plain("See [the docs](https://x.y/z) and **this**\n- a\n- b"), "See the docs and this a; b");
console.log("format ok");
