"""The auditor must check the type of a red-flag field before it compares the value.

A flag written as the string "false" or as 0, a negative or fractional count, or a
witness key left out used to come back VERIFIED. Each case pairs a control (the red
flag in its usual form, which was already rejected) with a variant (which was not).
"""

from __future__ import annotations

import io
import json
import sys
from typing import Any

import pytest

from mcproof.cli import main as cli_main
from mcproof.domain_protocol import audit_transition_certificate

from helpers import expect_eq, expect_false, expect_in, expect_true

HEX64 = "a" * 64
TYPE_RULE = "CERT_FIELD_TYPE_INVALID"


def _verified(**extra: Any) -> dict:
    cert: dict = {
        "epistemic_status": "VERIFIED",
        "witness_or_proof_sha256": HEX64,
        "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64},
    }
    cert.update(extra)
    return cert


def _rules(cert: Any) -> list[str]:
    return [f["rule"] for f in audit_transition_certificate(cert)["findings"]]


def _expect_rejected(cert: dict, rule: str) -> None:
    result = audit_transition_certificate(cert)
    expect_false(result["passed"], f"accepted: {cert} -> {result}")
    expect_eq(result["epistemic_status"], "REJECTED")
    expect_in(rule, _rules(cert))


def test_unmodified_verified_certificate_still_passes() -> None:
    result = audit_transition_certificate(_verified())
    expect_true(result["passed"], str(result))
    expect_eq(result["epistemic_status"], "VERIFIED")


def test_correctly_typed_flags_and_counts_still_pass() -> None:
    cert = _verified(
        includes_hidden_state=True,
        caller_bounds_verified=True,
        differential_match=True,
        oracles_checked=["a", "b"],
        step_consistency_violations=0,
        open_transitions=0,
        proven_floor=12,
        max_bound=12,
        witness="U" * 12,
        exact_optimum_reached=True,
    )
    result = audit_transition_certificate(cert)
    expect_true(result["passed"], str(result))


CASES = [
    (
        "tcb_pins.tcb_manifest_verified",
        {"tcb_pins": {"tcb_manifest_verified": False, "checker_sha256": HEX64}},
        "CERT_TCB_MANIFEST_UNLOCKED",
        [
            {"tcb_pins": {"tcb_manifest_verified": "false", "checker_sha256": HEX64}},
            {"tcb_pins": {"tcb_manifest_verified": "", "checker_sha256": HEX64}},
            {"tcb_pins": {"tcb_manifest_verified": 1, "checker_sha256": HEX64}},
            {"tcb_pins": {"tcb_manifest_verified": None, "checker_sha256": HEX64}},
        ],
    ),
    ("includes_hidden_state", {"includes_hidden_state": False}, "CERT_PARTIAL_STATE_PROJECTION", [{"includes_hidden_state": 0}, {"includes_hidden_state": "false"}]),
    ("caller_bounds_verified", {"caller_bounds_verified": False}, "CERT_UNVERIFIED_CALLER_INFLATION", [{"caller_bounds_verified": 0}, {"caller_bounds_verified": "no"}]),
    (
        "differential_match",
        {"differential_match": True, "oracles_checked": ["only"]},
        "CERT_SINGLE_ORACLE_DIFFERENTIAL",
        [{"differential_match": 1, "oracles_checked": ["only"]}, {"differential_match": "true", "oracles_checked": ["only"]}],
    ),
    (
        "step_consistency_violations",
        {"step_consistency_violations": 1},
        "CERT_STEP_INCONSISTENCY",
        [{"step_consistency_violations": -3}, {"step_consistency_violations": "1"}, {"step_consistency_violations": True}, {"step_consistency_violations": 0.9}],
    ),
    ("open_transitions", {"open_transitions": 2, "proof_mode": "inductive_potential"}, "CERT_TRUNCATED_INDUCTIVE_POTENTIAL", [{"open_transitions": -1}, {"open_transitions": "2"}]),
    ("exact_optimum_reached", {"exact_optimum_reached": False, "witness": "UUU", "proven_floor": 3}, "CERT_UNWITNESSED_VERIFIED_OPTIMUM", [{"exact_optimum_reached": 0, "witness": "UUU", "proven_floor": 3}]),
    (
        "proven_floor",
        {"proven_floor": 12, "witness": "U" * 11, "exact_optimum_reached": True},
        "CERT_WITNESS_FLOOR_MISMATCH",
        [
            {"proven_floor": "12", "witness": "U" * 12, "exact_optimum_reached": True},
            {"proven_floor": -12, "witness": "U" * 12, "exact_optimum_reached": True},
            {"proven_floor": True, "witness": "U", "exact_optimum_reached": True},
        ],
    ),
]


@pytest.mark.parametrize("field,control,control_rule,variants", CASES, ids=[c[0] for c in CASES])
def test_red_flag_variant_is_rejected_like_its_control(field: str, control: dict, control_rule: str, variants: list) -> None:
    _expect_rejected(_verified(**control), control_rule)
    for variant in variants:
        cert = _verified(**variant)
        _expect_rejected(cert, TYPE_RULE)
        named = [f["message"] for f in audit_transition_certificate(cert)["findings"] if f["rule"] == TYPE_RULE]
        expect_true(any(field.split(".")[-1] in m for m in named), f"finding does not name {field}: {named}")


def test_state_hash_mode_spelling_does_not_hide_a_partial_projection() -> None:
    for spelled in ("ascii_only", "ASCII_ONLY", " Ascii_Only "):
        _expect_rejected(_verified(state_hash_mode=spelled), "CERT_PARTIAL_STATE_PROJECTION")
    _expect_rejected(_verified(state_hash_mode=7), TYPE_RULE)


def test_missing_proven_floor_does_not_skip_the_unwitnessed_optimum_check() -> None:
    control = _verified(witness=None, exact_optimum_reached=False, proven_floor=12)
    _expect_rejected(control, "CERT_UNWITNESSED_VERIFIED_OPTIMUM")
    for variant in (
        _verified(witness=None, exact_optimum_reached=False),
        _verified(exact_optimum_reached=False),
        _verified(witness=None),
        _verified(winning_witness=""),
    ):
        _expect_rejected(variant, "CERT_UNWITNESSED_VERIFIED_OPTIMUM")


def test_control_records_must_be_objects_with_boolean_flags() -> None:
    base = {"must_fail_controls": ["c1"]}
    _expect_rejected(_verified(**base, control_records=["c1"]), TYPE_RULE)
    _expect_rejected(_verified(**base, control_records=[{"name": "c1", "oracle_invoked": "false"}]), TYPE_RULE)
    _expect_rejected(_verified(**base, control_records=[{"name": "c1", "oracle_invoked": True, "unexpectedly_passed": 1}]), TYPE_RULE)
    _expect_rejected(_verified(must_fail_controls=[1, 2]), TYPE_RULE)
    _expect_rejected(_verified(must_fail_controls="c1"), TYPE_RULE)


def test_certificate_that_is_not_an_object_is_rejected() -> None:
    for bad in ([], [{"epistemic_status": "VERIFIED"}], "VERIFIED", 7, None):
        result = audit_transition_certificate(bad)  # type: ignore[arg-type]
        expect_false(result["passed"], str(result))
        expect_eq(result["epistemic_status"], "REJECTED")
        expect_eq([f["rule"] for f in result["findings"]], ["CERT_NOT_AN_OBJECT"])


def _run_cli(cert_json: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(cert_json))
    code = cli_main(["--json", "audit-cert", "-"])
    return code, json.loads(capsys.readouterr().out)


def test_cli_rejects_string_false_and_non_object(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    string_false = _verified(tcb_pins={"tcb_manifest_verified": "false", "checker_sha256": HEX64})
    code, receipt = _run_cli(json.dumps(string_false), monkeypatch, capsys)
    expect_eq(code, 1)
    expect_eq(receipt["epistemic_status"], "REJECTED")
    code, receipt = _run_cli("[]", monkeypatch, capsys)
    expect_eq(code, 1)
    expect_eq(receipt["epistemic_status"], "REJECTED")
    code, receipt = _run_cli(json.dumps(_verified()), monkeypatch, capsys)
    expect_eq(code, 0)
    expect_eq(receipt["epistemic_status"], "VERIFIED")
