/* mcproof proof core: pure functions, no DOM, no clock, no randomness.
   Implements docs/data/RULES.md. Tested in Node (test/proof-core.test.mjs)
   and run live in the browser by site.js. Input is the parsed claims.json. */

export const TIER_RANK = { OPEN: 0, CONJECTURE: 1, KNOWN: 2, VERIFIED: 3, PROVEN: 4 };
export const KINDS = ["axiom", "definition", "lemma", "theorem", "obligation", "hazard"];
export const SECTIONS = ["axioms", "definitions", "baseline", "theorem", "obligations", "hazards"];
const URL_OK = (u) => typeof u === "string" && (u.startsWith("https://") || (/^[A-Za-z0-9_./-]+$/.test(u) && !u.startsWith("//")));

export function checkGraph(doc) {
  const errors = [];
  const claims = doc && Array.isArray(doc.claims) ? doc.claims : null;
  if (!claims || claims.length === 0) return { ok: false, errors: ["claims: missing, not a list, or empty (R1)"], computed: Object.create(null), order: [], openObligations: [] };
  const byId = new Map();
  for (const c of claims) {
    if (!c || typeof c.id !== "string" || !c.id) { errors.push("claim with missing id"); continue; }
    if (byId.has(c.id)) errors.push(`${c.id}: duplicate id`);
    if (!KINDS.includes(c.kind)) errors.push(`${c.id}: unknown kind ${JSON.stringify(c.kind)}`);
    if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(c.id)) errors.push(`${c.id}: id must match ^[A-Za-z][A-Za-z0-9_-]*$ (R1)`);
    if (typeof c.title !== "string" || !c.title.trim()) errors.push(`${c.id}: missing title (R1)`);
    if (typeof c.statement !== "string" || !c.statement.trim()) errors.push(`${c.id}: missing statement (R1)`);
    if (!SECTIONS.includes(c.section)) errors.push(`${c.id}: unknown section ${JSON.stringify(c.section)} (R1)`);
    if (!Object.hasOwn(TIER_RANK, c.asserted_tier)) errors.push(`${c.id}: unknown tier ${JSON.stringify(c.asserted_tier)}`);
    if (!Array.isArray(c.depends_on)) errors.push(`${c.id}: depends_on is not a list`);
    byId.set(c.id, c);
  }
  for (const c of claims) {
    if (!c || !byId.has(c.id)) continue;
    for (const d of Array.isArray(c.depends_on) ? c.depends_on : []) {
      if (!byId.has(d)) errors.push(`${c.id}: depends on missing claim ${JSON.stringify(d)}`);
    }
    const ev = Array.isArray(c.evidence) ? c.evidence : [];
    for (const e of ev) {
      if (!e || typeof e !== "object" || typeof e.label !== "string" || !e.label.trim() || !URL_OK(e.url)) {
        errors.push(`${c.id}: evidence must be {label, https-or-relative url} (R2)`);
      }
    }
    for (const d of Array.isArray(c.depends_on) ? c.depends_on : []) {
      if (typeof d !== "string") errors.push(`${c.id}: depends_on entries must be strings (R1)`);
    }
    if ((c.asserted_tier === "VERIFIED" || c.asserted_tier === "PROVEN") && ev.length === 0) {
      errors.push(`${c.id}: asserted ${c.asserted_tier} with no evidence (R2)`);
    }
    if (c.kind === "obligation" && c.asserted_tier === "OPEN" && ev.length > 0) {
      errors.push(`${c.id}: OPEN obligation carries evidence (R2)`);
    }
  }
  // Topological order, deterministic: Kahn with lexicographic tie-break.
  const indeg = new Map(), dependents = new Map();
  for (const id of byId.keys()) { indeg.set(id, 0); dependents.set(id, []); }
  for (const c of byId.values()) {
    for (const d of Array.isArray(c.depends_on) ? c.depends_on : []) {
      if (byId.has(d)) { indeg.set(c.id, indeg.get(c.id) + 1); dependents.get(d).push(c.id); }
    }
  }
  const ready = [...byId.keys()].filter((id) => indeg.get(id) === 0).sort();
  const order = [];
  while (ready.length) {
    const id = ready.shift();
    order.push(id);
    for (const nxt of dependents.get(id).slice().sort()) {
      indeg.set(nxt, indeg.get(nxt) - 1);
      if (indeg.get(nxt) === 0) { ready.push(nxt); ready.sort(); }
    }
  }
  if (order.length !== byId.size) errors.push("dependency graph has a cycle (R1)");

  const computed = Object.create(null);
  for (const id of order) {
    const c = byId.get(id);
    const asserted = TIER_RANK[c.asserted_tier];
    if (asserted === undefined) { computed[id] = "OPEN"; continue; }
    let allowed = asserted;
    if (c.kind !== "axiom" && c.kind !== "definition") {
      const depTiers = (Array.isArray(c.depends_on) ? c.depends_on : [])
        .filter((d) => byId.has(d)).map((d) => ({ id: d, tier: computed[d], rank: TIER_RANK[computed[d]] }));
      if (depTiers.some((d) => d.rank <= 1)) allowed = Math.min(allowed, 1);
      if (c.asserted_tier === "PROVEN") {
        const weak = depTiers.filter((d) => {
          const k = byId.get(d.id).kind;
          return !(d.rank >= 3 || k === "axiom" || k === "definition");
        });
        if (weak.length) allowed = Math.min(allowed, 3);
      }
    }
    if (asserted > allowed) {
      errors.push(`${id}: asserted ${c.asserted_tier} exceeds allowed tier (R3)`);
      computed[id] = "OPEN";
    } else {
      computed[id] = c.asserted_tier;
    }
  }
  const open = order.filter((id) => byId.get(id).kind === "obligation" && computed[id] === "OPEN");
  return { ok: errors.length === 0, errors, computed, order, openObligations: open };
}

/* Deterministic layout of the proof DAG: layer = longest path from a root.
   Same graph, same coordinates, on every machine. */
export function layoutGraph(doc, order) {
  const byId = new Map(doc.claims.map((c) => [c.id, c]));
  const layer = {};
  for (const id of order) {
    const deps = (byId.get(id).depends_on || []).filter((d) => byId.has(d));
    layer[id] = deps.length ? Math.max(...deps.map((d) => layer[d])) + 1 : 0;
  }
  const rows = new Map();
  for (const id of order) {
    if (!rows.has(layer[id])) rows.set(layer[id], []);
    rows.get(layer[id]).push(id);
  }
  const pos = {};
  for (const [lv, ids] of rows) ids.forEach((id, i) => { pos[id] = { layer: lv, index: i, rowSize: ids.length }; });
  return { pos, layers: rows.size };
}

/* Seeded PRNG (mulberry32) so the decorative weave is a function of the
   graph hash, never of the clock. Seed from the first 8 hex chars of a hash. */
export function seededRand(seedHex) {
  let a = parseInt(String(seedHex).slice(0, 8), 16) >>> 0;
  if (!Number.isFinite(a)) a = 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* Style as a point in space, after Eido's aesthetic mixer: linear tokens
   average linearly, hue averages on the circle so 0.95 and 0.05 stay red. */
export function mixPresets(presets, weights) {
  const out = {};
  let hx = 0, hy = 0, total = 0;
  for (const [name, w] of Object.entries(weights)) {
    const p = presets[name];
    if (!p || !(w > 0)) continue;
    total += w;
    for (const [k, v] of Object.entries(p)) {
      if (k === "hue") { hx += w * Math.cos(v * 2 * Math.PI); hy += w * Math.sin(v * 2 * Math.PI); }
      else out[k] = (out[k] || 0) + w * v;
    }
  }
  if (total === 0) return out;
  for (const k of Object.keys(out)) out[k] /= total;
  let hue = Math.atan2(hy, hx) / (2 * Math.PI);
  out.hue = ((hue % 1) + 1) % 1;
  return out;
}
