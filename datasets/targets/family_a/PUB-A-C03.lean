namespace PubAC03

def dvdInt (a b : Int) : Prop := ∃ k : Int, b = a * k

theorem dvdInt_refl (a : Int) : dvdInt a a := by
  refine ⟨1, ?_⟩
  omega

theorem dvdInt_trans (a b c : Int) (hab : dvdInt a b) (hbc : dvdInt b c) : dvdInt a c := by
  cases hab with
  | intro u hu =>
    cases hbc with
    | intro v hv =>
      refine ⟨u * v, ?_⟩
      rw [hv, hu, Int.mul_assoc]

end PubAC03
