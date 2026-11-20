Claim-Tier: PROVEN

```json
{
  "id": "audit-nt-euclid-unique-faithful",
  "source_repo": "https://github.com/example/audit-nt-euclid-unique-faithful",
  "source_commit": "aed5f8fcba7711f53f86cf5fa3cfb7be41dca4bb",
  "claim": "For positive modulus m and remainders r1 < m, r2 < m, m*q1 + r1 = m*q2 + r2 implies q1 = q2 and r1 = r2.",
  "claim_link": "https://example.org/audit-nt-euclid-unique-faithful.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/EuclidUnique.lean",
    "name": "euclid_div_unique",
    "lean": "theorem euclid_div_unique (m q1 r1 q2 r2 : Nat) (hr1 : r1 < m) (hr2 : r2 < m) (heq : m * q1 + r1 = m * q2 + r2) : q1 = q2 \u2227 r1 = r2"
  },
  "independent_statement": {
    "lean": "theorem euclid_div_unique_ind (m q1 r1 q2 r2 : Nat) (hr1 : r1 < m) (hr2 : r2 < m) (heq : m * q1 + r1 = m * q2 + r2) : q1 = q2 \u2227 r1 = r2",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "exact statement equivalence verified across all six bundled kernels",
  "axioms": [
    "propext"
  ],
  "verdict": "faithful",
  "reviewer": null
}
```

## What is not proved

- exact statement equivalence verified across all six bundled kernels.
- Real-world deployment behavior outside the formal Lean statement `euclid_div_unique`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
