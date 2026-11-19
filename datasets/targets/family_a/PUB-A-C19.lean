namespace PubAC19

structure TicketLock where
  serving : Nat
  nextTicket : Nat

def inv (s : TicketLock) : Prop := s.serving ≤ s.nextTicket

def issueTicket (s : TicketLock) : TicketLock := ⟨s.serving, s.nextTicket + 1⟩

def releaseLock (s : TicketLock) : TicketLock :=
  if s.serving < s.nextTicket then ⟨s.serving + 1, s.nextTicket⟩ else s

def holdsLock (s : TicketLock) (t : Nat) : Prop := t = s.serving ∧ t < s.nextTicket

theorem issue_preserves_inv (s : TicketLock) (h : inv s) : inv (issueTicket s) := by
  simp only [inv, issueTicket] at *
  omega

theorem release_preserves_inv (s : TicketLock) (h : inv s) : inv (releaseLock s) := by
  unfold releaseLock
  split
  · simp only [inv] at *; omega
  · exact h

theorem ticket_mutex (s : TicketLock) (t1 t2 : Nat)
    (h1 : holdsLock s t1) (h2 : holdsLock s t2) : t1 = t2 := by
  unfold holdsLock at *
  omega

end PubAC19
