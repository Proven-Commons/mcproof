# ScaleIvPos

`ScaleIvPos` proves order preservation when scaling an interval `[lo, hi]` by a non-negative integer scalar `k >= 0`. It backs exact rational row-scaling in interval solvers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC18.interval_pos_scale
Claim: When `0 <= k` and `lo <= x <= hi` over `Int`, `k * lo <= k * x` and `k * x <= k * hi`.
Verdict-Commit: 743892ca2ab1f0d3ebd27b75fe726e28f2068229
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC18

theorem interval_pos_scale (k lo hi x : Int) (hk : 0 ≤ k) (hx : lo ≤ x ∧ x ≤ hi) :
    k * lo ≤ k * x ∧ k * x ≤ k * hi := by
  exact ⟨Int.mul_le_mul_of_nonneg_left hx.1 hk, Int.mul_le_mul_of_nonneg_left hx.2 hk⟩

end PubDC18
```

## What is not proved

Endpoint reversal under negative multipliers `k < 0` requires a separate branch. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
