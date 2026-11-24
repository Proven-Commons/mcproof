namespace PubAC06

theorem euclid_div_unique (m q1 r1 q2 r2 : Nat) (hr1 : r1 < m) (hr2 : r2 < m)
    (heq : m * q1 + r1 = m * q2 + r2) : q1 = q2 ∧ r1 = r2 := by
  have hq_not_lt : ¬(q1 < q2) := by
    intro hlt
    have hle : q1 + 1 ≤ q2 := hlt
    have hmul : m * (q1 + 1) ≤ m * q2 := Nat.mul_le_mul_left m hle
    rw [Nat.mul_add, Nat.mul_one] at hmul
    omega
  have hq_not_gt : ¬(q2 < q1) := by
    intro hgt
    have hle : q2 + 1 ≤ q1 := hgt
    have hmul : m * (q2 + 1) ≤ m * q1 := Nat.mul_le_mul_left m hle
    rw [Nat.mul_add, Nat.mul_one] at hmul
    omega
  have hq : q1 = q2 := by omega
  subst hq
  exact ⟨rfl, by omega⟩

end PubAC06
