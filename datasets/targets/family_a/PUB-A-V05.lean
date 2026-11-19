namespace PubAV05

def isStrictInc3 : List Nat → Bool
  | [a, b, c] => (a < b) && (b < c)
  | _ => false

theorem vacuous_empty_nonempty : ¬ (∃ xs : List Nat, xs = [] ∧ xs.length > 0) := by
  intro hex
  cases hex with
  | intro xs hxs =>
    have h1 := hxs.1
    have h2 := hxs.2
    subst h1
    simp at h2

theorem strictPair_nonvacuous (xs : List Nat) (h : isStrictInc3 xs = true) :
    ∃ a b c, xs = [a, b, c] ∧ a < c := by
  match xs with
  | [a, b, c] =>
    unfold isStrictInc3 at h
    simp only [Bool.and_eq_true, decide_eq_true_eq] at h
    exact ⟨a, b, c, rfl, by omega⟩
  | [] => cases h
  | [_] => cases h
  | [_, _] => cases h
  | _ :: _ :: _ :: _ :: _ => cases h

theorem strictInc3_witness : isStrictInc3 [2, 5, 9] = true := by
  decide

end PubAV05
