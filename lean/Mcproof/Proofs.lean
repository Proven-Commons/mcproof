/-
  Complete proofs of all theorems in `Mcproof/Spec.lean` (v0.2).
  Zero `sorry`, zero custom axioms, and zero compiler escape hatches.
-/

import Mcproof

open Mcproof
open Mcproof.TransitionBounds
open Mcproof.AdapterBounds

theorem Mcproof.Spec.clampNat_in_range (lo hi x : Nat) (h : lo ≤ hi) :
    lo ≤ clampNat lo hi x ∧ clampNat lo hi x ≤ hi := by
  unfold clampNat
  split
  · omega
  · split <;> omega

theorem Mcproof.Spec.clampNat_of_mem (lo hi x : Nat) (h1 : lo ≤ x) (h2 : x ≤ hi) :
    clampNat lo hi x = x := by
  unfold clampNat
  split
  · omega
  · split <;> omega

theorem Mcproof.Spec.bezoutCheck_sound (a b x y g : Int) :
    bezoutCheck a b x y g = true → a * x + b * y = g := by
  unfold bezoutCheck
  intro h
  exact of_decide_eq_true h

theorem Mcproof.Spec.bezoutCheck_complete (a b x y g : Int) :
    a * x + b * y = g → bezoutCheck a b x y g = true := by
  unfold bezoutCheck
  intro h
  exact decide_eq_true h

theorem Mcproof.Spec.ratLeCross_sound (n1 d1 n2 d2 : Int) :
    ratLeCross n1 d1 n2 d2 = true → 0 < d1 ∧ 0 < d2 ∧ n1 * d2 ≤ n2 * d1 := by
  unfold ratLeCross
  intro h
  exact of_decide_eq_true h

theorem Mcproof.Spec.ratLeCross_refl_pos (n d : Int) (hd : 0 < d) :
    ratLeCross n d n d = true := by
  unfold ratLeCross
  apply decide_eq_true
  exact ⟨hd, hd, Int.le_refl (n * d)⟩

theorem Mcproof.Spec.cleanSegments_safe (segs out : List String) :
    cleanSegments segs = some out →
    out ≠ [] ∧ ∀ s ∈ out, s ≠ "" ∧ s ≠ "." ∧ s ≠ ".." ∧ ¬ s.contains '/' ∧ ¬ s.contains '\x00' := by
  intro h
  cases segs with
  | nil =>
    simp [cleanSegments] at h
  | cons hd tl =>
    change (if (hd :: tl).all isSafeSegment = true then some (hd :: tl) else none) = some out at h
    by_cases hall : (hd :: tl).all isSafeSegment = true
    · simp [hall] at h
      subst h
      refine ⟨by simp, ?_⟩
      intro s hs
      have hseg : isSafeSegment s = true := List.all_eq_true.mp hall s hs
      unfold isSafeSegment at hseg
      exact of_decide_eq_true hseg
    · simp [hall] at h

theorem Mcproof.Spec.cleanSegments_singleton (s : String)
    (hs : s ≠ "" ∧ s ≠ "." ∧ s ≠ ".." ∧ ¬ s.contains '/' ∧ ¬ s.contains '\x00') :
    cleanSegments [s] = some [s] := by
  unfold cleanSegments
  have hseg : isSafeSegment s = true := by
    unfold isSafeSegment
    exact decide_eq_true hs
  simp [hseg]

theorem Mcproof.Spec.quotientHeuristic_step_consistent
    {S A Q : Type} (step : S → A → Option S) (pi : S → Q) (qEdge : Q → Q → Prop) (hQ : Q → Nat)
    (hproj : ∀ s a s', step s a = some s' → pi s = pi s' ∨ qEdge (pi s) (pi s'))
    (hq : ∀ u v, qEdge u v → hQ u ≤ hQ v + 1) :
    ∀ s a s', step s a = some s' → quotientHeuristic pi hQ s ≤ quotientHeuristic pi hQ s' + 1 := by
  intro s a s' hstep
  unfold quotientHeuristic
  cases hproj s a s' hstep with
  | inl heq =>
    rw [heq]
    omega
  | inr hedge =>
    exact hq (pi s) (pi s') hedge

theorem Mcproof.Spec.quotientHeuristic_admissible
    {S A Q : Type} (step : S → A → Option S) (isGoal : S → Prop)
    (pi : S → Q) (qEdge : Q → Q → Prop) (hQ : Q → Nat)
    (hproj : ∀ s a s', step s a = some s' → pi s = pi s' ∨ qEdge (pi s) (pi s'))
    (hq : ∀ u v, qEdge u v → hQ u ≤ hQ v + 1)
    (hgoal : ∀ g, isGoal g → hQ (pi g) = 0) :
    ∀ s acts g, ValidPath step s acts g → isGoal g → quotientHeuristic pi hQ s ≤ acts.length := by
  intro s acts g hpath
  induction hpath with
  | nil s0 =>
    intro hg
    unfold quotientHeuristic
    have hz : hQ (pi s0) = 0 := hgoal s0 hg
    simp [hz]
  | @cons s0 s1 g0 a as hstep _ ih =>
    intro hg
    have hcons : quotientHeuristic pi hQ s0 ≤ quotientHeuristic pi hQ s1 + 1 :=
      Mcproof.Spec.quotientHeuristic_step_consistent step pi qEdge hQ hproj hq s0 a s1 hstep
    have htail : quotientHeuristic pi hQ s1 ≤ as.length := ih hg
    simp only [List.length_cons]
    omega

theorem Mcproof.Spec.prefundedHeuristic_admissible_and_goal
    {S : Type} (h : S → Nat) (c : Nat) (r : S → Nat) :
    (∀ s, prefundedHeuristic h c r s ≤ h s) ∧
    (∀ g, h g = 0 → prefundedHeuristic h c r g = 0) ∧
    (∀ s len, h s ≤ len → prefundedHeuristic h c r s ≤ len) := by
  refine ⟨?_, ?_, ?_⟩
  · intro s
    unfold prefundedHeuristic prefundedVal
    omega
  · intro g hg
    unfold prefundedHeuristic prefundedVal
    omega
  · intro s len hle
    unfold prefundedHeuristic prefundedVal
    omega

theorem Mcproof.Spec.prefundedHeuristic_step_consistent
    {S : Type} (h : S → Nat) (c : Nat) (r : S → Nat) (s s' : S)
    (hmono : r s' ≤ r s)
    (hdrop : h s ≤ h s' + 1 + c * (r s - r s')) :
    prefundedHeuristic h c r s ≤ prefundedHeuristic h c r s' + 1 := by
  unfold prefundedHeuristic prefundedVal
  have hmul_le : c * r s' ≤ c * r s := Nat.mul_le_mul_left c hmono
  have hdist : c * (r s - r s') = c * r s - c * r s' := Nat.mul_sub_left_distrib c (r s) (r s')
  rw [hdist] at hdrop
  omega

theorem Mcproof.Spec.prefundedVal_bounded_drop_witness :
    prefundedVal 12 1 1 = 11 ∧
    prefundedVal 10 1 0 = 10 ∧
    prefundedVal 12 1 1 ≤ prefundedVal 10 1 0 + 1 := by
  unfold prefundedVal
  omega

private theorem planSum_add {A : Type} (f g : A → Nat) (acts : List A) :
    planSum (fun a => f a + g a) acts = planSum f acts + planSum g acts := by
  induction acts with
  | nil => rfl
  | cons a as ih =>
    simp only [planSum, ih]
    omega

private theorem planSum_mul_left {A : Type} (w : Nat) (f : A → Nat) (acts : List A) :
    w * planSum f acts = planSum (fun a => w * f a) acts := by
  induction acts with
  | nil => simp [planSum]
  | cons a as ih =>
    simp only [planSum, Nat.mul_add, ih]

private theorem planSum_mono {A : Type} {f g : A → Nat} (acts : List A)
    (hfg : ∀ a, f a ≤ g a) :
    planSum f acts ≤ planSum g acts := by
  induction acts with
  | nil => simp [planSum]
  | cons a as ih =>
    simp only [planSum]
    exact Nat.add_le_add (hfg a) ih

private theorem dualObjective_le_actionDualLoad_sum
    {A : Type} (cs : List (DualConstraint A)) (acts : List A)
    (hlandmarks : ∀ c ∈ cs, c.demand ≤ planSum c.coeff acts) :
    dualObjective cs ≤ planSum (actionDualLoad cs) acts := by
  induction cs with
  | nil =>
    simp [dualObjective, actionDualLoad]
  | cons c rest ih =>
    have hc : c.demand ≤ planSum c.coeff acts := hlandmarks c (by simp)
    have hwc : c.weight * c.demand ≤ c.weight * planSum c.coeff acts :=
      Nat.mul_le_mul_left c.weight hc
    have hrest : dualObjective rest ≤ planSum (actionDualLoad rest) acts := by
      apply ih
      intro c' hc'
      exact hlandmarks c' (by simp [hc'])
    have hsum :
        c.weight * planSum c.coeff acts + planSum (actionDualLoad rest) acts =
        planSum (actionDualLoad (c :: rest)) acts := by
      rw [planSum_mul_left]
      exact (planSum_add (fun a => c.weight * c.coeff a) (actionDualLoad rest) acts).symm
    unfold dualObjective
    calc
      c.weight * c.demand + dualObjective rest
        ≤ c.weight * planSum c.coeff acts + planSum (actionDualLoad rest) acts :=
          Nat.add_le_add hwc hrest
      _ = planSum (actionDualLoad (c :: rest)) acts := hsum

theorem Mcproof.Spec.operatorCounting_dual_scaled_sound
    {A : Type} (cost : A → Nat) (scale : Nat) (cs : List (DualConstraint A)) (acts : List A)
    (hlandmarks : ∀ c ∈ cs, c.demand ≤ planSum c.coeff acts)
    (hfeasible : ∀ a, actionDualLoad cs a ≤ scale * cost a) :
    dualObjective cs ≤ scale * planSum cost acts := by
  have h1 : dualObjective cs ≤ planSum (actionDualLoad cs) acts :=
    dualObjective_le_actionDualLoad_sum cs acts hlandmarks
  have h2 : planSum (actionDualLoad cs) acts ≤ planSum (fun a => scale * cost a) acts :=
    planSum_mono acts hfeasible
  have h3 : planSum (fun a => scale * cost a) acts = scale * planSum cost acts :=
    (planSum_mul_left scale cost acts).symm
  omega

theorem Mcproof.Spec.operatorCounting_dual_div_admissible
    {A : Type} (cost : A → Nat) (scale : Nat) (cs : List (DualConstraint A)) (acts : List A)
    (hscale : 0 < scale)
    (hlandmarks : ∀ c ∈ cs, c.demand ≤ planSum c.coeff acts)
    (hfeasible : ∀ a, actionDualLoad cs a ≤ scale * cost a) :
    dualObjective cs / scale ≤ planSum cost acts := by
  have hscaled : dualObjective cs ≤ scale * planSum cost acts :=
    Mcproof.Spec.operatorCounting_dual_scaled_sound cost scale cs acts hlandmarks hfeasible
  have hdiv : dualObjective cs / scale * scale ≤ dualObjective cs :=
    Nat.div_mul_le_self (dualObjective cs) scale
  have hprod : dualObjective cs / scale * scale ≤ planSum cost acts * scale := by
    have hcomm : scale * planSum cost acts = planSum cost acts * scale := Nat.mul_comm scale (planSum cost acts)
    omega
  exact Nat.le_of_mul_le_mul_right hprod hscale

theorem Mcproof.Spec.dualFloorNat_sound_and_witness
    (scale planCost : Nat) (pairs : List (Nat × Nat))
    (hscale : 0 < scale)
    (hbound : dualObjectivePairs pairs ≤ scale * planCost) :
    dualFloorNat scale pairs ≤ planCost ∧ dualFloorNat 2 [(2, 9), (1, 8)] = 13 := by
  refine ⟨?_, ?_⟩
  · unfold dualFloorNat
    have hne : (scale == 0) = false := by
      cases scale with
      | zero => omega
      | succ _ => rfl
    rw [hne]
    simp only [Bool.false_eq_true, ↓reduceIte]
    have hdiv : dualObjectivePairs pairs / scale * scale ≤ dualObjectivePairs pairs :=
      Nat.div_mul_le_self (dualObjectivePairs pairs) scale
    have hprod : dualObjectivePairs pairs / scale * scale ≤ planCost * scale := by
      have hcomm : scale * planCost = planCost * scale := Nat.mul_comm scale planCost
      omega
    exact Nat.le_of_mul_le_mul_right hprod hscale
  · rfl

private theorem cyclicStep_val {k u v : Nat} (hu : u < k) (hv : v < k) :
    (v + k - u) % k = if u ≤ v then v - u else v + k - u := by
  by_cases huv : u ≤ v
  · simp only [huv, ↓reduceIte]
    have h1 : v + k - u = (v - u) + k := by omega
    rw [h1, Nat.add_mod_right]
    exact Nat.mod_eq_of_lt (by omega)
  · simp only [huv, ↓reduceIte]
    exact Nat.mod_eq_of_lt (by omega)

theorem Mcproof.Spec.cyclicSwitchTax_triangle
    (k a b c : Nat) (_hk : 0 < k) (ha : a < k) (hb : b < k) (hc : c < k) :
    cyclicSwitchTax k a c ≤ cyclicSwitchTax k a b + cyclicSwitchTax k b c := by
  unfold cyclicSwitchTax
  rw [cyclicStep_val ha hc, cyclicStep_val ha hb, cyclicStep_val hb hc]
  by_cases hab : a ≤ b <;> by_cases hbc : b ≤ c <;> by_cases hac : a ≤ c <;>
    simp only [hab, hbc, hac, ↓reduceIte] <;> omega

theorem Mcproof.Spec.cyclicSwitchDist_metric_and_witness
    (k a b c : Nat) (hk : 0 < k) :
    cyclicSwitchDist k a a = 0 ∧
    cyclicSwitchDist k a c ≤ cyclicSwitchDist k a b + cyclicSwitchDist k b c ∧
    cyclicSwitchDist 6 1 5 = 4 ∧
    cyclicSwitchDist 6 5 1 = 2 := by
  have hne : (k == 0) = false := by
    cases k with
    | zero => omega
    | succ _ => rfl
  refine ⟨?_, ?_, rfl, rfl⟩
  · unfold cyclicSwitchDist cyclicSwitchTax
    rw [hne]
    simp only [Bool.false_eq_true, ↓reduceIte]
    have hma : a % k < k := Nat.mod_lt a hk
    rw [cyclicStep_val hma hma]
    simp
  · unfold cyclicSwitchDist
    rw [hne]
    simp only [Bool.false_eq_true, ↓reduceIte]
    exact Mcproof.Spec.cyclicSwitchTax_triangle k (a % k) (b % k) (c % k) hk
      (Nat.mod_lt a hk) (Nat.mod_lt b hk) (Nat.mod_lt c hk)

private theorem countTrue_mono {X : Type} (p q : X → Bool) (xs : List X)
    (himp : ∀ x ∈ xs, p x = true → q x = true) :
    countTrue p xs ≤ countTrue q xs := by
  induction xs with
  | nil => simp [countTrue]
  | cons x rest ih =>
    have hx : (if p x = true then 1 else 0) ≤ (if q x = true then 1 else 0) := by
      cases hp : p x with
      | false => simp
      | true =>
        have hqx : q x = true := himp x (by simp) hp
        simp [hqx]
    have hrest : countTrue p rest ≤ countTrue q rest := by
      apply ih
      intro y hy
      exact himp y (by simp [hy])
    simp only [countTrue]
    omega

private theorem stepConsistent_implies_admissible
    {S A : Type} (step : S → A → Option S) (isGoal : S → Prop) (f : S → Nat)
    (hstep : ∀ s a s', step s a = some s' → f s ≤ f s' + 1)
    (hgoal : ∀ g, isGoal g → f g = 0) :
    ∀ s acts g, ValidPath step s acts g → isGoal g → f s ≤ acts.length := by
  intro s acts g hpath
  induction hpath with
  | nil s0 =>
    intro hg
    have hz : f s0 = 0 := hgoal s0 hg
    simp [hz]
  | @cons s0 s1 g0 a as hs _ ih =>
    intro hg
    have h1 : f s0 ≤ f s1 + 1 := hstep s0 a s1 hs
    have h2 : f s1 ≤ as.length := ih hg
    simp only [List.length_cons]
    omega

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
      prefundedHeuristic h c (intactSupply I intact) s ≤ acts.length) := by
  have hmono_all : ∀ s a s', step s a = some s' → intactSupply I intact s' ≤ intactSupply I intact s := by
    intro s a s' hs
    unfold intactSupply
    exact countTrue_mono (intact s') (intact s) I (hirrev s a s' hs)
  have hcons_all : ∀ s a s', step s a = some s' →
      prefundedHeuristic h c (intactSupply I intact) s ≤
      prefundedHeuristic h c (intactSupply I intact) s' + 1 := by
    intro s a s' hs
    exact Mcproof.Spec.prefundedHeuristic_step_consistent h c (intactSupply I intact) s s'
      (hmono_all s a s' hs) (hdrop s a s' hs)
  refine ⟨?_, hmono_all, hcons_all, ?_⟩
  · intro s
    have hc_eq : countTrue (inA s) U + countTrue (inB s) U = totalAtoms := hconserve s
    omega
  · apply stepConsistent_implies_admissible step isGoal (prefundedHeuristic h c (intactSupply I intact)) hcons_all
    intro g hg
    have hz : h g = 0 := hgoal g hg
    unfold prefundedHeuristic prefundedVal
    omega

private theorem cut_telescope_bound
    {V : Type} (vertices : List V) (occ S_cut : Nat → V → Bool) (cutCap : Nat → Nat) :
    ∀ T : Nat,
      (∀ t, t < T →
        tokensInCut vertices (occ t) (S_cut t) ≤
        tokensInCut vertices (occ (t + 1)) (S_cut (t + 1)) + cutCap t) →
      tokensInCut vertices (occ 0) (S_cut 0) ≤
      tokensInCut vertices (occ T) (S_cut T) + horizonCutCapacity cutCap T := by
  intro T
  induction T with
  | zero =>
    intro _
    simp [horizonCutCapacity]
  | succ n ih =>
    intro hstep
    have hprev :
        tokensInCut vertices (occ 0) (S_cut 0) ≤
        tokensInCut vertices (occ n) (S_cut n) + horizonCutCapacity cutCap n :=
      ih (fun t ht => hstep t (by omega))
    have hlast :
        tokensInCut vertices (occ n) (S_cut n) ≤
        tokensInCut vertices (occ (n + 1)) (S_cut (n + 1)) + cutCap n :=
      hstep n (by omega)
    simp only [horizonCutCapacity]
    omega

private theorem horizonCutCapacity_le_mul (cutCap : Nat → Nat) (capPerStep : Nat) :
    ∀ T : Nat, (∀ t, t < T → cutCap t ≤ capPerStep) → horizonCutCapacity cutCap T ≤ capPerStep * T := by
  intro T
  induction T with
  | zero =>
    intro _
    simp [horizonCutCapacity]
  | succ n ih =>
    intro hcap
    have hprev : horizonCutCapacity cutCap n ≤ capPerStep * n :=
      ih (fun t ht => hcap t (by omega))
    have hlast : cutCap n ≤ capPerStep := hcap n (by omega)
    simp only [horizonCutCapacity, Nat.mul_succ]
    omega

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
    demand ≤ capPerStep * T := by
  have htel :
      tokensInCut vertices (occ 0) (S_cut 0) ≤
      tokensInCut vertices (occ T) (S_cut T) + horizonCutCapacity cutCap T :=
    cut_telescope_bound vertices occ S_cut cutCap T hstep_cut
  have hmul : horizonCutCapacity cutCap T ≤ capPerStep * T :=
    horizonCutCapacity_le_mul cutCap capPerStep T hcap_bound
  refine ⟨?_, ?_, ?_, ?_⟩
  · intro t v
    unfold vertexArcFlow
    cases occ t v <;> simp
  · intro t v hb
    unfold vertexArcFlow
    have hocc : occ t v = false := hunblocked t v hb
    simp [hocc]
  · omega
  · omega

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
      composedDeficitHeuristic pi hQ K m s ≤ acts.length) := by
  have hgoal_z : ∀ g, isGoal g → composedDeficitHeuristic pi hQ K m g = 0 := by
    intro g hg
    obtain ⟨hq0, hmk⟩ := hgoal g hg
    unfold composedDeficitHeuristic quotientHeuristic deficitNat
    omega
  have hstep_c : ∀ s a s', step s a = some s' →
      composedDeficitHeuristic pi hQ K m s ≤ composedDeficitHeuristic pi hQ K m s' + 1 := by
    intro s a s' hs
    unfold composedDeficitHeuristic quotientHeuristic deficitNat
    cases he : isExt a with
    | true =>
      obtain ⟨hpi, hm⟩ := hext_loop s a s' hs he
      rw [hpi]
      omega
    | false =>
      obtain ⟨hq, hm⟩ := hint_step s a s' hs he
      omega
  refine ⟨hgoal_z, hstep_c, ?_⟩
  exact stepConsistent_implies_admissible step isGoal (composedDeficitHeuristic pi hQ K m) hstep_c hgoal_z

theorem Mcproof.Spec.ceilDiv_step_consistent_and_admissible
    {S : Type} (num : S → Nat) (scale : Nat) (s s' g : S) (planLen : Nat)
    (hscale : 0 < scale)
    (hgoal : num g = 0)
    (hstep : num s ≤ num s' + scale)
    (hbound : num s ≤ scale * planLen) :
    ceilDivNat (num g) scale = 0 ∧
    ceilDivNat (num s) scale ≤ ceilDivNat (num s') scale + 1 ∧
    ceilDivNat (num s) scale ≤ planLen ∧
    ceilDivNat 13 6 = 3 := by
  have hne : (scale == 0) = false := by
    cases scale with
    | zero => omega
    | succ _ => rfl
  refine ⟨?_, ?_, ?_, rfl⟩
  · unfold ceilDivNat
    rw [hne, hgoal]
    simp only [Bool.false_eq_true, ↓reduceIte]
    exact Nat.div_eq_of_lt (by omega)
  · unfold ceilDivNat
    rw [hne]
    simp only [Bool.false_eq_true, ↓reduceIte]
    have hle : num s + scale - 1 ≤ (num s' + scale - 1) + scale := by omega
    have hdiv : (num s + scale - 1) / scale ≤ ((num s' + scale - 1) + scale) / scale :=
      Nat.div_le_div_right hle
    rw [Nat.add_div_right (num s' + scale - 1) hscale] at hdiv
    exact hdiv
  · unfold ceilDivNat
    rw [hne]
    simp only [Bool.false_eq_true, ↓reduceIte]
    have hmul : (num s + scale - 1) / scale * scale ≤ num s + scale - 1 :=
      Nat.div_mul_le_self (num s + scale - 1) scale
    have hcomm : scale * planLen = planLen * scale := Nat.mul_comm scale planLen
    have hlt : (num s + scale - 1) / scale * scale < (planLen + 1) * scale := by
      rw [Nat.add_mul, Nat.one_mul]
      omega
    have hlt_q : (num s + scale - 1) / scale < planLen + 1 := by
      by_cases hge : planLen + 1 ≤ (num s + scale - 1) / scale
      · have hcontra : (planLen + 1) * scale ≤ (num s + scale - 1) / scale * scale :=
          Nat.mul_le_mul_right scale hge
        omega
      · omega
    omega

-- AdapterBounds helper lemmas & proofs (theorems 23..29) ----------------------

private theorem vecDot_comm : ∀ (u v : List Int), vecDot u v = vecDot v u
  | [], [] => rfl
  | [], _ :: _ => rfl
  | _ :: _, [] => rfl
  | x :: xs, y :: ys => by
      simp [vecDot, Int.mul_comm, vecDot_comm xs ys]

private theorem vecDot_scale_right (c : Int) : ∀ (u v : List Int),
    vecDot u (vecScale c v) = c * vecDot u v
  | [], _ => by simp [vecDot]
  | _ :: _, [] => by simp [vecDot, vecScale]
  | _ :: xs, _ :: ys => by
      simp [vecDot, vecScale, vecDot_scale_right c xs ys, Int.mul_add, Int.mul_left_comm]

private theorem vecDot_sub_right : ∀ (h u v : List Int),
    u.length = v.length →
    vecDot h (vecSub u v) = vecDot h u - vecDot h v
  | [], _, _, _ => by simp [vecDot]
  | _ :: _, [], [], _ => by simp [vecDot, vecSub]
  | _ :: _, [], _ :: _, hlen => by cases hlen
  | _ :: _, _ :: _, [], hlen => by cases hlen
  | _ :: xs, _ :: as, _ :: bs, hlen => by
      simp [vecDot, vecSub, vecDot_sub_right xs as bs (Nat.succ.inj hlen), Int.mul_sub]
      omega

private theorem vecScale_length (c : Int) : ∀ (v : List Int), (vecScale c v).length = v.length
  | [] => rfl
  | _ :: xs => by simp [vecScale, vecScale_length c xs]

private theorem vecAdd_length : ∀ (u v : List Int), u.length = v.length → (vecAdd u v).length = u.length
  | [], [], _ => rfl
  | [], _ :: _, h => by cases h
  | _ :: _, [], h => by cases h
  | _ :: xs, _ :: ys, h => by
      simp [vecAdd, vecAdd_length xs ys (Nat.succ.inj h)]

private theorem vecHadamard_length : ∀ (g w : List Int), g.length = w.length → (vecHadamard g w).length = g.length
  | [], [], _ => rfl
  | [], _ :: _, h => by cases h
  | _ :: _, [], h => by cases h
  | _ :: gs, _ :: ws, h => by simp [vecHadamard, vecHadamard_length gs ws (Nat.succ.inj h)]

private theorem vecDot_add_right : ∀ (w u v : List Int),
    u.length = v.length →
    vecDot w (vecAdd u v) = vecDot w u + vecDot w v
  | [], _, _, _ => by simp [vecDot]
  | _ :: _, [], [], _ => by simp [vecDot, vecAdd]
  | _ :: _, [], _ :: _, h => by cases h
  | _ :: _, _ :: _, [], h => by cases h
  | _ :: zs, _ :: xs, _ :: ys, h => by
      simp [vecDot, vecAdd, vecDot_add_right zs xs ys (Nat.succ.inj h), Int.mul_add]
      omega

private theorem vecDot_add_left : ∀ (u v w : List Int),
    u.length = v.length →
    vecDot (vecAdd u v) w = vecDot u w + vecDot v w
  | [], [], _, _ => by simp [vecDot, vecAdd]
  | [], _ :: _, _, h => by cases h
  | _ :: _, [], _, h => by cases h
  | _ :: _, _ :: _, [], _ => by simp [vecDot, vecAdd]
  | _ :: xs, _ :: ys, _ :: zs, h => by
      simp [vecDot, vecAdd, vecDot_add_left xs ys zs (Nat.succ.inj h), Int.add_mul]
      omega

private theorem vecNormSq_add : ∀ (u v : List Int),
    u.length = v.length →
    vecNormSq (vecAdd u v) = vecNormSq u + 2 * vecDot u v + vecNormSq v := by
  intro u v hlen
  unfold vecNormSq
  rw [vecDot_add_left u v (vecAdd u v) hlen]
  rw [vecDot_add_right u u v hlen, vecDot_add_right v u v hlen]
  rw [vecDot_comm v u]
  omega

private theorem tangent_orth_aux (h delta : List Int) (hlen : h.length = delta.length) :
    vecDot h (tangentProjScaled h delta) = 0 := by
  unfold tangentProjScaled
  have hlen_sc : (vecScale (vecNormSq h) delta).length = (vecScale (vecDot h delta) h).length := by
    rw [vecScale_length, vecScale_length, hlen]
  rw [vecDot_sub_right h _ _ hlen_sc, vecDot_scale_right, vecDot_scale_right]
  unfold vecNormSq
  rw [Int.mul_comm (vecDot h h) (vecDot h delta)]
  omega

theorem Mcproof.Spec.rmsnorm_tangent_orthogonal
    (h delta : List Int) (hlen : h.length = delta.length) :
    vecDot h (tangentProjScaled h delta) = 0 ∧
    tangentProjScaled [3, 4] [5, 0] = [80, -60] := by
  exact ⟨tangent_orth_aux h delta hlen, by decide⟩

theorem Mcproof.Spec.rmsnorm_orthogonal_stack_norm_inflation
    (h d1 d2 d3 : List Int)
    (hl1 : h.length = d1.length) (hl2 : h.length = d2.length) (hl3 : h.length = d3.length)
    (ho1 : vecDot h d1 = 0) (ho2 : vecDot h d2 = 0) (ho3 : vecDot h d3 = 0)
    (h12 : vecDot d1 d2 = 0) (h13 : vecDot d1 d3 = 0) (h23 : vecDot d2 d3 = 0) :
    vecNormSq (vecAdd h d1) = vecNormSq h + vecNormSq d1 ∧
    vecNormSq (vecAdd (vecAdd (vecAdd h d1) d2) d3) =
      vecNormSq h + vecNormSq d1 + vecNormSq d2 + vecNormSq d3 := by
  have h_hd1 : vecNormSq (vecAdd h d1) = vecNormSq h + vecNormSq d1 := by
    rw [vecNormSq_add h d1 hl1, ho1]
    omega
  refine ⟨h_hd1, ?_⟩
  have hlen_hd1 : (vecAdd h d1).length = d2.length := by
    rw [vecAdd_length h d1 hl1, hl2]
  have hdot_hd1_d2 : vecDot (vecAdd h d1) d2 = 0 := by
    rw [vecDot_add_left h d1 d2 hl1, ho2, h12]
    omega
  have h_hd12 : vecNormSq (vecAdd (vecAdd h d1) d2) = vecNormSq h + vecNormSq d1 + vecNormSq d2 := by
    rw [vecNormSq_add (vecAdd h d1) d2 hlen_hd1, hdot_hd1_d2, h_hd1]
    omega
  have hlen_hd12 : (vecAdd (vecAdd h d1) d2).length = d3.length := by
    rw [vecAdd_length (vecAdd h d1) d2 hlen_hd1, vecAdd_length h d1 hl1, hl3]
  have hdot_hd12_d3 : vecDot (vecAdd (vecAdd h d1) d2) d3 = 0 := by
    rw [vecDot_add_left (vecAdd h d1) d2 d3 hlen_hd1, vecDot_add_left h d1 d3 hl1, ho3, h13, h23]
    omega
  rw [vecNormSq_add (vecAdd (vecAdd h d1) d2) d3 hlen_hd12, hdot_hd12_d3, h_hd12]
  omega

private theorem sumNat_replicate : ∀ (L d : Nat), sumNat (List.replicate L d) = L * d
  | 0, _ => by simp [sumNat]
  | L + 1, d => by
      simp [List.replicate_succ, sumNat, sumNat_replicate L d, Nat.add_mul]
      omega

private theorem sumSqNat_replicate : ∀ (L d : Nat), sumSqNat (List.replicate L d) = L * (d * d)
  | 0, _ => by simp [sumSqNat]
  | L + 1, d => by
      simp [List.replicate_succ, sumSqNat, sumSqNat_replicate L d, Nat.add_mul]
      omega

private theorem sumSqNat_le_sq_sumNat : ∀ (ds : List Nat), sumSqNat ds ≤ sumNat ds * sumNat ds
  | [] => by simp [sumSqNat, sumNat]
  | x :: xs => by
      have ih := sumSqNat_le_sq_sumNat xs
      simp [sumSqNat, sumNat]
      have h_expand : (x + sumNat xs) * (x + sumNat xs) =
          x * x + sumNat xs * sumNat xs + 2 * (x * sumNat xs) := by
        rw [Nat.add_mul, Nat.mul_add, Nat.mul_add, Nat.mul_comm (sumNat xs) x]
        omega
      omega

theorem Mcproof.Spec.multilayer_quadratic_shrinkage_reduction (L d : Nat) (ds : List Nat) :
    L * sumSqNat (List.replicate L d) = sumNat (List.replicate L d) * sumNat (List.replicate L d) ∧
    sumSqNat ds ≤ sumNat ds * sumNat ds ∧
    (0 < d → 2 ≤ L → sumSqNat (List.replicate L d) < sumNat (List.replicate L d) * sumNat (List.replicate L d)) := by
  refine ⟨?_, sumSqNat_le_sq_sumNat ds, ?_⟩
  · rw [sumSqNat_replicate, sumNat_replicate]
    simp [Nat.mul_comm, Nat.mul_left_comm]
  · intro hd hL
    rw [sumSqNat_replicate, sumNat_replicate]
    have hdd : 0 < d * d := Nat.mul_pos hd hd
    have hpos : 0 < L * (d * d) := Nat.mul_pos (by omega) hdd
    have h1 : 1 * (L * (d * d)) < L * (L * (d * d)) :=
      Nat.mul_lt_mul_of_pos_right (by omega : 1 < L) hpos
    have h_assoc : L * (L * (d * d)) = (L * d) * (L * d) := by
      simp [Nat.mul_comm, Nat.mul_left_comm]
    omega

private theorem hadamard_dot_eq_sqDiag_metric : ∀ (g u v : List Int),
    vecDot (vecHadamard g u) (vecHadamard g v) = vecDot u (vecHadamard (vecSqDiag g) v)
  | [], [], _ => rfl
  | [], _ :: _, _ => rfl
  | _ :: _, [], _ => rfl
  | _ :: _, _ :: _, [] => by simp [vecDot, vecHadamard, vecSqDiag]
  | x :: xs, a :: as, b :: bs => by
      simp [vecDot, vecHadamard, vecSqDiag, hadamard_dot_eq_sqDiag_metric xs as bs]
      have hterm : (x * a) * (x * b) = a * (x * x * b) := by
        simp [Int.mul_comm, Int.mul_left_comm]
      rw [hterm]

theorem Mcproof.Spec.swiglu_gate_metric_and_counterexample (g u v : List Int) :
    vecDot (vecHadamard g u) (vecHadamard g v) = vecDot u (vecHadamard (vecSqDiag g) v) ∧
    vecDot [1, 1] [1, -1] = 0 ∧
    vecDot (vecHadamard [2, 1] [1, 1]) (vecHadamard [2, 1] [1, -1]) = 3 := by
  exact ⟨hadamard_dot_eq_sqDiag_metric g u v, by decide, by decide⟩

private theorem vecDot_hadamard_adjoint : ∀ (g u w : List Int),
    vecDot (vecHadamard g u) w = vecDot u (vecHadamard g w)
  | [], [], _ => rfl
  | [], _ :: _, _ => rfl
  | _ :: _, [], _ => rfl
  | _ :: _, _ :: _, [] => by simp [vecDot, vecHadamard]
  | x :: xs, a :: as, b :: bs => by
      simp [vecDot, vecHadamard, vecDot_hadamard_adjoint xs as bs]
      have h_assoc : x * a * b = a * (x * b) := by
        simp [Int.mul_comm, Int.mul_left_comm]
      rw [h_assoc]

theorem Mcproof.Spec.swiglu_radial_null_orthogonality
    (g u w : List Int) (hgu : g.length = u.length) (hgw : g.length = w.length) :
    vecDot (vecHadamard g (tangentProjScaled (vecHadamard g w) u)) w = 0 := by
  rw [vecDot_hadamard_adjoint, vecDot_comm]
  apply tangent_orth_aux
  rw [vecHadamard_length g w hgw, hgu]

theorem Mcproof.Spec.scalar_projection_retention_illusion :
    vecDot [1, 0] [0, 32] = 0 ∧
    vecDot (vecAdd [1, 0] [0, 32]) [1, 0] = vecNormSq [1, 0] ∧
    vecNormSq (vecSub (vecAdd [1, 0] [0, 32]) [1, 0]) = 1024 * vecNormSq [1, 0] := by
  decide

private theorem sq_nonneg (x : Int) : 0 ≤ x * x :=
  if hx : 0 ≤ x then
    Int.mul_nonneg hx hx
  else
    have hnx : 0 ≤ -x := by omega
    have heq : (-x) * (-x) = x * x := by rw [Int.neg_mul_neg]
    heq ▸ Int.mul_nonneg hnx hnx

private theorem nonneg_of_sq_le_sq {a b : Int} (hb : 0 ≤ b) (h : a * a ≤ b * b) : a ≤ b :=
  if hlt : b < a then
    have hpos1 : 0 < a - b := by omega
    have hpos2 : 0 < a + b := by omega
    have hmul : 0 < (a - b) * (a + b) := Int.mul_pos hpos1 hpos2
    have h_ab : (a - b) * (a + b) = a * a - b * b := by
      rw [Int.sub_mul, Int.mul_add, Int.mul_add, Int.mul_comm b a]
      omega
    by omega
  else by omega

private theorem poly_lower_identity (R2 D2 : Int) :
    (2 * R2 + D2) * (2 * R2 + D2) = 4 * (R2 + D2) * R2 + D2 * D2 := by
  have h1 : (2 * R2 + D2) * (2 * R2 + D2) =
      2 * R2 * (2 * R2) + (2 * R2 * D2 + D2 * (2 * R2)) + D2 * D2 := by
    rw [Int.add_mul, Int.mul_add, Int.mul_add]
    omega
  have h2 : 2 * R2 * (2 * R2) = 4 * (R2 * R2) := by
    have : (2 : Int) * R2 * (2 * R2) = (2 * 2) * (R2 * R2) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    exact this
  have h3 : 2 * R2 * D2 + D2 * (2 * R2) = 4 * (R2 * D2) := by
    have ha : (2 : Int) * R2 * D2 = 2 * (R2 * D2) := by simp [Int.mul_assoc]
    have hb : D2 * ((2 : Int) * R2) = 2 * (R2 * D2) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    omega
  have h4 : 4 * (R2 + D2) * R2 = 4 * (R2 * R2) + 4 * (R2 * D2) := by
    have hc : (4 : Int) * (R2 + D2) * R2 = 4 * ((R2 + D2) * R2) := by simp [Int.mul_assoc]
    rw [hc, Int.add_mul, Int.mul_add]
    have hd : D2 * R2 = R2 * D2 := Int.mul_comm D2 R2
    rw [hd]
  omega

private theorem poly_upper_identity (R2 D2 : Int) :
    (R2 + D2) * ((2 * R2 - D2) * (2 * R2 - D2)) + D2 * D2 * (3 * R2 - D2) =
    4 * R2 * (R2 * R2) := by
  have hsq : (2 * R2 - D2) * (2 * R2 - D2) = 4 * (R2 * R2) - 4 * (R2 * D2) + D2 * D2 := by
    rw [Int.sub_mul, Int.mul_sub, Int.mul_sub]
    have h22 : (2 : Int) * R2 * (2 * R2) = 4 * (R2 * R2) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    have h2d : (2 : Int) * R2 * D2 = 2 * (R2 * D2) := by simp [Int.mul_assoc]
    have hd2 : D2 * ((2 : Int) * R2) = 2 * (R2 * D2) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    omega
  rw [hsq, Int.add_mul]
  have hr : R2 * (4 * (R2 * R2) - 4 * (R2 * D2) + D2 * D2) =
      4 * R2 * (R2 * R2) - 4 * (R2 * (R2 * D2)) + R2 * (D2 * D2) := by
    rw [Int.mul_add, Int.mul_sub]
    have hr1 : R2 * ((4 : Int) * (R2 * R2)) = 4 * R2 * (R2 * R2) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    have hr2 : R2 * ((4 : Int) * (R2 * D2)) = 4 * (R2 * (R2 * D2)) := by
      simp [Int.mul_assoc, Int.mul_comm]
    rw [hr1, hr2]
  have hd : D2 * (4 * (R2 * R2) - 4 * (R2 * D2) + D2 * D2) =
      4 * (R2 * (R2 * D2)) - 4 * (R2 * (D2 * D2)) + D2 * (D2 * D2) := by
    rw [Int.mul_add, Int.mul_sub]
    have hd1 : D2 * ((4 : Int) * (R2 * R2)) = 4 * (R2 * (R2 * D2)) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    have hd2 : D2 * ((4 : Int) * (R2 * D2)) = 4 * (R2 * (D2 * D2)) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    rw [hd1, hd2]
  have hrem : D2 * D2 * (3 * R2 - D2) = 3 * (R2 * (D2 * D2)) - D2 * (D2 * D2) := by
    rw [Int.mul_sub]
    have hm1 : D2 * D2 * ((3 : Int) * R2) = 3 * (R2 * (D2 * D2)) := by
      simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
    have hm2 : D2 * D2 * D2 = D2 * (D2 * D2) := by simp [Int.mul_assoc]
    rw [hm1, hm2]
  omega

theorem Mcproof.Spec.rmsnorm_rational_shrinkage_sandwich
    (R2 D2 qn qd : Int)
    (hR : 0 < R2) (hD : 0 ≤ D2) (hqn : 0 < qn) (hqd : 0 < qd)
    (heq : (R2 + D2) * (qn * qn) = R2 * (qd * qd)) :
    shrinkageSandwichCheck R2 D2 qn qd = true ∧
    D2 * qd ≤ 2 * (R2 + D2) * (qd - qn) ∧
    2 * R2 * (qd - qn) ≤ D2 * qd := by
  have hpair : D2 * qd ≤ 2 * (R2 + D2) * (qd - qn) ∧ 2 * R2 * (qd - qn) ≤ D2 * qd := by
    constructor
    · have hD2_nn : 0 ≤ (D2 * qd) * (D2 * qd) := sq_nonneg (D2 * qd)
      have h_lhs : (2 * (R2 + D2) * qn) * (2 * (R2 + D2) * qn) =
          4 * (R2 + D2) * ((R2 + D2) * (qn * qn)) := by
        simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
      have h_rhs : ((2 * R2 + D2) * qd) * ((2 * R2 + D2) * qd) =
          ((2 * R2 + D2) * (2 * R2 + D2)) * (qd * qd) := by
        simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
      have h_sq : (2 * (R2 + D2) * qn) * (2 * (R2 + D2) * qn) ≤
          ((2 * R2 + D2) * qd) * ((2 * R2 + D2) * qd) := by
        rw [h_lhs, heq, h_rhs, poly_lower_identity R2 D2, Int.add_mul]
        have ha : 4 * (R2 + D2) * (R2 * (qd * qd)) = 4 * (R2 + D2) * R2 * (qd * qd) := by
          simp [Int.mul_assoc]
        have hb : D2 * D2 * (qd * qd) = (D2 * qd) * (D2 * qd) := by
          simp [Int.mul_comm, Int.mul_left_comm]
        omega
      have hb_nn : 0 ≤ (2 * R2 + D2) * qd := Int.mul_nonneg (by omega) (by omega)
      have h_lin := nonneg_of_sq_le_sq hb_nn h_sq
      have h_exp1 : 2 * (R2 + D2) * (qd - qn) = 2 * (R2 + D2) * qd - 2 * (R2 + D2) * qn :=
        Int.mul_sub (2 * (R2 + D2)) qd qn
      have h_exp2 : 2 * (R2 + D2) * qd = (2 * R2 + D2) * qd + D2 * qd := by
        have : (2 : Int) * (R2 + D2) = (2 * R2 + D2) + D2 := by omega
        rw [this, Int.add_mul]
      omega
    · exact if hbig : 2 * R2 ≤ D2 then
        have hpos : 0 < 2 * R2 * qn := Int.mul_pos (by omega) hqn
        have h1 : 2 * R2 * (qd - qn) ≤ 2 * R2 * qd := by
          rw [Int.mul_sub]
          omega
        have h2 : 2 * R2 * qd ≤ D2 * qd := Int.mul_le_mul_of_nonneg_right hbig (by omega)
        by omega
      else
        have h3R : 0 ≤ 3 * R2 - D2 := by omega
        have h_rem_nn : 0 ≤ D2 * D2 * (3 * R2 - D2) := Int.mul_nonneg (sq_nonneg D2) h3R
        have h_poly_le : (R2 + D2) * ((2 * R2 - D2) * (2 * R2 - D2)) ≤ 4 * R2 * (R2 * R2) := by
          have hp := poly_upper_identity R2 D2
          omega
        have h_mul_qd := Int.mul_le_mul_of_nonneg_right h_poly_le (sq_nonneg qd)
        have h_rhs_sub : 4 * R2 * (R2 * R2) * (qd * qd) =
            (R2 + D2) * ((2 * R2 * qn) * (2 * R2 * qn)) := by
          have s1 : 4 * R2 * (R2 * R2) * (qd * qd) = (4 * (R2 * R2)) * (R2 * (qd * qd)) := by
            simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
          rw [s1, ← heq]
          simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
        have h_lhs_sub : (R2 + D2) * ((2 * R2 - D2) * (2 * R2 - D2)) * (qd * qd) =
            (R2 + D2) * (((2 * R2 - D2) * qd) * ((2 * R2 - D2) * qd)) := by
          simp [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]
        have hRD_pos : 0 < R2 + D2 := by omega
        have h_sq2 : ((2 * R2 - D2) * qd) * ((2 * R2 - D2) * qd) ≤
            (2 * R2 * qn) * (2 * R2 * qn) :=
          if hgt : (2 * R2 * qn) * (2 * R2 * qn) < ((2 * R2 - D2) * qd) * ((2 * R2 - D2) * qd) then
            have h_strict := Int.mul_lt_mul_of_pos_left hgt hRD_pos
            by rw [h_lhs_sub, h_rhs_sub] at h_mul_qd; omega
          else by omega
        have hb2_nn : 0 ≤ 2 * R2 * qn := Int.mul_nonneg (by omega) (by omega)
        have h_lin2 := nonneg_of_sq_le_sq hb2_nn h_sq2
        have h_rew : (2 * R2 - D2) * qd = 2 * R2 * qd - D2 * qd := Int.sub_mul (2 * R2) D2 qd
        have h_rew2 : 2 * R2 * (qd - qn) = 2 * R2 * qd - 2 * R2 * qn := Int.mul_sub (2 * R2) qd qn
        by omega
  exact ⟨by unfold shrinkageSandwichCheck; exact decide_eq_true hpair, hpair⟩
