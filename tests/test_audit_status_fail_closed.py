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
from mcproof.domain_protocol import audit_transition_certificate

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


def test_known_refused_and_in_progress_are_recognized() -> None:
    for tier in ("KNOWN", "REFUSED", "IN_PROGRESS"):
        cert = {"epistemic_status": tier}
        result = audit_transition_certificate(cert)
        expect_true(result["passed"], f"{tier} certificate rejected: {result}")
        expect_eq(result["epistemic_status"], tier)
        rules = _rules(cert)
        expect_false("CERT_STATUS_UNKNOWN" in rules, f"unexpected CERT_STATUS_UNKNOWN for {tier}: {rules}")


def test_rejected_and_conjecture_are_not_relabeled_verified() -> None:
    rejected = audit_transition_certificate({"epistemic_status": "REJECTED"})
    expect_true(rejected["passed"], f"a plain rejection is not an illegal claim: {rejected}")
    expect_eq(rejected["epistemic_status"], "REJECTED")

    conjecture = audit_transition_certificate({"epistemic_status": "CONJECTURE"})
    expect_true(conjecture["passed"], f"CONJECTURE does not require pins: {conjecture}")
    expect_eq(conjecture["epistemic_status"], "CONJECTURE")


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
