# OddSumEven

`OddSumEven` verifies parity flip when summing two odd integers in modular arithmetic modules. It proves two odd integers always sum to an even integer, for formal audit contributors.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC03.odd_add_odd_even
Claim: Whenever `a = 2 * u + 1` and `b = 2 * v + 1`, the sum `a + b` equals `2 * (u + v + 1)`.
Verdict-Commit: f802dc537947843f4a62d581004bf64b8eddb9ad
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC03

def isOddInt (z : Int) : Prop := ∃ k : Int, z = 2 * k + 1
def isEvenInt (z : Int) : Prop := ∃ k : Int, z = 2 * k

theorem odd_add_odd_even (a b : Int) (ha : isOddInt a) (hb : isOddInt b) : isEvenInt (a + b) := by
  cases ha with
  | intro u hu =>
    cases hb with
    | intro v hv =>
      exact ⟨u + v + 1, by omega⟩

end PubDC03
```

## What is not proved

Signed hardware register wraparound on fixed-width C integers is not modeled here. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
