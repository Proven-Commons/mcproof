namespace PubAV12

def acceptPacket (highWater pktSeq : Nat) : Bool × Nat :=
  if pktSeq > highWater then (true, pktSeq) else (false, highWater)

theorem antiReplay_monotonic (hw pkt : Nat) :
    (acceptPacket hw pkt).2 ≥ hw ∧ ((acceptPacket hw pkt).1 = true → pkt > hw ∧ (acceptPacket hw pkt).2 = pkt) := by
  unfold acceptPacket
  split
  · refine ⟨by omega, ?_⟩
    intro _
    exact ⟨‹pkt > hw›, rfl⟩
  · refine ⟨by omega, ?_⟩
    intro hf
    cases hf

theorem antiReplay_blocks_dup (hw pkt : Nat) (hdup : pkt ≤ hw) :
    (acceptPacket hw pkt).1 = false := by
  unfold acceptPacket
  split
  · omega
  · rfl

end PubAV12
