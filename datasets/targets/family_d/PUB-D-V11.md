# QuorumMaj

`QuorumMaj` proves the arithmetic core of majority quorum intersection: two sets of size `> n / 2` satisfy `q1 + q2 > n`, so they cannot fit disjointly inside `n` nodes. It supports consensus safety docs.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV11.strict_maj_sum_gt
Claim: Whenever `2 * q1 > n` and `2 * q2 > n` on `Nat`, `q1 + q2 > n`.
Verdict-Commit: 72a4f7516ab09f4a63d810bfaeb3d282afe21956
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV11

theorem strict_maj_sum_gt (n q1 q2 : Nat) (h1 : 2 * q1 > n) (h2 : 2 * q2 > n) : q1 + q2 > n := by
  omega

end PubDV11
```

## What is not proved

Byzantine equivocation (where faulty nodes vote differently in `q1` and `q2`) requires the stronger `3f + 1` bound. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
