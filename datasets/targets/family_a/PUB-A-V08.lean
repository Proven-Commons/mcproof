namespace PubAV08

def WeakNull2 (a b c d : Int) : Prop :=
  ∀ x y : Int, x = 0 ∧ y = 0 → a * x + b * y = 0 ∧ c * x + d * y = 0

theorem identity_has_weakNull : WeakNull2 1 0 0 1 := by
  intro x y hxy
  omega

theorem kernel_annihilates_det (a b c d x y : Int)
    (h1 : a * x + b * y = 0) (h2 : c * x + d * y = 0) : (a * d - b * c) * x = 0 := by
  have hd1 : d * (a * x + b * y) = 0 := by rw [h1, Int.mul_zero]
  have hb2 : b * (c * x + d * y) = 0 := by rw [h2, Int.mul_zero]
  rw [Int.mul_add, ← Int.mul_assoc d a x, Int.mul_comm d a, ← Int.mul_assoc d b y, Int.mul_comm d b] at hd1
  rw [Int.mul_add, ← Int.mul_assoc b c x, ← Int.mul_assoc b d y] at hb2
  rw [Int.sub_mul]
  omega

end PubAV08
