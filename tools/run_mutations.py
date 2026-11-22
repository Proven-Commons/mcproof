#!/usr/bin/env python3
"""Planted-bug suite: corrupt the claim graph seventeen ways and require
tools/verify.py to reject every corruption. Modeled on the f0 gate
corruption suite. A checker that passes a corrupted graph is the bug.
"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "data" / "claims.json"
VERIFY = [sys.executable, "-I", "-B", str(ROOT / "tools" / "verify.py"), "--claims"]


def mutations(doc):
    def m(name, fn):
        d = copy.deepcopy(doc)
        fn(d)
        return name, d
    yield m("inflate T0 to PROVEN", lambda d: claim(d, "T0").update(asserted_tier="PROVEN"))
    yield m("inflate T0 to VERIFIED", lambda d: claim(d, "T0").update(asserted_tier="VERIFIED"))
    yield m("strip evidence from L1", lambda d: claim(d, "L1").update(evidence=[]))
    yield m("cycle O1->T0", lambda d: claim(d, "O1")["depends_on"].append("T0"))
    yield m("missing dependency", lambda d: claim(d, "L2")["depends_on"].append("ZZ9"))
    yield m("duplicate id", lambda d: d["claims"].append(copy.deepcopy(d["claims"][0])))
    yield m("unknown tier", lambda d: claim(d, "L3").update(asserted_tier="CERTAIN"))
    yield m("unknown kind", lambda d: claim(d, "L4").update(kind="fact"))
    yield m("evidence on OPEN obligation", lambda d: claim(d, "O1").update(
        evidence=[{"label": "x", "url": "https://example.invalid"}]))
    yield m("self dependency", lambda d: claim(d, "D3")["depends_on"].append("D3"))
    yield m("PROVEN over a merely KNOWN dependency", lambda d: d["claims"].append({
        "id": "X1", "kind": "lemma", "section": "baseline", "title": "x", "statement": "x",
        "asserted_tier": "PROVEN", "depends_on": ["H3"],
        "evidence": [{"label": "x", "url": "https://example.invalid"}]}))
    yield m("empty claim list entry", lambda d: d["claims"].append({}))
    yield m("javascript: evidence URL", lambda d: claim(d, "L1")["evidence"].append(
        {"label": "x", "url": "javascript:alert(1)"}))
    yield m("evidence with no label", lambda d: claim(d, "L1")["evidence"].append({"url": "https://example.invalid"}))
    yield m("missing title", lambda d: claim(d, "L1").pop("title"))
    yield m("unknown section vanishes claim", lambda d: claim(d, "L1").update(section="appendix"))
    yield m("prototype-name tier", lambda d: claim(d, "L1").update(asserted_tier="constructor"))


def claim(doc, cid):
    for c in doc["claims"]:
        if c.get("id") == cid:
            return c
    raise KeyError(cid)


def main():
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    cases = list(mutations(doc))
    killed = 0
    with tempfile.TemporaryDirectory() as td:
        for name, mutated in cases:
            p = Path(td) / "claims.json"
            p.write_text(json.dumps(mutated), encoding="utf-8")
            r = subprocess.run(VERIFY + [str(p)], capture_output=True, text=True)
            dead = r.returncode != 0
            killed += 1 if dead else 0
            print(f"{'killed ' if dead else 'SURVIVED'} {name}")
    print(f"{killed}/{len(cases)} corruptions rejected")
    if killed != len(cases):
        print("FAIL: a corrupted graph passed the checker", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
