namespace PubAC17

def BrokenFarkas (y1 y2 b1 b2 : Int) : Prop :=
  y1 ≥ 0 ∧ y2 ≥ 0 ∧ y1 * b1 + y2 * b2 < 0

theorem brokenFarkas_false_infeasible :
    BrokenFarkas 0 1 1 (-1) ∧ (∃ x : Int, 1 * x = 1 ∧ (-1) * x = (-1)) := by
  refine ⟨⟨by omega, by omega, by omega⟩, ⟨1, by omega, by omega⟩⟩

theorem farkas1d_infeasible (a1 a2 b1 b2 y1 y2 : Int)
    (hdual : y1 * a1 + y2 * a2 = 0)
    (hb : y1 * b1 + y2 * b2 < 0) : ¬ (∃ x : Int, a1 * x = b1 ∧ a2 * x = b2) := by
  intro hex
  cases hex with
  | intro x hx =>
    have hx1 := hx.1
    have hx2 := hx.2
    have hsum : y1 * b1 + y2 * b2 = (y1 * a1 + y2 * a2) * x := by
      rw [← hx1, ← hx2, Int.add_mul, Int.mul_assoc, Int.mul_assoc]
    rw [hdual, Int.zero_mul] at hsum
    omega

end PubAC17
