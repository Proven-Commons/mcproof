namespace PubAC21

structure FifoCounters where
  cap : Nat
  used : Nat
  enq : Nat
  deq : Nat

def fifoInv (s : FifoCounters) : Prop := s.used ≤ s.cap ∧ s.enq = s.deq + s.used

inductive FifoOp
  | push
  | pop

def stepFifo (s : FifoCounters) : FifoOp → FifoCounters
  | .push => if s.used < s.cap then ⟨s.cap, s.used + 1, s.enq + 1, s.deq⟩ else s
  | .pop => if s.used > 0 then ⟨s.cap, s.used - 1, s.enq, s.deq + 1⟩ else s

def runFifo : FifoCounters → List FifoOp → FifoCounters
  | s, [] => s
  | s, op :: ops => runFifo (stepFifo s op) ops

theorem stepFifo_preserves (s : FifoCounters) (op : FifoOp) (h : fifoInv s) :
    fifoInv (stepFifo s op) := by
  cases op with
  | push =>
    simp only [stepFifo]
    split
    · simp only [fifoInv] at *; omega
    · exact h
  | pop =>
    simp only [stepFifo]
    split
    · simp only [fifoInv] at *; omega
    · exact h

theorem fifo_trace_conserves (s : FifoCounters) (ops : List FifoOp) (h : fifoInv s) :
    fifoInv (runFifo s ops) := by
  induction ops generalizing s with
  | nil => exact h
  | cons op rest ih =>
    exact ih (stepFifo s op) (stepFifo_preserves s op h)

end PubAC21
