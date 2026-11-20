namespace PubAC05

def WeakBezout (a b g x y : Int) : Prop := a * x + b * y ≥ g

def checkBezout (a b g x y : Int) : Bool :=
  (g > 0) && (a % g == 0) && (b % g == 0) && (a * x + b * y == g)

theorem weakBezout_false_accepts : WeakBezout 6 9 1 1 0 := by
  unfold WeakBezout
  omega

theorem bezoutCert_sound (a b g x y : Int) (h : checkBezout a b g x y = true) :
    g > 0 ∧ a % g = 0 ∧ b % g = 0 ∧ a * x + b * y = g := by
  unfold checkBezout at h
  simp only [Bool.and_eq_true, decide_eq_true_eq, beq_iff_eq] at h
  exact ⟨h.1.1.1, h.1.1.2, h.1.2, h.2⟩

theorem bezoutCert_witness : checkBezout 15 21 3 3 (-2) = true := by
  decide

end PubAC05
