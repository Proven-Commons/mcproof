# EpochFence

`EpochFence` checks storage fencing-token rejection of stale leader writes. It proves writes accepted by `checkFence` always carry `writeToken >= minToken`, for distributed storage verifiers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC21.fence_write_sound
Claim: Whenever `checkFence minToken writeToken = true`, `writeToken >= minToken` holds.
Verdict-Commit: 060ab6a523594607c1a5e63774f0d037e3efb8bf
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC21

def checkFence (minToken writeToken : Nat) : Bool := writeToken ≥ minToken

theorem fence_write_sound (minToken writeToken : Nat)
    (h : checkFence minToken writeToken = true) : writeToken ≥ minToken := by
  unfold checkFence at h
  simp only [decide_eq_true_eq] at h
  exact h

end PubDC21
```

## What is not proved

Clock drift on physical wall-clock lease timers is unmodeled and irrelevant to integer token safety. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
