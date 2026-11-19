Claim-Tier: VERIFIED

```json
{
  "id": "audit-linalg-farkas-converse",
  "source_repo": "https://github.com/example/audit-linalg-farkas-converse",
  "source_commit": "c0b983bfb85aaef487e40d310dfe0b381e4a62c9",
  "claim": "If a rational system A x = b with x >= 0 is infeasible, then there exists y with y^T A >= 0 and y^T b < 0.",
  "claim_link": "https://example.org/audit-linalg-farkas-converse.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/FarkasEasyDir.lean",
    "name": "farkas_soundness_only",
    "lean": "theorem farkas_soundness_only (A : Mat) (b y : Vec) (hyA : nonneg (mulT y A)) (hyb : dot y b < 0) : \u00ac\u2203 x, nonneg x \u2227 mulVec A x = b"
  },
  "independent_statement": {
    "lean": "theorem farkas_completeness_ind (A : Mat) (b : Vec) (hinf : \u00ac\u2203 x, nonneg x \u2227 mulVec A x = b) : \u2203 y, nonneg (mulT y A) \u2227 dot y b < 0",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "proves only the easy soundness direction (dual witness implies infeasibility), not completeness (infeasibility implies witness exists)",
  "axioms": [
    "propext",
    "Classical.choice",
    "Quot.sound"
  ],
  "verdict": "weaker",
  "reviewer": null
}
```

## What is not proved

- proves only the easy soundness direction (dual witness implies infeasibility), not completeness (infeasibility implies witness exists).
- Real-world deployment behavior outside the formal Lean statement `farkas_soundness_only`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
