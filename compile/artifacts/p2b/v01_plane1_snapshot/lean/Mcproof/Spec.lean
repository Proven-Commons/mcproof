/-
  Challenge specification for the mcproof Lean 4 reference package.
  Each safety theorem is paired with a usefulness theorem so a trivial
  constant or rejecting implementation fails `lake comparator --paranoid`.
-/

import Mcproof

open Mcproof

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
