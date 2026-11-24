"""End-to-end reproducible CLI pipeline for Phase 2 + Phase 3 (`siliconcordat/mde#4`)."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .ablations import (
    build_constant_logit_bias_control,
    build_sabotage_and_goodhart_controls,
    run_loud_column_ablation,
)
from .activation_harvester import harvest_all_activations, verify_cached_activations_npz
from .compiler_suite import (
    DEFAULT_LAMBDA_LEAKAGE,
    DEFAULT_LAMBDA_RIDGE,
    DEFAULT_OUTPUT_GAIN,
    DEFAULT_PRESERVATION_WEIGHT,
    DEFAULT_RANK,
    PRE_REGISTERED_GATE_POLICY,
    compile_p2a_baseline,
    compile_p2b_deterministic,
    compile_phase6_companion_packs,
)
from .evaluator import (
    build_validation_scorecard_summary,
    evaluate_all_arms_on_validation,
    measure_live_b1_prefix_cache_parity,
)
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


def _resolve_bundle_with_disk_adapter_path(
    bundle_dict: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    out = copy.deepcopy(bundle_dict)
    ap = out.get("adapter_path")
    if isinstance(ap, str) and ap and not Path(ap).is_absolute():
        out["adapter_path"] = str((Path(repo_root) / ap).resolve())
    return out


def verify_control_gates_fail_closed(
    *,
    repo_root: Path,
    p2b_res: dict[str, Any],
    p2a_res: dict[str, Any],
    controls_res: dict[str, Any],
    source_lineage: dict[str, Any],
    zone_manifest_id: str,
    controls_dir: Path,
) -> dict[str, Any]:
    """Enforce fail-closed Stage 1/2/3 assertions on sabotage and tamper bundles and write receipt."""
    from warp_modeld.canary import reject_adapter_supplied_canaries
    from warp_modeld.certificate import CertificateBounds, RationalBound, verify_stack_division_free
    from warp_modeld.errors import (
        CertificateError,
        ForgedCanaryError,
        StaleLineageError,
        ZoneManifestDriftError,
    )
    from warp_modeld.fingerprint import (
        AdapterBundle,
        CheckpointFingerprint,
        Plane1Lineage,
        verify_stage1,
    )

    if controls_res["sabotage_patch"]["stage2_certificate_passes"]:
        raise RuntimeError("Fail-closed violation: sabotage_patch passed Stage 2 certificate gate")
    if not controls_res["sabotage_patch"]["norm_only_gate_passes"]:
        raise RuntimeError("Control calibration violation: sabotage_patch did not pass norm-only Gate 1")
    if p2a_res.get("stage2_gate_passes", False):
        raise RuntimeError("Fail-closed violation: unprojected P2-A passed Stage 2 certificate gate")
    if not controls_res["goodhart_patch"]["stage2_certificate_passes"]:
        raise RuntimeError("In-nullspace Goodhart control unexpectedly failed Stage 2 certificate gate")

    gp = p2b_res["gate_policy"]
    single_bounds = CertificateBounds(
        max_frobenius_sq=RationalBound(gp.max_frob_sq_num, gp.max_frob_sq_den),
        max_spectral_norm_sq=RationalBound(
            gp.max_spectral_sq_num if gp.max_spectral_sq_num is not None else gp.max_frob_sq_num,
            gp.max_spectral_sq_den,
        ),
        max_leakage_energy=RationalBound(
            gp.max_leakage_num if gp.max_leakage_num is not None else 1,
            gp.max_leakage_den,
        ),
        max_safety_dot_sq=RationalBound(
            gp.max_safety_dot_sq_num if gp.max_safety_dot_sq_num is not None else 1,
            gp.max_safety_dot_sq_den,
        ),
    )

    p2b_bundle_disk = _resolve_bundle_with_disk_adapter_path(p2b_res["warp_bundle"], repo_root)
    reject_adapter_supplied_canaries([p2b_bundle_disk])
    p2b_bundle_obj = AdapterBundle.from_dict(p2b_bundle_disk)
    pinned_ckpt = CheckpointFingerprint.from_dict(p2b_bundle_disk["checkpoint"])
    pinned_lin = Plane1Lineage.from_dict(source_lineage)
    warp_flags = p2b_res["warp_flags"]

    s1_p2b = verify_stage1(
        p2b_bundle_obj,
        pinned_ckpt,
        pinned_lin,
        warp_flags,
        pinned_zone_manifest_id=zone_manifest_id,
    )
    if not s1_p2b.adapter_file_verified:
        raise RuntimeError("P2-B Stage 1 on-disk GGUF SHA-256 verification did not execute")

    verify_stack_division_free(
        [
            (
                p2b_bundle_obj.certificate,
                p2b_bundle_obj.adapter_id,
                p2b_bundle_obj.adapter_sha256,
                p2b_bundle_obj.scale_num,
                p2b_bundle_obj.scale_den,
            )
        ],
        single_bounds,
        single_bounds,
        expected_base_weights_sha256=pinned_ckpt.weights_sha256,
    )

    bundle_rel_map = controls_res["warp_adversarial_bundles"]

    def _load_ctrl_dict(key: str) -> dict[str, Any]:
        rel_p = bundle_rel_map[key]
        p = Path(rel_p) if Path(rel_p).is_absolute() else (Path(repo_root) / rel_p)
        return json.loads(p.read_text(encoding="utf-8"))

    checks_out: dict[str, dict[str, Any]] = {}

    # 1. forged_canary -> Stage 3 pre-load ForgedCanaryError
    forged_canary_raw = _load_ctrl_dict("forged_canary_warp_bundle")
    try:
        reject_adapter_supplied_canaries([forged_canary_raw])
    except ForgedCanaryError as exc:
        checks_out["forged_canary"] = {
            "failed_closed": True,
            "rejection_stage": "stage3_preload_canary_hygiene",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", "ERR_FORGED_CANARY"),
        }
    else:
        raise RuntimeError("Fail-closed violation: forged_canary_warp_bundle was not rejected")

    # 2. stale_lineage -> Stage 1 StaleLineageError
    stale_raw = _resolve_bundle_with_disk_adapter_path(
        _load_ctrl_dict("stale_lineage_warp_bundle"), repo_root
    )
    try:
        verify_stage1(
            AdapterBundle.from_dict(stale_raw),
            pinned_ckpt,
            pinned_lin,
            warp_flags,
            pinned_zone_manifest_id=zone_manifest_id,
        )
    except StaleLineageError as exc:
        checks_out["stale_lineage"] = {
            "failed_closed": True,
            "rejection_stage": "stage1_lineage_binding",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", "ERR_STALE_LINEAGE"),
        }
    else:
        raise RuntimeError("Fail-closed violation: stale_lineage_warp_bundle was not rejected")

    # 3. drifted_zone_manifest -> Stage 1 ZoneManifestDriftError
    drift_raw = _resolve_bundle_with_disk_adapter_path(
        _load_ctrl_dict("drifted_zone_manifest_warp_bundle"), repo_root
    )
    try:
        verify_stage1(
            AdapterBundle.from_dict(drift_raw),
            pinned_ckpt,
            pinned_lin,
            warp_flags,
            pinned_zone_manifest_id=zone_manifest_id,
        )
    except ZoneManifestDriftError as exc:
        checks_out["drifted_zone_manifest"] = {
            "failed_closed": True,
            "rejection_stage": "stage1_zone_manifest_binding",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", "ERR_ZONE_MANIFEST_DRIFT"),
        }
    else:
        raise RuntimeError("Fail-closed violation: drifted_zone_manifest_warp_bundle was not rejected")

    # 4. forged_cert -> Stage 2 CertificateError
    forged_cert_raw = _resolve_bundle_with_disk_adapter_path(
        _load_ctrl_dict("forged_cert_warp_bundle"), repo_root
    )
    try:
        fc_obj = AdapterBundle.from_dict(forged_cert_raw)
        verify_stack_division_free(
            [
                (
                    fc_obj.certificate,
                    fc_obj.adapter_id,
                    fc_obj.adapter_sha256,
                    fc_obj.scale_num,
                    fc_obj.scale_den,
                )
            ],
            single_bounds,
            single_bounds,
            expected_base_weights_sha256=pinned_ckpt.weights_sha256,
        )
    except CertificateError as exc:
        checks_out["forged_cert"] = {
            "failed_closed": True,
            "rejection_stage": "stage2_integer_certificate",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", "ERR_CERTIFICATE_TAMPER"),
        }
    else:
        raise RuntimeError("Fail-closed violation: forged_cert_warp_bundle was not rejected")

    # 5. sabotage_patch -> Stage 1 passes, Stage 2 CertificateError
    sab_raw = _resolve_bundle_with_disk_adapter_path(
        _load_ctrl_dict("sabotage_warp_bundle"), repo_root
    )
    sab_obj = AdapterBundle.from_dict(sab_raw)
    verify_stage1(
        sab_obj,
        pinned_ckpt,
        pinned_lin,
        warp_flags,
        pinned_zone_manifest_id=zone_manifest_id,
    )
    try:
        verify_stack_division_free(
            [
                (
                    sab_obj.certificate,
                    sab_obj.adapter_id,
                    sab_obj.adapter_sha256,
                    sab_obj.scale_num,
                    sab_obj.scale_den,
                )
            ],
            single_bounds,
            single_bounds,
            expected_base_weights_sha256=pinned_ckpt.weights_sha256,
        )
    except CertificateError as exc:
        checks_out["sabotage_patch"] = {
            "failed_closed": True,
            "norm_only_gate_passes": True,
            "rejection_stage": "stage2_integer_certificate",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", "ERR_CERTIFICATE_BOUNDS"),
            "weft_rejection_reasons": controls_res["sabotage_patch"]["stage2_rejection_reasons"],
        }
    else:
        raise RuntimeError("Fail-closed violation: sabotage_warp_bundle was not rejected at Stage 2")

    # 6. goodhart_patch -> Stage 1 & Stage 2 admissible by construction (solved inside Null(K0));
    # caught by Stage 3 behavioral domain canaries and Phase 5 holdout, NOT Stage 2.
    gh_raw = _resolve_bundle_with_disk_adapter_path(
        _load_ctrl_dict("goodhart_warp_bundle"), repo_root
    )
    gh_obj = AdapterBundle.from_dict(gh_raw)
    verify_stage1(
        gh_obj,
        pinned_ckpt,
        pinned_lin,
        warp_flags,
        pinned_zone_manifest_id=zone_manifest_id,
    )
    verify_stack_division_free(
        [
            (
                gh_obj.certificate,
                gh_obj.adapter_id,
                gh_obj.adapter_sha256,
                gh_obj.scale_num,
                gh_obj.scale_den,
            )
        ],
        single_bounds,
        single_bounds,
        expected_base_weights_sha256=pinned_ckpt.weights_sha256,
    )

    receipt = {
        "schema": "mcproof-control-gate-verification-receipt/v0.1",
        "gate_policy": asdict(gp),
        "p2b_positive_control": {
            "stage1_passed": True,
            "stage1_adapter_file_verified": True,
            "checkpoint_has_ssm_recurrent": bool(pinned_ckpt.has_ssm_recurrent),
            "stage2_division_free_passed": True,
            "stage3_preload_canary_hygiene_passed": True,
        },
        "p2a_unprojected_baseline": {
            "stage2_division_free_passed": False,
            "weft_rejection_reasons": p2a_res["stage2_rejection_reasons"],
        },
        "fail_closed_stage1_stage2_stage3_preload_rejections": checks_out,
        "all_five_tamper_and_sabotage_controls_failed_closed": all(
            v["failed_closed"] for v in checks_out.values()
        )
        and len(checks_out) == 5,
        "in_nullspace_goodhart_boundary": {
            "stage1_passed": True,
            "stage2_division_free_passed": True,
            "in_nullspace_stage2_admissible": True,
            "caught_at_stage2": False,
            "rejection_boundary": "stage3_domain_canaries_and_phase5_holdout_not_stage2",
            "explanation": (
                "goodhart_patch is solved inside Null(K0) via BetaEditNullspaceProjector so linear "
                "Stage-2 covariance/norm bounds admit it by design; behavioral semantic corruption "
                "is caught at Stage-3 live verifier domain canaries (phase4_mount.py) and Phase-5 holdout."
            ),
        },
    }
    receipt_path = controls_dir / "control_gate_verification_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _refresh_cached_eval_scorecard(
    *,
    cached_scorecard_path: Path,
    cached_eval_jsonl_dir: Path | None,
    gguf_path: Path,
    safetensors_dir: Path,
    validation_jsonl: Path,
    plane1_spec_path: Path,
    llama_available: bool,
    verify_b1_parity_live: bool,
) -> dict[str, Any]:
    raw_sc = json.loads(cached_scorecard_path.read_text(encoding="utf-8"))
    arms = copy.deepcopy(raw_sc["arms"])
    n_prompts = int(raw_sc["n_prompts"])
    max_tokens = int(raw_sc["decoding"]["max_tokens"])
    spec_tokens = int(raw_sc["plane1_spec_tokens_qwen35"])
    p2b_scale = float(raw_sc.get("p2b_lora_scale", 1.0))
    safety_smoke = raw_sc.get("safety_preservation_smoke", {})

    overall_gp: dict[str, int] = {}
    for arm_name, arm_data in arms.items():
        arm_gp: dict[str, int] = {}
        if cached_eval_jsonl_dir is not None:
            cand_jsonl = cached_eval_jsonl_dir / f"validation_{arm_name.lower().replace('-', '_')}.jsonl"
            if cand_jsonl.is_file():
                for line in cand_jsonl.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    gp_k = str(row.get("grading_path") or "datasets_grade_item_script")
                    arm_gp[gp_k] = arm_gp.get(gp_k, 0) + 1
        if not arm_gp:
            existing_gp = arm_data.get("grading_paths_used")
            if isinstance(existing_gp, dict) and existing_gp:
                arm_gp = {str(k): int(v) for k, v in existing_gp.items()}
            else:
                arm_gp = {"datasets_grade_item_script": int(arm_data["total"])}
        arm_data["grading_paths_used"] = dict(sorted(arm_gp.items()))
        for k_gp, v_gp in arm_gp.items():
            overall_gp[k_gp] = overall_gp.get(k_gp, 0) + v_gp

    b1_exact = False
    b1_tested_items = 0
    if verify_b1_parity_live and llama_available and gguf_path.is_file() and safetensors_dir.is_dir():
        b1_exact, b1_tested_items = measure_live_b1_prefix_cache_parity(
            gguf_path=gguf_path,
            safetensors_dir=safetensors_dir,
            validation_jsonl=validation_jsonl,
            plane1_spec_path=plane1_spec_path,
            max_tokens=max_tokens,
            n_test_items=3,
        )
    elif "b1_prefix_cache_tested_items" in raw_sc and int(raw_sc["b1_prefix_cache_tested_items"]) > 0:
        b1_exact = bool(raw_sc.get("b1_prefix_cache_parity_verified", False))
        b1_tested_items = int(raw_sc["b1_prefix_cache_tested_items"])

    refreshed = build_validation_scorecard_summary(
        arm_summaries=arms,
        n_prompts=n_prompts,
        max_tokens=max_tokens,
        spec_token_count=spec_tokens,
        b1_prefix_cache_exact=b1_exact,
        b1_prefix_cache_tested_items=b1_tested_items,
        p2b_scale=p2b_scale,
        safety_probe_results=safety_smoke,
        grading_paths_used=overall_gp,
    )
    cached_scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    cached_scorecard_path.write_text(
        json.dumps(refreshed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return refreshed


def run_full_pipeline(
    *,
    compile_root: Path = _DEFAULT_COMPILE_ROOT,
    repo_root: Path = _DEFAULT_REPO_ROOT,
    datasets_dir: Path | None = None,
    deps_dir: Path | None = None,
    checkpoints_dir: Path | None = None,
    activations_npz_override: Path | None = None,
    cached_eval_jsonl_dir: Path | None = None,
    skip_harvest_if_cached: bool = False,
    skip_eval: bool = False,
    reuse_cached_eval: bool = False,
    verify_b1_parity_live_on_cached: bool = True,
    output_gain: float = DEFAULT_OUTPUT_GAIN,
    p2b_eval_scale: float = 1.0,
) -> dict[str, Any]:
    resolved_datasets_dir = (
        Path(datasets_dir)
        if datasets_dir is not None
        else (repo_root / "datasets" if (repo_root / "datasets").is_dir() else repo_root.parent / "datasets")
    )
    resolved_deps_dir = (
        Path(deps_dir)
        if deps_dir is not None
        else (repo_root / "deps" if (repo_root / "deps").is_dir() else repo_root.parent / "deps")
    )
    resolved_ckpts = (
        Path(checkpoints_dir)
        if checkpoints_dir is not None
        else (
            compile_root / "checkpoints"
            if (compile_root / "checkpoints" / "Qwen3.5-4B").is_dir()
            else repo_root.parent / "compile" / "checkpoints"
        )
    )

    gguf_path = resolved_ckpts / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf"
    st_dir = resolved_ckpts / "Qwen3.5-4B"
    artifacts_dir = compile_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Phase 2 Hardware & Checkpoint Discovery
    hw_report_path = artifacts_dir / "phase2_hardware_checkpoint_report.json"
    hw_report = build_hardware_and_checkpoint_report(
        gguf_path=gguf_path,
        safetensors_dir=st_dir,
        output_path=hw_report_path,
    )
    llama_commit = hw_report["llama_server"].get("commit")
    if not isinstance(llama_commit, str) or not llama_commit.strip():
        raise RuntimeError(
            "Phase 2 llama-server probe returned commit=None; cannot attest AdapterBundle without parsed commit"
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

    # 3. Harvest or strictly verify cached `harvested_activations.npz` via `hmac.compare_digest`
    npz_path = (
        Path(activations_npz_override)
        if activations_npz_override is not None
        else (
            artifacts_dir / "harvested_activations.npz"
            if (artifacts_dir / "harvested_activations.npz").is_file()
            else repo_root.parent / "compile" / "artifacts" / "harvested_activations.npz"
        )
    )
    local_meta_sidecar = artifacts_dir / "harvested_activations.meta.json"
    if skip_harvest_if_cached and npz_path.is_file():
        meta_to_check = (
            local_meta_sidecar if local_meta_sidecar.is_file() else npz_path.with_suffix(".meta.json")
        )
        harvest_meta = verify_cached_activations_npz(npz_path, meta_to_check)
        if not local_meta_sidecar.is_file() and meta_to_check.is_file():
            local_meta_sidecar.write_bytes(meta_to_check.read_bytes())
    else:
        npz_path = artifacts_dir / "harvested_activations.npz"
        harvest_meta = harvest_all_activations(
            safetensors_dir=st_dir,
            compile_jsonl=resolved_datasets_dir / "compile.jsonl",
            hybrid_k0_jsonl=resolved_datasets_dir / "hybrid_k0.jsonl",
            output_npz=npz_path,
        )

    # 4. Compile Arm P2-B (Full weft BetaEdit rank-8 CPU float64 solve)
    p2b_dir = artifacts_dir / "p2b"
    p2b_res = compile_p2b_deterministic(
        safetensors_dir=st_dir,
        activations_npz=npz_path,
        plane1_root=repo_root,
        plane1_rel_files=plane1_rel_files,
        source_lineage=source_lineage,
        output_dir=p2b_dir,
        llama_server_commit=llama_commit,
        zone_manifest_id=zone_manifest_id,
        rank=DEFAULT_RANK,
        lambda_leakage=DEFAULT_LAMBDA_LEAKAGE,
        lambda_ridge=DEFAULT_LAMBDA_RIDGE,
        preservation_weight=DEFAULT_PRESERVATION_WEIGHT,
        output_gain=output_gain,
        gate_policy=PRE_REGISTERED_GATE_POLICY,
    )

    # 5. Subprocess CPU float64 9/9 re-derivation check (`0`-byte diff across all 9 P2-B outputs!)
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
            "--phase2-report",
            str(hw_report_path),
            "--llama-server-commit",
            llama_commit,
            "--output-gain",
            str(output_gain),
        ]
        env = {**os.environ, "PYTHONHASHSEED": "0"}
        rd_proc = subprocess.run(rd_cmd, capture_output=True, text=True, env=env, check=False)
        if rd_proc.returncode != 0:
            raise RuntimeError(
                f"Subprocess 9/9 0-byte re-derivation FAILED:\n{rd_proc.stdout}\n{rd_proc.stderr}"
            )
        rederive_receipt = json.loads(rd_proc.stdout)
        if not rederive_receipt.get("zero_byte_diff_all") or rederive_receipt.get("checked_file_count") != 9:
            raise RuntimeError(f"Incomplete re-derivation receipt: {rederive_receipt}")
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
        gate_policy=PRE_REGISTERED_GATE_POLICY,
    )

    # 7. Run all 3 Mandatory Ablations & Negative Controls + Fail-Closed Verification Receipt
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

    control_gate_receipt = verify_control_gates_fail_closed(
        repo_root=repo_root,
        p2b_res=p2b_res,
        p2a_res=p2a_res,
        controls_res=controls_res,
        source_lineage=source_lineage,
        zone_manifest_id=zone_manifest_id,
        controls_dir=controls_dir,
    )

    # 8. Compile Phase 6 Companion Packs (`corpus` + `weft-eido`) for `@stack`
    comp_dir = artifacts_dir / "composition"
    comp_packs = compile_phase6_companion_packs(
        proj_shared=p2b_res["projector"],
        safetensors_dir=st_dir,
        activations_npz=npz_path,
        p2b_result=p2b_res,
        plane1_corpus_doc=resolved_deps_dir / "mission" / "playbook" / "verified-bar.md",
        plane1_eido_doc=resolved_deps_dir / "weft-eido" / "README.md",
        source_lineage=source_lineage,
        output_dir=comp_dir,
        zone_manifest_id=zone_manifest_id,
    )
    (comp_dir / "composition_manifest.json").write_text(
        json.dumps(comp_packs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # 9. Live Evaluation of all arms on `validation.jsonl` (48 prompts, temp=0, top_p=1.0)
    cached_scorecard_path = artifacts_dir / "evaluation" / "validation_scorecard.json"
    resolved_eval_jsonl_dir = (
        Path(cached_eval_jsonl_dir)
        if cached_eval_jsonl_dir is not None
        else (
            artifacts_dir / "evaluation"
            if (artifacts_dir / "evaluation" / "validation_b0.jsonl").is_file()
            else repo_root.parent / "compile" / "artifacts" / "evaluation"
        )
    )
    eval_summary = None
    if reuse_cached_eval and cached_scorecard_path.is_file():
        eval_summary = _refresh_cached_eval_scorecard(
            cached_scorecard_path=cached_scorecard_path,
            cached_eval_jsonl_dir=resolved_eval_jsonl_dir,
            gguf_path=gguf_path,
            safetensors_dir=st_dir,
            validation_jsonl=resolved_datasets_dir / "validation.jsonl",
            plane1_spec_path=repo_root / "spec" / "plane1_formal_spec.md",
            llama_available=bool(hw_report["llama_server"].get("available", False)),
            verify_b1_parity_live=verify_b1_parity_live_on_cached,
        )
    elif not skip_eval:
        eval_summary = evaluate_all_arms_on_validation(
            gguf_path=gguf_path,
            safetensors_dir=st_dir,
            validation_jsonl=resolved_datasets_dir / "validation.jsonl",
            plane1_spec_path=repo_root / "spec" / "plane1_formal_spec.md",
            repo_root=repo_root,
            datasets_dir=resolved_datasets_dir,
            p2a_gguf=p2a_dir / "formal-verification.p2a.f16.gguf",
            p2b_gguf=p2b_dir / "formal-verification.p2b.f16.gguf",
            sabotage_gguf=controls_dir / "formal-verification.sabotage.f16.gguf",
            goodhart_gguf=controls_dir / "formal-verification.goodhart.f16.gguf",
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
        "gate_policy": asdict(PRE_REGISTERED_GATE_POLICY),
        "quantization_spec": {
            "gguf_lora": "f16",
            "slab_f16": {"quant_dtype": "f16", "b_quant_dtype": "f16", "a_quant_dtype": "f16"},
            "slab_int4_int8": {"quant_dtype": "f16", "b_quant_dtype": "int4", "a_quant_dtype": "int8"},
            "slab_int4_f16": {"quant_dtype": "f16", "b_quant_dtype": "int4", "a_quant_dtype": "f16"},
        },
        "lora_alpha": float(DEFAULT_RANK),
        "p2b_eval_scale": p2b_eval_scale,
    }

    validation_efficacy_headline = None
    if isinstance(eval_summary, dict):
        prev = eval_summary.get("phase5_preview_on_public_validation", {})
        validation_efficacy_headline = {
            "efficacy_verdict": eval_summary["efficacy_verdict"],
            "control_ordering_summary": eval_summary["control_ordering_summary"],
            "p2b_relative_failure_reduction_vs_b0": prev.get("p2b_relative_failure_reduction_vs_b0"),
            "p2b_ceiling_ratio_vs_b1": prev.get("p2b_ceiling_ratio_vs_b1"),
            "p2b_sop_tokens_injected": eval_summary["p2b_sop_tokens_injected"],
            "b1_sop_tokens_injected": eval_summary["b1_sop_tokens_injected"],
            "b1_prefix_cache_parity_verified": eval_summary["b1_prefix_cache_parity_verified"],
            "b1_prefix_cache_tested_items": eval_summary["b1_prefix_cache_tested_items"],
        }

    master_manifest = {
        "schema": "mcproof-phase2-phase3-manifest/v0.2",
        "phase2_report": "compile/artifacts/phase2_hardware_checkpoint_report.json",
        "compiler_hyperparameters": compiler_hyperparameters,
        "harvest_summary": {k: v for k, v in harvest_meta.items() if k != "step_metadata"},
        "p2b": p2b_res["artifacts"],
        "p2a": p2a_res,
        "rederivation_checked_files": rederive_receipt["checked_file_count"],
        "rederivation_zero_byte_diff": rederive_receipt["zero_byte_diff_all"],
        "loud_column_ablation_headline": loud_col_res["headline_ratios"],
        "constant_logit_bias_sha256": logit_bias_res["sha256"],
        "negative_controls": {
            "sabotage_gguf_sha256": controls_res["sabotage_patch"]["gguf_sha256"],
            "sabotage_norm_only_passes": controls_res["sabotage_patch"]["norm_only_gate_passes"],
            "sabotage_stage2_cert_passes": controls_res["sabotage_patch"]["stage2_certificate_passes"],
            "goodhart_gguf_sha256": controls_res["goodhart_patch"]["gguf_sha256"],
            "goodhart_stage2_cert_passes": controls_res["goodhart_patch"]["stage2_certificate_passes"],
            "goodhart_in_nullspace_stage2_admissible": True,
            "goodhart_rejection_boundary": "stage3_domain_canaries_and_phase5_holdout_not_stage2",
            "all_five_tamper_and_sabotage_controls_failed_closed": control_gate_receipt[
                "all_five_tamper_and_sabotage_controls_failed_closed"
            ],
            "control_gate_verification_receipt": "compile/artifacts/controls/control_gate_verification_receipt.json",
        },
        "phase6_composition_packs": {
            k: {
                "gguf_path": v["gguf_path"],
                "gguf_sha256": v["gguf_sha256"],
                "warp_bundle_path": v["warp_bundle_path"],
            }
            for k, v in comp_packs.items()
        },
        "validation_efficacy_headline": validation_efficacy_headline,
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
    ap.add_argument("--checkpoints-dir", type=Path, default=None)
    ap.add_argument("--activations-npz", type=Path, default=None)
    ap.add_argument("--datasets-dir", type=Path, default=None)
    ap.add_argument("--deps-dir", type=Path, default=None)
    ap.add_argument("--cached-eval-jsonl-dir", type=Path, default=None)
    ap.add_argument("--skip-harvest-if-cached", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--reuse-cached-eval", action="store_true")
    ap.add_argument("--no-live-b1-parity-on-cached", action="store_true")
    ap.add_argument("--output-gain", type=float, default=DEFAULT_OUTPUT_GAIN)
    ap.add_argument("--p2b-eval-scale", type=float, default=1.0)
    args = ap.parse_args()
    res = run_full_pipeline(
        checkpoints_dir=args.checkpoints_dir,
        activations_npz_override=args.activations_npz,
        datasets_dir=args.datasets_dir,
        deps_dir=args.deps_dir,
        cached_eval_jsonl_dir=args.cached_eval_jsonl_dir,
        skip_harvest_if_cached=args.skip_harvest_if_cached,
        skip_eval=args.skip_eval,
        reuse_cached_eval=args.reuse_cached_eval,
        verify_b1_parity_live_on_cached=not args.no_live_b1_parity_on_cached,
        output_gain=args.output_gain,
        p2b_eval_scale=args.p2b_eval_scale,
    )
    print(json.dumps(res, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
