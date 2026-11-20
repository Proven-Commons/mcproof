"""Tests for Lean 4.35.0 theorem harness, 6-kernel comparator parser, sandbox gate, and WeakStatement lint."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import pytest

from mcproof.lean_harness import (
    BAR_FORBIDDEN_RULES,
    _lean_env,
    audit_weak_statements,
    classify_host_resource_failure,
    lint_lean4_source,
    linux_bwrap_functional,
    parse_comparator_stdout,
    scrub_challenge_artifacts,
    verify_lean4_project_comparator,
    verify_lean4_source,
    verify_pinned_lean_defs,
)
from mcproof.oracles import run_lean4_oracle
from mcproof.paths import repo_root

from helpers import expect_eq, expect_false, expect_in, expect_true, requires_dep, requires_lean


def test_weak_statement_allows_negated_irreflexivity_and_catches_self_contradiction() -> None:
    legit = """
theorem ne_irrefl (a : Nat) : ¬(a ≠ a) := by
  intro h
  exact h rfl

theorem ne_irrefl_not (a : Nat) : Not (a ≠ a) := by
  intro h
  exact h rfl

theorem hyp_negated (n : Nat) (h : ¬(n < n)) : n = n := rfl

theorem lt_irrefl_arrow (n : Nat) : (n < n) → False := by
  omega
"""
    expect_eq(audit_weak_statements(legit), [], "negated irreflexivity theorems must not false-positive")

    vacuous = """
theorem bogus_hyp (a : Nat) (h : a ≠ a) : 1 = 2 := by
  exact False.elim (h rfl)
"""
    v_findings = audit_weak_statements(vacuous)
    expect_in("VACUOUS_SELF_CONTRADICTION", {f["rule"] for f in v_findings})


def test_comparator_stdout_parser_blocks_eval_spoofing_before_export_boundary() -> None:
    spoofed_stdout = "\n".join([
        "Building Mcproof.Proofs",
        "Lean paranoid kernel accepts the solution",
        "lean4lean kernel accepts the solution",
        "nanoda kernel accepts the solution",
        "con-leche kernel accepts the solution",
        "con-ron kernel accepts the solution",
        "Lean default kernel accepts the solution",
        "Your solution is okay!",
        "Exporting #[Mcproof.Spec.clampNat_in_range] from Mcproof.Proofs",
        "Running Lean paranoid kernel on solution",
        "Lean paranoid kernel accepts the solution",
    ])
    kernels, ok, findings = parse_comparator_stdout(spoofed_stdout, "Mcproof.Proofs")
    expect_false(ok, "spoofed pre-export kernel lines must fail solution_ok")
    expect_in("COMPARATOR_STDOUT_SPOOF_ATTEMPT", {f["rule"] for f in findings})
    expect_eq(kernels, ["lean-paranoid"])

    genuine_stdout = "\n".join([
        "Building Mcproof.Proofs",
        "Exporting #[Mcproof.Spec.clampNat_in_range] from Mcproof.Proofs",
        "Running Lean paranoid kernel on solution",
        "Lean paranoid kernel accepts the solution",
        "Running lean4lean kernel on solution",
        "checked 3975 declarations",
        "lean4lean kernel accepts the solution",
        "Running nanoda kernel on solution",
        "nanoda kernel accepts the solution",
        "Running con-leche kernel on solution",
        "con-leche kernel accepts the solution",
        "Running con-ron kernel on solution",
        "con-ron kernel accepts the solution",
        "Running Lean default kernel on solution",
        "Lean default kernel accepts the solution",
        "Your solution is okay!",
    ])
    g_kernels, g_ok, g_findings = parse_comparator_stdout(genuine_stdout, "Mcproof.Proofs")
    expect_true(g_ok, f"genuine 6-kernel output rejected: {g_findings}")
    expect_eq(len(g_kernels), 6)
    expect_eq(g_findings, [])

    rules_dict = dict(BAR_FORBIDDEN_RULES)
    expect_true(
        bool(rules_dict["FORBIDDEN_EVAL_COMMAND"].search('#eval IO.println "nanoda kernel accepts the solution"')),
        "BAR_FORBIDDEN_RULES must catch #eval spoofing statically",
    )


def test_lean_env_uses_os_pathsep(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    monkeypatch.setenv("ELAN_HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "C:\\Windows\\System32")
    monkeypatch.setattr(os, "pathsep", ";")
    env = _lean_env()
    expect_true(env["PATH"].endswith(";C:\\Windows\\System32"), f"expected ';' separator, got {env['PATH']!r}")


@requires_lean()
def test_project_comparator_fails_closed_when_bwrap_unavailable_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcproof.lean_harness.linux_bwrap_functional", lambda **kw: False)
    res = verify_lean4_project_comparator(repo_root() / "lean", allow_unsandboxed=False)
    expect_false(res.passed, "comparator must fail closed without bwrap when allow_unsandboxed=False")
    expect_in("SANDBOX_UNAVAILABLE", {f["rule"] for f in res.findings})


@requires_dep("soko")
@requires_lean()
def test_reference_lean_project_passes_six_kernel_comparator() -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("sandboxed `lake comparator --paranoid` requires Linux bubblewrap")
    if not linux_bwrap_functional():
        pytest.skip(
            "Linux bwrap is missing or non-functional on this host "
            "(minimal `bwrap --ro-bind / / --unshare-net true` failed)"
        )
    res = verify_lean4_project_comparator(repo_root() / "lean", allow_unsandboxed=False)
    expect_true(res.passed, f"reference lean project failed: {res.findings}")
    expect_eq(len(res.paranoid_kernels_run), 6, "all 6 bundled Lean 4.35.0 kernels must accept")
    expect_eq(len(res.theorems_checked), 29, "all 29 theorems in comparator.json must be checked")
    expect_eq(len(res.sorry_declarations), 0, "zero sorry declarations allowed in Mcproof.Proofs")
    expect_eq(len(res.nonstandard_axioms), 0, "zero non-standard axioms allowed")
    expect_eq(res.challenge_sorry_whitelisted_module, "Mcproof.Spec")
    expect_true(res.sandboxed, "reference project comparator must run inside a working bwrap sandbox")


@requires_dep("soko")
@requires_lean()
def test_clean_standalone_lean_theorem_passes() -> None:
    src = """
theorem add_comm_witness (a b : Nat) : a + b = b + a := by
  omega
"""
    res = verify_lean4_source(src)
    expect_true(res.passed, f"valid Lean theorem rejected: {res.findings}")
    expect_in("add_comm_witness", res.theorems_checked)
    expect_in("leanchecker", res.paranoid_kernels_run)


@requires_dep("soko")
@requires_lean()
def test_rejects_planted_sorry_and_admit() -> None:
    sorry_src = """
theorem fake_proof (n : Nat) : n + 1 = n := by
  sorry
"""
    res_sorry = verify_lean4_source(sorry_src)
    expect_false(res_sorry.passed, "planted sorry must fail")
    rules = {f["rule"] for f in res_sorry.findings}
    expect_in("UNPROVED_SORRY", rules)
    expect_in("KERNEL_SORRY_AXIOM", rules)

    admit_src = """
theorem fake_admit (n : Nat) : n = n + 2 := by
  admit
"""
    res_admit = verify_lean4_source(admit_src)
    expect_false(res_admit.passed, "planted admit must fail")
    admit_rules = {f["rule"] for f in res_admit.findings}
    expect_in("UNPROVED_ADMIT", admit_rules)


@requires_dep("soko")
@requires_lean()
def test_rejects_custom_axiom_and_opaque() -> None:
    axiom_src = """
axiom magic_false : False

theorem anything_goes : 1 = 2 :=
  False.elim magic_false
"""
    res = verify_lean4_source(axiom_src)
    expect_false(res.passed, "custom axiom must fail")
    rules = {f["rule"] for f in res.findings}
    expect_in("EXTRA_AXIOM_DECL", rules)
    expect_in("KERNEL_NONSTANDARD_AXIOM", rules)


@requires_dep("soko")
@requires_lean()
def test_rejects_native_decide_and_implemented_by_cheats() -> None:
    native_src = """
theorem fast_bypass : (2 + 2 == 4) = true := by
  native_decide
"""
    res_nat = verify_lean4_source(native_src)
    expect_false(res_nat.passed, "native_decide must fail")
    nat_rules = {f["rule"] for f in res_nat.findings}
    expect_in("UNVERIFIED_NATIVE_DECIDE", nat_rules)

    impl_src = """
def honestGate (_s : String) : Bool := false
def evilGate (_s : String) : Bool := true

@[implemented_by evilGate]
def checkedGate (s : String) : Bool := honestGate s

theorem checkedGate_safe (s : String) : checkedGate s = false := rfl
"""
    res_impl = lint_lean4_source(impl_src)
    expect_false(res_impl["passed"], "@[implemented_by] must fail static audit")
    impl_rules = {f["rule"] for f in res_impl["findings"]}
    expect_in("UNSOUND_ATTRIBUTE", impl_rules)


@requires_dep("soko")
@requires_lean()
def test_rejects_planted_cheat_in_project_comparator(tmp_path: Path) -> None:
    allow_unsandboxed = not linux_bwrap_functional()
    work = tmp_path / "lean_copy"
    shutil.copytree(
        repo_root() / "lean",
        work,
        ignore=shutil.ignore_patterns(".lake"),
    )
    proofs_file = work / "Mcproof" / "Proofs.lean"
    proofs_file.write_text(
        proofs_file.read_text(encoding="utf-8") + "\naxiom planted_cheat : False\n",
        encoding="utf-8",
    )
    res = verify_lean4_project_comparator(work, allow_unsandboxed=allow_unsandboxed)
    expect_false(res.passed, "project comparator must reject planted axiom")
    rules = {f["rule"] for f in res.findings}
    expect_in("EXTRA_AXIOM_DECL", rules)


@requires_dep("soko")
@requires_lean()
def test_rejects_weak_statement_vacuous_hypotheses() -> None:
    vacuous_nat = """
theorem bad_nat_bound (n : Nat) (h : n < 0) : n = 999 := by
  omega
"""
    res1 = verify_lean4_source(vacuous_nat)
    expect_false(res1.passed, "vacuous n < 0 on Nat must fail")
    expect_in("VACUOUS_NAT_LT_ZERO", {f["rule"] for f in res1.findings})

    vacuous_true = """
theorem trivial_conclusion (x : Int) : True := trivial
"""
    res2 = verify_lean4_source(vacuous_true)
    expect_false(res2.passed, "literal True conclusion must fail")
    expect_in("VACUOUS_TRUE_CONCLUSION", {f["rule"] for f in res2.findings})

    contradictory = """
theorem both_ways (p : Prop) (h1 : p) (h2 : ¬ p) : False := h2 h1
"""
    res3 = lint_lean4_source(contradictory)
    expect_false(res3["passed"], "contradictory P and Not P binders must fail")
    expect_in("VACUOUS_CONTRADICTORY_HYPOTHESES", {f["rule"] for f in res3["findings"]})

    taut_hyp = """
theorem circular_gap (gap : Int) (h : 0 < gap) : 0 < gap := h
"""
    res4 = lint_lean4_source(taut_hyp)
    expect_false(res4["passed"], "circular binder premise matching conclusion must fail")
    expect_in("VACUOUS_TAUTOLOGICAL_HYPOTHESIS", {f["rule"] for f in res4["findings"]})


def test_pinned_def_mutation_challenge_scrub_and_host_limit_pure(tmp_path: Path) -> None:
    prompt_lean = """
def targetClamp (x : Nat) : Nat :=
  if x > 10 then 10 else x
"""
    forged_cand = """
def targetClamp (_x : Nat) : Nat := 10

theorem targetClamp_le_ten (x : Nat) : targetClamp x ≤ 10 := by
  omega
"""
    honest_cand = """
def targetClamp (x : Nat) : Nat :=
  if x > 10 then 10 else x

theorem targetClamp_le_ten (x : Nat) : targetClamp x ≤ 10 := by
  unfold targetClamp
  split <;> omega
"""
    expect_in("TARGET_DEF_BODY_MUTATED", {f["rule"] for f in verify_pinned_lean_defs(prompt_lean, forged_cand)})
    expect_eq(verify_pinned_lean_defs(prompt_lean, honest_cand), [])

    expect_true(classify_host_resource_failure(137, "") is not None)
    expect_true(classify_host_resource_failure(1, "error: excessive memory consumption") is not None)
    expect_true(classify_host_resource_failure(1, "type mismatch at application") is None)

    fake_proj = tmp_path / "proj"
    olean_dir = fake_proj / ".lake" / "build" / "lib" / "lean" / "Mcproof"
    olean_dir.mkdir(parents=True)
    stale_olean = olean_dir / "Spec.olean"
    stale_olean.write_bytes(b"stale")
    removed = scrub_challenge_artifacts(fake_proj, "Mcproof.Spec")
    expect_false(stale_olean.exists(), "Spec.olean must be unlinked")
    expect_eq(removed, [".lake/build/lib/lean/Mcproof/Spec.olean"])


@requires_dep("soko")
@requires_lean()
def test_lean_timeout_maps_to_incomplete_host_limit() -> None:
    t_rec = run_lean4_oracle("theorem quick_ok : 1 + 1 = 2 := rfl", timeout_sec=0)
    expect_false(t_rec.passed, "zero-second timeout must fail")
    expect_eq(t_rec.epistemic_status, "INCOMPLETE_HOST_LIMIT", "timeout must map to INCOMPLETE_HOST_LIMIT")
