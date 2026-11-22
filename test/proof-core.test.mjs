// Node tests for the browser checker. Run: node --test test/
// The load-bearing case: given the real claims.json, the JavaScript checker
// must agree with the Python certificate claim by claim.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { checkGraph, layoutGraph, mixPresets, seededRand } from "../docs/assets/proof-core.js";

const claims = JSON.parse(readFileSync(new URL("../docs/data/claims.json", import.meta.url), "utf8"));
const cert = JSON.parse(readFileSync(new URL("../docs/data/certificate.json", import.meta.url), "utf8"));

test("JS checker accepts the real graph", () => {
  const r = checkGraph(claims);
  assert.deepEqual(r.errors, []);
  assert.equal(r.ok, true);
});

test("JS computed tiers equal the Python certificate", () => {
  const r = checkGraph(claims);
  assert.deepEqual({ ...r.computed }, cert.computed_tiers);
  assert.deepEqual([...r.openObligations].sort(), cert.open_obligations);
});

test("T0 stays a conjecture while obligations are open", () => {
  const r = checkGraph(claims);
  assert.equal(r.computed.T0, "CONJECTURE");
});

test("tier inflation is rejected", () => {
  const bad = structuredClone(claims);
  bad.claims.find((c) => c.id === "T0").asserted_tier = "PROVEN";
  const r = checkGraph(bad);
  assert.equal(r.ok, false);
  assert.match(r.errors.join(" "), /T0.*R3/);
});

test("cycle is rejected", () => {
  const bad = structuredClone(claims);
  bad.claims.find((c) => c.id === "O1").depends_on.push("T0");
  assert.equal(checkGraph(bad).ok, false);
});

test("layout is deterministic and layered after dependencies", () => {
  const r = checkGraph(claims);
  const a = layoutGraph(claims, r.order);
  const b = layoutGraph(claims, r.order);
  assert.deepEqual(a, b);
  for (const c of claims.claims) {
    for (const d of c.depends_on) assert.ok(a.pos[d].layer < a.pos[c.id].layer, `${d} before ${c.id}`);
  }
});

test("hue mixes on the circle: red plus red stays red", () => {
  const m = mixPresets(
    { a: { hue: 0.95, density: 0.2 }, b: { hue: 0.05, density: 0.4 } },
    { a: 0.5, b: 0.5 });
  assert.ok(m.hue < 0.02 || m.hue > 0.98, `hue ${m.hue} should be red, not cyan`);
  assert.ok(Math.abs(m.density - 0.3) < 1e-9);
});

test("seeded randomness repeats exactly", () => {
  const r1 = seededRand("4e00656c"), r2 = seededRand("4e00656c");
  assert.deepEqual([r1(), r1(), r1()], [r2(), r2(), r2()]);
});

test("prototype names are not tiers or ids", () => {
  const a = structuredClone(claims);
  a.claims.find((c) => c.id === "L1").asserted_tier = "constructor";
  assert.equal(checkGraph(a).ok, false);
  const b = structuredClone(claims);
  b.claims.push({ id: "__proto__", kind: "lemma", section: "baseline", title: "x", statement: "x",
    asserted_tier: "KNOWN", depends_on: [], evidence: [] });
  assert.equal(checkGraph(b).ok, false);
});

test("dangerous evidence URLs and missing titles are rejected", () => {
  const a = structuredClone(claims);
  a.claims.find((c) => c.id === "L1").evidence.push({ label: "x", url: "javascript:alert(1)" });
  assert.equal(checkGraph(a).ok, false);
  const b = structuredClone(claims);
  delete b.claims.find((c) => c.id === "L1").title;
  assert.equal(checkGraph(b).ok, false);
});
