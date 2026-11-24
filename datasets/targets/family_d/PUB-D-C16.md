# TransposeDet

`TransposeDet` checks determinant invariance under matrix transposition on `2x2` integer matrices. It proves `det(A^T) = det(A)`, for exact Cramer and dual-system checkers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC16.det2_transpose_eq
Claim: Transposing off-diagonal entries `(b, c) -> (c, b)` leaves `a * d - c * b = a * d - b * c`.
Verdict-Commit: 04a942c6e1a44d4a5b92e94d053fd74c28447271
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC16

def det2 (a b c d : Int) : Int := a * d - b * c

theorem det2_transpose_eq (a b c d : Int) : det2 a c b d = det2 a b c d := by
  unfold det2
  rw [Int.mul_comm c b]

end PubDC16
```

## What is not proved

Extension to arbitrary `n x n` permutation-sign products is handled in external Python verifiers. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
