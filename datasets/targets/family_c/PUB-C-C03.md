Claim-Tier: CONJECTURE

```json
{
  "id": "audit-nt-bezout-nat-trap",
  "source_repo": "https://github.com/example/audit-nt-bezout-nat-trap",
  "source_commit": "732b2e2ec845fc025ac3369d86c0118553e241c8",
  "claim": "For all nonzero integers a and b, there exist integers x and y such that a*x + b*y = gcd(a, b).",
  "claim_link": "https://example.org/audit-nt-bezout-nat-trap.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/BezoutNat.lean",
    "name": "bezout_nat_only",
    "lean": "theorem bezout_nat_only (a b : Nat) (ha : a > 0) (hb : b > 0) : \u2203 x y : Int, (a : Int) * x + (b : Int) * y = Int.ofNat (Nat.gcd a b)"
  },
  "independent_statement": {
    "lean": "theorem bezout_all_nonzero_int (a b : Int) (ha : a \u2260 0) (hb : b \u2260 0) : \u2203 x y : Int, a * x + b * y = Int.ofNat (Int.natAbs a |>.gcd (Int.natAbs b))",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "restricts `a, b` to positive `Nat` instead of all nonzero `Int` (omitting negative integers)",
  "axioms": [
    "propext"
  ],
  "verdict": "weaker",
  "reviewer": null
}
```

## What is not proved

- restricts `a, b` to positive `Nat` instead of all nonzero `Int` (omitting negative integers).
- Real-world deployment behavior outside the formal Lean statement `bezout_nat_only`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
