namespace PubAV07

def imax (a b : Int) : Int := if a ≥ b then a else b

def imin (a b : Int) : Int := if a ≤ b then a else b

theorem interval_inter_nonempty (a1 b1 a2 b2 : Int) :
    (imax a1 a2 ≤ imin b1 b2) ↔ (∃ x : Int, (a1 ≤ x ∧ x ≤ b1) ∧ (a2 ≤ x ∧ x ≤ b2)) := by
  constructor
  · intro h
    refine ⟨imax a1 a2, ?_⟩
    unfold imax imin at *
    split at * <;> split at * <;> omega
  · intro hex
    cases hex with
    | intro x hx =>
      unfold imax imin
      split <;> split <;> omega

end PubAV07
