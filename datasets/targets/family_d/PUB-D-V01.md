# MulEvenLeft

`MulEvenLeft` verifies that multiplying an even integer by any integer yields an even integer. It provides a certified parity lemma for algebraic simplifiers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV01.even_mul_any
Claim: If `a = 2 * k` over `Int`, then for every integer `b`, `a * b = 2 * (k * b)` is even.
Verdict-Commit: 69b17b1e8a211d70567ba27bd46ed83ddf1065a7
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV01

def isEven (z : Int) : Prop := ∃ k : Int, z = 2 * k

theorem even_mul_any (a b : Int) (ha : isEven a) : isEven (a * b) := by
  cases ha with
  | intro k hk =>
    refine ⟨k * b, ?_⟩
    rw [hk, Int.mul_assoc]

end PubDV01
```

## What is not proved

Division or halving of odd integers is not defined or claimed in this module. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
