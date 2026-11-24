"""Cross-architecture adversarial regression suite (`NEON-C1..C4` & `NEON-D1/D2/D5`)."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from mcproof.domain_protocol import (
    audit_sandbox_cell_ast,
    audit_transition_certificate,
    run_restricted_sandbox_cell,
)
from mcproof.lean_harness import (
    audit_weak_statements,
    build_capped_lean_args,
    extract_normalized_lean_defs,
    verify_pinned_lean_defs,
)
from mcproof.mutation import audit_exact_checker_ast, run_checker_mutation_suite
from mcproof.oracles import run_checker_oracle
from mcproof.paths import repo_root
from mcproof.repair_loop import (
    _strip_lean_comments,
    compute_candidate_state_hash,
    default_dataset_item_grader,
    default_inference_oracle,
    retrieve_plane1_excerpt,
    run_repair_item,
)

from helpers import expect_eq, expect_false, expect_in, expect_true, requires_dep, requires_lean, requires_mde


def test_neon_c1_pure_ast_allowlist_and_mutation_suite_confinement(tmp_path: Path) -> None:
    marker = tmp_path / "MUST_NEVER_BE_WRITTEN.txt"
    malicious_py = (
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('PWN', encoding='utf-8')\n"
        "def verify(x):\n"
        "    return x == 1\n"
    )
    ast_findings = audit_exact_checker_ast(malicious_py)
    expect_in("FORBIDDEN_CHECKER_IMPORT", {f["rule"] for f in ast_findings})

    mut_rep = run_checker_mutation_suite(
        malicious_py,
        valid_cases=[{"args": [1]}],
        planted_mutations=[{"name": "m0", "args": [2]}],
    )
    expect_false(mut_rep.passed)
    expect_false(marker.exists(), "mutation suite must never execute unallowlisted imports on host")

    neg_pow_py = "def verify(x: int) -> bool:\n    return (2 ** -1) == x\n"
    expect_in("NEGATIVE_POW_FLOAT_COERCION", {f["rule"] for f in audit_exact_checker_ast(neg_pow_py)})

    for hop_py in (
        "import typing\n_io = typing.sys.modules.get('_io')\ndef verify(x): return x == 1\n",
        "import collections\ns = collections._sys\ndef verify(x): return x == 1\n",
        "from json import codecs\ndef verify(x): return x == 1\n",
        "from fractions import *\ndef verify(x): return x == 1\n",
        "from collections import _sys\ndef verify(x): return x == 1\n",
        "fn = open\ndef verify(x): return x == 1\n",
    ):
        expect_true(len(audit_exact_checker_ast(hop_py)) > 0, f"module-hop/builtin bypass missed: {hop_py!r}")


@requires_dep("soko")
@requires_mde()
def test_neon_c1_run_checker_oracle_never_executes_unallowlisted_or_rejected_code(tmp_path: Path) -> None:
    marker_pass = tmp_path / "HOST_EXECUTED_AND_PASSED.txt"
    malicious_pass_py = (
        "import pathlib\n"
        f"pathlib.Path({str(marker_pass)!r}).write_text('PASSED_AND_WROTE_HOST', encoding='utf-8')\n"
        "def verify(x):\n"
        "    return x == 1\n"
    )
    rec_pass = run_checker_oracle(malicious_pass_py, entry_fn="verify", valid_cases=(), allow_static_lint_only=True)
    expect_false(rec_pass.passed, "pathlib import must be rejected")
    expect_in("FORBIDDEN_CHECKER_IMPORT", {f["rule"] for f in rec_pass.findings})
    expect_false(marker_pass.exists(), "pathlib checker must never execute on host")

    marker_rej = tmp_path / "HOST_EXECUTED_DESPITE_REJECT.txt"
    malicious_rej_py = (
        "import pathlib\n"
        f"pathlib.Path({str(marker_rej)!r}).write_text('EXECUTED_DESPITE_STATIC_REJECT', encoding='utf-8')\n"
        "def verify(x):\n"
        "    return float(x) == 1.0\n"
    )
    rec_rej = run_checker_oracle(malicious_rej_py, entry_fn="verify", valid_cases=())
    expect_false(rec_rej.passed)
    expect_false(marker_rej.exists(), "statically rejected checker must never execute on host")

    marker_hop = tmp_path / "HOST_EXECUTED_TYPING_SYS.txt"
    typing_hop_py = (
        "import typing\n"
        "_io = typing.sys.modules.get('io') or typing.sys.modules.get('_io')\n"
        "if _io:\n"
        f"    with _io.open({str(marker_hop)!r}, 'w') as fh:\n"
        "        fh.write('PWN_TYPING_SYS')\n"
        "def verify(x):\n"
        "    return x == 1\n"
    )
    rec_hop = run_checker_oracle(typing_hop_py, entry_fn="verify", valid_cases=(), allow_static_lint_only=True)
    expect_false(rec_hop.passed, "typing.sys.modules['_io'] module-hop must be rejected")
    expect_in("FORBIDDEN_CHECKER_IO_ATTR", {f["rule"] for f in rec_hop.findings})
    expect_false(marker_hop.exists(), "typing.sys module-hop must never execute on host")


@requires_dep("soko")
@requires_lean()
def test_neon_c2_family_a_theorem_substitution_and_comment_mention_blocked() -> None:
    val_lines = (repo_root() / "datasets" / "validation.jsonl").read_text(encoding="utf-8").splitlines()
    fam_a_item = next(json.loads(ln) for ln in val_lines if json.loads(ln)["family"] == "A")
    harness_a = json.loads((repo_root() / "datasets" / fam_a_item["harness_path"]).read_text(encoding="utf-8"))
    thm_short = str(harness_a["theorem_name"]).split(".")[-1]

    # 1. Retyped trivial theorem with valid def sumOdd
    bogus_retyped = (
        "```lean\nnamespace PubAV01\n"
        "def sumOdd : Nat → Nat\n  | 0 => 0\n  | n + 1 => sumOdd n + (2 * n + 1)\n"
        f"theorem {thm_short} : 1 + 1 = 2 := rfl\nend PubAV01\n```"
    )
    inf_retyped = default_inference_oracle(
        {"id": fam_a_item["id"], "family": "A", "prompt": fam_a_item["prompt"]},
        bogus_retyped,
    )
    grad_retyped = default_dataset_item_grader(fam_a_item, bogus_retyped)
    expect_false(inf_retyped["passed"], f"retyped theorem must fail inference oracle: {inf_retyped}")
    expect_false(grad_retyped["passed"], f"retyped theorem must fail dataset grader: {grad_retyped}")

    # 2. Comment-only theorem mention
    bogus_comment = f"```lean\n-- {thm_short}\ntheorem unrelated_trivial : 2 + 2 = 4 := rfl\n```"
    inf_comment = default_inference_oracle(
        {"id": fam_a_item["id"], "family": "A", "prompt": fam_a_item["prompt"]},
        bogus_comment,
    )
    grad_comment = default_dataset_item_grader(fam_a_item, bogus_comment)
    expect_false(inf_comment["passed"], "comment-only theorem mention must fail inference oracle")
    expect_false(grad_comment["passed"], "comment-only theorem mention must fail dataset grader")

    # 3. Genuine positive completion with alpha-renamed theorem binder variable must still pass both!
    alpha_valid = (
        "```lean\nnamespace PubAV01\n"
        "def sumOdd : Nat → Nat\n  | 0 => 0\n  | n + 1 => sumOdd n + (2 * n + 1)\n"
        "theorem sumOdd_eq_sq (m : Nat) : sumOdd m = m * m := by\n"
        "  induction m with\n  | zero => rfl\n"
        "  | succ k ih =>\n    simp only [sumOdd, ih]\n"
        "    rw [Nat.add_mul, Nat.mul_add, Nat.one_mul, Nat.mul_one]\n    omega\n"
        "end PubAV01\n```"
    )
    inf_valid = default_inference_oracle(
        {"id": fam_a_item["id"], "family": "A", "prompt": fam_a_item["prompt"]},
        alpha_valid,
    )
    grad_valid = default_dataset_item_grader(fam_a_item, alpha_valid)
    expect_true(inf_valid["passed"], f"alpha-renamed valid proof rejected by inference oracle: {inf_valid}")
    expect_true(grad_valid["passed"], f"alpha-renamed valid proof rejected by dataset grader: {grad_valid}")


def test_neon_c3_lean_harness_trust0_pinned_defs_and_weak_statements() -> None:
    cmd = build_capped_lean_args("/usr/bin/lean", Path("Test.lean"))
    expect_in("--trust=0", cmd)

    prompt_pm = (
        "def vecDot : List Int → List Int → Int\n"
        "  | [], _ => 0\n  | _, [] => 0\n  | x :: xs, y :: ys => x * y + vecDot xs ys\n"
    )
    mutated_pm = "def vecDot : List Int → List Int → Int\n  | _, _ => 0\n"
    expect_true("vecDot" in extract_normalized_lean_defs(prompt_pm))
    expect_in("TARGET_DEF_BODY_MUTATED", {f["rule"] for f in verify_pinned_lean_defs(prompt_pm, mutated_pm)})

    prompt_eq = "def clampNat (lo hi x : Nat) : Nat := if x < lo then lo else if hi < x then hi else x\n"
    cand_abbrev = "abbrev clampNat (lo hi x : Nat) : Nat := lo\n"
    cand_ws = "def clampNat (lo hi x: Nat) : Nat := if x < lo then lo else if hi < x then hi else x\n"
    expect_in("TARGET_DEF_BODY_MUTATED", {f["rule"] for f in verify_pinned_lean_defs(prompt_eq, cand_abbrev)})
    expect_eq(verify_pinned_lean_defs(prompt_eq, cand_ws), [], "binder whitespace must not false-positive")

    expect_in("VACUOUS_TRUE_CONCLUSION", {f["rule"] for f in audit_weak_statements("theorem t : (True) := trivial\n")})
    expect_in(
        "VACUOUS_FALSE_HYPOTHESIS",
        {f["rule"] for f in audit_weak_statements("theorem t : (False) → 1 = 2 := fun h => False.elim h\n")},
    )
    expect_in(
        "VACUOUS_FALSE_HYPOTHESIS",
        {f["rule"] for f in audit_weak_statements("theorem t (h : True → False) : 1 = 2 := False.elim (h trivial)\n")},
    )


def test_neon_c4_nested_comments_period2_oscillation_and_chunk_rotation() -> None:
    nested_1 = "theorem t : 1 = 1 := /- outer /- inner -/ still comment A -/ rfl"
    nested_2 = "theorem t : 1 = 1 := /- outer /- inner -/ still comment B -/ rfl"
    expect_eq(_strip_lean_comments(nested_1), "theorem t : 1 = 1 := rfl")
    expect_eq(
        compute_candidate_state_hash("A", f"```lean\n{nested_1}\n```"),
        compute_candidate_state_hash("A", f"```lean\n{nested_2}\n```"),
    )

    osc_calls: list[int] = []

    def _osc_inf(_pv: object, _comp: str) -> dict[str, object]:
        idx = len(osc_calls)
        osc_calls.append(idx)
        rule = "RULE_X" if idx % 2 == 0 else "RULE_Y"
        return {"passed": False, "epistemic_status": "REJECTED", "findings": [{"rule": rule, "line": 1, "message": rule}]}

    osc_res = run_repair_item(
        {"id": "OSC-1", "family": "A", "prompt": "Prove something"},
        lambda _p, t: f"```lean\ntheorem t{t} : 1 = 1 := rfl\n```",
        max_turns=4,
        inference_oracle_fn=_osc_inf,
        eval_grader_fn=lambda _it, _c: {"passed": False, "findings": []},
        include_plane1_retrieval=False,
    )
    expect_true(osc_res["stagnation_events"] >= 1, "period-2 error oscillation must trigger stagnation escape")

    multi_findings = [{"rule": "LEAN_COMPILE_ERROR", "message": f"e{i}"} for i in range(6)]
    ret1 = retrieve_plane1_excerpt(
        family="A",
        prompt_text="Prove Lean 4 theorem with induction and omega",
        prior_findings=multi_findings,
        exclude_chunk_ids=(),
        prefer_worked_examples=False,
    )
    ret2 = retrieve_plane1_excerpt(
        family="A",
        prompt_text="Prove Lean 4 theorem with induction and omega",
        prior_findings=multi_findings,
        exclude_chunk_ids=ret1["chunk_ids"],
        prefer_worked_examples=True,
    )
    expect_eq(set(ret1["chunk_ids"]) & set(ret2["chunk_ids"]), set(), "excluded chunks must rotate cleanly")


@requires_dep("soko")
@requires_mde()
def test_neon_c4_family_b_entry_fn_ignores_generator_helpers() -> None:
    fam_b_prompt = (
        "Given generator:\n```python\ndef check_input_bounds(n):\n    return n > 0\n"
        "def generate(n):\n    return n * 2\n```\n"
        "Implement `verify(n, out)` returning True iff `out == 2 * n`."
    )
    valid_checker_b = (
        "```python\ndef verify(n, out):\n"
        "    return type(n) is int and type(out) is int and n > 0 and out == 2 * n\n```"
    )
    res = default_inference_oracle({"id": "B-MIS", "family": "B", "prompt": fam_b_prompt}, valid_checker_b)
    expect_true(res["passed"], f"valid `verify` rejected due to generator `check_input_bounds`: {res}")


def test_neon_d1_d2_d5_domain_protocol_allowlist_and_fail_closed_certs() -> None:
    for mod_code in (
        "import posix\n",
        "import _io\n",
        "import nt\n",
        "import _posixsubprocess\n",
        "import typing\nx = typing.sys\n",
        "import collections\nx = collections._sys\n",
        "from json import codecs\n",
        "from fractions import *\n",
        "fn = open\n",
    ):
        rej = run_restricted_sandbox_cell(mod_code)
        expect_false(rej["ok"], f"{mod_code!r} must be blocked by sandbox allowlist")
        expect_true(rej["ast_rejected"])

    expect_true(len(audit_sandbox_cell_ast("x = 2 ** -1\n", strict_exact_math=True)) > 0)

    bare_proven = audit_transition_certificate({"epistemic_status": "PROVEN"})
    expect_false(bare_proven["passed"], "bare PROVEN cert without tcb_pins/witness_or_proof_sha256 must fail")
    bare_rules = {f["rule"] for f in bare_proven["findings"]}
    expect_in("CERT_TCB_MANIFEST_UNLOCKED", bare_rules)
    expect_in("CERT_INVALID_WITNESS_SHA256", bare_rules)

    trunc_dijkstra = audit_transition_certificate(
        {
            "epistemic_status": "PROVEN",
            "certificate_kind": "EXACT_DIJKSTRA_OPTIMUM",
            "truncated_by_budget": True,
            "witness_or_proof_sha256": "a" * 64,
            "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": "b" * 64},
        }
    )
    expect_false(trunc_dijkstra["passed"], "truncated_by_budget=True cannot claim PROVEN EXACT_DIJKSTRA_OPTIMUM")
    expect_in("CERT_TRUNCATED_SEARCH_BUDGET", {f["rule"] for f in trunc_dijkstra["findings"]})
