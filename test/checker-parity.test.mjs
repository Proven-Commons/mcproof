// Python and JavaScript checkers must agree on every malformed graph (docs/data/RULES.md T1).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { checkGraph } from "../docs/assets/proof-core.js";

const claims = JSON.parse(readFileSync(new URL("../docs/data/claims.json", import.meta.url), "utf8"));
const ROOT = new URL("..", import.meta.url).pathname;
const VERIFY = ["python3", "-I", "-B", join(ROOT, "tools/verify.py"), "--claims"];

function ruleIdsFromErrors(errors) {
  const ids = new Set();
  for (const e of errors) {
    for (const m of String(e).matchAll(/\(R[123]\)/g)) ids.add(m[0].slice(1, -1));
  }
  return [...ids].sort();
}

function ruleIdsFromPython(stderr) {
  const ids = new Set();
  for (const m of stderr.matchAll(/\(R[123]\)/g)) ids.add(m[0].slice(1, -1));
  return [...ids].sort();
}

function pyCheck(doc) {
  const dir = mkdtempSync(join(tmpdir(), "mcproof-parity-"));
  const path = join(dir, "claims.json");
  writeFileSync(path, JSON.stringify(doc));
  const r = spawnSync(VERIFY[0], [...VERIFY.slice(1), path], { encoding: "utf8" });
  return { ok: r.status === 0, stderr: r.stderr || "", stdout: r.stdout || "" };
}

function jsCheck(doc) {
  const r = checkGraph(doc);
  return { ok: r.ok, errors: r.errors, ruleIds: ruleIdsFromErrors(r.errors) };
}

function assertParity(name, doc, { expectOk = false, expectRules = null } = {}) {
  const py = pyCheck(doc);
  const js = jsCheck(doc);
  assert.equal(py.ok, js.ok, `${name}: accept/reject mismatch py=${py.ok} js=${js.ok}`);
  if (expectOk !== undefined && expectOk !== null) {
    assert.equal(js.ok, expectOk, name);
  }
  if (!js.ok) {
    const pyRules = ruleIdsFromPython(py.stderr);
    assert.deepEqual(pyRules, js.ruleIds, `${name}: rule id mismatch py=${pyRules} js=${js.ruleIds}`);
    if (expectRules) {
      for (const rid of expectRules) {
        assert.ok(js.ruleIds.includes(rid), `${name}: expected ${rid} in ${js.ruleIds}`);
      }
    }
  }
}

test("both checkers accept the live claims.json", () => {
  assertParity("live graph", claims, { expectOk: true });
});

const parityCases = [
  {
    name: "empty evidence URL (MC18-01)",
    mutate: (d) => { d.claims.find((c) => c.id === "L1").evidence.push({ label: "empty", url: "" }); },
    expectRules: ["R2"],
  },
  {
    name: "kind as list (MC18-01)",
    mutate: (d) => { d.claims.find((c) => c.id === "A1").kind = ["axiom"]; },
    expectRules: ["R1"],
  },
  {
    name: "bare https evidence (MC18-01)",
    mutate: (d) => { d.claims.find((c) => c.id === "L1").evidence.push({ label: "bare", url: "https://" }); },
    expectRules: ["R2"],
  },
  {
    name: "dotdot relative evidence (MC18-01)",
    mutate: (d) => {
      d.claims.find((c) => c.id === "L1").evidence.push({ label: "traversal", url: "../../../../etc/passwd" });
    },
    expectRules: ["R2"],
  },
  {
    name: "non-list evidence (MC18-01)",
    mutate: (d) => { d.claims.find((c) => c.id === "O1").evidence = "not-a-list"; },
    expectRules: ["R2"],
  },
  {
    name: "relative url trailing newline",
    mutate: (d) => { d.claims.find((c) => c.id === "L1").evidence.push({ label: "nl", url: "docs/x\n" }); },
    expectRules: ["R2"],
  },
  {
    name: "https host vertical tab",
    mutate: (d) => { d.claims.find((c) => c.id === "L1").evidence.push({ label: "vt", url: "https://a\u000bb/x" }); },
    expectRules: ["R2"],
  },
  {
    name: "claim id as list",
    mutate: (d) => { d.claims.find((c) => c.id === "A1").id = []; },
    expectRules: ["R1"],
  },
  {
    name: "claim id as object",
    mutate: (d) => { d.claims.find((c) => c.id === "A1").id = {}; },
    expectRules: ["R1"],
  },
];

for (const { name, mutate, expectRules } of parityCases) {
  test(`parity reject: ${name}`, () => {
    const doc = structuredClone(claims);
    mutate(doc);
    assertParity(name, doc, { expectOk: false, expectRules });
  });
}

const FIELDS = [
  "kind",
  "asserted_tier",
  "section",
  "title",
  "statement",
  "depends_on",
  "evidence",
];
const BAD = [
  ["null", null],
  ["number", 42],
  ["list", ["x"]],
  ["object", { x: 1 }],
];

const TYPE_TARGET = { evidence: "L1", depends_on: "A1" };
const defaultTarget = (field) => TYPE_TARGET[field] || "A1";

for (const field of FIELDS) {
  for (const [label, value] of BAD) {
    test(`parity wrong type ${field}=${label}`, () => {
      const doc = structuredClone(claims);
      const c = doc.claims.find((x) => x.id === defaultTarget(field));
      c[field] = value;
      assertParity(`${field}=${label}`, doc, { expectOk: false });
    });
  }
  if (field === "evidence") continue;
  test(`parity missing ${field}`, () => {
    const doc = structuredClone(claims);
    delete doc.claims.find((x) => x.id === defaultTarget(field))[field];
    assertParity(`missing ${field}`, doc, { expectOk: false });
  });
}

const TRICKY_CHARS = (() => {
  const out = [];
  for (let i = 0; i <= 31; i++) out.push(String.fromCharCode(i));
  out.push(String.fromCharCode(127), "\u00a0", "\u2028", "\uFEFF", "\uFF0F");
  return out;
})();

const URL_INJECT = [
  { name: "relative", mk: (ch) => `docs/path${ch}` },
  { name: "host", mk: (ch) => `https://host${ch}.example/x` },
  { name: "path", mk: (ch) => `https://a/x${ch}` },
];
const STRING_FIELDS = [
  ["kind", "A1", (ch, base) => `${base}${ch}`],
  ["section", "A1", (ch, base) => `${base}${ch}`],
  ["asserted_tier", "A1", (ch, base) => `${base}${ch}`],
];

for (const ch of TRICKY_CHARS) {
  const label = `U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")}`;
  for (const { name, mk } of URL_INJECT) {
    test(`parity fuzz url ${label} in ${name}`, () => {
      const doc = structuredClone(claims);
      const url = mk(ch);
      doc.claims.find((c) => c.id === "L1").evidence.push({ label: "fuzz", url });
      assertParity(`url ${label} ${JSON.stringify(url)}`, doc, { expectOk: false, expectRules: ["R2"] });
    });
  }
  for (const [field, cid, build] of STRING_FIELDS) {
    const base = field === "kind" ? "axiom" : field === "section" ? "axioms" : "KNOWN";
    test(`parity fuzz ${field} ${label}`, () => {
      const doc = structuredClone(claims);
      doc.claims.find((c) => c.id === cid)[field] = build(ch, base);
      assertParity(`${field} ${label}`, doc, { expectOk: false, expectRules: ["R1"] });
    });
  }
}

test("Python rejects missing claims file without traceback", () => {
  const r = spawnSync("python3", ["-I", "-B", join(ROOT, "tools/verify.py"), "--claims", "/no/such/claims.json"], {
    encoding: "utf8",
  });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /FAIL:/);
  assert.doesNotMatch(r.stderr, /Traceback/);
});