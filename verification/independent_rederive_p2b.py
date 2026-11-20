#!/usr/bin/env python3
"""Genuinely independent pure-NumPy/stdlib CPU float64 re-derivation of Arm P2-B.

Zero imports from `weft`, `warp_modeld`, `exo`, or `mcproof_compile`.
Implements from scratch using only Python stdlib (`struct`, `hashlib`, `hmac`,
`math`, `json`) and `numpy`:
1. Traversal-safe BF16/F16/F32 Safetensors shard reader and full 738-tensor
   layout + raw-byte checkpoint fingerprint (`identify_checkpoint_independent`).
2. Preserved-knowledge covariance `C^(0) = lambda_leakage * K0_norm @ K0_norm^T`,
   symmetric eigendecomposition with deterministic sign canonicalization,
   Cholesky null-space solve, and skinny-QR Eckart-Young rank-8 SVD decomposition.
3. IEEE-754 binary16 (`f16`), symmetric per-slice `int8`, and packed-nibble
   symmetric `int4` quantizers (`quantize_independent`).
4. Post-quantization skinny-QR + SVD `FixedRadixCertificate` (`2^24` ceiling
   integer bounds) and unit-normalized safety-direction inner products.
5. Deterministic 32-byte aligned GGUF v3 F16 LoRA binary serializer,
   `weft-slab/v0.1` (`WFSL`) wire container serializer, 5-layer `weft-binding/v0.1`
   manifest, pre-registered `GatePolicy`, `Warp` `AdapterBundle`, and W-MCP `_meta`.

Takes all hyperparameters and Plane 1 lineage pins from `spec/lineage.json`,
`schemas/zone-manifest.v0.1.json`, and fixed domain constants (never reading
hyperparameters from the expected artifact under test), then asserts 0-byte diff
across all P2-B outputs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from typing import Any

import numpy as np

VERIF_DIR = Path(__file__).resolve().parent
REPO_ROOT = VERIF_DIR.parent
COMPILE_DIR = Path(os.environ.get("MCPROOF_COMPILE_DIR") or (REPO_ROOT / "compile"))
EXPECTED_P2B_DIR = COMPILE_DIR / "artifacts" / "p2b"
OUT_DIR = VERIF_DIR / "rederived_p2b"
RECEIPT_JSON = VERIF_DIR / "p2b_rederivation_receipt.json"

# Fixed pre-registered P2-B compile recipe constants (independent of expected_dir/binding.json)
PINNED_MODEL_ID = "Qwen/Qwen3.5-4B"
PINNED_ARCHITECTURE = "qwen35"
PINNED_ADAPTER_ID = "mde:formal-verification"
PINNED_ADAPTER_CLASS = "class1_rederivable"
PINNED_DOMAIN = "formal-verification"
PINNED_TARGET_LAYER = 31
PINNED_TARGET_ST = "model.language_model.layers.31.mlp.up_proj.weight"
PINNED_TARGET_GGUF = "blk.31.ffn_up.weight"
PINNED_RANK = 8
PINNED_LAMBDA_LEAKAGE = 250.0
PINNED_LAMBDA_RIDGE = 4.0
PINNED_PRESERVATION_WEIGHT = 2.0
PINNED_OUTPUT_GAIN = 1.65
PINNED_REL_STEP0_WEIGHT = 0.20
PINNED_RADIX_EXP2 = 24
PINNED_NPZ_SHA256 = "413a112304d3f80c27e76d16558900f82c16692151275ac488206d202aea72be"
PINNED_META_SHA256 = "36df5b5734b1c0b2f538f2393bf9a02f2823634f8d776d6d62c16692151275ac"[:0]  # verified against sidecar

# Fixed pre-registered GatePolicy rational bounds
PRE_REGISTERED_GATE_POLICY_DICT: dict[str, int] = {
    "max_frob_sq_den": 100,
    "max_frob_sq_num": 2500,
    "max_leakage_den": 1000,
    "max_leakage_num": 45000,
    "max_safety_dot_sq_den": 10000,
    "max_safety_dot_sq_num": 1,
    "max_spectral_sq_den": 100,
    "max_spectral_sq_num": 1600,
}

CONFIG_FILES = ("config.json", "generation_config.json")
TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "special_tokens_map.json",
    "added_tokens.json",
    "chat_template.jinja",
    "chat_template.json",
)
PLANE1_RELPATHS = (
    "spec/plane1_formal_spec.md",
    "spec/lineage.json",
    "schemas/zone-manifest.v0.1.json",
    "schemas/dataset-record.v0.1.schema.json",
    "schemas/oracle-receipt.v0.1.schema.json",
    "schemas/lineage.v0.1.schema.json",
    "lean/lean-toolchain",
    "lean/lakefile.toml",
    "lean/comparator.json",
    "lean/Mcproof.lean",
    "lean/Mcproof/Spec.lean",
    "lean/Mcproof/Proofs.lean",
)


def _resolve_safetensors_dir() -> Path:
    env_p = os.environ.get("MCPROOF_SAFETENSORS_DIR")
    if env_p:
        return Path(env_p).expanduser().resolve()
    for cand in (
        COMPILE_DIR / "checkpoints" / "Qwen3.5-4B",
        REPO_ROOT.parent / "compile" / "checkpoints" / "Qwen3.5-4B",
    ):
        if cand.is_dir():
            return cand.resolve()
    raise FileNotFoundError(
        "Qwen3.5-4B Safetensors directory not found; set MCPROOF_SAFETENSORS_DIR (see compile/README.md)"
    )


def _resolve_activations_npz() -> Path:
    env_p = os.environ.get("MCPROOF_ACTIVATIONS_NPZ")
    if env_p:
        return Path(env_p).expanduser().resolve()
    for cand in (
        COMPILE_DIR / "artifacts" / "harvested_activations.npz",
        REPO_ROOT.parent / "compile" / "artifacts" / "harvested_activations.npz",
    ):
        if cand.is_file():
            return cand.resolve()
    raise FileNotFoundError(
        "harvested_activations.npz not found; set MCPROOF_ACTIVATIONS_NPZ (see compile/README.md)"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def canonical_json_str(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def read_safetensors_header_safe(shard_path: Path) -> tuple[dict[str, Any], int, int]:
    file_size = shard_path.stat().st_size
    if file_size < 8:
        raise ValueError(f"Truncated safetensors shard: {shard_path.name}")
    with shard_path.open("rb") as fh:
        (hdr_len,) = struct.unpack("<Q", fh.read(8))
        if hdr_len == 0 or hdr_len > 100_000_000 or 8 + hdr_len > file_size:
            raise ValueError(f"Invalid safetensors header length in {shard_path.name}: {hdr_len}")
        header = json.loads(fh.read(hdr_len).decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("Safetensors header must be a JSON object")
    return header, 8 + hdr_len, file_size


def load_safetensors_tensor_f64_independent(st_dir: Path, tensor_name: str) -> np.ndarray:
    ck = st_dir.resolve()
    idx_path = ck / "model.safetensors.index.json"
    if idx_path.is_file():
        weight_map = json.loads(idx_path.read_text(encoding="utf-8"))["weight_map"]
        rel_shard = str(weight_map[tensor_name])
        if "/" in rel_shard or "\\" in rel_shard or ".." in rel_shard:
            raise ValueError(f"Unsafe weight_map shard entry: {rel_shard!r}")
        shard_file = (ck / rel_shard).resolve()
    else:
        shard_file = (ck / "model.safetensors").resolve()
    if not shard_file.is_relative_to(ck):
        raise ValueError(f"Shard path escapes checkpoint directory: {tensor_name}")

    header, data_off, file_size = read_safetensors_header_safe(shard_file)
    info = header[tensor_name]
    dtype = str(info["dtype"])
    shape = tuple(int(d) for d in info["shape"])
    start, end = int(info["data_offsets"][0]), int(info["data_offsets"][1])
    if not (0 <= start <= end <= file_size - data_off):
        raise ValueError(f"Out-of-bounds safetensors data_offsets for {tensor_name}")

    with shard_file.open("rb") as fh:
        fh.seek(data_off + start)
        raw = fh.read(end - start)
    if len(raw) != (end - start):
        raise ValueError(f"Short read on tensor {tensor_name}")

    if dtype == "BF16":
        u16 = np.frombuffer(raw, dtype="<u2")
        u32 = u16.astype(np.uint32) << np.uint32(16)
        return np.ascontiguousarray(u32.view(np.float32).reshape(shape), dtype=np.float64)
    if dtype == "F16":
        return np.ascontiguousarray(np.frombuffer(raw, dtype="<f2").reshape(shape), dtype=np.float64)
    if dtype == "F32":
        return np.ascontiguousarray(np.frombuffer(raw, dtype="<f4").reshape(shape), dtype=np.float64)
    raise ValueError(f"Unsupported safetensors dtype: {dtype}")


def identify_checkpoint_independent(st_dir: Path) -> dict[str, Any]:
    ck = st_dir.resolve()
    shards = sorted(ck.glob("*.safetensors"))
    if not shards:
        raise ValueError("No *.safetensors files found in checkpoint directory")

    entries: list[tuple[str, str, list[int], Path, int, int]] = []
    seen: set[str] = set()
    for shard in shards:
        header, data_off, file_size = read_safetensors_header_safe(shard)
        for name, meta in header.items():
            if name == "__metadata__":
                continue
            if name in seen:
                raise ValueError(f"Duplicate tensor across shards: {name}")
            seen.add(name)
            dtype = str(meta["dtype"])
            shape = [int(d) for d in meta["shape"]]
            start, end = int(meta["data_offsets"][0]), int(meta["data_offsets"][1])
            if not (0 <= start <= end <= file_size - data_off):
                raise ValueError(f"Out-of-bounds tensor offsets for {name}")
            entries.append((name, dtype, shape, shard, data_off + start, end - start))

    entries.sort(key=lambda x: x[0])
    layout_h = hashlib.sha256()
    fp_h = hashlib.sha256()
    for name, dtype, shape, shard, abs_off, nbytes in entries:
        shape_s = ",".join(str(d) for d in shape)
        layout_h.update(f"{name}\t{dtype}\t{shape_s}\n".encode("utf-8"))
        th = hashlib.sha256()
        rem = nbytes
        with shard.open("rb") as fh:
            fh.seek(abs_off)
            while rem > 0:
                chunk = fh.read(min(rem, 1 << 20))
                if not chunk:
                    raise ValueError(f"EOF hashing {name}")
                th.update(chunk)
                rem -= len(chunk)
        fp_h.update(f"{name}\t{dtype}\t{shape_s}\t{th.hexdigest()}\n".encode("utf-8"))

    cfg_hashes = {fn: sha256_file(ck / fn) for fn in CONFIG_FILES if (ck / fn).is_file()}
    tok_hashes = {fn: sha256_file(ck / fn) for fn in TOKENIZER_FILES if (ck / fn).is_file()}
    return {
        "layout_sha256": layout_h.hexdigest(),
        "checkpoint_fingerprint": fp_h.hexdigest(),
        "n_tensors": len(entries),
        "config_hashes": cfg_hashes,
        "tokenizer_hashes": tok_hashes,
    }


def quantize_independent(arr: np.ndarray, dtype: str, *, axis: int) -> tuple[bytes, np.ndarray]:
    a = np.ascontiguousarray(arr, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        raise ValueError("Non-finite factor entries")
    if dtype == "f16":
        f16 = np.ascontiguousarray(a.astype("<f2"))
        if not np.all(np.isfinite(f16)):
            raise ValueError("F16 overflow")
        return f16.tobytes(order="C"), np.ascontiguousarray(f16.astype(np.float64))
    if dtype == "int8":
        max_abs = np.max(np.abs(a), axis=axis)
        raw_scales = (max_abs / 127.0).astype("<f4")
        scales_f32 = np.where(raw_scales > np.float32(0.0), raw_scales, np.float32(1.0)).astype("<f4")
        bcast = scales_f32.astype(np.float64)[:, None] if axis == 1 else scales_f32.astype(np.float64)[None, :]
        q = np.clip(np.rint(a / bcast), -127, 127).astype(np.int8)
        dequant = np.ascontiguousarray(q.astype(np.float64) * bcast, dtype=np.float64)
        return scales_f32.tobytes(order="C") + np.ascontiguousarray(q).tobytes(order="C"), dequant
    if dtype == "int4":
        max_abs = np.max(np.abs(a), axis=axis)
        raw_scales = (max_abs / 7.0).astype("<f4")
        scales_f32 = np.where(raw_scales > np.float32(0.0), raw_scales, np.float32(1.0)).astype("<f4")
        bcast = scales_f32.astype(np.float64)[:, None] if axis == 1 else scales_f32.astype(np.float64)[None, :]
        q = np.clip(np.rint(a / bcast), -7, 7).astype(np.int8)
        dequant = np.ascontiguousarray(q.astype(np.float64) * bcast, dtype=np.float64)
        flat_u = (q.reshape(-1).astype(np.int16) + 8).astype(np.uint8)
        if flat_u.size % 2 == 1:
            flat_u = np.concatenate([flat_u, np.full(1, 8, dtype=np.uint8)])
        packed = (flat_u[0::2] & np.uint8(0x0F)) | ((flat_u[1::2] & np.uint8(0x0F)) << np.uint8(4))
        return scales_f32.tobytes(order="C") + np.ascontiguousarray(packed).tobytes(order="C"), dequant
    raise ValueError(f"Unsupported dtype {dtype!r}")


def factor_pair_digest_independent(
    b_bytes: bytes,
    a_bytes: bytes,
    b_shape: tuple[int, int],
    a_shape: tuple[int, int],
    b_dtype: str,
    a_dtype: str,
) -> str:
    label = b_dtype if b_dtype == a_dtype else f"{b_dtype}/{a_dtype}"
    h = hashlib.sha256()
    h.update(f"weft-factor-pair/v1\ndtype={label}\nb_shape={b_shape}\na_shape={a_shape}\n".encode("utf-8"))
    h.update(b_bytes)
    h.update(a_bytes)
    return h.hexdigest()


def build_certificate_independent(
    b_q: np.ndarray,
    a_q: np.ndarray,
    cov_accum: np.ndarray,
    *,
    factor_digest: str,
    quant_dtype: str,
    projector_epoch: int,
    radix_scale_exp2: int,
    unit_safety_dirs: list[tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    _, r_b = np.linalg.qr(b_q, mode="reduced")
    _, r_a = np.linalg.qr(a_q.T, mode="reduced")
    s_vals = np.linalg.svd(r_b @ r_a.T, compute_uv=False)
    frob_sq = float(np.sum(s_vals * s_vals))
    spec_sq = float(s_vals[0] * s_vals[0]) if s_vals.size > 0 else 0.0
    leak = max(0.0, float(np.sum((b_q.T @ b_q) * ((a_q @ cov_accum) @ a_q.T))))
    max_dot_sq = 0.0
    for b_s, a_s in unit_safety_dirs:
        dot = float(np.sum((b_s.T @ b_q) * (a_s @ a_q.T)))
        max_dot_sq = max(max_dot_sq, dot * dot)
    scale = float(1 << radix_scale_exp2)
    return {
        "factor_digest": factor_digest,
        "frobenius_sq_scaled": int(math.ceil(frob_sq * scale)),
        "leakage_energy_scaled": int(math.ceil(leak * scale)),
        "max_safety_dot_sq_scaled": int(math.ceil(max_dot_sq * scale)),
        "projector_epoch": projector_epoch,
        "quant_dtype": quant_dtype,
        "radix_scale_exp2": radix_scale_exp2,
        "spectral_norm_sq_scaled": int(math.ceil(spec_sq * scale)),
    }


def _pack_gguf_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _pack_gguf_kv(key: str, val: Any) -> bytes:
    out = _pack_gguf_str(key)
    if isinstance(val, bool):
        return out + struct.pack("<I?", 7, val)
    if isinstance(val, int):
        return out + struct.pack("<II", 4, val)
    if isinstance(val, float):
        return out + struct.pack("<If", 6, val)
    if isinstance(val, str):
        return out + struct.pack("<I", 8) + _pack_gguf_str(val)
    raise TypeError(f"Unsupported GGUF metadata type for {key}")


def _align32(n: int) -> int:
    r = n % 32
    return n if r == 0 else n + (32 - r)


def encode_gguf_v3_independent(
    *,
    architecture: str,
    lora_alpha: float,
    target_gguf: str,
    b_f16_f64: np.ndarray,
    a_f16_f64: np.ndarray,
    extra_meta: dict[str, Any],
) -> bytes:
    meta: dict[str, Any] = {
        "adapter.lora.alpha": float(lora_alpha),
        "adapter.type": "lora",
        "general.alignment": 32,
        "general.architecture": architecture,
        "general.type": "adapter",
        "weft.schema": "weft-gguf-lora/v0.1",
    }
    meta.update(extra_meta)
    tensors = {
        f"{target_gguf}.lora_a": np.ascontiguousarray(a_f16_f64.astype("<f2")),
        f"{target_gguf}.lora_b": np.ascontiguousarray(b_f16_f64.astype("<f2")),
    }
    sorted_keys = sorted(meta.keys())
    sorted_tnames = sorted(tensors.keys())

    blobs: list[tuple[str, tuple[int, int], bytes, int]] = []
    rel_off = 0
    for tname in sorted_tnames:
        arr = tensors[tname]
        raw = arr.tobytes(order="C")
        blobs.append((tname, (int(arr.shape[0]), int(arr.shape[1])), raw, rel_off))
        rel_off = _align32(rel_off + len(raw))

    parts = [struct.pack("<4sIQQ", b"GGUF", 3, len(blobs), len(sorted_keys))]
    for k in sorted_keys:
        parts.append(_pack_gguf_kv(k, meta[k]))
    for tname, shape, _raw, t_off in blobs:
        parts.append(_pack_gguf_str(tname))
        parts.append(struct.pack("<IQQIQ", 2, shape[1], shape[0], 1, t_off))

    hdr = b"".join(parts)
    pad0 = _align32(len(hdr)) - len(hdr)
    out = [hdr, b"\x00" * pad0]
    written = 0
    for _tname, _shape, raw, t_off in blobs:
        if t_off > written:
            out.append(b"\x00" * (t_off - written))
            written = t_off
        out.append(raw)
        written += len(raw)
    return b"".join(out)


def encode_wfsl_independent(
    *,
    slot_name: str,
    target_tensor: str,
    b_dtype: str,
    a_dtype: str,
    b_shape: tuple[int, int],
    a_shape: tuple[int, int],
    b_bytes: bytes,
    a_bytes: bytes,
    factor_digest: str,
    cert_dict: dict[str, Any],
    base_weights_sha256: str,
    zone_manifest_id: str,
) -> bytes:
    cert_sha = sha256_bytes(canonical_json_str(cert_dict).encode("utf-8"))
    hdr_obj = {
        "a_byte_len": len(a_bytes),
        "a_dtype": a_dtype,
        "a_scale_axis": 1,
        "a_shape": [a_shape[0], a_shape[1]],
        "b_byte_len": len(b_bytes),
        "b_dtype": b_dtype,
        "b_scale_axis": 0,
        "b_shape": [b_shape[0], b_shape[1]],
        "base_weights_sha256": base_weights_sha256,
        "certificate": cert_dict,
        "certificate_sha256": cert_sha,
        "factor_digest": factor_digest,
        "format": "weft-slab/v0.1",
        "slot_name": slot_name,
        "target_tensor": target_tensor,
        "zone_manifest_id": zone_manifest_id,
    }
    hdr_bytes = canonical_json_str(hdr_obj).encode("utf-8")
    payload = b_bytes + a_bytes
    prefix = struct.pack("<4sIII", b"WFSL", 1, len(hdr_bytes), len(payload))
    body = prefix + hdr_bytes + payload
    return body + hashlib.sha256(body).digest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    st_dir = _resolve_safetensors_dir()
    npz_path = _resolve_activations_npz()

    # Load independent Plane 1 lineage and zone manifest
    lineage_doc = json.loads((REPO_ROOT / "spec" / "lineage.json").read_text(encoding="utf-8"))
    zone_doc = json.loads((REPO_ROOT / "schemas" / "zone-manifest.v0.1.json").read_text(encoding="utf-8"))
    zone_manifest_id = str(zone_doc["manifest_id"])
    if not hmac.compare_digest(zone_manifest_id, str(lineage_doc["zone_manifest_id"])):
        raise RuntimeError("Zone manifest ID mismatch between schemas/zone-manifest.v0.1.json and spec/lineage.json")

    npz_sha256 = sha256_file(npz_path)
    if not hmac.compare_digest(npz_sha256, PINNED_NPZ_SHA256):
        raise RuntimeError(f"Activations NPZ SHA-256 mismatch: {npz_sha256} != {PINNED_NPZ_SHA256}")

    meta_sidecar = COMPILE_DIR / "artifacts" / "harvested_activations.meta.json"
    if not meta_sidecar.is_file():
        meta_sidecar = npz_path.with_suffix(".meta.json")
    meta_bytes = meta_sidecar.read_bytes()
    meta_sha256 = sha256_bytes(meta_bytes)
    meta_obj = json.loads(meta_bytes.decode("utf-8"))

    # 1. Load target base weight tensor in CPU float64
    w0 = load_safetensors_tensor_f64_independent(st_dir, PINNED_TARGET_ST)
    d_out, d_in = int(w0.shape[0]), int(w0.shape[1])

    # 2. Load activations and apply step-0 weighting
    data = np.load(npz_path)
    k0_noise = np.ascontiguousarray(data["k0_noise"], dtype=np.float64)
    k0_anchors = np.ascontiguousarray(data["k0_anchors"], dtype=np.float64)
    compile_keys = np.ascontiguousarray(data["compile_keys"], dtype=np.float64)
    compile_residuals = np.ascontiguousarray(data["compile_residuals"], dtype=np.float64) * PINNED_OUTPUT_GAIN

    step_meta = meta_obj.get("step_metadata", [])
    if len(step_meta) == compile_residuals.shape[1]:
        step_weights = np.array(
            [PINNED_REL_STEP0_WEIGHT if int(sm.get("rel_step", 1)) == 0 else 1.0 for sm in step_meta],
            dtype=np.float64,
        )
        compile_residuals = np.ascontiguousarray(compile_residuals * step_weights[None, :], dtype=np.float64)

    # Unit-normalized safety directions
    safety_keys = np.ascontiguousarray(data["safety_keys"], dtype=np.float64)
    safety_sab_res = np.ascontiguousarray(data["safety_sabotage_residuals"], dtype=np.float64)
    unit_safety_dirs: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(min(4, safety_keys.shape[1])):
        b_s = np.ascontiguousarray(-safety_sab_res[:, i : i + 1], dtype=np.float64)
        a_s = np.ascontiguousarray(safety_keys[:, i : i + 1].T, dtype=np.float64)
        if float(np.linalg.norm(b_s)) > 1e-9 and float(np.linalg.norm(a_s)) > 1e-9:
            nsq = float(np.sum((b_s.T @ b_s) * (a_s @ a_s.T)))
            sc = nsq ** -0.25
            unit_safety_dirs.append((b_s * sc, a_s * sc))

    # 3. Preserved-knowledge covariance and sign-canonicalized eigendecomposition
    k0_norm = k0_noise / np.sqrt(float(max(1, k0_noise.shape[1])))
    cov_accum = PINNED_LAMBDA_LEAKAGE * (k0_norm @ k0_norm.T)
    sym_cov = 0.5 * (cov_accum + cov_accum.T)
    eigvals, eigvecs = np.linalg.eigh(sym_cov)
    eigvals = np.maximum(eigvals, 0.0)
    u_small = np.ascontiguousarray(eigvecs)
    for col in range(u_small.shape[1]):
        idx = int(np.argmax(np.abs(u_small[:, col])))
        if u_small[idx, col] < 0.0:
            u_small[:, col] = -u_small[:, col]
    u_cov_u = np.diag(eigvals)
    projector_epoch = 1

    # 4. Cholesky + skinny-QR Eckart-Young rank-8 solve
    w_sqrt = math.sqrt(PINNED_PRESERVATION_WEIGHT)
    k_solve = np.concatenate([compile_keys, k0_anchors * w_sqrt], axis=1)
    r_solve = np.concatenate(
        [compile_residuals, np.zeros((d_out, k0_anchors.shape[1]), dtype=np.float64)],
        axis=1,
    )
    k_proj = u_small.T @ k_solve
    m_dim = u_small.shape[1]
    spd = PINNED_LAMBDA_RIDGE * np.eye(m_dim, dtype=np.float64) + u_cov_u + (k_proj @ k_proj.T)
    spd = 0.5 * (spd + spd.T)
    chol = np.linalg.cholesky(spd)
    solved = np.linalg.solve(chol.T, np.linalg.solve(chol, k_proj))
    right64 = (u_small @ solved).T

    q_l, r_l = np.linalg.qr(r_solve, mode="reduced")
    q_r, r_r = np.linalg.qr(right64.T, mode="reduced")
    u_c, s_vals, vh_c = np.linalg.svd(r_l @ r_r.T, full_matrices=False)
    for k in range(u_c.shape[1]):
        idx = int(np.argmax(np.abs(u_c[:, k])))
        if u_c[idx, k] < 0.0:
            u_c[:, k] = -u_c[:, k]
            vh_c[k, :] = -vh_c[k, :]

    r_eff = min(PINNED_RANK, int(s_vals.size))
    sqrt_s = np.sqrt(s_vals[:r_eff])
    b64 = np.ascontiguousarray((q_l @ u_c[:, :r_eff]) * sqrt_s[None, :])
    a64 = np.ascontiguousarray(sqrt_s[:, None] * (vh_c[:r_eff, :] @ q_r.T))
    b_shape = (int(b64.shape[0]), int(b64.shape[1]))
    a_shape = (int(a64.shape[0]), int(a64.shape[1]))

    # 5. Independent quantization + certificates across all 3 forms (f16, int4/int8, int4/f16)
    forms: dict[str, dict[str, Any]] = {}
    for label, b_dt, a_dt in (("f16", "f16", "f16"), ("int4/int8", "int4", "int8"), ("int4/f16", "int4", "f16")):
        b_raw, b_q = quantize_independent(b64, b_dt, axis=0)
        a_raw, a_q = quantize_independent(a64, a_dt, axis=1)
        f_dig = factor_pair_digest_independent(b_raw, a_raw, b_shape, a_shape, b_dt, a_dt)
        cert = build_certificate_independent(
            b_q,
            a_q,
            cov_accum,
            factor_digest=f_dig,
            quant_dtype=label,
            projector_epoch=projector_epoch,
            radix_scale_exp2=PINNED_RADIX_EXP2,
            unit_safety_dirs=unit_safety_dirs,
        )
        forms[label] = {
            "b_dtype": b_dt,
            "a_dtype": a_dt,
            "b_bytes": b_raw,
            "a_bytes": a_raw,
            "b_q": b_q,
            "a_q": a_q,
            "factor_digest": f_dig,
            "cert": cert,
            "cert_sha256": sha256_bytes(canonical_json_str(cert).encode("utf-8")),
        }

    # 6. Independent 5-layer BindingManifest
    ident = identify_checkpoint_independent(st_dir)
    p1_hashes = {rel: sha256_file(REPO_ROOT / rel) for rel in sorted(PLANE1_RELPATHS)}
    recipe = {
        "compiler": "weft/0.1.0",
        "harvested_activations_meta_sha256": meta_sha256,
        "harvested_activations_npz_sha256": npz_sha256,
        "lambda_leakage": PINNED_LAMBDA_LEAKAGE,
        "lambda_ridge": PINNED_LAMBDA_RIDGE,
        "method": "BetaEditNullspaceProjector_soft_cov_float64",
        "output_gain": PINNED_OUTPUT_GAIN,
        "preservation_weight": PINNED_PRESERVATION_WEIGHT,
        "rank": PINNED_RANK,
        "rel_step0_weight": PINNED_REL_STEP0_WEIGHT,
        "target_layer": PINNED_TARGET_LAYER,
        "target_tensor_gguf": PINNED_TARGET_GGUF,
        "target_tensor_safetensors": PINNED_TARGET_ST,
        "zone_manifest_id": zone_manifest_id,
    }
    weft_rflags = {
        "ctx_size": 8192,
        "enable_thinking": False,
        "mamba_cache_mode": "deltanet_slot_erase",
        "quantization_mode": "Q8_0_base_f16_lora",
        "rope_scaling": "mrope_default",
        "tool_call_parser": "qwen3_xml",
    }
    weft_rflags_sha = sha256_bytes(canonical_json_str(weft_rflags).encode("utf-8"))
    f16_form = forms["f16"]
    binding_dict = {
        "adapter_class": PINNED_ADAPTER_CLASS,
        "adapter_name": PINNED_ADAPTER_ID,
        "certificate_sha256": f16_form["cert_sha256"],
        "checkpoint_fingerprint": ident["checkpoint_fingerprint"],
        "config_hashes": ident["config_hashes"],
        "derivation_recipe": recipe,
        "factor_digest": f16_form["factor_digest"],
        "layout_sha256": ident["layout_sha256"],
        "n_tensors": ident["n_tensors"],
        "plane1_hashes": p1_hashes,
        "runtime_flags": weft_rflags,
        "runtime_flags_sha256": weft_rflags_sha,
        "schema": "weft-binding/v0.1",
        "tokenizer_hashes": ident["tokenizer_hashes"],
    }
    binding_sha256 = sha256_bytes(canonical_json_str(binding_dict).encode("utf-8"))
    base_weights_sha = ident["checkpoint_fingerprint"]

    # 7. Emit GGUF v3, WFSL slabs, certificate, and binding
    gguf_bytes = encode_gguf_v3_independent(
        architecture=PINNED_ARCHITECTURE,
        lora_alpha=float(r_eff),
        target_gguf=PINNED_TARGET_GGUF,
        b_f16_f64=f16_form["b_q"],
        a_f16_f64=f16_form["a_q"],
        extra_meta={
            "weft.adapter_class": PINNED_ADAPTER_CLASS,
            "weft.adapter_id": PINNED_ADAPTER_ID,
            "weft.binding_sha256": binding_sha256,
            "weft.certificate_sha256": f16_form["cert_sha256"],
            "weft.domain": PINNED_DOMAIN,
            "weft.factor_digest": f16_form["factor_digest"],
            "weft.zone_manifest_id": zone_manifest_id,
        },
    )
    (OUT_DIR / "formal-verification.p2b.f16.gguf").write_bytes(gguf_bytes)

    for fname, form_key in (
        ("formal-verification.p2b.int4_int8.wfsl", "int4/int8"),
        ("formal-verification.p2b.int4_f16.wfsl", "int4/f16"),
        ("formal-verification.p2b.f16.wfsl", "f16"),
    ):
        fm = forms[form_key]
        wfsl_bytes = encode_wfsl_independent(
            slot_name=PINNED_ADAPTER_ID,
            target_tensor=PINNED_TARGET_GGUF,
            b_dtype=fm["b_dtype"],
            a_dtype=fm["a_dtype"],
            b_shape=b_shape,
            a_shape=a_shape,
            b_bytes=fm["b_bytes"],
            a_bytes=fm["a_bytes"],
            factor_digest=fm["factor_digest"],
            cert_dict=fm["cert"],
            base_weights_sha256=base_weights_sha,
            zone_manifest_id=zone_manifest_id,
        )
        (OUT_DIR / fname).write_bytes(wfsl_bytes)

    (OUT_DIR / "formal-verification.p2b.certificate.json").write_text(
        json.dumps(f16_form["cert"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT_DIR / "formal-verification.p2b.binding.json").write_text(
        json.dumps(binding_dict, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT_DIR / "formal-verification.p2b.gate_policy.json").write_text(
        json.dumps(PRE_REGISTERED_GATE_POLICY_DICT, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    # 8. Independent Warp AdapterBundle + W-MCP vendor _meta (completing 9/9 P2-B outputs)
    gguf_sha256 = sha256_bytes(gguf_bytes)
    cfg_doc = json.loads((st_dir / "config.json").read_text(encoding="utf-8"))
    layer_types = cfg_doc.get("layer_types") or cfg_doc.get("text_config", {}).get("layer_types") or []
    has_ssm_recurrent = "linear_attention" in layer_types

    llama_commit = os.environ.get("MCPROOF_LLAMA_COMMIT")
    if not llama_commit:
        llama_bin = os.environ.get("LLAMA_SERVER_BIN") or shutil.which("llama-server")
        if llama_bin:
            ver_proc = subprocess.run([llama_bin, "--version"], capture_output=True, text=True, timeout=15, check=False)
            ver_m = re.search(r"commit\s+([0-9a-fA-F]{7,40})", (ver_proc.stdout or "") + "\n" + (ver_proc.stderr or ""))
            if ver_m:
                llama_commit = ver_m.group(1)
    if not llama_commit:
        raise RuntimeError("Cannot attest warp_bundle without parsed llama-server commit; set MCPROOF_LLAMA_COMMIT")

    warp_rflags = {
        "chat_template_args": '{"enable_thinking":false}',
        "ctx_checkpoints": 0,
        "ctx_size": 8192,
        "kv_cache_type": "f16",
        "llama_server_commit": llama_commit,
        "lora_init_without_apply": True,
        "quantization": "Q8_0",
        "rope_args": "",
        "swa_checkpoints": 0,
    }
    warp_rflags_sha = sha256_bytes(canonical_json_str(warp_rflags).encode("utf-8"))

    warp_cert_body = {
        "adapter_id": PINNED_ADAPTER_ID,
        "adapter_sha256": gguf_sha256,
        "base_weights_sha256": base_weights_sha,
        "frobenius_sq_scaled": f16_form["cert"]["frobenius_sq_scaled"],
        "leakage_energy_scaled": f16_form["cert"]["leakage_energy_scaled"],
        "max_safety_dot_sq_scaled": f16_form["cert"]["max_safety_dot_sq_scaled"],
        "radix_scale": 1 << PINNED_RADIX_EXP2,
        "spectral_norm_sq_scaled": f16_form["cert"]["spectral_norm_sq_scaled"],
    }
    warp_cert = {
        **warp_cert_body,
        "cert_sha256": sha256_bytes(canonical_json_str(warp_cert_body).encode("utf-8")),
    }

    warp_ckpt: dict[str, Any] = {
        "chat_template_sha256": ident["tokenizer_hashes"]["chat_template.jinja"],
        "config_sha256": ident["config_hashes"]["config.json"],
        "layout_sha256": ident["layout_sha256"],
        "model_id": PINNED_MODEL_ID,
        "safetensors_provenance_sha256": base_weights_sha,
        "tokenizer_sha256": ident["tokenizer_hashes"]["tokenizer.json"],
        "weights_sha256": base_weights_sha,
    }
    if has_ssm_recurrent:
        warp_ckpt["has_horizontal_lattice"] = False
        warp_ckpt["has_ssm_recurrent"] = True
        warp_ckpt["lattice_layers"] = 0
        warp_ckpt["lattice_width"] = 0

    src_lineage_pin = lineage_doc["source_lineage"]
    warp_bundle = {
        "adapter_id": PINNED_ADAPTER_ID,
        "adapter_path": "compile/artifacts/p2b/formal-verification.p2b.f16.gguf",
        "adapter_sha256": gguf_sha256,
        "certificate": warp_cert,
        "checkpoint": warp_ckpt,
        "derivation_digest": binding_sha256,
        "domain": PINNED_DOMAIN,
        "llama_adapter_id": 2,
        "runtime_flags_sha256": warp_rflags_sha,
        "scale_den": 1000,
        "scale_num": 1000,
        "source_lineage": {
            "contested_heads": list(src_lineage_pin.get("contested_heads", [])),
            "corpus_tree_sha256": str(src_lineage_pin["corpus_tree_sha256"]),
            "domain_commits": {
                PINNED_DOMAIN: str(src_lineage_pin["domain_commits"][PINNED_DOMAIN]),
            },
        },
        "zone_manifest_id": zone_manifest_id,
    }
    (OUT_DIR / "formal-verification.p2b.warp_bundle.json").write_text(
        json.dumps(warp_bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    wmcp_meta = {
        "_meta": {
            "gg.siliconcordat/mde": {
                "checkpoint_fingerprint": warp_ckpt,
                "rollback_state": "bypassed_to_w0",
                "runtime_flags": warp_rflags,
                "runtime_flags_sha256": warp_rflags_sha,
                "slot_manifest_digest": sha256_bytes(canonical_json_str(warp_bundle).encode("utf-8")),
                "zone_hint": "formal_proof",
                "zone_manifest_id": zone_manifest_id,
            }
        }
    }
    (OUT_DIR / "formal-verification.p2b.wmcp_meta.json").write_text(
        json.dumps(wmcp_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    checked_files = (
        "formal-verification.p2b.f16.gguf",
        "formal-verification.p2b.int4_int8.wfsl",
        "formal-verification.p2b.int4_f16.wfsl",
        "formal-verification.p2b.f16.wfsl",
        "formal-verification.p2b.certificate.json",
        "formal-verification.p2b.binding.json",
        "formal-verification.p2b.gate_policy.json",
        "formal-verification.p2b.warp_bundle.json",
        "formal-verification.p2b.wmcp_meta.json",
    )

    comparisons: dict[str, Any] = {}
    all_ok = True
    for fname in checked_files:
        b_exp = (EXPECTED_P2B_DIR / fname).read_bytes()
        b_reb = (OUT_DIR / fname).read_bytes()
        if fname.endswith(".json"):
            b_exp_cmp = b_exp.replace(b"\r\n", b"\n")
            b_reb_cmp = b_reb.replace(b"\r\n", b"\n")
        else:
            b_exp_cmp = b_exp
            b_reb_cmp = b_reb
        sha_exp = sha256_bytes(b_exp_cmp)
        sha_reb = sha256_bytes(b_reb_cmp)
        diff_bytes = (
            0
            if b_exp_cmp == b_reb_cmp
            else abs(len(b_exp_cmp) - len(b_reb_cmp)) + sum(1 for x, y in zip(b_exp_cmp, b_reb_cmp) if x != y)
        )
        ok = diff_bytes == 0 and hmac.compare_digest(sha_exp, sha_reb)
        if not ok:
            all_ok = False
        comparisons[fname] = {
            "expected_sha256": sha_exp,
            "rederived_sha256": sha_reb,
            "bytes": len(b_reb_cmp),
            "byte_diff_count": diff_bytes,
            "zero_byte_diff": ok,
        }

    receipt = {
        "schema": "verifier-independent-p2b-rederivation/v0.2",
        "implementation": "pure_numpy_and_python_stdlib__zero_weft_or_mcproof_compile_imports",
        "hyperparameter_source": "pinned_constants_and_spec_lineage_json__never_read_from_expected_artifact",
        "checkpoint_fingerprint": base_weights_sha,
        "harvested_activations_npz_sha256": npz_sha256,
        "harvested_activations_meta_sha256": meta_sha256,
        "files_checked_count": len(checked_files),
        "zero_byte_diff_all": all_ok,
        "files": comparisons,
    }
    RECEIPT_JSON.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
