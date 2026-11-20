# IvSub

`IvSub` proves exact subtraction bounds `[a1 - b2, b1 - a2]` for two closed intervals despite variable dependence warnings. It gives formal enclosure guarantees for interval residual verifiers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC15.interval_sub_enclosure
Claim: For `x in [a1, b1]` and `y in [a2, b2]`, the difference `x - y` lies in `[a1 - b2, b1 - a2]`.
Verdict-Commit: f66c829d25bc0a978e50adfabfe240697cb8879c
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC15

theorem interval_sub_enclosure (a1 b1 a2 b2 x y : Int)
    (hx : a1 ≤ x ∧ x ≤ b1) (hy : a2 ≤ y ∧ y ≤ b2) :
    a1 - b2 ≤ x - y ∧ x - y ≤ b1 - a2 := by
  omega

end PubDC15
```

## What is not proved

Sub-distributivity tightening when `x` and `y` alias the same variable is not modeled here. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
