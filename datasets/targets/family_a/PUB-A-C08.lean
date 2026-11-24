namespace PubAC08

def WeakCollision (xs : List Nat) (ok : Bool) : Prop := ok = true → xs.length ≥ 0

def alwaysCollision (_xs : List Nat) : Bool := true

def validCollision (xs : List Nat) (i j : Nat) : Bool :=
  (i < j) && (j < xs.length) && (xs[i]? == xs[j]?)

theorem alwaysCollision_meets_weak (xs : List Nat) : WeakCollision xs (alwaysCollision xs) := by
  intro _
  omega

theorem validCollision_sound (xs : List Nat) (i j : Nat) (h : validCollision xs i j = true) :
    i < j ∧ j < xs.length ∧ xs[i]? = xs[j]? := by
  unfold validCollision at h
  simp only [Bool.and_eq_true, decide_eq_true_eq, beq_iff_eq] at h
  exact ⟨h.1.1, h.1.2, h.2⟩

theorem validCollision_witness : validCollision [4, 7, 4] 0 2 = true := by
  decide

end PubAC08
