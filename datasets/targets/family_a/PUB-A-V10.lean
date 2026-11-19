namespace PubAV10

structure ChanState where
  sent : Nat
  inFlight : Nat
  delivered : Nat

def chanInv (s : ChanState) : Prop := s.sent = s.inFlight + s.delivered

inductive ChanEv
  | send
  | ack

def stepChan (s : ChanState) : ChanEv → ChanState
  | .send => ⟨s.sent + 1, s.inFlight + 1, s.delivered⟩
  | .ack => if s.inFlight > 0 then ⟨s.sent, s.inFlight - 1, s.delivered + 1⟩ else s

theorem stepChan_inv (s : ChanState) (ev : ChanEv) (h : chanInv s) :
    chanInv (stepChan s ev) := by
  cases ev with
  | send => simp only [stepChan, chanInv] at *; omega
  | ack => simp only [stepChan]; split <;> (simp only [chanInv] at *; omega)

theorem foldChan_inv (s : ChanState) (evs : List ChanEv) (h : chanInv s) :
    chanInv (evs.foldl stepChan s) := by
  induction evs generalizing s with
  | nil => exact h
  | cons ev rest ih => exact ih (stepChan s ev) (stepChan_inv s ev h)

theorem channel_trace_inv (s : ChanState) (evs : List ChanEv) (h : chanInv s) :
    let s' := evs.foldl stepChan s; chanInv s' ∧ s'.delivered ≤ s'.sent := by
  have hi : chanInv (evs.foldl stepChan s) := foldChan_inv s evs h
  unfold chanInv at hi
  exact ⟨hi, by omega⟩

end PubAV10
