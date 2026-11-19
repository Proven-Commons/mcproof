"""End-to-end reproducible CLI pipeline for Phase 2 + Phase 3 (`siliconcordat/mde#4`)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .ablations import (
    build_constant_logit_bias_control,
    build_sabotage_and_goodhart_controls,
    run_loud_column_ablation,
)
from .activation_harvester import harvest_all_activations
from .compiler_suite import (
    DEFAULT_LAMBDA_LEAKAGE,
    DEFAULT_LAMBDA_RIDGE,
    DEFAULT_PRESERVATION_WEIGHT,
    DEFAULT_RANK,
    compile_p2a_baseline,
    compile_p2b_deterministic,
    compile_phase6_companion_packs,
)
from .evaluator import evaluate_all_arms_on_validation
from .hardware_probe import (
    PINNED_ZONE_MANIFEST_ID,
    build_hardware_and_checkpoint_report,
)


_DEFAULT_COMPILE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REPO_ROOT = (
    _DEFAULT_COMPILE_ROOT.parent
    if (_DEFAULT_COMPILE_ROOT.parent / "spec" / "lineage.json").is_file()
    else (_DEFAULT_COMPILE_ROOT.parent / "repo")
)


def run_full_pipeline(
    *,
    compile_root: Path = _DEFAULT_COMPILE_ROOT,
    repo_root: Path = _DEFAULT_REPO_ROOT,
    datasets_dir: Path = _DEFAULT_REPO_ROOT / "datasets",
    deps_dir: Path = _DEFAULT_REPO_ROOT.parent / "deps",
    skip_harvest_if_cached: bool = False,
    skip_eval: bool = False,
    reuse_cached_eval: bool = False,
    output_gain: float = 1.65,
    p2b_eval_scale: float = 1.0,
) -> dict[str, Any]:
    gguf_path = compile_root / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf"
    st_dir = compile_root / "checkpoints" / "Qwen3.5-4B"
    artifacts_dir = compile_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Phase 2 Hardware & Checkpoint Discovery
    hw_report_path = artifacts_dir / "phase2_hardware_checkpoint_report.json"
    hw_report = build_hardware_and_checkpoint_report(
        gguf_path=gguf_path,
        safetensors_dir=st_dir,
        output_path=hw_report_path,
    )

    # 2. Load Plane 1 lineage from `repo/spec/lineage.json`
    lineage_json_path = repo_root / "spec" / "lineage.json"
    lineage_data = json.loads(lineage_json_path.read_text(encoding="utf-8"))
    source_lineage = lineage_data["source_lineage"]
    zone_manifest_id = lineage_data.get("zone_manifest_id", PINNED_ZONE_MANIFEST_ID)
    plane1_rel_files = sorted(
        set(lineage_data.get("tracked_plane1_files", {}).keys())
        | {"spec/plane1_formal_spec.md", "spec/lineage.json"}
    )

    # 3. Harvest real activations over `compile.jsonl` (96) + `hybrid_k0.jsonl` (2048 + 24)
    npz_path = artifacts_dir / "harvested_activations.npz"
    if not (skip_harvest_if_cached and npz_path.is_file()):
        harvest_meta = harvest_all_activations(
            safetensors_dir=st_dir,
            compile_jsonl=datasets_dir / "compile.jsonl",
            hybrid_k0_jsonl=datasets_dir / "hybrid_k0.jsonl",
            output_npz=npz_path,
        )
    else:
        harvest_meta = json.loads(npz_path.with_suffix(".meta.json").read_text(encoding="utf-8"))

    # 4. Compile Arm P2-B (Full weft BetaEdit rank-8 CPU float64 solve)
    p2b_dir = artifacts_dir / "p2b"
    p2b_res = compile_p2b_deterministic(
        safetensors_dir=st_dir,
        activations_npz=npz_path,
        plane1_root=repo_root,
        plane1_rel_files=plane1_rel_files,
        source_lineage=source_lineage,
        output_dir=p2b_dir,
        llama_server_commit=hw_report["llama_server"]["commit"],
        zone_manifest_id=zone_manifest_id,
        rank=DEFAULT_RANK,
        lambda_leakage=DEFAULT_LAMBDA_LEAKAGE,
        lambda_ridge=DEFAULT_LAMBDA_RIDGE,
        preservation_weight=DEFAULT_PRESERVATION_WEIGHT,
        output_gain=output_gain,
    )

    # 5. Independent 2nd-process CPU float64 re-derivation check (`0`-byte diff!)
    with tempfile.TemporaryDirectory(prefix="mcproof_rederive_check_") as tmp_rd:
        rd_cmd = [
            sys.executable,
            "-m",
            "mcproof_compile.rederive",
            "--expected-p2b-dir",
            str(p2b_dir),
            "--output-dir",
            str(Path(tmp_rd) / "rederived"),
            "--safetensors-dir",
            str(st_dir),
            "--activations-npz",
            str(npz_path),
            "--plane1-root",
            str(repo_root),
        ]
        env = {**os.environ, "PYTHONHASHSEED": "0"}
        rd_proc = subprocess.run(rd_cmd, capture_output=True, text=True, env=env, check=False)
        if rd_proc.returncode != 0:
            raise RuntimeError(
                f"Independent subprocess 0-byte re-derivation FAILED:\n{rd_proc.stdout}\n{rd_proc.stderr}"
            )
        rederive_receipt = json.loads(rd_proc.stdout)
    (artifacts_dir / "rederivation_receipt.json").write_text(
        json.dumps(rederive_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # 6. Compile Arm P2-A (Activation-projected low-rank steering without null-space BetaEdit)
    p2a_dir = artifacts_dir / "p2a"
    p2b_frob = float(
        np.linalg.norm(
            p2b_res["p2b_f16_patch"].factor_b @ p2b_res["p2b_f16_patch"].factor_a, ord="fro"
        )
    )
    p2a_res = compile_p2a_baseline(
        w0_down=p2b_res["w0_down"],
        compile_keys=p2b_res["compile_keys"],
        compile_residuals=p2b_res["compile_residuals"],
        cov_accum_for_audit=p2b_res["projector"].cov_accum,
        safety_directions=p2b_res["safety_directions"],
        target_frob_norm=p2b_frob,
        base_weights_sha256=p2b_res["binding_manifest"].checkpoint_fingerprint,
        zone_manifest_id=zone_manifest_id,
        output_dir=p2a_dir,
        rank=DEFAULT_RANK,
    )

    # 7. Run all 3 Mandatory Ablations & Negative Controls
    npz_data = np.load(npz_path)
    ablations_dir = artifacts_dir / "ablations"
    ablations_dir.mkdir(parents=True, exist_ok=True)

    loud_col_res = run_loud_column_ablation(
        safetensors_dir=st_dir,
        ffn_down_k0=np.ascontiguousarray(npz_data["ffn_down_k0"], dtype=np.float64),
        up_k0_eval=p2b_res["k0_norm"],
        p2b_raw_b64=p2b_res["raw_b64"],
        p2b_raw_a64=p2b_res["raw_a64"],
        up_cov_accum=p2b_res["projector"].cov_accum,
    )
    loud_col_path = ablations_dir / "loud_column_ablation.json"
    loud_col_path.write_text(json.dumps(loud_col_res, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    logit_bias_path = ablations_dir / "constant_logit_bias.json"
    logit_bias_res = build_constant_logit_bias_control(
        safetensors_dir=st_dir,
        compile_ffn_residuals=np.ascontiguousarray(npz_data["compile_ffn_residuals"], dtype=np.float64),
        compile_pos_toks=npz_data["compile_pos_toks"],
        compile_neg_toks=npz_data["compile_neg_toks"],
        output_path=logit_bias_path,
    )

    controls_dir = artifacts_dir / "controls"
    controls_res = build_sabotage_and_goodhart_controls(
        cov_true_proj=p2b_res["projector"],
        k0_norm=p2b_res["k0_norm"],
        k0_anchors=p2b_res["k0_anchors"],
        safety_keys=np.ascontiguousarray(npz_data["safety_keys"], dtype=np.float64),
        safety_sabotage_residuals=np.ascontiguousarray(
            npz_data["safety_sabotage_residuals"], dtype=np.float64
        ),
        compile_keys=p2b_res["compile_keys"],
        goodhart_residuals=np.ascontiguousarray(npz_data["goodhart_residuals"], dtype=np.float64),
        architecture="qwen35",
        base_weights_sha256=p2b_res["binding_manifest"].checkpoint_fingerprint,
        zone_manifest_id=zone_manifest_id,
        p2b_warp_bundle=p2b_res["warp_bundle"],
        gate_policy=p2b_res["gate_policy"],
        controls_dir=controls_dir,
    )
    (controls_dir / "negative_controls_summary.json").write_text(
        json.dumps(controls_res, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # 8. Compile Phase 6 Companion Packs (`corpus` + `weft-eido`) for `@stack`
    comp_dir = artifacts_dir / "composition"
    comp_packs = compile_phase6_companion_packs(
        proj_shared=p2b_res["projector"],
        safetensors_dir=st_dir,
        activations_npz=npz_path,
        p2b_result=p2b_res,
        plane1_corpus_doc=deps_dir / "mission" / "playbook" / "verified-bar.md",
        plane1_eido_doc=deps_dir / "weft-eido" / "README.md",
        source_lineage=source_lineage,
        output_dir=comp_dir,
        zone_manifest_id=zone_manifest_id,
    )
    (comp_dir / "composition_manifest.json").write_text(
        json.dumps(comp_packs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # 9. Live Evaluation of all arms on `validation.jsonl` (48 prompts, temp=0, top_p=1.0)
    cached_scorecard_path = artifacts_dir / "evaluation" / "validation_scorecard.json"
    eval_summary = None
    if reuse_cached_eval and cached_scorecard_path.is_file():
        eval_summary = json.loads(cached_scorecard_path.read_text(encoding="utf-8"))
    elif not skip_eval:
        eval_summary = evaluate_all_arms_on_validation(
            gguf_path=gguf_path,
            safetensors_dir=st_dir,
            validation_jsonl=datasets_dir / "validation.jsonl",
            plane1_spec_path=repo_root / "spec" / "plane1_formal_spec.md",
            repo_root=repo_root,
            p2a_gguf=Path(p2a_res["gguf_f16_path"]),
            p2b_gguf=Path(p2b_res["artifacts"]["gguf_f16_path"]),
            sabotage_gguf=Path(controls_res["sabotage_patch"]["gguf_path"]),
            goodhart_gguf=Path(controls_res["goodhart_patch"]["gguf_path"]),
            logit_bias_json=logit_bias_path,
            output_dir=artifacts_dir / "evaluation",
            p2b_scale=p2b_eval_scale,
        )

    p2b_recipe = dict(p2b_res["binding_manifest"].derivation_recipe)
    compiler_hyperparameters = {
        **p2b_recipe,
        "max_slots": 8,
        "nullspace_threshold": 1e9,
        "threshold_mode": "absolute",
        "radix_scale_exp2": 24,
        "seed": 20261119,
        "k0_trace_normalization": "1/sqrt(n_k0_noise)",
        "quantization_spec": {
            "gguf_lora": "f16",
            "slab_f16": {"quant_dtype": "f16", "b_quant_dtype": "f16", "a_quant_dtype": "f16"},
            "slab_int4_int8": {"quant_dtype": "f16", "b_quant_dtype": "int4", "a_quant_dtype": "int8"},
            "slab_int4_f16": {"quant_dtype": "f16", "b_quant_dtype": "int4", "a_quant_dtype": "f16"},
        },
        "lora_alpha": float(DEFAULT_RANK),
        "p2b_eval_scale": p2b_eval_scale,
    }

    master_manifest = {
        "schema": "mcproof-phase2-phase3-manifest/v0.1",
        "phase2_report": str(hw_report_path),
        "compiler_hyperparameters": compiler_hyperparameters,
        "harvest_summary": {k: v for k, v in harvest_meta.items() if k != "step_metadata"},
        "p2b": p2b_res["artifacts"],
        "p2a": p2a_res,
        "rederivation_zero_byte_diff": rederive_receipt["zero_byte_diff_all"],
        "loud_column_ablation_headline": loud_col_res["headline_ratios"],
        "constant_logit_bias_sha256": logit_bias_res["sha256"],
        "negative_controls": {
            "sabotage_gguf_sha256": controls_res["sabotage_patch"]["gguf_sha256"],
            "sabotage_norm_only_passes": controls_res["sabotage_patch"]["norm_only_gate_passes"],
            "sabotage_stage2_cert_passes": controls_res["sabotage_patch"]["stage2_certificate_passes"],
            "goodhart_gguf_sha256": controls_res["goodhart_patch"]["gguf_sha256"],
            "goodhart_stage2_cert_passes": controls_res["goodhart_patch"]["stage2_certificate_passes"],
        },
        "phase6_composition_packs": {
            k: {"gguf_path": v["gguf_path"], "gguf_sha256": v["gguf_sha256"], "warp_bundle_path": v["warp_bundle_path"]}
            for k, v in comp_packs.items()
        },
        "validation_scorecard": eval_summary,
    }
    manifest_json = json.dumps(master_manifest, indent=2, sort_keys=True) + "\n"
    tmp_m1 = artifacts_dir / ".MANIFEST.json.tmp"
    tmp_m2 = artifacts_dir / ".compiler_manifest.json.tmp"
    tmp_m1.write_text(manifest_json, encoding="utf-8")
    tmp_m2.write_text(manifest_json, encoding="utf-8")
    tmp_m1.replace(artifacts_dir / "MANIFEST.json")
    tmp_m2.replace(artifacts_dir / "compiler_manifest.json")
    return master_manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Phase 2 + Phase 3 mcproof compilation & evaluation")
    ap.add_argument("--skip-harvest-if-cached", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--reuse-cached-eval", action="store_true")
    ap.add_argument("--output-gain", type=float, default=1.65)
    ap.add_argument("--p2b-eval-scale", type=float, default=1.0)
    args = ap.parse_args()
    res = run_full_pipeline(
        skip_harvest_if_cached=args.skip_harvest_if_cached,
        skip_eval=args.skip_eval,
        reuse_cached_eval=args.reuse_cached_eval,
        output_gain=args.output_gain,
        p2b_eval_scale=args.p2b_eval_scale,
    )
    print(json.dumps(res, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
