Claim-Tier: CONJECTURE

```json
{
  "id": "audit-nt-fermat-sorry",
  "source_repo": "https://github.com/example/audit-nt-fermat-sorry",
  "source_commit": "e0371b88aaa8fccd01e9c90893cddfe2a213871d",
  "claim": "For every prime p and integer a coprime to p, a^(p-1) \u2261 1 (mod p).",
  "claim_link": "https://example.org/audit-nt-fermat-sorry.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/FermatLittle.lean",
    "name": "fermat_little_mod",
    "lean": "theorem fermat_little_mod (p a : Nat) (hp : Prime p) (hcop : Nat.gcd a p = 1) : (a ^ (p - 1)) % p = 1"
  },
  "independent_statement": {
    "lean": "theorem fermat_little_mod_ind (p a : Nat) (hp : Prime p) (hcop : Nat.gcd a p = 1) : (a ^ (p - 1)) % p = 1",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "`lake comparator --paranoid` rejected solution due to illegal `sorryAx` axiom in helper lemma",
  "axioms": [
    "propext",
    "sorryAx"
  ],
  "verdict": "does not build",
  "reviewer": null
}
```

## What is not proved

- `lake comparator --paranoid` rejected solution due to illegal `sorryAx` axiom in helper lemma.
- Real-world deployment behavior outside the formal Lean statement `fermat_little_mod`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
