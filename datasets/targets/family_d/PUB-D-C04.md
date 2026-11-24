# GcdSelf

`GcdSelf` records boundary identities of `Nat.gcd` used by fraction canonicalizers. It proves `gcd n n = n` and `gcd n 0 = n`, for developers maintaining exact rational libraries.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC04.gcd_self_and_zero
Claim: Every natural number `n` satisfies `Nat.gcd n n = n` and `Nat.gcd n 0 = n` in stock Lean 4.
Verdict-Commit: f38e7857d0a9ad705c3fa439d2b357a850d00aa4
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC04

theorem gcd_self_and_zero (n : Nat) : Nat.gcd n n = n ∧ Nat.gcd n 0 = n := by
  exact ⟨Nat.gcd_self n, Nat.gcd_zero_right n⟩

end PubDC04
```

## What is not proved

Runtime step count on multi-thousand-bit integers is tested separately rather than proved. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
