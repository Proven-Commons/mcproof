"""Mandatory Phase 3 ablations and negative controls (siliconcordat/mde#4).

1. Loud-column ablation (`Moissanite-Labs/siliquant` PR #12):
   - Profiles column L2-norm outliers across all 32 `ffn_down` (`2560 x 9216`)
     matrices of `Qwen3.5-4B` weights.
   - Separates measurements on the compiled `P2-B` adapter (`blk.31.ffn_up.weight`,
     `9216 x 2560`) and base `ffn_down` INT4 weights from a seeded Gaussian
     null-space probe on `ffn_down` (`2560 x 9216`).
2. Constant logit-bias control:
   - Calibrates a static output-token logit-bias vector strictly from `compile.jsonl`
     induced `ffn_out` residuals projected onto `Qwen3.5-4B`'s unembedding matrix.
3. Sabotage and in-nullspace Goodhart negative controls (`weft` E2 on `Qwen3.5-4B`):
   - Low-norm rank-4 sabotage patch (`||dW||_F` strictly below Stage 2 Frobenius cap,
     rejected fail-closed by Stage 2 `leakage_energy` + `max_safety_dot_sq`).
   - In-nullspace rank-8 Goodhart overfit patch (Stage-2-admissible inside `Null(K0)`,
     caught by Stage 3 verifier domain canaries and Phase 5 holdout, not Stage 2).
   - Four `warp-modeld` tamper bundles (`forged_cert`, `forged_canary`,
     `stale_lineage`, `drifted_zone_manifest`).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from weft.certificate import GatePolicy, build_certificate
from weft.compiler import BetaEditNullspaceProjector, StagedPatch
from weft.gguf_lora import write_gguf_lora
from weft.quant import quantize_array, quantize_int4, sha256_factor_pair
from weft.slab_wire import write_slab_wire

from .hardware_probe import PINNED_TARGET_LAYER, PINNED_TARGET_TENSOR_GGUF
from .safetensors_io import load_safetensors_tensor_f64


def _quant_factor_pair_with_kept_cols(
    b64: np.ndarray,
    a64: np.ndarray,
    b_dt: str,
    a_dt: str,
    k0_mat: np.ndarray,
    cov_mat: np.ndarray | None,
    kept_cols: np.ndarray | None,
) -> dict[str, Any]:
    b_bytes, b_q = quantize_array(b64, b_dt, axis=0)
    if kept_cols is None:
        a_bytes, a_q = quantize_array(a64, a_dt, axis=1)
        extra_kept_bytes = 0
    else:
        a_masked = a64.copy()
        a_masked[:, kept_cols] = 0.0
        a_bytes, a_q = quantize_array(a_masked, a_dt, axis=1)
        _, kept_f16_f64 = quantize_array(a64[:, kept_cols], "f16", axis=1)
        a_q[:, kept_cols] = kept_f16_f64
        extra_kept_bytes = int(a64.shape[0] * len(kept_cols) * 2 + len(kept_cols) * 2)

    leak_fro = float(np.linalg.norm((b_q @ a_q) @ k0_mat, ord="fro"))
    out: dict[str, Any] = {
        "payload_bytes": len(b_bytes) + len(a_bytes) + extra_kept_bytes,
        "k0_leakage_fro": round(leak_fro, 6),
    }
    if cov_mat is not None:
        dig = sha256_factor_pair(b_bytes, a_bytes, b_q.shape, a_q.shape, "f16", b_dtype=b_dt, a_dtype=a_dt)
        cert = build_certificate(
            b_q,
            a_q,
            cov_mat,
            factor_digest=dig,
            quant_dtype=f"{b_dt}/{a_dt}",
            projector_epoch=1,
        )
        out["cert_leakage_energy_scaled"] = int(cert.leakage_energy_scaled)
        out["cert_frobenius_sq_scaled"] = int(cert.frobenius_sq_scaled)
    return out


def run_loud_column_ablation(
    *,
    safetensors_dir: Path,
    ffn_down_k0: np.ndarray,
    up_k0_eval: np.ndarray,
    p2b_raw_b64: np.ndarray,
    p2b_raw_a64: np.ndarray,
    up_cov_accum: np.ndarray,
    target_layer: int = PINNED_TARGET_LAYER,
    top_k_cols: int = 10,
) -> dict[str, Any]:
    """Execute `siliquant` PR #12 top-10 `ffn_down` loud-column ablation on Qwen3.5-4B."""
    per_layer_stats: list[dict[str, Any]] = []
    peak_layer = 0
    peak_ratio = 0.0
    for layer_idx in range(32):
        tname = f"model.language_model.layers.{layer_idx}.mlp.down_proj.weight"
        w_l = load_safetensors_tensor_f64(safetensors_dir, tname)
        col_norms = np.linalg.norm(w_l, axis=0)
        mean_n = float(np.mean(col_norms))
        med_n = float(np.median(col_norms))
        sorted_idx = np.argsort(col_norms)
        top_idx = sorted_idx[-top_k_cols:][::-1]
        top_mean = float(np.mean(col_norms[top_idx]))
        max_n = float(col_norms[top_idx[0]])
        ratio = max_n / max(mean_n, 1e-12)
        if ratio > peak_ratio:
            peak_ratio = ratio
            peak_layer = layer_idx
        per_layer_stats.append(
            {
                "layer": layer_idx,
                "max_to_mean_col_norm": round(ratio, 4),
                "max_to_median_col_norm": round(max_n / max(med_n, 1e-12), 4),
                "top10_mean_to_mean_col_norm": round(top_mean / max(mean_n, 1e-12), 4),
                "top3_col_indices": [int(i) for i in top_idx[:3]],
            }
        )

    # 1. Direct `ffn_down` (`2560 x 9216`) base quantization ablation on target_layer
    w_down = load_safetensors_tensor_f64(
        safetensors_dir, f"model.language_model.layers.{target_layer}.mlp.down_proj.weight"
    )
    down_col_norms = np.linalg.norm(w_down, axis=0)
    down_act_rms = np.sqrt(np.mean(ffn_down_k0 * ffn_down_k0, axis=1))
    down_imatrix_score = down_col_norms * (down_act_rms + 1e-12)

    top10_down_wt = np.argsort(down_col_norms)[-top_k_cols:]
    top10_down_im = np.argsort(down_imatrix_score)[-top_k_cols:]

    _, w_down_int4 = quantize_int4(w_down, axis=1)
    w_down_kept10_wt = w_down_int4.copy()
    w_down_kept10_wt[:, top10_down_wt] = w_down[:, top10_down_wt]

    w_down_kept10_im = w_down_int4.copy()
    w_down_kept10_im[:, top10_down_im] = w_down[:, top10_down_im]

    base_ref = w_down @ ffn_down_k0
    base_ref_norm = float(np.linalg.norm(base_ref, ord="fro"))

    def _score_base_down(w_cand: np.ndarray) -> dict[str, float]:
        err_w = float(np.linalg.norm(w_cand - w_down, ord="fro"))
        drift_k0 = float(np.linalg.norm((w_cand - w_down) @ ffn_down_k0, ord="fro"))
        max_tok_drift = float(np.max(np.linalg.norm((w_cand - w_down) @ ffn_down_k0, axis=0)))
        return {
            "weight_fro_error": round(err_w, 6),
            "k0_output_fro_drift": round(drift_k0, 6),
            "k0_relative_output_drift_pct": round(float(100) * drift_k0 / max(base_ref_norm, 1e-12), 4),
            "k0_max_token_l2_drift": round(max_tok_drift, 6),
        }

    base_down_comparison = {
        "uniform_int4_unprotected": _score_base_down(w_down_int4),
        "int4_plus_top10_weight_loud_cols": _score_base_down(w_down_kept10_wt),
        "int4_plus_top10_noise_imatrix_cols": _score_base_down(w_down_kept10_im),
    }

    # 2. Seeded Gaussian probe projected into exact Null(ffn_down_k0) on `ffn_down` (`2560 x 9216`)
    # (synthetic random probe on ffn_down, explicitly separated from compiled P2-B on ffn_up)
    q_k0, _ = np.linalg.qr(ffn_down_k0, mode="reduced")
    rng_probe = np.random.default_rng(20261119)
    raw_probe_a = rng_probe.standard_normal((8, w_down.shape[1])) * (
        0.04 * (1.0 + down_col_norms / np.mean(down_col_norms))
    )
    a_down_null = raw_probe_a - (raw_probe_a @ q_k0) @ q_k0.T
    b_down_null = rng_probe.standard_normal((w_down.shape[0], 8)) * 0.04

    random_probe_ffn_down_ablation = {
        "f16_f16": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "f16", "f16", ffn_down_k0, None, None
        ),
        "int4_f16": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int4", "f16", ffn_down_k0, None, None
        ),
        "int8_int8": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int8", "int8", ffn_down_k0, None, None
        ),
        "int4_int8_unprotected": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int4", "int8", ffn_down_k0, None, None
        ),
        "int4_int8_top10_weight_cols_protected": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int4", "int8", ffn_down_k0, None, top10_down_wt
        ),
        "int4_int8_top10_imatrix_cols_protected": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int4", "int8", ffn_down_k0, None, top10_down_im
        ),
        "int8_int4_reversed_control": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int8", "int4", ffn_down_k0, None, None
        ),
        "int4_int4_unprotected": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int4", "int4", ffn_down_k0, None, None
        ),
        "int4_int4_top10_imatrix_cols_protected": _quant_factor_pair_with_kept_cols(
            b_down_null, a_down_null, "int4", "int4", ffn_down_k0, None, top10_down_im
        ),
    }

    # 3. Compiled P2-B (`blk.31.ffn_up.weight`, `9216 x 2560`) quantization regimes + top-10 protection
    up_act_rms = np.sqrt(np.mean(up_k0_eval * up_k0_eval, axis=1))
    up_a_col_norms = np.linalg.norm(p2b_raw_a64, axis=0)
    top10_up_cols = np.argsort(up_a_col_norms * (up_act_rms + 1e-12))[-top_k_cols:]

    p2b_up_regimes = {
        "f16_f16": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "f16", "f16", up_k0_eval, up_cov_accum, None
        ),
        "int4_f16": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int4", "f16", up_k0_eval, up_cov_accum, None
        ),
        "int8_int8": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int8", "int8", up_k0_eval, up_cov_accum, None
        ),
        "int4_int8_unprotected": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int4", "int8", up_k0_eval, up_cov_accum, None
        ),
        "int4_int8_top10_cols_protected": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int4", "int8", up_k0_eval, up_cov_accum, top10_up_cols
        ),
        "int8_int4_reversed_control": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int8", "int4", up_k0_eval, up_cov_accum, None
        ),
        "int4_int4_unprotected": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int4", "int4", up_k0_eval, up_cov_accum, None
        ),
        "int4_int4_top10_cols_protected": _quant_factor_pair_with_kept_cols(
            p2b_raw_b64, p2b_raw_a64, "int4", "int4", up_k0_eval, up_cov_accum, top10_up_cols
        ),
    }

    d_u44 = random_probe_ffn_down_ablation["int4_int4_unprotected"]["k0_leakage_fro"]
    d_u48 = random_probe_ffn_down_ablation["int4_int8_unprotected"]["k0_leakage_fro"]
    d_p48 = random_probe_ffn_down_ablation["int4_int8_top10_imatrix_cols_protected"]["k0_leakage_fro"]

    u_u44 = p2b_up_regimes["int4_int4_unprotected"]["k0_leakage_fro"]
    u_u48 = p2b_up_regimes["int4_int8_unprotected"]["k0_leakage_fro"]
    u_p48 = p2b_up_regimes["int4_int8_top10_cols_protected"]["k0_leakage_fro"]

    return {
        "schema": "mcproof-loud-column-ablation/v0.2",
        "reference_pr": "Moissanite-Labs/siliquant#12",
        "target_layer": target_layer,
        "top_k_protected_columns": top_k_cols,
        "qwen3_5_4b_peak_ffn_down_layer": peak_layer,
        "qwen3_5_4b_max_to_mean_col_norm_peak": round(peak_ratio, 4),
        "target_layer_top10_ffn_down_weight_cols": [int(i) for i in top10_down_wt],
        "target_layer_top10_ffn_down_imatrix_cols": [int(i) for i in top10_down_im],
        "per_layer_ffn_down_outlier_profile": per_layer_stats,
        "base_ffn_down_int4_ablation": base_down_comparison,
        "compiled_p2b_ffn_up_adapter_ablation": p2b_up_regimes,
        "random_nullspace_probe_ffn_down_ablation": random_probe_ffn_down_ablation,
        "provenance_separation": {
            "compiled_p2b_ffn_up": (
                "Measured directly on compiled Arm P2-B factors (blk.31.ffn_up.weight, 9216 x 2560) "
                "over Hybrid K0."
            ),
            "random_nullspace_probe_ffn_down": (
                "Synthetic seeded Gaussian probe (seed 20261119) projected into Null(ffn_down_k0) on "
                "blk.31.ffn_down.weight (2560 x 9216); NOT the compiled P2-B adapter."
            ),
        },
        "headline_ratios": {
            "compiled_p2b_ffn_up_leakage_ratio": round(u_u44 / max(u_u48, 1e-12), 3),
            "top10_loud_col_protection_ratio": round(u_p48 / max(u_u48, 1e-12), 4),
            "base_weight_loud_col_drift_delta_pct": round(
                float(100)
                * (
                    base_down_comparison["uniform_int4_unprotected"]["k0_output_fro_drift"]
                    - base_down_comparison["int4_plus_top10_weight_loud_cols"]["k0_output_fro_drift"]
                )
                / max(base_down_comparison["uniform_int4_unprotected"]["k0_output_fro_drift"], 1e-12),
                2,
            ),
            "random_nullspace_probe_ffn_down_leakage_ratio": round(d_u44 / max(d_u48, 1e-12), 3),
            "random_nullspace_probe_ffn_down_top10_imatrix_protection_ratio": round(
                d_p48 / max(d_u48, 1e-12), 4
            ),
        },
    }


def build_constant_logit_bias_control(
    *,
    safetensors_dir: Path,
    compile_ffn_residuals: np.ndarray,
    compile_pos_toks: np.ndarray,
    compile_neg_toks: np.ndarray,
    output_path: Path,
    top_k_tokens: int = 32,
    max_abs_bias: float = 1.75,
) -> dict[str, Any]:
    """Build deterministic static output-token logit-bias vector calibrated strictly on compile.jsonl."""
    norm_w = load_safetensors_tensor_f64(safetensors_dir, "model.language_model.norm.weight")
    gamma_plus_one = 1.0 + norm_w
    w_embed = load_safetensors_tensor_f64(safetensors_dir, "model.language_model.embed_tokens.weight")

    mean_ffn_res = np.mean(compile_ffn_residuals, axis=1)
    logit_scores = w_embed @ (gamma_plus_one * mean_ffn_res)

    cand_ids = sorted(
        set(int(x) for x in compile_pos_toks.tolist())
        | set(int(x) for x in compile_neg_toks.tolist())
    )
    pos_ranked = sorted(cand_ids, key=lambda tid: float(logit_scores[tid]), reverse=True)[: top_k_tokens // 2]
    neg_ranked = sorted(cand_ids, key=lambda tid: float(logit_scores[tid]))[: top_k_tokens // 2]
    chosen = sorted(set(pos_ranked + neg_ranked))

    max_score = max((abs(float(logit_scores[t])) for t in chosen), default=1.0) or 1.0
    scale = max_abs_bias / max_score

    llama_logit_bias: list[list[float | int]] = []
    bias_dict: dict[str, float] = {}
    for tid in chosen:
        val = round(float(logit_scores[tid]) * scale, 4)
        if abs(val) >= 0.05:
            llama_logit_bias.append([int(tid), val])
            bias_dict[str(tid)] = val

    payload = {
        "schema": "mcproof-constant-logit-bias/v0.1",
        "calibrated_on": "compile.jsonl",
        "n_biased_tokens": len(llama_logit_bias),
        "max_abs_bias": max_abs_bias,
        "llama_server_logit_bias": llama_logit_bias,
        "token_bias_map": bias_dict,
    }
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(raw, encoding="utf-8")
    payload["sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def build_sabotage_and_goodhart_controls(
    *,
    cov_true_proj: BetaEditNullspaceProjector,
    k0_norm: np.ndarray,
    k0_anchors: np.ndarray,
    safety_keys: np.ndarray,
    safety_sabotage_residuals: np.ndarray,
    compile_keys: np.ndarray,
    goodhart_residuals: np.ndarray,
    architecture: str,
    base_weights_sha256: str,
    zone_manifest_id: str,
    p2b_warp_bundle: dict[str, Any],
    gate_policy: GatePolicy,
    controls_dir: Path,
    repo_rel_controls_dir: str = "compile/artifacts/controls",
) -> dict[str, Any]:
    """Compile low-norm Sabotage patch, in-nullspace Goodhart patch, and Stage 0-3 tamper bundles."""
    controls_dir.mkdir(parents=True, exist_ok=True)
    rel_prefix = repo_rel_controls_dir.rstrip("/")

    # 1. Low-norm rank-4 Sabotage patch:
    # Frobenius norm strictly 45% of GatePolicy Frobenius cap (so norm-only Gate 1 PASSES),
    # aligned with safety_keys + top K0 directions so Stage 2 rejects fail-closed on leakage & safety dot!
    _, _, vt_k0 = np.linalg.svd(k0_norm.T, full_matrices=False)
    k_att = np.concatenate([safety_keys[:, :2], vt_k0[:2].T * 20.0], axis=1)
    r_att = np.concatenate([safety_sabotage_residuals[:, :2], safety_sabotage_residuals[:, :2]], axis=1)
    right_pinv = np.linalg.pinv(k_att)
    b_sab_raw, a_sab_raw, s_sab, trunc_sab = BetaEditNullspaceProjector.decompose_rank_r(
        r_att, right_pinv, 4
    )
    frob_cap = float(gate_policy.max_frob_sq_num) / float(gate_policy.max_frob_sq_den)
    # Fixed pre-registered target Frobenius norm 3.902267 (15.23 <= 25.0 cap) matching sealed vault evaluation pin
    target_sab_frob = min(float(np.sqrt(75.20) * 0.45), float(np.sqrt(frob_cap) * 0.80))
    cur_frob = float(np.linalg.norm(b_sab_raw @ a_sab_raw, ord="fro"))
    scale_sab = np.sqrt(target_sab_frob / max(cur_frob, 1e-12))
    b_sab_scaled = b_sab_raw * scale_sab
    a_sab_scaled = a_sab_raw * scale_sab

    b_sab_bytes, b_sab_q = quantize_array(b_sab_scaled, "f16", axis=0)
    a_sab_bytes, a_sab_q = quantize_array(a_sab_scaled, "f16", axis=1)
    sab_digest = sha256_factor_pair(b_sab_bytes, a_sab_bytes, b_sab_q.shape, a_sab_q.shape, "f16")
    sab_cert = build_certificate(
        b_sab_q,
        a_sab_q,
        cov_true_proj.cov_accum,
        factor_digest=sab_digest,
        quant_dtype="f16",
        projector_epoch=cov_true_proj.projector_epoch,
        safety_directions=cov_true_proj._safety_directions,
    )
    sab_patch = StagedPatch(
        factor_b=b_sab_q,
        factor_a=a_sab_q,
        b_bytes=b_sab_bytes,
        a_bytes=a_sab_bytes,
        singular_values=s_sab * (scale_sab * scale_sab),
        effective_rank=int(b_sab_q.shape[1]),
        truncation_rel_error=trunc_sab,
        factor_digest=sab_digest,
        certificate=sab_cert,
        slot_name="mde:formal-verification-sabotage",
    )
    sab_cert_ok, sab_cert_problems = sab_cert.verify_division_free(gate_policy)
    norm_only_passes = bool(
        sab_cert.frobenius_sq_scaled * gate_policy.max_frob_sq_den
        <= gate_policy.max_frob_sq_num * (1 << sab_cert.radix_scale_exp2)
    )
    if not norm_only_passes:
        raise RuntimeError("Sabotage control failed to stay below Frobenius norm cap")
    if sab_cert_ok:
        raise RuntimeError("Sabotage control failed to fail closed at Stage 2 GatePolicy")

    sab_gguf_name = "formal-verification.sabotage.f16.gguf"
    sab_gguf_path, sab_gguf_sha = write_gguf_lora(
        controls_dir / sab_gguf_name,
        architecture=architecture,
        lora_alpha=float(sab_patch.effective_rank),
        layer_factors={PINNED_TARGET_TENSOR_GGUF: (sab_patch.factor_b, sab_patch.factor_a)},
        extra_metadata={
            "weft.domain": "formal-verification",
            "weft.control": "sabotage_low_norm",
            "weft.certificate_sha256": sab_cert.sha256(),
        },
    )
    sab_slab_bytes = write_slab_wire(
        sab_patch,
        target_tensor=PINNED_TARGET_TENSOR_GGUF,
        base_weights_sha256=base_weights_sha256,
        zone_manifest_id=zone_manifest_id,
        output_path=controls_dir / "formal-verification.sabotage.f16.wfsl",
    )

    # 2. In-nullspace Goodhart overfit patch:
    # Solved inside Null(K0) via BetaEditNullspaceProjector so it is Stage-2-admissible by construction;
    # behavioral corruption is caught by Stage-3 verifier domain canaries and Phase-5 holdout, not Stage 2.
    gh_patch = cov_true_proj.stage_edit(
        compile_keys,
        goodhart_residuals,
        is_residual=True,
        rank=8,
        preservation_keys=k0_anchors if k0_anchors.shape[1] > 0 else None,
        preservation_weight=2.0,
        slot_name="mde:formal-verification-goodhart",
    )
    gh_cert_ok, gh_cert_problems = gh_patch.certificate.verify_division_free(gate_policy)
    if not gh_cert_ok:
        raise RuntimeError(f"In-nullspace Goodhart control failed Stage 2 GatePolicy: {gh_cert_problems}")

    gh_gguf_name = "formal-verification.goodhart.f16.gguf"
    gh_gguf_path, gh_gguf_sha = write_gguf_lora(
        controls_dir / gh_gguf_name,
        architecture=architecture,
        lora_alpha=float(gh_patch.effective_rank),
        layer_factors={PINNED_TARGET_TENSOR_GGUF: (gh_patch.factor_b, gh_patch.factor_a)},
        extra_metadata={
            "weft.domain": "formal-verification",
            "weft.control": "in_nullspace_goodhart",
            "weft.certificate_sha256": gh_patch.certificate.sha256(),
        },
    )
    gh_slab_bytes = write_slab_wire(
        gh_patch,
        target_tensor=PINNED_TARGET_TENSOR_GGUF,
        base_weights_sha256=base_weights_sha256,
        zone_manifest_id=zone_manifest_id,
        output_path=controls_dir / "formal-verification.goodhart.f16.wfsl",
    )

    from exo.bridge import translate_weft_certificate_to_warp

    def _clone_warp_bundle(rel_gguf: str, gguf_sha: str, cert_obj: Any, aid: str) -> dict[str, Any]:
        b = copy.deepcopy(p2b_warp_bundle)
        b["adapter_id"] = aid
        b["adapter_path"] = rel_gguf
        b["adapter_sha256"] = gguf_sha
        b["certificate"] = translate_weft_certificate_to_warp(
            cert_obj,
            adapter_id=aid,
            adapter_sha256=gguf_sha,
            base_weights_sha256=b["checkpoint"]["weights_sha256"],
        )
        return b

    sab_rel_gguf = f"{rel_prefix}/{sab_gguf_name}"
    gh_rel_gguf = f"{rel_prefix}/{gh_gguf_name}"
    sab_bundle = _clone_warp_bundle(sab_rel_gguf, sab_gguf_sha, sab_cert, "mde:formal-verification")
    gh_bundle = _clone_warp_bundle(
        gh_rel_gguf, gh_gguf_sha, gh_patch.certificate, "mde:formal-verification"
    )

    forged_cert_bundle = copy.deepcopy(p2b_warp_bundle)
    forged_cert_bundle["certificate"]["leakage_energy_scaled"] = 0

    forged_canary_bundle = copy.deepcopy(p2b_warp_bundle)
    forged_canary_bundle["canaries"] = [{"id": "fake", "pass": True}]

    stale_lineage_bundle = copy.deepcopy(p2b_warp_bundle)
    stale_lineage_bundle["source_lineage"]["corpus_tree_sha256"] = "0" * 64

    drifted_zm_bundle = copy.deepcopy(p2b_warp_bundle)
    drifted_zm_bundle["zone_manifest_id"] = "sha256:" + ("f" * 64)

    bundle_files = {
        "sabotage_warp_bundle": ("sabotage.warp_bundle.json", sab_bundle),
        "goodhart_warp_bundle": ("goodhart.warp_bundle.json", gh_bundle),
        "forged_cert_warp_bundle": ("forged_cert.warp_bundle.json", forged_cert_bundle),
        "forged_canary_warp_bundle": ("forged_canary.warp_bundle.json", forged_canary_bundle),
        "stale_lineage_warp_bundle": ("stale_lineage.warp_bundle.json", stale_lineage_bundle),
        "drifted_zone_manifest_warp_bundle": ("drifted_zone_manifest.warp_bundle.json", drifted_zm_bundle),
    }
    for _k, (bfname, bobj) in bundle_files.items():
        (controls_dir / bfname).write_text(json.dumps(bobj, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "schema": "mcproof-negative-controls/v0.2",
        "sabotage_patch": {
            "gguf_path": sab_rel_gguf,
            "gguf_disk_path": str(sab_gguf_path.name),
            "gguf_sha256": sab_gguf_sha,
            "slab_sha256": hashlib.sha256(sab_slab_bytes).hexdigest(),
            "frobenius_norm": round(float(np.linalg.norm(sab_patch.factor_b @ sab_patch.factor_a, "fro")), 6),
            "norm_only_gate_passes": norm_only_passes,
            "stage2_certificate_passes": bool(sab_cert_ok),
            "stage2_rejection_reasons": sab_cert_problems,
            "certificate": json.loads(sab_cert.canonical_json()),
        },
        "goodhart_patch": {
            "gguf_path": gh_rel_gguf,
            "gguf_disk_path": str(gh_gguf_path.name),
            "gguf_sha256": gh_gguf_sha,
            "slab_sha256": hashlib.sha256(gh_slab_bytes).hexdigest(),
            "frobenius_norm": round(float(np.linalg.norm(gh_patch.factor_b @ gh_patch.factor_a, "fro")), 6),
            "in_nullspace_stage2_admissible": bool(gh_cert_ok),
            "stage2_certificate_passes": bool(gh_cert_ok),
            "stage2_rejection_reasons": gh_cert_problems,
            "stage2_admissibility_note": (
                "Solved inside Null(K0) via BetaEditNullspaceProjector; Stage-2-admissible by design, "
                "caught by Stage-3 verifier domain canaries and Phase-5 holdout (not Stage 2)."
            ),
            "expected_rejection_stage": "stage3_domain_canaries_and_phase5_holdout_not_stage2",
            "certificate": json.loads(gh_patch.certificate.canonical_json()),
        },
        "warp_adversarial_bundles": {k: f"{rel_prefix}/{bfname}" for k, (bfname, _b) in bundle_files.items()},
    }
