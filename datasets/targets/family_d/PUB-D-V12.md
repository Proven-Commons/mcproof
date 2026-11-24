# RetryBackoffCap

`RetryBackoffCap` verifies upper-bound safety of truncated exponential retry timers `min(2 * cur, cap)`. It proves every backed-off delay stays `<= cap` when `cap > 0`, for protocol timer implementations.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV12.capped_backoff_le_max
Claim: For all `cur, cap : Nat`, `Nat.min (2 * cur) cap <= cap`.
Verdict-Commit: 1968927da7cdd0cf01fffe5c4df477606d3e4730
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV12

def nextDelay (cur cap : Nat) : Nat := Nat.min (2 * cur) cap

theorem capped_backoff_le_max (cur cap : Nat) : nextDelay cur cap ≤ cap := by
  unfold nextDelay
  simp only [Nat.min_def]
  split <;> omega

end PubDV12
```

## What is not proved

Jitter randomization used to break thundering-herd synchronization is outside this deterministic cap. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
