#!/usr/bin/env python3
"""Deterministic grader for mixed_composition_30.jsonl (Phase 5 Mixed Integrity, Phase 6 T-C2 & 7 Hazards)."""

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
    SILICONCORDAT_ROOT,
    VAULT_ROOT,
    check_boundary_sections,
    extract_fenced_blocks,
    extract_skip_containers,
    load_soko_checker_auditor,
    run_lean4_verification,
    run_mde_code_audit_file,
    run_prose_guard,
    strip_fenced_and_skip_blocks,
    strip_thinking_blocks,
)

DATASET_PATH = VAULT_ROOT / "mixed_composition_30.jsonl"
SPECS_PATH = VAULT_ROOT / "fixtures" / "mixed_specs.json"
GOLD_PATH = VAULT_ROOT / "gold" / "mixed_gold.jsonl"
ZONE_MANIFEST_PATH = SILICONCORDAT_ROOT / "mde" / "schemas" / "zone-manifest.v0.1.json"


def _load_exo_router_modules() -> tuple[Any, Any]:
    exo_src = str(SILICONCORDAT_ROOT / "exo" / "src")
    if exo_src not in sys.path:
        sys.path.insert(0, exo_src)
    import exo.policy as exo_policy
    import exo.router as exo_router

    return exo_router, exo_policy


def load_specs() -> dict[str, dict[str, Any]]:
    raw = json.loads(SPECS_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item for item in raw["items"]}


def verify_exo_routing_contract(spec: Mapping[str, Any]) -> list[str]:
    """Verify the prompt's L5/L4 routing metadata against live siliconcordat/exo ZoneRouter."""
    exo_router, exo_policy = _load_exo_router_modules()
    rcfg = spec["router_check"]
    policy = exo_policy.RepoPolicy.from_dict(rcfg["repo_policy"])
    use_manifest = bool(rcfg.get("use_zone_manifest", False))
    router = (
        exo_router.ZoneRouter.from_zone_manifest_file(ZONE_MANIFEST_PATH)
        if use_manifest
        else exo_router.ZoneRouter()
    )
    req = exo_router.RouteRequest(
        zone=rcfg["zone"],
        active_domains=tuple(rcfg["active_domains"]),
        repo_policy=policy,
        file_path=rcfg.get("file_path"),
        contains_formal_claims=bool(rcfg.get("contains_formal_claims", False)),
        contains_certified_plot=bool(rcfg.get("contains_certified_plot", False)),
        contains_illustrative_toy=bool(rcfg.get("contains_illustrative_toy", False)),
        data_eido_skip_marked=bool(rcfg.get("data_eido_skip_marked", False)),
    )
    expect_contested = rcfg.get("expect_contested_key")
    errors: list[str] = []
    if expect_contested:
        try:
            router.route(req)
            errors.append(f"exo_router_failed_to_raise_ContestedPreferenceError:{expect_contested}")
        except exo_router.ContestedPreferenceError as exc:
            if exc.conflict_key != expect_contested:
                errors.append(f"exo_router_wrong_conflict_key:{exc.conflict_key}!={expect_contested}")
        return errors

    decision = router.route(req)
    scale_map = decision.scale_map()
    for dom, exp_scale in rcfg.get("expected_scales", {}).items():
        got_scale = scale_map.get(dom)
        if got_scale is None or abs(got_scale - float(exp_scale)) > 1e-9:
            errors.append(f"exo_scale_mismatch:{dom}:got_{got_scale}_exp_{exp_scale}")
    for flag_name, exp_val in rcfg.get("expected_constraints", {}).items():
        got_val = getattr(decision.constraints, flag_name)
        if got_val != exp_val:
            errors.append(f"exo_constraint_mismatch:{flag_name}:got_{got_val}_exp_{exp_val}")
    return errors


def _validate_condensed_json_block(raw_json: str) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "condensed.json"
        jpath.write_text(raw_json + "\n", encoding="utf-8")
        mde_errs = run_mde_code_audit_file(jpath)
        for me in mde_errs:
            errors.append(f"mde_json_audit:{me}")
    if errors:
        return errors
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        return ["condensed_not_object"]
    if data.get("version") != 1:
        errors.append("condensed_version_must_be_1")
    blocks = data.get("blocks")
    if not isinstance(blocks, dict) or not blocks:
        errors.append("condensed_blocks_missing_or_empty")
    else:
        for k, variants in blocks.items():
            if not re.fullmatch(r"[0-9a-f]{8}", str(k)):
                errors.append(f"condensed_invalid_fnv1a_key:{k}")
            if not isinstance(variants, list) or len(variants) != 3:
                errors.append(f"condensed_block_must_have_3_levels:{k}")
            else:
                for idx, s in enumerate(variants):
                    if not isinstance(s, str) or not s.strip():
                        errors.append(f"condensed_empty_variant:{k}[{idx}]")
                    elif "<script" in s.lower():
                        errors.append(f"condensed_xss_script_tag:{k}[{idx}]")
    return errors


def grade_mixed_item(item_id: str, response_text: str, specs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    response_text = strip_thinking_blocks(response_text)
    if item_id not in specs:
        raise KeyError(f"Unknown mixed composition ID: {item_id}")
    spec = specs[item_id]
    formal_corruptions: list[str] = []
    prose_or_zone_leaks: list[str] = []

    router_errs = verify_exo_routing_contract(spec)
    prose_or_zone_leaks.extend(router_errs)

    if spec.get("expect_contested_escalation", False):
        lower = response_text.lower()
        if not any(
            tok in lower
            for tok in (
                "contestedpreferenceerror",
                "contested",
                "hard veto 2",
                "precedence_overrides",
                "data-eido-skip",
                "escalate",
            )
        ):
            formal_corruptions.append("missing_fail_closed_contested_escalation")
        for bad in spec.get("must_not_contain", []):
            if bad in response_text:
                prose_or_zone_leaks.append(f"forbidden_contested_output:{bad}")
    else:
        if spec.get("require_data_eido_skip", False):
            if not extract_skip_containers(response_text):
                formal_corruptions.append("missing_data_eido_skip_protection")

        if spec.get("expected_sha40"):
            sha40 = spec["expected_sha40"]
            if sha40 not in response_text:
                formal_corruptions.append(f"truncated_or_missing_sha40:{sha40[:12]}")

        for ax in spec.get("required_formal_identifiers", []):
            if ax not in response_text:
                formal_corruptions.append(f"corrupted_formal_identifier:{ax}")

        if spec.get("require_boundary_sections", False):
            b_errs = check_boundary_sections(
                response_text,
                require_trust_words=bool(spec.get("require_trust_words", True)),
            )
            formal_corruptions.extend(b_errs)

        if spec.get("required_lean_checks"):
            lean_blocks = extract_fenced_blocks(response_text, "lean")
            if not lean_blocks:
                lean_blocks = extract_fenced_blocks(response_text, "lean4")
            if not lean_blocks:
                formal_corruptions.append("missing_lean_block")
            else:
                lres = run_lean4_verification(
                    "\n\n".join(lean_blocks),
                    required_checks=spec["required_lean_checks"],
                    run_leanchecker=True,
                )
                if not lres["ok"]:
                    formal_corruptions.extend(lres["errors"])

        if spec.get("require_exact_python_checker", False):
            py_blocks = extract_fenced_blocks(response_text, "python")
            if not py_blocks:
                formal_corruptions.append("missing_exact_python_verifier_block")
            else:
                aud = load_soko_checker_auditor()
                py_src = "\n\n".join(py_blocks)
                rep = aud.audit_checker_source(py_src, label="research_verifier.py", strict_exact_math=True)
                if not rep.get("clean", False):
                    for f in rep.get("findings", []):
                        formal_corruptions.append(f"exact_verifier_corrupted:{f.get('rule')}")
                with tempfile.TemporaryDirectory() as td:
                    pfile = Path(td) / "verifier.py"
                    pfile.write_text(py_src + "\n", encoding="utf-8")
                    for me in run_mde_code_audit_file(pfile):
                        formal_corruptions.append(f"verifier_code_audit:{me}")

        if spec.get("require_condensed_json", False):
            jblocks = extract_fenced_blocks(response_text, "json")
            if not jblocks:
                prose_or_zone_leaks.append("missing_condensed_json_block")
            else:
                prose_or_zone_leaks.extend(_validate_condensed_json_block(jblocks[0]))

        for req_tok in spec.get("must_contain", []):
            if req_tok not in response_text:
                prose_or_zone_leaks.append(f"missing_required_zone_token:{req_tok}")

        for bad_tok in spec.get("must_not_contain", []):
            if bad_tok in response_text:
                prose_or_zone_leaks.append(f"forbidden_zone_leak_token:{bad_tok}")

    if spec.get("check_surrounding_prose", True):
        prose_only = strip_fenced_and_skip_blocks(response_text)
        prose_only = re.sub(r"<[^>]+>", "", prose_only).strip()
        if len(prose_only) < 25:
            prose_or_zone_leaks.append("missing_surrounding_prose")
        else:
            prep = run_prose_guard(prose_only)
            if not prep["ok"]:
                prose_or_zone_leaks.extend(prep["errors"])

    passed = len(formal_corruptions) == 0 and len(prose_or_zone_leaks) == 0
    return {
        "id": item_id,
        "hazard_id": spec["hazard_id"],
        "zone": spec["zone"],
        "passed": passed,
        "formal_block_corruptions": formal_corruptions,
        "prose_or_zone_leaks": prose_or_zone_leaks,
    }


def grade_batch(responses_by_id: Mapping[str, str], max_workers: int = 6) -> dict[str, Any]:
    specs = load_specs()
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(grade_mixed_item, iid, responses_by_id.get(iid, ""), specs): iid
            for iid in sorted(specs.keys())
        }
        for fut in as_completed(futs):
            iid = futs[fut]
            results[iid] = fut.result()

    ordered = [results[k] for k in sorted(results.keys())]
    corrupted_formal_count = sum(1 for r in ordered if len(r["formal_block_corruptions"]) > 0)
    prose_leak_count = sum(1 for r in ordered if len(r["prose_or_zone_leaks"]) > 0)
    by_hazard: dict[str, dict[str, int]] = {}
    for h in range(1, 8):
        key = f"H{h}"
        sub = [r for r in ordered if r["hazard_id"] == key]
        by_hazard[key] = {
            "passed": sum(1 for r in sub if r["passed"]),
            "total": len(sub),
        }

    total_passed = sum(1 for r in ordered if r["passed"])
    total_count = len(ordered)
    return {
        "split": "mixed_composition_30",
        "total_passed": total_passed,
        "total_count": total_count,
        "corrupted_formal_blocks": corrupted_formal_count,
        "prose_or_zone_leaks": prose_leak_count,
        "phase5_mixed_integrity_gate": corrupted_formal_count == 0,
        "phase6_tc2_isolation_gate": corrupted_formal_count == 0 and prose_leak_count == 0,
        "by_hazard": by_hazard,
        "failed_ids": [r["id"] for r in ordered if not r["passed"]],
        "outcomes": ordered,
    }


def _load_jsonl_responses(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = str(row.get("response", row.get("completion", "")))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", help="Single mixed prompt ID")
    ap.add_argument("--response-file", type=Path, help="Single response file")
    ap.add_argument("--responses", type=Path, help="Batch JSONL of {id, response}")
    ap.add_argument("--verify-gold", action="store_true", help="Verify all 30 gold mixed completions")
    ap.add_argument("--workers", type=int, default=6, help="Worker threads")
    args = ap.parse_args(argv)

    if args.verify_gold:
        rep = grade_batch(_load_jsonl_responses(GOLD_PATH), max_workers=args.workers)
        summary = {k: v for k, v in rep.items() if k != "outcomes"}
        if rep["failed_ids"]:
            summary["failure_details"] = [o for o in rep["outcomes"] if not o["passed"]]
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if rep["total_passed"] == rep["total_count"] else 1

    if args.responses is not None:
        rep = grade_batch(_load_jsonl_responses(args.responses), max_workers=args.workers)
        summary = {k: v for k, v in rep.items() if k != "outcomes"}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if rep["phase6_tc2_isolation_gate"] else 1

    if args.id and args.response_file is not None:
        specs = load_specs()
        res = grade_mixed_item(args.id, args.response_file.read_text(encoding="utf-8"), specs)
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0 if res["passed"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
