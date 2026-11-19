Claim-Tier: VERIFIED

```json
{
  "id": "audit-linalg-det-diag-only",
  "source_repo": "https://github.com/example/audit-linalg-det-diag-only",
  "source_commit": "5d6855b204baf25ccde2c3d1356a7895b3a87e72",
  "claim": "For all 2x2 integer matrices A and B, det(A * B) = det(A) * det(B).",
  "claim_link": "https://example.org/audit-linalg-det-diag-only.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/Det2Diag.lean",
    "name": "det2_mul_diag",
    "lean": "theorem det2_mul_diag (a d p s : Int) : det2 (mul2 \u27e8a, 0, 0, d\u27e9 \u27e8p, 0, 0, s\u27e9) = det2 \u27e8a, 0, 0, d\u27e9 * det2 \u27e8p, 0, 0, s\u27e9"
  },
  "independent_statement": {
    "lean": "theorem det2_mul_all (A B : Mat2) : det2 (mul2 A B) = det2 A * det2 B",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "proves determinant multiplicativity only when off-diagonal entries are zero rather than general 2x2 matrices",
  "axioms": [
    "propext"
  ],
  "verdict": "weaker",
  "reviewer": null
}
```

## What is not proved

- proves determinant multiplicativity only when off-diagonal entries are zero rather than general 2x2 matrices.
- Real-world deployment behavior outside the formal Lean statement `det2_mul_diag`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
