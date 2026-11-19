namespace PubAC04

def dvdNat (d n : Nat) : Prop := ∃ k : Nat, n = d * k

theorem dvdNat_linComb (d a b u v : Nat) (ha : dvdNat d a) (hb : dvdNat d b) :
    dvdNat d (a * u + b * v) := by
  cases ha with
  | intro ka hka =>
    cases hb with
    | intro kb hkb =>
      refine ⟨ka * u + kb * v, ?_⟩
      rw [hka, hkb, Nat.mul_assoc, Nat.mul_assoc, ← Nat.mul_add]

end PubAC04
