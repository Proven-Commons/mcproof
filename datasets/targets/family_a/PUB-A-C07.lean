namespace PubAC07

def binom : Nat → Nat → Nat
  | _, 0 => 1
  | 0, _ + 1 => 0
  | n + 1, k + 1 => binom n k + binom n (k + 1)

theorem binom_gt_zero (n k : Nat) (h : n < k) : binom n k = 0 := by
  induction n generalizing k with
  | zero =>
    cases k with
    | zero => omega
    | succ k' => rfl
  | succ n' ih =>
    cases k with
    | zero => omega
    | succ k' =>
      simp only [binom]
      have h1 : binom n' k' = 0 := ih k' (by omega)
      have h2 : binom n' (k' + 1) = 0 := ih (k' + 1) (by omega)
      omega

theorem binom_self (n : Nat) : binom n n = 1 := by
  induction n with
  | zero => rfl
  | succ n' ih =>
    simp only [binom]
    have hz : binom n' (n' + 1) = 0 := binom_gt_zero n' (n' + 1) (by omega)
    omega

theorem pascal_step (n k : Nat) : binom (n + 1) (k + 1) = binom n k + binom n (k + 1) := by
  rfl

end PubAC07
