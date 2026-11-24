# MapBijectionLen

`MapBijectionLen` checks cardinality preservation under list mapping `xs.map f`. It supports finite combinatorial bijection scripts.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV05.map_preserves_card
Claim: For every function `f : Nat → Nat` and finite list `xs`, `(xs.map f).length = xs.length`.
Verdict-Commit: b84871e677614ba8c9ed35406d080ee42237a4e9
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV05

theorem map_preserves_card (f : Nat → Nat) (xs : List Nat) : (xs.map f).length = xs.length := by
  simp

end PubDV05
```

## What is not proved

Injectivity of `f` (needed to preserve duplicate-freedom `Nodup`) is not assumed or proved here. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
