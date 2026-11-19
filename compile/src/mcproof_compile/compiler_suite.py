"""Phase 3 deterministic CPU float64 compilation suite (`P2-B`, `P2-A`, Phase 6 packs, and controls)."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from exo.bridge import build_warp_adapter_bundle
from warp_modeld.fingerprint import RuntimeFlags as WarpRuntimeFlags
from weft.binding import (
    ADAPTER_CLASS_1,
    RuntimeFlags as WeftRuntimeFlags,
    build_binding_manifest,
    verify_binding,
)
from weft.certificate import GatePolicy, build_certificate
from weft.compiler import BetaEditConfig, BetaEditNullspaceProjector, StagedPatch
from weft.gguf_lora import read_gguf_lora, write_gguf_lora
from weft.quant import quantize_array, sha256_factor_pair
from weft.slab_wire import verify_slab_wire, write_slab_wire

from .hardware_probe import (
    PINNED_MODEL_ID,
    PINNED_TARGET_LAYER,
    PINNED_TARGET_TENSOR_GGUF,
    PINNED_TARGET_TENSOR_ST,
    PINNED_ZONE_MANIFEST_ID,
)
from .safetensors_io import load_safetensors_tensor_f64

DEFAULT_LAMBDA_LEAKAGE = 250.0
DEFAULT_LAMBDA_RIDGE = 4.0
DEFAULT_RANK = 8
DEFAULT_PRESERVATION_WEIGHT = 2.0
DEFAULT_OUTPUT_GAIN = 1.65

# Fixed pre-registered integer GatePolicy caps (not calibrated from the candidate patch):
#   max ||dW||_F^2     <= 2500 / 100    = 25.0
#   max ||dW||_2^2     <= 1600 / 100    = 16.0
#   max leakage_energy <= 45000 / 1000  = 45.0
#   max safety_dot^2   <= 1 / 10000     = 1e-4
PRE_REGISTERED_GATE_POLICY = GatePolicy(
    max_frob_sq_num=2500,
    max_frob_sq_den=100,
    max_spectral_sq_num=1600,
    max_spectral_sq_den=100,
    max_leakage_num=45000,
    max_leakage_den=1000,
    max_safety_dot_sq_num=1,
    max_safety_dot_sq_den=10000,
)


def detect_checkpoint_state_bank_flags(safetensors_dir: Path) -> dict[str, Any]:
    """Derive SSM/linear-attention recurrent state-bank flags from checkpoint `config.json`."""
    cfg_path = Path(safetensors_dir) / "config.json"
    cfg_json: dict[str, Any] = {}
    if cfg_path.is_file():
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            cfg_json = loaded
    text_cfg = cfg_json.get("text_config") if isinstance(cfg_json.get("text_config"), dict) else {}
    raw_layers = cfg_json.get("layer_types")
    if not isinstance(raw_layers, list):
        raw_layers = text_cfg.get("layer_types") if isinstance(text_cfg.get("layer_types"), list) else []
    has_ssm_recurrent = bool("linear_attention" in raw_layers)
    return {
        "has_ssm_recurrent": has_ssm_recurrent,
        "has_horizontal_lattice": False,
        "lattice_layers": 0,
        "lattice_width": 0,
    }


def _quantize_raw_factors_as_patch(
    b64: np.ndarray,
    a64: np.ndarray,
    s_vals: np.ndarray,
    trunc_err: float,
    *,
    b_dtype: str,
    a_dtype: str,
    cov_accum: np.ndarray,
    projector_epoch: int,
    radix_scale_exp2: int,
    safety_directions: list[tuple[np.ndarray, np.ndarray]],
    slot_name: str,
) -> StagedPatch:
    b_bytes, b_q = quantize_array(b64, b_dtype, axis=0)
    a_bytes, a_q = quantize_array(a64, a_dtype, axis=1)
    q_label = b_dtype if b_dtype == a_dtype else f"{b_dtype}/{a_dtype}"
    digest = sha256_factor_pair(
        b_bytes,
        a_bytes,
        (int(b_q.shape[0]), int(b_q.shape[1])),
        (int(a_q.shape[0]), int(a_q.shape[1])),
        "f16",
        b_dtype=b_dtype,
        a_dtype=a_dtype,
    )
    cert = build_certificate(
        b_q,
        a_q,
        cov_accum,
        factor_digest=digest,
        quant_dtype=q_label,
        projector_epoch=projector_epoch,
        radix_scale_exp2=radix_scale_exp2,
        safety_directions=safety_directions,
    )
    return StagedPatch(
        factor_b=b_q,
        factor_a=a_q,
        b_bytes=b_bytes,
        a_bytes=a_bytes,
        singular_values=s_vals,
        effective_rank=int(b_q.shape[1]),
        truncation_rel_error=trunc_err,
        factor_digest=digest,
        certificate=cert,
        slot_name=slot_name,
    )


def _extract_raw_betaedit_factors(
    proj: BetaEditNullspaceProjector,
    keys: np.ndarray,
    residuals: np.ndarray,
    *,
    rank: int,
    preservation_keys: np.ndarray | None,
    preservation_weight: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Run exact BetaEdit subspace solve returning pre-quantization float64 (B, A, s_vals, trunc_err)."""
    k64 = np.ascontiguousarray(keys, dtype=np.float64)
    r64 = np.ascontiguousarray(residuals, dtype=np.float64)
    if preservation_keys is not None and preservation_keys.size > 0:
        pk = np.ascontiguousarray(preservation_keys, dtype=np.float64)
        w_sqrt = float(np.sqrt(max(0.0, preservation_weight)))
        k_solve = np.concatenate([k64, pk * w_sqrt], axis=1)
        r_solve = np.concatenate(
            [r64, np.zeros((proj.config.d_out, pk.shape[1]), dtype=np.float64)], axis=1
        )
    else:
        k_solve = k64
        r_solve = r64

    k_proj = proj.u_small.T @ k_solve
    m_dim = proj.u_small.shape[1]
    spd = (
        proj.config.lambda_ridge * np.eye(m_dim, dtype=np.float64)
        + proj._cached_u_cov_u
        + (k_proj @ k_proj.T)
    )
    spd = 0.5 * (spd + spd.T)
    chol = np.linalg.cholesky(spd)
    y_tmp = np.linalg.solve(chol, k_proj)
    solved = np.linalg.solve(chol.T, y_tmp)
    right64 = (proj.u_small @ solved).T
    return proj.decompose_rank_r(r_solve, right64, rank)


def build_safety_directions_from_npz(data: Any) -> list[tuple[np.ndarray, np.ndarray]]:
    safety_keys = np.ascontiguousarray(data["safety_keys"], dtype=np.float64)
    safety_sab_res = np.ascontiguousarray(data["safety_sabotage_residuals"], dtype=np.float64)
    dirs: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(min(4, safety_keys.shape[1])):
        b_s = -safety_sab_res[:, i : i + 1]
        a_s = safety_keys[:, i : i + 1].T
        if float(np.linalg.norm(b_s)) > 1e-9 and float(np.linalg.norm(a_s)) > 1e-9:
            dirs.append((b_s, a_s))
    return dirs


def compile_p2b_deterministic(
    *,
    safetensors_dir: Path,
    activations_npz: Path,
    plane1_root: Path,
    plane1_rel_files: list[str],
    source_lineage: dict[str, Any],
    output_dir: Path,
    llama_server_commit: str | None = None,
    zone_manifest_id: str = PINNED_ZONE_MANIFEST_ID,
    rank: int = DEFAULT_RANK,
    lambda_leakage: float = DEFAULT_LAMBDA_LEAKAGE,
    lambda_ridge: float = DEFAULT_LAMBDA_RIDGE,
    preservation_weight: float = DEFAULT_PRESERVATION_WEIGHT,
    output_gain: float = DEFAULT_OUTPUT_GAIN,
    gate_policy: GatePolicy = PRE_REGISTERED_GATE_POLICY,
    repo_rel_p2b_dir: str = "compile/artifacts/p2b",
) -> dict[str, Any]:
    """Deterministic CPU float64 compilation of Arm P2-B (weft BetaEdit rank <= 8)."""
    if not isinstance(llama_server_commit, str) or not llama_server_commit.strip():
        raise RuntimeError(
            "Cannot attest warp AdapterBundle without a verified non-empty llama_server_commit"
        )
    commit_clean = llama_server_commit.strip()
    rel_p2b_prefix = repo_rel_p2b_dir.rstrip("/")

    output_dir.mkdir(parents=True, exist_ok=True)
    w0_down = load_safetensors_tensor_f64(safetensors_dir, PINNED_TARGET_TENSOR_ST)
    d_out, d_in = w0_down.shape

    npz_sha256 = hashlib.sha256(activations_npz.read_bytes()).hexdigest()
    data = np.load(activations_npz)
    k0_noise = np.ascontiguousarray(data["k0_noise"], dtype=np.float64)
    k0_anchors = np.ascontiguousarray(data["k0_anchors"], dtype=np.float64)
    compile_keys = np.ascontiguousarray(data["compile_keys"], dtype=np.float64)
    compile_residuals = np.ascontiguousarray(data["compile_residuals"], dtype=np.float64) * float(output_gain)
    meta_sidecar = activations_npz.with_suffix(".meta.json")
    meta_sha256: str | None = None
    rel_step0_weight = 1.0
    if meta_sidecar.is_file():
        meta_bytes = meta_sidecar.read_bytes()
        meta_sha256 = hashlib.sha256(meta_bytes).hexdigest()
        meta_obj = json.loads(meta_bytes.decode("utf-8"))
        if isinstance(meta_obj, dict) and isinstance(meta_obj.get("npz_sha256"), str):
            if not hmac.compare_digest(npz_sha256, meta_obj["npz_sha256"].lower()):
                raise RuntimeError(
                    f"Activations NPZ SHA-256 ({npz_sha256}) disagrees with sidecar ({meta_obj['npz_sha256']})"
                )
        step_meta = meta_obj.get("step_metadata", []) if isinstance(meta_obj, dict) else []
        if len(step_meta) == compile_residuals.shape[1]:
            rel_step0_weight = 0.20
            step_weights = np.array(
                [rel_step0_weight if int(sm.get("rel_step", 1)) == 0 else 1.0 for sm in step_meta],
                dtype=np.float64,
            )
            compile_residuals = np.ascontiguousarray(compile_residuals * step_weights[None, :], dtype=np.float64)
    safety_dirs = build_safety_directions_from_npz(data)

    # Trace-normalize K0 noise by 1/sqrt(n_noise) per weft E4/E5 convention
    k0_norm = k0_noise / np.sqrt(float(max(1, k0_noise.shape[1])))

    cfg_f16 = BetaEditConfig(
        d_in=d_in,
        d_out=d_out,
        max_rank=rank,
        max_slots=8,
        lambda_leakage=lambda_leakage,
        lambda_ridge=lambda_ridge,
        nullspace_threshold=1e9,
        threshold_mode="absolute",
        radix_scale_exp2=24,
        quant_dtype="f16",
    )
    proj = BetaEditNullspaceProjector(w0_down, cfg_f16)
    proj.initialize_anchor_covariance(k0_norm)
    for b_s, a_s in safety_dirs:
        proj.register_safety_direction(b_s, a_s)

    pres_keys = k0_anchors if k0_anchors.shape[1] > 0 else None

    # Snapshot projector epoch & covariance digest and extract exact float64 (b64, a64) BEFORE stage_edit
    pre_epoch = int(proj.projector_epoch)
    pre_cov_accum = np.ascontiguousarray(proj.cov_accum, dtype=np.float64).copy()
    pre_cov_sha256 = hashlib.sha256(pre_cov_accum.tobytes()).hexdigest()
    pre_u_cov_u_sha256 = hashlib.sha256(
        np.ascontiguousarray(proj._cached_u_cov_u, dtype=np.float64).tobytes()
    ).hexdigest()
    pre_safety_dirs = [(b_s.copy(), a_s.copy()) for b_s, a_s in proj._safety_directions]

    b64, a64, s_vals, trunc_err = _extract_raw_betaedit_factors(
        proj,
        compile_keys,
        compile_residuals,
        rank=rank,
        preservation_keys=pres_keys,
        preservation_weight=preservation_weight,
    )

    p2b_f16 = proj.stage_edit(
        compile_keys,
        compile_residuals,
        is_residual=True,
        rank=rank,
        preservation_keys=pres_keys,
        preservation_weight=preservation_weight,
        slot_name="mde:formal-verification",
    )

    # Assert stage_edit did not mutate projector epoch or covariance state
    post_epoch = int(proj.projector_epoch)
    post_cov_sha256 = hashlib.sha256(
        np.ascontiguousarray(proj.cov_accum, dtype=np.float64).tobytes()
    ).hexdigest()
    post_u_cov_u_sha256 = hashlib.sha256(
        np.ascontiguousarray(proj._cached_u_cov_u, dtype=np.float64).tobytes()
    ).hexdigest()
    if (
        post_epoch != pre_epoch
        or not hmac.compare_digest(post_cov_sha256, pre_cov_sha256)
        or not hmac.compare_digest(post_u_cov_u_sha256, pre_u_cov_u_sha2256 := pre_u_cov_u_sha256)
    ):
        raise RuntimeError(
            f"Projector state mutated across stage_edit: epoch {pre_epoch}->{post_epoch}, "
            f"cov {pre_cov_sha256}->{post_cov_sha256}, u_cov_u {pre_u_cov_u_sha2256}->{post_u_cov_u_sha256}"
        )

    # Assert pre-quantization float64 factors match f16 patch within IEEE-754 binary16 rounding tolerance
    b_f16_bytes_check, _ = quantize_array(b64, "f16", axis=0)
    a_f16_bytes_check, _ = quantize_array(a64, "f16", axis=1)
    if b_f16_bytes_check != p2b_f16.b_bytes or a_f16_bytes_check != p2b_f16.a_bytes:
        raise RuntimeError("Pre-stage_edit float64 solve diverged from stage_edit quantized F16 bytes")

    f16_frob_diff = float(
        np.linalg.norm((b64 @ a64) - (p2b_f16.factor_b @ p2b_f16.factor_a), ord="fro")
    )
    u_binary16 = float(2**-11)
    f16_rounding_tol = (
        4.0 * u_binary16 * float(np.linalg.norm(b64, ord="fro")) * float(np.linalg.norm(a64, ord="fro"))
        + 1e-6
    )
    if f16_frob_diff > f16_rounding_tol:
        raise RuntimeError(
            f"||b64 @ a64 - B_f16 @ A_f16||_F ({f16_frob_diff}) exceeded F16 rounding bound ({f16_rounding_tol})"
        )

    p2b_int4_int8 = _quantize_raw_factors_as_patch(
        b64,
        a64,
        s_vals,
        trunc_err,
        b_dtype="int4",
        a_dtype="int8",
        cov_accum=pre_cov_accum,
        projector_epoch=pre_epoch,
        radix_scale_exp2=cfg_f16.radix_scale_exp2,
        safety_directions=pre_safety_dirs,
        slot_name="mde:formal-verification",
    )
    p2b_int4_f16 = _quantize_raw_factors_as_patch(
        b64,
        a64,
        s_vals,
        trunc_err,
        b_dtype="int4",
        a_dtype="f16",
        cov_accum=pre_cov_accum,
        projector_epoch=pre_epoch,
        radix_scale_exp2=cfg_f16.radix_scale_exp2,
        safety_directions=pre_safety_dirs,
        slot_name="mde:formal-verification",
    )

    # Assert all 3 certificates share the identical projector_epoch & pre_cov_accum digest and pass GatePolicy
    for label, patch_cand in (
        ("f16", p2b_f16),
        ("int4/int8", p2b_int4_int8),
        ("int4/f16", p2b_int4_f16),
    ):
        if patch_cand.certificate.projector_epoch != pre_epoch:
            raise RuntimeError(
                f"P2-B {label} certificate projector_epoch ({patch_cand.certificate.projector_epoch}) != {pre_epoch}"
            )
        rechecked_cert = build_certificate(
            patch_cand.factor_b,
            patch_cand.factor_a,
            pre_cov_accum,
            factor_digest=patch_cand.factor_digest,
            quant_dtype=patch_cand.certificate.quant_dtype,
            projector_epoch=pre_epoch,
            radix_scale_exp2=cfg_f16.radix_scale_exp2,
            safety_directions=pre_safety_dirs,
        )
        if not hmac.compare_digest(rechecked_cert.sha256(), patch_cand.certificate.sha256()):
            raise RuntimeError(f"P2-B {label} certificate covariance digest mismatch against pre_cov_accum")
        ok_c, probs_c = patch_cand.certificate.verify_division_free(gate_policy)
        if not ok_c:
            raise RuntimeError(f"P2-B {label} certificate failed pre-registered GatePolicy: {probs_c}")

    # Build 5-layer Weft BindingManifest
    weft_flags = WeftRuntimeFlags(
        quantization_mode="Q8_0_base_f16_lora",
        mamba_cache_mode="deltanet_slot_erase",
        enable_thinking=False,
        tool_call_parser="qwen3_xml",
        rope_scaling="mrope_default",
        ctx_size=8192,
    )
    derivation_recipe = {
        "compiler": "weft/0.1.0",
        "method": "BetaEditNullspaceProjector_soft_cov_float64",
        "target_layer": PINNED_TARGET_LAYER,
        "target_tensor_safetensors": PINNED_TARGET_TENSOR_ST,
        "target_tensor_gguf": PINNED_TARGET_TENSOR_GGUF,
        "rank": rank,
        "lambda_leakage": lambda_leakage,
        "lambda_ridge": lambda_ridge,
        "preservation_weight": preservation_weight,
        "output_gain": output_gain,
        "rel_step0_weight": rel_step0_weight,
        "harvested_activations_npz_sha256": npz_sha256,
        "harvested_activations_meta_sha256": meta_sha256,
        "zone_manifest_id": zone_manifest_id,
    }
    binding_manifest = build_binding_manifest(
        adapter_name="mde:formal-verification",
        adapter_class=ADAPTER_CLASS_1,
        checkpoint_dir=safetensors_dir,
        plane1_root=plane1_root,
        plane1_files=plane1_rel_files,
        derivation_recipe=derivation_recipe,
        runtime_flags=weft_flags,
        factor_digest=p2b_f16.factor_digest,
        certificate_sha256=p2b_f16.certificate.sha256(),
    )
    bind_verify = verify_binding(
        binding_manifest,
        checkpoint_dir=safetensors_dir,
        runtime_flags=weft_flags,
        plane1_root=plane1_root,
        expected_factor_digest=p2b_f16.factor_digest,
        expected_certificate_sha256=p2b_f16.certificate.sha256(),
    )
    if not bind_verify.ok:
        raise RuntimeError(f"P2-B 5-layer binding check failed: {bind_verify.problems}")

    base_weights_sha = binding_manifest.checkpoint_fingerprint

    # Emit GGUF v3 F16 LoRA (`gguf_lora.py`)
    gguf_name = "formal-verification.p2b.f16.gguf"
    gguf_path = output_dir / gguf_name
    _, gguf_sha256 = write_gguf_lora(
        gguf_path,
        architecture="qwen35",
        lora_alpha=float(p2b_f16.effective_rank),
        layer_factors={PINNED_TARGET_TENSOR_GGUF: (p2b_f16.factor_b, p2b_f16.factor_a)},
        extra_metadata={
            "weft.adapter_class": ADAPTER_CLASS_1,
            "weft.adapter_id": "mde:formal-verification",
            "weft.binding_sha256": binding_manifest.sha256(),
            "weft.certificate_sha256": p2b_f16.certificate.sha256(),
            "weft.domain": "formal-verification",
            "weft.factor_digest": p2b_f16.factor_digest,
            "weft.zone_manifest_id": zone_manifest_id,
        },
    )
    parsed_gguf = read_gguf_lora(gguf_path)
    if f"{PINNED_TARGET_TENSOR_GGUF}.lora_a" not in parsed_gguf.tensors:
        raise RuntimeError("GGUF round-trip verification failed on lora_a tensor")

    # Emit weft-slab/v0.1 binary containers (int4/int8, int4/f16, and f16/f16)
    slab_i4_i8_name = "formal-verification.p2b.int4_int8.wfsl"
    slab_i4_f16_name = "formal-verification.p2b.int4_f16.wfsl"
    slab_f16_name = "formal-verification.p2b.f16.wfsl"
    slab_i4_i8_path = output_dir / slab_i4_i8_name
    slab_i4_f16_path = output_dir / slab_i4_f16_name
    slab_f16_path = output_dir / slab_f16_name

    blob_i4_i8 = write_slab_wire(
        p2b_int4_int8,
        target_tensor=PINNED_TARGET_TENSOR_GGUF,
        base_weights_sha256=base_weights_sha,
        zone_manifest_id=zone_manifest_id,
        output_path=slab_i4_i8_path,
    )
    blob_i4_f16 = write_slab_wire(
        p2b_int4_f16,
        target_tensor=PINNED_TARGET_TENSOR_GGUF,
        base_weights_sha256=base_weights_sha,
        zone_manifest_id=zone_manifest_id,
        output_path=slab_i4_f16_path,
    )
    blob_f16 = write_slab_wire(
        p2b_f16,
        target_tensor=PINNED_TARGET_TENSOR_GGUF,
        base_weights_sha256=base_weights_sha,
        zone_manifest_id=zone_manifest_id,
        output_path=slab_f16_path,
    )

    for spath in (slab_i4_i8_path, slab_i4_f16_path, slab_f16_path):
        s_ok, s_probs, _ = verify_slab_wire(
            spath,
            gate_policy=gate_policy,
            expected_zone_manifest_id=zone_manifest_id,
            expected_base_weights_sha256=base_weights_sha,
        )
        if not s_ok:
            raise RuntimeError(f"Slab container verification failed for {spath.name}: {s_probs}")

    # Emit certificates, binding manifest, GatePolicy, Warp AdapterBundle, and vendor-namespaced _meta
    cert_name = "formal-verification.p2b.certificate.json"
    bind_name = "formal-verification.p2b.binding.json"
    gate_policy_name = "formal-verification.p2b.gate_policy.json"
    warp_bundle_name = "formal-verification.p2b.warp_bundle.json"
    wmcp_meta_name = "formal-verification.p2b.wmcp_meta.json"

    cert_path = output_dir / cert_name
    cert_path.write_text(
        json.dumps(asdict(p2b_f16.certificate), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    bind_path = output_dir / bind_name
    bind_path.write_text(
        json.dumps(asdict(binding_manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    gate_policy_path = output_dir / gate_policy_name
    gate_policy_path.write_text(
        json.dumps(asdict(gate_policy), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    warp_flags = WarpRuntimeFlags(
        llama_server_commit=commit_clean,
        quantization="Q8_0",
        ctx_size=8192,
        kv_cache_type="f16",
        ctx_checkpoints=0,
        swa_checkpoints=0,
        lora_init_without_apply=True,
        rope_args="",
        chat_template_args='{"enable_thinking":false}',
    )
    rel_gguf_posix = f"{rel_p2b_prefix}/{gguf_name}"
    state_bank_flags = detect_checkpoint_state_bank_flags(safetensors_dir)

    warp_bundle = build_warp_adapter_bundle(
        adapter_id="mde:formal-verification",
        domain="formal-verification",
        llama_adapter_id=2,
        weft_manifest=binding_manifest,
        weft_certificate=p2b_f16.certificate,
        gguf_sha256=gguf_sha256,
        model_id=PINNED_MODEL_ID,
        source_lineage=source_lineage,
        runtime_flags_sha256=warp_flags.canonical_digest(),
        scale=1.0,
        adapter_path=rel_gguf_posix,
    )
    warp_bundle["checkpoint"].update(state_bank_flags)
    warp_bundle["zone_manifest_id"] = zone_manifest_id
    warp_bundle_path = output_dir / warp_bundle_name
    warp_bundle_path.write_text(
        json.dumps(warp_bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Hard Veto 4 vendor-namespaced W-MCP Profile B metadata (`_meta["gg.siliconcordat/mde"]`)
    wmcp_meta = {
        "_meta": {
            "gg.siliconcordat/mde": {
                "checkpoint_fingerprint": warp_bundle["checkpoint"],
                "runtime_flags": warp_flags.to_dict(),
                "runtime_flags_sha256": warp_flags.canonical_digest(),
                "slot_manifest_digest": hashlib.sha256(
                    json.dumps(warp_bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "zone_manifest_id": zone_manifest_id,
                "zone_hint": "formal_proof",
                "rollback_state": "bypassed_to_w0",
            }
        }
    }
    wmcp_meta_path = output_dir / wmcp_meta_name
    wmcp_meta_path.write_text(json.dumps(wmcp_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "projector": proj,
        "projector_epoch": pre_epoch,
        "covariance_sha256": pre_cov_sha256,
        "f16_vs_float64_frob_diff": f16_frob_diff,
        "f16_rounding_tolerance": f16_rounding_tol,
        "w0_down": w0_down,
        "k0_norm": k0_norm,
        "k0_anchors": k0_anchors,
        "compile_keys": compile_keys,
        "compile_residuals": compile_residuals,
        "safety_directions": safety_dirs,
        "raw_b64": b64,
        "raw_a64": a64,
        "p2b_f16_patch": p2b_f16,
        "p2b_int4_int8_patch": p2b_int4_int8,
        "p2b_int4_f16_patch": p2b_int4_f16,
        "binding_manifest": binding_manifest,
        "gate_policy": gate_policy,
        "warp_flags": warp_flags,
        "warp_bundle": warp_bundle,
        "disk_gguf_path": gguf_path,
        "artifacts": {
            "gguf_f16_path": rel_gguf_posix,
            "gguf_f16_sha256": gguf_sha256,
            "gguf_f16_bytes": gguf_path.stat().st_size,
            "slab_int4_int8_path": f"{rel_p2b_prefix}/{slab_i4_i8_name}",
            "slab_int4_int8_sha256": hashlib.sha256(blob_i4_i8).hexdigest(),
            "slab_int4_int8_bytes": len(blob_i4_i8),
            "slab_int4_f16_path": f"{rel_p2b_prefix}/{slab_i4_f16_name}",
            "slab_int4_f16_sha256": hashlib.sha256(blob_i4_f16).hexdigest(),
            "slab_int4_f16_bytes": len(blob_i4_f16),
            "slab_f16_path": f"{rel_p2b_prefix}/{slab_f16_name}",
            "slab_f16_sha256": hashlib.sha256(blob_f16).hexdigest(),
            "certificate_path": f"{rel_p2b_prefix}/{cert_name}",
            "certificate_sha256": p2b_f16.certificate.sha256(),
            "factor_f16_digest": p2b_f16.factor_digest,
            "factor_int4_int8_digest": p2b_int4_int8.factor_digest,
            "factor_int4_f16_digest": p2b_int4_f16.factor_digest,
            "binding_path": f"{rel_p2b_prefix}/{bind_name}",
            "binding_sha256": binding_manifest.sha256(),
            "gate_policy_path": f"{rel_p2b_prefix}/{gate_policy_name}",
            "warp_bundle_path": f"{rel_p2b_prefix}/{warp_bundle_name}",
            "wmcp_meta_path": f"{rel_p2b_prefix}/{wmcp_meta_name}",
        },
    }


def compile_p2a_baseline(
    *,
    w0_down: np.ndarray,
    compile_keys: np.ndarray,
    compile_residuals: np.ndarray,
    cov_accum_for_audit: np.ndarray,
    safety_directions: list[tuple[np.ndarray, np.ndarray]],
    target_frob_norm: float,
    base_weights_sha256: str,
    zone_manifest_id: str,
    output_dir: Path,
    rank: int = DEFAULT_RANK,
    gate_policy: GatePolicy = PRE_REGISTERED_GATE_POLICY,
    repo_rel_p2a_dir: str = "compile/artifacts/p2a",
) -> dict[str, Any]:
    """Compile Arm P2-A: activation-projected low-rank steering WITHOUT null-space BetaEdit solve."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rel_p2a_prefix = repo_rel_p2a_dir.rstrip("/")
    k_norms_sq = np.sum(compile_keys * compile_keys, axis=0, keepdims=True) + 1e-6
    right_proj = (compile_keys / k_norms_sq).T
    b_raw, a_raw, s_vals, trunc_err = BetaEditNullspaceProjector.decompose_rank_r(
        compile_residuals, right_proj, rank
    )
    cur_frob = float(np.linalg.norm(b_raw @ a_raw, ord="fro"))
    scale = np.sqrt(target_frob_norm / max(cur_frob, 1e-12))
    b_scaled = b_raw * scale
    a_scaled = a_raw * scale

    p2a_patch = _quantize_raw_factors_as_patch(
        b_scaled,
        a_scaled,
        s_vals * (scale * scale),
        trunc_err,
        b_dtype="f16",
        a_dtype="f16",
        cov_accum=cov_accum_for_audit,
        projector_epoch=1,
        radix_scale_exp2=24,
        safety_directions=safety_directions,
        slot_name="mde:formal-verification-p2a",
    )
    ok_p2a, probs_p2a = p2a_patch.certificate.verify_division_free(gate_policy)
    if ok_p2a:
        raise RuntimeError("Unprojected Arm P2-A baseline unexpectedly passed PRE_REGISTERED_GATE_POLICY")

    gguf_name = "formal-verification.p2a.f16.gguf"
    slab_name = "formal-verification.p2a.f16.wfsl"
    cert_name = "formal-verification.p2a.certificate.json"

    gguf_path = output_dir / gguf_name
    _, gguf_sha = write_gguf_lora(
        gguf_path,
        architecture="qwen35",
        lora_alpha=float(p2a_patch.effective_rank),
        layer_factors={PINNED_TARGET_TENSOR_GGUF: (p2a_patch.factor_b, p2a_patch.factor_a)},
        extra_metadata={
            "weft.arm": "P2-A",
            "weft.certificate_sha256": p2a_patch.certificate.sha256(),
            "weft.domain": "formal-verification",
        },
    )
    slab_path = output_dir / slab_name
    slab_blob = write_slab_wire(
        p2a_patch,
        target_tensor=PINNED_TARGET_TENSOR_GGUF,
        base_weights_sha256=base_weights_sha256,
        zone_manifest_id=zone_manifest_id,
        output_path=slab_path,
    )
    cert_path = output_dir / cert_name
    cert_path.write_text(
        json.dumps(asdict(p2a_patch.certificate), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "gguf_f16_path": f"{rel_p2a_prefix}/{gguf_name}",
        "gguf_f16_sha256": gguf_sha,
        "slab_f16_path": f"{rel_p2a_prefix}/{slab_name}",
        "slab_f16_sha256": hashlib.sha256(slab_blob).hexdigest(),
        "certificate_sha256": p2a_patch.certificate.sha256(),
        "certificate": asdict(p2a_patch.certificate),
        "frobenius_norm": round(float(np.linalg.norm(p2a_patch.factor_b @ p2a_patch.factor_a, "fro")), 6),
        "stage2_gate_passes": False,
        "stage2_rejection_reasons": probs_p2a,
    }


def compile_phase6_companion_packs(
    *,
    proj_shared: BetaEditNullspaceProjector,
    safetensors_dir: Path,
    activations_npz: Path,
    p2b_result: dict[str, Any],
    plane1_corpus_doc: Path,
    plane1_eido_doc: Path,
    source_lineage: dict[str, Any],
    output_dir: Path,
    zone_manifest_id: str = PINNED_ZONE_MANIFEST_ID,
    rank: int = DEFAULT_RANK,
    repo_rel_comp_dir: str = "compile/artifacts/composition",
) -> dict[str, Any]:
    """Compile companion real Qwen3.5-4B rank-8 adapters (`mde:corpus`, `mde:weft-eido`) for Phase 6."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rel_comp_prefix = repo_rel_comp_dir.rstrip("/")
    state_bank_flags = detect_checkpoint_state_bank_flags(safetensors_dir)

    data = np.load(activations_npz)
    k0_anchors = np.ascontiguousarray(data["k0_anchors"], dtype=np.float64)
    pres_keys = k0_anchors if k0_anchors.shape[1] > 0 else None

    weft_flags = WeftRuntimeFlags(
        quantization_mode="Q8_0_base_f16_lora",
        mamba_cache_mode="deltanet_slot_erase",
        enable_thinking=False,
        tool_call_parser="qwen3_xml",
        rope_scaling="mrope_default",
        ctx_size=8192,
    )
    warp_flags: WarpRuntimeFlags = p2b_result["warp_flags"]
    base_weights_sha = p2b_result["binding_manifest"].checkpoint_fingerprint

    packs_out: dict[str, Any] = {}
    specs = [
        ("corpus", "mde:corpus", 0, data["corpus_keys"], data["corpus_residuals"], plane1_corpus_doc),
        ("weft-eido", "mde:weft-eido", 1, data["eido_keys"], data["eido_residuals"], plane1_eido_doc),
    ]
    for domain, aid, llama_id, raw_k, raw_r, p1_doc in specs:
        patch = proj_shared.stage_edit(
            np.ascontiguousarray(raw_k, dtype=np.float64),
            np.ascontiguousarray(raw_r, dtype=np.float64),
            is_residual=True,
            rank=rank,
            preservation_keys=pres_keys,
            preservation_weight=2.0,
            slot_name=aid,
        )
        gguf_name = f"{domain}.f16.gguf"
        slab_name = f"{domain}.f16.wfsl"
        bundle_name = f"{domain}.warp_bundle.json"

        gguf_path = output_dir / gguf_name
        _, gguf_sha = write_gguf_lora(
            gguf_path,
            architecture="qwen35",
            lora_alpha=float(patch.effective_rank),
            layer_factors={PINNED_TARGET_TENSOR_GGUF: (patch.factor_b, patch.factor_a)},
            extra_metadata={
                "weft.adapter_class": ADAPTER_CLASS_1,
                "weft.adapter_id": aid,
                "weft.certificate_sha256": patch.certificate.sha256(),
                "weft.domain": domain,
                "weft.zone_manifest_id": zone_manifest_id,
            },
        )
        slab_path = output_dir / slab_name
        slab_blob = write_slab_wire(
            patch,
            target_tensor=PINNED_TARGET_TENSOR_GGUF,
            base_weights_sha256=base_weights_sha,
            zone_manifest_id=zone_manifest_id,
            output_path=slab_path,
        )
        p1_hash_map = {p1_doc.name: hashlib.sha256(p1_doc.read_bytes()).hexdigest()}
        manifest = build_binding_manifest(
            adapter_name=aid,
            adapter_class=ADAPTER_CLASS_1,
            checkpoint_dir=safetensors_dir,
            plane1_hashes=p1_hash_map,
            derivation_recipe={
                "compiler": "weft/0.1.0",
                "domain": domain,
                "target_tensor_gguf": PINNED_TARGET_TENSOR_GGUF,
                "rank": int(patch.effective_rank),
                "zone_manifest_id": zone_manifest_id,
            },
            runtime_flags=weft_flags,
            factor_digest=patch.factor_digest,
            certificate_sha256=patch.certificate.sha256(),
        )
        rel_gguf = f"{rel_comp_prefix}/{gguf_name}"
        bundle = build_warp_adapter_bundle(
            adapter_id=aid,
            domain=domain,
            llama_adapter_id=llama_id,
            weft_manifest=manifest,
            weft_certificate=patch.certificate,
            gguf_sha256=gguf_sha,
            model_id=PINNED_MODEL_ID,
            source_lineage=source_lineage,
            runtime_flags_sha256=warp_flags.canonical_digest(),
            scale=1.0,
            adapter_path=rel_gguf,
        )
        bundle["checkpoint"].update(state_bank_flags)
        bundle["zone_manifest_id"] = zone_manifest_id
        bundle_path = output_dir / bundle_name
        bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        packs_out[domain] = {
            "adapter_id": aid,
            "llama_adapter_id": llama_id,
            "gguf_path": rel_gguf,
            "gguf_sha256": gguf_sha,
            "slab_path": f"{rel_comp_prefix}/{slab_name}",
            "slab_sha256": hashlib.sha256(slab_blob).hexdigest(),
            "certificate_sha256": patch.certificate.sha256(),
            "binding_sha256": manifest.sha256(),
            "warp_bundle_path": f"{rel_comp_prefix}/{bundle_name}",
            "certificate": asdict(patch.certificate),
        }

    # Copy formal-verification P2-B into composition/ as slot 2 for 3-pack convenience
    fv_gguf_name = "formal-verification.f16.gguf"
    fv_bundle_name = "formal-verification.warp_bundle.json"
    fv_comp_gguf = output_dir / fv_gguf_name
    fv_src_gguf: Path = p2b_result["disk_gguf_path"]
    fv_comp_gguf.write_bytes(fv_src_gguf.read_bytes())

    fv_rel_gguf = f"{rel_comp_prefix}/{fv_gguf_name}"
    fv_comp_bundle = copy.deepcopy(p2b_result["warp_bundle"])
    fv_comp_bundle["checkpoint"].update(state_bank_flags)
    fv_comp_bundle["adapter_path"] = fv_rel_gguf
    fv_comp_bundle_path = output_dir / fv_bundle_name
    fv_comp_bundle_path.write_text(
        json.dumps(fv_comp_bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    packs_out["formal-verification"] = {
        "adapter_id": "mde:formal-verification",
        "llama_adapter_id": 2,
        "gguf_path": fv_rel_gguf,
        "gguf_sha256": p2b_result["artifacts"]["gguf_f16_sha256"],
        "warp_bundle_path": f"{rel_comp_prefix}/{fv_bundle_name}",
    }
    return packs_out
