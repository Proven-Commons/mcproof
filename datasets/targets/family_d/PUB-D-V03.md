# BezoutScale

`BezoutScale` proves linear scaling of Bezout witnesses from `a * x + b * y = g` to any multiple `g * c`. It underpins exact linear Diophantine solvers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV03.bezout_scale_rhs
Claim: If `a * x + b * y = g` over `Int`, then `a * (x * c) + b * (y * c) = g * c` for every `c : Int`.
Verdict-Commit: 019f86a5da87b7e852a8b36afe8f1b3ce142cce7
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV03

theorem bezout_scale_rhs (a b g x y c : Int) (h : a * x + b * y = g) :
    a * (x * c) + b * (y * c) = g * c := by
  rw [← Int.mul_assoc a x c, ← Int.mul_assoc b y c, ← Int.add_mul, h]

end PubDV03
```

## What is not proved

Minimality of the scaled witness `(x * c, y * c)` is not claimed. Lattice reduction is separate. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
