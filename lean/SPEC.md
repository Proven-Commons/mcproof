# Specification: mcproof Lean Reference Library

`mcproof` in `lean/` is the domain-general Lean 4.35.0 reference package for the Formal Verification MDE. It defines pure kernels for natural clamping, exact Bezout witnesses, division-free rational order, path containment, quotient state-transition heuristics, pre-funded monotone potential repair, and operator-counting LP dual bounds, checked by `lake comparator --paranoid`.

## Scope

1. `Mcproof.clampNat lo hi x` moves a natural number `x` into `[lo, hi]`, returning `lo` when `lo > hi`.
2. `Mcproof.bezoutCheck a b x y g` returns `true` if and only if `a * x + b * y = g` over exact integers.
3. `Mcproof.ratLeCross n1 d1 n2 d2` checks `n1 / d1 <= n2 / d2` for positive denominators via exact integer cross-multiplication `n1 * d2 <= n2 * d1`.
4. `Mcproof.cleanSegments segs` accepts a non-empty list of segments only when every segment is non-empty, neither `.` nor `..`, and free of `/` and NUL bytes.
5. `Mcproof.TransitionBounds.quotientHeuristic pi hQ` pulls back a 1-step-consistent quotient heuristic `hQ` to full states over `ValidPath`.
6. `Mcproof.TransitionBounds.prefundedVal h c r` and `prefundedHeuristic` subtract monotone resource credit `c * r` in `Nat` to restore universal 1-step consistency under bounded multi-step heuristic drops.
7. `Mcproof.TransitionBounds.dualObjective`, `actionDualLoad`, and `dualFloorNat` compute division-free integer lower bounds from non-negative operator-counting / Farkas dual constraints.
8. `Mcproof.TransitionBounds.cyclicSwitchTax`, `cyclicSwitchDist`, `intactSupply`, `vertexArcFlow`, `tokensInCut`, `horizonCutCapacity`, `composedDeficitHeuristic`, and `ceilDivNat` formalize cyclic mode-switch metrics, two-species conservation potentials, vertex-split flow horizon bounds, composed deficits, and exact ceilings.
9. `Mcproof.AdapterBounds.tangentProjScaled`, `vecDot`, `vecNormSq`, `vecAdd`, `vecSub`, `vecHadamard`, `vecSqDiag`, `sumNat`, `sumSqNat`, and `shrinkageSandwichCheck` formalize exact integer RMSNorm tangent projection, multi-layer `1/L` quadratic radial-shrinkage reduction, SwiGLU gate metrics, and rational shrinkage bounds.

## What must always hold

| Property | Theorem |
| --- | --- |
| When `lo <= hi`, `clampNat lo hi x` lies inside `[lo, hi]`. | `Mcproof.Spec.clampNat_in_range` |
| Every input already in `[lo, hi]` returns unchanged. | `Mcproof.Spec.clampNat_of_mem` |
| `bezoutCheck` returns `true` only when `a * x + b * y = g`. | `Mcproof.Spec.bezoutCheck_sound` |
| `bezoutCheck` returns `true` on every valid integer witness. | `Mcproof.Spec.bezoutCheck_complete` |
| `ratLeCross` certifies `0 < d1`, `0 < d2`, and `n1 * d2 <= n2 * d1`. | `Mcproof.Spec.ratLeCross_sound` |
| Every fraction with `0 < d` satisfies `ratLeCross n d n d = true`. | `Mcproof.Spec.ratLeCross_refl_pos` |
| Accepted segment lists are non-empty and free of `.`, `..`, `/`, and NUL. | `Mcproof.Spec.cleanSegments_safe` |
| Every single safe segment `[s]` is accepted as `some [s]`. | `Mcproof.Spec.cleanSegments_singleton` |
| Quotient homomorphism heuristics satisfy `h(s) <= h(s') + 1` on every valid transition. | `Mcproof.Spec.quotientHeuristic_step_consistent` |
| Quotient homomorphism heuristics bound the length of every valid goal-reaching path. | `Mcproof.Spec.quotientHeuristic_admissible` |
| Pre-funded potentials preserve `h_hat(g) = 0` and inherit admissibility `h_hat(s) <= len`. | `Mcproof.Spec.prefundedHeuristic_admissible_and_goal` |
| Monotone resource `r(s') <= r(s)` repairs `1 + c * (r(s) - r(s'))` drops to `h_hat(s) <= h_hat(s') + 1`. | `Mcproof.Spec.prefundedHeuristic_step_consistent` |
| Concrete `12 -> 10` drop repairs to `11 -> 10` under `c = 1, r : 1 -> 0`. | `Mcproof.Spec.prefundedVal_bounded_drop_witness` |
| Non-negative operator-counting dual weights satisfy `dualObjective cs <= scale * planSum cost acts`. | `Mcproof.Spec.operatorCounting_dual_scaled_sound` |
| For `0 < scale`, `(dualObjective cs) / scale <= planSum cost acts`. | `Mcproof.Spec.operatorCounting_dual_div_admissible` |
| Executable `dualFloorNat` bounds `planCost` and evaluates `dualFloorNat 2 [(2,9),(1,8)] = 13`. | `Mcproof.Spec.dualFloorNat_sound_and_witness` |
| Cyclic mode-switch tax `(c + k - a) % k` satisfies triangle inequality for modes `< k`. | `Mcproof.Spec.cyclicSwitchTax_triangle` |
| Unrestricted `cyclicSwitchDist` satisfies identity, triangle inequality, and `k = 6` witnesses. | `Mcproof.Spec.cyclicSwitchDist_metric_and_witness` |
| Two-species conservation and irreversible harvests ensure global potential consistency and admissibility. | `Mcproof.Spec.conservation_harvest_potential_repair` |
| Collision-free trajectories induce unit vertex-split flows bounded by cumulative min-cut capacity. | `Mcproof.Spec.vertexSplit_unit_flow_horizon_bound` |
| Zero-self-loop quotient heuristics compose with monotone target deficits while preserving 1-step consistency. | `Mcproof.Spec.zeroSelfLoop_deficit_composition` |
| Exact rational ceiling `ceilDivNat` preserves `0` on goals, 1-step consistency, and admissibility. | `Mcproof.Spec.ceilDiv_step_consistent_and_admissible` |
| Division-free RMSNorm tangent projection `tangentProjScaled h delta` is orthogonal to `h`. | `Mcproof.Spec.rmsnorm_tangent_orthogonal` |
| Pairwise-orthogonal tangent adapter stacks inflate squared norm additively. | `Mcproof.Spec.rmsnorm_orthogonal_stack_norm_inflation` |
| Splitting total impulse `D = L * d` across `L` layers cuts quadratic shrinkage by factor `L`. | `Mcproof.Spec.multilayer_quadratic_shrinkage_reduction` |
| Elementwise gate inner product equals `diag(g^2)` metric and breaks naive `X X^T` orthogonality. | `Mcproof.Spec.swiglu_gate_metric_and_counterexample` |
| Projecting up-residuals orthogonal to `g ⊙ (W_down^T h_0)` zeroes radial post-gate inner product. | `Mcproof.Spec.swiglu_radial_null_orthogonality` |
| Orthogonal sibling cross-talk `[0, 32]` keeps `100%` scalar projection while adding `1024x` drift energy. | `Mcproof.Spec.scalar_projection_retention_illusion` |
| RMSNorm radial base-logit shrinkage lies inside `[D2 / (2*(R2 + D2)), D2 / (2*R2)]`. | `Mcproof.Spec.rmsnorm_rational_shrinkage_sandwich` |

## Oracle

`tests/run_tests.py` compares the `mcproof_lean` executable against an independent Python oracle using exact `int` and `fractions.Fraction` arithmetic across seeded random and mutated inputs.
