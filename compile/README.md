# mcproof-compile

`mcproof-compile` compiles and tests low-rank weight adapters for `Qwen3.5-4B` on formal verification tasks. It solves a closed-form CPU `float64` null-space `BetaEdit` update from cached activations, emits integer-certified containers, and grades baselines and negative controls against `mcproof` verification oracles. Maintainers and verifiers use it to audit Phase 2 and Phase 3 results on local hardware with zero cloud spend.

## Determinism boundary

Compilation splits into two stages with distinct reproducibility guarantees:

- **Stage A (`activation_harvester.py`, hardware-specific):** Runs `Qwen3.5-4B` forward passes in `bfloat16` on the local accelerator (`mps`, `cuda`, or `cpu`). Because `bfloat16` reductions differ across backends, harvested activations are pinned by `harvested_activations.npz` and verified via `hmac.compare_digest` against `npz_sha256` in `harvested_activations.meta.json` before reuse.
- **Stage B (`compiler_suite.py` and `rederive.py`, bit-exact):** Solves `BetaEdit` in pure CPU `float64`, extracts `(B_64, A_64)` before `stage_edit`, and verifies identical `projector_epoch` and covariance digests across `f16`, `int4/int8`, and `int4/f16` certificates. Re-derivation rebuilds from `compiler_suite` constants and `spec/lineage.json`, matching `9/9` `P2-B` files with `0`-byte diff.

## Pre-registered gates, ablations, and negative efficacy

All three `P2-B` certificates pass fixed `PRE_REGISTERED_GATE_POLICY` caps (`||dW||_F^2 <= 25.0`, `||dW||_2^2 <= 16.0`, `leakage <= 45.0`, `safety_dot^2 <= 1e-4`). Unprojected `P2-A` and low-norm `sabotage` fail Stage 2, while `forged_cert`, `stale_lineage`, `drifted_zone_manifest`, and `forged_canary` fail closed in `artifacts/controls/control_gate_verification_receipt.json`.

`goodhart_patch` is solved inside `Null(K0)`, so linear Stage 2 bounds admit it by design. Behavioral corruption from `goodhart_patch` is caught by Stage 3 verifier domain canaries and Phase 5 holdout rather than Stage 2.

In `artifacts/ablations/loud_column_ablation.json`, measurements on the compiled `P2-B` `ffn_up` adapter (`2.295x` `int4/int8` vs `int4/int4` leakage ratio, `0.9998x` top-10 column protection ratio, `-0.01%` base `ffn_down` INT4 loud-column drift delta) are separated from the seeded Gaussian null-space probe on `ffn_down` (`20.766x`).

Public validation (`validation.jsonl`, `48` prompts, `artifacts/evaluation/validation_scorecard.json`) records `efficacy_verdict = REJECTED_NEGATIVE_EFFICACY`. Pass counts order as `P2-A 0/48 [0.00%] < P2-B 2/48 [4.17%] < B0 4/48 [8.33%] = goodhart 4/48 [8.33%] < constant logit_bias 6/48 [12.50%] < B1 8/48 [16.67%]`, with `p2b_relative_failure_reduction_vs_b0 = -0.045455` (`0` SOP tokens injected for `P2-B` vs `32,216` for `B1`).

## Prerequisites and reproduction

Pure-Python unit tests (`safetensors_io`, `hardware_probe`, `activation_harvester`, `evaluator`) require only `python >= 3.11`, `pytest`, and `numpy`:

```bash
PYTHONHASHSEED=0 python3 -m pytest compile/tests -W error -v
```

Full integration tests, `9/9` `0`-byte re-derivation, and pipeline execution require `siliconcordat/weft`, `siliconcordat/warp`, and `siliconcordat/exo` on `PYTHONPATH`, plus `Qwen3.5-4B` Safetensors and GGUF checkpoints under `compile/checkpoints/` and `harvested_activations.npz` under `compile/artifacts/`:

```bash
export PYTHONPATH="$WEFT_SRC:$WARP_SRC:$EXO_SRC:compile/src:src"
PYTHONHASHSEED=0 python3 -m pytest compile/tests -W error -v
cargo run --quiet --manifest-path "$MDE_ROOT/Cargo.toml" -- guard --code-audit compile/src compile/tests compile/artifacts
```

Re-run deterministic CPU `float64` compilation, controls, ablations, and standalone `9/9` `0`-byte re-derivation:

```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  python3 -m mcproof_compile.pipeline --skip-harvest-if-cached --reuse-cached-eval

PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  python3 -m mcproof_compile.rederive \
  --expected-p2b-dir compile/artifacts/p2b \
  --output-dir /tmp/mcproof_rederived_p2b
```
