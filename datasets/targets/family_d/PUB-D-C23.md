# IdemDedup

`IdemDedup` verifies idempotency watermark progression in exactly-once RPC handlers. It proves consecutive steps never shrink the watermark and skip already-processed IDs, for RPC state auditors.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC23.dedup_monotonic_watermark
Claim: Updating `wm' = if reqId == wm + 1 then wm + 1 else wm` satisfies `wm <= wm' <= wm + 1`.
Verdict-Commit: 3d7ac19b63e0809c7c48cc95d9d31c30902e4356
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC23

def stepWatermark (wm reqId : Nat) : Nat := if reqId == wm + 1 then wm + 1 else wm

theorem dedup_monotonic_watermark (wm reqId : Nat) :
    wm ≤ stepWatermark wm reqId ∧ stepWatermark wm reqId ≤ wm + 1 := by
  unfold stepWatermark
  split <;> omega

end PubDC23
```

## What is not proved

Out-of-order request buffering above `wm + 1` is intentionally dropped in this sequential model. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
