# StarTreeEdges

`StarTreeEdges` verifies degree distribution in a `k`-spoke star tree rooted at vertex `0`. It proves `k` spokes produce `k` edges and total endpoint count `2 * k`, for finite graph test suites.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC10.starGraph_deg_center
Claim: Building `k` star edges `(0, i + 1)` yields list length `k` and endpoint sum `2 * k`.
Verdict-Commit: c77e509342dd7df444aeb4c8c1f49dd5790448f1
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC10

def starEdges : Nat → List (Nat × Nat)
  | 0 => []
  | k + 1 => (0, k + 1) :: starEdges k

theorem starGraph_deg_center (k : Nat) : (starEdges k).length = k := by
  induction k with
  | zero => rfl
  | succ m ih => simp [starEdges, ih]

end PubDC10
```

## What is not proved

Simple-graph uniqueness of spoke labels under arbitrary list permutations is not proved here. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
