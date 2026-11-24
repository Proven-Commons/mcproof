# FilterPart

`FilterPart` checks disjoint predicate counting over finite lists for combinatorial sieves. It proves elements matching `p` plus elements failing `p` equal `xs.length`, for counting-argument verifiers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC11.partition_count_sum
Claim: For every boolean predicate `p : Nat → Bool` and list `xs`, `(xs.filter p).length + (xs.filter (fun x => !p x)).length = xs.length`.
Verdict-Commit: bb593d6d36a7d99fb58c520f8ad8425c5a6b70df
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC11

theorem partition_count_sum (p : Nat → Bool) (xs : List Nat) :
    (xs.filter p).length + (xs.filter (fun x => !p x)).length = xs.length := by
  induction xs with
  | nil => rfl
  | cons x rest ih =>
    cases hp : p x <;> simp [List.filter, hp] <;> omega

end PubDC11
```

## What is not proved

Equivalence between the boolean predicate `p` and an external mathematical set definition rests on specification review. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
