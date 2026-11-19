#!/usr/bin/env python3
"""Pure independent CPU float64 re-derivation of P2-B (Hard Veto 1 check).

Does NOT import `mcproof_compile`. Reads raw BF16 Safetensors bytes directly,
re-executes `siliconcordat/weft` CPU float64 `BetaEditNullspaceProjector`,
`FixedRadixCertificate`, `write_gguf_lora`, `write_slab_wire`, and `BindingManifest`
inside `verification/rederived_p2b/`, and asserts
exact `0`-byte diff (identical SHA-256) against `compile/artifacts/p2b/`.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any

import numpy as np

_VERIF_DIR = Path(__file__).resolve().parent
PLANE1_ROOT = _VERIF_DIR.parent
_SC_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (PLANE1_ROOT.parents[1] / "siliconcordat"))
WEFT_SRC = Path(os.environ.get("WEFT_SRC") or (_SC_ROOT / "weft" / "src"))
sys.path.insert(0, str(WEFT_SRC))

from weft.binding import ADAPTER_CLASS_1, RuntimeFlags as WeftRuntimeFlags, build_binding_manifest  # noqa: E402
from weft.certificate import build_certificate  # noqa: E402
from weft.compiler import BetaEditConfig, BetaEditNullspaceProjector, StagedPatch  # noqa: E402
from weft.gguf_lora import write_gguf_lora  # noqa: E402
from weft.quant import quantize_array, sha256_factor_pair  # noqa: E402
from weft.slab_wire import write_slab_wire  # noqa: E402

COMPILE_DIR = Path(os.environ.get("MCPROOF_COMPILE_DIR") or (PLANE1_ROOT / "compile"))
EXPECTED_P2B_DIR = COMPILE_DIR / "artifacts" / "p2b"
ACTIVATIONS_NPZ = COMPILE_DIR / "artifacts" / "harvested_activations.npz"
SAFETENSORS_DIR = COMPILE_DIR / "checkpoints" / "Qwen3.5-4B"
OUT_DIR = _VERIF_DIR / "rederived_p2b"
RECEIPT_JSON = _VERIF_DIR / "p2b_rederivation_receipt.json"


def load_safetensors_bf16_as_f64_independent(st_dir: Path, tensor_name: str) -> np.ndarray:
    """Zero-framework independent Safetensors reader converting BF16/F16/F32 -> CPU float64."""
    idx_path = st_dir / "model.safetensors.index.json"
    if idx_path.is_file():
        weight_map = json.loads(idx_path.read_text(encoding="utf-8"))["weight_map"]
        shard_file = st_dir / weight_map[tensor_name]
    else:
        shard_file = st_dir / "model.safetensors"

    with shard_file.open("rb") as fh:
        (hdr_len,) = struct.unpack("<Q", fh.read(8))
        header = json.loads(fh.read(hdr_len).decode("utf-8"))
        info = header[tensor_name]
        dtype = info["dtype"]
        shape = tuple(int(d) for d in info["shape"])
        start, end = int(info["data_offsets"][0]), int(info["data_offsets"][1])
        fh.seek(8 + hdr_len + start)
        raw = fh.read(end - start)

    if dtype == "BF16":
        u16 = np.frombuffer(raw, dtype="<u2")
        u32 = u16.astype(np.uint32) << 16
        f32 = u32.view(np.float32)
        return np.ascontiguousarray(f32.reshape(shape), dtype=np.float64)
    if dtype == "F16":
        f16 = np.frombuffer(raw, dtype="<f2")
        return np.ascontiguousarray(f16.reshape(shape), dtype=np.float64)
    if dtype == "F32":
        f32 = np.frombuffer(raw, dtype="<f4")
        return np.ascontiguousarray(f32.reshape(shape), dtype=np.float64)
    raise ValueError(f"Unsupported safetensors dtype: {dtype}")


def quantize_factors_independent(
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exp_bind_raw = json.loads(
        (EXPECTED_P2B_DIR / "formal-verification.p2b.binding.json").read_text(encoding="utf-8")
    )
    recipe = exp_bind_raw["derivation_recipe"]
    target_st = str(recipe["target_tensor_safetensors"])
    target_gguf = str(recipe["target_tensor_gguf"])
    rank = int(recipe["rank"])
    lambda_leakage = float(recipe["lambda_leakage"])
    lambda_ridge = float(recipe["lambda_ridge"])
    preservation_weight = float(recipe["preservation_weight"])
    output_gain = float(recipe["output_gain"])
    zone_manifest_id = str(recipe["zone_manifest_id"])

    npz_bytes = ACTIVATIONS_NPZ.read_bytes()
    npz_sha256 = hashlib.sha256(npz_bytes).hexdigest()
    if npz_sha256 != recipe["harvested_activations_npz_sha256"]:
        raise RuntimeError(
            f"Activations NPZ SHA-256 mismatch: {npz_sha256} != {recipe['harvested_activations_npz_sha256']}"
        )

    w0 = load_safetensors_bf16_as_f64_independent(SAFETENSORS_DIR, target_st)
    d_out, d_in = w0.shape
    data = np.load(ACTIVATIONS_NPZ)
    k0_noise = np.ascontiguousarray(data["k0_noise"], dtype=np.float64)
    k0_anchors = np.ascontiguousarray(data["k0_anchors"], dtype=np.float64)
    compile_keys = np.ascontiguousarray(data["compile_keys"], dtype=np.float64)
    compile_residuals = np.ascontiguousarray(data["compile_residuals"], dtype=np.float64) * output_gain
    meta_sidecar = ACTIVATIONS_NPZ.with_suffix(".meta.json")
    meta_sha256: str | None = None
    if meta_sidecar.is_file():
        meta_bytes = meta_sidecar.read_bytes()
        meta_sha256 = hashlib.sha256(meta_bytes).hexdigest()
        if "harvested_activations_meta_sha256" in recipe and meta_sha256 != recipe["harvested_activations_meta_sha256"]:
            raise RuntimeError(
                f"Activations meta SHA-256 mismatch: {meta_sha256} != {recipe['harvested_activations_meta_sha256']}"
            )
        meta_obj = json.loads(meta_bytes.decode("utf-8"))
        step_meta = meta_obj.get("step_metadata", [])
        rel_step0_weight = float(recipe.get("rel_step0_weight", 0.20))
        if len(step_meta) == compile_residuals.shape[1]:
            step_weights = np.array(
                [rel_step0_weight if int(sm.get("rel_step", 1)) == 0 else 1.0 for sm in step_meta],
                dtype=np.float64,
            )
            compile_residuals = np.ascontiguousarray(compile_residuals * step_weights[None, :], dtype=np.float64)

    safety_keys = np.ascontiguousarray(data["safety_keys"], dtype=np.float64)
    safety_sab_res = np.ascontiguousarray(data["safety_sabotage_residuals"], dtype=np.float64)
    safety_dirs: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(min(4, safety_keys.shape[1])):
        b_s = -safety_sab_res[:, i : i + 1]
        a_s = safety_keys[:, i : i + 1].T
        if float(np.linalg.norm(b_s)) > 1e-9 and float(np.linalg.norm(a_s)) > 1e-9:
            safety_dirs.append((b_s, a_s))

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
    proj = BetaEditNullspaceProjector(w0, cfg_f16)
    proj.initialize_anchor_covariance(k0_norm)
    for b_s, a_s in safety_dirs:
        proj.register_safety_direction(b_s, a_s)

    pres_keys = k0_anchors if k0_anchors.shape[1] > 0 else None
    p2b_f16 = proj.stage_edit(
        compile_keys,
        compile_residuals,
        is_residual=True,
        rank=rank,
        preservation_keys=pres_keys,
        preservation_weight=preservation_weight,
        slot_name="mde:formal-verification",
    )

    # Independent float64 pre-quantized factor solve for asymmetric slabs
    if pres_keys is not None and pres_keys.size > 0:
        w_sqrt = float(np.sqrt(max(0.0, preservation_weight)))
        k_solve = np.concatenate([compile_keys, pres_keys * w_sqrt], axis=1)
        r_solve = np.concatenate(
            [compile_residuals, np.zeros((d_out, pres_keys.shape[1]), dtype=np.float64)], axis=1
        )
    else:
        k_solve = compile_keys
        r_solve = compile_residuals

    k_proj = proj.u_small.T @ k_solve
    m_dim = proj.u_small.shape[1]
    spd = (
        cfg_f16.lambda_ridge * np.eye(m_dim, dtype=np.float64)
        + proj._cached_u_cov_u
        + (k_proj @ k_proj.T)
    )
    spd = 0.5 * (spd + spd.T)
    chol = np.linalg.cholesky(spd)
    solved = np.linalg.solve(chol.T, np.linalg.solve(chol, k_proj))
    right64 = (proj.u_small @ solved).T
    b64, a64, s_vals, trunc_err = proj.decompose_rank_r(r_solve, right64, rank)

    p2b_i4_i8 = quantize_factors_independent(
        b64,
        a64,
        s_vals,
        trunc_err,
        b_dtype="int4",
        a_dtype="int8",
        cov_accum=proj.cov_accum,
        projector_epoch=proj.projector_epoch,
        radix_scale_exp2=24,
        safety_directions=proj._safety_directions,
        slot_name="mde:formal-verification",
    )
    p2b_i4_f16 = quantize_factors_independent(
        b64,
        a64,
        s_vals,
        trunc_err,
        b_dtype="int4",
        a_dtype="f16",
        cov_accum=proj.cov_accum,
        projector_epoch=proj.projector_epoch,
        radix_scale_exp2=24,
        safety_directions=proj._safety_directions,
        slot_name="mde:formal-verification",
    )

    weft_flags = WeftRuntimeFlags(**exp_bind_raw["runtime_flags"])
    p1_files = sorted(exp_bind_raw["plane1_hashes"].keys())
    binding_manifest = build_binding_manifest(
        adapter_name="mde:formal-verification",
        adapter_class=ADAPTER_CLASS_1,
        checkpoint_dir=SAFETENSORS_DIR,
        plane1_root=PLANE1_ROOT,
        plane1_files=p1_files,
        derivation_recipe=recipe,
        runtime_flags=weft_flags,
        factor_digest=p2b_f16.factor_digest,
        certificate_sha256=p2b_f16.certificate.sha256(),
    )
    base_weights_sha = binding_manifest.checkpoint_fingerprint

    write_gguf_lora(
        OUT_DIR / "formal-verification.p2b.f16.gguf",
        architecture="qwen35",
        lora_alpha=float(p2b_f16.effective_rank),
        layer_factors={target_gguf: (p2b_f16.factor_b, p2b_f16.factor_a)},
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
    write_slab_wire(
        p2b_i4_i8,
        target_tensor=target_gguf,
        base_weights_sha256=base_weights_sha,
        zone_manifest_id=zone_manifest_id,
        output_path=OUT_DIR / "formal-verification.p2b.int4_int8.wfsl",
    )
    write_slab_wire(
        p2b_i4_f16,
        target_tensor=target_gguf,
        base_weights_sha256=base_weights_sha,
        zone_manifest_id=zone_manifest_id,
        output_path=OUT_DIR / "formal-verification.p2b.int4_f16.wfsl",
    )
    write_slab_wire(
        p2b_f16,
        target_tensor=target_gguf,
        base_weights_sha256=base_weights_sha,
        zone_manifest_id=zone_manifest_id,
        output_path=OUT_DIR / "formal-verification.p2b.f16.wfsl",
    )
    (OUT_DIR / "formal-verification.p2b.certificate.json").write_text(
        json.dumps(asdict(p2b_f16.certificate), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "formal-verification.p2b.binding.json").write_text(
        json.dumps(asdict(binding_manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    checked_files = (
        "formal-verification.p2b.f16.gguf",
        "formal-verification.p2b.int4_int8.wfsl",
        "formal-verification.p2b.int4_f16.wfsl",
        "formal-verification.p2b.f16.wfsl",
        "formal-verification.p2b.certificate.json",
        "formal-verification.p2b.binding.json",
    )
    comparisons: dict[str, Any] = {}
    all_ok = True
    for fname in checked_files:
        b_exp = (EXPECTED_P2B_DIR / fname).read_bytes()
        b_reb = (OUT_DIR / fname).read_bytes()
        sha_exp = hashlib.sha256(b_exp).hexdigest()
        sha_reb = hashlib.sha256(b_reb).hexdigest()
        diff_bytes = 0 if b_exp == b_reb else abs(len(b_exp) - len(b_reb)) + sum(
            1 for x, y in zip(b_exp, b_reb) if x != y
        )
        ok = (diff_bytes == 0 and sha_exp == sha_reb)
        if not ok:
            all_ok = False
        comparisons[fname] = {
            "expected_sha256": sha_exp,
            "rederived_sha256": sha_reb,
            "bytes": len(b_reb),
            "byte_diff_count": diff_bytes,
            "zero_byte_diff": ok,
        }

    receipt = {
        "schema": "verifier-independent-p2b-rederivation/v0.1",
        "method": "pure_weft_cpu_float64_no_mcproof_compile_imports",
        "target_tensor_safetensors": target_st,
        "target_tensor_gguf": target_gguf,
        "activations_npz_sha256": npz_sha256,
        "zero_byte_diff_all": all_ok,
        "files": comparisons,
    }
    RECEIPT_JSON.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
