namespace PubAV01

def sumOdd : Nat → Nat
  | 0 => 0
  | n + 1 => sumOdd n + (2 * n + 1)

theorem sumOdd_eq_sq (n : Nat) : sumOdd n = n * n := by
  induction n with
  | zero => rfl
  | succ m ih =>
    simp only [sumOdd, ih]
    rw [Nat.add_mul, Nat.mul_add, Nat.one_mul, Nat.mul_one]
    omega

end PubAV01
