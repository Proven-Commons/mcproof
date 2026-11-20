# EvenSum

`EvenSum` checks additive closure of even integers inside deterministic number-theory pipelines. It proves the sum of two even integers is even, for reviewers checking parity guards.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC02.even_add_even
Claim: If `a = 2 * u` and `b = 2 * v` over `Int`, their sum `a + b` admits an explicit factor of `2`.
Verdict-Commit: f505214726b8f424c6a835fb193dc91847d3be4c
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC02

def isEvenInt (z : Int) : Prop := ∃ k : Int, z = 2 * k

theorem even_add_even (a b : Int) (ha : isEvenInt a) (hb : isEvenInt b) : isEvenInt (a + b) := by
  cases ha with
  | intro u hu =>
    cases hb with
    | intro v hv =>
      exact ⟨u + v, by omega⟩

end PubDC02
```

## What is not proved

Parity of external JSON inputs before deserialization is outside the Lean theorem. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
