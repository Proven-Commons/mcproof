#!/usr/bin/env python3
"""Deterministic prerender: bake claims.json into docs/index.html.

Replaces the regions between <!--prerender:NAME--> ... <!--/prerender:NAME-->
markers with HTML computed from docs/data/claims.json and the certificate
from tools/verify.py. No timestamps, no environment reads: the same input
gives the same bytes. CI builds twice and diffs to prove it.

Run tools/verify.py --write-certificate first (or pass --verify to do both).
"""
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import verify as checker  # noqa: E402

KIND_WORD = {"axiom": "Axiom", "definition": "Definition", "lemma": "Lemma",
             "theorem": "Theorem", "obligation": "Obligation", "hazard": "Hazard guard"}
TIER_WORD = {"OPEN": "Open", "CONJECTURE": "Conjecture", "KNOWN": "Known",
             "VERIFIED": "Verified", "PROVEN": "Proven"}
TIER_RUNG = {"OPEN": 0, "CONJECTURE": 1, "KNOWN": 2, "VERIFIED": 4, "PROVEN": 5}
SECTIONS = ["axioms", "definitions", "baseline", "theorem", "obligations", "hazards"]


def esc(s):
    return html.escape(str(s), quote=True)


def ladder(tier):
    rung = TIER_RUNG[tier]
    cells = "".join("<i></i>" for _ in range(5))
    return f'<span class="ladder" data-r="{rung}" aria-hidden="true">{cells}</span>'


def claim_html(c, computed, by_id):
    tier = computed[c["id"]]
    deps = [d for d in c["depends_on"] if d in by_id]
    dep_html = ""
    if deps:
        links = ", ".join(f'<a href="#claim-{esc(d)}">{esc(d)}</a>' for d in deps)
        dep_html = f'<p class="deps"><span>Uses</span> {links}</p>'
    ev_html = ""
    ev = c.get("evidence") if isinstance(c.get("evidence"), list) else []
    if ev:
        items = "".join(
            f'<li><a href="{esc(e.get("url", "#"))}">{esc(e.get("label", "source"))}</a></li>'
            for e in ev if isinstance(e, dict))
        ev_html = f'<div class="evid"><span>Evidence</span><ul>{items}</ul></div>'
    return (
        f'<article class="claim" id="claim-{esc(c["id"])}" data-claim="{esc(c["id"])}" '
        f'data-kind="{esc(c["kind"])}" data-tier="{esc(tier)}" data-eido-skip>\n'
        f'<header><span class="cid">{esc(KIND_WORD[c["kind"]])} {esc(c["id"])}</span>'
        f'<span class="tier">{ladder(tier)}{esc(TIER_WORD[tier])}</span></header>\n'
        f'<h3>{esc(c["title"])}</h3>\n<p>{esc(c["statement"])}</p>\n{dep_html}{ev_html}</article>'
    )


def replace_region(text, name, body):
    open_m = f"<!--prerender:{name}-->"
    close_m = f"<!--/prerender:{name}-->"
    if open_m not in text or close_m not in text:
        raise SystemExit(f"FAIL: prerender markers for {name!r} not found in index.html")
    head, rest = text.split(open_m, 1)
    _, tail = rest.split(close_m, 1)
    return head + open_m + body + close_m + tail


def main(argv):
    do_verify = "--verify" in argv
    claims_path = ROOT / "docs" / "data" / "claims.json"
    raw, doc = checker.load(claims_path)
    errors, computed, open_obligations = checker.check(doc)
    if errors:
        checker.fail(errors)
    cert_bytes = checker.certificate(raw, computed, open_obligations)
    if do_verify:
        (ROOT / "docs" / "data" / "certificate.json").write_bytes(cert_bytes)
    cert = json.loads(cert_bytes.decode("utf-8"))
    claims = doc["claims"]
    by_id = {c["id"]: c for c in claims}
    index = ROOT / "docs" / "index.html"
    text = index.read_text(encoding="utf-8")

    for section in SECTIONS:
        body = "\n".join(claim_html(c, computed, by_id) for c in claims if c.get("section") == section)
        text = replace_region(text, f"claims-{section}", "\n" + body + "\n")

    verified_lemmas = sum(1 for c in claims
                          if c.get("kind") == "lemma" and computed.get(c["id"]) == "VERIFIED")
    stats = (
        f'<div class="stat"><dt>claims in the graph</dt><dd>{len(claims)}</dd></div>'
        f'<div class="stat"><dt>verified lemmas (the baseline)</dt><dd>{verified_lemmas}</dd></div>'
        f'<div class="stat"><dt>open obligations</dt><dd>{len(open_obligations)}</dd></div>'
        f'<div class="stat"><dt>main theorem T0</dt><dd>{TIER_WORD[computed.get("T0", "OPEN")]}</dd></div>'
    )
    text = replace_region(text, "stats", stats)
    seal = (
        f'<span class="seal-hash">claims sha256:{cert["claims_sha256"][:16]}…</span> '
        f'<span class="seal-hash">graph sha256:{cert["graph_sha256"][:16]}…</span>'
    )
    text = replace_region(text, "seal", seal)
    index.write_text(text, encoding="utf-8")
    print(f"OK prerendered {len(claims)} claims, open={len(open_obligations)}, "
          f"T0={computed.get('T0')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
