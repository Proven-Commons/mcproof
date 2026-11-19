# BipartiteFlip

`BipartiteFlip` checks color-inversion symmetry on 2-colored graphs. It proves flipping `0 <-> 1` on both endpoints of a properly colored edge keeps the endpoints distinct, for graph-coloring auditors.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC09.flipColor_preserves_diff
Claim: For colors `c1, c2` in `{0, 1}` with `c1 != c2`, swapping `1 - c` yields valid `{0, 1}` colors that remain unequal.
Verdict-Commit: 4f51b92a3020a43eca03eaf4e09f7b6914339861
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC09

def flipBit (c : Nat) : Nat := 1 - c

theorem flipColor_preserves_diff (c1 c2 : Nat) (h1 : c1 ≤ 1) (h2 : c2 ≤ 1) (hne : c1 ≠ c2) :
    flipBit c1 ≤ 1 ∧ flipBit c2 ≤ 1 ∧ flipBit c1 ≠ flipBit c2 := by
  unfold flipBit
  omega

end PubDC09
```

## What is not proved

Odd-cycle detection on non-bipartite inputs is handled by an external witness checker. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
