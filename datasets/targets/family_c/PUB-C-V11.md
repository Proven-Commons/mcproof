Claim-Tier: VERIFIED

```json
{
  "id": "audit-proto-2pc-liveness-gap",
  "source_repo": "https://github.com/example/audit-proto-2pc-liveness-gap",
  "source_commit": "17e8cc48753b33f872a273bb9543ce15c1e787f6",
  "claim": "Two-Phase Commit guarantees both safety (no conflicting decisions) and eventual termination under arbitrary message loss.",
  "claim_link": "https://example.org/audit-proto-2pc-liveness-gap.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/TwoPCSafe.lean",
    "name": "twoPC_safety_only",
    "lean": "theorem twoPC_safety_only (s : Coord2PC) (allYes : Bool) (h : RealSafe s) : RealSafe (decide2PC s allYes)"
  },
  "independent_statement": {
    "lean": "theorem twoPC_safe_and_live (tr : InfiniteTrace) : AlwaysSafe tr \u2227 EventuallyDecidesUnderLoss tr",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "proves single-step safety only; synchronous/lossy 2PC is famously blocking and does not prove termination",
  "axioms": [
    "propext"
  ],
  "verdict": "weaker",
  "reviewer": null
}
```

## What is not proved

- proves single-step safety only; synchronous/lossy 2PC is famously blocking and does not prove termination.
- Real-world deployment behavior outside the formal Lean statement `twoPC_safety_only`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
