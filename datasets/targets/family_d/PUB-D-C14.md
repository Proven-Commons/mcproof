# IvNeg

`IvNeg` verifies endpoint reflection when negating a closed integer interval `[lo, hi]`. It proves `x in [lo, hi]` implies `-x in [-hi, -lo]` with identical interval width, for interval-arithmetic solvers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC14.interval_neg_enclosure
Claim: Negating `x` inside `[lo, hi]` lands inside `[-hi, -lo]` and preserves `(-lo) - (-hi) = hi - lo`.
Verdict-Commit: 80cc1cee1d3afd0ca20de6dcb89e7eb377698ed6
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC14

theorem interval_neg_enclosure (lo hi x : Int) (hx : lo ≤ x ∧ x ≤ hi) :
    (-hi ≤ -x ∧ -x ≤ -lo) ∧ ((-lo) - (-hi) = hi - lo) := by
  omega

end PubDC14
```

## What is not proved

Directed IEEE-754 floating-point rounding modes are excluded because endpoints are exact integers. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
