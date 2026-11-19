"""Pure NumPy/stdlib Safetensors tensor loader into exact CPU float64."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

_DTYPE_ELEM_BYTES: dict[str, int] = {
    "BF16": 2,
    "F16": 2,
    "F32": 4,
}


def read_safetensors_header(path: Path) -> tuple[dict[str, Any], int]:
    """Read Safetensors JSON header and return (header_dict, data_start_offset)."""
    with path.open("rb") as fh:
        len_bytes = fh.read(8)
        if len(len_bytes) != 8:
            raise ValueError(f"Truncated safetensors header length: {path.name}")
        header_len = struct.unpack("<Q", len_bytes)[0]
        if header_len == 0 or header_len > 100_000_000:
            raise ValueError(f"Unreasonable safetensors header length: {header_len}")
        hdr_raw = fh.read(header_len)
        if len(hdr_raw) != header_len:
            raise ValueError(f"Truncated safetensors JSON header: {path.name}")
    header = json.loads(hdr_raw.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("Safetensors header must be a JSON object.")
    return header, 8 + header_len


def bf16_bits_to_float64(bits: np.ndarray) -> np.ndarray:
    """Dequantize uint16 BF16 bit patterns into exact CPU float64 values."""
    u16 = np.ascontiguousarray(bits, dtype="<u2")
    u32 = u16.astype(np.uint32) << np.uint32(16)
    return u32.view(np.float32).astype(np.float64)


def load_safetensors_tensor_f64(checkpoint_dir: Path | str, tensor_name: str) -> np.ndarray:
    """Load a single tensor from a single-file or sharded Safetensors directory into exact float64."""
    ck = Path(checkpoint_dir)
    ck_resolved = ck.resolve()
    index_path = ck / "model.safetensors.index.json"
    if index_path.is_file():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        weight_map = idx.get("weight_map", {})
        if not isinstance(weight_map, dict) or tensor_name not in weight_map:
            raise KeyError(f"Tensor {tensor_name!r} not found in {index_path.name}")
        raw_rel = weight_map[tensor_name]
        if not isinstance(raw_rel, str) or not raw_rel.strip() or Path(raw_rel).is_absolute():
            raise ValueError(f"weight_map entry escapes checkpoint dir: {tensor_name!r}")
        shard_path = (ck / raw_rel).resolve()
        if not shard_path.is_relative_to(ck_resolved):
            raise ValueError(f"weight_map entry escapes checkpoint dir: {tensor_name!r}")
        if not shard_path.is_file():
            raise FileNotFoundError(f"Safetensors shard missing for {tensor_name!r}: {shard_path.name}")
    else:
        shards = sorted(ck.glob("*.safetensors"))
        if not shards:
            raise FileNotFoundError(f"No *.safetensors files found in {ck.name}")
        shard_path = None
        for cand in shards:
            cand_resolved = cand.resolve()
            if not cand_resolved.is_relative_to(ck_resolved):
                raise ValueError(f"Safetensors shard symlink escapes checkpoint dir: {cand.name}")
            hdr, _ = read_safetensors_header(cand_resolved)
            if tensor_name in hdr:
                shard_path = cand_resolved
                break
        if shard_path is None:
            raise KeyError(f"Tensor {tensor_name!r} not found in any shard under {ck.name}")

    file_size = shard_path.stat().st_size
    header, data_offset = read_safetensors_header(shard_path)
    if data_offset < 8 or data_offset > file_size:
        raise ValueError(f"Invalid safetensors data_offset {data_offset} for file size {file_size}")
    if tensor_name not in header or not isinstance(header[tensor_name], dict):
        raise KeyError(f"Tensor {tensor_name!r} missing from shard header {shard_path.name}")

    meta = header[tensor_name]
    dtype = str(meta.get("dtype", ""))
    if dtype not in _DTYPE_ELEM_BYTES:
        raise ValueError(f"Unsupported safetensors dtype {dtype!r} for {tensor_name!r}")

    raw_shape = meta.get("shape")
    if not isinstance(raw_shape, list) or any(type(d) is not int or d < 0 for d in raw_shape):
        raise ValueError(f"Invalid tensor shape {raw_shape!r} for {tensor_name!r}")
    shape = tuple(int(d) for d in raw_shape)

    raw_offsets = meta.get("data_offsets")
    if (
        not isinstance(raw_offsets, list)
        or len(raw_offsets) != 2
        or type(raw_offsets[0]) is not int
        or type(raw_offsets[1]) is not int
    ):
        raise ValueError(f"Invalid tensor data_offsets {raw_offsets!r} for {tensor_name!r}")
    start, end = int(raw_offsets[0]), int(raw_offsets[1])
    data_section_size = file_size - data_offset
    if not (0 <= start <= end <= data_section_size):
        raise ValueError(
            f"tensor data_offsets [{start}, {end}] out of bounds for data section size {data_section_size}"
        )

    nbytes = end - start
    expected_bytes = math.prod(shape) * _DTYPE_ELEM_BYTES[dtype]
    if nbytes != expected_bytes:
        raise ValueError(
            f"tensor byte span {nbytes} does not match shape {shape} * {_DTYPE_ELEM_BYTES[dtype]} ({expected_bytes})"
        )

    with shard_path.open("rb") as fh:
        fh.seek(data_offset + start)
        raw = fh.read(nbytes)
    if len(raw) != nbytes:
        raise IOError(f"Truncated read for tensor {tensor_name!r} in {shard_path.name}")

    if dtype == "BF16":
        u16 = np.frombuffer(raw, dtype="<u2").reshape(shape)
        return np.ascontiguousarray(bf16_bits_to_float64(u16), dtype=np.float64)
    if dtype == "F16":
        f16 = np.frombuffer(raw, dtype="<f2").reshape(shape)
        return np.ascontiguousarray(f16.astype(np.float64), dtype=np.float64)
    f32 = np.frombuffer(raw, dtype="<f4").reshape(shape)
    return np.ascontiguousarray(f32.astype(np.float64), dtype=np.float64)
