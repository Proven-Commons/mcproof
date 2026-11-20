namespace PubAC24

structure LeaseState where
  epoch : Nat
  leader : Nat

def grantLease (s : LeaseState) (reqEpoch candidate : Nat) : Option LeaseState :=
  if reqEpoch > s.epoch then some ⟨reqEpoch, candidate⟩ else none

theorem lease_epoch_monotonic (s s' : LeaseState) (reqEpoch candidate : Nat)
    (h : grantLease s reqEpoch candidate = some s') :
    s'.epoch > s.epoch ∧ s'.leader = candidate := by
  unfold grantLease at h
  split at h
  · injection h with hs
    subst hs
    exact ⟨‹reqEpoch > s.epoch›, rfl⟩
  · cases h

theorem lease_reject_stale (s : LeaseState) (reqEpoch candidate : Nat)
    (hle : reqEpoch ≤ s.epoch) : grantLease s reqEpoch candidate = none := by
  unfold grantLease
  split
  · omega
  · rfl

end PubAC24
