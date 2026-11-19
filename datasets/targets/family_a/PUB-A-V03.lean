namespace PubAV03

theorem diff_sq_factor (a b : Int) : a * a - b * b = (a - b) * (a + b) := by
  rw [Int.sub_mul, Int.mul_add, Int.mul_add, Int.mul_comm b a]
  omega

theorem diff_sq_composite (a b : Int) (hb : b ≥ 0) (hgap : a > b + 1) :
    ∃ u v : Int, u > 1 ∧ v > 1 ∧ a * a - b * b = u * v := by
  refine ⟨a - b, a + b, by omega, by omega, diff_sq_factor a b⟩

end PubAV03
