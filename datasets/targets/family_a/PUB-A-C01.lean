namespace PubAC01

theorem even_mul_succ (n : Nat) : ∃ k : Nat, n * (n + 1) = 2 * k := by
  induction n with
  | zero =>
    exact ⟨0, rfl⟩
  | succ m ih =>
    cases ih with
    | intro k hk =>
      refine ⟨k + m + 1, ?_⟩
      have hstep : (m + 1) * (m + 1 + 1) = m * (m + 1) + 2 * (m + 1) := by
        rw [Nat.mul_add (m + 1) (m + 1) 1, Nat.add_mul m 1 (m + 1)]
        omega
      omega

end PubAC01
