# PigeonSum

`PigeonSum` formalizes the discrete averaging pigeonhole bound over bucket counts. It proves that if the sum of `xs` exceeds `xs.length`, at least one bucket holds `>= 2` items, for combinatorial proof authors.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC12.sum_le_len_of_all_le_one
Claim: No list of natural numbers bounded everywhere by `<= 1` can have total sum strictly greater than its length.
Verdict-Commit: 3dfe1e53a80a1789981195015147dec66b94fd5b
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC12

def sumNat : List Nat → Nat
  | [] => 0
  | x :: xs => x + sumNat xs

theorem sum_le_len_of_all_le_one (xs : List Nat) (h : ∀ x ∈ xs, x ≤ 1) : sumNat xs ≤ xs.length := by
  induction xs with
  | nil => simp [sumNat]
  | cons x rest ih =>
    have hx : x ≤ 1 := h x (by simp)
    have hrest : ∀ y ∈ rest, y ≤ 1 := fun y hy => h y (by simp [hy])
    have ihr := ih hrest
    simp only [sumNat, List.length_cons]
    omega

end PubDC12
```

## What is not proved

Constructing the minimum index of the overloaded bucket is delegated to the runtime witness finder. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
