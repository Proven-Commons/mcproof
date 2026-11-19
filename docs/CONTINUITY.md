# Capability Continuity Record: `mde:formal-verification`

`docs/CONTINUITY.md` is the canonical steward record for the `mde:formal-verification` capability in `Proven-Commons/mcproof`. It preserves the capability identity, three-tier contracts, peer adaptations, scratch reproduction commands, empirical lessons, and open follow-up work across sessions. Engineers and agents modifying `mcproof`, `weft`, `warp`, `exo`, or `mde` read this record before changing interfaces or gates.

## Capability Identity and Human Purpose

- **Capability ID:** `mde:formal-verification` (`adapter_class = class1_rederivable`, `primary_zone = formal_proof`, `l1_bank_tag = 3`)
- **Specification Blueprint:** [siliconcordat/mde issue 4](https://github.com/siliconcordat/mde/issues/4) under the [Siliconcordat Master Plan](https://github.com/siliconcordat/.github/blob/main/MASTER-PLAN.md)
- **Human Purpose:** Test whether formal verification habits compile into `Qwen3.5-4B` weights via `weft` `BetaEdit` null-space projection without degrading general model capabilities or weakening deterministic verification gates.
- **Current Status:** Infrastructure, null-space projection, zero-`weft`-import `9/9` `0`-byte CPU `float64` re-derivation, `9/9` live RPC tamper rejections, `O(1)` rollback (`0.0` top-20 logprob diff, `5.528 ms`), `8/8` safety canaries, and `85.0%` general retention passed. Public `validation.jsonl` (`2/48` vs `B0` `4/48`, `REJECTED_NEGATIVE_EFFICACY`), sealed `private_holdout.jsonl` (`0/96` across `B0`, `P2-B`, and `B1`), and Phase 6 `T-C1` live `step0` drift (`weft-eido` `0.0%` live retention) hit pre-registered fail-closed boundaries. `P2-B` (`scale = 1.0`) is not promoted.

## Three-Tier Placement and Five Hard Vetoes

### Three-Tier Contract

1. **Tier 1 (Human Specification Authority):** Theorem intent, axiom selection, trust-boundary judgment, and resolution of contested domain rules stay under human authority.
2. **Tier 2 (Deterministic Oracles, Zero Weights):** Six-kernel `lake comparator --paranoid` on Lean `v4.35.0` (fail-closed `bwrap` sandboxing by default, anti-spoofing `#eval` ban, external `collectAxioms` check), dual-oracle planted-bug mutation testing (`>= 80%` exact `5 * k >= 4 * n` kill floor under `python3 -I -O -B -W error`), `f0` ledger corruption checks, traversal-safe `formal-claims-audit` verdict checks, vendored `prose_gate.py`, and `mde guard --code-audit` CST checks enforce soundness mechanically.
3. **Tier 3 (Candidate Weight Reflexes):** Six reflexes target weight compilation (`WeakStatement` vacuous-hypothesis hunting, distinct dual-oracle skeletons, exact `int` and `Fraction` arithmetic, mandatory `What is not proved` and `What you must trust` sections, honest `PROVEN`/`VERIFIED`/`KNOWN`/`CONJECTURE` labels, and escape-hatch-free Lean 4).

### Five Hard Vetoes

1. **Zero opaque weight blobs:** Every `Class 1` slab, GGUF LoRA, certificate, binding, gate policy, Warp bundle, and W-MCP metadata file (`9/9` `P2-B` files) must rebuild with `0` byte differences on CPU `float64` from pinned Plane 1 files, `Hybrid K0`, and base checkpoint weights (`verification/independent_rederive_p2b.py`).
2. **Zero silent conflict resolution:** Contested syntax zones (`html_delivery`) raise `ContestedPreferenceError` at L4 `exo` and `ERR_CONTESTED_LINEAGE` at L3 `warp-modeld`, dropping active adapter scales to `0.0`.
3. **Zero stale lineage:** Any `1`-byte edit to the `11` tracked Plane 1 files invalidates `corpus_tree_sha256` (`5bdb7f30363b956e82947f668f98c48f99876e87fb5ed4f785b873e4f4f98305`) and triggers automatic adapter unload (`ERR_STALE_LINEAGE`).
4. **Zero adapter-supplied canaries:** Inline or forged canary fields inside an adapter bundle fail closed (`ERR_FORGED_CANARY_REJECTED`), and `ExternalCommandCanaryRunner` rejects aggregate-only JSON lacking per-canary `outcomes` (`>= min_preservation`).
5. **Zero gate-lowering on Honest Kill Boundary:** Failing public validation (`2/48 < B0 4/48`), primary private holdout (`0/96`), or live `T-C1` `step0` composition retention keeps deep proof search in Plane 1 retrieval and Tier 2 compiler loops without lowering any threshold.

## Peer Responsibilities and Companion Changes

| Layer and Peer | Responsibility | Verified Adaptation and Reference |
| --- | --- | --- |
| L5 `siliconcordat/mde` (`52ce017`) | Canonical `zone-manifest.v0.1.json` (`sha256:4e00656c...`), CST span tagging, `SHA256SUMS` integrity, `guard --code-audit` | Verified directly against `schemas/zone-manifest.v0.1.json`, `datasets/SHA256SUMS` (`312953bc...`), and repository `.py`/`.json` files |
| L4 `siliconcordat/exo` | `ZoneRouter` routing `formal_proof` to `formal-verification` (`l1_bank_tag = 3`), `ContestedPreferenceError` on `html_delivery`, `data-eido-skip` audit | [siliconcordat/exo PR four](https://github.com/siliconcordat/exo/tree/feat/mde4-phase4-phase6-stack) (`e68c406`, `40/40` tests, mirrored in `stack/patches/exo-mde4-phase4-phase6-stack.patch`) |
| L3 `siliconcordat/warp` | Four-stage admission gate (`verify_stage1`, fixed `PRE_REGISTERED_GATE_POLICY`, per-canary opaque Stage 3 outcomes, `< 10 ms` multi-slot `O(1)` kill switch) | [siliconcordat/warp PR 5](https://github.com/siliconcordat/warp/pull/5) (`390176c`, `57/57` tests, mirrored in `stack/patches/warp-mde4-phase4-live-gate.patch`) |
| L2 `siliconcordat/weft` (`3d66f07`) | CPU `float64` `BetaEditNullspaceProjector`, `FixedRadixCertificate`, `weft-slab/v0.1`, deterministic F16 GGUF v3 LoRA writer | Cross-checked by zero-`weft`-import pure-NumPy rebuild across all `9/9` `P2-B` outputs (`verification/p2b_rederivation_receipt.json`) |
| Companion `Moissanite-Labs/weft-eido` | Phase 6 UI contrast audit across `360` OKLCH hues (`0` dark-theme WCAG failures) | Tracked in `stack/patches/weft-eido-pr25-contrast-audit.patch` (`d87b958`, `120/120` tests) |
| Companion `Moissanite-Labs/siliquant` | Loud-column activation-weighted quantization ablation (`ffn_down` probe and compiled `P2-B` `ffn_up`) | [Moissanite-Labs/siliquant PR 12](https://github.com/Moissanite-Labs/siliquant/pull/12) (`67b29a4`, `2.295x` on compiled `P2-B` `ffn_up`, `20.766x` on seeded Gaussian `ffn_down` null-space probe) |

## Scratch Reproduction and Audit Runbook

### 1. Standalone Fresh Clone vs Full Bootstrapped Suite

```sh
# Standalone fresh clone (only pytest + numpy installed):
python3 ./bin/mcproof --json lineage --verify
python3 -O -B -W error -m pytest -v

# Bootstrap pinned external repos and run full Tier 2 gates:
./bin/bootstrap-deps --with-siliconcordat
./bin/mcproof --json lineage --verify --require-deps
./bin/mcproof --json integrity datasets
./bin/mcproof --json bar
./bin/mcproof --allow-unsandboxed --json lean --project
./bin/mcproof --json mde-guard .
```

### 2. Zero-Import `0`-Byte CPU `float64` Re-Derivation of All `9/9` `P2-B` Files

Stage `Qwen/Qwen3.5-4B` BF16 Safetensors (`MCPROOF_CHECKPOINTS_DIR`) and `harvested_activations.npz` (`sha256: 413a1123...`, verified against committed `compile/artifacts/harvested_activations.meta.json`):

```sh
PYTHONPATH="" PYTHONHASHSEED=0 python3 -I verification/independent_rederive_p2b.py
```

### 3. Live 4-Layer Stack Mount and Sealed-Vault Verification

With `llama-server` `0.5.0+` (`LLAMA_SERVER_BIN`), `Qwen3.5-4B-Q8_0.gguf` (`sha256: 10cc391b...`), and the private holdout vault mounted read-only outside git at `<workspace>/mcproof-vault/`:

```sh
MCPROOF_LIVE_LLAMA_TESTS=1 python3 -m pytest stack/tests/test_stack_suite.py -v
MCPROOF_VAULT_DIR=<workspace>/mcproof-vault python3 verification/verify_datasets_and_vault.py
MCPROOF_VAULT_DIR=<workspace>/mcproof-vault python3 verification/verify_canary_zero_flake.py
MCPROOF_VAULT_DIR=<workspace>/mcproof-vault python3 verification/verify_stack_sealed.py
python3 verification/build_final_receipt.py
```

## Retained Empirical Lessons

1. **Null-space projection prevents catastrophic forgetting (`85.0%` vs `0.0%`), while single-layer rank-8 steering regresses on public validation (`2/48` vs `B0` `4/48`):** At matched Frobenius norm (`4.336`), unprojected `P2-A` leaked `34,545x` more `K0` energy than `P2-B` (`2.01e13` vs `5.83e8` scaled) and collapsed to `0/100` on `general_retention_100.jsonl` (`P2-B` and zone-routed 3-pack both scored `85/100` vs `B0` `84/100`). However, on public `validation.jsonl` (`48` items), `P2-B` (`2/48`) trailed bare `B0` (`4/48`), `goodhart` (`4/48`), constant `logit_bias` (`6/48`), and `B1` (`8/48`).
2. **Single-pass `4B` proof synthesis is capacity-bound (`0/96` across `B0`, `P2-B`, and `B1`):** Injecting the full `32,216`-token Plane 1 spec (`B1`, `2.05x` slower, `b1_prefix_cache_parity_verified = true` across `3` live full-string items) also scored `0/96` on `private_holdout.jsonl`.
3. **Asymmetric `int4/int8` leakage gain depends strongly on target matrix geometry (`2.295x` on `P2-B` `ffn_up` vs `20.766x` on `ffn_down` probe):** On compiled `P2-B` (`blk.31.ffn_up.weight`, `9216 x 2560`), `int4/int8` (`58,357` B, `69.2%` smaller than F16) reduced `K0` Frobenius leakage `2.295x` vs `int4/int4` (`top-10` column protection `0.9998x`). The larger `20.766x` (`0.8797x` with top-10 imatrix protection) occurs on a seeded Gaussian null-space probe on `ffn_down` (`2560 x 9216`), where base INT4 activation-weighted imatrix protection cuts `K0` output drift `10.27%` while static weight-norm top-10 shifts drift `-0.01%`.
4. **CPU linear subspace orthogonality (`99.85%`) does not imply live nonlinear `step0` composition invariance (`T-C1` FAIL):** When `weft-eido` and `corpus` co-activate at `[0.2, 1.0, 0.0]` (`ui_module`), CPU linear subspace alignment stays `>= 99.85%`, yet nonlinear transformer propagation shifts `weft-eido` live `step0` logprobs by `0.0611` (`31.77x` its `0.0019` solo shift, `0.0%` live retention). Gate `T-C1` must measure live `step0` drift directly without `max()` fallback to CPU subspace scores.

## Evidence Limits and Next Actions

1. **Live 8 GiB RTX 3080 workbench telemetry replay (`geminus`):** Live serving ran on a 64 GiB Apple M1 Max (`llama-server 0.5.0`, `$0` cloud) while `geminus` (`UX582HS`, 8 GiB RTX 3080) had SSH and RPC ports closed (`linux_rtx3080_online = false`, `vram_measurement_kind = analytical_projection_not_nvml`). Replay `T-C5` `nvidia-smi` telemetry once Linux workbench SSH is provisioned.
2. **Multi-turn Plane 1 retrieval and Tier 2 repair loop harness:** Build a bounded multi-turn Plane 1 section-retrieval + Tier 2 `mcproof grade` diagnostic feedback loop (`k <= 4` compiler rounds) and benchmark pass@k across `validation.jsonl` and `private_holdout.jsonl` under unchanged Tier 2 oracles.
