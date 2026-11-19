"""Independent 0-byte deterministic CPU float64 re-derivation verifier for P2-B.

Can be invoked standalone across separate processes or from `verification/` to verify
exact byte-for-byte identity (`0`-byte diff) across all P2-B outputs.

Usage:
  PYTHONHASHSEED=0 python3 -m mcproof_compile.rederive \
    --expected-p2b-dir compile/artifacts/p2b \
    --output-dir /tmp/rederived_p2b
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .compiler_suite import compile_p2b_deterministic


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_independent_rederivation(
    *,
    expected_p2b_dir: Path,
    output_dir: Path,
    safetensors_dir: Path,
    activations_npz: Path,
    plane1_root: Path,
    plane1_rel_files: list[str],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    binding_ref = json.loads(
        (expected_p2b_dir / "formal-verification.p2b.binding.json").read_text(encoding="utf-8")
    )
    recipe = binding_ref["derivation_recipe"]

    rebuilt = compile_p2b_deterministic(
        safetensors_dir=safetensors_dir,
        activations_npz=activations_npz,
        plane1_root=plane1_root,
        plane1_rel_files=plane1_rel_files,
        source_lineage=source_lineage,
        output_dir=output_dir,
        zone_manifest_id=recipe["zone_manifest_id"],
        rank=int(recipe["rank"]),
        lambda_leakage=float(recipe["lambda_leakage"]),
        lambda_ridge=float(recipe["lambda_ridge"]),
        preservation_weight=float(recipe["preservation_weight"]),
        output_gain=float(recipe["output_gain"]),
    )

    checked_files = (
        "formal-verification.p2b.f16.gguf",
        "formal-verification.p2b.int4_int8.wfsl",
        "formal-verification.p2b.int4_f16.wfsl",
        "formal-verification.p2b.f16.wfsl",
        "formal-verification.p2b.certificate.json",
        "formal-verification.p2b.binding.json",
    )
    comparisons: dict[str, dict[str, Any]] = {}
    all_zero_diff = True
    for fname in checked_files:
        exp_p = expected_p2b_dir / fname
        reb_p = output_dir / fname
        exp_b = exp_p.read_bytes()
        reb_b = reb_p.read_bytes()
        exp_sha = hashlib.sha256(exp_b).hexdigest()
        reb_sha = hashlib.sha256(reb_b).hexdigest()
        byte_diff = 0 if exp_b == reb_b else abs(len(exp_b) - len(reb_b)) + sum(
            1 for x, y in zip(exp_b, reb_b) if x != y
        )
        if byte_diff != 0 or exp_sha != reb_sha:
            all_zero_diff = False
        comparisons[fname] = {
            "expected_sha256": exp_sha,
            "rederived_sha256": reb_sha,
            "byte_len": len(reb_b),
            "byte_diff_count": byte_diff,
            "zero_byte_diff": byte_diff == 0 and exp_sha == reb_sha,
        }

    return {
        "schema": "mcproof-rederivation-receipt/v0.1",
        "zero_byte_diff_all": all_zero_diff,
        "files": comparisons,
        "factor_f16_digest": rebuilt["artifacts"]["factor_f16_digest"],
        "certificate_sha256": rebuilt["artifacts"]["certificate_sha256"],
    }


def main() -> None:
    compile_root = Path(__file__).resolve().parents[2]
    repo_root = (
        compile_root.parent
        if (compile_root.parent / "spec" / "lineage.json").is_file()
        else (compile_root.parent / "repo")
    )
    ap = argparse.ArgumentParser(description="Independent CPU float64 0-byte re-derivation check")
    ap.add_argument("--expected-p2b-dir", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument(
        "--safetensors-dir",
        default=compile_root / "checkpoints" / "Qwen3.5-4B",
        type=Path,
    )
    ap.add_argument(
        "--activations-npz",
        default=compile_root / "artifacts" / "harvested_activations.npz",
        type=Path,
    )
    ap.add_argument(
        "--plane1-root",
        default=repo_root,
        type=Path,
    )
    ap.add_argument(
        "--plane1-file",
        action="append",
        dest="plane1_files",
        default=None,
    )
    args = ap.parse_args()

    exp_bundle = json.loads(
        (args.expected_p2b_dir / "formal-verification.p2b.warp_bundle.json").read_text(encoding="utf-8")
    )
    exp_bind = json.loads(
        (args.expected_p2b_dir / "formal-verification.p2b.binding.json").read_text(encoding="utf-8")
    )
    p1_files = args.plane1_files or sorted(exp_bind["plane1_hashes"].keys())

    receipt = run_independent_rederivation(
        expected_p2b_dir=args.expected_p2b_dir,
        output_dir=args.output_dir,
        safetensors_dir=args.safetensors_dir,
        activations_npz=args.activations_npz,
        plane1_root=args.plane1_root,
        plane1_rel_files=p1_files,
        source_lineage=exp_bundle["source_lineage"],
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["zero_byte_diff_all"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
