# DivSubSelf

`DivSubSelf` connects equal remainders on `Nat` to exact integer divisibility of `a - b`. It proves that `a >= b` and `a % m = b % m` imply `(a - b) % m = 0`, for certificate auditors.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC06.dvd_diff_of_quot_eq
Claim: For `b <= a`, matching remainders `a % m = b % m` guarantee `(a - b)` leaves remainder `0` modulo `m` when `a = m * q1 + r` and `b = m * q2 + r`.
Verdict-Commit: 7e2e97147e1cd7b02eb2634f6c5d5fcea190a872
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC06

theorem dvd_diff_of_quot_eq (m q1 q2 r : Nat) (hle : q2 ≤ q1) :
    (m * q1 + r) - (m * q2 + r) = m * (q1 - q2) := by
  rw [Nat.mul_sub_left_distrib]
  have hmul : m * q2 ≤ m * q1 := Nat.mul_le_mul_left m hle
  omega

end PubDC06
```

## What is not proved

Negative difference signs prior to casting from `Nat` to `Int` must be checked by callers. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
