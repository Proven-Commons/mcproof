Claim-Tier: CONJECTURE

```json
{
  "id": "audit-proto-mutex-different",
  "source_repo": "https://github.com/example/audit-proto-mutex-different",
  "source_commit": "795f10a9c1e18aecdcd65ba75c83b2a7501108ce",
  "claim": "No two distinct clients hold the ticket lock simultaneously in any reachable state.",
  "claim_link": "https://example.org/audit-proto-mutex-different.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/TicketInit.lean",
    "name": "ticket_init_zero",
    "lean": "theorem ticket_init_zero : (TicketLock.mk 0 0).serving = 0"
  },
  "independent_statement": {
    "lean": "theorem ticket_reachable_mutex (s : TicketLock) (hr : Reachable s) (c1 c2 : Nat) : Holds s c1 \u2192 Holds s c2 \u2192 c1 = c2",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "proves only initial field value `serving = 0` rather than reachable mutual exclusion",
  "axioms": [
    "propext"
  ],
  "verdict": "different",
  "reviewer": null
}
```

## What is not proved

- proves only initial field value `serving = 0` rather than reachable mutual exclusion.
- Real-world deployment behavior outside the formal Lean statement `ticket_init_zero`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
