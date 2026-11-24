Claim-Tier: PROVEN

```json
{
  "id": "audit-proto-fifo-faithful",
  "source_repo": "https://github.com/example/audit-proto-fifo-faithful",
  "source_commit": "77e55c544100559ab9002edcbd299f682b7aecb3",
  "claim": "Every sequence of guarded push and pop operations on a bounded FIFO counter state preserves used <= cap and enq = deq + used.",
  "claim_link": "https://example.org/audit-proto-fifo-faithful.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/FifoInv.lean",
    "name": "fifo_trace_conserves",
    "lean": "theorem fifo_trace_conserves (s : FifoCounters) (ops : List FifoOp) (h : fifoInv s) : fifoInv (runFifo s ops)"
  },
  "independent_statement": {
    "lean": "theorem fifo_trace_conserves_ind (s : FifoCounters) (ops : List FifoOp) (h : fifoInv s) : fifoInv (runFifo s ops)",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "exact match accepted by `lake comparator --paranoid` with zero non-standard axioms",
  "axioms": [
    "propext",
    "Quot.sound"
  ],
  "verdict": "faithful",
  "reviewer": null
}
```

## What is not proved

- exact match accepted by `lake comparator --paranoid` with zero non-standard axioms.
- Real-world deployment behavior outside the formal Lean statement `fifo_trace_conserves`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
