"""Pure NumPy/stdlib Safetensors tensor loader into exact CPU float64."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from weft.binding import read_safetensors_header
from weft.quant import bf16_bits_to_float64


def load_safetensors_tensor_f64(checkpoint_dir: Path | str, tensor_name: str) -> np.ndarray:
    """Load a single tensor from a single-file or sharded Safetensors directory into exact float64."""
    ck = Path(checkpoint_dir)
    index_path = ck / "model.safetensors.index.json"
    if index_path.is_file():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        weight_map = idx.get("weight_map", {})
        if tensor_name not in weight_map:
            raise KeyError(f"Tensor {tensor_name!r} not found in {index_path}")
        shard_path = ck / weight_map[tensor_name]
    else:
        shards = sorted(ck.glob("*.safetensors"))
        if not shards:
            raise FileNotFoundError(f"No *.safetensors files found in {ck}")
        shard_path = None
        for cand in shards:
            hdr, _ = read_safetensors_header(cand)
            if tensor_name in hdr:
                shard_path = cand
                break
        if shard_path is None:
            raise KeyError(f"Tensor {tensor_name!r} not found in any shard under {ck}")

    header, data_offset = read_safetensors_header(shard_path)
    meta = header[tensor_name]
    dtype = str(meta["dtype"])
    shape = tuple(int(d) for d in meta["shape"])
    start, end = int(meta["data_offsets"][0]), int(meta["data_offsets"][1])
    nbytes = end - start

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
    if dtype == "F32":
        f32 = np.frombuffer(raw, dtype="<f4").reshape(shape)
        return np.ascontiguousarray(f32.astype(np.float64), dtype=np.float64)
    raise ValueError(f"Unsupported safetensors dtype {dtype!r} for {tensor_name!r}")
