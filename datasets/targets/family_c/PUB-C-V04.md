Claim-Tier: VERIFIED

# TreeCnt: formally checked core with differential replay

`TreeCnt` checks exact `finite combinatorics` invariants and pairs Lean 4 kernel proofs on its pure model with deterministic Python differential tests.

Status: in progress. Independent specification review has not been recorded in `bar.toml`, so this package is not verified.

## What is proved

| Claim | Theorem |
|-------|---------|
| Primary soundness invariant holds on all modeled inputs. | `TreeCnt.Spec.vertices_eq_edges_succ` |
| Secondary structural property holds without escape hatches. | `TreeCnt.Spec.leaf_step` |

## What is not proved

- Command-line input parsing and text formatting in `Main.lean` (covered only by finite differential tests).
- Wall-clock execution time, memory allocation bounds, and external OS environment behavior.
- Independent human adequacy sign-off on `SPEC.md`.

## What you must trust

- The Lean kernel and the five external kernels shipped with Lean that replay the exported proof terms.
- The Lean compiler and runtime that lower proved definitions into native code.
- The physical hardware and operating system executing the binary and Python test oracle.

## Re-check it

```sh
lake build
lake comparator --paranoid
python3 tests/run_tests.py
```
