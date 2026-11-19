#!/usr/bin/env python3
"""Deterministic per-item Tier 2 verifier for `datasets/{compile,validation}.jsonl`.

Delegates primary Family A/B/C/D checks to `../repo/bin/mcproof` and runs deep
project-level Bar/Verdict/F0 replay for Family C items when `--id` is supplied.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DATASETS_ROOT = Path(__file__).resolve().parents[1]
LAB_ROOT = DATASETS_ROOT.parent
MCPROOF_BIN = LAB_ROOT / "repo" / "bin" / "mcproof"
DEPS_ROOT = LAB_ROOT / "deps"


def _load_item(item_id: str) -> dict[str, Any]:
    for name in ("compile.jsonl", "validation.jsonl"):
        p = DATASETS_ROOT / name
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("id") == item_id:
                return row
    raise KeyError(f"unknown dataset item id: {item_id}")


def _extract_json_block(text: str) -> str | None:
    marker = "```json"
    idx = text.find(marker)
    if idx < 0:
        return None
    rest = text[idx + len(marker):]
    end = rest.find("```")
    if end < 0:
        return None
    return rest[:end].strip()


def _run_family_c_deep_oracle(harness: dict[str, Any], completion_text: str) -> tuple[bool, list[str]]:
    otype = harness.get("oracle_type")
    meta = harness.get("spec_meta", {})
    errs: list[str] = []

    if otype == "bar_check":
        bar_tpl = DEPS_ROOT / "mission" / "bar" / "template"
        bar_chk = DEPS_ROOT / "mission" / "bar" / "check.py"
        pkg = meta["pkg"]
        thms = meta["theorem_names"]
        readme_body = re.sub(r"(?im)^Claim-Tier:[^\n]*\n+", "", completion_text, count=1)
        says_verified = bool(
            re.search(r"(?im)^status\s*:\s*verified\b", readme_body)
            and not re.search(r"(?im)^status\s*:.*not verified", readme_body)
        )
        bar_status = "verified" if says_verified else meta["bar_status"]
        with tempfile.TemporaryDirectory(prefix="mcproof_ds_bar_") as td:
            root = Path(td)
            shutil.copytree(bar_tpl, root, dirs_exist_ok=True)
            (root / "Clamp.lean").unlink(missing_ok=True)
            shutil.rmtree(root / "Clamp", ignore_errors=True)
            (root / f"{pkg}.lean").write_text(f"namespace {pkg}\ndef op (x : Nat) : Nat := x\nend {pkg}\n", encoding="utf-8")
            (root / pkg).mkdir(exist_ok=True)
            spec_lines = [f"import {pkg}", f"namespace {pkg}.Spec"]
            proof_lines = [f"import {pkg}", f"namespace {pkg}.Spec"]
            for tfull in thms:
                tshort = tfull.split(".")[-1]
                spec_lines.append(f"theorem {tshort} (x : Nat) : {pkg}.op x = x := by sorry")
                proof_lines.append(f"theorem {tshort} (x : Nat) : {pkg}.op x = x := rfl")
            spec_lines.append(f"end {pkg}.Spec\n")
            proof_lines.append(f"end {pkg}.Spec\n")
            (root / pkg / "Spec.lean").write_text("\n".join(spec_lines), encoding="utf-8")
            (root / pkg / "Proofs.lean").write_text("\n".join(proof_lines), encoding="utf-8")
            (root / "Main.lean").write_text(f"import {pkg}\ndef main : IO Unit := IO.println s!\"{{{pkg}.op 1}}\"\n", encoding="utf-8")
            (root / "lakefile.toml").write_text(
                f'name = "{pkg.lower()}"\nversion = "0.1.0"\ndefaultTargets = ["{pkg}"]\n\n'
                f'[[lean_lib]]\nname = "{pkg}"\n\n'
                f'[[lean_lib]]\nname = "{pkg}.Spec"\n\n'
                f'[[lean_lib]]\nname = "{pkg}.Proofs"\n\n'
                f'[[lean_exe]]\nname = "{pkg.lower()}"\nroot = "Main"\n',
                encoding="utf-8",
            )
            (root / "comparator.json").write_text(
                json.dumps({
                    "challenge_module": f"{pkg}.Spec",
                    "solution_module": f"{pkg}.Proofs",
                    "theorem_names": thms,
                    "permitted_axioms": ["propext", "Quot.sound", "Classical.choice"],
                }, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "bar.toml").write_text(
                f'[project]\nname = "{pkg.lower()}"\nstatus = "{bar_status}"\npage = "README.md"\n'
                f'spec_authors = ["example-author"]\nentry_points = ["Main.lean"]\n\n'
                f'[spec]\nfiles = ["SPEC.md", "{pkg}/Spec.lean"]\ncode = ["{pkg}.op"]\n\n'
                f'[tests]\nresults = "tests/TEST-RESULTS.md"\ncommand = "{meta["test_cmd"]}"\nfiles = ["tests/run_tests.py"]\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(readme_body, encoding="utf-8")
            out_json = root / "bar_out.json"
            proc = subprocess.run(
                [sys.executable, "-O", "-B", "-W", "error", str(bar_chk), str(root), "--no-lean", "--offline", "--json", str(out_json)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                errs.append(f"bar_check_failed:{(proc.stdout + proc.stderr).strip()[:200]}")
            elif out_json.is_file():
                rep = json.loads(out_json.read_text(encoding="utf-8"))
                by_item = {r["item"]: r["status"] for r in rep.get("items", [])}
                for req_i in (2, 4, 5, 6):
                    if by_item.get(req_i) != "PASS":
                        errs.append(f"bar_item_{req_i}_not_PASS:{by_item.get(req_i)}")
        return len(errs) == 0, errs

    if otype == "verdict_audit":
        jb = _extract_json_block(completion_text)
        if jb is None:
            return False, ["missing_verdict_json_block"]
        try:
            obj = json.loads(jb)
        except ValueError as exc:
            return False, [f"invalid_verdict_json:{exc}"]
        if obj.get("verdict") != meta.get("expected_verdict"):
            errs.append(f"verdict_mismatch:{obj.get('verdict')}!={meta.get('expected_verdict')}")
        if obj.get("source_commit") != meta.get("source_commit"):
            errs.append("source_commit_mismatch_or_truncated")
        if obj.get("axioms") != meta.get("expected_axioms"):
            errs.append("axioms_list_mismatch")
        return len(errs) == 0, errs

    if otype == "f0_claim_gate":
        jb = _extract_json_block(completion_text)
        if jb is None:
            return False, ["missing_f0_json_block"]
        try:
            payload = json.loads(jb)
        except ValueError as exc:
            return False, [f"invalid_f0_json:{exc}"]
        rec = payload.get("record")
        bucket = payload.get("chart_bucket")
        if not isinstance(rec, dict) or bucket not in ("claimed", "verified"):
            return False, ["invalid_f0_wrapper"]
        f0_src = DEPS_ROOT / "f0"
        with tempfile.TemporaryDirectory(prefix="mcproof_ds_f0_") as td:
            rdir = Path(td)
            (rdir / "data").mkdir()
            (rdir / "docs").mkdir()
            shutil.copytree(f0_src / "scripts", rdir / "scripts")
            shutil.copyfile(f0_src / "feed.schema.json", rdir / "feed.schema.json")
            shutil.copyfile(f0_src / "feed.schema.json", rdir / "docs" / "feed.schema.json")
            art_bytes = meta["cert_artifact_bytes_utf8"].encode("utf-8")
            art_sha = meta["cert_artifact_sha256"]
            (rdir / "data" / "certificate.artifact.json").write_bytes(art_bytes)
            mirror_obj = {
                "kappa": "90446448750933/125000000000000000",
                "decimal": "0.000723571590007464",
                "certificate": "certificates/selected-result.json",
                "certificate_sha256": art_sha,
            }
            mirror_bytes = (json.dumps(mirror_obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
            (rdir / "data" / "selected-result.json").write_bytes(mirror_bytes)
            blob_sha1 = hashlib.sha1(b"blob %d\x00" % len(mirror_bytes) + mirror_bytes).hexdigest()
            raw_cap = {
                "path": "certificates/selected-result.json",
                "sha": blob_sha1,
                "size": len(mirror_bytes),
                "content": base64.b64encode(mirror_bytes).decode("ascii"),
            }
            (rdir / "data" / "selected-result.raw.json").write_text(json.dumps(raw_cap, indent=2) + "\n", encoding="utf-8")
            (rdir / "data" / "records.json").write_text(
                json.dumps({"records": [rec]}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            gen_at = "2026-11-19T00:00:00Z"
            main_sha = hashlib.sha256(b"upstream-main-anchor").hexdigest()[:40]
            sel_block = {
                "kappa": mirror_obj["kappa"],
                "decimal": mirror_obj["decimal"],
                "certificate_sha256": art_sha,
                "selected_result_sha256": hashlib.sha256(mirror_bytes).hexdigest(),
                "source_blob_sha": blob_sha1,
                "source_path": "certificates/selected-result.json",
            }
            feed_obj = {
                "feed_version": 1,
                "generated_at": gen_at,
                "upstream_main_sha": main_sha,
                "selected_result": sel_block,
                "records": [rec] if not rec.get("stale") else [],
                "quarantined": [rec] if rec.get("stale") else [],
            }
            c_row_claimed = {
                "pr": rec.get("pr"),
                "head_sha": rec.get("head_sha"),
                "kappa_decimal": rec.get("kappa_decimal"),
                "draft": rec.get("draft", False),
                "pr_updated_at": rec.get("pr_updated_at"),
                "pr_url": (rec.get("source_refs") or {}).get("pr_url"),
            }
            c_row_ver = {
                "pr": rec.get("pr"),
                "head_sha": rec.get("head_sha"),
                "kappa_decimal": rec.get("kappa_decimal"),
                "tier": rec.get("tier"),
                "pr_updated_at": rec.get("pr_updated_at"),
                "pr_url": (rec.get("source_refs") or {}).get("pr_url"),
            }
            chart_obj = {
                "generated_at": gen_at,
                "claimed": [c_row_claimed] if bucket == "claimed" else [],
                "verified": [c_row_ver] if bucket == "verified" else [],
            }
            (rdir / "docs" / "feed.json").write_text(
                json.dumps(feed_obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (rdir / "docs" / "chart-data.json").write_text(
                json.dumps(chart_obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            proc = subprocess.run(
                [sys.executable, "-O", "-B", "-W", "error", str(rdir / "scripts" / "gate.py"), "--root", str(rdir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                errs.append(f"f0_gate_failed:{(proc.stdout + proc.stderr).strip()[:200]}")
            if rec.get("tier") != meta.get("expected_f0_tier") or bucket != meta.get("expected_chart_bucket"):
                errs.append("f0_tier_or_bucket_mismatch")
        return len(errs) == 0, errs

    return True, []


def main() -> int:
    ap = argparse.ArgumentParser(description="Grade a public dataset item completion with Tier 2 oracles.")
    ap.add_argument("--id", required=True, help="Dataset item ID (e.g. PUB-A-C01)")
    ap.add_argument("--input", default=None, help="Candidate completion path or '-' for stdin (defaults to gold target)")
    ap.add_argument("--negative", action="store_true", help="Grade the record's negative_completion instead")
    args = ap.parse_args()

    row = _load_item(args.id)
    if args.negative:
        comp_text = row["negative_completion"]
    elif args.input == "-":
        comp_text = sys.stdin.read()
    elif args.input is not None:
        comp_text = Path(args.input).read_text(encoding="utf-8")
    else:
        comp_text = (DATASETS_ROOT / row["target_path"]).read_text(encoding="utf-8")

    cmd = [
        str(MCPROOF_BIN),
        "--json",
        "grade",
        "--family",
        row["family"],
        "--expected-tier",
        row["expected_tier"],
        "--input",
        "-",
    ]
    if row["family"] == "B":
        cmd.extend(["--fixture-json", str(DATASETS_ROOT / row["harness_path"])])

    proc = subprocess.run(cmd, input=comp_text, capture_output=True, text=True, check=False)
    receipt = json.loads(proc.stdout)
    passed = bool(receipt.get("passed", False)) and proc.returncode == 0

    if row["family"] == "C":
        harness = json.loads((DATASETS_ROOT / row["harness_path"]).read_text(encoding="utf-8"))
        c_ok, c_errs = _run_family_c_deep_oracle(harness, comp_text)
        if not c_ok:
            passed = False
            findings = list(receipt.get("findings", []))
            for ce in c_errs:
                findings.append({"rule": "FAMILY_C_DEEP_ORACLE", "message": ce})
            receipt["passed"] = False
            receipt["epistemic_status"] = "REJECTED"
            receipt["findings"] = findings

    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
