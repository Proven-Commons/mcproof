# mcproof Lean 4 Reference Package

`mcproof` in `lean/` is a stock-`Init` Lean 4.35.0 library and executable checking bounded clamping, Bezout witnesses, rational order, path containment, and discrete state-transition lower-bound soundness. Engineers use it to validate multi-kernel theorem checking under the [Proven Commons Verified Bar](https://github.com/Proven-Commons/mission/blob/main/playbook/verified-bar.md).

Status: in progress. Independent human specification review has not been recorded yet, so this package is not verified.

## What is proved

| Claim | Theorem |
| --- | --- |
| When `lo <= hi`, `clampNat lo hi x` stays between `lo` and `hi`. | `Mcproof.Spec.clampNat_in_range` |
| An input already in `[lo, hi]` returns unchanged from `clampNat`. | `Mcproof.Spec.clampNat_of_mem` |
| `bezoutCheck` returns `true` only when `a * x + b * y = g`. | `Mcproof.Spec.bezoutCheck_sound` |
| Every valid witness `a * x + b * y = g` passes `bezoutCheck`. | `Mcproof.Spec.bezoutCheck_complete` |
| `ratLeCross` returns `true` only when `0 < d1`, `0 < d2`, and `n1 * d2 <= n2 * d1`. | `Mcproof.Spec.ratLeCross_sound` |
| Every fraction with `0 < d` passes `ratLeCross n d n d`. | `Mcproof.Spec.ratLeCross_refl_pos` |
| Accepted path lists from `cleanSegments` are non-empty and exclude `.`, `..`, `/`, and NUL. | `Mcproof.Spec.cleanSegments_safe` |
| A single valid segment `[s]` returns `some [s]` from `cleanSegments`. | `Mcproof.Spec.cleanSegments_singleton` |
| Quotient homomorphism pullback `hQ (pi s)` is globally 1-step consistent on full states. | `Mcproof.Spec.quotientHeuristic_step_consistent` |
| Quotient homomorphism pullback bounds every `ValidPath` reaching a goal state. | `Mcproof.Spec.quotientHeuristic_admissible` |
| Pre-funded resource potential `h(s) - c * r(s)` preserves `0` on goals and admissibility. | `Mcproof.Spec.prefundedHeuristic_admissible_and_goal` |
| Pre-funded potential restores universal `h_hat(s) <= h_hat(s') + 1` in `Nat`. | `Mcproof.Spec.prefundedHeuristic_step_consistent` |
| Concrete `12 -> 10` witness repairs to `11 -> 10` under `c = 1, r : 1 -> 0`. | `Mcproof.Spec.prefundedVal_bounded_drop_witness` |
| Non-negative operator-counting / Farkas dual bounds `scale * planSum cost acts`. | `Mcproof.Spec.operatorCounting_dual_scaled_sound` |
| Division-free integer dual floor `dualObjective cs / scale` is admissible for `0 < scale`. | `Mcproof.Spec.operatorCounting_dual_div_admissible` |
| Executable `dualFloorNat` bounds `planCost` and checks `dualFloorNat 2 [(2,9),(1,8)] = 13`. | `Mcproof.Spec.dualFloorNat_sound_and_witness` |
| Cyclic mode-switch tax `(c + k - a) % k` satisfies triangle inequality for `a, b, c < k`. | `Mcproof.Spec.cyclicSwitchTax_triangle` |
| Unrestricted `cyclicSwitchDist` satisfies zero self-tax, triangle inequality, and `k = 6` witnesses. | `Mcproof.Spec.cyclicSwitchDist_metric_and_witness` |
| Two-species conservation and irreversible harvests fund global pre-funded potential repair. | `Mcproof.Spec.conservation_harvest_potential_repair` |
| Vertex-split unit-capacity flows bound horizon demand by cumulative min-cut capacity. | `Mcproof.Spec.vertexSplit_unit_flow_horizon_bound` |
| Zero-self-loop quotient + monotone deficit composition preserves 1-step consistency and admissibility. | `Mcproof.Spec.zeroSelfLoop_deficit_composition` |
| Exact rational ceiling `ceilDivNat` preserves `0` on goals, 1-step consistency, and admissibility. | `Mcproof.Spec.ceilDiv_step_consistent_and_admissible` |
| Division-free RMSNorm tangent projection `tangentProjScaled h delta` is orthogonal to `h`. | `Mcproof.Spec.rmsnorm_tangent_orthogonal` |
| Pairwise-orthogonal tangent adapter stacks inflate squared norm additively. | `Mcproof.Spec.rmsnorm_orthogonal_stack_norm_inflation` |
| Balanced `L`-layer split cuts cumulative quadratic radial shrinkage by exact factor `L`. | `Mcproof.Spec.multilayer_quadratic_shrinkage_reduction` |
| Elementwise gate inner product equals `diag(g^2)` metric with `[2, 1]` counterexample. | `Mcproof.Spec.swiglu_gate_metric_and_counterexample` |
| Hadamard adjoint projection orthogonal to `g ⊙ (W_down^T h_0)` zeroes radial inner product. | `Mcproof.Spec.swiglu_radial_null_orthogonality` |
| Orthogonal `[0, 32]` cross-talk keeps `100%` scalar projection while injecting `1024x` drift energy. | `Mcproof.Spec.scalar_projection_retention_illusion` |
| RMSNorm radial base-logit shrinkage lies in exact rational sandwich `[D2/(2*(R2+D2)), D2/(2*R2)]`. | `Mcproof.Spec.rmsnorm_rational_shrinkage_sandwich` |

## What is not proved

- Command-line string parsing and standard-output formatting in `Main.lean` are covered by differential tests rather than Lean theorems.
- Whether a concrete transition-system implementation satisfies the quotient-edge or dual-load hypotheses on all reachable transitions must be verified by exhaustive edge or certificate checks.
- Operating-system symlink resolution, execution latency, and memory usage sit outside these theorems.

## What you must trust

- The Lean 4.35.0 kernel and the five bundled external kernels (`leanchecker-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`).
- The Lean compiler and C runtime that lower `Mcproof.lean`, `Mcproof/TransitionBounds.lean`, and `Main.lean` into native machine code.
- The host hardware, operating system, and `bubblewrap` sandbox on Linux hosts.
- Python 3 exact `int` and `fractions.Fraction` arithmetic in the differential test oracle.

## Re-check it

Run the build, multi-kernel proof comparator, and differential test suite from `lean/`:

```sh
lake build
lake comparator --paranoid
python3 tests/run_tests.py
```

On macOS hosts where Linux `bubblewrap` is absent, pass `--inadvisably-no-sandbox` to `lake comparator --paranoid` to execute all six kernels locally while recording `sandboxed = false`.
