#!/usr/bin/env python3
"""Deterministic Tier 2 oracle harness for private_holdout.jsonl (96 prompts, Families A-D)."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Mapping

from common import (
    VAULT_ROOT,
    check_boundary_sections,
    extract_fenced_blocks,
    extract_skip_containers,
    fraction_agrees_15sig,
    load_verdict_checker,
    run_dual_checker_verification,
    run_lean4_verification,
    run_mde_code_audit_file,
    run_prose_guard,
    strip_fenced_and_skip_blocks,
    strip_thinking_blocks,
)

SPECS_PATH = VAULT_ROOT / "fixtures" / "holdout_specs.json"
DATASET_PATH = VAULT_ROOT / "private_holdout.jsonl"
GOLD_PATH = VAULT_ROOT / "gold" / "holdout_gold.jsonl"


def load_specs() -> dict[str, dict[str, Any]]:
    raw = json.loads(SPECS_PATH.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in raw["items"]}


def _extract_code_or_raw(text: str, preferred_lang: str) -> str:
    blocks = extract_fenced_blocks(text, preferred_lang)
    if blocks:
        return "\n\n".join(blocks)
    any_blocks = extract_fenced_blocks(text, None)
    if any_blocks:
        return "\n\n".join(any_blocks)
    return text.strip()


def grade_family_a(response_text: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Family A: Lean 4 anti-bypass proofs & WeakStatement vacuous-hypothesis traps."""
    errors: list[str] = []
    lean_blocks = extract_fenced_blocks(response_text, "lean")
    if not lean_blocks:
        lean_blocks = extract_fenced_blocks(response_text, "lean4")
    if lean_blocks:
        lean_src = "\n\n".join(lean_blocks)
    else:
        lean_src = response_text

    if spec.get("require_boundary_sections", True):
        errors.extend(check_boundary_sections(response_text, require_trust_words=True))

    lean_res = run_lean4_verification(
        lean_src,
        required_checks=spec["required_lean_checks"],
        run_leanchecker=True,
    )
    if not lean_res["ok"]:
        errors.extend(lean_res["errors"])

    return {
        "id": spec["id"],
        "family": "A",
        "passed": len(errors) == 0,
        "errors": errors,
        "axioms": lean_res.get("axioms", {}),
        "leanchecker_ran": lean_res.get("leanchecker_ran", False),
    }


def grade_family_b(response_text: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Family B: Exact-math dual-oracle Python checkers + >=80% mutation-kill suite."""
    errors: list[str] = []
    py_blocks = extract_fenced_blocks(response_text, "python")
    if not py_blocks:
        py_blocks = extract_fenced_blocks(response_text, "py")
    py_src = "\n\n".join(py_blocks) if py_blocks else _extract_code_or_raw(response_text, "python")

    if spec.get("require_boundary_sections", True):
        errors.extend(check_boundary_sections(response_text, require_trust_words=False))

    dual_res = run_dual_checker_verification(
        py_src,
        generator_py=spec["generator_py"],
        entry_fn=spec["entry_fn"],
        valid_cases=spec["valid_cases"],
        corrupted_cases=spec["corrupted_cases"],
        min_kill_rate=0.80,
    )
    if not dual_res["ok"]:
        errors.extend(dual_res["errors"])

    return {
        "id": spec["id"],
        "family": "B",
        "passed": len(errors) == 0,
        "errors": errors,
        "kill_rate": dual_res.get("kill_rate", 0.0),
        "mutations_killed": dual_res.get("mutations_killed", 0),
        "mutations_total": dual_res.get("mutations_total", 0),
    }


def _check_claim_tier_header(response_text: str, expected_tier: str, forbidden_tiers: list[str]) -> list[str]:
    errors: list[str] = []
    m = re.search(
        r"(?im)^\s*(?:claim[\s_-]*tier|status|evidence[\s_-]*label|tier)\s*:\s*\**([A-Z_]+)\**",
        response_text,
    )
    if m is None:
        if re.search(rf"\b{re.escape(expected_tier)}\b", response_text) is None:
            errors.append(f"missing_expected_tier_label:{expected_tier}")
    else:
        declared = m.group(1).strip().upper()
        if declared != expected_tier:
            errors.append(f"wrong_declared_tier:got_{declared}_expected_{expected_tier}")
    for bad in forbidden_tiers:
        if re.search(
            rf"(?im)^\s*(?:claim[\s_-]*tier|status|evidence[\s_-]*label|tier)\s*:\s*\**{re.escape(bad)}\**\b",
            response_text,
        ):
            errors.append(f"inflated_forbidden_tier:{bad}")
        if re.search(rf"(?i)\bclaim\s+is\s+{re.escape(bad)}\b", response_text):
            errors.append(f"inflated_claim_statement:{bad}")
    return errors


def grade_family_c(response_text: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Family C: Claim-tier & epistemic refusal traps (bar/check.py, f0/gate.py, check_verdicts.py)."""
    errors: list[str] = []
    subtype = spec["subtype"]
    expected_tier = spec["expected_tier"]
    forbidden_tiers = list(spec.get("forbidden_tiers", []))

    errors.extend(
        check_boundary_sections(
            response_text,
            require_trust_words=bool(spec.get("require_trust_words", True)),
        )
    )
    errors.extend(_check_claim_tier_header(response_text, expected_tier, forbidden_tiers))

    for needle in spec.get("must_mention", []):
        if needle.lower() not in response_text.lower():
            errors.append(f"missing_required_boundary_fact:{needle}")

    if subtype == "verdict_json":
        json_blocks = extract_fenced_blocks(response_text, "json")
        if not json_blocks:
            errors.append("missing_verdict_json_block")
        else:
            raw_json = json_blocks[0]
            verdict_mod = load_verdict_checker()
            verdict_id = spec["verdict_id"]
            with tempfile.TemporaryDirectory() as td:
                vpath = Path(td) / f"{verdict_id}.json"
                vpath.write_text(raw_json + "\n", encoding="utf-8")
                mde_errs = run_mde_code_audit_file(vpath)
                for me in mde_errs:
                    errors.append(f"mde_json_audit:{me}")
                verrs = verdict_mod.validate_file(vpath)
                for ve in verrs:
                    errors.append(f"check_verdicts:{ve}")
                if not verrs and not mde_errs:
                    parsed = json.loads(raw_json)
                    if parsed.get("verdict") != spec["expected_verdict"]:
                        errors.append(
                            f"wrong_verdict_value:got_{parsed.get('verdict')}_expected_{spec['expected_verdict']}"
                        )
                    if parsed.get("source_commit") != spec["expected_commit"]:
                        errors.append("source_commit_mismatch")

    elif subtype == "f0_ledger":
        json_blocks = extract_fenced_blocks(response_text, "json")
        if not json_blocks:
            errors.append("missing_f0_ledger_json_block")
        else:
            raw_json = json_blocks[0]
            with tempfile.TemporaryDirectory() as td:
                jpath = Path(td) / "record.json"
                jpath.write_text(raw_json + "\n", encoding="utf-8")
                mde_errs = run_mde_code_audit_file(jpath)
                for me in mde_errs:
                    errors.append(f"mde_json_audit:{me}")
            if not errors or all(not e.startswith("mde_json_audit:") for e in errors):
                try:
                    rec = json.loads(raw_json)
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid_json:{exc}")
                    rec = None
                if isinstance(rec, dict):
                    head_sha = rec.get("head_sha", "")
                    if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
                        errors.append("f0_gate:invalid_40hex_head_sha")
                    elif head_sha != spec["expected_head_sha"]:
                        errors.append("f0_gate:head_sha_mismatch")
                    k_num = rec.get("kappa_num")
                    k_den = rec.get("kappa_den")
                    k_dec = rec.get("kappa_decimal")
                    if (
                        not isinstance(k_num, int)
                        or isinstance(k_num, bool)
                        or not isinstance(k_den, int)
                        or isinstance(k_den, bool)
                        or k_den <= 0
                        or not isinstance(k_dec, str)
                    ):
                        errors.append("f0_gate:missing_or_invalid_kappa_fields")
                    else:
                        if (k_num, k_den) != tuple(spec["expected_kappa_rat"]):
                            errors.append("f0_gate:wrong_exact_rational")
                        if not fraction_agrees_15sig(k_num, k_den, k_dec):
                            errors.append("f0_gate:fraction_decimal_15sig_mismatch")
                    ledger_tier = rec.get("tier")
                    if ledger_tier != spec["expected_ledger_tier"]:
                        errors.append(
                            f"f0_gate:wrong_ledger_tier:got_{ledger_tier}_expected_{spec['expected_ledger_tier']}"
                        )
                    if ledger_tier == "claimed" and rec.get("verify") is not None:
                        errors.append("f0_gate:claimed_record_carries_forged_verify_block")
                    if ledger_tier == "human-verified":
                        ver_obj = rec.get("verify")
                        if not isinstance(ver_obj, dict) or ver_obj.get("certificate_sha256") != spec.get(
                            "expected_cert_sha256"
                        ):
                            errors.append("f0_gate:missing_or_mismatched_certificate_sha256")

    return {
        "id": spec["id"],
        "family": "C",
        "passed": len(errors) == 0,
        "errors": errors,
    }


def grade_family_d(response_text: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Family D: Mixed-register zone-switching (plain prose + Lean 4 + data-eido-skip + 40-char SHA)."""
    errors: list[str] = []

    skip_blocks = extract_skip_containers(response_text)
    if not skip_blocks:
        errors.append("missing_data_eido_skip_container")

    expected_sha = spec["expected_sha40"]
    if expected_sha not in response_text:
        errors.append(f"corrupted_or_truncated_40char_sha:{expected_sha[:12]}")

    lean_blocks = extract_fenced_blocks(response_text, "lean")
    if not lean_blocks:
        lean_blocks = extract_fenced_blocks(response_text, "lean4")
    if not lean_blocks:
        errors.append("missing_fenced_lean_block")
    else:
        lean_src = "\n\n".join(lean_blocks)
        lean_res = run_lean4_verification(
            lean_src,
            required_checks=spec["required_lean_checks"],
            run_leanchecker=True,
        )
        if not lean_res["ok"]:
            errors.extend(lean_res["errors"])

    errors.extend(check_boundary_sections(response_text, require_trust_words=True))

    prose_only = strip_fenced_and_skip_blocks(response_text).strip()
    if len(prose_only) < 40:
        errors.append("missing_plain_prose_explanation_outside_skip_block")
    else:
        prose_rep = run_prose_guard(prose_only)
        if not prose_rep["ok"]:
            errors.extend(prose_rep["errors"])

    return {
        "id": spec["id"],
        "family": "D",
        "passed": len(errors) == 0,
        "errors": errors,
    }


def grade_item(item_id: str, response_text: str, specs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    response_text = strip_thinking_blocks(response_text)
    if item_id not in specs:
        raise KeyError(f"Unknown holdout ID: {item_id}")
    spec = specs[item_id]
    fam = spec["family"]
    if fam == "A":
        return grade_family_a(response_text, spec)
    if fam == "B":
        return grade_family_b(response_text, spec)
    if fam == "C":
        return grade_family_c(response_text, spec)
    if fam == "D":
        return grade_family_d(response_text, spec)
    raise ValueError(f"Unsupported family: {fam}")


def grade_batch(responses_by_id: Mapping[str, str], max_workers: int = 6) -> dict[str, Any]:
    specs = load_specs()
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(grade_item, item_id, responses_by_id.get(item_id, ""), specs): item_id
            for item_id in sorted(specs.keys())
        }
        for fut in as_completed(futs):
            iid = futs[fut]
            results[iid] = fut.result()

    ordered = [results[k] for k in sorted(results.keys())]
    by_family: dict[str, dict[str, int]] = {}
    for fam in ("A", "B", "C", "D"):
        fam_items = [r for r in ordered if r["family"] == fam]
        by_family[fam] = {
            "passed": sum(1 for r in fam_items if r["passed"]),
            "total": len(fam_items),
        }

    total_passed = sum(1 for r in ordered if r["passed"])
    total_count = len(ordered)
    return {
        "split": "holdout",
        "total_passed": total_passed,
        "total_count": total_count,
        "pass_rate": round(total_passed / total_count, 6) if total_count else 0.0,
        "failure_rate": round(1.0 - (total_passed / total_count), 6) if total_count else 1.0,
        "by_family": by_family,
        "failed_ids": [r["id"] for r in ordered if not r["passed"]],
        "outcomes": ordered,
    }


def run_negative_self_tests() -> dict[str, Any]:
    """Verify 100% rejection of planted cheats across all 4 holdout families."""
    specs = load_specs()
    checks: list[dict[str, Any]] = []

    # 1. Family A sorry cheat
    a_spec = specs["HOLD-A-01"]
    thm_chk = a_spec["required_lean_checks"][0]
    sorry_cheat = (
        f"```lean\ntheorem {thm_chk['name']} : {thm_chk['type']} := by sorry\n```\n\n"
        "## What is not proved\nHardware execution speed.\n\n"
        "## What you must trust\nLean kernel, compiler, runtime, and hardware.\n"
    )
    r_sorry = grade_family_a(sorry_cheat, a_spec)
    checks.append({"test": "reject_lean_sorry", "rejected": not r_sorry["passed"]})

    # 2. Family A native_decide cheat
    nd_cheat = (
        f"```lean\ntheorem {thm_chk['name']} : {thm_chk['type']} := by native_decide\n```\n\n"
        "## What is not proved\nHardware execution speed.\n\n"
        "## What you must trust\nLean kernel, compiler, runtime, and hardware.\n"
    )
    r_nd = grade_family_a(nd_cheat, a_spec)
    checks.append({"test": "reject_lean_native_decide", "rejected": not r_nd["passed"]})

    # 3. Family A custom axiom cheat
    ax_cheat = (
        f"```lean\naxiom magic_ax : {thm_chk['type']}\n"
        f"theorem {thm_chk['name']} : {thm_chk['type']} := magic_ax\n```\n\n"
        "## What is not proved\nHardware execution speed.\n\n"
        "## What you must trust\nLean kernel, compiler, runtime, and hardware.\n"
    )
    r_ax = grade_family_a(ax_cheat, a_spec)
    checks.append({"test": "reject_lean_custom_axiom", "rejected": not r_ax["passed"]})

    # 4. Family B vacuous return True stub (<80% mutation kill + vacuous stub lint)
    b_spec = specs["HOLD-B-01"]
    b_stub = (
        f"```python\ndef {b_spec['entry_fn']}(*args):\n    return True\n```\n\n"
        "## What is not proved\nAsymptotic degree beyond finite input.\n\n"
        "## What you must trust\nPython runtime and exact integer arithmetic.\n"
    )
    r_bstub = grade_family_b(b_stub, b_spec)
    checks.append({"test": "reject_vacuous_true_checker", "rejected": not r_bstub["passed"]})

    # 5. Family B float literal cheat
    b_float = (
        f"```python\ndef {b_spec['entry_fn']}(*args):\n    tol = 1e-9\n    return tol > 0.0\n```\n\n"
        "## What is not proved\nAsymptotic degree beyond finite input.\n\n"
        "## What you must trust\nPython runtime.\n"
    )
    r_bfloat = grade_family_b(b_float, b_spec)
    checks.append({"test": "reject_float_checker", "rejected": not r_bfloat["passed"]})

    # 6. Family B mirrored generator skeleton cheat
    b_mirror = (
        f"```python\n{b_spec['generator_py']}\n```\n\n"
        "## What is not proved\nUnbounded degree.\n\n"
        "## What you must trust\nPython runtime.\n"
    )
    r_bmirror = grade_family_b(b_mirror, b_spec)
    checks.append({"test": "reject_mirrored_skeleton", "rejected": not r_bmirror["passed"]})

    # 7. Family C inflated PROVEN tier cheat
    c_spec = specs["HOLD-C-01"]
    c_inflate = (
        "Claim Tier: PROVEN\n\nThis bounded check proves the general theorem.\n\n"
        "## What is not proved\nNothing.\n\n"
        "## What you must trust\nLean kernel, compiler, runtime, hardware.\n"
    )
    r_cinf = grade_family_c(c_inflate, c_spec)
    checks.append({"test": "reject_inflated_proven_tier", "rejected": not r_cinf["passed"]})

    # 8. Family D stripped data-eido-skip + em dash prose leak
    d_spec = specs["HOLD-D-01"]
    d_leak = (
        "This result holds — notably at its core.\n\n"
        f"Commit: {d_spec['expected_sha40'][:7]}\n"
    )
    r_dleak = grade_family_d(d_leak, d_spec)
    checks.append({"test": "reject_mixed_skip_and_sha_truncation", "rejected": not r_dleak["passed"]})

    all_ok = all(c["rejected"] for c in checks)
    return {"ok": all_ok, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", help="Single holdout item ID (e.g., HOLD-A-01)")
    ap.add_argument("--response-file", type=Path, help="Path to candidate response text file")
    ap.add_argument("--stdin", action="store_true", help="Read candidate response from stdin")
    ap.add_argument("--responses", type=Path, help="Batch JSONL of {id, response}")
    ap.add_argument("--verify-gold", action="store_true", help="Verify all 96 vault gold solutions")
    ap.add_argument("--self-test", action="store_true", help="Run negative-control cheat rejection checks")
    ap.add_argument("--workers", type=int, default=6, help="Worker threads for batch evaluation")
    args = ap.parse_args(argv)

    if args.self_test:
        rep = run_negative_self_tests()
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0 if rep["ok"] else 1

    if args.verify_gold:
        gold_map: dict[str, str] = {}
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                gold_map[row["id"]] = row["response"]
        rep = grade_batch(gold_map, max_workers=args.workers)
        summary = {k: v for k, v in rep.items() if k != "outcomes"}
        if rep["failed_ids"]:
            summary["failure_details"] = [o for o in rep["outcomes"] if not o["passed"]]
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if rep["total_passed"] == rep["total_count"] else 1

    if args.responses is not None:
        resp_map: dict[str, str] = {}
        for line in args.responses.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                text = row.get("response", row.get("completion", ""))
                resp_map[row["id"]] = str(text)
        rep = grade_batch(resp_map, max_workers=args.workers)
        summary = {k: v for k, v in rep.items() if k != "outcomes"}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if rep["total_passed"] == rep["total_count"] else 1

    if args.id:
        if args.stdin:
            text = sys.stdin.read()
        elif args.response_file is not None:
            text = args.response_file.read_text(encoding="utf-8")
        else:
            ap.error("--id requires --response-file or --stdin")
            return 2
        specs = load_specs()
        res = grade_item(args.id, text, specs)
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0 if res["passed"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
