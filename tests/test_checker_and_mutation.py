"""Tests for exact int/Fraction dual-oracle checker audit and >= 80% mutation kill floor."""

from __future__ import annotations

from mcproof.mutation import parse_f0_corruption_lines, run_checker_mutation_suite
from mcproof.oracles import grade_family_completion, run_checker_oracle

from helpers import expect_eq, expect_false, expect_in, expect_true, requires_dep, requires_mde

GENERATOR_SRC = """
def solve_bezout(a: int, b: int) -> dict[str, int]:
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t
    if old_r < 0:
        old_r, old_s, old_t = -old_r, -old_s, -old_t
    return {"a": a, "b": b, "g": old_r, "x": old_s, "y": old_t}
"""

SOUND_CHECKER_SRC = """
from fractions import Fraction


def verify(cert: dict[str, int]) -> bool:
    for k in ("a", "b", "g", "x", "y"):
        if k not in cert or type(cert[k]) is not int:
            return False
    a, b, g, x, y = cert["a"], cert["b"], cert["g"], cert["x"], cert["y"]
    if g <= 0:
        return False
    if a * x + b * y != g:
        return False
    if a % g != 0 or b % g != 0:
        return False
    if Fraction(a, g) * g != Fraction(a, 1):
        return False
    return True
"""

VALID_CASES = [
    {"args": [{"a": 30, "b": 18, "g": 6, "x": -1, "y": 2}]},
    {"args": [{"a": 35, "b": 15, "g": 5, "x": 1, "y": -2}]},
]

PLANTED_MUTATIONS = [
    {"name": "wrong_gcd_multiple", "args": [{"a": 30, "b": 18, "g": 12, "x": 1, "y": -1}]},
    {"name": "broken_linear_comb", "args": [{"a": 30, "b": 18, "g": 6, "x": 1, "y": 2}]},
    {"name": "nonpositive_g", "args": [{"a": 30, "b": 18, "g": -6, "x": 1, "y": -2}]},
    {"name": "nondivisor_g", "args": [{"a": 30, "b": 18, "g": 4, "x": 2, "y": -3}]},
    {"name": "missing_field", "args": [{"a": 30, "b": 18, "g": 6, "x": -1}]},
]


def test_mutation_suite_standalone_sound_and_return_true_kill_floor() -> None:
    ok_rep = run_checker_mutation_suite(
        SOUND_CHECKER_SRC,
        valid_cases=VALID_CASES,
        planted_mutations=PLANTED_MUTATIONS,
    )
    expect_true(ok_rep.passed, f"sound checker rejected by mutation suite: {ok_rep.findings}")
    expect_eq(ok_rep.mutations_killed, 5)
    expect_eq(ok_rep.kill_rate_bps, 10000)

    trivial_src = """
def verify(cert: dict[str, int]) -> bool:
    return True
"""
    mut_rep = run_checker_mutation_suite(
        trivial_src,
        valid_cases=VALID_CASES,
        planted_mutations=PLANTED_MUTATIONS,
    )
    expect_false(mut_rep.passed, "trivial return True verifier must fail <80% kill floor")
    expect_eq(mut_rep.mutations_killed, 0)
    expect_eq(mut_rep.kill_rate_bps, 0)
    expect_in("MUTATION_KILL_FLOOR_BREACH", {f["rule"] for f in mut_rep.findings})


def test_mutation_driver_resilient_to_candidate_stdout_without_newline() -> None:
    noisy_checker = SOUND_CHECKER_SRC + '\nprint("NO_NEWLINE_STDOUT_PAYLOAD", end="")\n'
    noisy_call_checker = noisy_checker.replace(
        "return True",
        'print("INLINE_NO_NEWLINE", end=""); return True',
    )
    rep = run_checker_mutation_suite(
        noisy_call_checker,
        valid_cases=VALID_CASES,
        planted_mutations=PLANTED_MUTATIONS,
    )
    expect_true(rep.passed, f"candidate print(..., end='') must not corrupt result.json: {rep.findings}")
    expect_eq(rep.mutations_killed, 5)


def test_f0_unparseable_corruption_output_reports_zero_over_zero_not_fabricated_four() -> None:
    killed, total, failed_corrs, findings = parse_f0_corruption_lines("", 1, "unexpected crash")
    expect_eq(killed, 0)
    expect_eq(total, 0, "must never fabricate denominator 4 on unparseable output")
    expect_eq(failed_corrs, [])
    rules = {f["rule"] for f in findings}
    expect_in("F0_CORRUPTION_OUTPUT_UNPARSEABLE", rules)
    expect_in("F0_CORRUPTION_ESCAPED", rules)


@requires_dep("soko")
@requires_mde()
def test_family_b_without_valid_cases_fails_closed() -> None:
    rec = grade_family_completion("B", f"```python\n{SOUND_CHECKER_SRC}\n```", valid_cases=())
    expect_false(rec.passed, "Family B without valid_cases fixtures must fail closed")
    expect_in("MISSING_VALID_CASES", {f["rule"] for f in rec.findings})


@requires_dep("soko")
@requires_mde()
def test_sound_dual_oracle_exact_checker_passes() -> None:
    rec = run_checker_oracle(
        SOUND_CHECKER_SRC,
        generator_or_spec_source=GENERATOR_SRC,
        valid_cases=VALID_CASES,
        planted_mutations=PLANTED_MUTATIONS,
    )
    expect_true(rec.passed, f"sound checker rejected: {rec.findings}")
    expect_eq(rec.epistemic_status, "VERIFIED")
    mut = rec.checks["mutation_suite"]
    expect_eq(mut["mutations_killed"], 5)
    expect_eq(mut["kill_rate_bps"], 10000)


@requires_dep("soko")
@requires_mde()
def test_trivial_return_true_verifier_fails_mutation_kill_floor() -> None:
    trivial_src = """
def verify(cert: dict[str, int]) -> bool:
    return True
"""
    full_rec = run_checker_oracle(
        trivial_src,
        valid_cases=VALID_CASES,
        planted_mutations=PLANTED_MUTATIONS,
    )
    expect_false(full_rec.passed, "run_checker_oracle must reject trivial return True")
    rules = {f["rule"] for f in full_rec.findings}
    expect_in("VACUOUS_CONSTANT_TRUE_RETURN", rules)
    expect_in("MUTATION_KILL_FLOOR_BREACH", rules)


@requires_dep("soko")
@requires_mde()
def test_bare_assert_checker_stripped_under_python_O_and_caught() -> None:
    bare_assert_src = """
def verify(cert: dict[str, int]) -> bool:
    assert cert["a"] * cert["x"] + cert["b"] * cert["y"] == cert["g"]
    assert cert["g"] > 0
    return True
"""
    rec = run_checker_oracle(
        bare_assert_src,
        valid_cases=VALID_CASES,
        planted_mutations=PLANTED_MUTATIONS[:4],
    )
    expect_false(rec.passed, "bare assert checker must fail mde guard AND -O mutation suite")
    rules = {f["rule"] for f in rec.findings}
    expect_in("bare_assert", rules)
    expect_in("MUTATION_KILL_FLOOR_BREACH", rules)


@requires_dep("soko")
@requires_mde()
def test_rejects_float_literal_true_division_and_mirrored_skeleton() -> None:
    float_src = """
def verify(cert: dict[str, int]) -> bool:
    tol = 1e-9
    ratio = cert["a"] / cert["g"]
    return abs(ratio - float(cert["a"] // cert["g"])) < tol
"""
    rec_float = run_checker_oracle(float_src, valid_cases=VALID_CASES, planted_mutations=PLANTED_MUTATIONS)
    expect_false(rec_float.passed, "float checker must fail")
    f_rules = {f["rule"] for f in rec_float.findings}
    expect_in("FLOAT_LITERAL_IN_EXACT_CHECKER", f_rules)
    expect_in("FLOAT_DIVISION_IN_EXACT_CHECKER", f_rules)
    expect_in("FLOAT_COERCION_CALL", f_rules)

    mirrored_src = GENERATOR_SRC.replace("solve_bezout", "verify").replace("old_r", "u_r").replace("old_s", "u_s")
    rec_mirror = run_checker_oracle(mirrored_src, generator_or_spec_source=GENERATOR_SRC)
    expect_false(rec_mirror.passed, "identical AST skeleton up to variable rename must fail")
    expect_in("IDENTICAL_ALPHA_SKELETON", {f["rule"] for f in rec_mirror.findings})
    expect_in("MISSING_VALID_CASES", {f["rule"] for f in rec_mirror.findings})
