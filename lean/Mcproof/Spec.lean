/-
  Challenge specification for the mcproof Lean 4 reference package (v0.2).
  Each safety or soundness theorem is paired with a usefulness or non-vacuity
  theorem so a trivial constant or rejecting implementation fails `lake comparator --paranoid`.
-/

import Mcproof

open Mcproof
open Mcproof.TransitionBounds
open Mcproof.AdapterBounds

/-- Safety: when `lo <= hi`, `clampNat lo hi x` lies inside `[lo, hi]`. -/
theorem Mcproof.Spec.clampNat_in_range (lo hi x : Nat) (h : lo ≤ hi) :
    lo ≤ clampNat lo hi x ∧ clampNat lo hi x ≤ hi := sorry

/-- Usefulness: an in-range input is returned unchanged. -/
theorem Mcproof.Spec.clampNat_of_mem (lo hi x : Nat) (h1 : lo ≤ x) (h2 : x ≤ hi) :
    clampNat lo hi x = x := sorry

/-- Soundness: `bezoutCheck` returns `true` only when `a * x + b * y = g`. -/
theorem Mcproof.Spec.bezoutCheck_sound (a b x y g : Int) :
    bezoutCheck a b x y g = true → a * x + b * y = g := sorry

/-- Completeness: `bezoutCheck` accepts every valid integer witness. -/
theorem Mcproof.Spec.bezoutCheck_complete (a b x y g : Int) :
    a * x + b * y = g → bezoutCheck a b x y g = true := sorry

/-- Soundness: `ratLeCross` certifies positive denominators and exact cross-multiplied order. -/
theorem Mcproof.Spec.ratLeCross_sound (n1 d1 n2 d2 : Int) :
    ratLeCross n1 d1 n2 d2 = true → 0 < d1 ∧ 0 < d2 ∧ n1 * d2 ≤ n2 * d1 := sorry

/-- Usefulness: every fraction with positive denominator is less than or equal to itself. -/
theorem Mcproof.Spec.ratLeCross_refl_pos (n d : Int) (hd : 0 < d) :
    ratLeCross n d n d = true := sorry

/-- Safety: every segment accepted by `cleanSegments` is non-empty and free of traversal or `/`. -/
theorem Mcproof.Spec.cleanSegments_safe (segs out : List String) :
    cleanSegments segs = some out →
    out ≠ [] ∧ ∀ s ∈ out, s ≠ "" ∧ s ≠ "." ∧ s ≠ ".." ∧ ¬ s.contains '/' ∧ ¬ s.contains '\x00' := sorry

/-- Usefulness: a single safe segment is accepted unchanged (`none`-always implementations fail). -/
theorem Mcproof.Spec.cleanSegments_singleton (s : String)
    (hs : s ≠ "" ∧ s ≠ "." ∧ s ≠ ".." ∧ ¬ s.contains '/' ∧ ¬ s.contains '\x00') :
    cleanSegments [s] = some [s] := sorry

/-- Quotient homomorphism global 1-step consistency on the full state space. -/
theorem Mcproof.Spec.quotientHeuristic_step_consistent
    {S A Q : Type} (step : S → A → Option S) (pi : S → Q) (qEdge : Q → Q → Prop) (hQ : Q → Nat)
    (hproj : ∀ s a s', step s a = some s' → pi s = pi s' ∨ qEdge (pi s) (pi s'))
    (hq : ∀ u v, qEdge u v → hQ u ≤ hQ v + 1) :
    ∀ s a s', step s a = some s' → quotientHeuristic pi hQ s ≤ quotientHeuristic pi hQ s' + 1 := sorry

/-- Quotient homomorphism admissibility across every valid path reaching a goal state. -/
theorem Mcproof.Spec.quotientHeuristic_admissible
    {S A Q : Type} (step : S → A → Option S) (isGoal : S → Prop)
    (pi : S → Q) (qEdge : Q → Q → Prop) (hQ : Q → Nat)
    (hproj : ∀ s a s', step s a = some s' → pi s = pi s' ∨ qEdge (pi s) (pi s'))
    (hq : ∀ u v, qEdge u v → hQ u ≤ hQ v + 1)
    (hgoal : ∀ g, isGoal g → hQ (pi g) = 0) :
    ∀ s acts g, ValidPath step s acts g → isGoal g → quotientHeuristic pi hQ s ≤ acts.length := sorry

/-- Pre-funded resource potential goal preservation and admissibility inheritance. -/
theorem Mcproof.Spec.prefundedHeuristic_admissible_and_goal
    {S : Type} (h : S → Nat) (c : Nat) (r : S → Nat) :
    (∀ s, prefundedHeuristic h c r s ≤ h s) ∧
    (∀ g, h g = 0 → prefundedHeuristic h c r g = 0) ∧
    (∀ s len, h s ≤ len → prefundedHeuristic h c r s ≤ len) := sorry

/-- Pre-Funded Monotone Potential Repair Theorem: restores universal 1-step consistency in `Nat`. -/
theorem Mcproof.Spec.prefundedHeuristic_step_consistent
    {S : Type} (h : S → Nat) (c : Nat) (r : S → Nat) (s s' : S)
    (hmono : r s' ≤ r s)
    (hdrop : h s ≤ h s' + 1 + c * (r s - r s')) :
    prefundedHeuristic h c r s ≤ prefundedHeuristic h c r s' + 1 := sorry

/-- Non-vacuity witness for bounded 2-step drop repair (`h: 12 -> 10` repaired to `11 -> 10` under `r: 1 -> 0`). -/
theorem Mcproof.Spec.prefundedVal_bounded_drop_witness :
    prefundedVal 12 1 1 = 11 ∧
    prefundedVal 10 1 0 = 10 ∧
    prefundedVal 12 1 1 ≤ prefundedVal 10 1 0 + 1 := sorry

/-- Non-negative operator-counting / Farkas LP dual scaled lower-bound soundness. -/
theorem Mcproof.Spec.operatorCounting_dual_scaled_sound
    {A : Type} (cost : A → Nat) (scale : Nat) (cs : List (DualConstraint A)) (acts : List A)
    (hlandmarks : ∀ c ∈ cs, c.demand ≤ planSum c.coeff acts)
    (hfeasible : ∀ a, actionDualLoad cs a ≤ scale * cost a) :
    dualObjective cs ≤ scale * planSum cost acts := sorry

/-- Division-free integer dual floor admissibility `(dualObjective cs) / scale <= planSum cost acts`. -/
theorem Mcproof.Spec.operatorCounting_dual_div_admissible
    {A : Type} (cost : A → Nat) (scale : Nat) (cs : List (DualConstraint A)) (acts : List A)
    (hscale : 0 < scale)
    (hlandmarks : ∀ c ∈ cs, c.demand ≤ planSum c.coeff acts)
    (hfeasible : ∀ a, actionDualLoad cs a ≤ scale * cost a) :
    dualObjective cs / scale ≤ planSum cost acts := sorry

/-- Executable `dualFloorNat` soundness and non-trivial multi-constraint witness (`13`). -/
theorem Mcproof.Spec.dualFloorNat_sound_and_witness
    (scale planCost : Nat) (pairs : List (Nat × Nat))
    (hscale : 0 < scale)
    (hbound : dualObjectivePairs pairs ≤ scale * planCost) :
    dualFloorNat scale pairs ≤ planCost ∧ dualFloorNat 2 [(2, 9), (1, 8)] = 13 := sorry

/-- Cyclic mode-switch triangle inequality `cyclicSwitchTax k a c <= cyclicSwitchTax k a b + cyclicSwitchTax k b c` for modes `< k`. -/
theorem Mcproof.Spec.cyclicSwitchTax_triangle
    (k a b c : Nat) (hk : 0 < k) (ha : a < k) (hb : b < k) (hc : c < k) :
    cyclicSwitchTax k a c ≤ cyclicSwitchTax k a b + cyclicSwitchTax k b c := sorry

/-- Unrestricted `cyclicSwitchDist` metric admissibility (zero self-tax, triangle inequality, and `k = 6` witness). -/
theorem Mcproof.Spec.cyclicSwitchDist_metric_and_witness
    (k a b c : Nat) (hk : 0 < k) :
    cyclicSwitchDist k a a = 0 ∧
    cyclicSwitchDist k a c ≤ cyclicSwitchDist k a b + cyclicSwitchDist k b c ∧
    cyclicSwitchDist 6 1 5 = 4 ∧
    cyclicSwitchDist 6 5 1 = 2 := sorry

/-- Two-species conservation identity and global pre-funded potential repair under irreversible harvests on `I`. -/
theorem Mcproof.Spec.conservation_harvest_potential_repair
    {S A X : Type} (step : S → A → Option S) (isGoal : S → Prop)
    (U I : List X) (inA inB intact : S → X → Bool) (totalAtoms : Nat)
    (h : S → Nat) (c : Nat)
    (hconserve : ∀ s, countTrue (inA s) U + countTrue (inB s) U = totalAtoms)
    (hirrev : ∀ s a s', step s a = some s' → ∀ x ∈ I, intact s' x = true → intact s x = true)
    (hdrop : ∀ s a s', step s a = some s' →
      h s ≤ h s' + 1 + c * (intactSupply I intact s - intactSupply I intact s'))
    (hgoal : ∀ g, isGoal g → h g = 0) :
    (∀ s, countTrue (inA s) U = totalAtoms - countTrue (inB s) U) ∧
    (∀ s a s', step s a = some s' → intactSupply I intact s' ≤ intactSupply I intact s) ∧
    (∀ s a s', step s a = some s' →
      prefundedHeuristic h c (intactSupply I intact) s ≤
      prefundedHeuristic h c (intactSupply I intact) s' + 1) ∧
    (∀ s acts g, ValidPath step s acts g → isGoal g →
      prefundedHeuristic h c (intactSupply I intact) s ≤ acts.length) := sorry

/-- Vertex-split unit-capacity flow feasibility and time-expanded min-cut horizon lower bound. -/
theorem Mcproof.Spec.vertexSplit_unit_flow_horizon_bound
    {V : Type} (vertices : List V) (occ blocked S_cut : Nat → V → Bool)
    (cutCap : Nat → Nat) (capPerStep demand T : Nat)
    (hunblocked : ∀ t v, blocked t v = true → occ t v = false)
    (hstep_cut : ∀ t, t < T →
      tokensInCut vertices (occ t) (S_cut t) ≤
      tokensInCut vertices (occ (t + 1)) (S_cut (t + 1)) + cutCap t)
    (hcap_bound : ∀ t, t < T → cutCap t ≤ capPerStep)
    (hinit : demand ≤ tokensInCut vertices (occ 0) (S_cut 0))
    (hsink : tokensInCut vertices (occ T) (S_cut T) = 0) :
    (∀ t v, vertexArcFlow occ t v ≤ 1) ∧
    (∀ t v, blocked t v = true → vertexArcFlow occ t v = 0) ∧
    demand ≤ horizonCutCapacity cutCap T ∧
    demand ≤ capPerStep * T := sorry

/-- Zero-self-loop quotient + monotone deficit composition: preserves goal `0`, 1-step consistency, and admissibility. -/
theorem Mcproof.Spec.zeroSelfLoop_deficit_composition
    {S A Q : Type} (step : S → A → Option S) (isGoal : S → Prop) (isExt : A → Bool)
    (pi : S → Q) (hQ : Q → Nat) (K : Nat) (m : S → Nat)
    (hext_loop : ∀ s a s', step s a = some s' → isExt a = true → pi s' = pi s ∧ m s' ≤ m s + 1)
    (hint_step : ∀ s a s', step s a = some s' → isExt a = false → hQ (pi s) ≤ hQ (pi s') + 1 ∧ m s' ≤ m s)
    (hgoal : ∀ g, isGoal g → hQ (pi g) = 0 ∧ K ≤ m g) :
    (∀ g, isGoal g → composedDeficitHeuristic pi hQ K m g = 0) ∧
    (∀ s a s', step s a = some s' →
      composedDeficitHeuristic pi hQ K m s ≤ composedDeficitHeuristic pi hQ K m s' + 1) ∧
    (∀ s acts g, ValidPath step s acts g → isGoal g →
      composedDeficitHeuristic pi hQ K m s ≤ acts.length) := sorry

/-- Rational-ceiling 1-step consistency and admissibility preservation (`ceil(num(s) / scale)`). -/
theorem Mcproof.Spec.ceilDiv_step_consistent_and_admissible
    {S : Type} (num : S → Nat) (scale : Nat) (s s' g : S) (planLen : Nat)
    (hscale : 0 < scale)
    (hgoal : num g = 0)
    (hstep : num s ≤ num s' + scale)
    (hbound : num s ≤ scale * planLen) :
    ceilDivNat (num g) scale = 0 ∧
    ceilDivNat (num s) scale ≤ ceilDivNat (num s') scale + 1 ∧
    ceilDivNat (num s) scale ≤ planLen ∧
    ceilDivNat 13 6 = 3 := sorry

/-- Division-free RMSNorm tangent projection orthogonality `<h, ||h||^2 * delta - <h, delta> * h> = 0`. -/
theorem Mcproof.Spec.rmsnorm_tangent_orthogonal
    (h delta : List Int) (hlen : h.length = delta.length) :
    vecDot h (tangentProjScaled h delta) = 0 ∧
    tangentProjScaled [3, 4] [5, 0] = [80, -60] := sorry

/-- Additive squared-norm inflation under pairwise-orthogonal RMSNorm tangent adapter stacks. -/
theorem Mcproof.Spec.rmsnorm_orthogonal_stack_norm_inflation
    (h d1 d2 d3 : List Int)
    (hl1 : h.length = d1.length) (hl2 : h.length = d2.length) (hl3 : h.length = d3.length)
    (ho1 : vecDot h d1 = 0) (ho2 : vecDot h d2 = 0) (ho3 : vecDot h d3 = 0)
    (h12 : vecDot d1 d2 = 0) (h13 : vecDot d1 d3 = 0) (h23 : vecDot d2 d3 = 0) :
    vecNormSq (vecAdd h d1) = vecNormSq h + vecNormSq d1 ∧
    vecNormSq (vecAdd (vecAdd (vecAdd h d1) d2) d3) =
      vecNormSq h + vecNormSq d1 + vecNormSq d2 + vecNormSq d3 := sorry

/-- Multi-layer `1/L` quadratic radial-shrinkage reduction over `L` balanced layers. -/
theorem Mcproof.Spec.multilayer_quadratic_shrinkage_reduction
    (L d : Nat) (ds : List Nat) :
    L * sumSqNat (List.replicate L d) = sumNat (List.replicate L d) * sumNat (List.replicate L d) ∧
    sumSqNat ds ≤ sumNat ds * sumNat ds ∧
    (0 < d → 2 ≤ L → sumSqNat (List.replicate L d) < sumNat (List.replicate L d) * sumNat (List.replicate L d)) := sorry

/-- SwiGLU elementwise gate metric `<g ⊙ u, g ⊙ v> = <u, diag(g^2) v>` and pre-gate orthogonality counterexample. -/
theorem Mcproof.Spec.swiglu_gate_metric_and_counterexample
    (g u v : List Int) :
    vecDot (vecHadamard g u) (vecHadamard g v) = vecDot u (vecHadamard (vecSqDiag g) v) ∧
    vecDot [1, 1] [1, -1] = 0 ∧
    vecDot (vecHadamard [2, 1] [1, 1]) (vecHadamard [2, 1] [1, -1]) = 3 := sorry

/-- SwiGLU Hadamard adjoint radial-null hyperplane orthogonality `<g ⊙ tangentProj(g ⊙ w, u), w> = 0`. -/
theorem Mcproof.Spec.swiglu_radial_null_orthogonality
    (g u w : List Int) (hgu : g.length = u.length) (hgw : g.length = w.length) :
    vecDot (vecHadamard g (tangentProjScaled (vecHadamard g w) u)) w = 0 := sorry

/-- Scalar-projection subspace-retention illusion (`100%` inner-product retention with `1024x` orthogonal drift energy). -/
theorem Mcproof.Spec.scalar_projection_retention_illusion :
    vecDot [1, 0] [0, 32] = 0 ∧
    vecDot (vecAdd [1, 0] [0, 32]) [1, 0] = vecNormSq [1, 0] ∧
    vecNormSq (vecSub (vecAdd [1, 0] [0, 32]) [1, 0]) = 1024 * vecNormSq [1, 0] := sorry

/-- Exact rational sandwich `D2 / (2*(R2 + D2)) <= (qd - qn)/qd <= D2 / (2*R2)` for RMSNorm radial base-logit shrinkage. -/
theorem Mcproof.Spec.rmsnorm_rational_shrinkage_sandwich
    (R2 D2 qn qd : Int)
    (hR : 0 < R2) (hD : 0 ≤ D2) (hqn : 0 < qn) (hqd : 0 < qd)
    (heq : (R2 + D2) * (qn * qn) = R2 * (qd * qd)) :
    shrinkageSandwichCheck R2 D2 qn qd = true ∧
    D2 * qd ≤ 2 * (R2 + D2) * (qd - qn) ∧
    2 * R2 * (qd - qn) ≤ D2 * qd := sorry
