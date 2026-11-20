namespace PubAC15

theorem interval_add_enclosure (a1 b1 a2 b2 x y : Int)
    (hx : a1 ≤ x ∧ x ≤ b1) (hy : a2 ≤ y ∧ y ≤ b2) :
    (a1 + a2 ≤ x + y ∧ x + y ≤ b1 + b2) ∧ ((b1 + b2) - (a1 + a2) = (b1 - a1) + (b2 - a2)) := by
  omega

end PubAC15
