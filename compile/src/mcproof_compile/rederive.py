"""Deterministic 0-byte CPU float64 re-derivation verifier across all 9/9 P2-B outputs.

Compiles Arm P2-B from scratch into a fresh directory taking hyperparameters from
`compiler_suite` constants and `source_lineage` / `zone_manifest_id` / tracked Plane 1
files from `<repo_root>/spec/lineage.json` (never from `--expected-p2b-dir`), then
verifies byte-for-byte identity across all 9/9 P2-B artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from .activation_harvester import verify_cached_activations_npz
from .compiler_suite import (
    DEFAULT_LAMBDA_LEAKAGE,
    DEFAULT_LAMBDA_RIDGE,
    DEFAULT_OUTPUT_GAIN,
    DEFAULT_PRESERVATION_WEIGHT,
    DEFAULT_RANK,
    PRE_REGISTERED_GATE_POLICY,
    compile_p2b_deterministic,
)
from .hardware_probe import PINNED_ZONE_MANIFEST_ID, probe_llama_server

P2B_CHECKED_FILES: tuple[str, ...] = (
    "formal-verification.p2b.f16.gguf",
    "formal-verification.p2b.f16.wfsl",
    "formal-verification.p2b.int4_int8.wfsl",
    "formal-verification.p2b.int4_f16.wfsl",
    "formal-verification.p2b.certificate.json",
    "formal-verification.p2b.binding.json",
    "formal-verification.p2b.gate_policy.json",
    "formal-verification.p2b.warp_bundle.json",
    "formal-verification.p2b.wmcp_meta.json",
)


def _load_lineage_inputs_from_repo(
    plane1_root: Path,
) -> tuple[dict[str, Any], str, list[str]]:
    lineage_path = Path(plane1_root) / "spec" / "lineage.json"
    if not lineage_path.is_file():
        raise FileNotFoundError(f"Missing pinned Plane 1 lineage file: {lineage_path}")
    lineage_doc = json.loads(lineage_path.read_text(encoding="utf-8"))
    source_lineage = dict(lineage_doc["source_lineage"])
    zone_manifest_id = str(lineage_doc.get("zone_manifest_id", PINNED_ZONE_MANIFEST_ID))
    tracked = lineage_doc.get("tracked_plane1_files", {})
    plane1_rel_files = sorted(
        set(tracked.keys() if isinstance(tracked, dict) else ())
        | {"spec/plane1_formal_spec.md", "spec/lineage.json"}
    )
    return source_lineage, zone_manifest_id, plane1_rel_files


def _resolve_llama_server_commit(
    explicit_commit: str | None,
    phase2_report_path: Path | None = None,
) -> str:
    if isinstance(explicit_commit, str) and explicit_commit.strip():
        return explicit_commit.strip()
    probed = probe_llama_server()
    probed_commit = probed.get("commit")
    if isinstance(probed_commit, str) and probed_commit.strip():
        return probed_commit.strip()
    if phase2_report_path is not None and phase2_report_path.is_file():
        hw_doc = json.loads(phase2_report_path.read_text(encoding="utf-8"))
        rep_commit = ((hw_doc.get("llama_server") or {}).get("commit"))
        if isinstance(rep_commit, str) and rep_commit.strip():
            return rep_commit.strip()
    raise RuntimeError(
        "Unable to resolve verified llama_server_commit from live llama-server or Phase 2 hardware report"
    )


def run_independent_rederivation(
    *,
    expected_p2b_dir: Path,
    output_dir: Path,
    safetensors_dir: Path,
    activations_npz: Path,
    plane1_root: Path,
    plane1_rel_files: list[str] | None = None,
    source_lineage: dict[str, Any] | None = None,
    zone_manifest_id: str | None = None,
    llama_server_commit: str | None = None,
    phase2_report_path: Path | None = None,
    rank: int = DEFAULT_RANK,
    lambda_leakage: float = DEFAULT_LAMBDA_LEAKAGE,
    lambda_ridge: float = DEFAULT_LAMBDA_RIDGE,
    preservation_weight: float = DEFAULT_PRESERVATION_WEIGHT,
    output_gain: float = DEFAULT_OUTPUT_GAIN,
    repo_rel_p2b_dir: str = "compile/artifacts/p2b",
) -> dict[str, Any]:
    """Re-run CPU float64 compilation from independent repo/compiler constants and check all 9/9 files."""
    if source_lineage is None or plane1_rel_files is None or zone_manifest_id is None:
        repo_lineage, repo_zm_id, repo_p1_files = _load_lineage_inputs_from_repo(plane1_root)
        if source_lineage is None:
            source_lineage = repo_lineage
        if zone_manifest_id is None:
            zone_manifest_id = repo_zm_id
        if plane1_rel_files is None:
            plane1_rel_files = repo_p1_files

    meta_sidecar = Path(activations_npz).with_suffix(".meta.json")
    if meta_sidecar.is_file():
        verify_cached_activations_npz(Path(activations_npz), meta_sidecar)

    resolved_commit = _resolve_llama_server_commit(llama_server_commit, phase2_report_path)

    rebuilt = compile_p2b_deterministic(
        safetensors_dir=safetensors_dir,
        activations_npz=activations_npz,
        plane1_root=plane1_root,
        plane1_rel_files=plane1_rel_files,
        source_lineage=source_lineage,
        output_dir=output_dir,
        llama_server_commit=resolved_commit,
        zone_manifest_id=zone_manifest_id,
        rank=int(rank),
        lambda_leakage=float(lambda_leakage),
        lambda_ridge=float(lambda_ridge),
        preservation_weight=float(preservation_weight),
        output_gain=float(output_gain),
        gate_policy=PRE_REGISTERED_GATE_POLICY,
        repo_rel_p2b_dir=repo_rel_p2b_dir,
    )

    comparisons: dict[str, dict[str, Any]] = {}
    all_zero_diff = True
    matched_count = 0
    for fname in P2B_CHECKED_FILES:
        exp_p = Path(expected_p2b_dir) / fname
        reb_p = Path(output_dir) / fname
        reb_b = reb_p.read_bytes()
        reb_sha = hashlib.sha256(reb_b).hexdigest()

        if not exp_p.is_file():
            all_zero_diff = False
            comparisons[fname] = {
                "expected_sha256": None,
                "rederived_sha256": reb_sha,
                "byte_len": len(reb_b),
                "byte_diff_count": len(reb_b),
                "crlf_only_mismatch": False,
                "diagnostic": "missing_expected_file",
                "zero_byte_diff": False,
            }
            continue

        exp_b = exp_p.read_bytes()
        exp_sha = hashlib.sha256(exp_b).hexdigest()
        exact_equal = exp_b == reb_b and hmac.compare_digest(exp_sha, reb_sha)
        byte_diff = 0 if exact_equal else abs(len(exp_b) - len(reb_b)) + sum(
            1 for x, y in zip(exp_b, reb_b) if x != y
        )
        crlf_only = False
        diag = "exact_match"
        if not exact_equal:
            all_zero_diff = False
            if fname.endswith(".json") and exp_b.replace(b"\r\n", b"\n") == reb_b:
                crlf_only = True
                diag = (
                    "expected_json_has_crlf_line_endings_lf_content_matches "
                    "(configure git core.autocrlf=false or .gitattributes eol=lf)"
                )
            else:
                diag = "byte_mismatch"
        else:
            matched_count += 1

        comparisons[fname] = {
            "expected_sha256": exp_sha,
            "rederived_sha256": reb_sha,
            "byte_len": len(reb_b),
            "byte_diff_count": byte_diff,
            "crlf_only_mismatch": crlf_only,
            "diagnostic": diag,
            "zero_byte_diff": exact_equal,
        }

    return {
        "schema": "mcproof-rederivation-receipt/v0.2",
        "checked_file_count": len(P2B_CHECKED_FILES),
        "matched_file_count": matched_count,
        "zero_byte_diff_all": all_zero_diff and matched_count == len(P2B_CHECKED_FILES),
        "parameter_provenance": {
            "hyperparameters_source": "mcproof_compile.compiler_suite.DEFAULT_*",
            "lineage_source": "spec/lineage.json",
            "gate_policy_source": "mcproof_compile.compiler_suite.PRE_REGISTERED_GATE_POLICY",
        },
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
    ap = argparse.ArgumentParser(
        description="Deterministic CPU float64 0-byte re-derivation check across all 9/9 P2-B files"
    )
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
        "--phase2-report",
        default=compile_root / "artifacts" / "phase2_hardware_checkpoint_report.json",
        type=Path,
    )
    ap.add_argument("--llama-server-commit", default=None, type=str)
    ap.add_argument("--rank", default=DEFAULT_RANK, type=int)
    ap.add_argument("--lambda-leakage", default=DEFAULT_LAMBDA_LEAKAGE, type=float)
    ap.add_argument("--lambda-ridge", default=DEFAULT_LAMBDA_RIDGE, type=float)
    ap.add_argument("--preservation-weight", default=DEFAULT_PRESERVATION_WEIGHT, type=float)
    ap.add_argument("--output-gain", default=DEFAULT_OUTPUT_GAIN, type=float)
    args = ap.parse_args()

    receipt = run_independent_rederivation(
        expected_p2b_dir=args.expected_p2b_dir,
        output_dir=args.output_dir,
        safetensors_dir=args.safetensors_dir,
        activations_npz=args.activations_npz,
        plane1_root=args.plane1_root,
        llama_server_commit=args.llama_server_commit,
        phase2_report_path=args.phase2_report,
        rank=args.rank,
        lambda_leakage=args.lambda_leakage,
        lambda_ridge=args.lambda_ridge,
        preservation_weight=args.preservation_weight,
        output_gain=args.output_gain,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["zero_byte_diff_all"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
