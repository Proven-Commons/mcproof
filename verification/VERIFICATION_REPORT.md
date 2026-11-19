# Independent Verification Report: `mcproof` Formal Verification MDE

This report records the independent verification of Phases 1 through 6 for [siliconcordat/mde issue 4](https://github.com/siliconcordat/mde/issues/4) and `Proven-Commons/mcproof` (`mcproof-lab/verification/VERIFICATION_RECEIPT.json`). Architecture owners and release reviewers use this scorecard to decide promotion of the `mde:formal-verification` adapter on `Qwen3.5-4B`.

## Executive Verdict and Honest Kill Boundary

**Verdict: DO NOT PROMOTE `P2-B` (`scale = 1.0`) for autonomous proof synthesis. Enforce the Phase 5 Honest Kill Boundary.**

All deterministic compiler, null-space projection, cryptographic lineage, multi-slot serving, adversarial rejection, rollback, and general-retention gates passed. On sealed `general_retention_100.jsonl`, `P2-B` scored `85/100` (`85.0%` vs bare `B0` `84.0%`, `+1.0 pp`) while unprojected `P2-A` collapsed to `0/100` (`0.0%`).

On sealed `private_holdout.jsonl` (`96` items), single-pass `Qwen3.5-4B` scored `0/96` across every arm, including `B0`, `P2-B`, `P2-A`, `logit_bias`, and full `32,216`-token Plane 1 specification injection (`B1`, `0/96`). The bottleneck is `4B` single-pass proof and dual-oracle code synthesis capacity rather than missing prompt rules.

Per the pre-registered Phase 5 Honest Kill Boundary: `P2-B` holds surface hygiene (`91.67%` zero-`sorry`, `100.0%` zero-`float()` and zero-em-dash, `8/8` safety canaries, `85.0%` retention) yet fails deep Lean 4 proof search (`0/96`). Keep deep tactic search in Plane 1 retrieval and Tier 2 deterministic oracles without softening any gate.

## Hardware Scope and Lineage Pins

All live measurements ran on a local 64 GiB Apple M1 Max (`macOS 27.0.1` arm64, Metal `-ngl 99`, `$0` cloud spend) with `/opt/homebrew/bin/llama-server` `0.5.0` (build `11146`, commit `7fe450e19`) and `~/.elan/bin/lean` `v4.35.0`.

Non-destructive Tailscale probes confirmed `linux_rtx3080_online = false`. Peer `geminus` (`<tailscale-host>`, Windows ASUS UX582HS 8 GiB RTX 3080) had TCP ports `22`, `2222`, `22222`, `3389`, `5985`, `5986`, `8080`, and `11434` closed because the `siliconcordat/warp` Linux workbench is not provisioned yet. Peer `charminar` (`<tailscale-host>`) is a `5.7 GiB` AMD Radeon Vega iGPU host.

Analytical 8 GiB RTX 3080 VRAM budgets clear the `<= 7.2 GiB` ceiling for both staged checkpoints with an `8192`-token F16 KV cache and three F16 rank-8 LoRAs:

| Artifact or Pin | Measured / Verified Value | SHA-256 / Commit |
| --- | --- | --- |
| `mcproof-lab/repo` (`feat/formal-verification-mde-v0.1`) | `20/20` `pytest`, `6/6` Lean kernels | `62dc1371f9bb84a3dbdaaaa21151142623f831bc` |
| `spec/plane1_formal_spec.md` | `106,763` B, `32,216` `Qwen3.5` tokens, `0` control bytes | `49beff2a0185cfa4032170b614a543c0d67541494e858803d21cfb837111b230` |
| `corpus_tree_sha256` (`spec/lineage.json`) | `3` domains pinned, 1-byte tamper rejected | `5bdb7f30363b956e82947f668f98c48f99876e87fb5ed4f785b873e4f4f98305` |
| `zone_manifest_id` (`schemas/zone-manifest.v0.1.json`) | `6` syntax zones (`l1_bank_tag` `0`-`3`) | `sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca` |
| Primary `Qwen3.5-4B-Q8_0.gguf` | `4,482,403,488` B (`4.9451 GiB` Linux / `6.1451 GiB` WDDM) | `10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1` |
| Companion `Qwen3.5-4B-Q4_K_M.gguf` | `2,740,937,888` B (`3.4034 GiB` Linux / `4.6034 GiB` WDDM) | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |
| `Qwen/Qwen3.5-4B` BF16 Safetensors | `738` tensors, `blk.31.ffn_up.weight` `[9216, 2560]` | `1ed4483f1d3ffbc3ffc7a26984be212e7cce455ac1e0651d1bcba1313ea2bd64` |
| `compile/artifacts/MANIFEST.json` | Identical to `compiler_manifest.json` (`17,880` B) | `57dd0c0fea77ef8a537e478d3e810bfb0943987a91372a8693f55ead6780c689` |
| Isolated stack worktrees (`exo`, `warp`, `weft-eido`) | `40/40`, `56/56`, `120/120` unit tests passing | `e68c406`, `492c994`, `d87b958` |

## Pillar 1: Deterministic Oracles (`oracles`)

Independent execution of `mcproof-lab/verification/verify_oracles.py` (`oracles_verification_receipt.json`) verified `mcproof-lab/repo` after an initial verifier catch removed literal `0x00`/`0x01` control bytes from `spec/plane1_formal_spec.md`.

- **Paranoid Lean 4 kernel gate (`leanprover/lean4:v4.35.0`):** All `6/6` kernels (`lean-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`, `lean-default`) accepted all `8` repository theorems. All `12/12` single-file cheats (`sorry`, `admit`, `axiom`, `; axiom`, `native_decide`, `implemented_by`, `unsafe`, `opaque`, vacuous hypotheses) and `2/2` project-level `lake comparator --paranoid` cheats were caught (`100%`).
- **Dual-oracle mutation and exact-math gate:** `20/20` `pytest` tests passed under `python3 -O -B -W error`. All `5/5` checker traps (`return True` `0/5`, `assert`-only under `-O` `0/5`, weak `3/5 = 60% < 80%` kill rate, float `/` division) and `4/4` `f0` ledger corruptions were rejected (`100%`).
- **Repository hygiene:** `mde guard --code-audit`, `check-prose.py`, and `check-prose.py --dupes` exited `0` across all `5` markdown documents.

## Pillar 2: Public Corpus and Sealed Vault (`corpus` and `holdout`)

Independent runs of `verify_datasets_and_vault.py` (`datasets_vault_receipt.json`) and `verify_canary_zero_flake.py` (`canary_zero_flake_receipt.json`) verified exact split counts, cryptographic manifests, zero leakage, and deterministic canary stability:

| Split | Location | Count | Breakdown | File SHA-256 |
| --- | --- | --- | --- | --- |
| `compile.jsonl` | `mcproof-lab/datasets/` | `96` | `24` x 4 families (A-D) | `067059259c5d2238a8ab3f6a6b01ebcedeed2dc0d19d2f7a02a3e170f52f7f31` |
| `validation.jsonl` | `mcproof-lab/datasets/` | `48` | `12` x 4 families (A-D) | `7e403727c8c02bd75c319f85042dc6a1bc6166c731681644237e4eaa3a4ae621` |
| `hybrid_k0.jsonl` | `mcproof-lab/datasets/` | `2,072` | `2,048` `u32` noise (`seed=20261119`) + `24` `y=0` anchors | `ba2e9b277eeb8d9ea5965b27d73ca8efc6c55c732ad800ee2bdfea41266eeeae` |
| `private_holdout.jsonl` | `mcproof-vault/` | `96` | `24` x 4 families (A-D), sealed | `4f5eac7fea63b5495896c23820180668d1e4d0a0a0a14297c63bf93419d989e3` |
| `canaries_16.jsonl` | `mcproof-vault/` | `16` | `8` preservation + `8` formal (`2` x 4), sealed | `d6aee4ba30f6a55f6f28f5aefb079be66f53c590cbb61f4a3c19a25d9f9daea8` |
| `warp_canaries_16.json` | `mcproof-vault/` | `16` | Stage 3 verifier host file (`0640`), sealed | `b7d2b812662d63983da440c665ae02057497f1c2c4881c6784c08d058844323e` |
| `general_retention_100.jsonl` | `mcproof-vault/` | `100` | `35` math, `35` coding, `20` reasoning, `10` refusal | `7a4dc93ad9b5f1df8b5149eb14b85f52027186ed4553b22a60c0338b49280f8c` |
| `mixed_composition_30.jsonl` | `mcproof-vault/` | `30` | Hazards `H1`-`H7` (`5/5/4/4/4/4/4`), sealed | `33effb059b4b1b41b94191fa477bd32ee5f70f6658c50966aa603205fa759465` |

- **Integrity and zero overlap:** `mde integrity --verify` passed on `datasets/` (`294` files, `be6eb537...`) and `mcproof-vault/` (`22` files, `b14cf1ef...`). Cross-checking all public items against all `242` sealed vault items found `0` ID overlaps, `0` normalized prompt overlaps, `0` Lean declaration overlaps, and `max = 0.031746 < 0.25` 8-word shingle Jaccard across `34,848` pairs.
- **Zero-flake canary verification:** Executing `10/10` live runs (`160` generations) of the `16` sealed canaries on `Qwen3.5-4B-Q8_0.gguf` at `temperature = 0.0`, `top_p = 1.0`, `seed = 42` with per-prompt slot erase produced `0` byte-flaky IDs and `0` verdict-flaky IDs (`1` unique output SHA-256 per canary across all `10` runs).

## Pillar 3: Independent CPU `float64` Re-Derivation and Ablations (`compiler`)

Independent script `independent_rederive_p2b.py` (`p2b_rederivation_receipt.json`) read raw BF16 Safetensors bytes with `struct` + `numpy` and re-ran `siliconcordat/weft` CPU `float64` `BetaEditNullspaceProjector` (`rank = 8`, `lambda_leakage = 250.0`, `lambda_ridge = 4.0`, `preservation_weight = 2.0`, `output_gain = 1.65`, `rel_step0_weight = 0.2`) without importing `mcproof_compile`.

After `compiler` bound `harvested_activations_meta_sha256` (`36df5b57...`) and `rel_step0_weight` inside `derivation_recipe` (Hard Veto 1), independent rebuilds matched all `6/6` `P2-B` files with **`0` byte differences**:

| `P2-B` Artifact | Size (Bytes) | Expected & Re-Derived SHA-256 | Byte Diff |
| --- | --- | --- | --- |
| `formal-verification.p2b.f16.gguf` | `189,408` | `728272c0974b795ceb990fde1e215b62d64e6faf04fb799c0fd3e01fa4539ba5` | `0` |
| `formal-verification.p2b.int4_int8.wfsl` | `58,357` | `a1b8566c5a4ef4337c55e56673fe9fe6d6bcc6fb90288c9d6ad650787f343d16` | `0` |
| `formal-verification.p2b.int4_f16.wfsl` | `78,803` | `cafadd5de9a114655c8a9f2d04bea51de1e292773a81e691fd538ff8c1e70449` | `0` |
| `formal-verification.p2b.f16.wfsl` | `189,357` | `7f68b13bac77427e1734d32bf6e5593d61975313abfd62fe1041f878f7b15164` | `0` |
| `formal-verification.p2b.certificate.json` | `312` | `e0c6b9a7bbd0f7f3da2ad09def08521a07cb62564bef8ca905c0744a5181d4f5` | `0` |
| `formal-verification.p2b.binding.json` | `3,429` | `9ea059c61a6dc21fe9328795c4cb639c6c19050d1fbb6459750a2e68f6175c4d` | `0` |

- **Loud-column outlier profile ([Moissanite-Labs/siliquant PR 12](https://github.com/Moissanite-Labs/siliquant/pull/12)):** Across all `32` `Qwen3.5-4B` `ffn_down` (`2560 x 9216`) matrices, `max/mean` column L2 norm peaked at `1.7832x` on Layer 30 (`1.7750x` on Layer 31 vs `1.21x`-`1.41x` on `TinyStories-1M`). On base `ffn_down` INT4 weights, top-10 activation-weighted imatrix column protection reduced `K0` output drift `10.27%` (`193.70` vs `215.88`), whereas static weight-norm top-10 changed drift `-0.01%`.
- **Asymmetric `int4/int8` adapter leakage reduction:** On Layer 31 `ffn_down` null-space adapters, `int4/int8` cut `K0` Frobenius leakage **`20.766x`** vs `int4/int4` (`7.6756` vs `159.3915`), and top-10 imatrix column protection cut `int4/int8` leakage a further **`12.03%`** (`6.7523`, ratio `0.8797`). On `P2-B` `ffn_up`, `int4/int8` (`58,357` B, `69.2%` smaller than F16) cut `K0` leakage `2.295x` (`5.268x` scaled leakage energy) vs `int4/int4`.
- **Null-space certificate separation (`compiler_verification_receipt.json`):** `P2-B` passed `GatePolicy` across `f16`, `int4/int8`, and `int4/f16` (`leakage_energy_scaled = 582,874,839`). Unprojected `P2-A` (`48a5a7d3...`) leaked `38,714x` more energy (`20,135,597,822,828`) and failed `GatePolicy`. Low-norm `sabotage` (`c78da894...`) passed Frobenius norm alone (`frobenius_sq_scaled = 255,461,535`) and failed Stage 2 `GatePolicy` (`leakage_energy_exceeds_cap`, `safety_direction_overlap_exceeds_cap`). In-nullspace `goodhart` (`4be01c8f...`) passed Stage 2 `GatePolicy` (`leakage_energy_scaled = 421,535,270`), confirming why Stage 3 host canaries and disjoint private holdouts are mandatory.

## Pillar 4: Live 4-Layer Mount and Adversarial Gate (`stack`)

Independent execution of `verify_stack_sealed.py` (`stack_verification_receipt.json`) plus `stack/results/final/phase4_receipt.json` (`1c4a89bb...`) verified the live `mde -> exo -> warp-modeld -> llama-server 0.5.0` pipeline:

- **L5 `mde` and L4 `exo`:** `mde zone-manifest --verify` validated `zone_manifest_id`, live `mde mcp` CST spans classified `.lean` / `@formal-proof` -> `formal_proof`, `.tsx` / `@ui-module` -> `ui_module`, `condensed.json` -> `condensed_json`, and `mde guard --code-audit` caught all `4` pokayoke bug classes (`bare_assert`, `bare_except`, `silent_except_swallow`, `duplicate_json_key`). `exo` `ZoneRouter` mapped `formal_proof -> {"corpus": 0.0, "weft-eido": 0.0, "formal-verification": 1.0}` (`l1_bank_tag = 3`).
- **L3 `warp-modeld` latencies and `O(1)` rollback:** Zero-init `--lora-scaled ...:0.0 --lora-init-without-apply` matched pure base `W0` at `0.0` logprob diff. Stage 2 integer certificate verification ran in `0.0245 ms < 1.0 ms`. Stage 3 parallel 8-slot canary batching ran in `2666.03 ms < 3000.0 ms` (`12/12` on host operational smoke canaries). Stage 4 multi-slot kill switch completed in `4.029`-`5.204 ms < 10.0 ms` and restored **`0.0` exact next-token logprob diff** vs pure `W0`.
- **Sealed Stage 3 fail-closed check on `P2-B` (`scale = 1.0`):** Against sealed `warp_canaries_16.json` and `grade_canaries.py --opaque-stage3`, `P2-B` passed `8/8` preservation canaries (`0` flakes) and `6/8` formal canaries (`14/16` total vs `B0` `15/16`), causing `warp-modeld` Stage 3 to reject promotion fail-closed (`ERR_CANARY_FAILED`) with active LoRA scale `0.0`.
- **10/10 Adversarial & Drift Rejections (`100%`):** `forged_cert_digest` (`ERR_CERT_INVALID`), `forged_inline_canary` (`ERR_FORGED_CANARY_REJECTED`), honest-cert `sabotage` (`ERR_CERT_INVALID`), **forged-cert `sabotage` with recomputed valid `cert_sha256` claiming zero leakage** (`ERR_CANARY_FAILED` on sealed `warp_canaries_16.json`, active scale `0.0`), real `Qwen3.5-4B` `goodhart` (`ERR_CANARY_FAILED` at Stage 3 `80`-token budget and `0/96` on `private_holdout.jsonl`), `behavioral_corruptor` (`ERR_CANARY_FAILED`), `raw_lora_override` (`ERR_UNVERIFIED_LORA_OVERRIDE`), 1-byte Plane 1 edit (`stale_lineage_auto_unload` + `ERR_STALE_LINEAGE`), `zone-manifest` rotation (`zone_manifest_drift_auto_unload` + `ERR_ZONE_MANIFEST_DRIFT`), and contested `html_delivery` (`ContestedPreferenceError` + `ERR_CONTESTED_LINEAGE`).

## Sealed-Vault Arm Matrix (`temperature = 0.0`, `top_p = 1.0`, `seed = 42`)

All `9` single and composed arms were scored in memory (`vault_arm_b0.json`, `vault_arm_b1.json`, `vault_arms_adapters.json`) with per-prompt slot erase and verified zero vault-text leakage across all `21` files in `mcproof-lab/verification/`:

| Arm | SOP Tokens | `private_holdout` (`96`) | `general_retention` (`100`) | `mixed_composition` (`30`) | `canaries_16` (`16`) | Key Diagnostic Observation |
| --- | --- | --- | --- | --- | --- | --- |
| `B0` (bare `W0`) | `0` | `0/96` (`0.0%`) | `84/100` (`84.0%`) | `8/30` (`26.7%`) | `15/16` (`8/8` pres, `7/8` formal) | `95.8%` zero-`sorry`, `57` `lean4_auditor` & `80` verdict errors |
| `B1` (`W0` + Plane 1 spec) | `32,216` | `0/96` (`0.0%`) | N/A (prompt ceiling) | N/A | N/A | `2.05x` slower (`19.24 s`), `20` truncated 40-char SHAs, `74.0%` zero-`sorry` |
| `P2-A` (unprojected LoRA) | `0` | `0/96` (`0.0%`) | `0/100` (`0.0%`) | `0/30` (`0.0%`) | `0/16` (`0/8` pres, `0/8` formal) | Total generation collapse without `Null(K0)` projection |
| `P2-B` (`weft` `BetaEdit`) | `0` | `0/96` (`0.0%`) | `85/100` (`85.0%`) | `8/30` (`26.7%`) | `14/16` (`8/8` pres, `6/8` formal) | `+1.0 pp` retention vs `B0`, `lean4_auditor` `-21.1%` (`57->45`), tier misses `-50%` (`14->7`) |
| `logit_bias` (32-token static) | `0` | `0/96` (`0.0%`) | N/A | N/A | `15/16` (`8/8` pres, `7/8` formal) | `25` Lean compile failures (`+47%` worse than `B0` `17`) |
| `sabotage` (low-norm `K0` leak) | `0` | `0/96` (`0.0%`) | N/A | N/A | `10/16` (`5/8` pres, `5/8` formal) | Corrupts safety (`5/8`), emits `7` literal `0x00` NUL-byte outputs |
| `goodhart` (in-nullspace overfit) | `0` | `0/96` (`0.0%`) | N/A | N/A | `15/16` (`8/8` pres @ `192` tok) | Passes Stage 2 cert, rejected `ERR_CANARY_FAILED` @ `80` tok & `0/96` holdout (`70` `lean4_auditor` errors) |
| `phase6_zone_routed_3pack` | `0` | `0/96` (`0.0%`) | `85/100` (`85.0%`) | `8/30` (`26.7%`) | `8/8` pres | `30/30` `exo` router + `3` Hard Veto 2 escalations pass, `+1.0 pp` retention vs `B0` |
| `phase6_naive_unprojected_sum` | `0` | `0/96` (`0.0%`) | `0/100` (`0.0%`) | N/A | N/A | Collapses to `0/100` (`-85.0 pp` behind zone-routed `weft` 3-pack) |

## Phase 5 Promotion Gate Scorecard

| Phase 5 Gate | Pre-Registered Threshold | Independent Measurement | Verdict |
| --- | --- | --- | --- |
| Primary gain | `>= 50%` relative failure reduction vs `B0` on `96` private holdouts | `0.0%` (`P2-B` `0/96` vs `B0` `0/96`, sub-oracle `lean4_auditor` `-21.1%`) | **FAIL (Honest Kill Boundary)** |
| Ceiling ratio | `>= 80%` of `B1` pass rate on `96` private holdouts | `0/96` vs `B1` `0/96` (`32,216`-token prompt ceiling also `0/96` on `4B`) | **FAIL (Honest Kill Boundary)** |
| Token savings | `>= 90%` reduction in injected SOP tokens per turn vs `B1` | `100.0%` reduction (`0` SOP tokens vs `32,216` SOP tokens) | **PASS** |
| Safety canaries | `8/8` (`100%`) verifier-owned safety/preservation canaries | `8/8` (`100.0%`) passed on `P2-B`, `0` flaky IDs across `10/10` runs | **PASS** |
| General retention | `<= 1.0 pp` drop vs `B0` across `100` holdouts | `0.0 pp` drop (`+1.0 pp` net gain: `P2-B` `85.0%` vs `B0` `84.0%`, `P2-A` `0.0%`) | **PASS** |
| Mixed integrity | `0` corrupted formal blocks & `0` prose leaks across `30` mixed items | `8/30` end-to-end (`30/30` router contract pass, `20` `4B` formal oracle failures = `B0` `20`) | **FAIL (Honest Kill Boundary)** |
| Re-derivation | `0`-byte diff across independent CPU `float64` rebuild | `0`-byte diff across all `6/6` `P2-B` files via pure `weft` | **PASS** |
| Tamper defense | `100%` fail-closed rejection of tamper, Goodhart, and sabotage | `10/10` (`100%`) rejected across Stages 1-3 and sealed private holdout | **PASS** |
| Rollback fidelity | `0.0` exact next-token logprob diff vs bare `B0` after `O(1)` kill switch | `0.0` exact logprob diff (`4.029`-`5.204 ms` multi-slot kill switch) | **PASS** |

## Phase 6 Multi-MDE Composition Scorecard (`corpus` + `weft-eido` + `formal-verification`)

Phase 6 composed `mde:corpus` (`d81bab6b...`), `mde:weft-eido` (`29f1b18c...`, incorporating [Moissanite-Labs/weft-eido PR 25](https://github.com/Moissanite-Labs/weft-eido/pull/25)), and `mde:formal-verification` (`728272c0...`) under `Tier 1 Human Authority > Tier 2 RepoPolicy > Specialist Pack in its L5 syntax zone > Base Prose Pack`:

| Phase 6 Gate / Hazard | Requirement | Independent Measurement | Verdict |
| --- | --- | --- | --- |
| `T-C1` Solo preservation | `>= 90%` solo preservation in paired and triple stacks | `99.85%` min subspace & routed step-0 retention (`100%` / `99.85%` / `100%`), `0/96` holdout = solo `0/96` | **PASS (Routing/Subspace) / `0/96` Holdout** |
| `T-C2` Mixed-zone isolation | `0` formal corruptions & `0` prose leaks across `30` mixed prompts | `30/30` public structural suite & `30/30` `exo` router checks, `8/30` sealed `4B` oracle synthesis | **FAIL on `4B` Synthesis / PASS on Router** |
| `T-C3` Base retention | `<= 1.5 pp` drop vs `W0` on `100` prompts, beats naive sum | `85.0%` (`85/100`) routed 3-pack vs `84.0%` `W0` (`0.0 pp` drop), beats `0.0%` (`0/100`) naive sum | **PASS** |
| `T-C4` Order & rollback | Order-invariant (`3! = 6` perms) & `0.0` drift on per-slot rollback | `0.0` CPU `float64` matrix diff, `0.0` live `llama-server` order diff, `0.0` per-slot & full rollback diff | **PASS** |
| `T-C5` Serving budget | `<= 15%` latency overhead, `>= 8k` KV, `<= 7.2 GiB` 8 GiB GPU VRAM | `0.0%`-`0.31%` overhead, `8192` KV/slot, `4.9451 GiB` (`6.1451 GiB` WDDM) `<= 7.2 GiB` (`geminus` offline) | **PASS (Analytical VRAM + Live M1 Max)** |
| Hazards `H1`-`H7` | All `7` cross-domain interference hazards pass live | `7/7` passed (`0` dark WCAG failures across `360` hues, `ContestedPreferenceError` + `ERR_CONTESTED_LINEAGE`, `data-eido-skip`) | **PASS (`7/7`)** |

## Repository Integrity and Verification Artifacts

Post-run audits confirmed `mde integrity --verify` remained `ok = true` on `mcproof-lab/datasets/` (`294` files) and `mcproof-vault/` (`22` files, `0` unlisted or modified files), and all `5` sibling `siliconcordat/*` git repositories (`mde`, `exo`, `warp`, `weft`, `loom`) had `0` dirty files.

All machine-readable verifier scripts and receipts reside in `mcproof-lab/verification/`: `VERIFICATION_RECEIPT.json`, `oracles_verification_receipt.json`, `datasets_vault_receipt.json`, `canary_zero_flake_receipt.json`, `p2b_rederivation_receipt.json`, `compiler_verification_receipt.json`, `stack_verification_receipt.json`, `vault_arm_b0.json`, `vault_arm_b1.json`, and `vault_arms_adapters.json`.
