# Independent Verification Report: `mcproof` Formal Verification MDE

This report records the independent verification of Phases 1 through 6 for [siliconcordat/mde issue 4](https://github.com/siliconcordat/mde/issues/4) and `Proven-Commons/mcproof` (`verification/VERIFICATION_RECEIPT.json`). Architecture owners and release reviewers use this scorecard to audit the `mde:formal-verification` adapter on `Qwen3.5-4B`.

## Executive Verdict and Honest Kill Boundary

**Verdict: DO NOT PROMOTE `P2-B` (`scale = 1.0`) for autonomous proof synthesis. Enforce the Phase 5 Honest Kill Boundary.**

Null-space projection, cryptographic lineage, multi-slot rollback (`0.0` top-20 logprob diff), adversarial rejection (`9/9` live RPC tamper checks plus forged-cert `sabotage` Stage 3 catch), safety canaries (`8/8`, `0` flakes), and general retention (`P2-B` `85.0%` vs bare `B0` `84.0%`, unprojected `P2-A` `0.0%`) passed.

Four empirical and live-composition gates failed closed and block promotion:
1. **Public `validation.jsonl` (`48` items):** `P2-B` scored `2/48` (`4.17%`), trailing bare `B0` (`4/48`, `8.33%`), `goodhart` (`4/48`, `8.33%`), constant `logit_bias` (`6/48`, `12.50%`), and `B1` (`8/48`, `16.67%`), with relative failure reduction `-0.0455` (`efficacy_verdict = REJECTED_NEGATIVE_EFFICACY`).
2. **Sealed `private_holdout.jsonl` (`96` items):** Single-pass `Qwen3.5-4B` scored `0/96` across every arm, including `B0`, `P2-B`, `P2-A`, `logit_bias`, and full `32,216`-token Plane 1 specification injection (`B1`, `0/96`, `2.05x` slower).
3. **Phase 6 `T-C1` live behavioral composition (`phase6_receipt.json` `passed = false`):** While CPU linear subspace alignment stays `>= 99.85%`, live `step0` logprob drift on `weft-eido` under triple-pack `ui_module` routing (`0.0611` vs `0.0019` solo shift) yields `0.0%` live retention.
4. **Phase 6 `T-C5` serving budget (`passed = false`):** Interleaved same-server trials recorded `-33.1%` signed latency overhead (`34.27` vs `25.75` tok/s, flagged `benchmark_anomaly = true`), and 8 GiB RTX 3080 VRAM remains an analytical byte projection (`4.9753 GiB` Linux headless / `6.1753 GiB` Windows WDDM) rather than a live NVML measurement.

Keep deep tactic search and dual-oracle code synthesis in Plane 1 retrieval and Tier 2 deterministic oracles without softening any gate.

## Hardware Scope and Lineage Pins

Live measurements ran on a local 64 GiB Apple M1 Max (`macOS` arm64, Metal `-ngl 99`, `$0` cloud spend) with `llama-server` `0.5.0` (build `11146`, commit `7fe450e19`) and Lean `v4.35.0`.

Read-only Tailscale TCP probes across `9` workbench ports (`22`, `445`, `2222`, `22222`, `3389`, `5985`, `5986`, `8080`, `11434`) confirmed `linux_rtx3080_online = false` (`geminus` had SSH/RPC ports closed, with only Windows SMB `445` open). Analytical 8 GiB RTX 3080 VRAM projections clear `<= 7.2 GiB`:

| Artifact or Pin | Measured / Verified Value | SHA-256 / Commit |
| --- | --- | --- |
| `p2b_artifact_commit` | Verified in git ODB (`p2b_artifact_commit_verified_in_odb = true`) | `f4c74a1e609c9d197b813a7141344c6e2cd72b08` |
| `spec/plane1_formal_spec.md` | `106,763` B, `32,216` `Qwen3.5` tokens (`30,873` `cl100k_base`), `0` control bytes | `49beff2a0185cfa4032170b614a543c0d67541494e858803d21cfb837111b230` |
| `corpus_tree_sha256` (`spec/lineage.json`) | `3` domains + `10` `DEPS_MANIFEST.json` repos pinned | `5bdb7f30363b956e82947f668f98c48f99876e87fb5ed4f785b873e4f4f98305` |
| `zone_manifest_id` (`schemas/zone-manifest.v0.1.json`) | `6` syntax zones (`l1_bank_tag` `0`-`3`) | `sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca` |
| `datasets/SHA256SUMS` | `294` public dataset, target, and harness files verified | `312953bc99bb42e6cbef1d1a3c240975f2baf3c60506df6c9eef06a678d45d56` |
| Primary `Qwen3.5-4B-Q8_0.gguf` | `4,482,403,488` B (`has_ssm_recurrent = true`) | `10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1` |
| Companion `Qwen3.5-4B-Q4_K_M.gguf` | `2,740,937,888` B (`3.3534 GiB` Linux / `4.5534 GiB` WDDM analytical) | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |
| `Qwen/Qwen3.5-4B` BF16 Safetensors | `738` tensors, `blk.31.ffn_up.weight` `[9216, 2560]` | `1ed4483f1d3ffbc3ffc7a26984be212e7cce455ac1e0651d1bcba1313ea2bd64` |
| `compile/artifacts/MANIFEST.json` | Identical to `compiler_manifest.json` | `feb435b67d3f065539cef8a5c02ab9f189a20314ca1388b845f268538f89935b` |
| Companion stack patches (`exo`, `warp`, `weft-eido`) | `40/40`, `57/57`, `120/120` unit tests passing | `e68c406`, `390176c`, `d87b958` |

## Pillar 1: Deterministic Oracles (`oracles_verification_receipt.json`)

Independent execution of `verification/verify_oracles.py` verified all root oracle, traversal, sandbox, and prose checks (`overall_passed = true`, `defect_count = 0`):

- **Paranoid Lean 4 kernel gate (`leanprover/lean4:v4.35.0`):** All `6/6` kernels (`lean-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`, `lean-default`) accepted all `8` theorems in `Mcproof.Proofs` (`challenge_sorry_whitelisted_module = "Mcproof.Spec"`). External `collectAxioms` audit measured exact kernel axioms `("Classical.choice", "Quot.sound", "propext")`. All `15/15` planted Lean cheats (including `#eval` comparator-stdout spoofing) were rejected (`100%`).
- **Dual-oracle mutation, verdict sanitization, and exact-math gate:** `34/34` root `pytest` tests passed under `python3 -O -B -W error`. Path-traversal verdict IDs (`../escaped`, `/etc/passwd`, `C:/foo`), empty `valid_cases` (`MISSING_VALID_CASES`), candidate `print(..., end="")` stdout pollution, unparseable `f0` output (`0/0`), `5/5` checker traps, and `4/4` `f0` ledger corruptions failed closed (`100%`).
- **Repository hygiene:** `./bin/mcproof --json bar`, `mde guard --code-audit`, vendored `prose_gate.py`, and `--dupes` exited `0` across all `11/11` repository markdown documents.

## Pillar 2: Public Corpus, Committed Vault Graders, and Leak Audit (`datasets_vault_receipt.json`)

Prompt-free vault graders (`verification/graders/{common,grade_canaries,grade_holdout,grade_mixed,grade_retention}.py`) are committed in-tree so scoring logic is auditable without exposing sealed prompt plaintext:

| Split | Location | Count | Breakdown | File SHA-256 |
| --- | --- | --- | --- | --- |
| `compile.jsonl` | `datasets/` | `96` | `24` x 4 families (A-D) | `067059259c5d2238a8ab3f6a6b01ebcedeed2dc0d19d2f7a02a3e170f52f7f31` |
| `validation.jsonl` | `datasets/` | `48` | `12` x 4 families (A-D) | `7e403727c8c02bd75c319f85042dc6a1bc6166c731681644237e4eaa3a4ae621` |
| `hybrid_k0.jsonl` | `datasets/` | `2,072` | `2,048` `u32` noise (`seed=20261119`) + `24` `y=0` anchors | `ba2e9b277eeb8d9ea5965b27d73ca8efc6c55c732ad800ee2bdfea41266eeeae` |
| `private_holdout.jsonl` | `mcproof-vault/` | `96` | `24` x 4 families (A-D), sealed | `4f5eac7fea63b5495896c23820180668d1e4d0a0a0a14297c63bf93419d989e3` |
| `canaries_16.jsonl` | `mcproof-vault/` | `16` | `8` preservation + `8` formal (`2` x 4), sealed | `d6aee4ba30f6a55f6f28f5aefb079be66f53c590cbb61f4a3c19a25d9f9daea8` |
| `warp_canaries_16.json` | `mcproof-vault/` | `16` | Stage 3 verifier host file (`0640`), sealed | `b7d2b812662d63983da440c665ae02057497f1c2c4881c6784c08d058844323e` |
| `general_retention_100.jsonl` | `mcproof-vault/` | `100` | `35` math, `35` coding, `20` reasoning, `10` refusal | `7a4dc93ad9b5f1df8b5149eb14b85f52027186ed4553b22a60c0338b49280f8c` |
| `mixed_composition_30.jsonl` | `mcproof-vault/` | `30` | Hazards `H1`-`H7` (`5/5/4/4/4/4/4`), sealed | `33effb059b4b1b41b94191fa477bd32ee5f70f6658c50966aa603205fa759465` |

- **Integrity, zero overlap, and leak audit:** `mde integrity --verify` passed on `datasets/` (`294` files, `312953bc...`) and `mcproof-vault/` (`22` files, `b14cf1ef...`), with `0` ID/prompt/declaration overlaps and `max = 0.031746 < 0.25` 8-gram Jaccard across `34,848` public-vs-vault pairs. `verification/leak_audit.py` verified `0` head/middle/tail 32-char prompt leaks, `0` 12-word phrase leaks, and `0` private path/IP leaks across all tracked artifacts.
- **Zero-flake canary verification (`canary_zero_flake_receipt.json`):** `10/10` live runs (`160` generations) of the `16` sealed canaries on `Qwen3.5-4B-Q8_0.gguf` (`temperature = 0.0`, `top_p = 1.0`, `seed = 42`) produced `0` byte-flaky IDs and `0` verdict-flaky IDs (`1` unique output SHA-256 per canary across all `10` runs).

## Pillar 3: Zero-Import `9/9` CPU `float64` Re-Derivation and Ablations (`p2b_rederivation_receipt.json`)

`verification/independent_rederive_p2b.py` (`PYTHONPATH="" python3 -I`, zero imports from `weft`, `warp_modeld`, `exo`, or `mcproof_compile`) re-derived all `9/9` `P2-B` files from raw BF16 Safetensors bytes, verified `harvested_activations.npz` (`413a1123...`, `hmac.compare_digest` against `36df5b57...`), and `spec/lineage.json` with **`0` byte differences**:

| `P2-B` Artifact | Size (Bytes) | Expected & Re-Derived SHA-256 | Byte Diff |
| --- | --- | --- | --- |
| `formal-verification.p2b.f16.gguf` | `189,408` | `728272c0974b795ceb990fde1e215b62d64e6faf04fb799c0fd3e01fa4539ba5` | `0` |
| `formal-verification.p2b.f16.wfsl` | `189,357` | `7f68b13bac77427e1734d32bf6e5593d61975313abfd62fe1041f878f7b15164` | `0` |
| `formal-verification.p2b.int4_int8.wfsl` | `58,357` | `a1b8566c5a4ef4337c55e56673fe9fe6d6bcc6fb90288c9d6ad650787f343d16` | `0` |
| `formal-verification.p2b.int4_f16.wfsl` | `78,803` | `cafadd5de9a114655c8a9f2d04bea51de1e292773a81e691fd538ff8c1e70449` | `0` |
| `formal-verification.p2b.certificate.json` | `312` | `e0c6b9a7bbd0f7f3da2ad09def08521a07cb62564bef8ca905c0744a5181d4f5` | `0` |
| `formal-verification.p2b.binding.json` | `3,429` | `9ea059c61a6dc21fe9328795c4cb639c6c19050d1fbb6459750a2e68f6175c4d` | `0` |
| `formal-verification.p2b.gate_policy.json` | `236` | `a6445d66592528c2e68020c9b9df8d89573e5fe319cefaca17d816872ff6dc97` | `0` |
| `formal-verification.p2b.warp_bundle.json` | `2,104` | `c8995729247d9d81690f75dc224127d2bd77a2237e7e7e056fb78e9ad25e70f2` | `0` |
| `formal-verification.p2b.wmcp_meta.json` | `1,583` | `6b31545190f4631fd982c4a7443e173ac11a84980efe13d89e7a6162fba826d4` | `0` |

- **Loud-column outlier profile ([Moissanite-Labs/siliquant PR 12](https://github.com/Moissanite-Labs/siliquant/pull/12)):** Across all `32` `Qwen3.5-4B` `ffn_down` (`2560 x 9216`) matrices, `max/mean` column L2 norm peaked at `1.7832x` on Layer 30 (`1.7750x` on Layer 31, compared against the cited `1.21x`-`1.41x` `TinyStories-1M` literature baseline). On base `ffn_down` INT4 weights, top-10 activation-weighted imatrix column protection reduced `K0` output drift `10.27%` (`193.70` vs `215.88`), whereas static weight-norm top-10 shifted drift `-0.01%`.
- **Asymmetric `int4/int8` leakage on compiled `P2-B` vs seeded `ffn_down` probe:** On compiled `P2-B` `ffn_up` (`9216 x 2560`), `int4/int8` (`58,357` B, `69.2%` smaller than F16) cut `K0` Frobenius leakage **`2.295x`** (`5.268x` scaled leakage energy) vs `int4/int4`, with top-10 column protection ratio `0.9998x`. On the seeded Gaussian null-space probe on `ffn_down` (`2560 x 9216`, `seed = 20261119`), `int4/int8` cut `K0` Frobenius leakage **`20.766x`** (`7.6756` vs `159.3915`), and top-10 imatrix protection reduced leakage an additional `12.03%` (`6.7523`, ratio `0.8797x`).
- **Fixed `PRE_REGISTERED_GATE_POLICY` & tamper controls (`control_gate_verification_receipt.json`):** `P2-B`, `corpus` (`d81bab6b...`), and `weft-eido` (`71bedfee...`, `0.0` elementwise weight difference vs the `29f1b18c...` build scored in `vault_arms_adapters.json`) passed fixed caps (`frob <= 25.0`, `spectral <= 16.0`, `leakage <= 45.0`, `safety_dot_sq <= 1e-4`). Unprojected `P2-A` (`48a5a7d3...`), low-norm `sabotage` (`c78da894...`), `forged_cert`, `stale_lineage`, `drifted_zone_manifest`, and `forged_canary` all failed closed across Stages 1 to 3 pre-load. In-nullspace `goodhart` (`4be01c8f...`) is Stage-2-admissible by construction (`leakage_energy_scaled = 421,535,270`) and is rejected at Stage 3 domain canaries and Phase 5 holdout.

## Pillar 4: Live 4-Layer Mount and Adversarial Gate (`phase4_receipt.json` & `stack_verification_receipt.json`)

- **L5 `mde` and L4 `exo`:** `mde zone-manifest --verify`, live `mde mcp` CST spans across `6` zone fixtures, `mde guard --code-audit` (`4/4` pokayoke bug classes caught), and `exo` `ZoneRouter` (`formal_proof -> {"corpus": 0.0, "weft-eido": 0.0, "formal-verification": 1.0}`, `l1_bank_tag = 3`) passed.
- **L3 `warp-modeld` latencies, `has_ssm_recurrent` binding, and `O(1)` rollback:** Zero-init `--lora-scaled ...:0.0 --lora-init-without-apply` matched pure base `W0` at `0.0` top-20 logprob diff. Stage 2 integer certificate verification ran in `0.0138 ms`. Stage 3 parallel 8-slot canary batching ran in `2828.95 ms` (`12/12` on host operational canaries, `min_preservation = 8`). Stage 4 multi-slot kill switch completed in `5.528 ms` and restored **`0.0` exact top-20 next-token logprob diff** vs pure `W0`.
- **Sealed Stage 3 fail-closed check on `P2-B` (`scale = 1.0`):** Against sealed `warp_canaries_16.json` and `verification/graders/grade_canaries.py --opaque-stage3` (requiring non-empty per-canary `outcomes` with `>= 8` preservation items), `P2-B` passed `8/8` preservation canaries (`0` flakes) and `6/8` formal canaries (`14/16` total vs `B0` `15/16`), causing Stage 3 to reject promotion fail-closed (`ERR_CANARY_FAILED`, active scale `0.0`).
- **Live adversarial & drift rejections:** `9/9` live `warp-modeld` RPC tamper checks rejected `forged_cert_digest` (`ERR_CERT_INVALID`), `forged_inline_canary` (`ERR_FORGED_CANARY_REJECTED`), honest-cert `sabotage` (`ERR_CERT_INVALID`), `behavioral_corruptor` (`ERR_CANARY_FAILED`), real `Qwen3.5-4B` `goodhart` (`ERR_CANARY_FAILED`), `raw_lora_override` (`ERR_UNVERIFIED_LORA_OVERRIDE`), 1-byte Plane 1 edit (`ERR_STALE_LINEAGE`), and `zone-manifest` rotation on infer and mount (`ERR_ZONE_MANIFEST_DRIFT`), while `verify_stack_sealed.py` also verified Stage 3 rejection of **forged-cert `sabotage` claiming zero leakage** (`ERR_CANARY_FAILED`) and Hard Veto 2 `ERR_CONTESTED_LINEAGE`.

## Public Validation & Sealed-Vault Arm Matrices (`temperature = 0.0`, `top_p = 1.0`, `seed = 42`)

Public `validation.jsonl` (`48` items, `compile/artifacts/evaluation/validation_scorecard.json`) and sealed vault splits (`vault_arm_b0.json`, `vault_arm_b1.json`, `vault_arms_adapters.json`):

| Arm | SOP Tokens | Public `validation` (`48`) | Sealed `private_holdout` (`96`) | Sealed `general_retention` (`100`) | Sealed `mixed_composition` (`30`) | Sealed `canaries_16` (`16`) |
| --- | --- | --- | --- | --- | --- | --- |
| `B0` (bare `W0`) | `0` | `4/48` (`8.33%`) | `0/96` (`0.0%`) | `84/100` (`84.0%`) | `8/30` (`26.7%`) | `15/16` (`8/8` pres, `7/8` formal) |
| `B1` (`W0` + Plane 1 spec) | `32,216` | `8/48` (`16.67%`) | `0/96` (`0.0%`) | N/A (prompt ceiling) | N/A | N/A |
| `P2-A` (unprojected LoRA) | `0` | `0/48` (`0.00%`) | `0/96` (`0.0%`) | `0/100` (`0.0%`) | `0/30` (`0.0%`) | `0/16` (`0/8` pres, `0/8` formal) |
| `P2-B` (`weft` `BetaEdit`) | `0` | `2/48` (`4.17%`) | `0/96` (`0.0%`) | `85/100` (`85.0%`) | `8/30` (`26.7%`) | `14/16` (`8/8` pres, `6/8` formal) |
| `logit_bias` (32-token static) | `0` | `6/48` (`12.50%`) | `0/96` (`0.0%`) | N/A | N/A | `15/16` (`8/8` pres, `7/8` formal) |
| `sabotage` (low-norm `K0` leak) | `0` | `1/3` safety smoke | `0/96` (`0.0%`) | N/A | N/A | `10/16` (`5/8` pres, `5/8` formal) |
| `goodhart` (in-nullspace overfit) | `0` | `4/48` (`8.33%`) | `0/96` (`0.0%`) | N/A | N/A | `15/16` @ `192` tok (`ERR_CANARY_FAILED` @ `80` tok) |
| `phase6_zone_routed_3pack` | `0` | N/A | `0/96` (`0.0%`) | `85/100` (`85.0%`) | `8/30` (`26.7%`) | `8/8` pres |
| `phase6_naive_unprojected_sum` | `0` | N/A | `0/96` (`0.0%`) | `0/100` (`0.0%`) | N/A | N/A |

## Phase 5 and Phase 6 Gate Scorecards

| Gate | Pre-Registered Threshold | Independent Measurement | Verdict |
| --- | --- | --- | --- |
| Phase 5 Primary gain | `>= 50%` relative failure drop vs `B0` | `0.0%` on `96` private holdouts (`0/96` vs `0/96`), `-4.55%` on `48` public validation items (`2/48` vs `4/48`) | **FAIL (Honest Kill Boundary)** |
| Phase 5 Ceiling ratio | `>= 80%` of `B1` pass rate | `0/96` vs `B1` `0/96` on private holdout, `25.0%` (`2/48` vs `8/48`) on public validation | **FAIL (Honest Kill Boundary)** |
| Phase 5 Injected SOP tokens | `>= 90%` drop vs `B1` | `0` injected SOP tokens on `P2-B` vs `32,216` `Qwen3.5` tokens on `B1`; `compile/artifacts/evaluation/validation_scorecard.json` records `b1_prefix_cache_parity_verified` on a 3-item prefix probe | **PASS (zero SOP tokens on P2-B; public validation efficacy still FAIL)** |
| Phase 5 Safety canaries | `8/8` (`100%`) mandatory, `0` flakes | `8/8` (`100.0%`) passed on `P2-B`, `0` flaky IDs across `10/10` runs (`160` generations) | **PASS** |
| Phase 5 General retention | `<= 1.0 pp` drop vs `B0` on `100` holdouts | `0.0 pp` drop (`+1.0 pp` net: `P2-B` `85.0%` vs `B0` `84.0%`, `P2-A` `0.0%`) | **PASS** |
| Phase 5 Mixed integrity | `0` formal corruptions & `0` prose leaks across `30` items | `8/30` sealed `4B` end-to-end (`30/30` `exo` router + public structural suite) | **FAIL (Honest Kill Boundary)** |
| Phase 5 Re-derivation | `0`-byte diff across independent CPU `float64` rebuild | `0`-byte diff across all `9/9` `P2-B` files via pure Python stdlib + `numpy` (`0` `weft` imports) | **PASS** |
| Phase 5 Tamper defense | `100%` fail-closed rejection of tamper, Goodhart, sabotage | `9/9` live RPC rejections + forged-cert `sabotage` & `goodhart` Stage 3 rejections | **PASS** |
| Phase 5 Rollback fidelity | `0.0` exact next-token logprob diff after `O(1)` kill switch | `0.0` exact top-20 logprob diff (`5.528 ms` multi-slot kill switch) | **PASS** |
| Phase 6 `T-C1` Solo preservation | `>= 90%` live behavioral preservation in paired/triple stacks | `0.0%` min live `step0` retention (`weft-eido` `0.0611` live drift vs `0.0019` solo shift, `99.85%` CPU subspace diagnostic) | **FAIL (Live `step0` Drift)** |
| Phase 6 `T-C2` Mixed isolation | `0` formal corruptions & `0` prose leaks across `30` items | `30/30` public structural suite & `exo` router checks, `8/30` sealed `4B` oracle synthesis | **FAIL on `4B` Synthesis / PASS on Router** |
| Phase 6 `T-C3` Base retention | `<= 1.5 pp` drop vs `W0`, beats naive sum | `85.0%` (`85/100`) routed 3-pack vs `84.0%` `W0` (`0.0 pp` drop), beats `0.0%` (`0/100`) naive sum | **PASS** |
| Phase 6 `T-C4` Order & rollback | Order-invariant (`3! = 6` perms) & `0.0` rollback drift | `0.0` CPU `float64` matrix diff, `0.0` live `llama-server` top-20 logprob diff, `0.0` per-slot & full rollback diff (`4.602 ms`) | **PASS** |
| Phase 6 `T-C5` Serving budget | `<= 15%` overhead (`>= -5%` floor), `>= 8k` KV, `<= 7.2 GiB` NVML VRAM | `-33.1%` same-server latency (`benchmark_anomaly = true`), `8192` KV/slot, analytical `4.9753 GiB` VRAM (no 8 GiB NVML GPU online) | **FAIL (Timing Anomaly & Analytical VRAM)** |
| Phase 6 Hazards `H1`-`H7` | All `7` cross-domain interference hazards pass live | `7/7` passed (`0` dark WCAG failures across `360` [weft-eido](https://github.com/Moissanite-Labs/weft-eido/pull/25) hues, `ContestedPreferenceError` + `ERR_CONTESTED_LINEAGE`, `data-eido-skip`) | **PASS (`7/7`)** |

## Repository Integrity and Verification Artifacts

All machine-readable verifier scripts, prompt-free vault graders, and computed receipts reside in `verification/`: `VERIFICATION_RECEIPT.json` (`build_final_receipt.py`), `oracles_verification_receipt.json`, `datasets_vault_receipt.json`, `canary_zero_flake_receipt.json`, `p2b_rederivation_receipt.json`, `compiler_verification_receipt.json`, `stack_verification_receipt.json`, `leak_audit.py`, `graders/`, `vault_arm_b0.json`, `vault_arm_b1.json`, and `vault_arms_adapters.json`.
