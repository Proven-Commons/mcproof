/* mcproof site runtime. Everything visual is a function of data/claims.json:
   the verdict, the claim tiers, the DAG figure, the weave, and the first
   position of the style point. No clock-based randomness anywhere. */
import { checkGraph, layoutGraph, mixPresets, seededRand } from "./proof-core.js";

const root = document.documentElement;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const motionOn = () => root.getAttribute("data-motion") !== "off";

let DOC = null, CERT = null, LIVE = null; // parsed claims, certificate, live result

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function cssVar(name) {
  return getComputedStyle(root).getPropertyValue(name).trim();
}

/* ---------- the live proof ---------- */
function renderVerdict(result, hashOk, certOk) {
  const box = $("[data-verdict]"), text = $("[data-verdict-text]"), facts = $("[data-verdict-facts]");
  const qed = $("[data-qed]");
  facts.textContent = "";
  const add = (msg, cls) => { const li = document.createElement("li"); li.textContent = msg; if (cls) li.className = cls; facts.append(li); };
  if (result.ok && hashOk && certOk) {
    box.dataset.state = "pass"; qed.textContent = "∎";
    text.textContent = "Q.E.D. for this page: the claim graph checks, and it is the graph CI certified.";
    add(`${Object.keys(result.computed).length} claims recomputed in this tab; tiers match docs/data/certificate.json claim by claim.`);
    add(`claims.json SHA-256 in this tab matches the certificate (${CERT.claims_sha256.slice(0, 16)}…).`);
    add(`Open obligations: ${result.openObligations.join(", ")}. Theorem T0 therefore computes to ${result.computed.T0}, and cannot rise until they close.`);
  } else {
    box.dataset.state = "fail"; qed.textContent = "✗";
    text.textContent = "Proof refused. The checker rejects this graph, and so would CI: this page could not publish in this state.";
    for (const e of result.errors) add(e, "bad-item");
    if (!hashOk) add("claims.json hash differs from the certificate.", "bad-item");
    if (!certOk) add("computed tiers differ from the certificate.", "bad-item");
  }
  // Mirror computed tiers onto the printed claims.
  for (const el of $$("[data-claim]")) {
    const t = result.computed[el.dataset.claim];
    el.classList.toggle("live-fail", Boolean(t && el.dataset.tier !== t));
    if (t) el.dataset.tier = t;
  }
  const foot = $("[data-foot-seal]");
  if (foot) foot.textContent = result.ok && hashOk && certOk
    ? `Live check in this tab: pass, graph sha256:${CERT.graph_sha256.slice(0, 16)}….`
    : "Live check in this tab: fail, see the proof state panel.";
}

function runCheck(doc, rawText) {
  const result = checkGraph(doc);
  LIVE = result;
  const done = (hashOk) => {
    const certOk = CERT && JSON.stringify(
      Object.fromEntries(Object.entries(result.computed).sort())) ===
      JSON.stringify(Object.fromEntries(Object.entries(CERT.computed_tiers).sort()));
    renderVerdict(result, hashOk, certOk);
    drawDag(doc, result);
  };
  if (rawText && CERT && window.crypto?.subtle) {
    sha256Hex(rawText).then((h) => done(h === CERT.claims_sha256)).catch(() => done(false));
  } else {
    done(rawText == null ? false : true); // tampered in-memory copy: hash cannot match
  }
  return result;
}

/* ---------- the Derivation figure ---------- */
const TIER_COLOR = () => ({
  PROVEN: cssVar("--ok"), VERIFIED: cssVar("--ok"), KNOWN: cssVar("--acc"),
  CONJECTURE: cssVar("--warn"), OPEN: cssVar("--bad"),
});
let dagNodes = [];
function drawDag(doc, result) {
  const canvas = $("#dag-canvas");
  if (!canvas || !result.order.length) return;
  const { pos, layers } = layoutGraph(doc, result.order);
  const byId = new Map(doc.claims.map((c) => [c.id, c]));
  const W = 900, H = 640, dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.aspectRatio = `${W} / ${H}`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const colors = TIER_COLOR(), ink = cssVar("--ink"), ink3 = cssVar("--ink-3"), line = cssVar("--line");
  const xy = (id) => {
    const p = pos[id];
    return { x: 46 + (W - 92) * (layers <= 1 ? 0 : p.layer / (layers - 1)),
             y: 30 + (H - 60) * (p.rowSize <= 1 ? 0.5 : p.index / (p.rowSize - 1)) };
  };
  dagNodes = result.order.map((id) => ({ id, ...xy(id), tier: result.computed[id], title: byId.get(id).title }));
  ctx.lineWidth = 1;
  for (const c of doc.claims) {
    for (const d of c.depends_on || []) {
      if (!pos[d] || !pos[c.id]) continue;
      const a = xy(d), b = xy(c.id);
      ctx.strokeStyle = line;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.bezierCurveTo(a.x + 34, a.y, b.x - 34, b.y, b.x, b.y);
      ctx.stroke();
    }
  }
  ctx.font = "600 11px ui-monospace, Menlo, monospace";
  ctx.textAlign = "center";
  dagNodes.forEach((n, i) => {
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.id === "T0" ? 13 : 9, 0, Math.PI * 2);
    ctx.fillStyle = colors[n.tier] || ink3;
    ctx.fill();
    ctx.fillStyle = ink;
    // Alternate label side in dense layers so ids never overlap.
    const dy = n.id === "T0" ? -19 : (i % 2 === 0 ? -15 : 22);
    ctx.fillText(n.id, n.x, n.y + dy);
  });
  const out = $("[data-dag-readout]");
  if (out) out.textContent = `${dagNodes.length} claims · ${layers} layers deep`;
  canvas.onpointermove = (ev) => {
    const r = canvas.getBoundingClientRect();
    const x = (ev.clientX - r.left) * (W / r.width), y = (ev.clientY - r.top) * (H / r.height);
    const hit = dagNodes.find((n) => (n.x - x) ** 2 + (n.y - y) ** 2 < 15 ** 2);
    canvas.style.cursor = hit ? "pointer" : "default";
    if (out) out.textContent = hit ? `${hit.id} · ${hit.tier} · ${hit.title}` : `${dagNodes.length} claims · ${layers} layers deep`;
    canvas.onclick = hit ? () => document.getElementById(`claim-${hit.id}`)?.scrollIntoView({ behavior: motionOn() ? "smooth" : "auto" }) : null;
  };
}

/* ---------- the weave: harmonics seeded by the graph hash (after Eido's loom) ---------- */
let weave = null;
function startWeave(seedHex) {
  const canvas = $("#weave");
  if (!canvas) return;
  const rand = seededRand(seedHex || "0");
  const threads = Array.from({ length: 22 }, (_, i) => ({
    base: i / 21, a1: 4 + rand() * 9, f1: 1.3 + rand() * 2.2, p1: rand() * Math.PI * 2,
    a2: 2 + rand() * 5, f2: 3.1 + rand() * 3.4, p2: rand() * Math.PI * 2,
  }));
  const frame = (t) => {
    const r = canvas.parentElement.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(r.width * dpr)) { canvas.width = r.width * dpr; canvas.height = r.height * dpr; }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    ctx.strokeStyle = cssVar("--acc");
    ctx.globalAlpha = 0.16;
    ctx.lineWidth = 1;
    for (const th of threads) {
      ctx.beginPath();
      for (let x = 0; x <= r.width; x += 6) {
        const u = x / r.width;
        const y = th.base * r.height
          + Math.sin(u * th.f1 * Math.PI * 2 + th.p1 + t) * th.a1
          + Math.sin(u * th.f2 * Math.PI * 2 + th.p2 - t * 0.6) * th.a2;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  };
  if (weave) cancelAnimationFrame(weave.raf);
  weave = { raf: 0 };
  if (!motionOn()) { frame(0); return; }
  const t0 = performance.now();
  const tick = () => { frame((performance.now() - t0) / 2400); weave.raf = requestAnimationFrame(tick); };
  tick();
}

/* ---------- style as a point in space (Eido) ---------- */
const PRESETS = {
  formal:  { hue: 0.58, density: 0.86, rounding: 0.06, contrast: 0.03 },
  loom:    { hue: 0.47, density: 1.04, rounding: 0.5,  contrast: 0.0 },
  radiant: { hue: 0.12, density: 1.18, rounding: 0.92, contrast: -0.02 },
};
const VERT = { formal: [110, 14], loom: [14, 178], radiant: [206, 178] };
let proofPoint = { formal: 1 / 3, loom: 1 / 3, radiant: 1 / 3 };
let point = { ...proofPoint };

function applyPoint(w, why) {
  point = { ...w };
  const s = mixPresets(PRESETS, w);
  root.style.setProperty("--hue", String(s.hue));
  root.style.setProperty("--density", String(s.density));
  root.style.setProperty("--rounding", String(s.rounding));
  root.style.setProperty("--contrast", String(s.contrast));
  const dot = $("[data-simplex-dot]");
  if (dot) {
    dot.setAttribute("cx", String(w.formal * VERT.formal[0] + w.loom * VERT.loom[0] + w.radiant * VERT.radiant[0]));
    dot.setAttribute("cy", String(w.formal * VERT.formal[1] + w.loom * VERT.loom[1] + w.radiant * VERT.radiant[1]));
  }
  const label = `Formal ${Math.round(w.formal * 100)}%, Loom ${Math.round(w.loom * 100)}%, Radiant ${Math.round(w.radiant * 100)}%`;
  const out = $("[data-mixer-out]");
  if (out) out.textContent = why ? `${label} (${why})` : label;
  $("#simplex")?.setAttribute("aria-valuetext", label);
  if (DOC && LIVE) drawDag(DOC, LIVE);
}

function barycentric(x, y) {
  const [ax, ay] = VERT.formal, [bx, by] = VERT.loom, [cx, cy] = VERT.radiant;
  const den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
  let a = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den;
  let b = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den;
  let c = 1 - a - b;
  a = Math.max(0, a); b = Math.max(0, b); c = Math.max(0, c);
  const s = a + b + c || 1;
  return { formal: a / s, loom: b / s, radiant: c / s };
}

function setupSimplex() {
  const svg = $("#simplex");
  if (!svg) return;
  const move = (ev) => {
    const r = svg.getBoundingClientRect();
    applyPoint(barycentric((ev.clientX - r.left) * (220 / r.width), (ev.clientY - r.top) * (200 / r.height)), "your point");
  };
  svg.addEventListener("pointerdown", (ev) => { svg.setPointerCapture(ev.pointerId); move(ev); });
  svg.addEventListener("pointermove", (ev) => { if (ev.buttons) move(ev); });
  svg.addEventListener("keydown", (ev) => {
    const step = 0.06, w = { ...point };
    if (ev.key === "ArrowUp") { w.formal += step; w.loom -= step / 2; w.radiant -= step / 2; }
    else if (ev.key === "ArrowLeft") { w.loom += step; w.formal -= step / 2; w.radiant -= step / 2; }
    else if (ev.key === "ArrowRight") { w.radiant += step; w.formal -= step / 2; w.loom -= step / 2; }
    else if (ev.key === "ArrowDown") { w.formal -= step; w.loom += step / 2; w.radiant += step / 2; }
    else return;
    ev.preventDefault();
    for (const k of Object.keys(w)) w[k] = Math.max(0, w[k]);
    const s = w.formal + w.loom + w.radiant || 1;
    applyPoint({ formal: w.formal / s, loom: w.loom / s, radiant: w.radiant / s }, "your point");
  });
  $("[data-mixer-reset]")?.addEventListener("click", () => applyPoint(proofPoint, "the proof point, from the graph hash"));
}

/* ---------- header tools ---------- */
function setupTools() {
  const themeBtn = $("[data-theme-toggle]");
  themeBtn?.addEventListener("click", () => {
    const dark = root.getAttribute("data-theme") === "dark" ||
      (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = dark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("mcproof-theme", next); } catch { /* private mode */ }
    if (DOC && LIVE) drawDag(DOC, LIVE);
    if (CERT) startWeave(CERT.graph_sha256);
  });
  const motionBtn = $("[data-motion-toggle]");
  const syncMotion = () => motionBtn?.setAttribute("aria-pressed", String(motionOn()));
  syncMotion();
  motionBtn?.addEventListener("click", () => {
    const next = motionOn() ? "off" : "on";
    root.setAttribute("data-motion", next);
    root.setAttribute("data-motion-pref", next);
    try { localStorage.setItem("mcproof-motion", next); } catch { /* private mode */ }
    syncMotion();
    if (CERT) startWeave(CERT.graph_sha256);
  });
  // Tamper demo: Hazard-grade corruption, in memory only.
  const tamper = $("[data-tamper]"), restore = $("[data-restore]"), note = $("[data-tamper-note]");
  tamper?.addEventListener("click", () => {
    const bad = structuredClone(DOC);
    bad.claims.find((c) => c.id === "O1").depends_on.push("T0");
    runCheck(bad, null);
    tamper.hidden = true; restore.hidden = false; note.hidden = false;
  });
  restore?.addEventListener("click", () => {
    init();
    tamper.hidden = false; restore.hidden = true; note.hidden = true;
  });
  // Copy the agent line.
  $$("[data-copy]").forEach((btn) => btn.addEventListener("click", async () => {
    const src = document.getElementById(btn.dataset.copy);
    const said = btn.parentElement?.querySelector(".ab-said");
    try { await navigator.clipboard.writeText(src.textContent.trim()); if (said) said.textContent = "Copied."; }
    catch { if (said) said.textContent = "Copy failed: select the line by hand."; }
  }));
  setupCondense();
}

/* Condense plain prose; refuse proof blocks (Hazard H7, data-eido-skip). */
function setupCondense() {
  const btn = $("[data-condense-toggle]");
  if (!btn) return;
  const originals = new Map();
  let condensed = null, on = false;
  btn.addEventListener("click", async () => {
    if (!condensed) {
      try { condensed = await (await fetch("condensed.json")).json(); }
      catch { btn.textContent = "Condense (unavailable)"; return; }
    }
    on = !on;
    btn.setAttribute("aria-pressed", String(on));
    for (const el of $$("[data-condense]")) {
      if (el.closest("[data-eido-skip]")) continue;
      if (!originals.has(el)) originals.set(el, el.innerHTML);
      el.innerHTML = on && condensed[el.dataset.condense] ? condensed[el.dataset.condense] : originals.get(el);
    }
    for (const el of $$("[data-eido-skip]")) {
      el.classList.remove("condense-refused");
      if (on) { void el.offsetWidth; el.classList.add("condense-refused"); }
    }
    btn.textContent = on ? "Condense (proof blocks refused)" : "Condense";
  });
}

/* ---------- boot ---------- */
async function init() {
  const text = $("[data-verdict-text]");
  try {
    const [claimsRes, certRes] = await Promise.all([fetch("data/claims.json"), fetch("data/certificate.json")]);
    const raw = await claimsRes.text();
    DOC = JSON.parse(raw);
    CERT = await certRes.json();
    runCheck(DOC, raw);
    // The proof point: first three bytes of the graph hash, normalised.
    const b = [0, 2, 4].map((i) => parseInt(CERT.graph_sha256.slice(i, i + 2), 16) + 32);
    const sum = b[0] + b[1] + b[2];
    proofPoint = { formal: b[0] / sum, loom: b[1] / sum, radiant: b[2] / sum };
    applyPoint(proofPoint, "the proof point, from the graph hash");
    startWeave(CERT.graph_sha256);
  } catch (err) {
    if (text) text.textContent = `Could not load the claim graph (${err.name}). The printed claims below were baked at build time and stand as published.`;
  }
}
setupSimplex();
setupTools();
applyPoint(proofPoint, "loading");
init();
let resizeT;
addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (DOC && LIVE) drawDag(DOC, LIVE); if (CERT) startWeave(CERT.graph_sha256); }, 200); });
