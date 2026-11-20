namespace PubAV11

structure RWLock where
  readers : Nat
  writers : Nat

def WeakRWSafe (s : RWLock) : Prop := s.writers ≤ 1

def RWSafe (s : RWLock) : Prop := s.writers = 0 ∨ (s.writers = 1 ∧ s.readers = 0)

inductive RWOp
  | acqR
  | relR
  | acqW
  | relW

def stepRW (s : RWLock) : RWOp → RWLock
  | .acqR => if s.writers == 0 then ⟨s.readers + 1, 0⟩ else s
  | .relR => if s.readers > 0 then ⟨s.readers - 1, s.writers⟩ else s
  | .acqW => if s.writers == 0 && s.readers == 0 then ⟨0, 1⟩ else s
  | .relW => if s.writers == 1 then ⟨s.readers, 0⟩ else s

theorem dataRace_meets_weak : WeakRWSafe ⟨3, 1⟩ := by
  simp only [WeakRWSafe]
  omega

theorem rwLock_step_safe (s : RWLock) (op : RWOp) (h : RWSafe s) :
    RWSafe (stepRW s op) := by
  cases op with
  | acqR =>
    simp only [stepRW]
    split
    · left; rfl
    · exact h
  | relR =>
    simp only [stepRW]
    split
    · simp only [RWSafe] at *; omega
    · exact h
  | acqW =>
    simp only [stepRW]
    split
    · right; exact ⟨rfl, rfl⟩
    · exact h
  | relW =>
    simp only [stepRW]
    split
    · left; rfl
    · exact h

end PubAV11
