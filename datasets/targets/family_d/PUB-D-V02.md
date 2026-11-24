# ModIdem

`ModIdem` proves idempotence of remainder reduction `(n % m) % m = n % m` in stock Lean 4. It supports canonical modular normalizers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV02.mod_idem_nat
Claim: Applying `% m` a second time produces the exact same natural number `(n % m) % m = n % m`.
Verdict-Commit: ff0395e5d39d8230936868ee1bb112e8d16617bb
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV02

theorem mod_idem_nat (n m : Nat) : (n % m) % m = n % m := by
  exact Nat.mod_mod n m

end PubDV02
```

## What is not proved

Signed remainder conventions in C versus Euclidean remainder in Python must be aligned at FFI boundaries. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
