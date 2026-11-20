namespace PubAC16

theorem cramer2_offdiag_zero (a b c d : Int) :
    a * (-b) + b * a = 0 ∧ c * d + d * (-c) = 0 := by
  constructor
  · rw [Int.mul_neg, Int.mul_comm b a]
    omega
  · rw [Int.mul_neg, Int.mul_comm d c]
    omega

theorem cramer2_diag_eq (a b c d : Int) :
    a * d + b * (-c) = d * a + (-b) * c := by
  rw [Int.mul_comm a d, Int.mul_neg, Int.neg_mul]

end PubAC16
