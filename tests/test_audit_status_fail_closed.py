"""An empty or unknown certificate must not come back VERIFIED.

The auditor used to return VERIFIED whenever it found no red-flag field.
A certificate with no status has no such field, so `{}` passed. The same
path relabeled REJECTED and CONJECTURE as VERIFIED.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from mcproof.cli import main as cli_main
from mcproof.domain_protocol import RECOGNIZED_CERT_STATUSES, audit_transition_certificate

from helpers import expect_eq, expect_false, expect_in, expect_true

HEX64 = "a" * 64


def _rules(cert: dict) -> list[str]:
    return [f["rule"] for f in audit_transition_certificate(cert)["findings"]]


def test_empty_certificate_is_rejected() -> None:
    result = audit_transition_certificate({})
    expect_false(result["passed"])
    expect_eq(result["epistemic_status"], "REJECTED")
    expect_in("CERT_STATUS_ABSENT", _rules({}))


def test_unknown_status_is_rejected() -> None:
    cert = {"epistemic_status": "BANANA"}
    result = audit_transition_certificate(cert)
    expect_false(result["passed"])
    expect_eq(result["epistemic_status"], "REJECTED")
    expect_in("CERT_STATUS_UNKNOWN", _rules(cert))


def _cited_known(**citation_overrides: object) -> dict:
    citation = {
        "source": "Euclid, Elements",
        "reference": "Book I, Proposition 47",
        "artifact_sha256": HEX64,
    }
    citation.update(citation_overrides)
    return {"epistemic_status": "KNOWN", "citation": citation}


def _expect_citation_rejected(cert: dict, rule: str) -> None:
    result = audit_transition_certificate(cert)
    expect_false(result["passed"], f"KNOWN was accepted: {result}")
    expect_eq(result["epistemic_status"], "REJECTED")
    expect_in(rule, _rules(cert))


def test_known_refused_and_in_progress_are_recognized() -> None:
    expect_true({"KNOWN", "REFUSED", "IN_PROGRESS"} <= RECOGNIZED_CERT_STATUSES)
    for tier in ("REFUSED", "IN_PROGRESS"):
        cert = {"epistemic_status": tier}
        result = audit_transition_certificate(cert)
        expect_true(result["passed"], f"{tier} certificate rejected: {result}")
        expect_eq(result["epistemic_status"], tier)
        rules = _rules(cert)
        expect_false("CERT_STATUS_UNKNOWN" in rules, f"unexpected CERT_STATUS_UNKNOWN for {tier}: {rules}")
    known_rules = _rules({"epistemic_status": "KNOWN"})
    expect_false("CERT_STATUS_UNKNOWN" in known_rules, known_rules)
    expect_in("CERT_KNOWN_CITATION_MISSING", known_rules)


def test_rejected_and_conjecture_are_not_relabeled_verified() -> None:
    rejected = audit_transition_certificate({"epistemic_status": "REJECTED"})
    expect_true(rejected["passed"], f"a plain rejection is not an illegal claim: {rejected}")
    expect_eq(rejected["epistemic_status"], "REJECTED")

    conjecture = audit_transition_certificate({"epistemic_status": "CONJECTURE"})
    expect_true(conjecture["passed"], f"CONJECTURE does not require pins: {conjecture}")
    expect_eq(conjecture["epistemic_status"], "CONJECTURE")


def test_conjecture_to_known_without_evidence_is_rejected() -> None:
    """A7 rejects a lower tier promoted to KNOWN, including one that carries a citation.

    Reverting the KNOWN arm of the tier check lets the cited certificate pass.
    """
    cert = {"epistemic_status": "KNOWN", "prior_status": "CONJECTURE"}
    result = audit_transition_certificate(cert)
    expect_false(result["passed"], f"CONJECTURE to KNOWN was accepted: {result}")
    expect_eq(result["epistemic_status"], "REJECTED")
    expect_in("CERT_A7_ILLEGAL_TIER_SWAP", _rules(cert))

    cited = _cited_known()
    cited["prior_status"] = "CONJECTURE"
    cited_result = audit_transition_certificate(cited)
    expect_false(cited_result["passed"], f"cited CONJECTURE to KNOWN was accepted: {cited_result}")
    expect_eq(cited_result["epistemic_status"], "REJECTED")
    expect_in("CERT_A7_ILLEGAL_TIER_SWAP", _rules(cited))


def test_bare_known_is_rejected() -> None:
    """A bare KNOWN certificate has no citation. Removing the citation check lets it pass."""
    _expect_citation_rejected({"epistemic_status": "KNOWN"}, "CERT_KNOWN_CITATION_MISSING")


def test_known_missing_or_blank_source_is_rejected() -> None:
    """Removing the citation check lets a citation with no usable source pass."""
    missing = _cited_known()
    del missing["citation"]["source"]
    _expect_citation_rejected(missing, "CERT_KNOWN_CITATION_MISSING")
    _expect_citation_rejected(_cited_known(source="   "), "CERT_KNOWN_CITATION_MISSING")
    _expect_citation_rejected(_cited_known(source=""), "CERT_KNOWN_CITATION_MISSING")


def test_known_missing_or_blank_reference_is_rejected() -> None:
    """Removing the citation check lets a citation with no usable reference pass."""
    missing = _cited_known()
    del missing["citation"]["reference"]
    _expect_citation_rejected(missing, "CERT_KNOWN_CITATION_MISSING")
    _expect_citation_rejected(_cited_known(reference=" \t"), "CERT_KNOWN_CITATION_MISSING")


def test_known_missing_or_malformed_digest_is_rejected() -> None:
    """Removing the citation check lets a missing, short, or uppercase digest pass."""
    missing = _cited_known()
    del missing["citation"]["artifact_sha256"]
    _expect_citation_rejected(missing, "CERT_KNOWN_CITATION_MISSING")
    _expect_citation_rejected(_cited_known(artifact_sha256="zz"), "CERT_KNOWN_CITATION_MALFORMED")
    _expect_citation_rejected(_cited_known(artifact_sha256="A" * 64), "CERT_KNOWN_CITATION_MALFORMED")


def test_known_without_citation_is_rejected_for_other_priors() -> None:
    """evidence_kind, a blank prior, and REFUSED are not a citation."""
    _expect_citation_rejected(
        {"epistemic_status": "KNOWN", "evidence_kind": "none"},
        "CERT_KNOWN_CITATION_MISSING",
    )
    _expect_citation_rejected(
        {"epistemic_status": "KNOWN", "prior_status": "   "},
        "CERT_KNOWN_CITATION_MISSING",
    )
    _expect_citation_rejected(
        {"epistemic_status": "KNOWN", "prior_status": "REFUSED"},
        "CERT_KNOWN_CITATION_MISSING",
    )


def test_known_proof_digest_and_tcb_pins_are_not_a_citation() -> None:
    """The pins that satisfy VERIFIED do not satisfy KNOWN.

    Removing the citation check lets this certificate pass and stay KNOWN.
    """
    cert = {
        "epistemic_status": "KNOWN",
        "witness_or_proof_sha256": HEX64,
        "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64},
    }
    _expect_citation_rejected(cert, "CERT_KNOWN_CITATION_MISSING")
    expect_false("CERT_A7_ILLEGAL_TIER_SWAP" in _rules(cert), _rules(cert))


def test_known_with_citation_keeps_known() -> None:
    """A source, a reference, and a lowercase artifact digest stay KNOWN."""
    cert = _cited_known()
    result = audit_transition_certificate(cert)
    expect_true(result["passed"], f"cited KNOWN rejected: {result}")
    expect_eq(result["epistemic_status"], "KNOWN")
    rules = _rules(cert)
    expect_false("CERT_KNOWN_CITATION_MISSING" in rules, result)
    expect_false("CERT_KNOWN_CITATION_MALFORMED" in rules, result)
    expect_false("CERT_A7_ILLEGAL_TIER_SWAP" in rules, result)


def test_verified_with_pins_still_passes() -> None:
    cert = {
        "epistemic_status": "VERIFIED",
        "witness_or_proof_sha256": HEX64,
        "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64},
    }
    result = audit_transition_certificate(cert)
    expect_true(result["passed"], f"pinned VERIFIED certificate rejected: {result}")
    expect_eq(result["epistemic_status"], "VERIFIED")


def test_cli_rejects_empty_certificate(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("{}\n", encoding="utf-8")
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        code = cli_main(["--json", "audit-cert", str(path)])
        raw = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    expect_eq(code, 1)
    parsed = json.loads(raw)
    expect_eq(parsed["epistemic_status"], "REJECTED")
    expect_false(parsed["passed"])
