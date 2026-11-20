namespace PubAC23

structure Coord2PC where
  committed : Bool
  aborted : Bool

def TautologicalSafe (s : Coord2PC) : Prop :=
  (s.committed = true ∧ s.aborted = false) → ¬(s.committed = true ∧ s.aborted = true)

def RealSafe (s : Coord2PC) : Prop :=
  ¬(s.committed = true ∧ s.aborted = true)

def decide2PC (s : Coord2PC) (allYes : Bool) : Coord2PC :=
  if s.committed || s.aborted then s else if allYes then ⟨true, false⟩ else ⟨false, true⟩

theorem splitBrain_meets_tautology : TautologicalSafe ⟨true, true⟩ := by
  unfold TautologicalSafe
  intro h
  cases h.2

theorem twoPC_safe_step (s : Coord2PC) (allYes : Bool) (h : RealSafe s) :
    RealSafe (decide2PC s allYes) := by
  unfold decide2PC RealSafe at *
  cases hs1 : s.committed <;> cases hs2 : s.aborted <;> cases allYes <;> simp_all

end PubAC23
