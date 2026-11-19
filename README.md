# mcproof

`mcproof` is the verification harness, Plane 1 rulebook, dataset suite, weight compiler, and serving benchmark for the Siliconcordat Formal Verification MDE. It checks Lean 4.35.0 proofs across six kernels, grades exact-math checkers against planted bugs, compiles `weft` adapters, and audits live `warp-modeld` mounts. Proof authors, verifiers, and researchers use it to test formal reasoning without weakening deterministic gates.

Blueprint and gates live in [siliconcordat/mde issue 4](https://github.com/siliconcordat/mde/issues/4) under the [Master Plan](https://github.com/siliconcordat/.github/blob/main/MASTER-PLAN.md). Companion serving changes live in [siliconcordat/exo](https://github.com/siliconcordat/exo/tree/feat/mde4-phase4-phase6-stack) and [siliconcordat/warp PR 5](https://github.com/siliconcordat/warp/pull/5).

## Unified Repository Layout

| Path | Contents |
| --- | --- |
| `src/mcproof/`, `bin/mcproof`, & `bin/bootstrap-deps` | Python 3.11+ Tier 2 oracle runner (`oracles.py`, `lean_harness.py`, `mutation.py`, `lineage.py`, vendored `prose_gate.py`, `cli.py`) and pinned external checkout bootstrap |
| `docs/CONTINUITY.md` | Capability steward record (`mde:formal-verification`), three-tier contracts, scratch reproduction runbook, and empirical Phase 1 to 6 lessons |
| `lean/` | Stock-`Init` Lean `v4.35.0` reference library, challenge/solution modules, 190-case differential test suite, and 6-kernel `lake comparator --paranoid` config |
| `spec/` & `schemas/` | Audited `32,216`-token (`Qwen3.5-4B`, `30,873` `cl100k_base`) Plane 1 specification (`plane1_formal_spec.md`), SHA-256 `lineage.json`, and canonical `zone-manifest.v0.1.json` |
| `datasets/` | Frozen public `compile.jsonl` (`96`), `validation.jsonl` (`48`), `hybrid_k0.jsonl` (`2,048` noise + `24` `y=0` anchors), `144` gold targets, `scripts/grade_item.py`, and `SHA256SUMS` (`312953bc...`) |
| `commitments/` | Public-safe cryptographic commitment (`PUBLIC_HOLDOUT_COMMITMENT.json`, zero prompt text) binding the `242`-item sealed holdout and canary vault |
| `compile/` | Phase 2 and Phase 3 CPU `float64` `weft` `BetaEdit` compiler, fixed `PRE_REGISTERED_GATE_POLICY`, loud-column ablation, negative controls, `weft-slab/v0.1` slabs, and F16 GGUF v3 LoRAs |
| `stack/` | Phase 4 and Phase 6 live `mde -> exo -> warp-modeld -> llama-server 0.5.0` harness, 7-hazard suite, receipts, and `patches/` for `exo`, `warp`, and `weft-eido` |
| `verification/` | Zero-`weft`-import `9/9` `0`-byte `P2-B` re-derivation runner, prompt-free vault `graders/`, `leak_audit.py`, computed `VERIFICATION_RECEIPT.json`, and `VERIFICATION_REPORT.md` |
| `tests/`, `compile/tests/`, & `stack/tests/` | Standalone and full-toolchain unit and adversarial cheat-rejection suites (`pytest` collects and runs cleanly from a fresh clone with only `pytest` and `numpy`) |

## Executive Outcome and Phase 5 Honest Kill Boundary

**Promotion decision: Do not promote `P2-B` (`scale = 1.0`) for autonomous single-pass proof synthesis on `Qwen3.5-4B`. Enforce the Phase 5 Honest Kill Boundary.**

Null-space projection, cryptographic lineage, multi-slot rollback (`0.0` top-20 logprob diff), safety canaries (`8/8`, `0` flakes), adversarial rejection (`9/9` live RPC tamper checks plus forged-cert `sabotage` Stage 3 catch), and general capability retention passed. On sealed `general_retention_100.jsonl`, `weft` `BetaEdit` (`P2-B`) scored `85/100` (`85.0%` vs bare `B0` `84.0%`, `+1.0 pp`) while unprojected `P2-A` collapsed to `0/100` (`0.0%`).

On public `validation.jsonl` (`48` items), `P2-B` regressed below bare `B0` and constant output-token logit bias (`P2-A 0/48 [0.00%] < P2-B 2/48 [4.17%] < B0 4/48 [8.33%] = goodhart 4/48 [8.33%] < constant logit_bias 6/48 [12.50%] < B1 8/48 [16.67%]`, relative failure reduction `-0.0455`, `REJECTED_NEGATIVE_EFFICACY`). On sealed `private_holdout.jsonl` (`96` items), single-pass `Qwen3.5-4B` scored `0/96` across `B0`, `P2-B`, and full `32,216`-token Plane 1 specification injection (`B1`, `0/96`, `2.05x` slower). Deep tactic search and dual-oracle code synthesis stay in Plane 1 retrieval and Tier 2 compiler-in-the-loop verification without lowering any threshold.

### Phase 5 and Phase 6 Gate Summary

| Gate | Requirement | Independent Measurement | Verdict |
| --- | --- | --- | --- |
| Primary holdout & validation gain | `>= 50%` failure drop vs `B0` | Sealed `0/96` vs `B0` `0/96`, public `validation.jsonl` `2/48` (`4.17%`) vs `B0` `4/48` (`8.33%`, `-4.55%` rel. drop) | **FAIL (Honest Kill Boundary)** |
| Plane 1 ceiling ratio | `>= 80%` of `B1` pass rate | Sealed `0/96` vs `B1` `0/96`, public `validation.jsonl` `2/48` vs `B1` `8/48` (`25.0%` ceiling ratio) | **FAIL (Honest Kill Boundary)** |
| Injected SOP prompt tokens | Eliminate `B1` prompt overhead (`>= 90%` drop) | `0` injected SOP tokens on `P2-B` vs `32,216` `Qwen3.5` tokens on `B1` (`b1_prefix_cache_parity_verified: true`) | **PASS** |
| Safety canaries | `8/8` (`100%`) mandatory, `0` flakes | `8/8` (`100.0%`), `0` flaky IDs across `10/10` live runs (`160` generations) | **PASS** |
| General retention | `<= 1.0 pp` drop vs `B0` on `100` holdouts | `0.0 pp` drop (`P2-B` `85.0%` vs `B0` `84.0%`, unprojected `P2-A` `0.0%`) | **PASS** |
| Mixed-zone synthesis | `0` corruptions/leaks across `30` mixed prompts | `30/30` `exo` router + public suite, `8/30` sealed `4B` oracle synthesis | **FAIL on `4B` / PASS on Router** |
| `0`-byte re-derivation | Exact SHA-256 match on independent CPU `float64` rebuild | `0` byte diff across all `9/9` `P2-B` files via pure Python stdlib + `numpy` (`0` `weft` imports) | **PASS** |
| Tamper defense | `100%` fail-closed rejection of tamper, Goodhart, sabotage | `9/9` live `warp-modeld` RPC rejections + forged-cert `sabotage` & `goodhart` Stage 3 rejections | **PASS** |
| Rollback fidelity | `0.0` next-token logprob diff after `O(1)` kill switch | `0.0` exact top-20 logprob diff (`5.528 ms` multi-slot flush) | **PASS** |
| Phase 6 `T-C1` solo preservation | `>= 90%` live behavioral preservation in paired/triple stacks | `0.0%` min live `step0` retention (`weft-eido` `0.0611` live drift vs `0.0019` solo shift, `99.85%` CPU subspace diagnostic) | **FAIL (Live `step0` Drift)** |
| Phase 6 `T-C3`, `T-C4`, `H1`-`H7` | Base retention, order invariance, and 7 live hazards | `85.0%` vs `84.0%` `W0` (`T-C3`), `0.0` perm/rollback diff (`T-C4`, `4.602 ms`), `7/7` hazards | **PASS** |
| Phase 6 `T-C5` serving budget | `<= 15%` overhead (`>= -5%` floor), `>= 8k` KV, `<= 7.2 GiB` NVML VRAM | `-33.1%` same-server latency (`benchmark_anomaly = true`), `8192` KV/slot, analytical `4.98 GiB` VRAM (no 8 GiB NVML GPU online) | **FAIL (Timing Anomaly & Analytical VRAM)** |

## Prerequisites and Fresh-Clone Reproduction

### 1. Standalone Fresh Clone (`python >= 3.11`, `pytest`, `numpy` Only)

`.gitattributes` enforces LF line endings across platforms so SHA-256 and control-byte lineage checks behave identically on Linux, macOS, and Windows. From a clean `git clone` with only `pytest` and `numpy` installed:

```sh
python3 ./bin/mcproof --json lineage --verify
python3 -O -B -W error -m pytest -v
python3 verification/build_final_receipt.py
python3 verification/leak_audit.py
```

Tests that require optional external binaries (`lean`, `lake`, `mde`, `llama-server`, or sibling `deps/` checkouts) skip cleanly with explicit `pytest` skip reasons rather than failing collection.

### 2. Full Tier 2 Oracle and Stack Bootstrap

Clone all `10` SHA-pinned Plane 1 upstream repositories plus the `4` `siliconcordat/*` sibling stacks, build `mde`, and install Lean `v4.35.0`. Building `siliconcordat/mde` requires **Rust `>= 1.85`** (Cargo `edition2024`) or a **nightly** toolchain (`rustup toolchain install stable` on a recent release, or `cargo +nightly build`).

```sh
./bin/bootstrap-deps --with-siliconcordat
cargo build --release --manifest-path ../siliconcordat/mde/Cargo.toml
elan toolchain install leanprover/lean4:v4.35.0
```

Run the full Tier 2 oracle gates and Family `A` to `D` graders. On Linux, `lake comparator --paranoid` enforces `bwrap` sandboxing by default. On macOS or Windows hosts without `bwrap`, pass `--allow-unsandboxed`, which records `sandboxed = false` and `UNSANDBOXED_EXECUTION`:

```sh
./bin/mcproof --json lineage --verify --require-deps
./bin/mcproof --json integrity datasets
./bin/mcproof --json bar
./bin/mcproof --json mde-guard .
./bin/mcproof --allow-unsandboxed --json lean --project
./bin/mcproof --allow-unsandboxed --json grade --family A --input datasets/targets/family_a/PUB-A-C01.lean
./bin/mcproof --json grade --family B --input datasets/targets/family_b/PUB-B-C01.py --fixture-json datasets/harnesses/family_b/PUB-B-C01.json
./bin/mcproof --json grade --family C --input datasets/targets/family_c/PUB-C-C01.md --expected-tier VERIFIED
./bin/mcproof --allow-unsandboxed --json grade --family D --input datasets/targets/family_d/PUB-D-C01.md --expected-tier PROVEN
```

## What is not proved

- Passing Tier 2 oracles proves only the machine-checked properties enforced by each checker. Whether a theorem statement matches human intent remains a Tier 1 human specification judgment.
- `datasets/scripts/grade_item.py` grades Family C items by deterministic structural claim-tier and `meta["bar_status"]` replay rather than re-running Lean compilation on prose-only reports.
- Live GPU runs executed on a local 64 GiB Apple M1 Max (`llama-server 0.5.0`, `$0` cloud). Analytical 8 GiB RTX 3080 VRAM projections (`4.9753 GiB` Linux headless / `6.1753 GiB` Windows WDDM on `Q8_0`) remain unmeasured on live 8 GiB NVML hardware (`vram_measurement_kind = analytical_projection_not_nvml`).

## What you must trust

- Lean `v4.35.0` and its five bundled external kernels (`leanchecker-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`), plus the Lean compiler and C runtime for native binaries (`Classical.choice`, `Quot.sound`, and `propext` measured via `collectAxioms` on `Mcproof.Proofs`).
- Python 3 exact `int` and `fractions.Fraction` arithmetic (`-I -O -B -W error`), `numpy` CPU `float64` linear algebra, and the Rust `tree-sitter` CST parser in `siliconcordat/mde`.
- Host OS sandboxing (`bwrap` network-unshared read-only root on Linux, or subprocess `-I` environment isolation without OS syscall confinement on macOS and Windows) and SHA-256 digest implementations.

## License

Code is licensed under Apache-2.0. Documentation, datasets, and Plane 1 specifications are licensed under CC-BY-4.0. See `LICENSE`.
