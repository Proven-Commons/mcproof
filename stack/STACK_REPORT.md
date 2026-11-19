# Phase 4 and Phase 6 Stack Report

`STACK_REPORT.md` records the live four-layer integration and three-pack composition results for the [Formal Verification MDE blueprint](https://github.com/siliconcordat/mde/issues/4). It summarizes end-to-end checks across `mde`, `exo`, `warp-modeld`, and `llama-server` `0.5.0` (`7fe450e19`) using the compiled `Qwen3.5-4B` adapters. It is written for maintainers and independent verifiers auditing Phase 4 and Phase 6 acceptance gates.

## Pinned Artifacts and Lineage

- `zone_manifest_id`: `sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca`
- `corpus_tree_sha256`: `5bdb7f30363b956e82947f668f98c48f99876e87fb5ed4f785b873e4f4f98305`
- Base GGUF (`Qwen3.5-4B-Q8_0.gguf`, `4,482,403,488` B, `has_ssm_recurrent = true` parsed from GGUF header): `10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1`
- Safetensors checkpoint fingerprint (cross-bound via `verify_supplied_checkpoint_against_served_gguf`): `1ed4483f1d3ffbc3ffc7a26984be212e7cce455ac1e0651d1bcba1313ea2bd64`
- `mde:formal-verification` (`P2-B` F16 GGUF, `189,408` B): `728272c0974b795ceb990fde1e215b62d64e6faf04fb799c0fd3e01fa4539ba5` (`int4/int8` slab `58,357` B, `int4/f16` slab `78,803` B)
- `mde:corpus` (F16 GGUF, `189,184` B): `d81bab6b8c5555674dbbe29e38566435fedc1828d652fbfbf12f35f9562ea640`
- `mde:weft-eido` (F16 GGUF, `189,184` B): `71bedfeee40d0b11a559f73d1c720822a1281452859f43a250bf86bc2755bb86`

## Phase 4 Results (`results/final/phase4_receipt.json`)

| Step | Gate | Measured | Status |
| :--- | :--- | :--- | :--- |
| Step 4.1 (`mde`) | CST span zones + pokayoke `--code-audit` | All 6 zone fixtures + 4 pokayoke rules caught | PASS |
| Step 4.2 (`exo`) | `formal_proof` routing + `zone_manifest_id` forward | `{"corpus": 0.0, "weft-eido": 0.0, "formal-verification": 1.0}`, bank tag `3` | PASS |
| Step 4.3 Stage 1 | Five-layer checkpoint, `has_ssm_recurrent`, lineage, and zone pin | Verified (`zero_init` vs pure `W0` top-20 logprob diff `0.0`) | PASS |
| Step 4.3 Stage 2 | Division-free integer `FixedRadixCertificate` (`< 1 ms`) | `0.0138 ms` | PASS |
| Step 4.3 Stage 3 | Parallel-slot shadow load + host canaries (`< 3000 ms`, `min_preservation = 8`) | `2828.95 ms` (`12/12` passed) | PASS |
| Step 4.3 Stage 4 | `O(1)` kill switch + multi-slot KV/DeltaNet flush (`< 10 ms`) | `5.528 ms` | PASS |
| Step 4.3 Controls | Live `warp-modeld` RPC rejections of forged cert, forged canary, sabotage, Goodhart, corruptor, raw `lora`, stale/drift | `9/9` genuine live RPC rejections (`ERR_CERT_INVALID`, `ERR_FORGED_CANARY_REJECTED`, `ERR_CANARY_FAILED`, `ERR_UNVERIFIED_LORA_OVERRIDE`, `ERR_STALE_LINEAGE`, `ERR_ZONE_MANIFEST_DRIFT`) | PASS |
| Step 4.4 Drift | 1-byte Plane 1 edit + `zone-manifest` rotation + rollback | Auto-unload (`ERR_STALE_LINEAGE`, `ERR_ZONE_MANIFEST_DRIFT`), `0.0` top-20 logprob diff | PASS |

## Phase 6 Results (`results/final/phase6_receipt.json`)

Overall Phase 6 verdict: **`passed = false`** (`T-C1` fails on live `step0` behavioral drift under triple-pack routing, and `T-C5` fails closed on negative timing anomaly plus analytical-only 8 GiB VRAM). Precedence order enforced: `Tier 1 Human Authority > Tier 2 RepoPolicy > Specialist Pack in its L5 syntax zone > Base Prose Pack`.

- **Seven Interference Hazards (`H1` to `H7`)**: `7/7` passed live, including the [weft-eido 360-hue WCAG contrast audit](https://github.com/Moissanite-Labs/weft-eido/pull/25) (`120/120` unit tests, `0` dark-theme failures across `360` hues, `4.99:1` weakest muted-on-wash pair), Hard Veto 2 `ContestedPreferenceError` escalation on un-overridden `html_delivery` and unmarked `condense_formal_claims`, and `data-eido-skip` DOM protection.
- **`T-C1` (Solo Gain Preservation, `>= 90%` live `step0` retention, FAIL)**: Live `step0` retention measured `0.0%` minimum across routed triple mounts because `weft-eido` (`ui_module` scales `[0.2, 1.0, 0.0]`) exhibited `0.0611` live `step0` logprob drift vs its `0.0019` solo shift (`corpus` `100.0%`, `weft-eido` `0.0%`, `formal-verification` `100.0%`). CPU linear subspace alignment (`99.85%` minimum) is recorded separately as a non-gating diagnostic.
- **`T-C2` (Mixed-Zone Isolation)**: `0` formal corruptions and `0` prose leaks across `30/30` public structural mixed prompts (`8/30` on sealed `4B` end-to-end oracle synthesis).
- **`T-C3` (Base Capability Retention, `<= 1.5 pp` drop)**: `92.0%` (`23/25`) routed triple vs `92.0%` (`23/25`) bare `W0` (`0.0 pp` drop) on the public retention suite (`85.0%` vs `84.0%` on sealed `general_retention_100.jsonl`), outperforming `4.0%` (`1/25`) naive unweighted summation.
- **`T-C4` (Order Invariance and Rollback)**: `0.0` matrix diff across all `6` CPU `float64` permutations, `0.0` live C++ multi-LoRA order top-20 logprob diff, `0.0` per-slot selective rollback diff, and `0.0` full-stack rollback logprob diff (`4.602 ms`).
- **`T-C5` (Serving Budget, `<= 15%` same-server overhead, `>= 8192` KV, `<= 7.2 GiB` NVML VRAM, FAIL)**: `-33.1%` signed decode overhead across `5` interleaved trials on the same `LiveLlamaProcess` (`34.27` triple-LoRA active vs `25.75` `W0` zero-scale median tok/s, flagged `benchmark_anomaly = true` below the `-5.0%` floor), `8192` KV tokens per slot, and `vram_measurement_kind = analytical_projection_not_nvml` (`4.9753 GiB` Linux headless / `6.1753 GiB` Windows WDDM analytical 8 GiB RTX 3080 VRAM projection on `Q8_0`, `3.3534 GiB` / `4.5534 GiB` on `Q4_K_M`).
