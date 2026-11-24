# FarkasConeScale

`FarkasConeScale` proves positive scaling invariance of Farkas dual infeasibility RHS `y^T b < 0`. Multiplying negative `dot_yb < 0` by positive `k > 0` stays strictly negative, for rational certificate normalizers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV09.dual_witness_pos_scale
Claim: For integers `k > 0` and `s < 0`, `k * s < 0` holds without rounding loss.
Verdict-Commit: a75d59a99f43e5999227e5241b7b3031e0c3a0d0
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV09

theorem dual_witness_pos_scale (k s : Int) (hk : 0 < k) (hs : s < 0) : k * s < 0 := by
  have hpos : 0 < k * (-s) := Int.mul_pos hk (by omega)
  rw [Int.mul_neg] at hpos
  omega

end PubDV09
```

## What is not proved

Clearing denominators across an `m`-element rational vector requires positive common multiple `L > 0`. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
