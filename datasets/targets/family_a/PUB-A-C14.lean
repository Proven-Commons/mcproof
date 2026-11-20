namespace PubAC14

def WeakSubset (lo1 hi1 lo2 hi2 : Int) : Prop :=
  ∀ x : Int, lo1 ≤ x ∧ x ≤ hi1 → lo2 ≤ x ∧ x ≤ hi2

def checkNonEmptySubset (lo1 hi1 lo2 hi2 : Int) : Bool :=
  (lo1 ≤ hi1) && (lo2 ≤ lo1) && (hi1 ≤ hi2)

theorem inverted_interval_vacuous : WeakSubset 10 2 0 1 := by
  intro x hx
  omega

theorem nonEmptySubset_sound (lo1 hi1 lo2 hi2 : Int)
    (h : checkNonEmptySubset lo1 hi1 lo2 hi2 = true) :
    (∃ x : Int, lo1 ≤ x ∧ x ≤ hi1) ∧ WeakSubset lo1 hi1 lo2 hi2 := by
  unfold checkNonEmptySubset at h
  simp only [Bool.and_eq_true, decide_eq_true_eq] at h
  refine ⟨⟨lo1, by omega, h.1.1⟩, ?_⟩
  intro x hx
  omega

end PubAC14
