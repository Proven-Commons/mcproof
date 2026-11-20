"""Command-line interface for `mcproof` deterministic Tier 2 verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from .lineage import build_lineage_manifest, verify_lineage_manifest
from .oracles import (
    OracleReceipt,
    grade_family_completion,
    run_all_reference_selftests,
    run_checker_oracle,
    run_claim_hygiene_oracle,
    run_f0_gate_oracle,
    run_lean4_oracle,
    run_mde_code_audit,
    run_mde_integrity,
    run_mission_bar_oracle,
    run_prose_and_mixed_zone_oracle,
    run_verdicts_oracle,
)
from .paths import repo_root


def _read_text_or_stdin(path_arg: str) -> str:
    if path_arg == "-":
        return sys.stdin.read()
    return Path(path_arg).read_text(encoding="utf-8")


def _emit(receipt: OracleReceipt, as_json: bool) -> int:
    if as_json:
        print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True))
    else:
        verdict = "PASS" if receipt.passed else "FAIL"
        print(f"[{verdict}] oracle={receipt.oracle} status={receipt.epistemic_status} sha256={receipt.receipt_sha256[:16]}")
        for f in receipt.findings:
            loc = f":{f['line']}" if "line" in f else ""
            print(f"  - [{f['rule']}{loc}] {f['message']}")
    return 0 if receipt.passed else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcproof",
        description="Deterministic Tier 2 formal verification oracle harness for the Siliconcordat Formal Verification MDE.",
    )
    p.add_argument("--json", action="store_true", help="Emit deterministic JSON receipt")
    sub = p.add_subparsers(dest="subcommand", required=True)

    # lean
    s_lean = sub.add_parser("lean", help="Verify a Lean 4 file, snippet ('-' for stdin), or Lake project directory")
    s_lean.add_argument("target", nargs="?", default=None, help="Path to .lean file, Lake project dir, or '-' for stdin (defaults to repo lean/)")
    s_lean.add_argument("--project", action="store_true", help="Run full 6-kernel `lake comparator --paranoid` on project dir")
    s_lean.add_argument("--allow-mathlib", action="store_true", help="Disable strict_init_only lint")
    s_lean.add_argument("--no-vacuous-check", action="store_true", help="Skip WeakStatement vacuous-hypothesis lint")
    s_lean.add_argument("--allow-unsandboxed", action="store_true", help="Explicitly permit comparator `--inadvisably-no-sandbox` when Linux bwrap is unavailable")

    # checker
    s_chk = sub.add_parser("checker", help="Audit an exact-math Python checker (AST + mde guard + python3 -O -B -W error + >=80%% mutation kill)")
    s_chk.add_argument("checker_file", help="Path to Python checker file or '-' for stdin")
    s_chk.add_argument("--generator-file", default=None, help="Optional generator/spec Python file to enforce distinct AST skeleton")
    s_chk.add_argument("--entry-fn", default="verify", help="Entry-point function name (default: verify)")
    s_chk.add_argument("--fixture-json", default=None, help="Optional JSON file with {'valid_cases': [...], 'planted_mutations': [...]}")
    s_chk.add_argument("--cargo-run", action="store_true", help="Invoke mde via `cargo run --manifest-path ...` explicitly")

    # claims
    s_clm = sub.add_parser("claims", help="Audit markdown formal claim hygiene (`What is not proved`, `What you must trust`, honest tiers)")
    s_clm.add_argument("markdown_file", help="Path to markdown document or '-' for stdin")
    s_clm.add_argument("--expected-tier", default=None, help="Expected tier (PROVEN, VERIFIED, KNOWN, CONJECTURE, REFUSED)")
    s_clm.add_argument("--has-kernel-proof", action="store_true", help="Mark that a kernel-verified proof accompanies the claim")

    # bar
    s_bar = sub.add_parser("bar", help="Run Proven-Commons `mission/bar/check.py` against a Lean library directory")
    s_bar.add_argument("project_dir", nargs="?", default=None, help="Project directory (defaults to repo lean/)")
    s_bar.add_argument("--run-tests", action="store_true", help="Re-run differential tests during bar check")

    # f0-gate
    s_f0 = sub.add_parser("f0-gate", help="Run Foundation-0 `scripts/gate.py` + `run_gate_corruptions.py` under `python3 -O -B -W error`")
    s_f0.add_argument("--root", default=None, help="Path to f0 checkout (defaults to deps/f0)")

    # verdicts
    s_vrd = sub.add_parser("verdicts", help="Run Foundation-0 `formal-claims-audit/scripts/check_verdicts.py`")
    s_vrd.add_argument("path", nargs="?", default=None, help="Verdict JSON file or directory")

    # mde-guard
    s_mde = sub.add_parser("mde-guard", help="Run `siliconcordat/mde guard --code-audit` on `.py` and `.json` files/dirs")
    s_mde.add_argument("paths", nargs="+", help="Files or directories to audit")
    s_mde.add_argument("--cargo-run", action="store_true", help="Force `cargo run --manifest-path` invocation")

    # prose
    s_prs = sub.add_parser("prose", help="Run vendored `prose_gate.py` (or `--prose-script`), `--dupes`, and mixed-register zone checks")
    s_prs.add_argument("markdown_file", help="Path to markdown document or '-' for stdin")
    s_prs.add_argument("--mixed-formal", action="store_true", help="Require formal sections, `data-eido-skip`, and 40-char verdict SHAs")
    s_prs.add_argument("--prose-script", default=None, help="Optional override path to check-prose.py script")

    # integrity
    s_int = sub.add_parser("integrity", help="Write or verify `SHA256SUMS` via `siliconcordat/mde integrity`")
    s_int.add_argument("root_dir", help="Target directory")
    s_int.add_argument("--write", action="store_true", help="Write SHA256SUMS instead of verifying")
    s_int.add_argument("--manifest", default="SHA256SUMS", help="Manifest filename (default: SHA256SUMS)")
    s_int.add_argument("--allow-unlisted", action="store_true", help="Allow unlisted files when verifying")

    # lineage
    s_lin = sub.add_parser("lineage", help="Write or verify `spec/lineage.json` Plane 1 SHA-256 lineage binding")
    s_lin.add_argument("--write", action="store_true", help="Recompute and write spec/lineage.json")
    s_lin.add_argument("--verify", action="store_true", help="Verify spec/lineage.json against live Plane 1 files (default)")
    s_lin.add_argument("--require-deps", action="store_true", help="Fail closed if `deps/DEPS_MANIFEST.json` or `deps/` git checkouts are absent")

    # grade
    s_grd = sub.add_parser("grade", help="Grade a Family A, B, C, or D completion file or stdin")
    s_grd.add_argument("--family", required=True, choices=["A", "B", "C", "D", "a", "b", "c", "d"])
    s_grd.add_argument("--input", default="-", help="Completion file path or '-' for stdin")
    s_grd.add_argument("--expected-tier", default=None, help="Expected claim tier")
    s_grd.add_argument("--fixture-json", default=None, help="Optional JSON fixture with generator_source / valid_cases / planted_mutations")

    # selftest
    s_self = sub.add_parser("selftest", help="Run full Tier 2 oracle and Plane 1 lineage self-test suite")
    s_self.add_argument("--allow-unsandboxed", action="store_true", help="Explicitly permit comparator `--inadvisably-no-sandbox` when Linux bwrap is unavailable")

    return p


def _dispatch(args: argparse.Namespace) -> int:
    cmd = args.subcommand

    if cmd == "lean":
        if args.target is None:
            rec = run_lean4_oracle(
                repo_root() / "lean",
                is_project_dir=True,
                strict_init_only=not args.allow_mathlib,
                allow_unsandboxed=args.allow_unsandboxed,
            )
        elif args.target == "-":
            src = sys.stdin.read()
            rec = run_lean4_oracle(
                src,
                is_project_dir=False,
                strict_init_only=not args.allow_mathlib,
                check_vacuous=not args.no_vacuous_check,
                allow_unsandboxed=args.allow_unsandboxed,
            )
        else:
            t_path = Path(args.target)
            rec = run_lean4_oracle(
                t_path,
                is_project_dir=args.project or t_path.is_dir(),
                strict_init_only=not args.allow_mathlib,
                check_vacuous=not args.no_vacuous_check,
                allow_unsandboxed=args.allow_unsandboxed,
            )
        return _emit(rec, args.json)

    if cmd == "checker":
        src = _read_text_or_stdin(args.checker_file)
        gen = Path(args.generator_file).read_text(encoding="utf-8") if args.generator_file else None
        valid_cases: list[dict[str, Any]] = []
        planted: list[dict[str, Any]] | None = None
        if args.fixture_json:
            fx = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
            valid_cases = list(fx.get("valid_cases", []))
            if "planted_mutations" in fx:
                planted = list(fx["planted_mutations"])
        rec = run_checker_oracle(
            src,
            generator_or_spec_source=gen,
            entry_fn=args.entry_fn,
            valid_cases=valid_cases,
            planted_mutations=planted,
            force_cargo_run=args.cargo_run,
        )
        return _emit(rec, args.json)

    if cmd == "claims":
        md = _read_text_or_stdin(args.markdown_file)
        rec = run_claim_hygiene_oracle(
            md,
            expected_tier=args.expected_tier,
            has_kernel_proof=args.has_kernel_proof,
        )
        return _emit(rec, args.json)

    if cmd == "bar":
        proj = Path(args.project_dir) if args.project_dir else (repo_root() / "lean")
        rec = run_mission_bar_oracle(proj, no_lean=True, offline=True, run_tests=args.run_tests)
        return _emit(rec, args.json)

    if cmd == "f0-gate":
        f0_dir = Path(args.root) if args.root else None
        rec = run_f0_gate_oracle(f0_dir)
        return _emit(rec, args.json)

    if cmd == "verdicts":
        vp = Path(args.path) if args.path else None
        rec = run_verdicts_oracle(vp)
        return _emit(rec, args.json)

    if cmd == "mde-guard":
        rec = run_mde_code_audit(args.paths, force_cargo_run=args.cargo_run)
        return _emit(rec, args.json)

    if cmd == "prose":
        md = _read_text_or_stdin(args.markdown_file)
        label = "stdin.md" if args.markdown_file == "-" else args.markdown_file
        rec = run_prose_and_mixed_zone_oracle(
            md,
            label=label,
            require_formal_sections=args.mixed_formal,
            require_data_eido_skip=args.mixed_formal,
            verify_embedded_lean=True,
            verify_verdict_shas=args.mixed_formal,
            prose_script_override=args.prose_script,
        )
        return _emit(rec, args.json)

    if cmd == "integrity":
        rec = run_mde_integrity(
            Path(args.root_dir),
            write=args.write,
            manifest_name=args.manifest,
            allow_unlisted=args.allow_unlisted,
        )
        return _emit(rec, args.json)

    if cmd == "lineage":
        r_root = repo_root()
        if args.write:
            manifest = build_lineage_manifest(r_root)
            out_path = r_root / "spec" / "lineage.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rep = verify_lineage_manifest(r_root, require_deps=args.require_deps)
        rec = OracleReceipt.create(
            oracle="lineage",
            passed=rep.passed,
            epistemic_status="VERIFIED" if rep.passed else "REJECTED",
            checks=rep.to_dict(),
            findings=[{"rule": "STALE_LINEAGE", "message": m} for m in rep.findings],
        )
        return _emit(rec, args.json)

    if cmd == "grade":
        comp = _read_text_or_stdin(args.input)
        gen_src: str | None = None
        valid_cases_g: list[dict[str, Any]] = []
        planted_g: list[dict[str, Any]] | None = None
        if args.fixture_json:
            fx = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
            gen_src = fx.get("generator_source")
            valid_cases_g = list(fx.get("valid_cases", []))
            if "planted_mutations" in fx:
                planted_g = list(fx["planted_mutations"])
        rec = grade_family_completion(
            args.family,
            comp,
            expected_tier=args.expected_tier,
            generator_source=gen_src,
            valid_cases=valid_cases_g,
            planted_mutations=planted_g,
        )
        return _emit(rec, args.json)

    if cmd == "selftest":
        rec = run_all_reference_selftests(allow_unsandboxed=args.allow_unsandboxed)
        return _emit(rec, args.json)

    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = str(args.subcommand or "mcproof")
    try:
        return _dispatch(args)
    except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError, OSError, ValueError, KeyError) as exc:
        rec = OracleReceipt.create(
            oracle=cmd,
            passed=False,
            epistemic_status="REJECTED",
            checks={"error": type(exc).__name__},
            findings=[{"rule": "ORACLE_EXEC_ERROR", "message": str(exc)[:240]}],
        )
        return _emit(rec, bool(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
