namespace PubAC11

def WeakEdgeColor (cu cv : Nat) : Prop := cu ≤ 1 ∧ cv ≤ 1

def checkEdge2Color (cu cv : Nat) : Bool :=
  ((cu == 0) || (cu == 1)) && ((cv == 0) || (cv == 1)) && (cu != cv)

theorem monoZero_meets_weak : WeakEdgeColor 0 0 := by
  exact ⟨by omega, by omega⟩

theorem properTwoColor_edge (cu cv : Nat) (h : checkEdge2Color cu cv = true) :
    (cu = 0 ∨ cu = 1) ∧ (cv = 0 ∨ cv = 1) ∧ cu ≠ cv := by
  unfold checkEdge2Color at h
  simp only [Bool.and_eq_true, Bool.or_eq_true, beq_iff_eq, bne_iff_ne] at h
  exact ⟨h.1.1, h.1.2, h.2⟩

theorem monoZero_rejected : checkEdge2Color 0 0 = false := by
  decide

end PubAC11
