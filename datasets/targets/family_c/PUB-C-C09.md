Claim-Tier: CONJECTURE

```json
{
  "id": "audit-comb-pigeon-vacuous",
  "source_repo": "https://github.com/example/audit-comb-pigeon-vacuous",
  "source_commit": "f26136f9722272284ca1cf08a8163596c49ee69d",
  "claim": "Every mapping from n+1 elements into n buckets assigns at least two distinct elements to the same bucket.",
  "claim_link": "https://example.org/audit-comb-pigeon-vacuous.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/PigeonVacuous.lean",
    "name": "pigeonhole_fin",
    "lean": "theorem pigeonhole_fin (n : Nat) (f : Nat \u2192 Nat) (hvac : n < 0) : \u2203 i j, i < j \u2227 j \u2264 n \u2227 f i = f j"
  },
  "independent_statement": {
    "lean": "theorem pigeonhole_fin_ind (n : Nat) (f : Nat \u2192 Nat) (hrange : \u2200 i, i \u2264 n \u2192 f i < n) : \u2203 i j, i < j \u2227 j \u2264 n \u2227 f i = f j",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "replaces valid range hypothesis with impossible `n < 0` on `Nat`, making the lab statement vacuously true",
  "axioms": [
    "propext"
  ],
  "verdict": "weaker",
  "reviewer": null
}
```

## What is not proved

- replaces valid range hypothesis with impossible `n < 0` on `Nat`, making the lab statement vacuously true.
- Real-world deployment behavior outside the formal Lean statement `pigeonhole_fin`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
