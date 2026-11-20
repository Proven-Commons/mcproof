# RevInvolution

`RevInvolution` verifies bijection and length conservation when reversing finite combinatorial sequences. It proves reversing twice restores the original list and preserves length, for permutation checkers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC07.reverse_involutive_len
Claim: Every list `xs : List Nat` satisfies `xs.reverse.reverse = xs` and `xs.reverse.length = xs.length`.
Verdict-Commit: 5777b659ecb566c29a3a9ed9627c61635be8a8b2
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC07

theorem reverse_involutive_len (xs : List Nat) :
    xs.reverse.reverse = xs ∧ xs.reverse.length = xs.length := by
  exact ⟨List.reverse_reverse xs, List.length_reverse⟩

end PubDC07
```

## What is not proved

In-place array mutation in Python or Rust wrappers is outside this functional list model. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
