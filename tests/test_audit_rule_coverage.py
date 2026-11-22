"""Each certificate rule below must have a test that turns red when the rule is removed.

Deleting the check for one of these four rules used to leave every test green.
Each case adds one corruption to a minimal VERIFIED certificate with good pins
and digest. The corruption fires that rule and no other, and the matching good
certificate passes, so a test cannot go green by rejecting for a different reason.
"""

from __future__ import annotations

from mcproof.domain_protocol import audit_transition_certificate

from helpers import expect_eq, expect_false, expect_true

HEX64 = "a" * 64
OTHER_HEX64 = "b" * 64


def _minimal_verified(**extra: object) -> dict:
    cert: dict = {
        "epistemic_status": "VERIFIED",
        "witness_or_proof_sha256": HEX64,
        "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64},
    }
    cert.update(extra)
    return cert


def _expect_only_rule(cert: dict, rule: str) -> None:
    result = audit_transition_certificate(cert)
    expect_false(result["passed"], f"{rule}: corrupted certificate was accepted: {result}")
    expect_eq(result["epistemic_status"], "REJECTED")
    expect_eq([f["rule"] for f in result["findings"]], [rule], "the corruption must fire this rule alone")


def _expect_accepted(cert: dict) -> None:
    result = audit_transition_certificate(cert)
    expect_true(result["passed"], f"good certificate was rejected: {result}")
    expect_eq(result["epistemic_status"], "VERIFIED")


def _control(*, passed: bool) -> dict:
    return _minimal_verified(
        must_fail_controls=["c1"],
        control_records=[{"name": "c1", "oracle_invoked": True, "unexpectedly_passed": passed}],
    )


def test_a6_control_that_unexpectedly_passed_is_rejected() -> None:
    _expect_accepted(_control(passed=False))
    _expect_only_rule(_control(passed=True), "CERT_A6_CONTROL_PASSED")


def _floor(*, floor: int, bound: int, moves: int) -> dict:
    return _minimal_verified(
        proven_floor=floor,
        max_bound=bound,
        witness="U" * moves,
        exact_optimum_reached=True,
    )


def test_floor_above_the_search_bound_is_rejected() -> None:
    _expect_accepted(_floor(floor=10, bound=10, moves=10))
    _expect_only_rule(_floor(floor=12, bound=10, moves=12), "CERT_FLOOR_EXCEEDS_MAX_BOUND")


def test_instance_digest_that_differs_from_the_canonical_one_is_rejected() -> None:
    _expect_accepted(_minimal_verified(instance_sha256=HEX64, canonical_instance_sha256=HEX64))
    _expect_only_rule(
        _minimal_verified(instance_sha256=HEX64, canonical_instance_sha256=OTHER_HEX64),
        "CERT_INSTANCE_DIGEST_MISMATCH",
    )


def test_witness_cost_that_differs_from_the_claimed_floor_is_rejected() -> None:
    _expect_accepted(_floor(floor=12, bound=12, moves=12))
    _expect_only_rule(_floor(floor=12, bound=12, moves=11), "CERT_WITNESS_FLOOR_MISMATCH")


def test_rejected_witness_cannot_carry_verified() -> None:
    _expect_accepted(_minimal_verified(valid_winning_witness=True))
    _expect_only_rule(_minimal_verified(valid_winning_witness=False), "CERT_A7_ILLEGAL_TIER_SWAP")
    _expect_only_rule(_minimal_verified(valid_winning_route=False), "CERT_A7_ILLEGAL_TIER_SWAP")


def test_empty_must_fail_controls_list_is_rejected() -> None:
    _expect_only_rule(_minimal_verified(must_fail_controls=[]), "CERT_A6_MISSING_OR_DUPLICATE_CONTROLS")
