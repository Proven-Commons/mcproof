"""Tests for Lean 4.35.0 theorem harness, 6-kernel comparator, and 100% cheat rejection."""

from __future__ import annotations

import shutil
from pathlib import Path

from mcproof.lean_harness import (
    lint_lean4_source,
    verify_lean4_project_comparator,
    verify_lean4_source,
)
from mcproof.paths import repo_root

from helpers import expect_eq, expect_false, expect_in, expect_true


def test_reference_lean_project_passes_six_kernel_comparator() -> None:
    res = verify_lean4_project_comparator(repo_root() / "lean")
    expect_true(res.passed, f"reference lean project failed: {res.findings}")
    expect_eq(len(res.paranoid_kernels_run), 6, "all 6 bundled Lean 4.35.0 kernels must accept")
    expect_eq(len(res.theorems_checked), 8, "all 8 theorems in comparator.json must be checked")
    expect_eq(len(res.sorry_declarations), 0, "zero sorry declarations allowed in Proofs")
    expect_eq(len(res.nonstandard_axioms), 0, "zero non-standard axioms allowed")


def test_clean_standalone_lean_theorem_passes() -> None:
    src = """
theorem add_comm_witness (a b : Nat) : a + b = b + a := by
  omega
"""
    res = verify_lean4_source(src)
    expect_true(res.passed, f"valid Lean theorem rejected: {res.findings}")
    expect_in("add_comm_witness", res.theorems_checked)
    expect_in("leanchecker", res.paranoid_kernels_run)


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


def test_rejects_planted_cheat_in_project_comparator(tmp_path: Path) -> None:
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
    res = verify_lean4_project_comparator(work)
    expect_false(res.passed, "project comparator must reject planted axiom")
    rules = {f["rule"] for f in res.findings}
    expect_in("EXTRA_AXIOM_DECL", rules)


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
