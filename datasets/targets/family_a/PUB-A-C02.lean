namespace PubAC02

def WeakModInv (m a x : Nat) : Prop := m > 1 → (a * x) % m ≤ m

def zeroInv (_m _a : Nat) : Nat := 0

def checkModInv (m a x : Nat) : Bool := (m > 1) && ((a * x) % m == 1)

theorem zeroInv_meets_weak (m a : Nat) : WeakModInv m a (zeroInv m a) := by
  intro hm
  unfold zeroInv
  have hlt : (a * 0) % m < m := Nat.mod_lt (a * 0) (by omega)
  omega

theorem checkModInv_sound (m a x : Nat) (h : checkModInv m a x = true) :
    m > 1 ∧ (a * x) % m = 1 := by
  unfold checkModInv at h
  simp only [Bool.and_eq_true, decide_eq_true_eq, beq_iff_eq] at h
  exact h

theorem checkModInv_witness : checkModInv 7 3 5 = true := by
  decide

end PubAC02
