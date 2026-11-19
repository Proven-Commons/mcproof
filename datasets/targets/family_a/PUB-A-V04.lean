namespace PubAV04

def triEdges : Nat → Nat
  | 0 => 0
  | n + 1 => triEdges n + n

theorem completeGraph_edges_twice (n : Nat) : 2 * triEdges n + n = n * n := by
  induction n with
  | zero => rfl
  | succ m ih =>
    simp only [triEdges, Nat.mul_add]
    rw [Nat.add_mul m 1 m, Nat.one_mul, Nat.mul_one]
    omega

end PubAV04
