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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANK = {"OPEN": 0, "CONJECTURE": 1, "KNOWN": 2, "VERIFIED": 3, "PROVEN": 4}
KINDS = {"axiom", "definition", "lemma", "theorem", "obligation", "hazard"}
SECTIONS = {"axioms", "definitions", "baseline", "theorem", "obligations", "hazards"}
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(:[0-9]+)?$", re.ASCII)
HTTPS_TAIL_RE = re.compile(r"^(/[A-Za-z0-9_./:@%?&=-]*)?([?#][A-Za-z0-9_./:@%?&=-]*)?$", re.ASCII)
REL_URL_RE = re.compile(r"^[A-Za-z0-9_./-]+$", re.ASCII)


def url_ok(url):
    """R2-URL: same rule as docs/assets/proof-core.js urlOk."""
    if not isinstance(url, str) or not url:
        return False
    if url.startswith("//"):
        return False
    if url.startswith("https://"):
        rest = url[8:]
        if not rest:
            return False
        auth_end = len(rest)
        for sep in "/?#":
            i = rest.find(sep)
            if i != -1:
                auth_end = min(auth_end, i)
        authority = rest[:auth_end]
        if not authority or not HOST_RE.fullmatch(authority):
            return False
        tail = rest[auth_end:]
        if tail and not HTTPS_TAIL_RE.fullmatch(tail):
            return False
        return True
    if ".." in url.split("/"):
        return False
    return REL_URL_RE.fullmatch(url) is not None


def fail(errors):
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    print(f"FAIL: {len(errors)} error(s)", file=sys.stderr)
    raise SystemExit(1)


def load(path):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        fail([f"{path}: cannot read ({exc.__class__.__name__})"])
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
            errors.append("claim with missing id (R1)")
            continue
        cid = c["id"]
        if cid in by_id:
            errors.append(f"{cid}: duplicate id")
        kind = c.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            errors.append(f"{cid}: unknown kind {kind!r} (R1)")
        tier = c.get("asserted_tier")
        if not isinstance(tier, str) or tier not in RANK:
            errors.append(f"{cid}: unknown tier {tier!r} (R1)")
        if not ID_RE.match(cid):
            errors.append(f"{cid}: id must match ^[A-Za-z][A-Za-z0-9_-]*$ (R1)")
        if not isinstance(c.get("title"), str) or not c["title"].strip():
            errors.append(f"{cid}: missing title (R1)")
        if not isinstance(c.get("statement"), str) or not c["statement"].strip():
            errors.append(f"{cid}: missing statement (R1)")
        section = c.get("section")
        if not isinstance(section, str) or section not in SECTIONS:
            errors.append(f"{cid}: unknown section {section!r} (R1)")
        if not isinstance(c.get("depends_on"), list):
            errors.append(f"{cid}: depends_on is not a list")
        if "evidence" in c and not isinstance(c.get("evidence"), list):
            errors.append(f"{cid}: evidence is not a list (R2)")
        by_id[cid] = c
    for c in claims:
        cid_raw = c.get("id") if isinstance(c, dict) else None
        if not isinstance(c, dict) or not isinstance(cid_raw, str) or cid_raw not in by_id:
            continue
        cid = cid_raw
        deps = c["depends_on"] if isinstance(c.get("depends_on"), list) else []
        for d in deps:
            if not isinstance(d, str):
                errors.append(f"{cid}: depends_on entries must be strings (R1)")
            elif d not in by_id:
                errors.append(f"{cid}: depends on missing claim {d!r} (R1)")
        if "evidence" in c and not isinstance(c.get("evidence"), list):
            continue
        ev = c["evidence"] if isinstance(c.get("evidence"), list) else []
        for e in ev:
            if not isinstance(e, dict):
                errors.append(f"{cid}: evidence must be {{label, https-or-relative url}} (R2)")
                continue
            label = e.get("label")
            url = e.get("url")
            if not (isinstance(label, str) and label.strip() and url_ok(url)):
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
        if not isinstance(tier, str) or tier not in RANK:
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
    if claims_path.is_dir():
        fail([f"{claims_path}: is a directory"])
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