namespace PubAV06

def sublists : List Nat → List (List Nat)
  | [] => [[]]
  | x :: xs => let ps := sublists xs; ps ++ ps.map (x :: ·)

theorem sublists_length_pow2 (xs : List Nat) : (sublists xs).length = 2 ^ xs.length := by
  induction xs with
  | nil => rfl
  | cons x rest ih =>
    simp only [sublists, List.length_append, List.length_map, List.length_cons, ih, Nat.pow_succ]
    omega

end PubAV06
