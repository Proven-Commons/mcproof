namespace PubAC20

def WeakRecvSpec (_localTs _msgTs nextTs : Nat) : Prop := nextTs ≥ 0

def resetClock (_localTs _msgTs : Nat) : Nat := 0

def lamportRecv (localTs msgTs : Nat) : Nat := Nat.max localTs msgTs + 1

theorem resetClock_meets_weak (l m : Nat) : WeakRecvSpec l m (resetClock l m) := by
  unfold WeakRecvSpec resetClock
  omega

theorem lamportRecv_causal (localTs msgTs : Nat) :
    lamportRecv localTs msgTs > localTs ∧ lamportRecv localTs msgTs > msgTs := by
  unfold lamportRecv
  simp only [Nat.max_def]
  split <;> omega

end PubAC20
