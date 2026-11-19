# Capability Continuity Record: `mde:formal-verification`

`docs/CONTINUITY.md` is the canonical steward record for the `mde:formal-verification` capability in `Proven-Commons/mcproof`. It preserves the capability identity, three-tier contracts, peer adaptations, scratch reproduction commands, empirical lessons, and open follow-up work across sessions. Engineers and agents modifying `mcproof`, `weft`, `warp`, `exo`, or `mde` read this record before changing interfaces or gates.

## Capability Identity and Human Purpose

- **Capability ID:** `mde:formal-verification` (`adapter_class = class1_rederivable`, `primary_zone = formal_proof`, `l1_bank_tag = 3`)
- **Specification Blueprint:** [siliconcordat/mde issue 4](https://github.com/siliconcordat/mde/issues/4) under the [Siliconcordat Master Plan](https://github.com/siliconcordat/.github/blob/main/MASTER-PLAN.md)
- **Human Purpose:** Test whether formal verification habits compile into `Qwen3.5-4B` weights via `weft` `BetaEdit` null-space projection without degrading general model capabilities or weakening deterministic verification gates.
- **Current Status:** Infrastructure, null-space projection, `0`-byte CPU `float64` re-derivation, `10/10` adversarial rejection, `O(1)` rollback, `8/8` safety canaries, and `85.0%` general retention passed. Single-pass `Qwen3.5-4B` proof synthesis hit the pre-registered Phase 5 Honest Kill Boundary (`0/96` across `B0`, `P2-B`, and `B1`). `P2-B` (`scale = 1.0`) is not promoted for autonomous single-pass proof synthesis.

## Three-Tier Placement and Five Hard Vetoes

### Three-Tier Contract

1. **Tier 1 (Human Specification Authority):** Theorem intent, axiom selection, trust-boundary judgment, and resolution of contested domain rules stay under human authority.
2. **Tier 2 (Deterministic Oracles, Zero Weights):** Six-kernel `lake comparator --paranoid` on Lean `v4.35.0`, dual-oracle planted-bug mutation testing (`>= 80%` kill floor under `python3 -O -B -W error`), `f0` ledger corruption checks, `formal-claims-audit` verdict checks, and `mde guard --code-audit` CST checks enforce soundness mechanically.
3. **Tier 3 (Candidate Weight Reflexes):** Six reflexes target weight compilation (`WeakStatement` vacuous-hypothesis hunting, distinct dual-oracle skeletons, exact `int` and `Fraction` arithmetic, mandatory `What is not proved` and `What you must trust` sections, honest `PROVEN`/`VERIFIED`/`KNOWN`/`CONJECTURE` labels, and escape-hatch-free Lean 4).

### Five Hard Vetoes

1. **Zero opaque weight blobs:** Every `Class 1` slab, GGUF LoRA, certificate, and binding file must rebuild with `0` byte differences on CPU `float64` from pinned Plane 1 files, `Hybrid K0`, and base checkpoint weights (`compile/artifacts/p2b/formal-verification.p2b.binding.json`).
2. **Zero silent conflict resolution:** Contested syntax zones (`html_delivery`) raise `ContestedPreferenceError` at L4 `exo` and `ERR_CONTESTED_LINEAGE` at L3 `warp-modeld`, dropping active adapter scales to `0.0`.
3. **Zero stale lineage:** Any `1`-byte edit to the `11` tracked Plane 1 files invalidates `corpus_tree_sha256` (`5bdb7f30363b956e82947f668f98c48f99876e87fb5ed4f785b873e4f4f98305`) and triggers automatic adapter unload (`ERR_STALE_LINEAGE`).
4. **Zero adapter-supplied canaries:** Inline or forged canary fields inside an adapter bundle fail closed at Stage 1 (`ERR_FORGED_CANARY_REJECTED`). Stage 3 reads only host-owned `0640` canary files.
5. **Zero gate-lowering on Honest Kill Boundary:** Failing primary holdout synthesis (`0/96`) keeps deep proof search in Plane 1 retrieval and Tier 2 compiler loops without lowering any threshold.

## Peer Responsibilities and Companion Changes

| Layer and Peer | Responsibility | Verified Adaptation and Reference |
| --- | --- | --- |
| L5 `siliconcordat/mde` (`52ce017`) | Canonical `zone-manifest.v0.1.json` (`sha256:4e00656c...`), CST span tagging, `SHA256SUMS` integrity, `guard --code-audit` | Verified directly against `schemas/zone-manifest.v0.1.json` and `270` repository `.py`/`.json` files |
| L4 `siliconcordat/exo` | `ZoneRouter` routing `formal_proof` to `formal-verification` (`l1_bank_tag = 3`), `ContestedPreferenceError` on `html_delivery`, `data-eido-skip` audit | [siliconcordat/exo PR four](https://github.com/siliconcordat/exo/tree/feat/mde4-phase4-phase6-stack) (`e68c406`, `40/40` tests, mirrored in `stack/patches/exo-mde4-phase4-phase6-stack.patch`) |
| L3 `siliconcordat/warp` | Four-stage admission gate (`verify_stage1`, integer `GatePolicy`, parallel 8-slot Stage 3 canaries, `< 10 ms` multi-slot `O(1)` kill switch) | [siliconcordat/warp PR 5](https://github.com/siliconcordat/warp/pull/5) (`492c994`, `56/56` tests, mirrored in `stack/patches/warp-mde4-phase4-live-gate.patch`) |
| L2 `siliconcordat/weft` (`3d66f07`) | CPU `float64` `BetaEditNullspaceProjector`, `FixedRadixCertificate`, `weft-slab/v0.1`, deterministic F16 GGUF v3 LoRA writer | Verified `0`-byte diff across all `6/6` `P2-B` outputs (`verification/p2b_rederivation_receipt.json`) |
| Companion `Moissanite-Labs/weft-eido` | Phase 6 UI contrast audit across `360` OKLCH hues (`0` dark-theme WCAG failures) | Tracked in `stack/patches/weft-eido-pr25-contrast-audit.patch` (`d87b958`, `120/120` tests) |
| Companion `Moissanite-Labs/siliquant` | Loud-column activation-weighted quantization ablation (`ffn_down` and `ffn_up`) | [Moissanite-Labs/siliquant PR 12](https://github.com/Moissanite-Labs/siliquant/pull/12) (`67b29a4`, `20.766x` `int4/int8` leakage reduction) |

## Scratch Reproduction and Audit Runbook

### 1. Deterministic Oracles, Lineage, Dataset Integrity, and Unit Suite

Run from the repository root (`<workspace>/mcproof-lab/repo/` with Plane 1 source clones at `<workspace>/mcproof-lab/deps/`):

```sh
./bin/mcproof --json lineage --verify
./bin/mcproof --json integrity datasets
./bin/mcproof --json lean --project
./bin/mcproof --json mde-guard .
python3 -O -B -m pytest -v
```

### 2. Independent `0`-Byte CPU `float64` Re-Derivation of `P2-B`

With `Qwen/Qwen3.5-4B` BF16 Safetensors staged at `compile/checkpoints/Qwen3.5-4B` and harvested activations at `compile/artifacts/harvested_activations.npz` (`sha256: 413a1123...`):

```sh
PYTHONHASHSEED=0 python3 verification/independent_rederive_p2b.py
```

### 3. Live 4-Layer Stack Mount and Sealed-Vault Verification

With `llama-server` `0.5.0+` (`LLAMA_SERVER_BIN`), `Qwen3.5-4B-Q8_0.gguf` (`sha256: 10cc391b...`), and the private holdout vault mounted read-only outside git at `<workspace>/mcproof-vault/`:

```sh
MCPROOF_LIVE_LLAMA_TESTS=1 python3 -m pytest stack/tests/test_stack_suite.py -v
MCPROOF_VAULT_DIR=<workspace>/mcproof-vault python3 verification/verify_datasets_and_vault.py
MCPROOF_VAULT_DIR=<workspace>/mcproof-vault python3 verification/verify_canary_zero_flake.py
MCPROOF_VAULT_DIR=<workspace>/mcproof-vault python3 verification/verify_stack_sealed.py
```

## Retained Empirical Lessons

1. **Null-space projection prevents catastrophic forgetting (`85.0%` vs `0.0%`):** At matched Frobenius norm (`4.336`), unprojected `P2-A` leaked `38,714x` more `K0` energy than `weft` `BetaEdit` `P2-B` (`2.01e13` vs `5.83e8` scaled) and collapsed from `84.0%` (`B0`) to `0.0%` (`0/100`) on `general_retention_100.jsonl`. `P2-B` and the zone-routed 3-pack both scored `85.0%` (`85/100`), beating naive unprojected 3-pack summation (`0/100`) by `+85.0 pp`.
2. **Single-pass `4B` proof synthesis is capacity-bound, not prompt-bound (`0/96` on `B1`):** Injecting the full `32,216`-token Plane 1 spec (`B1`, `2.05x` slower) also scored `0/96` on `private_holdout.jsonl`. `P2-B` cut `lean4_auditor` violations `-21.1%` and missing tier labels `-50.0%` (`100%` zero-`float()`), showing rank-8 linear edits steer local structure while tactic closure needs Tier 2 compiler loops.
3. **Asymmetric `int4/int8` plus imatrix column protection preserves null-space orthogonality:** Quantizing `B` to `int4` and input-nullspace factor `A` to `int8` cut Layer 31 `ffn_down` `K0` Frobenius leakage `20.766x` vs `int4/int4` (`7.6756` vs `159.3915`), and activation-weighted top-10 column protection reduced leakage an additional `12.03%` (`6.7523`) at `69.2%` byte savings vs F16.
4. **Stage 2 spectral certificates and Stage 3 host canaries catch orthogonal attack classes:** Low-norm `sabotage` failed Stage 2 `GatePolicy` (`ERR_CERT_INVALID`). When given a forged valid certificate digest claiming zero leakage, `sabotage` passed Stage 2 and was caught at Stage 3 by host canaries (`ERR_CANARY_FAILED`). In-nullspace `goodhart` legitimately passed Stage 2 (`leakage_energy_scaled = 421,535,270`) and was caught at Stage 3 (`80`-token budget) and on `private_holdout.jsonl` (`0/96`).

## Evidence Limits and Next Actions

1. **Live 8 GiB RTX 3080 workbench telemetry replay (`geminus`):** Live serving ran on a 64 GiB Apple M1 Max (`llama-server 0.5.0`, `$0` cloud) while `geminus` (`UX582HS`, 8 GiB RTX 3080) had SSH ports closed (`linux_rtx3080_online = false`). Analytical budgets clear `<= 7.2 GiB` (`4.9451 GiB` Linux / `6.1451 GiB` WDDM on `Q8_0`, `3.4034` / `4.6034 GiB` on `Q4_K_M`). Next action: replay `T-C5` `nvidia-smi` telemetry on `geminus`.
2. **Multi-turn Plane 1 retrieval and Tier 2 repair loop harness:** Single-pass `Qwen3.5-4B` generation (`B0`, `B1`, `P2-B`) scored `0/96` on `private_holdout.jsonl`. Next action: build a bounded multi-turn Plane 1 section-retrieval + Tier 2 `mcproof grade` diagnostic feedback loop (`k <= 4` compiler rounds) and benchmark pass@k across `validation.jsonl` and `private_holdout.jsonl` under the unchanged Tier 2 oracles.
