# PairCount

`PairCount` proves the combinatorial split `n * n = n + 2 * offDiag(n)` separating diagonal pairs `(i, i)` from unordered off-diagonal pairs `{i, j}`. It backs symmetry reductions in pair-wise checkers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV06.ordered_pairs_diag_split
Claim: Defining `offDiag 0 = 0` and `offDiag (n + 1) = offDiag n + n` yields `n + 2 * offDiag n = n * n`.
Verdict-Commit: b93e3378c535b7831056a4864d52731e1fddcacc
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV06

def offDiag : Nat → Nat
  | 0 => 0
  | n + 1 => offDiag n + n

theorem ordered_pairs_diag_split (n : Nat) : n + 2 * offDiag n = n * n := by
  induction n with
  | zero => rfl
  | succ m ih =>
    simp only [offDiag, Nat.mul_add]
    rw [Nat.add_mul m 1 m, Nat.one_mul, Nat.mul_one]
    omega

end PubDV06
```

## What is not proved

Memory layout of upper-triangular packed arrays in C is outside this arithmetic identity. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
