# Formal Verification MDE Public Datasets

`datasets/` holds the public Phase 1 compilation, validation, and Hybrid `K0` calibration splits for `siliconcordat/mde#4`. Every prompt includes a verified gold target, a baseline failure target, and a deterministic Tier 2 oracle command for `weft` compilers, `exo` routers, and independent verifiers.

## Directory Layout

- `compile.jsonl`: 96 SHA-256-pinned prompts (24 per Family A, B, C, and D) for `weft` `BetaEdit` target harvesting.
- `validation.jsonl`: 48 SHA-256-pinned prompts (12 per Family A, B, C, and D) for hyperparameter and rank selection.
- `hybrid_k0.jsonl`: 2,048 seeded random-vocabulary noise sequences (`seed = 20261119`) plus 24 public register-scoped `y = 0` preservation anchors across `prose`, `condensed_json`, `ui_module`, and `code`.
- `targets/`: 144 materialized gold completion files (`family_a/*.lean`, `family_b/*.py`, `family_c/*.md`, `family_d/*.md`).
- `harnesses/`: 144 deterministic fixture and metadata JSON files consumed by `mcproof` and `scripts/grade_item.py`.
- `scripts/grade_item.py`: standalone per-item verifier delegating to `../repo/bin/mcproof` and replaying Family C Bar, Verdict, and F0 gates.
- `manifest.json`: machine-readable split counts, subtopic matrix, `zone_manifest_id`, and `sha256` derivation rule.
- `SHA256SUMS`: integrity manifest written and checked by `siliconcordat/mde` (`mde integrity`).

## Domain Isolation

All 144 `PUB-` prompts stay strictly inside four reserved public subtopics so the sealed private holdout (`HOLD-`, `CAN-`, `RET-`, `MIX-`) uses disjoint mathematics:

1. `elementary_number_theory`: divisibility, parity, modular congruences, Euclidean `gcd`, Bezout witnesses, and coprime Chinese Remainder pairs.
2. `finite_combinatorics`: pigeonhole collisions, Pascal and Vandermonde binomial identities, finite graph handshaking, trees, and 2-coloring.
3. `rational_interval_linalg`: exact `int` and `fractions.Fraction` determinants, Cramer and Gaussian rank witnesses, Farkas dual certificates, and closed rational intervals.
4. `finite_state_protocols`: non-cryptographic ticket locks, semaphores, Lamport clocks, bounded FIFO queues, credit flow control, and 2PC safety.

## Families and Tier 2 Oracles

- **Family A (`formal_proof`, 24 compile / 12 validation)**: stock-`Init` Lean `v4.35.0` proofs and `WeakStatement` vacuous-hypothesis traps checked across all six kernels of `lake comparator --paranoid`, `leanchecker`, `collectAxioms`, and `soko` `lean4_auditor.py`.
- **Family B (`code`, 24 compile / 12 validation)**: exact `int` and `Fraction` Python certificate verifiers (`def verify(inst, cert) -> bool`) audited for distinct AST alpha-skeletons, zero `float` or `/` coercion, zero `assert` under `mde guard --code-audit`, clean `python3 -O -B -W error` execution, and 100% planted-bug mutation kills (`>= 80%` floor).
- **Family C (`formal_proof`, 24 compile / 12 validation)**: epistemic claim-tier hygiene and refusal traps checked by `mcproof`, `mission/bar/check.py`, `formal-claims-audit/scripts/check_verdicts.py`, and `f0/scripts/gate.py`. The `bar_check` oracle is the one that builds a Lean project from pinned `spec_meta.statements`. `PUB-C-V02` is a `verdict_audit` item and does not use that path.
- **Family D (`formal_proof`, 24 compile / 12 validation)**: mixed-register technical notes combining plain prose (`check-prose.py` and `--dupes`), `<div class="formal-claim" data-eido-skip>` protection, full 40-character verdict SHAs, kernel-checked Lean 4 blocks, and mandatory boundary sections.

## Re-check Commands

Run all commands from `datasets/`:

```sh
../repo/bin/mcproof integrity . --verify
../repo/bin/mcproof --json mde-guard .
python3 scripts/grade_item.py --id PUB-A-C01
python3 scripts/grade_item.py --id PUB-B-C01
python3 scripts/grade_item.py --id PUB-C-C01
python3 scripts/grade_item.py --id PUB-D-C01
```

## What is not proved

Passing these 144 public items proves compilation and validation target fidelity on the four `PUB-` mathematical domains. Out-of-distribution generalization is measured separately on the sealed private holdout vault.

## What you must trust

You must trust the Lean 4.35.0 kernel and bundled external checkers, the Python 3 interpreter (`-O -B -W error`), the `siliconcordat/mde` Rust binary, SHA-256 manifest verification, and the host hardware.
