/-
  Complete proofs of all theorems in `Mcproof/Spec.lean`.
  Zero `sorry`, zero custom axioms, and zero compiler escape hatches.
-/

import Mcproof

open Mcproof

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
