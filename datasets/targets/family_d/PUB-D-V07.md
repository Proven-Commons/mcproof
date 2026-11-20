# IvMidpoint

`IvMidpoint` checks division-free midpoint containment `2 * lo <= lo + hi <= 2 * hi` for closed intervals. It supports exact rational bisection routines.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV07.twice_midpoint_in_scaled_iv
Claim: Whenever `lo <= hi` over `Int`, the doubled midpoint `lo + hi` satisfies `2 * lo <= lo + hi ∧ lo + hi <= 2 * hi`.
Verdict-Commit: d905d6358ffa9d996b0d6c5b1c149a8bd625fa1a
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV07

theorem twice_midpoint_in_scaled_iv (lo hi : Int) (h : lo ≤ hi) :
    2 * lo ≤ lo + hi ∧ lo + hi ≤ 2 * hi := by
  omega

end PubDV07
```

## What is not proved

Termination depth of adaptive interval bisection depends on caller tolerance parameters. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
