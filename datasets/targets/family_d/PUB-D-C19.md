# SemaphoreBound

`SemaphoreBound` verifies conservation of `available + held = maxPermits` in a counting semaphore state machine. It serves systems engineers auditing bounded concurrency primitives.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC19.sem_step_bounds
Claim: Guarded `acquire` (when `available > 0`) and `release` (when `held > 0`) preserve `available + held = cap`.
Verdict-Commit: 4db5d0dc1f428d28b4bd07ef3f6dd131ea0afdf7
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC19

structure Sem where
  cap : Nat
  avail : Nat
  held : Nat

def semInv (s : Sem) : Prop := s.avail + s.held = s.cap
def acqSem (s : Sem) : Sem := if s.avail > 0 then ⟨s.cap, s.avail - 1, s.held + 1⟩ else s
def relSem (s : Sem) : Sem := if s.held > 0 then ⟨s.cap, s.avail + 1, s.held - 1⟩ else s

theorem sem_step_bounds (s : Sem) (h : semInv s) : semInv (acqSem s) ∧ semInv (relSem s) := by
  constructor
  · unfold acqSem; split <;> (simp only [semInv] at *; omega)
  · unfold relSem; split <;> (simp only [semInv] at *; omega)

end PubDC19
```

## What is not proved

Fairness across blocked threads waiting on the semaphore queue is not proved. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
