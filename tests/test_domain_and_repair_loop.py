"""Tests for domain-general DomainOracle protocol, label-free repair loop, stagnation escape, sandbox, and F-01..F-08/A6/A7 gates."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from mcproof.cli import main as cli_main
from mcproof.domain_protocol import (
    BudgetLedger,
    DomainDiagnostic,
    DomainGradeResult,
    DomainOracle,
    FormalVerificationDomainOracle,
    audit_portfolio_bounds,
    audit_transition_certificate,
    loads_strict_certificate_json,
    run_restricted_sandbox_cell,
    verify_dual_product_parity,
    verify_minimal_goal_stopping,
    verify_rational_lp_certificate,
)
from mcproof.paths import repo_root
from mcproof.repair_loop import (
    MAX_RETRIEVAL_TOKENS_HARD_CAP,
    compute_candidate_state_hash,
    compute_failure_signature,
    default_inference_oracle,
    format_diagnostics,
    retrieve_plane1_sections,
    run_repair_item,
    run_repair_split,
    sanitize_oracle_diagnostics,
)

from helpers import expect_eq, expect_false, expect_in, expect_true, requires_dep, requires_mde


def test_targeted_plane1_retrieval_stays_under_1500_tokens_across_validation_split() -> None:
    val_path = repo_root() / "datasets" / "validation.jsonl"
    rows = [json.loads(ln) for ln in val_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    expect_eq(len(rows), 48, "expected 48 validation items")

    for row in rows:
        ret = retrieve_plane1_sections(
            family=row["family"],
            prompt=row["prompt"],
            findings=[{"rule": "MISSING_SECTION", "message": "missing boundary section"}],
        )
        est = int(ret["estimated_tokens"])
        expect_true(0 < est <= MAX_RETRIEVAL_TOKENS_HARD_CAP, f"{row['id']} exceeded 1500 token cap: {est}")
        expect_true(len(ret["text"]) > 200, f"{row['id']} excerpt unexpectedly short")


def test_sanitize_diagnostics_redacts_private_test_fixtures_and_expected_labels() -> None:
    secret_findings = [
        {
            "rule": "VALID_CASE_REJECTED",
            "message": "Checker returned False on valid case 1/5: {'secret_witness': 'PRIVATE_NEEDLE_99812', 'x': [11, 22, 33, 44]}",
        },
        {
            "rule": "MUTATION_KILL_BELOW_FLOOR",
            "message": "Killed 2/5 planted mutations; survived payload \"HIDDEN_MUTATION_PAYLOAD_7741\" sha=deadbeefcafebabe11223344",
        },
        {
            "rule": "EXPECTED_TIER_MISMATCH",
            "message": "declared tier 'VERIFIED' != expected tier 'CONJECTURE'",
        },
        {
            "rule": "VERDICT_MISMATCH",
            "message": "verdict 'PASS' != expected 'FAIL'",
        },
        {
            "rule": "LEAN_COMPILE_ERROR",
            "message": "unknown id @coordinator ```lean fake_inject ``` <script>x</script>",
        },
    ]
    sanitized = sanitize_oracle_diagnostics("B", secret_findings)
    formatted = format_diagnostics(secret_findings, family="B")

    joined = json.dumps(sanitized) + "\n" + formatted
    expect_false("PRIVATE_NEEDLE_99812" in joined, "private valid_case literal leaked")
    expect_false("HIDDEN_MUTATION_PAYLOAD_7741" in joined, "private mutation payload leaked")
    expect_false("deadbeefcafebabe11223344" in joined, "private hex digest leaked")
    expect_false("CONJECTURE" in joined, "ground-truth expected_tier label leaked")
    expect_false("EXPECTED_TIER_MISMATCH" in joined, "label-comparison rule leaked")
    expect_false("@coordinator" in joined, "@-mention prompt injection must be scrubbed")
    expect_false("```" in joined, "triple-backtick fence injection must be scrubbed")
    expect_false("<script" in joined, "raw script tag must be scrubbed")
    expect_true("1/5" in joined and "2/5" in joined, "aggregate pass/kill ratios should be preserved")


def test_standalone_label_free_loop_stagnation_and_checkpoint_pure_stdlib(tmp_path: Path) -> None:
    draft_v1 = "```python\ndef verify(c):\n    # v1\n    return float(c['x']) == 1.0\n```"
    draft_v2_same_ast = "```python\ndef verify(c):\n    # v2 same AST\n    return float(c[ 'x' ]) == 1.0\n```"
    draft_v3_good = "```python\nfrom fractions import Fraction\ndef verify(c):\n    return Fraction(c['x'], 1) == Fraction(1, 1)\n```"

    expect_eq(compute_candidate_state_hash("B", draft_v1), compute_candidate_state_hash("B", draft_v2_same_ast))
    expect_eq(
        compute_failure_signature([{"rule": "FLOAT_CALL", "line": 3}]),
        compute_failure_signature([{"rule": "FLOAT_CALL", "line": 3, "message": "other"}]),
    )

    task = {
        "id": "PURE-B-01",
        "family": "B",
        "expected_tier": "SECRET_DO_NOT_LEAK",
        "prompt": "Write exact checker `def verify(c):` testing `x == 1`.",
    }

    def _pure_inf_oracle(pub: Mapping[str, Any], comp: str) -> dict[str, Any]:
        expect_eq(set(pub.keys()), {"id", "family", "prompt"})
        has_float = "float(" in comp
        return {
            "passed": not has_float,
            "epistemic_status": "LINT_PASS" if not has_float else "REJECTED",
            "findings": [{"rule": "FLOAT_COERCION_CALL", "line": 3, "message": "float() forbidden"}] if has_float else [],
        }

    def _posthoc_eval(_item: Mapping[str, Any], comp: str) -> dict[str, Any]:
        ok = "Fraction(" in comp and "float(" not in comp
        return {
            "passed": ok,
            "findings": [] if ok else [{"rule": "SECRET_EVAL_CANARY", "message": "HIDDEN_GROUND_TRUTH_991"}],
        }

    prompts: list[str] = []

    def _gen(up: str, t_idx: int) -> str:
        prompts.append(up)
        expect_false("SECRET_DO_NOT_LEAK" in up or "HIDDEN_GROUND_TRUTH_991" in up)
        return draft_v1 if t_idx == 1 else (draft_v2_same_ast if t_idx == 2 else draft_v3_good)

    ckpt = tmp_path / "pure_ckpt.jsonl"
    split = run_repair_split(
        [task],
        _gen,
        max_turns=4,
        inference_oracle_fn=_pure_inf_oracle,
        eval_grader_fn=_posthoc_eval,
        checkpoint_jsonl=ckpt,
    )
    res = split["items"][0]
    expect_true(res["passed"])
    expect_eq(res["turns_used"], 3)
    expect_true(res["stagnation_events"] >= 1)
    expect_in("Stagnation Escape Alert", prompts[2])
    expect_in("Refuted Routes (Do Not Re-Explore)", prompts[2])
    expect_eq(len(res["refuted_routes"]), 2)

    prompts.clear()
    split_resumed = run_repair_split(
        [task],
        _gen,
        max_turns=4,
        inference_oracle_fn=_pure_inf_oracle,
        eval_grader_fn=_posthoc_eval,
        checkpoint_jsonl=ckpt,
    )
    expect_eq(len(prompts), 0, "checkpoint resume must skip completed item")
    expect_eq(split_resumed["pass_curve"]["k=4"]["passed"], 1)


@requires_dep("soko")
@requires_mde()
def test_label_free_default_inference_oracle_with_live_soko_and_mde() -> None:
    good_checker = """```python
from fractions import Fraction

def verify(case: dict) -> bool:
    if not isinstance(case, dict):
        return False
    a = case.get("a")
    b = case.get("b")
    s = case.get("sum")
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (a, b, s)):
        return False
    return Fraction(a, 1) + Fraction(b, 1) == Fraction(s, 1)
```"""
    bad_checker = """```python
def verify(case: dict) -> bool:
    return float(case["a"]) + float(case["b"]) == float(case["sum"])
```"""
    task = {
        "id": "SYNTH-B-01",
        "family": "B",
        "expected_tier": "SECRET_GROUND_TRUTH_TIER_DO_NOT_READ",
        "valid_cases": [{"a": 999111, "b": 222333, "sum": 1221444}],
        "prompt": "Write an exact-integer sum verifier `def verify(case: dict) -> bool:` checking `a + b == sum`.",
    }
    inf_bad = default_inference_oracle(task, bad_checker)
    expect_false(inf_bad["passed"], "float() checker must fail static inference audit")
    expect_false("SECRET_GROUND_TRUTH_TIER_DO_NOT_READ" in json.dumps(inf_bad))
    expect_false("999111" in json.dumps(inf_bad))

    inf_good = default_inference_oracle(task, good_checker)
    expect_true(inf_good["passed"], f"exact Fraction checker must pass inference audit: {inf_good}")
    expect_eq(inf_good["epistemic_status"], "LINT_PASS")


def test_pluggable_domain_oracle_protocol_and_budget_ledger() -> None:
    builtin = FormalVerificationDomainOracle()
    expect_true(isinstance(builtin, DomainOracle), "FormalVerificationDomainOracle must satisfy DomainOracle Protocol")
    ctx = builtin.retrieve_plane1_context({"family": "A", "prompt": "Prove Nat clamping bounds using omega."})
    expect_true("Lean" in ctx, "expected Lean Plane 1 guidance")

    class ToyGraphOracle:
        @property
        def domain_id(self) -> str:
            return "mde:toy-graph"

        def retrieve_plane1_context(
            self,
            task: Mapping[str, Any],
            prior_diagnostics: Sequence[DomainDiagnostic] = (),
            max_tokens: int = 1250,
        ) -> str:
            return f"Graph spec for {task['id']} (max={max_tokens}, errs={len(prior_diagnostics)})"

        def grade_candidate(self, task: Mapping[str, Any], candidate: str) -> DomainGradeResult:
            ok = candidate.strip() == str(task["expected"])
            diags = () if ok else (DomainDiagnostic(rule="WRONG_PATH_COST", message="path cost mismatch"),)
            return DomainGradeResult(passed=ok, epistemic_status="VERIFIED" if ok else "REJECTED", diagnostics=diags, metrics={})

        def format_repair_feedback(self, _task: Mapping[str, Any], grade: DomainGradeResult) -> str:
            return "; ".join(f"{d.rule}:{d.message}" for d in grade.diagnostics)

    ext = ToyGraphOracle()
    expect_true(isinstance(ext, DomainOracle), "external specialist class must satisfy DomainOracle without inheritance")
    g_fail = ext.grade_candidate({"id": "G1", "expected": "4"}, "5")
    expect_false(g_fail.passed)
    expect_in("WRONG_PATH_COST", ext.format_repair_feedback({"id": "G1"}, g_fail))

    ledger = BudgetLedger(max_turns=4, max_tokens=1000, max_steps=50)
    ledger.turns_used = 2
    expect_false(ledger.exhausted())
    ledger.steps_used = 50
    expect_true(ledger.exhausted())


def test_restricted_sandbox_cell_enforces_imports_builtins_and_timeout() -> None:
    ok_res = run_restricted_sandbox_cell(
        "from collections import deque\nfrom fractions import Fraction\nq = deque([Fraction(1, 3), Fraction(2, 3)])\nprint(sum(q) + OFFSET)\n",
        injected_globals={"OFFSET": 4},
    )
    expect_true(ok_res["ok"], f"valid pure-algorithmic cell rejected: {ok_res}")
    expect_eq(ok_res["stdout"].strip(), "5")

    for bad_code in (
        "import socket\n",
        "import subprocess\n",
        "from urllib import request\n",
        "import ext_helper\n",
        "f = open('/etc/hosts')\n",
        "x = ().__class__.__bases__[0].__subclasses__()\n",
    ):
        rej = run_restricted_sandbox_cell(bad_code, extra_forbidden_modules=["ext_helper"])
        expect_false(rej["ok"], f"forbidden cell should be rejected: {bad_code!r}")
        expect_true(rej["ast_rejected"], f"expected AST rejection on {bad_code!r}")

    t_out = run_restricted_sandbox_cell("while True:\n    x = 1\n", timeout_sec=0.4)
    expect_false(t_out["ok"], "infinite loop must fail")
    expect_true(t_out["timed_out"], "infinite loop must set timed_out=True")


def test_dual_product_parity_portfolio_bounds_and_goal_stopping_close_f06_f07_and_overrun() -> None:
    f06_coarse = verify_dual_product_parity(
        spec_init=(0, 0),
        impl_init=(0, 0),
        spec_actions=lambda s: ("tick",) if s[0] < 2 else (),
        impl_actions=lambda u: ("tick",) if u[0] < 2 else (),
        spec_step=lambda s, _a: (s[0] + 1, 0),
        impl_step=lambda u, _a: (u[0] + 1, 1 if u[0] + 1 == 2 else 0),
        spec_invariant=lambda s: s[1] == 0,
        impl_invariant=lambda u: u[1] == 0,
        spec_is_goal=lambda s: s[0] == 2,
        impl_is_goal=lambda u: u[0] == 2,
        spec_obs=lambda _s: 0,
        impl_obs=lambda _u: 0,
    )
    expect_false(f06_coarse["passed"])
    expect_in("F06_IMPL_INVARIANT_VIOLATION_OR_DIVERGENCE", {f["rule"] for f in f06_coarse["findings"]})

    f06_collapsed = verify_dual_product_parity(
        spec_init=0,
        impl_init=0,
        spec_actions=lambda s: ("a", "b") if s == 0 else (),
        impl_actions=lambda u: ("a", "b") if u == 0 else (),
        spec_step=lambda _s, _act: 1,
        impl_step=lambda _u, act: 1 if act == "a" else 2,
        spec_invariant=lambda s: s in (0, 1),
        impl_invariant=lambda u: u in (0, 1),
        spec_is_goal=lambda s: s == 1,
        impl_is_goal=lambda u: u in (1, 2),
        spec_obs=lambda s: 0 if s == 0 else 1,
        impl_obs=lambda u: 0 if u == 0 else 1,
    )
    expect_false(f06_collapsed["passed"])
    expect_in("F06_IMPL_INVARIANT_VIOLATION_OR_DIVERGENCE", {f["rule"] for f in f06_collapsed["findings"]})

    f06_clean = verify_dual_product_parity(
        spec_init=0,
        impl_init=0,
        spec_actions=lambda s: ("a", "b") if s < 2 else (),
        impl_actions=lambda u: ("a", "b") if u < 2 else (),
        spec_step=lambda s, act: s + (1 if act == "a" else 2),
        impl_step=lambda u, act: u + (1 if act == "a" else 2),
        spec_invariant=lambda s: 0 <= s <= 3,
        impl_invariant=lambda u: 0 <= u <= 3,
        spec_is_goal=lambda s: s == 2,
        impl_is_goal=lambda u: u == 2,
        spec_obs=lambda s: s,
        impl_obs=lambda u: u,
    )
    expect_true(f06_clean["passed"])
    expect_eq(f06_clean["epistemic_status"], "PROVEN")

    port_bad = audit_portfolio_bounds(
        [
            {"id": "ITEM-INV", "proven_floor": 50, "shortest_known": 48, "epistemic_status": "VERIFIED"},
            {"id": "ITEM-UNREG", "proven_floor": 40, "shortest_known": 48, "epistemic_status": "VERIFIED"},
        ],
        registered_verified_ids=frozenset(),
    )
    expect_false(port_bad["passed"])
    p_rules = {f["rule"] for f in port_bad["findings"]}
    expect_in("CERT_F07_INCONSISTENT_PORTFOLIO_BOUNDS", p_rules)
    expect_in("CERT_F07_UNVERIFIED_CALLER_BOUNDS", p_rules)

    overrun = verify_minimal_goal_stopping(
        init_state=0,
        actions=[1, 1, 1],
        step_fn=lambda s, a: s + a,
        is_goal_fn=lambda s: s == 2,
    )
    expect_false(overrun["passed"])
    expect_in("CERT_POST_GOAL_EXTRA_ACTIONS", {f["rule"] for f in overrun["findings"]})

    exact_stop = verify_minimal_goal_stopping(
        init_state=0,
        actions=[1, 1],
        step_fn=lambda s, a: s + a,
        is_goal_fn=lambda s: s == 2,
    )
    expect_true(exact_stop["passed"])


def test_audit_transition_certificate_catches_f01_to_f08_and_a6_a7(tmp_path: Path) -> None:
    valid_cert = {
        "epistemic_status": "VERIFIED",
        "proof_mode": "quotient_homomorphism",
        "complete_space": True,
        "complete_domain_closed": True,
        "differential_match": True,
        "oracles_checked": ["ref_spec_oracle", "flat_bitmask_oracle"],
        "includes_hidden_state": True,
        "exact_optimum_reached": True,
        "proven_floor": 12,
        "witness": "UUDDLRLRBAAB",
        "witness_cost": 12,
        "witness_or_proof_sha256": "a" * 64,
        "instance_sha256": "b" * 64,
        "canonical_instance_sha256": "b" * 64,
        "step_consistency_violations": 0,
        "must_fail_controls": ["corrupt_floor_plus_one", "truncate_witness_tail"],
        "control_records": [
            {"name": "corrupt_floor_plus_one", "oracle_invoked": True, "unexpectedly_passed": False},
            {"name": "truncate_witness_tail", "oracle_invoked": True, "unexpectedly_passed": False},
        ],
        "tcb_pins": {
            "tcb_manifest_verified": True,
            "checker_sha256": "c" * 64,
        },
    }
    clean = audit_transition_certificate(
        valid_cert,
        require_must_fail_controls=True,
        registered_artifact_digests=frozenset({"a" * 64}),
    )
    expect_true(clean["passed"], f"valid certificate rejected: {clean}")

    corruptions: list[tuple[str, dict[str, Any]]] = [
        ("CERT_SINGLE_ORACLE_DIFFERENTIAL", {**valid_cert, "oracles_checked": ["only_one"]}),
        ("CERT_PARTIAL_STATE_PROJECTION", {**valid_cert, "includes_hidden_state": False}),
        ("CERT_TCB_MANIFEST_UNLOCKED", {**valid_cert, "tcb_pins": {"tcb_manifest_verified": False, "checker_sha256": "short"}}),
        ("CERT_UNWITNESSED_VERIFIED_OPTIMUM", {**valid_cert, "witness": None, "exact_optimum_reached": False}),
        ("CERT_STEP_INCONSISTENCY", {**valid_cert, "step_consistency_violations": 1}),
        ("CERT_TRUNCATED_INDUCTIVE_POTENTIAL", {**valid_cert, "proof_mode": "inductive_potential", "complete_domain_closed": False}),
        (
            "CERT_IMPL_INVARIANT_SKIPPED",
            {**valid_cert, "epistemic_status": "PROVEN", "impl_invariant_checked": False, "obs_projection_injective": False},
        ),
        ("CERT_UNVERIFIED_CALLER_INFLATION", {**valid_cert, "caller_bounds_verified": False}),
        ("CERT_INVALID_WITNESS_SHA256", {**valid_cert, "witness_or_proof_sha256": "ab"}),
        ("CERT_A6_MISSING_OR_DUPLICATE_CONTROLS", {**valid_cert, "must_fail_controls": ["dup_ctrl", "dup_ctrl"]}),
        (
            "CERT_A6_TAUTOLOGICAL_CONTROL",
            {
                **valid_cert,
                "control_records": [{"name": "seeded_noop", "oracle_invoked": False, "seed_equals_target": True}],
            },
        ),
        ("CERT_A7_ILLEGAL_TIER_SWAP", {**valid_cert, "prior_status": "LINT_PASS"}),
        ("CERT_A7_ILLEGAL_TIER_SWAP", {**valid_cert, "prior_status": "LOWER_BOUND_UNWITNESSED"}),
    ]
    for expected_rule, bad_cert in corruptions:
        res = audit_transition_certificate(bad_cert, require_must_fail_controls=True)
        expect_false(res["passed"], f"expected {expected_rule} to fail closed")
        rules = {f["rule"] for f in res["findings"]}
        expect_in(expected_rule, rules)

    unreg = audit_transition_certificate(
        valid_cert,
        registered_artifact_digests=frozenset({"d" * 64}),
    )
    expect_false(unreg["passed"])
    expect_in("CERT_UNREGISTERED_WITNESS_DIGEST", {f["rule"] for f in unreg["findings"]})

    cert_file = tmp_path / "cert.json"
    cert_file.write_text(json.dumps(valid_cert), encoding="utf-8", newline="\n")
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        expect_eq(cli_main(["--json", "audit-cert", str(cert_file)]), 0)
        for bad_raw in (
            '{"proven_floor": 12.5}',
            '{"proven_floor": 12, "proven_floor": 13}',
            '{"proven_floor": ' + ("9" * 65) + "}",
        ):
            bad_file = tmp_path / "bad_strict.json"
            bad_file.write_text(bad_raw, encoding="utf-8", newline="\n")
            expect_false(cli_main(["--json", "audit-cert", str(bad_file)]) == 0)
    finally:
        sys.stdout = old_stdout
    expect_eq(loads_strict_certificate_json('{"a": 42, "b": "7/3"}')["a"], 42)

    lp_bounds_ok = verify_rational_lp_certificate(
        {
            "mode": "bounds",
            "A": [[1, 1], [2, 0]],
            "b": [9, 8],
            "c": [2, 1],
            "y": ["1", "1/2"],
            "claimed_lower_bound": "13",
        }
    )
    expect_true(lp_bounds_ok["passed"])
    expect_eq(lp_bounds_ok["dual_objective"], "13/1")

    lp_bool_sneak = verify_rational_lp_certificate(
        {"mode": "bounds", "A": [[1]], "b": [True], "c": [1], "y": [1], "claimed_lower_bound": 1}
    )
    expect_false(lp_bool_sneak["passed"])

    lp_farkas_ok = verify_rational_lp_certificate({"mode": "infeasible", "A": [[-1, -1]], "b": [1], "y": [1]})
    expect_true(lp_farkas_ok["passed"])
