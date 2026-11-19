# mcproof-compile

`mcproof-compile` is the deterministic CPU `float64` weight compiler and evaluation suite for the Formal Verification Multi-Domain Editing proof of concept. It extracts hidden activations from `Qwen3.5-4B` and solves a closed-form null-space `BetaEdit` update over `Hybrid K0` calibration data. It is built for maintainers and independent verifiers reproducing Phase 2 and Phase 3 results on local hardware with zero cloud spend.

Every run emits certified `weft-slab/v0.1` containers, F16 GGUF v3 LoRA adapters, and exact integer bounds, then scores all baselines and negative controls against Tier 2 verification oracles.

## Directory layout

- `checkpoints/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q8_0.gguf`: Primary `Q8_0` GGUF checkpoint (`4.17 GiB`) served by `llama-server` (`0.5.0`, commit `7fe450e19`).
- `checkpoints/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q4_K_M.gguf`: Companion `Q4_K_M` GGUF checkpoint (`2.55 GiB`) staged for Windows WDDM 8 GiB RTX 3080 VRAM headroom.
- `checkpoints/Qwen3.5-4B/`: Full `BF16` Safetensors checkpoint, config, tokenizer, and `chat_template.jinja` bound by five-layer `weft.binding` digests.
- `src/mcproof_compile/hardware_probe.py`: Phase 2 local host, `llama-server`, non-destructive Tailscale peer (`geminus` and `charminar`) reachability, and 8 GiB RTX 3080 VRAM fit audit.
- `src/mcproof_compile/activation_harvester.py`: Forward-pass harvester extracting `blk.31.ffn_up.weight` keys (`d_in = 2560`), SwiGLU + zero-centered `RMSNorm` target residuals (`d_out = 9216`), and `ffn_down` `Hybrid K0` probes (`d_in = 9216`).
- `src/mcproof_compile/compiler_suite.py`: Pure CPU `float64` compiler producing Arm `P2-B` (`f16/f16` GGUF, `int4/int8` slab, `int4/f16` slab, integer `FixedRadixCertificate`, `BindingManifest`, `warp-modeld` `AdapterBundle`, and vendor-namespaced `_meta["gg.siliconcordat/mde"]`), Arm `P2-A`, and Phase 6 companion packs (`corpus`, `weft-eido`).
- `src/mcproof_compile/ablations.py`: `siliquant` top-10 `ffn_down` outlier-column protection ablation across all 32 layers, constant output-token logit-bias control, low-norm sabotage patch, in-nullspace Goodhart overfit patch, and four `warp-modeld` tamper bundles.
- `src/mcproof_compile/rederive.py`: Standalone independent `0`-byte CPU `float64` re-derivation runner.
- `src/mcproof_compile/evaluator.py`: Deterministic live `llama-server` evaluation runner (`temperature = 0.0`, `top_p = 1.0`) across `B0`, `B1`, `P2-A`, `P2-B`, `logit_bias`, `sabotage`, and `goodhart`.

## Reproducing compilation and 0-byte re-derivation

Run the unit suite and code audit first:

```bash
PYTHONHASHSEED=0 .venv/bin/pytest -W error -v
cargo run --quiet --manifest-path "$MDE_ROOT/Cargo.toml" -- guard --code-audit src
```

Run the full Phase 2 and Phase 3 compilation and `validation.jsonl` evaluation pipeline:

```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -m mcproof_compile.pipeline
```

Run an independent `0`-byte CPU `float64` re-derivation of `P2-B` into any target directory:

```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python -m mcproof_compile.rederive \
  --expected-p2b-dir artifacts/p2b \
  --output-dir /tmp/mcproof_rederived_p2b
```
