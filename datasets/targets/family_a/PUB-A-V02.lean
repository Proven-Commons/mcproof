namespace PubAV02

def FlawedCRT (x r1 m1 r2 m2 : Nat) : Prop :=
  (x + m1 - r1 % m1) % m1 = (x + m2 - r2 % m2) % m2

def checkCRTPair (x r1 m1 r2 m2 : Nat) : Bool :=
  (m1 > 0) && (m2 > 0) && (x % m1 == r1 % m1) && (x % m2 == r2 % m2)

theorem flawedCRT_false_accepts : FlawedCRT 2 1 3 1 5 ∧ ¬(2 % 3 = 1 ∧ 2 % 5 = 1) := by
  unfold FlawedCRT
  decide

theorem crtPair_sound (x r1 m1 r2 m2 : Nat) (h : checkCRTPair x r1 m1 r2 m2 = true) :
    m1 > 0 ∧ m2 > 0 ∧ x % m1 = r1 % m1 ∧ x % m2 = r2 % m2 := by
  unfold checkCRTPair at h
  simp only [Bool.and_eq_true, decide_eq_true_eq, beq_iff_eq] at h
  exact ⟨h.1.1.1, h.1.1.2, h.1.2, h.2⟩

end PubAV02
