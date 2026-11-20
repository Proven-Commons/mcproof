Claim-Tier: VERIFIED

```json
{
  "id": "audit-linalg-ivmul-pos-only",
  "source_repo": "https://github.com/example/audit-linalg-ivmul-pos-only",
  "source_commit": "d1c5d8db778c01fea5afc4979852c664e98d659a",
  "claim": "Closed rational interval multiplication encloses x * y for all real/rational x in [a1, b1] and y in [a2, b2].",
  "claim_link": "https://example.org/audit-linalg-ivmul-pos-only.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/IvMulPos.lean",
    "name": "iv_mul_nonneg_only",
    "lean": "theorem iv_mul_nonneg_only (a1 b1 a2 b2 x y : Int) (ha1 : 0 \u2264 a1) (ha2 : 0 \u2264 a2) (hx : a1 \u2264 x \u2227 x \u2264 b1) (hy : a2 \u2264 y \u2227 y \u2264 b2) : a1 * a2 \u2264 x * y \u2227 x * y \u2264 b1 * b2"
  },
  "independent_statement": {
    "lean": "theorem iv_mul_general (a1 b1 a2 b2 x y : Int) (hx : a1 \u2264 x \u2227 x \u2264 b1) (hy : a2 \u2264 y \u2227 y \u2264 b2) : min4 (a1*a2) (a1*b2) (b1*a2) (b1*b2) \u2264 x * y \u2227 x * y \u2264 max4 (a1*a2) (a1*b2) (b1*a2) (b1*b2)",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "assumes `0 <= a1` and `0 <= a2`, failing on negative interval endpoints",
  "axioms": [
    "propext"
  ],
  "verdict": "weaker",
  "reviewer": null
}
```

## What is not proved

- assumes `0 <= a1` and `0 <= a2`, failing on negative interval endpoints.
- Real-world deployment behavior outside the formal Lean statement `iv_mul_nonneg_only`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
