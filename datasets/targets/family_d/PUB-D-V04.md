# PathTreeInv

`PathTreeInv` verifies vertex-edge counts on an `n`-edge linear path graph `0 - 1 - ... - n`. It gives a clean sanity theorem for finite graph generators.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV04.pathGraph_edges_len
Claim: Constructing `pathEdges n` produces exactly `n` edges connecting `n + 1` vertices.
Verdict-Commit: 0630f72d9cdcab612d0628e86f39d8202cf8ff06
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV04

def pathEdges : Nat → List (Nat × Nat)
  | 0 => []
  | n + 1 => (n, n + 1) :: pathEdges n

theorem pathGraph_edges_len (n : Nat) : (pathEdges n).length + 1 = n + 1 := by
  induction n with
  | zero => rfl
  | succ m ih =>
    simp only [pathEdges, List.length_cons]
    omega

end PubDV04
```

## What is not proved

Diameter and shortest-path uniqueness on `pathEdges n` are tested outside this proof. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
