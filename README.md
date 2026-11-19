# mcproof

`mcproof` is the verification harness, Plane 1 rulebook, dataset suite, weight compiler, and serving benchmark for the Siliconcordat Formal Verification MDE. It checks Lean 4.35.0 proofs across six kernels, grades exact-math checkers against planted bugs, compiles `weft` adapters, and audits live `warp-modeld` mounts. Proof authors, verifiers, and researchers use it to test formal reasoning without weakening deterministic gates.

Blueprint and gates live in [siliconcordat/mde issue 4](https://github.com/siliconcordat/mde/issues/4) under the [Master Plan](https://github.com/siliconcordat/.github/blob/main/MASTER-PLAN.md). Companion serving changes live in [siliconcordat/exo](https://github.com/siliconcordat/exo/tree/feat/mde4-phase4-phase6-stack) and [siliconcordat/warp PR 5](https://github.com/siliconcordat/warp/pull/5).

## Unified Repository Layout

| Path | Contents |
| --- | --- |
| `src/mcproof/` & `bin/mcproof` | Zero-dependency Python 3.11+ Tier 2 oracle runner (`oracles.py`, `lean_harness.py`, `mutation.py`, `lineage.py`, `cli.py`) |
| `docs/CONTINUITY.md` | Capability steward record (`mde:formal-verification`), three-tier contracts, scratch reproduction runbook, and empirical Phase 1 to 6 lessons |
| `lean/` | Stock-`Init` Lean `v4.35.0` reference library, challenge/solution modules, 190-case differential test suite, and 6-kernel `lake comparator --paranoid` config |
| `spec/` & `schemas/` | Audited `32,216`-token (`Qwen3.5-4B`) Plane 1 formal specification (`plane1_formal_spec.md`), SHA-256 `lineage.json`, and canonical `zone-manifest.v0.1.json` |
| `datasets/` | Frozen public `compile.jsonl` (`96`), `validation.jsonl` (`48`), `hybrid_k0.jsonl` (`2,048` noise + `24` `y=0` anchors), 144 gold targets, harnesses, and `SHA256SUMS` |
| `commitments/` | Public-safe cryptographic commitment (`PUBLIC_HOLDOUT_COMMITMENT.json`, zero prompt text) binding the `242`-item sealed holdout and canary vault |
| `compile/` | Phase 2 and Phase 3 CPU `float64` `weft` `BetaEdit` compiler, `siliquant` loud-column ablation, negative controls, `weft-slab/v0.1` slabs, and F16 GGUF v3 LoRAs |
| `stack/` | Phase 4 and Phase 6 live `mde -> exo -> warp-modeld -> llama-server 0.5.0` harness, 7-hazard suite, receipts, and `patches/` for `exo`, `warp`, and `weft-eido` |
| `verification/` | Independent Phase 1 to Phase 6 verification scripts, `0`-byte pure-`weft` re-derivation runner, component receipts, `VERIFICATION_RECEIPT.json`, and `VERIFICATION_REPORT.md` |
| `tests/` | Root unit and adversarial cheat-rejection suite (`pytest` runs `tests/`, `compile/tests/`, and `stack/tests/` together) |

## Executive Outcome and Phase 5 Honest Kill Boundary

**Promotion decision: Do not promote `P2-B` (`scale = 1.0`) for autonomous single-pass proof synthesis on `Qwen3.5-4B`. Enforce the Phase 5 Honest Kill Boundary.**

Every deterministic infrastructure, null-space projection, cryptographic lineage, multi-slot serving, tamper-defense (`10/10`), rollback (`0.0` logprob diff), safety-canary (`8/8`), and general-retention gate passed. On sealed `general_retention_100.jsonl`, `weft` `BetaEdit` (`P2-B`) scored `85/100` (`85.0%` vs bare `B0` `84.0%`, `+1.0 pp`) while unprojected `P2-A` collapsed to `0/100` (`0.0%`).

On sealed `private_holdout.jsonl` (`96` items), single-pass `Qwen3.5-4B` scored `0/96` across every arm, including bare `B0` (`0/96`), `P2-B` (`0/96`), and full `32,216`-token Plane 1 specification injection (`B1`, `0/96`, `2.05x` slower). Because even the full Plane 1 prompt ceiling scores `0/96` on single-pass `4B` generation, deep tactic and dual-oracle code synthesis stays in Plane 1 retrieval and Tier 2 compiler-in-the-loop verification without lowering any threshold.

### Phase 5 and Phase 6 Gate Summary

| Gate | Requirement | Independent Measurement | Verdict |
| --- | --- | --- | --- |
| Primary holdout gain | `>= 50%` failure drop vs `B0` on `96` holdouts | `0.0%` (`P2-B` `0/96` vs `B0` `0/96`, `lean4_auditor` errors `-21.1%`) | **FAIL (Honest Kill Boundary)** |
| Plane 1 ceiling ratio | `>= 80%` of `B1` on `96` holdouts | `0/96` vs `B1` `0/96` (`32,216`-token ceiling also `0/96` on `4B`) | **FAIL (Honest Kill Boundary)** |
| SOP token savings | `>= 90%` reduction vs `B1` | `100.0%` (`0` vs `32,216` SOP tokens) | **PASS** |
| Safety canaries | `8/8` (`100%`) mandatory, `0` flakes | `8/8` (`100.0%`), `0` flaky IDs across `10/10` live runs (`160` generations) | **PASS** |
| General retention | `<= 1.0 pp` drop vs `B0` on `100` holdouts | `0.0 pp` drop (`P2-B` `85.0%` vs `B0` `84.0%`, unprojected `P2-A` `0.0%`) | **PASS** |
| Mixed-zone synthesis | `0` corruptions/leaks across `30` mixed prompts | `30/30` `exo` router + public suite, `8/30` sealed `4B` oracle synthesis | **FAIL on `4B` / PASS on Router** |
| `0`-byte re-derivation | Exact SHA-256 match on independent CPU `float64` rebuild | `0` byte diff across all `6/6` `P2-B` GGUF, slab, cert, and binding files | **PASS** |
| Tamper defense | `100%` rejection of forged cert, Goodhart, sabotage, drift | `10/10` (`100%`) rejected fail-closed across Stages 1 to 3 and holdout | **PASS** |
| Rollback fidelity | `0.0` next-token logprob diff after `O(1)` kill switch | `0.0` exact diff (`4.029` to `5.204 ms` multi-slot flush) | **PASS** |
| Phase 6 `T-C1`, `T-C3`, `T-C4`, `T-C5`, `H1`-`H7` | 3-pack composition (`corpus` + `weft-eido` + `formal-verification`) | `99.85%` subspace retention, `85.0%` vs `84.0%` `W0` (`T-C3`), `0.0` perm/rollback diff (`T-C4`), `4.95 GiB <= 7.2 GiB` analytical RTX 3080 VRAM (`T-C5`), `7/7` hazards pass | **PASS** |

## Reproduction Commands

Verify Plane 1 lineage, dataset `SHA256SUMS`, Lean 4.35.0 six-kernel comparator, code audit, prose gates, and all unit tests from the repository root:

```sh
./bin/mcproof --json lineage --verify
./bin/mcproof --json integrity datasets
./bin/mcproof --json lean --project
./bin/mcproof --json mde-guard .
python3 -m pytest -v
```

Grade a candidate completion across Families `A`, `B`, `C`, and `D`:

```sh
./bin/mcproof --json grade --family A --input datasets/targets/family_a/PUB-A-C01.lean
./bin/mcproof --json grade --family B --input datasets/targets/family_b/PUB-B-C01.py --fixture-json datasets/harnesses/family_b/PUB-B-C01.json
./bin/mcproof --json grade --family C --input datasets/targets/family_c/PUB-C-C01.md --expected-tier VERIFIED
./bin/mcproof --json grade --family D --input datasets/targets/family_d/PUB-D-C01.md --expected-tier PROVEN
```

## What is not proved

- Passing Tier 2 oracles proves only the machine-checked properties enforced by each checker. Whether a theorem statement matches human intent remains a Tier 1 human specification judgment.
- Live GPU runs executed on a local 64 GiB Apple M1 Max (`llama-server 0.5.0`, `$0` cloud). Analytical 8 GiB RTX 3080 VRAM budgets (`4.95 GiB` Linux headless / `6.15 GiB` Windows WDDM on `Q8_0`) await live Linux workbench provisioning (`linux_rtx3080_online = false`).

## What you must trust

- Lean `v4.35.0` and its five bundled external kernels (`leanchecker-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`), plus the Lean compiler and C runtime for native binaries.
- Python 3 exact `int` and `fractions.Fraction` arithmetic (`-O -B -W error`), `numpy` CPU `float64` linear algebra in `weft`, and the Rust `tree-sitter` CST parser in `siliconcordat/mde`.
- Host hardware, operating-system process isolation, and SHA-256 digest implementations.

## License

Code is licensed under Apache-2.0. Documentation, datasets, and Plane 1 specifications are licensed under CC-BY-4.0. See `LICENSE`.
