# CongSymmTrans

`CongSymmTrans` checks equivalence laws for modular congruence `a % m = b % m`. It proves symmetry and transitivity for all moduli `m`, for teams building residue-class verifiers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC05.modCong_equiv
Claim: Modular equality `a % m = b % m` is symmetric and transitive across all natural numbers.
Verdict-Commit: 774f855d09cf67c362fd8278a2ef2d401125d602
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC05

def modCong (m a b : Nat) : Prop := a % m = b % m

theorem modCong_equiv (m a b c : Nat) :
    (modCong m a b → modCong m b a) ∧ (modCong m a b → modCong m b c → modCong m a c) := by
  unfold modCong
  refine ⟨?_, ?_⟩
  · intro h; exact h.symm
  · intro h1 h2; exact Eq.trans h1 h2

end PubDC05
```

## What is not proved

Primality of the modulus `m` and existence of multiplicative inverses are not claimed here. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
