# SkewQuadZero

`SkewQuadZero` verifies that every `2x2` skew-symmetric integer matrix `[0, b; -b, 0]` has identically zero quadratic form `x^T K x = 0`. It supports LP primal-dual skew-form checkers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC17.skew2_quad_zero
Claim: For all integers `b, x1, x2`, the bilinear evaluation `x1 * (b * x2) + x2 * ((-b) * x1)` equals `0`.
Verdict-Commit: d92ddc90199df8c1f062f7a3939fb26c915e01c2
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC17

theorem skew2_quad_zero (b x1 x2 : Int) : x1 * (b * x2) + x2 * ((-b) * x1) = 0 := by
  rw [Int.neg_mul, Int.mul_neg, ← Int.mul_assoc x1 b x2, Int.mul_comm x1 b, Int.mul_assoc b x1 x2, Int.mul_comm x2 (b * x1), Int.mul_assoc b x1 x2]
  omega

end PubDC17
```

## What is not proved

Higher-dimensional Pfaffian identities are outside the scope of this `2x2` lemma. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
