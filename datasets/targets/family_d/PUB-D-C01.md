# ModAddZero

This note documents the `ModAddZero` modular cancellation check for exact residue calculators. It proves that adding an exact multiple of `m` leaves the remainder unchanged, for engineers auditing modular arithmetic kernels.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC01.mod_add_multiple_cancel
Claim: Adding any integer multiple `m * q` to `a` preserves `(a + m * q) % m = a % m` on natural numbers.
Verdict-Commit: 3db679d4d44863ebc0198f098f9ffcf147434021
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC01

theorem mod_add_multiple_cancel (a m q : Nat) : (a + m * q) % m = a % m := by
  induction q with
  | zero => simp
  | succ k ih =>
    rw [Nat.mul_succ, ← Nat.add_assoc, Nat.add_mod_right, ih]

end PubDC01
```

## What is not proved

Input parser bounds and 64-bit machine word overflow before lifting to `Nat` remain unproved. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
