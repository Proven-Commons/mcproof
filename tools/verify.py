#!/usr/bin/env python3
"""Independent checker for the mcproof claim graph (docs/data/RULES.md).

Shares no code with docs/assets/proof-core.js. No floats decide any
verdict; tier ranks are ints. Safe under python3 -O (no bare assert
carries a verdict; failures raise SystemExit with a message).

Usage:
  python3 tools/verify.py [--claims PATH] [--write-certificate]
Exit 0 and print CERTIFICATE sha256 on success; exit 1 listing every
error on failure.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANK = {"OPEN": 0, "CONJECTURE": 1, "KNOWN": 2, "VERIFIED": 3, "PROVEN": 4}
KINDS = {"axiom", "definition", "lemma", "theorem", "obligation", "hazard"}
SECTIONS = {"axioms", "definitions", "baseline", "theorem", "obligations", "hazards"}
ID_RE = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def fail(errors):
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    print(f"FAIL: {len(errors)} error(s)", file=sys.stderr)
    raise SystemExit(1)


def load(path):
    raw = path.read_bytes()
    def no_dupes(pairs):
        seen = {}
        for k, v in pairs:
            if k in seen:
                raise ValueError(f"duplicate JSON key {k!r}")
            seen[k] = v
        return seen
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=no_dupes)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        fail([f"{path.name}: not valid UTF-8 JSON ({exc.__class__.__name__})"])
    return raw, doc


def check(doc):
    errors = []
    claims = doc.get("claims") if isinstance(doc, dict) else None
    if not isinstance(claims, list) or not claims:
        return ["claims: missing, not a list, or empty (R1)"], {}, []
    by_id = {}
    for c in claims:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c.get("id"):
            errors.append("claim with missing id")
            continue
        cid = c["id"]
        if cid in by_id:
            errors.append(f"{cid}: duplicate id")
        if c.get("kind") not in KINDS:
            errors.append(f"{cid}: unknown kind {c.get('kind')!r}")
        if c.get("asserted_tier") not in RANK:
            errors.append(f"{cid}: unknown tier {c.get('asserted_tier')!r}")
        if not ID_RE.match(cid):
            errors.append(f"{cid}: id must match ^[A-Za-z][A-Za-z0-9_-]*$ (R1)")
        if not isinstance(c.get("title"), str) or not c["title"].strip():
            errors.append(f"{cid}: missing title (R1)")
        if not isinstance(c.get("statement"), str) or not c["statement"].strip():
            errors.append(f"{cid}: missing statement (R1)")
        if c.get("section") not in SECTIONS:
            errors.append(f"{cid}: unknown section {c.get('section')!r} (R1)")
        if not isinstance(c.get("depends_on"), list):
            errors.append(f"{cid}: depends_on is not a list")
        by_id[cid] = c
    for c in claims:
        if not isinstance(c, dict) or c.get("id") not in by_id:
            continue
        cid = c["id"]
        deps = c["depends_on"] if isinstance(c.get("depends_on"), list) else []
        for d in deps:
            if not isinstance(d, str):
                errors.append(f"{cid}: depends_on entries must be strings (R1)")
            elif d not in by_id:
                errors.append(f"{cid}: depends on missing claim {d!r}")
        ev = c["evidence"] if isinstance(c.get("evidence"), list) else []
        for e in ev:
            url = e.get("url") if isinstance(e, dict) else None
            label = e.get("label") if isinstance(e, dict) else None
            url_ok = isinstance(url, str) and (url.startswith("https://") or
                      (all(ch.isalnum() or ch in "_./-" for ch in url) and not url.startswith("//")))
            if not (isinstance(label, str) and label.strip() and url_ok):
                errors.append(f"{cid}: evidence must be {{label, https-or-relative url}} (R2)")
        if c.get("asserted_tier") in ("VERIFIED", "PROVEN") and not ev:
            errors.append(f"{cid}: asserted {c['asserted_tier']} with no evidence (R2)")
        if c.get("kind") == "obligation" and c.get("asserted_tier") == "OPEN" and ev:
            errors.append(f"{cid}: OPEN obligation carries evidence (R2)")
    # Kahn topological order, lexicographic tie-break (deterministic).
    indeg = {i: 0 for i in by_id}
    dependents = {i: [] for i in by_id}
    for c in by_id.values():
        for d in c["depends_on"] if isinstance(c.get("depends_on"), list) else []:
            if isinstance(d, str) and d in by_id:
                indeg[c["id"]] += 1
                dependents[d].append(c["id"])
    ready = sorted(i for i, n in indeg.items() if n == 0)
    order = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in sorted(dependents[nid]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
                ready.sort()
    if len(order) != len(by_id):
        errors.append("dependency graph has a cycle (R1)")
    computed = {}
    for cid in order:
        c = by_id[cid]
        tier = c.get("asserted_tier")
        if tier not in RANK:
            computed[cid] = "OPEN"
            continue
        allowed = RANK[tier]
        if c.get("kind") not in ("axiom", "definition"):
            deps = [d for d in c["depends_on"] if isinstance(d, str) and d in by_id] if isinstance(c.get("depends_on"), list) else []
            if any(RANK[computed[d]] <= 1 for d in deps):
                allowed = min(allowed, 1)
            if tier == "PROVEN":
                weak = [d for d in deps
                        if not (RANK[computed[d]] >= 3 or by_id[d].get("kind") in ("axiom", "definition"))]
                if weak:
                    allowed = min(allowed, 3)
        if RANK[tier] > allowed:
            errors.append(f"{cid}: asserted {tier} exceeds allowed tier (R3)")
            computed[cid] = "OPEN"
        else:
            computed[cid] = tier
    open_obligations = [i for i in order if by_id[i].get("kind") == "obligation" and computed.get(i) == "OPEN"]
    return errors, computed, open_obligations


def certificate(raw, computed, open_obligations):
    lines = [f"{cid}>{computed[cid]}" for cid in sorted(computed)]
    graph_hash = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    cert = {
        "schema": "mcproof/certificate/v1",
        "claims_sha256": hashlib.sha256(raw).hexdigest(),
        "graph_sha256": graph_hash,
        "claim_count": len(computed),
        "computed_tiers": {cid: computed[cid] for cid in sorted(computed)},
        "open_obligations": sorted(open_obligations),
        "verdict": "CHECKED",
        "rules": "docs/data/RULES.md",
        "checker": "tools/verify.py",
    }
    return (json.dumps(cert, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv):
    claims_path = ROOT / "docs" / "data" / "claims.json"
    write = False
    i = 1
    while i < len(argv):
        if argv[i] == "--claims" and i + 1 < len(argv):
            claims_path = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--write-certificate":
            write = True
            i += 1
        else:
            fail([f"unknown argument {argv[i]!r}"])
    raw, doc = load(claims_path)
    errors, computed, open_obligations = check(doc)
    if errors:
        fail(errors)
    cert_bytes = certificate(raw, computed, open_obligations)
    if write:
        out = ROOT / "docs" / "data" / "certificate.json"
        out.write_bytes(cert_bytes)
        print(f"wrote {out.relative_to(ROOT)}")
    print(f"OK claims={len(computed)} open_obligations={len(open_obligations)}")
    print(f"CERTIFICATE sha256:{hashlib.sha256(cert_bytes).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
