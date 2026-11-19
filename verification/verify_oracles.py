#!/usr/bin/env python3
"""Independent verification harness for Proven-Commons/mcproof deterministic oracles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

_VERIF_DIR = Path(__file__).resolve().parent
REPO_ROOT = _VERIF_DIR.parent
_SC_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (REPO_ROOT.parents[1] / "siliconcordat"))
DEPS_ROOT = Path(os.environ.get("MCPROOF_DEPS_DIR") or (REPO_ROOT.parent / "deps"))
MDE_BIN = Path(os.environ.get("MDE_BIN") or (_SC_ROOT / "mde" / "target" / "debug" / "mde"))
CHECK_PROSE = Path.home() / ".hermes" / "team-skills" / "scripts" / "check-prose.py"
OUT_JSON = _VERIF_DIR / "oracles_verification_receipt.json"

sys.path.insert(0, str(REPO_ROOT / "src"))
from mcproof.lean_harness import verify_lean4_project_comparator, verify_lean4_source  # noqa: E402
from mcproof.lineage import verify_lineage_manifest  # noqa: E402
from mcproof.mutation import run_checker_mutation_suite, run_f0_gate_and_corruptions  # noqa: E402
from mcproof.oracles import (  # noqa: E402
    grade_family_completion,
    run_checker_oracle,
    run_claim_hygiene_oracle,
    run_prose_and_mixed_zone_oracle,
)


def main() -> int:
    report: dict = {"checks": {}, "defects": []}

    # 1. Inspect spec/plane1_formal_spec.md for any binary/NUL bytes and SHA-256 lineage
    spec_path = REPO_ROOT / "spec" / "plane1_formal_spec.md"
    raw_spec = spec_path.read_bytes()
    nul_positions = [i for i, b in enumerate(raw_spec) if b == 0]
    ctrl_bytes = sorted({b for b in raw_spec if b < 32 and b not in (9, 10, 13)})
    spec_sha = hashlib.sha256(raw_spec).hexdigest()
    spec_text = raw_spec.decode("utf-8")

    lineage_rep = verify_lineage_manifest(REPO_ROOT)
    report["checks"]["plane1_spec"] = {
        "bytes": len(raw_spec),
        "lines": len(spec_text.splitlines()),
        "sha256": spec_sha,
        "nul_byte_count": len(nul_positions),
        "control_bytes": ctrl_bytes,
        "lineage_passed": lineage_rep.passed,
        "lineage_details": lineage_rep.to_dict(),
    }
    if nul_positions or ctrl_bytes:
        report["defects"].append(f"plane1_formal_spec.md contains control/NUL bytes: nul={len(nul_positions)}, ctrl={ctrl_bytes}")
    if not lineage_rep.passed:
        report["defects"].append(f"lineage verification failed: {lineage_rep.findings}")

    # Test 1-byte tamper on isolated copy of repo Plane 1 files
    with tempfile.TemporaryDirectory(prefix="verif_lineage_") as td:
        tmp_repo = Path(td) / "repo"
        for sub in ("spec", "schemas", "lean"):
            shutil.copytree(
                REPO_ROOT / sub,
                tmp_repo / sub,
                ignore=shutil.ignore_patterns(".lake", "__pycache__"),
            )
        tamper_target = tmp_repo / "spec" / "plane1_formal_spec.md"
        orig_bytes = tamper_target.read_bytes()
        tamper_target.write_bytes(orig_bytes[:-1] + (b"X" if orig_bytes[-1:] != b"X" else b"Y"))
        tampered_lineage = verify_lineage_manifest(tmp_repo)
        report["checks"]["lineage_1byte_tamper_rejected"] = (not tampered_lineage.passed) and tampered_lineage.stale_lineage
        if tampered_lineage.passed or not tampered_lineage.stale_lineage:
            report["defects"].append("1-byte Plane 1 mutation was NOT flagged stale_lineage")

    # 2. Verify all 10 upstream dependency SHAs
    deps_manifest = json.loads((DEPS_ROOT / "DEPS_MANIFEST.json").read_text(encoding="utf-8"))
    deps_verified = {}
    for repo_name, info in sorted(deps_manifest["repos"].items()):
        d = DEPS_ROOT / info["dir"]
        head = subprocess.check_output(["git", "-C", str(d), "rev-parse", "HEAD"], text=True).strip()
        ok = (head == info["commit"])
        deps_verified[repo_name] = {"expected": info["commit"], "actual": head, "match": ok}
        if not ok:
            report["defects"].append(f"dep SHA mismatch for {repo_name}: {head} != {info['commit']}")
    report["checks"]["deps_shas"] = deps_verified

    # 3. Run pytest under python3 -O -B -W error
    venv_py = REPO_ROOT / ".venv" / "bin" / "python"
    pytest_proc = subprocess.run(
        [str(venv_py), "-O", "-B", "-W", "error", "-m", "pytest", str(REPO_ROOT / "tests"), "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    report["checks"]["pytest_strict"] = {
        "returncode": pytest_proc.returncode,
        "summary_tail": pytest_proc.stdout.strip().splitlines()[-5:],
    }
    if pytest_proc.returncode != 0:
        report["defects"].append(f"pytest failed under -O -B -W error: {pytest_proc.stdout[-400:]} {pytest_proc.stderr[-400:]}")

    # 4. Independent Lean 4 `lake build` + 6-kernel `lake comparator --paranoid` + adversarial cheats
    clean_proj_res = verify_lean4_project_comparator(REPO_ROOT / "lean")
    report["checks"]["lean_clean_project"] = clean_proj_res.to_dict()
    if not clean_proj_res.passed or len(clean_proj_res.paranoid_kernels_run) != 6:
        report["defects"].append(f"clean Lean project failed 6-kernel comparator: {clean_proj_res.to_dict()}")

    # Adversarial Lean cheats (both single-file harness AND full project comparator copy!)
    lean_cheats = {
        "sorry_tactic": "theorem t_sorry (n : Nat) : n + 1 = n + 2 := by\n  sorry\n",
        "admit_tactic": "theorem t_admit (n : Nat) : n + 1 = n + 2 := by\n  admit\n",
        "custom_axiom": "axiom magic_false : False\ntheorem t_ax (n : Nat) : n = n + 1 := False.elim magic_false\n",
        "inline_semicolon_axiom": "section; axiom sneaky : 0 = 1\ntheorem t_sneaky : 0 = 1 := sneaky\nend\n",
        "native_decide_cheat": "theorem t_native : (2 + 2 == 4) = true := by\n  native_decide\n",
        "implemented_by_cheat": (
            "def badFn (n : Nat) : Nat := n\n"
            "@[implemented_by badFn]\ndef specFn (n : Nat) : Nat := n + 1\n"
            "theorem t_impl : badFn 0 = 0 := rfl\n"
        ),
        "unsafe_cheat": "unsafe def ufn : Nat := 0\ntheorem t_u : 1 = 1 := rfl\n",
        "opaque_cheat": "opaque hiddenVal : Nat\ntheorem t_op : hiddenVal = hiddenVal := rfl\n",
        "vacuous_false_hyp": "theorem t_vac_false (n : Nat) (h : False) : n = n + 1 := False.elim h\n",
        "vacuous_nat_lt_zero": "theorem t_vac_nat (n : Nat) (h : n < 0) : n = n + 1 := by omega\n",
        "vacuous_true_conc": "theorem t_vac_true (n : Nat) : True := trivial\n",
        "vacuous_contradictory_hyps": "theorem t_vac_contra (P : Prop) (h1 : P) (h2 : ¬ P) : 0 = 1 := absurd h1 h2\n",
    }
    cheat_outcomes = {}
    for cname, csrc in lean_cheats.items():
        res = verify_lean4_source(csrc, label=f"{cname}.lean")
        caught = not res.passed
        cheat_outcomes[cname] = {
            "caught": caught,
            "rules": [f["rule"] for f in res.findings],
            "nonstandard_axioms": list(res.nonstandard_axioms),
            "sorry_declarations": list(res.sorry_declarations),
        }
        if not caught:
            report["defects"].append(f"Lean cheat {cname} ESCAPED verify_lean4_source!")

    # Also test planted project-level cheats against `lake comparator --paranoid` in a temp copy!
    proj_cheat_outcomes = {}
    with tempfile.TemporaryDirectory(prefix="verif_lean_proj_") as td:
        tmp_lean = Path(td) / "lean"
        shutil.copytree(REPO_ROOT / "lean", tmp_lean)
        orig_proofs = (tmp_lean / "Mcproof" / "Proofs.lean").read_text(encoding="utf-8")

        # Plant 1: replace a proof in Proofs.lean with `sorry`
        (tmp_lean / "Mcproof" / "Proofs.lean").write_text(
            orig_proofs.replace("exact of_decide_eq_true h", "sorry", 1),
            encoding="utf-8",
        )
        r_proj_sorry = verify_lean4_project_comparator(tmp_lean)
        proj_cheat_outcomes["project_sorry"] = {
            "caught": not r_proj_sorry.passed,
            "rules": [f["rule"] for f in r_proj_sorry.findings],
        }

        # Plant 2: replace `decide_eq_true` proof with `native_decide` on concrete helper + custom axiom
        (tmp_lean / "Mcproof" / "Proofs.lean").write_text(
            "axiom cheatAx : ∀ (a b x y g : Int), bezoutCheck a b x y g = true → a * x + b * y = g\n"
            + orig_proofs.replace(
                "theorem Mcproof.Spec.bezoutCheck_sound (a b x y g : Int) :\n"
                "    bezoutCheck a b x y g = true → a * x + b * y = g := by\n"
                "  unfold bezoutCheck\n  intro h\n  exact of_decide_eq_true h",
                "theorem Mcproof.Spec.bezoutCheck_sound (a b x y g : Int) :\n"
                "    bezoutCheck a b x y g = true → a * x + b * y = g := cheatAx a b x y g",
            ),
            encoding="utf-8",
        )
        r_proj_ax = verify_lean4_project_comparator(tmp_lean)
        proj_cheat_outcomes["project_custom_axiom"] = {
            "caught": not r_proj_ax.passed,
            "rules": [f["rule"] for f in r_proj_ax.findings],
        }

        for k, v in proj_cheat_outcomes.items():
            if not v["caught"]:
                report["defects"].append(f"Project-level Lean cheat {k} ESCAPED!")

    report["checks"]["lean_adversarial_cheats"] = cheat_outcomes
    report["checks"]["lean_project_cheats"] = proj_cheat_outcomes

    # 5. Test planted-bug mutation checker against trivial `return True`, `assert`-only, float-coercion, and 3/5 (60% < 80%) checkers
    valid_bezout = [
        {"args": [30, 12, 1, -2, 6]},
        {"args": [35, 15, 1, -2, 5]},
    ]
    planted_bezout = [
        {"name": "wrong_linear_comb", "args": [30, 12, 1, -1, 6]},
        {"name": "non_divisor_g", "args": [30, 12, 0, 0, 7]},
        {"name": "negative_gcd", "args": [30, 12, -1, 2, -6]},
        {"name": "unreduced_multiple_gcd", "args": [30, 12, 2, -4, 12]},
        {"name": "zero_both_wrong_g", "args": [0, 0, 5, 5, 1]},
    ]
    checker_candidates = {
        "good_exact_checker": (
            True,
            "import math\n"
            "def verify(a: int, b: int, x: int, y: int, g: int) -> bool:\n"
            "    if g < 0:\n"
            "        return False\n"
            "    if a == 0 and b == 0:\n"
            "        return g == 0\n"
            "    if g == 0 or a % g != 0 or b % g != 0:\n"
            "        return False\n"
            "    return (a * x + b * y == g) and (math.gcd(a, b) == g)\n",
        ),
        "trivial_return_true": (
            False,
            "def verify(*args, **kwargs) -> bool:\n    return True\n",
        ),
        "assert_only_stripped_under_dash_O": (
            False,
            "import math\n"
            "def verify(a: int, b: int, x: int, y: int, g: int) -> bool:\n"
            "    assert g >= 0 and a * x + b * y == g and math.gcd(a, b) == g\n"
            "    return True\n",
        ),
        "weak_60pct_kill_3of5": (
            False,
            "def verify(a: int, b: int, x: int, y: int, g: int) -> bool:\n"
            "    # Only checks linear combination, misses negative_gcd and unreduced_multiple_gcd (kills 3/5 = 60% < 80%)\n"
            "    return a * x + b * y == g\n",
        ),
        "float_true_division_cheat": (
            False,
            "import math\n"
            "def verify(a: int, b: int, x: int, y: int, g: int) -> bool:\n"
            "    if g <= 0:\n"
            "        return a == 0 and b == 0 and g == 0\n"
            "    ratio = (a * x + b * y) / g\n"
            "    return ratio == 1.0 and math.gcd(a, b) == g\n",
        ),
    }
    checker_outcomes = {}
    for name, (expect_pass, src) in checker_candidates.items():
        rec = run_checker_oracle(
            src,
            valid_cases=valid_bezout,
            planted_mutations=planted_bezout,
            strict_exact_math=True,
        )
        ok = (rec.passed == expect_pass)
        checker_outcomes[name] = {
            "expected_pass": expect_pass,
            "actual_pass": rec.passed,
            "matched_expectation": ok,
            "kill_fraction": (rec.checks.get("mutation_suite") or {}).get("kill_fraction"),
            "kill_rate_bps": (rec.checks.get("mutation_suite") or {}).get("kill_rate_bps"),
            "rules": [f["rule"] for f in rec.findings],
        }
        if not ok:
            report["defects"].append(f"Checker candidate {name} expected_pass={expect_pass}, got {rec.passed}")
    report["checks"]["checker_adversarial_matrix"] = checker_outcomes

    # 6. Run f0 gate + corruptions
    f0_rep = run_f0_gate_and_corruptions()
    report["checks"]["f0_gate_corruptions"] = f0_rep.to_dict()
    if not f0_rep.passed:
        report["defects"].append(f"f0 gate corruptions failed: {f0_rep.to_dict()}")

    # 7. Prose + --dupes + outcome-forecast sweep across ALL markdown files in repo
    md_files = sorted(
        p for p in REPO_ROOT.rglob("*.md")
        if not any(part in (".git", ".venv", ".lake", ".pytest_cache") for part in p.parts)
    )
    p1 = subprocess.run([sys.executable, str(CHECK_PROSE), *[str(p) for p in md_files]], capture_output=True, text=True, check=False)
    p2 = subprocess.run([sys.executable, str(CHECK_PROSE), "--dupes", *[str(p) for p in md_files]], capture_output=True, text=True, check=False)
    report["checks"]["prose_gate"] = {
        "files": [str(p.relative_to(REPO_ROOT)) for p in md_files],
        "check_prose_rc": p1.returncode,
        "check_prose_out": p1.stdout.strip(),
        "check_dupes_rc": p2.returncode,
        "check_dupes_out": p2.stdout.strip(),
    }
    if p1.returncode != 0 or p2.returncode != 0:
        report["defects"].append(f"prose gate failed: rc={p1.returncode}/{p2.returncode}: {p1.stdout} {p2.stdout}")

    # 8. Check README first-3-lines rule and siliconcordat/* clean git status
    readme_lines = [ln.strip() for ln in (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines() if ln.strip()]
    sc_dirty = {}
    for r in (".github", "mde", "exo", "warp", "weft", "loom"):
        st = subprocess.check_output(["git", "-C", str(_SC_ROOT / r), "status", "--porcelain"], text=True).strip()
        sc_dirty[r] = st
        if st:
            report["defects"].append(f"siliconcordat/{r} modified in place: {st}")
    report["checks"]["readme_top_lines"] = readme_lines[:3]
    report["checks"]["siliconcordat_clean"] = sc_dirty

    report["overall_passed"] = len(report["defects"]) == 0
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": report["overall_passed"], "defect_count": len(report["defects"]), "defects": report["defects"]}, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
