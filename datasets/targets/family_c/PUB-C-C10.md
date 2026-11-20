Claim-Tier: PROVEN

```json
{
  "id": "audit-comb-handshake-faithful",
  "source_repo": "https://github.com/example/audit-comb-handshake-faithful",
  "source_commit": "a124132251b1a8f71feb781afd9ec257fda84350",
  "claim": "In every finite undirected edge list, the total endpoint count equals twice the number of edges.",
  "claim_link": "https://example.org/audit-comb-handshake-faithful.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/Handshake.lean",
    "name": "endpoint_sum_eq_two_mul",
    "lean": "theorem endpoint_sum_eq_two_mul (es : List (Nat \u00d7 Nat)) : endpointCount es = 2 * es.length"
  },
  "independent_statement": {
    "lean": "theorem endpoint_sum_eq_two_mul_ind (es : List (Nat \u00d7 Nat)) : endpointCount es = 2 * es.length",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "exact structural match verified by `lake comparator --paranoid` with standard axioms only",
  "axioms": [
    "propext",
    "Quot.sound"
  ],
  "verdict": "faithful",
  "reviewer": null
}
```

## What is not proved

- exact structural match verified by `lake comparator --paranoid` with standard axioms only.
- Real-world deployment behavior outside the formal Lean statement `endpoint_sum_eq_two_mul`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
