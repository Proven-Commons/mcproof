namespace PubAC13

structure Mat2 where
  a : Int
  b : Int
  c : Int
  d : Int

def det2 (M : Mat2) : Int := M.a * M.d - M.b * M.c

def mul2 (X Y : Mat2) : Mat2 :=
  ⟨X.a * Y.a + X.b * Y.c, X.a * Y.b + X.b * Y.d, X.c * Y.a + X.d * Y.c, X.c * Y.b + X.d * Y.d⟩

theorem det2_id : det2 ⟨1, 0, 0, 1⟩ = 1 := by
  decide

theorem det2_mul (u v p q : Int) :
    det2 (mul2 ⟨u, 0, 0, v⟩ ⟨p, 0, 0, q⟩) = det2 ⟨u, 0, 0, v⟩ * det2 ⟨p, 0, 0, q⟩ := by
  simp only [mul2, det2, Int.zero_mul, Int.mul_zero, Int.add_zero, Int.zero_add, Int.sub_zero]
  rw [Int.mul_assoc u v (p * q), ← Int.mul_assoc v p q, Int.mul_comm v p, Int.mul_assoc p v q, ← Int.mul_assoc u p (v * q)]

end PubAC13
