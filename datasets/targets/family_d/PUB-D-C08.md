# BinomOne

`BinomOne` proves the linear singleton-subset count `choose1 n = n` by induction. It serves developers auditing base cases of finite subset enumerators.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC08.choose_one_right
Claim: Counting 1-element selections via `choose1 0 = 0` and `choose1 (n + 1) = 1 + choose1 n` equals `n` for all `n`.
Verdict-Commit: d8b67bc35b36f8ee5590d7ad7afd6d74b660560a
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC08

def choose1 : Nat → Nat
  | 0 => 0
  | n + 1 => 1 + choose1 n

theorem choose_one_right (n : Nat) : choose1 n = n := by
  induction n with
  | zero => rfl
  | succ m ih =>
    simp only [choose1, ih]
    omega

end PubDC08
```

## What is not proved

Higher `k`-subset binomial recurrences are proved in separate modules. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
