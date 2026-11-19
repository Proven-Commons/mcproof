# MonotonicBallot

`MonotonicBallot` proves that an acceptor updating `promisedBallot := max promisedBallot reqBallot` never lowers its ballot promise. It supports consensus safety audits.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC20.ballot_never_decreases
Claim: For every current `promised : Nat` and incoming `req : Nat`, `Nat.max promised req >= promised` and `>= req`.
Verdict-Commit: 5fdf29da757768d50ae9b0f252778bfc3461c06c
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC20

def promiseStep (promised req : Nat) : Nat := Nat.max promised req

theorem ballot_never_decreases (promised req : Nat) :
    promiseStep promised req ≥ promised ∧ promiseStep promised req ≥ req := by
  unfold promiseStep
  simp only [Nat.max_def]
  split <;> omega

end PubDC20
```

## What is not proved

Network message duplication and disk fsync durability are outside this pure state step. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
