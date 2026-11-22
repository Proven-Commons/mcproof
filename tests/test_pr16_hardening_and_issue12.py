"""Comprehensive regression and guard-coverage suite for PR #16 hardening and Issue #12.

Every guard introduced in `domain_protocol.py` and `repair_loop.py` is paired with an
accepted positive control and a failing negative variant asserting exact rule names,
covering 100% of named rules in `domain_protocol.py` and every Issue #12 stopping,
gap-accounting, eligibility, and checkpoint-invalidation path.
"""

from __future__ import annotations

from fractions import Fraction
import io
import json
from pathlib import Path
import sys
from typing import Any, Mapping

import pytest

from mcproof.cli import main as cli_main
from mcproof.domain_protocol import (
    audit_portfolio_bounds,
    audit_transition_certificate,
    run_restricted_sandbox_cell,
    verify_dual_product_parity,
    verify_minimal_goal_stopping,
    verify_rational_lp_certificate,
)
from mcproof.repair_loop import (
    evaluate_early_stop_eligibility,
    run_repair_item,
    run_repair_split,
    summarize_oracle_grader_gap,
)

from helpers import expect_eq, expect_false, expect_in, expect_true

HEX64 = "a" * 64
HEX64_B = "b" * 64
HEX64_C = "c" * 64
ZEROS64 = "0" * 64
TYPE_RULE = "CERT_FIELD_TYPE_INVALID"


def _verified(**extra: Any) -> dict[str, Any]:
    cert: dict[str, Any] = {
        "epistemic_status": "VERIFIED",
        "witness_or_proof_sha256": HEX64,
        "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64},
    }
    cert.update(extra)
    return cert


def _rules(rep: Mapping[str, Any]) -> list[str]:
    return [str(f["rule"]) for f in rep.get("findings", ())]


def _expect_only_rule(cert: Mapping[str, Any], rule: str, **kwargs: Any) -> None:
    rep = audit_transition_certificate(cert, **kwargs)
    expect_false(rep["passed"], f"expected {rule} rejection, got {rep}")
    expect_eq(rep["epistemic_status"], "REJECTED")
    expect_eq(_rules(rep), [rule], f"expected solely {rule}, got {rep}")


def _expect_rejected_with(cert: Mapping[str, Any], rule: str, **kwargs: Any) -> None:
    rep = audit_transition_certificate(cert, **kwargs)
    expect_false(rep["passed"], f"expected {rule} rejection, got {rep}")
    expect_eq(rep["epistemic_status"], "REJECTED")
    expect_in(rule, _rules(rep))


def _expect_accepted(cert: Mapping[str, Any], expected_status: str = "VERIFIED", **kwargs: Any) -> None:
    rep = audit_transition_certificate(cert, **kwargs)
    expect_true(rep["passed"], f"valid cert rejected: {rep}")
    expect_eq(rep["epistemic_status"], expected_status)


# ---------------------------------------------------------------------------
# 1. Sandbox injected_globals validation (domain_protocol.py:422-435)
# ---------------------------------------------------------------------------


def test_sandbox_injected_globals_rejects_trailing_newline_and_bad_keys() -> None:
    ok_res = run_restricted_sandbox_cell("print(x_1 + 1)", injected_globals={"x_1": 41})
    expect_true(ok_res["ok"], f"valid injected_globals failed: {ok_res}")
    expect_eq(ok_res["stdout"].strip(), "42")

    for bad_key in ("x\n", "1bad", "a;import os", "", "a" * 65, 7):
        res = run_restricted_sandbox_cell("print(1)", injected_globals={bad_key: 1})  # type: ignore[dict-item]
        expect_false(res["ok"], f"bad key {bad_key!r} should be rejected")
        expect_true(res["ast_rejected"])
        expect_eq(res["returncode"], 2)
        expect_true(any("invalid_injected_global_key" in v for v in res["violations"]))


# ---------------------------------------------------------------------------
# 2. Portfolio bounds hardening (domain_protocol.py:600-675)
# ---------------------------------------------------------------------------


def test_portfolio_bounds_empty_types_transitivity_and_whitespace_status() -> None:
    # Empty / non-sequence inputs fail closed with CERT_PORTFOLIO_EMPTY
    for bad_items in ([], "", b"abc", None):
        rep = audit_portfolio_bounds(bad_items)  # type: ignore[arg-type]
        expect_false(rep["passed"])
        expect_eq(rep["epistemic_status"], "REJECTED")
        expect_eq(_rules(rep), ["CERT_PORTFOLIO_EMPTY"])

    # Valid registered item passes cleanly
    ok_rep = audit_portfolio_bounds(
        [{"id": "P1", "proven_floor": 5, "shortest_known": 6, "live_record": 7, "epistemic_status": "VERIFIED"}],
        registered_verified_ids=frozenset({"P1"}),
    )
    expect_true(ok_rep["passed"], str(ok_rep))
    expect_eq(ok_rep["items"][0]["epistemic_status"], "VERIFIED")

    # Unregistered non-VERIFIED item is triaged without error
    unreg_ok = audit_portfolio_bounds(
        [{"id": "P2", "proven_floor": 5, "shortest_known": 6, "epistemic_status": "LOWER_BOUND"}],
        registered_verified_ids=frozenset(),
    )
    expect_true(unreg_ok["passed"], str(unreg_ok))
    expect_eq(unreg_ok["items"][0]["epistemic_status"], "UNVERIFIED_CALLER_BOUNDS")

    # Non-mapping item rejected with CERT_FIELD_TYPE_INVALID
    bad_row = audit_portfolio_bounds(["not_an_object"])  # type: ignore[list-item]
    expect_false(bad_row["passed"])
    expect_eq(_rules(bad_row), [TYPE_RULE])

    # Non-count bounds and non-str epistemic_status rejected with CERT_FIELD_TYPE_INVALID
    for bad_field in (
        {"id": "B1", "proven_floor": True},
        {"id": "B2", "shortest_known": -1},
        {"id": "B3", "live_record": "5"},
        {"id": "B4", "epistemic_status": 123},
    ):
        rep = audit_portfolio_bounds([bad_field])
        expect_false(rep["passed"], f"accepted bad field {bad_field}")
        expect_eq(_rules(rep), [TYPE_RULE])
        expect_eq(rep["items"][0]["epistemic_status"], "REJECTED_INVALID_BOUND_TYPE")

    # All three inversion pairs: p_floor > s_known, s_known > l_rec, p_floor > l_rec (s_known omitted)
    for inv_row in (
        {"id": "I1", "proven_floor": 10, "shortest_known": 9},
        {"id": "I2", "shortest_known": 10, "live_record": 9},
        {"id": "I3", "proven_floor": 10, "live_record": 9},
    ):
        rep = audit_portfolio_bounds([inv_row], registered_verified_ids=frozenset({inv_row["id"]}))
        expect_false(rep["passed"], f"accepted inverted bounds {inv_row}")
        expect_eq(_rules(rep), ["CERT_F07_INCONSISTENT_PORTFOLIO_BOUNDS"])

    # Whitespace-padded VERIFIED / PROVEN on unregistered ID fails closed!
    for padded in (" VERIFIED", "VERIFIED ", "\tPROVEN\n", " proven "):
        rep = audit_portfolio_bounds(
            [{"id": "UNREG", "proven_floor": 5, "shortest_known": 5, "epistemic_status": padded}],
            registered_verified_ids=frozenset(),
        )
        expect_false(rep["passed"], f"whitespace status {padded!r} bypassed F-07")
        expect_eq(_rules(rep), ["CERT_F07_UNVERIFIED_CALLER_BOUNDS"])


# ---------------------------------------------------------------------------
# 3. Blank Unicode, dual witness keys, nested empty containers, A6, F01, F03, F08
# ---------------------------------------------------------------------------


def test_blank_unicode_rejected_across_witness_engines_controls_and_known_citation() -> None:
    # Positive control: NFD accented text has a visible base letter + combining mark (Mn) and must pass
    _expect_accepted(_verified(witness="e\u0301", proven_floor=2))
    _expect_accepted(_verified(differential_match=True, oracles_checked=["engine_a", "e\u0301"]))

    blank_tokens = (
        "\u2800",  # Braille Pattern Blank
        "\u3164",  # Hangul Filler
        "\uffa0",  # Halfwidth Hangul Filler
        "\u00ad",  # Soft Hyphen (Cf)
        "\u200b",  # Zero-Width Space (Cf)
        "\u00a0",  # No-Break Space (Zs)
        "\u2028",  # Line Separator (Zl)
        "\u034f",  # Combining Grapheme Joiner (Mn)
        "\ufe00",  # Variation Selector-1 (Mn)
        "\ufe0f",  # Variation Selector-16 (Mn)
        "\U000e0100",  # Variation Selector Supplement-17 (Mn)
        "\u180b",  # Mongolian Free Variation Selector One (Mn)
        "\u0301",  # Standalone Combining Acute Accent (Mn)
    )
    for tok in blank_tokens:
        # Witness string & list element
        _expect_only_rule(_verified(witness=tok, proven_floor=1), "CERT_UNWITNESSED_VERIFIED_OPTIMUM")
        _expect_rejected_with(_verified(witness=[tok], proven_floor=1), "CERT_UNWITNESSED_VERIFIED_OPTIMUM")
        _expect_rejected_with(_verified(witness=[tok], proven_floor=1), TYPE_RULE)

        # Differential engine lists
        _expect_rejected_with(
            _verified(differential_match=True, oracles_checked=["engine_a", tok]),
            TYPE_RULE,
        )
        _expect_rejected_with(
            _verified(differential_match=True, oracles_checked=["engine_a", tok]),
            "CERT_SINGLE_ORACLE_DIFFERENTIAL",
        )

        # Control names in must_fail_controls & control_records
        _expect_rejected_with(
            _verified(
                must_fail_controls=[tok],
                control_records=[{"name": tok, "oracle_invoked": True, "unexpectedly_passed": False}],
            ),
            "CERT_A6_MISSING_OR_DUPLICATE_CONTROLS",
        )
        _expect_rejected_with(
            _verified(
                must_fail_controls=["c1"],
                control_records=[{"name": tok, "oracle_invoked": True, "unexpectedly_passed": False}],
            ),
            TYPE_RULE,
        )

        # KNOWN citation fields
        _expect_only_rule(
            {
                "epistemic_status": "KNOWN",
                "citation": {"source": tok, "reference": "ref-1", "artifact_sha256": HEX64},
            },
            "CERT_KNOWN_CITATION_MISSING",
        )


def test_dual_witness_keys_and_nested_empty_containers_fail_closed() -> None:
    # Both present & valid & matching proven_floor -> accepted
    _expect_accepted(_verified(witness="U", winning_witness="U", proven_floor=1))
    _expect_accepted(_verified(witness=[{"move": "U", "step": 1}], proven_floor=1))

    # Dual witness keys: one valid + one empty / null / blank -> rejected!
    for bad_dual in (
        _verified(witness="U", winning_witness="", proven_floor=1),
        _verified(witness="", winning_witness="U", proven_floor=1),
        _verified(witness="U", winning_witness=None, proven_floor=1),
        _verified(witness="U", winning_witness="\u2800", proven_floor=1),
    ):
        _expect_only_rule(bad_dual, "CERT_UNWITNESSED_VERIFIED_OPTIMUM")

    # Dual witness keys: length disagreement against proven_floor -> CERT_WITNESS_FLOOR_MISMATCH
    _expect_only_rule(_verified(witness="U", winning_witness="UU", proven_floor=1), "CERT_WITNESS_FLOOR_MISMATCH")

    # Empty and nested-empty container list witnesses fail closed!
    for bad_list_witness in (
        [],
        [[]],
        [{}],
        [[], {}],
        [[[]]],
        [{"a": ""}],
        [{"a": []}],
        [{"\u2800": 1}],
        [{"a": None}],
        [{"a": True}],
        [None],
        [True],
        [1.5],  # intentional negative control: float step forbidden
    ):
        cert = _verified(witness=bad_list_witness, proven_floor=1)
        _expect_rejected_with(cert, "CERT_UNWITNESSED_VERIFIED_OPTIMUM")
        if len(bad_list_witness) > 0:
            _expect_rejected_with(cert, TYPE_RULE)

    # Non-string, non-list witness, non-JSON element, and over-deep nested witness (>16) fail closed
    _expect_rejected_with(_verified(witness=123, proven_floor=1), TYPE_RULE)
    _expect_rejected_with(_verified(witness=[object()], proven_floor=1), TYPE_RULE)
    deep_w: Any = "U"
    for _ in range(18):
        deep_w = [deep_w]
    _expect_rejected_with(_verified(witness=deep_w, proven_floor=1), TYPE_RULE)


def test_a6_must_fail_controls_omitted_control_records_and_tautological_omissions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Good control coverage passes
    good = _verified(
        must_fail_controls=["c1", "c2"],
        control_records=[
            {"name": "c1", "oracle_invoked": True, "unexpectedly_passed": False},
            {"name": "c2", "oracle_invoked": True, "unexpectedly_passed": False},
        ],
    )
    _expect_accepted(good)

    # Partial control_records misses c2
    _expect_only_rule(
        _verified(
            must_fail_controls=["c1", "c2"],
            control_records=[{"name": "c1", "oracle_invoked": True, "unexpectedly_passed": False}],
        ),
        "CERT_A6_CONTROL_COVERAGE_INCOMPLETE",
    )

    # Omitted control_records entirely when must_fail_controls is declared -> fails closed EVEN without require_must_fail_controls!
    omitted_crecs = _verified(must_fail_controls=["c1"])
    _expect_only_rule(omitted_crecs, "CERT_A6_CONTROL_COVERAGE_INCOMPLETE")

    # Same payload via `mcproof audit-cert` CLI (`cli.py:363`) fails closed with exit code 1!
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(omitted_crecs)))
    rc = cli_main(["--json", "audit-cert", "-"])
    out = json.loads(capsys.readouterr().out)
    expect_eq(rc, 1)
    expect_eq(out["epistemic_status"], "REJECTED")
    expect_in("CERT_A6_CONTROL_COVERAGE_INCOMPLETE", [f["rule"] for f in out["findings"]])

    # Control record omitting oracle_invoked or unexpectedly_passed -> CERT_A6_TAUTOLOGICAL_CONTROL
    _expect_only_rule(
        _verified(must_fail_controls=["c1"], control_records=[{"name": "c1", "unexpectedly_passed": False}]),
        "CERT_A6_TAUTOLOGICAL_CONTROL",
    )
    _expect_only_rule(
        _verified(must_fail_controls=["c1"], control_records=[{"name": "c1", "oracle_invoked": True}]),
        "CERT_A6_TAUTOLOGICAL_CONTROL",
    )


def test_f01_all_present_oracle_lists_f03_all_present_tcb_pins_and_f08_instance_digests() -> None:
    # F-01: every present oracle list must have >= 2 distinct visible engines
    _expect_accepted(
        _verified(differential_match=True, oracles_checked=["a", "b"], engines_verified=["x", "y"])
    )
    _expect_only_rule(
        _verified(differential_match=True, oracles_checked=["a", "b"], engines_verified=["x", "x"]),
        "CERT_SINGLE_ORACLE_DIFFERENTIAL",
    )
    _expect_only_rule(
        _verified(differential_match=True),
        "CERT_SINGLE_ORACLE_DIFFERENTIAL",
    )
    _expect_rejected_with(
        _verified(differential_match=True, checkers_executed="not_a_list"),
        TYPE_RULE,
    )

    # F-03: every present checker digest key in tcb_pins must be valid non-zero 64-hex (no trailing newline!)
    _expect_accepted(
        _verified(
            tcb_pins={
                "tcb_manifest_verified": True,
                "checker_sha256": HEX64,
                "checker_auditor_py_sha256": HEX64_B,
            }
        )
    )
    for bad_digest in (ZEROS64, HEX64 + "\n", "A" * 64, "short"):
        _expect_only_rule(
            _verified(
                tcb_pins={
                    "tcb_manifest_verified": True,
                    "checker_sha256": HEX64,
                    "checker_auditor_py_sha256": bad_digest,
                }
            ),
            "CERT_TCB_MANIFEST_UNLOCKED",
        )

    # F-08: witness_or_proof_sha256 rejects all-zeros and trailing newline
    for bad_wsha in (ZEROS64, HEX64 + "\n"):
        _expect_only_rule(_verified(witness_or_proof_sha256=bad_wsha), "CERT_INVALID_WITNESS_SHA256")

    # Instance digest format checks reject all-zeros, uppercase, short, and trailing newline
    _expect_accepted(_verified(instance_sha256=HEX64_B, canonical_instance_sha256=HEX64_B))
    for bad_idig in (ZEROS64, HEX64 + "\n", "B" * 64, "abc", ""):
        _expect_only_rule(_verified(instance_sha256=bad_idig), "CERT_INSTANCE_DIGEST_MALFORMED")
        _expect_only_rule(_verified(canonical_instance_sha256=bad_idig), "CERT_INSTANCE_DIGEST_MALFORMED")

    # certified_lower_bound type guard + F-05 incomplete graph
    _expect_accepted(_verified(certified_lower_bound=5, complete_space=True))
    _expect_only_rule(_verified(certified_lower_bound=5, complete_space=False), "CERT_TRUNCATED_INDUCTIVE_POTENTIAL")
    _expect_rejected_with(_verified(certified_lower_bound=-1, complete_space=True), TYPE_RULE)
    _expect_rejected_with(_verified(certified_lower_bound=True, complete_space=True), TYPE_RULE)


# ---------------------------------------------------------------------------
# 4. Complete coverage of remaining domain_protocol.py rules (100% of 47 rules)
# ---------------------------------------------------------------------------


def test_verify_dual_product_parity_covers_all_f05_and_f06_rules() -> None:
    def _base(**overrides: Any) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "spec_init": 0,
            "impl_init": 0,
            "spec_actions": lambda s: [1] if s < 2 else [],
            "impl_actions": lambda u: [1] if u < 2 else [],
            "spec_step": lambda s, a: s + a,
            "impl_step": lambda u, a: u + a,
            "spec_invariant": lambda s: 0 <= s <= 2,
            "impl_invariant": lambda u: 0 <= u <= 2,
            "spec_is_goal": lambda s: s == 2,
            "impl_is_goal": lambda u: u == 2,
            "spec_obs": lambda s: s,
            "impl_obs": lambda u: u,
            "max_product_states": 100,
        }
        kw.update(overrides)
        return verify_dual_product_parity(**kw)

    ok = _base()
    expect_true(ok["passed"])
    expect_eq(ok["epistemic_status"], "PROVEN")

    obs_bad = _base(impl_obs=lambda u: u + 10)
    expect_false(obs_bad["passed"])
    expect_eq(_rules(obs_bad), ["F06_OBSERVATION_DIVERGENCE"])

    goal_bad = _base(impl_is_goal=lambda u: u == 1)
    expect_false(goal_bad["passed"])
    expect_eq(_rules(goal_bad), ["F06_GOAL_PARITY_MISMATCH"])

    act_bad = _base(impl_actions=lambda u: [1, 2] if u == 0 else [])
    expect_false(act_bad["passed"])
    expect_eq(_rules(act_bad), ["F06_ACTION_SET_MISMATCH"])

    trunc = _base(max_product_states=1)
    expect_false(trunc["passed"])
    expect_eq(trunc["epistemic_status"], "REJECTED_INCOMPLETE_PRODUCT_SPACE")
    expect_eq(_rules(trunc), ["F05_INCOMPLETE_PRODUCT_GRAPH"])


def test_verify_minimal_goal_stopping_covers_invalid_step_and_goal_not_reached() -> None:
    bad_step = verify_minimal_goal_stopping(
        init_state=0,
        actions=[1, 99],
        step_fn=lambda s, a: None if a == 99 else s + a,
        is_goal_fn=lambda s: s == 2,
    )
    expect_false(bad_step["passed"])
    expect_eq(_rules(bad_step), ["CERT_INVALID_TRANSITION_STEP"])

    not_reached = verify_minimal_goal_stopping(
        init_state=0,
        actions=[1],
        step_fn=lambda s, a: s + a,
        is_goal_fn=lambda s: s == 2,
    )
    expect_false(not_reached["passed"])
    expect_eq(_rules(not_reached), ["CERT_GOAL_NOT_REACHED"])


def test_verify_rational_lp_certificate_covers_every_rule_and_guard() -> None:
    # Valid bounds certificate
    ok_bounds = verify_rational_lp_certificate(
        {"mode": "bounds", "A": [[1, 1]], "b": [5], "c": [1, 1], "y": [1], "claimed_lower_bound": 5}
    )
    expect_true(ok_bounds["passed"])

    # Valid Farkas infeasibility certificate: A=[[-1]], b=[1], y=[1] => y^T A = [-1] <= 0, y^T b = 1 > 0
    ok_farkas = verify_rational_lp_certificate({"mode": "infeasible", "A": [[-1]], "b": [1], "y": [1]})
    expect_true(ok_farkas["passed"])

    # LP_CERT_NOT_AN_OBJECT
    for non_obj in ([], None, "bounds", 42):
        rep = verify_rational_lp_certificate(non_obj)  # type: ignore[arg-type]
        expect_false(rep["passed"])
        expect_eq(_rules(rep), ["LP_CERT_NOT_AN_OBJECT"])

    # LP_CERT_MALFORMED (non-str mode, non-list A/b/y/c, non-list row in A, missing key, float/bool)
    for malformed in (
        {"mode": 7, "A": [[1]], "b": [1], "y": [1], "c": [1], "claimed_lower_bound": 1},
        {"mode": "bounds", "A": "not_list", "b": [1], "y": [1], "c": [1], "claimed_lower_bound": 1},
        {"mode": "bounds", "A": ["1"], "b": [1], "y": [1], "c": [1], "claimed_lower_bound": 1},
        {"mode": "bounds", "A": [[1]], "b": [1], "y": [1], "c": "1", "claimed_lower_bound": 1},
        {"mode": "bounds", "A": [[1]], "b": [1], "y": [1]},
    ):
        rep = verify_rational_lp_certificate(malformed)
        expect_false(rep["passed"], f"accepted malformed LP cert {malformed}")
        expect_eq(_rules(rep), ["LP_CERT_MALFORMED"])

    # LP_CERT_EMPTY_SYSTEM
    for empty_a in ([], [[]]):
        rep = verify_rational_lp_certificate(
            {"mode": "bounds", "A": empty_a, "b": [], "c": [], "y": [], "claimed_lower_bound": 0}
        )
        expect_false(rep["passed"])
        expect_eq(_rules(rep), ["LP_CERT_EMPTY_SYSTEM"])

    # LP_CERT_DIMENSION_MISMATCH (b/y/jagged A/c)
    for bad_dim in (
        {"mode": "bounds", "A": [[1, 1]], "b": [1, 2], "c": [1, 1], "y": [1], "claimed_lower_bound": 1},
        {"mode": "bounds", "A": [[1, 1], [1]], "b": [1, 1], "c": [1, 1], "y": [1, 1], "claimed_lower_bound": 1},
        {"mode": "bounds", "A": [[1, 1]], "b": [1], "c": [1], "y": [1], "claimed_lower_bound": 1},
    ):
        rep = verify_rational_lp_certificate(bad_dim)
        expect_false(rep["passed"])
        expect_in("LP_CERT_DIMENSION_MISMATCH", _rules(rep))

    # LP_DUAL_NEGATIVE_MULTIPLIER
    neg_y = verify_rational_lp_certificate(
        {"mode": "bounds", "A": [[1]], "b": [-1], "c": [1], "y": [-1], "claimed_lower_bound": 0}
    )
    expect_false(neg_y["passed"])
    expect_in("LP_DUAL_NEGATIVE_MULTIPLIER", _rules(neg_y))

    # LP_DUAL_INFEASIBLE_COLUMN (y^T A = 2 > c = 1)
    infeas_col = verify_rational_lp_certificate(
        {"mode": "bounds", "A": [[2]], "b": [1], "c": [1], "y": [1], "claimed_lower_bound": 1}
    )
    expect_false(infeas_col["passed"])
    expect_eq(_rules(infeas_col), ["LP_DUAL_INFEASIBLE_COLUMN"])

    # LP_DUAL_OBJECTIVE_BELOW_CLAIM (y^T b = 1 < claim = 2)
    below = verify_rational_lp_certificate(
        {"mode": "bounds", "A": [[1]], "b": [1], "c": [1], "y": [1], "claimed_lower_bound": 2}
    )
    expect_false(below["passed"])
    expect_eq(_rules(below), ["LP_DUAL_OBJECTIVE_BELOW_CLAIM"])

    # LP_FARKAS_POSITIVE_COLUMN (y^T A = [1] > 0)
    farkas_pos = verify_rational_lp_certificate({"mode": "infeasible", "A": [[1]], "b": [1], "y": [1]})
    expect_false(farkas_pos["passed"])
    expect_eq(_rules(farkas_pos), ["LP_FARKAS_POSITIVE_COLUMN"])

    # LP_FARKAS_NONPOSITIVE_WITNESS (y^T b = 0 <= 0)
    farkas_zero = verify_rational_lp_certificate({"mode": "infeasible", "A": [[-1]], "b": [0], "y": [1]})
    expect_false(farkas_zero["passed"])
    expect_eq(_rules(farkas_zero), ["LP_FARKAS_NONPOSITIVE_WITNESS"])

    # LP_CERT_UNSUPPORTED_MODE
    bad_mode = verify_rational_lp_certificate({"mode": "primal_magic", "A": [[1]], "b": [1], "y": [1]})
    expect_false(bad_mode["passed"])
    expect_eq(_rules(bad_mode), ["LP_CERT_UNSUPPORTED_MODE"])


# ---------------------------------------------------------------------------
# 5. Repair loop Issue #12: subtier stopping, retention, gap, eligibility, checkpoints
# ---------------------------------------------------------------------------


def test_repair_loop_default_preserves_backward_compat_and_forbid_subtier_retains_best_turn() -> None:
    item = {"id": "WIT-B-01", "family": "B", "prompt": "Write exact checker"}
    lint_oracle = lambda _pv, _c: {"passed": True, "epistemic_status": "LINT_PASS", "findings": []}
    turn1_only_grader = lambda _it, c: {"passed": c == "cand_1", "findings": []}
    gen = lambda _p, t: f"cand_{t}"

    # Default forbid_subtier_early_stop=False preserves backward-compatible turn-1 stop
    default_res = run_repair_item(
        item,
        gen,
        max_turns=4,
        inference_oracle_fn=lint_oracle,
        eval_grader_fn=turn1_only_grader,
        include_plane1_retrieval=False,
    )
    expect_eq(default_res["turns_used"], 1)
    expect_true(default_res["passed"])
    expect_true(default_res["inference_certified"])
    expect_false(default_res["forbid_subtier_early_stop"])

    # Opt-in forbid_subtier_early_stop=True blocks subtier stop AND retains best oracle-passing turn (turn 1)
    strict_res = run_repair_item(
        item,
        gen,
        max_turns=4,
        inference_oracle_fn=lint_oracle,
        eval_grader_fn=turn1_only_grader,
        include_plane1_retrieval=False,
        forbid_subtier_early_stop=True,
    )
    expect_eq(strict_res["turns_used"], 4)
    expect_false(strict_res["inference_certified"])
    expect_eq(strict_res["best_oracle_pass_turn"], 1)
    expect_true(strict_res["pass_at_1"])
    expect_true(strict_res["pass_at_2"])
    expect_true(strict_res["pass_at_3"])
    expect_true(strict_res["pass_at_4"])
    expect_true(strict_res["passed"])
    expect_eq(strict_res["refuted_routes"], [])

    # When a later turn upgrades from LINT_PASS to VERIFIED, strict mode stops and deploys the upgraded turn
    upgrade_oracle = lambda _pv, c: {
        "passed": True,
        "epistemic_status": "VERIFIED" if c == "cand_3" else "LINT_PASS",
        "findings": [],
    }
    turn3_grader = lambda _it, c: {"passed": c == "cand_3", "findings": []}
    up_res = run_repair_item(
        item,
        gen,
        max_turns=4,
        inference_oracle_fn=upgrade_oracle,
        eval_grader_fn=turn3_grader,
        include_plane1_retrieval=False,
        forbid_subtier_early_stop=True,
    )
    expect_eq(up_res["turns_used"], 3)
    expect_true(up_res["inference_certified"])
    expect_eq(up_res["inference_certified_at_turn"], 3)
    expect_false(up_res["pass_at_1"])
    expect_false(up_res["pass_at_2"])
    expect_true(up_res["pass_at_3"])
    expect_true(up_res["passed"])

    # Even with allow_early_stop=False, a later VERIFIED turn outranks an earlier LINT_PASS turn
    no_stop_up = run_repair_item(
        item,
        gen,
        max_turns=4,
        inference_oracle_fn=upgrade_oracle,
        eval_grader_fn=turn3_grader,
        include_plane1_retrieval=False,
        allow_early_stop=False,
        forbid_subtier_early_stop=True,
    )
    expect_eq(no_stop_up["turns_used"], 4)
    expect_false(no_stop_up["inference_certified"])
    expect_eq(no_stop_up["best_oracle_pass_turn"], 3)
    expect_false(no_stop_up["pass_at_1"])
    expect_false(no_stop_up["pass_at_2"])
    expect_true(no_stop_up["pass_at_3"])
    expect_true(no_stop_up["passed"])

    # PROVEN also stops early under forbid_subtier_early_stop=True; missing/unknown status does NOT
    proven_res = run_repair_item(
        item,
        gen,
        max_turns=3,
        inference_oracle_fn=lambda _pv, _c: {"passed": True, "epistemic_status": "PROVEN", "findings": []},
        eval_grader_fn=turn1_only_grader,
        include_plane1_retrieval=False,
        forbid_subtier_early_stop=True,
    )
    expect_eq(proven_res["turns_used"], 1)
    expect_true(proven_res["inference_certified"])

    missing_status_res = run_repair_item(
        item,
        gen,
        max_turns=3,
        inference_oracle_fn=lambda _pv, _c: {"passed": True, "findings": []},
        eval_grader_fn=turn1_only_grader,
        include_plane1_retrieval=False,
        forbid_subtier_early_stop=True,
    )
    expect_eq(missing_status_res["turns_used"], 3)
    expect_false(missing_status_res["inference_certified"])
    expect_true(missing_status_res["passed"])


def test_repair_split_gap_counting_eligibility_wiring_and_checkpoint_invalidation(tmp_path: Path) -> None:
    items = [
        {"id": "A-1", "family": "A", "prompt": "Prove A"},
        {"id": "B-1", "family": "B", "prompt": "Check B1"},
        {"id": "B-2", "family": "B", "prompt": "Check B2"},
    ]
    calls: list[str] = []

    def _gen(prompt: str, turn_idx: int) -> str:
        calls.append(f"{turn_idx}:{prompt[:12]}")
        return f"attempt_{turn_idx}"

    def _inf(pub: Mapping[str, Any], _comp: str) -> dict[str, Any]:
        if pub["family"] == "A":
            return {"passed": True, "epistemic_status": "VERIFIED", "findings": []}
        return {"passed": True, "epistemic_status": "LINT_PASS", "findings": []}

    def _eval(it: Mapping[str, Any], _comp: str) -> dict[str, Any]:
        # Family A passes grader; Family B fails grader (100% false oracle pass rate!)
        return {"passed": it["family"] == "A", "findings": []}

    ckpt = tmp_path / "issue12_ckpt.jsonl"

    # Run 1: default early stop enabled -> all 3 items stop at turn 1
    run1 = run_repair_split(
        items,
        _gen,
        max_turns=3,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt,
    )
    expect_eq(len(calls), 3)
    expect_eq(run1["oracle_grader_gap"]["by_family"]["A"]["false_pass_rate_frac"], "0/1")
    expect_eq(run1["oracle_grader_gap"]["by_family"]["B"]["false_pass_rate_frac"], "1/1")
    expect_eq(run1["oracle_grader_gap"]["by_family"]["B"]["premature_turn1_stops"], 2)
    expect_true(run1["early_stop_eligibility"]["A"]["allow_early_stop"])
    expect_eq(run1["early_stop_eligibility"]["A"]["reason"], "ELIGIBLE")
    expect_false(run1["early_stop_eligibility"]["B"]["allow_early_stop"])
    expect_eq(run1["early_stop_eligibility"]["B"]["reason"], "ORACLE_GAP_EXCEEDS_THRESHOLD")

    # Run 2: resume SAME checkpoint with lowercase `early_stop_disabled_families={"b"}`
    # -> MUST invalidate cached 1-turn Family B records and re-run B for all 3 turns while skipping A!
    calls.clear()
    run2 = run_repair_split(
        items,
        _gen,
        max_turns=3,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt,
        early_stop_disabled_families=frozenset({"b"}),
    )
    expect_eq(run2["early_stop_disabled_families"], ["B"])
    expect_eq(len(calls), 6, "expected 2 Family B items x 3 turns re-run (Family A stays cached)")
    b_rows = [r for r in run2["items"] if r["family"] == "B"]
    expect_eq([r["turns_used"] for r in b_rows], [3, 3])
    # Crucially, Family B STILL measures oracle_passes=2 & ORACLE_GAP_EXCEEDS_THRESHOLD (not 0/UNMEASURED!)
    expect_eq(run2["oracle_grader_gap"]["by_family"]["B"]["oracle_passes"], 2)
    expect_eq(run2["oracle_grader_gap"]["by_family"]["B"]["grader_rejects_among_oracle_passes"], 2)
    expect_eq(run2["oracle_grader_gap"]["by_family"]["B"]["false_pass_rate_frac"], "1/1")
    expect_false(run2["early_stop_eligibility"]["B"]["allow_early_stop"])
    expect_eq(run2["early_stop_eligibility"]["B"]["reason"], "ORACLE_GAP_EXCEEDS_THRESHOLD")

    # Run 3: resume again with same policy -> updated 3-turn records are now cached (0 calls!)
    calls.clear()
    run3 = run_repair_split(
        items,
        _gen,
        max_turns=3,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt,
        early_stop_disabled_families=frozenset({"B"}),
    )
    expect_eq(len(calls), 0, "refreshed 3-turn Family B checkpoint must be reused")
    expect_eq(run3["oracle_grader_gap"]["by_family"]["B"]["oracle_passes"], 2)

    # Run 4: prior_gap_summary automatically disables ineligible Family B on a fresh split
    calls.clear()
    run4 = run_repair_split(
        items,
        _gen,
        max_turns=3,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        prior_gap_summary=run1["oracle_grader_gap"],
    )
    expect_eq(run4["early_stop_disabled_families"], ["B"])
    expect_eq(len(calls), 1 + 3 + 3, "Family A stops at 1; Family B auto-disabled and runs 3 turns each")

    # Run 5: forbid_subtier_early_stop=True invalidates earlier 1-turn LINT_PASS checkpoint
    ckpt2 = tmp_path / "subtier_ckpt.jsonl"
    run_repair_split(
        [items[1]],
        _gen,
        max_turns=3,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt2,
        forbid_subtier_early_stop=False,
    )
    calls.clear()
    run5 = run_repair_split(
        [items[1]],
        _gen,
        max_turns=3,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt2,
        forbid_subtier_early_stop=True,
    )
    expect_eq(len(calls), 3, "forbid_subtier_early_stop=True must invalidate subtier 1-turn checkpoint")
    expect_eq(run5["items"][0]["turns_used"], 3)

    # Run 6: increasing max_turns invalidates an uncertified cached record
    ckpt3 = tmp_path / "budget_grow_ckpt.jsonl"
    always_fail_oracle = lambda _pv, _c: {"passed": False, "epistemic_status": "REJECTED", "findings": []}
    run_repair_split(
        [items[1]],
        _gen,
        max_turns=2,
        inference_oracle_fn=always_fail_oracle,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt3,
    )
    calls.clear()
    run6 = run_repair_split(
        [items[1]],
        _gen,
        max_turns=4,
        inference_oracle_fn=always_fail_oracle,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt3,
    )
    expect_eq(len(calls), 4, "increasing max_turns must invalidate uncertified cached item")
    expect_eq(run6["items"][0]["turns_used"], 4)

    # Run 7: shrinking max_turns (4 -> 2) invalidates cached 4-turn record
    ckpt4 = tmp_path / "budget_shrink_ckpt.jsonl"
    run_repair_split(
        [items[1]],
        _gen,
        max_turns=4,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt4,
        early_stop_disabled_families=frozenset({"B"}),
    )
    calls.clear()
    run7 = run_repair_split(
        [items[1]],
        _gen,
        max_turns=2,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt4,
        early_stop_disabled_families=frozenset({"B"}),
    )
    expect_eq(len(calls), 2, "shrinking max_turns (4 -> 2) must invalidate 4-turn cached record")
    expect_eq(run7["max_turns"], 2)
    expect_eq(run7["items"][0]["max_turns"], 2)
    expect_eq(run7["items"][0]["turns_used"], 2)

    # Run 8: max_turns == 1 policy flips (allow_early_stop True -> False, forbid_subtier False -> True) invalidate
    ckpt5 = tmp_path / "max1_flip_ckpt.jsonl"
    run_repair_split(
        [items[1]],
        _gen,
        max_turns=1,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt5,
    )
    calls.clear()
    run8_disabled = run_repair_split(
        [items[1]],
        _gen,
        max_turns=1,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt5,
        early_stop_disabled_families=frozenset({"B"}),
    )
    expect_eq(len(calls), 1, "max_turns=1 early_stop_disabled policy flip must invalidate cached certified record")
    expect_false(run8_disabled["items"][0]["inference_certified"])
    expect_false(run8_disabled["items"][0]["allow_early_stop"])

    ckpt6 = tmp_path / "max1_subtier_ckpt.jsonl"
    run_repair_split(
        [items[1]],
        _gen,
        max_turns=1,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt6,
        forbid_subtier_early_stop=False,
    )
    calls.clear()
    run8_subtier = run_repair_split(
        [items[1]],
        _gen,
        max_turns=1,
        inference_oracle_fn=_inf,
        eval_grader_fn=_eval,
        include_plane1_retrieval=False,
        checkpoint_jsonl=ckpt6,
        forbid_subtier_early_stop=True,
    )
    expect_eq(len(calls), 1, "max_turns=1 forbid_subtier_early_stop flip must invalidate cached certified record")
    expect_false(run8_subtier["items"][0]["inference_certified"])
    expect_true(run8_subtier["items"][0]["forbid_subtier_early_stop"])


def test_summarize_oracle_grader_gap_legacy_compact_and_eligibility_validation() -> None:
    # Compact legacy receipts (no `turns` key): 23 oracle passes, 15 rejects, 10 turn-1 stops
    compact_rows: list[dict[str, Any]] = []
    for i in range(10):
        compact_rows.append({"family": "B", "inference_certified": True, "passed": False, "turns_used": 1})
    for i in range(5):
        compact_rows.append({"family": "B", "inference_certified": True, "passed": False, "turns_used": 2})
    for i in range(8):
        compact_rows.append({"family": "B", "inference_certified": True, "passed": True, "turns_used": 1})
    compact_rows.append({"family": "B", "inference_certified": False, "passed": True, "turns_used": 4})

    gap = summarize_oracle_grader_gap(compact_rows)
    fam_b = gap["by_family"]["B"]
    expect_eq(fam_b["oracle_passes"], 23)
    expect_eq(fam_b["grader_rejects_among_oracle_passes"], 15)
    expect_eq(fam_b["premature_turn1_stops"], 10)
    expect_eq(fam_b["grader_without_oracle_passes"], 1)
    expect_eq(fam_b["false_pass_rate_frac"], "15/23")

    # Exact eligibility threshold boundaries & underpowered guard
    elig = evaluate_early_stop_eligibility(
        {
            "by_family": {
                "A": {"oracle_passes": 20, "grader_rejects_among_oracle_passes": 1},  # exact 1/20 == threshold -> ELIGIBLE
                "B": {"oracle_passes": 23, "grader_rejects_among_oracle_passes": 15},  # > 1/20 -> ineligible
                "C": {"oracle_passes": 0, "grader_rejects_among_oracle_passes": 0},  # < min_oracle_passes -> underpowered
            }
        },
        max_false_pass_rate=Fraction(1, 20),
        min_oracle_passes=1,
    )
    expect_true(elig["A"]["allow_early_stop"])
    expect_eq(elig["A"]["reason"], "ELIGIBLE")
    expect_false(elig["B"]["allow_early_stop"])
    expect_eq(elig["B"]["reason"], "ORACLE_GAP_EXCEEDS_THRESHOLD")
    expect_false(elig["C"]["allow_early_stop"])
    expect_eq(elig["C"]["reason"], "UNMEASURED_OR_UNDERPOWERED_ORACLE_GAP")

    # Fail-closed ValueError guards on malformed inputs & non-int/bool/float counts
    bad_calls = [
        lambda: evaluate_early_stop_eligibility("not_a_mapping"),  # type: ignore[arg-type]
        lambda: evaluate_early_stop_eligibility({"by_family": {}}, max_false_pass_rate=Fraction(-1, 10)),
        lambda: evaluate_early_stop_eligibility({"by_family": {}}, max_false_pass_rate=Fraction(11, 10)),
        lambda: evaluate_early_stop_eligibility({"by_family": {}}, max_false_pass_rate=0.05),  # type: ignore[arg-type]
        lambda: evaluate_early_stop_eligibility({"by_family": {}}, min_oracle_passes=0),
        lambda: evaluate_early_stop_eligibility({"by_family": {}}, min_oracle_passes=True),
        lambda: evaluate_early_stop_eligibility({"by_family": "not_a_mapping"}),
        lambda: evaluate_early_stop_eligibility({"by_family": {"A": "not_a_mapping"}}),
        lambda: evaluate_early_stop_eligibility({"by_family": {"A": {"oracle_passes": True, "grader_rejects_among_oracle_passes": 0}}}),
        lambda: evaluate_early_stop_eligibility({"by_family": {"A": {"oracle_passes": 5, "grader_rejects_among_oracle_passes": 6}}}),
        lambda: evaluate_early_stop_eligibility({"by_family": {"A": {"oracle_passes": -1, "grader_rejects_among_oracle_passes": 0}}}),
    ]
    for fn in bad_calls:
        with pytest.raises(ValueError):
            fn()
